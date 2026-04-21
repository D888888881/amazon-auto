"""调用 scripts/asin_find_project 中的 seller_wizard_main（子进程，避免污染 Django 进程）。"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from django.conf import settings


def _parse_stdout_json(text: str, stderr_lines: list[str]) -> dict:
    """解析子进程 stdout；允许 BOM、前后空白，或混有杂项时提取第一个 JSON 对象/数组。"""
    s = text.lstrip('\ufeff').strip()
    if not s:
        tail = '\n'.join(stderr_lines[-40:]).strip()
        raise RuntimeError(
            'seller_wizard 标准输出为空（未收到 JSON）。'
            + (f'\nstderr 尾部：\n{tail}' if tail else '')
        )
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        dec = json.JSONDecoder()
        data = None
        for i, ch in enumerate(s):
            if ch not in '{[':
                continue
            try:
                data, _end = dec.raw_decode(s, i)
                break
            except json.JSONDecodeError:
                continue
        if data is None:
            tail = '\n'.join(stderr_lines[-40:]).strip()
            raise RuntimeError(
                'seller_wizard 标准输出不是合法 JSON（可能被其它文本污染）。'
                f'\nstdout 前 600 字符：\n{s[:600]}'
                + (f'\n--- stderr 尾部 ---\n{tail}' if tail else '')
            )
    if not isinstance(data, dict):
        raise RuntimeError(
            f'seller_wizard 返回的 JSON 根类型应为对象(dict)，实际为 {type(data).__name__}'
        )
    return data


def run_seller_wizard(
    asins: list[str] | None,
    parity: float,
    cost_overrides: dict | None = None,
    on_stderr_line: Callable[[str], None] | None = None,
) -> dict:
    """
    运行分析子进程。可选 on_stderr_line 用于实时接收子进程 stderr 每一行（含脚本 print 日志）。
    """
    base = Path(settings.BASE_DIR).resolve()
    runner = base / 'scripts' / 'asin_find_project' / 'django_runner_seller_wizard.py'
    if not runner.is_file():
        raise FileNotFoundError(f'未找到脚本：{runner}')
    payload_obj = {'parity': parity}
    if asins:
        payload_obj['asins'] = asins
    if cost_overrides:
        payload_obj['cost_overrides'] = cost_overrides
    payload = json.dumps(payload_obj, ensure_ascii=False).encode('utf-8')

    proc = subprocess.Popen(
        [sys.executable, str(runner)],
        cwd=str(runner.parent),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
    proc.stdin.write(payload)
    proc.stdin.close()

    stderr_lines: list[str] = []

    def drain_stderr() -> None:
        try:
            for raw in iter(proc.stderr.readline, b''):
                if not raw:
                    break
                line = raw.decode('utf-8', errors='replace').rstrip()
                stderr_lines.append(line)
                if on_stderr_line:
                    try:
                        on_stderr_line(line)
                    except Exception:
                        pass
        except Exception:
            pass

    t = threading.Thread(target=drain_stderr, daemon=True)
    t.start()

    stdout = proc.stdout.read()
    rc = proc.wait()
    t.join(timeout=30)

    if rc != 0:
        err = '\n'.join(stderr_lines[-120:]).strip()
        if not err:
            err = stdout.decode('utf-8', errors='replace').strip() or 'seller_wizard 执行失败'
        raise RuntimeError(err)

    out = stdout.decode('utf-8', errors='replace')
    return _parse_stdout_json(out, stderr_lines)


def run_ad_difficulty_for_asins(
    asins: list[str],
    on_stderr_line: Callable[[str], None] | None = None,
) -> dict:
    """按勾选 ASIN 触发广告难度计算（仅更新 ranking_percent 相关）。"""
    base = Path(settings.BASE_DIR).resolve()
    runner = base / 'scripts' / 'asin_find_project' / 'django_runner_ad_difficulty.py'
    if not runner.is_file():
        raise FileNotFoundError(f'未找到脚本：{runner}')
    payload_obj = {'asins': [str(x).strip().upper() for x in asins if str(x).strip()]}
    payload = json.dumps(payload_obj, ensure_ascii=False).encode('utf-8')

    proc = subprocess.Popen(
        [sys.executable, str(runner)],
        cwd=str(runner.parent),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
    proc.stdin.write(payload)
    proc.stdin.close()

    stderr_lines: list[str] = []

    def drain_stderr() -> None:
        try:
            for raw in iter(proc.stderr.readline, b''):
                if not raw:
                    break
                line = raw.decode('utf-8', errors='replace').rstrip()
                stderr_lines.append(line)
                if on_stderr_line:
                    try:
                        on_stderr_line(line)
                    except Exception:
                        pass
        except Exception:
            pass

    t = threading.Thread(target=drain_stderr, daemon=True)
    t.start()

    stdout = proc.stdout.read()
    rc = proc.wait()
    t.join(timeout=30)

    if rc != 0:
        err = '\n'.join(stderr_lines[-120:]).strip()
        if not err:
            err = stdout.decode('utf-8', errors='replace').strip() or '广告难度计算执行失败'
        raise RuntimeError(err)

    out = stdout.decode('utf-8', errors='replace')
    return _parse_stdout_json(out, stderr_lines)
