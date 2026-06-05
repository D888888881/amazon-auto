"""卖家精灵子账号被禁用时自动解禁并重试。"""
from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from django.conf import settings

T = TypeVar('T')

RANK_LOGIN_USER_MARKER = 'rank-login-user'


def is_seller_account_banned_error(exc: BaseException) -> bool:
    """子进程 stderr 中 KeyError: 'rank-login-user' 表示子账号被禁用。"""
    if isinstance(exc, KeyError) and RANK_LOGIN_USER_MARKER in str(exc.args):
        return True
    text = f'{type(exc).__name__}: {exc}'
    return RANK_LOGIN_USER_MARKER in text


def _script_dir() -> Path:
    return Path(settings.BASE_DIR).resolve() / 'scripts' / 'asin_find_project'


def unlock_seller_sub_account(*, on_log: Callable[[str], None] | None = None) -> tuple[bool, str]:
    """
    执行 scripts/asin_find_project/unlock_seller_info.py 解除子账号禁用。
    返回 (是否成功, 说明)。
    """
    script = _script_dir() / 'unlock_seller_info.py'
    if not script.is_file():
        return False, f'未找到解禁脚本：{script}'

    if on_log:
        on_log('正在执行卖家精灵子账号解禁程序…')

    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(_script_dir()),
            capture_output=True,
            text=True,
            timeout=300,
            encoding='utf-8',
            errors='replace',
        )
    except subprocess.TimeoutExpired:
        return False, '解禁脚本执行超时（300s）'
    except OSError as exc:
        return False, f'无法启动解禁脚本：{exc}'

    tail = '\n'.join(
        line for line in (proc.stdout or '').splitlines()[-20:] + (proc.stderr or '').splitlines()[-20:]
        if line.strip()
    )
    if proc.returncode != 0:
        msg = tail or f'exit code {proc.returncode}'
        return False, msg

    if on_log:
        on_log('卖家精灵子账号解禁程序执行完成。')
    return True, tail or 'ok'


def execute_with_seller_unlock_retry(
    fn: Callable[[], T],
    *,
    on_log: Callable[[str], None] | None = None,
    max_unlock_attempts: int = 1,
) -> T:
    """执行 fn；若遇 rank-login-user 则解禁后重试（最多 max_unlock_attempts 次）。"""
    unlocks = 0
    while True:
        try:
            return fn()
        except Exception as exc:
            if unlocks >= max_unlock_attempts or not is_seller_account_banned_error(exc):
                raise
            unlocks += 1
            if on_log:
                on_log('检测到卖家精灵子账号被禁用（rank-login-user），正在自动解禁…')
            ok, msg = unlock_seller_sub_account(on_log=on_log)
            if not ok:
                raise RuntimeError(f'自动解禁失败：{msg}') from exc
            if on_log:
                on_log('解禁成功，正在重试当前步骤…')
            continue
