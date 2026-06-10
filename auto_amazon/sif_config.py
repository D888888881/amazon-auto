"""SIF authorization / token 配置文件读写（与 scripts/asin_find_project 共用目录）。"""
from __future__ import annotations

import sys
from pathlib import Path

from django.conf import settings


def sif_config_dir() -> Path:
    return (
        Path(settings.BASE_DIR).resolve()
        / 'scripts'
        / 'asin_find_project'
        / 'config_file'
    )


def sif_authorization_path() -> Path:
    return sif_config_dir() / 'sif_authorization.txt'


def sif_token_path() -> Path:
    return sif_config_dir() / 'sif_token.txt'


def read_sif_authorization() -> str:
    path = sif_authorization_path()
    if not path.is_file():
        return ''
    return path.read_text(encoding='utf-8').strip()


def write_sif_authorization(value: str) -> None:
    path = sif_authorization_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = (value or '').strip()
    path.write_text(cleaned + ('\n' if cleaned else ''), encoding='utf-8')


def read_sif_token_status() -> dict:
    path = sif_token_path()
    if not path.is_file():
        return {'exists': False, 'preview': '', 'length': 0}
    text = path.read_text(encoding='utf-8').strip()
    if not text or text == '未找到 sif_token':
        return {'exists': False, 'preview': text, 'length': 0}
    preview = f'{text[:20]}…' if len(text) > 20 else text
    return {'exists': True, 'preview': preview, 'length': len(text)}


def _ensure_script_path() -> Path:
    script_dir = Path(settings.BASE_DIR).resolve() / 'scripts' / 'asin_find_project'
    script_path = str(script_dir)
    if script_path not in sys.path:
        sys.path.insert(0, script_path)
    return script_dir


def refresh_sif_token() -> tuple[bool, str]:
    """调用 sif_set_cookie 用当前 authorization 换取 sif_token。"""
    _ensure_script_path()
    try:
        from sif_set_cookie import get_sif_cookie

        token = get_sif_cookie()
    except Exception as exc:
        return False, f'{type(exc).__name__}: {exc}'
    if not token:
        return False, '未从 SIF 响应中获取到 sif_token'
    return True, token
