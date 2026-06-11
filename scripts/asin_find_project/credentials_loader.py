# -*- coding: utf-8 -*-
"""从 config_file 读取网页「凭证配置」保存的卖家精灵相关凭证。"""
from __future__ import annotations

import ast
from pathlib import Path

_CONFIG_DIR = Path(__file__).resolve().parent / 'config_file'

_CHILD_IDS_FILE = _CONFIG_DIR / 'seller_child_ids.txt'
_USERNAME_FILE = _CONFIG_DIR / 'seller_username.txt'
_PASSWORD_FILE = _CONFIG_DIR / 'seller_password.txt'
_AO_LO_TO_N_FILE = _CONFIG_DIR / 'ao_lo_to_n.txt'


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ''
    return path.read_text(encoding='utf-8').strip()


def read_child_ids(*, default: list[str] | None = None) -> list[str]:
    raw = _read_text(_CHILD_IDS_FILE)
    if not raw:
        return list(default or [])
    ids: list[str] = []
    for chunk in raw.replace('\n', ',').split(','):
        s = chunk.strip()
        if s:
            ids.append(s)
    return ids


def read_seller_username(*, default: str = '') -> str:
    return _read_text(_USERNAME_FILE) or default


def read_seller_password(*, default: str = '') -> str:
    return _read_text(_PASSWORD_FILE) or default


def read_ao_lo_to_n_raw() -> str:
    """原样读取文件内容（保留 Python 字面量写法，如 "\\"TOKEN\\""）。"""
    return _read_text(_AO_LO_TO_N_FILE)


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

    # 已是运行时格式："TOKEN="（仅首尾各一个双引号，无反斜杠）
    if (
        s.startswith('"')
        and s.endswith('"')
        and '\\' not in s
        and s.count('"') == 2
    ):
        return s

    # Python 字符串字面量："\"TOKEN=\"" —— 与 ast.literal_eval 求值一致
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

    # 兜底：去掉转义与多余引号后重建
    inner = s.replace('\\"', '"').replace("\\'", "'").strip()
    while len(inner) >= 2 and inner[0] == '"' and inner[-1] == '"':
        inner = inner[1:-1]
    inner = inner.strip('"')
    if not inner:
        return ''
    return f'"{inner}"'


def read_ao_lo_to_n(*, default: str = '') -> str:
    """供 Cookie 使用：读取文件并按 Python 字面量规则求值。"""
    raw = read_ao_lo_to_n_raw()
    if not raw:
        return default
    return resolve_ao_lo_to_n_for_cookie(raw)
