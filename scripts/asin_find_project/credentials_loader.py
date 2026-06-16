# -*- coding: utf-8 -*-
"""从 config_file 读取网页「凭证配置」保存的卖家精灵相关凭证（单次 / 大批量两套）。"""
from __future__ import annotations

import ast
import os
from pathlib import Path

_CONFIG_DIR = Path(__file__).resolve().parent / 'config_file'

_PROFILE_FILES = {
    'single': {
        'child_ids': _CONFIG_DIR / 'seller_child_ids.txt',
        'username': _CONFIG_DIR / 'seller_username.txt',
        'password': _CONFIG_DIR / 'seller_password.txt',
        'ao_lo_to_n': _CONFIG_DIR / 'ao_lo_to_n.txt',
    },
    'bulk': {
        'child_ids': _CONFIG_DIR / 'seller_bulk_child_ids.txt',
        'username': _CONFIG_DIR / 'seller_bulk_username.txt',
        'password': _CONFIG_DIR / 'seller_bulk_password.txt',
        'ao_lo_to_n': _CONFIG_DIR / 'seller_bulk_ao_lo_to_n.txt',
    },
}


def credential_profile() -> str:
    """Worker 环境变量 SELLER_CREDENTIAL_PROFILE：single | bulk。"""
    p = os.environ.get('SELLER_CREDENTIAL_PROFILE', 'single').strip().lower()
    return 'bulk' if p == 'bulk' else 'single'


def _paths(profile: str | None = None) -> dict[str, Path]:
    key = 'bulk' if (profile or credential_profile()) == 'bulk' else 'single'
    return _PROFILE_FILES[key]


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ''
    return path.read_text(encoding='utf-8').strip()


def _bulk_active_credentials() -> dict[str, str] | None:
    try:
        from bulk_account_pool import get_active_account_credentials

        return get_active_account_credentials()
    except ImportError:
        return None


def read_child_ids(*, profile: str | None = None, default: list[str] | None = None) -> list[str]:
    prof = profile or credential_profile()
    if prof == 'bulk':
        cred = _bulk_active_credentials()
        if cred and cred.get('child_id'):
            return [cred['child_id']]
    raw = _read_text(_paths(profile)['child_ids'])
    if not raw:
        return list(default or [])
    ids: list[str] = []
    for chunk in raw.replace('\n', ',').split(','):
        s = chunk.strip()
        if s:
            ids.append(s)
    return ids


def read_seller_username(*, profile: str | None = None, default: str = '') -> str:
    prof = profile or credential_profile()
    if prof == 'bulk':
        cred = _bulk_active_credentials()
        if cred and cred.get('username'):
            return cred['username']
    return _read_text(_paths(profile)['username']) or default


def read_seller_password(*, profile: str | None = None, default: str = '') -> str:
    prof = profile or credential_profile()
    if prof == 'bulk':
        cred = _bulk_active_credentials()
        if cred and cred.get('password'):
            return cred['password']
    return _read_text(_paths(profile)['password']) or default


def read_ao_lo_to_n_raw(*, profile: str | None = None) -> str:
    """原样读取文件内容（保留 Python 字面量写法）。"""
    prof = profile or credential_profile()
    if prof == 'bulk':
        cred = _bulk_active_credentials()
        if cred and cred.get('ao_lo_to_n'):
            return cred['ao_lo_to_n']
    return _read_text(_paths(profile)['ao_lo_to_n'])


def resolve_ao_lo_to_n_for_cookie(value: str) -> str:
    """
    将配置中的 Python 字符串字面量转为运行时 Cookie 值。

    文件/表单可保存：  "\\"53481218714...=\\""  （Python 源码写法，含反斜杠）
    Cookie 实际赋值：  "53481218714...="      （与 hardcoded "\\"TOKEN\\"" 求值后一致）
    """
    if not value:
        return ''
    s = value.strip()
    if not s:
        return ''

    if (
        s.startswith('"')
        and s.endswith('"')
        and '\\' not in s
        and s.count('"') == 2
    ):
        return s

    if '\\' in s or s.count('"') > 2:
        try:
            lit = s
            if not (lit.startswith('"') or lit.startswith("'")):
                lit = f'"{lit}"'
            parsed = ast.literal_eval(lit)
            if isinstance(parsed, str) and parsed.startswith('"') and parsed.endswith('"'):
                return parsed
        except (SyntaxError, ValueError):
            pass

    inner = s.replace('\\"', '"').replace("\\'", "'").strip()
    while len(inner) >= 2 and inner[0] == '"' and inner[-1] == '"':
        inner = inner[1:-1]
    inner = inner.strip('"')
    if not inner:
        return ''
    return f'"{inner}"'


def read_ao_lo_to_n(*, profile: str | None = None, default: str = '') -> str:
    """供 Cookie 使用：读取文件并按 Python 字面量规则求值。"""
    raw = read_ao_lo_to_n_raw(profile=profile)
    if not raw:
        return default
    return resolve_ao_lo_to_n_for_cookie(raw)
