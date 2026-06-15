"""在 Worker 进程内直接运行 scripts/asin_find_project（避免每 ASIN 起子进程）。"""
from __future__ import annotations

import asyncio
import io
import os
import sys
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from django.conf import settings


def script_project_dir() -> Path:
    return Path(settings.BASE_DIR).resolve() / 'scripts' / 'asin_find_project'


@contextmanager
def asin_script_cwd():
    """切换 cwd 并确保脚本目录在 sys.path 中。"""
    d = script_project_dir()
    if not d.is_dir():
        raise FileNotFoundError(f'未找到脚本目录：{d}')
    inserted = False
    ds = str(d)
    if ds not in sys.path:
        sys.path.insert(0, ds)
        inserted = True
    prev = os.getcwd()
    os.chdir(d)
    try:
        yield d
    finally:
        os.chdir(prev)
        if inserted:
            try:
                sys.path.remove(ds)
            except ValueError:
                pass


def to_jsonable(obj: Any) -> Any:
    import numpy as np

    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, (np.floating, np.float32, np.float64)):
        return float(obj)
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    if isinstance(obj, (float, int, str, bool)) or obj is None:
        return obj
    return str(obj)


class _LineCallbackWriter(io.TextIOBase):
    """将 stderr 行转发到 on_line 回调。"""

    def __init__(self, on_line: Callable[[str], None] | None, underlying):
        self._on_line = on_line
        self._underlying = underlying
        self._buf = ''

    def write(self, s: str) -> int:
        if self._underlying:
            self._underlying.write(s)
        self._buf += s
        while '\n' in self._buf:
            line, self._buf = self._buf.split('\n', 1)
            line = line.rstrip()
            if line and self._on_line:
                try:
                    self._on_line(line)
                except Exception:
                    pass
        return len(s)

    def flush(self) -> None:
        if self._underlying:
            self._underlying.flush()
        if self._buf.strip() and self._on_line:
            try:
                self._on_line(self._buf.rstrip())
            except Exception:
                pass
            self._buf = ''


def run_seller_wizard_inprocess(
    asins: list[str] | None,
    parity: float,
    cost_overrides: dict | None = None,
    on_stderr_line: Callable[[str], None] | None = None,
) -> dict:
    if on_stderr_line:
        on_stderr_line('PROGRESS:inprocess 模式：正在准备脚本环境…')
    with asin_script_cwd():
        if on_stderr_line:
            on_stderr_line('PROGRESS:正在加载 seller_wizard 模块（首次可能较慢）…')
        from async_seller_wizard_api import seller_wizard_main

        old_stderr = sys.stderr
        if on_stderr_line:
            sys.stderr = _LineCallbackWriter(on_stderr_line, old_stderr)

        stdout_real = sys.stdout
        stdout_buf = io.StringIO()
        sys.stdout = stdout_buf
        try:
            raw = asyncio.run(
                seller_wizard_main(
                    parity,
                    asins=asins,
                    cost_overrides=cost_overrides or None,
                )
            )
        finally:
            sys.stdout = stdout_real
            if on_stderr_line:
                sys.stderr = old_stderr
            leaked = stdout_buf.getvalue()
            if leaked.strip() and on_stderr_line:
                for line in leaked.splitlines():
                    text = line.strip()
                    if text:
                        on_stderr_line(text)

        data = to_jsonable(raw) if raw is not None else {}
        if not isinstance(data, dict):
            raise RuntimeError(
                f'seller_wizard 返回类型应为 dict，实际为 {type(data).__name__}'
            )
        return data


def run_ad_difficulty_inprocess(
    asins: list[str],
    on_stderr_line: Callable[[str], None] | None = None,
) -> dict:
    with asin_script_cwd():
        from async_seller_wizard_api import calculate_ad_difficulty_for_asins

        old_stderr = sys.stderr
        if on_stderr_line:
            sys.stderr = _LineCallbackWriter(on_stderr_line, old_stderr)

        stdout_real = sys.stdout
        stdout_buf = io.StringIO()
        sys.stdout = stdout_buf
        try:
            raw = asyncio.run(
                calculate_ad_difficulty_for_asins(
                    [str(x).strip().upper() for x in asins if str(x).strip()] or None
                )
            )
        finally:
            sys.stdout = stdout_real
            if on_stderr_line:
                sys.stderr = old_stderr

        data = to_jsonable(raw) if raw is not None else {}
        if not isinstance(data, dict):
            raise RuntimeError(
                f'广告难度返回类型应为 dict，实际为 {type(data).__name__}'
            )
        return data
