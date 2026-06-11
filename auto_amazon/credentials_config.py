"""凭证配置读写（SIF + 卖家精灵子账号等，与 scripts/asin_find_project/config_file 共用）。"""
from __future__ import annotations

import sys
from pathlib import Path

from django.conf import settings


def config_dir() -> Path:
    return (
        Path(settings.BASE_DIR).resolve()
        / 'scripts'
        / 'asin_find_project'
        / 'config_file'
    )


def sif_authorization_path() -> Path:
    return config_dir() / 'sif_authorization.txt'


def sif_token_path() -> Path:
    return config_dir() / 'sif_token.txt'


def seller_child_ids_path() -> Path:
    return config_dir() / 'seller_child_ids.txt'


def seller_username_path() -> Path:
    return config_dir() / 'seller_username.txt'


def seller_password_path() -> Path:
    return config_dir() / 'seller_password.txt'


def ao_lo_to_n_path() -> Path:
    return config_dir() / 'ao_lo_to_n.txt'


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = (value or '').strip()
    path.write_text(cleaned + ('\n' if cleaned else ''), encoding='utf-8')


def read_sif_authorization() -> str:
    path = sif_authorization_path()
    if not path.is_file():
        return ''
    return path.read_text(encoding='utf-8').strip()


def write_sif_authorization(value: str) -> None:
    _write_text(sif_authorization_path(), value)


def read_sif_token_status() -> dict:
    path = sif_token_path()
    if not path.is_file():
        return {'exists': False, 'preview': '', 'length': 0}
    text = path.read_text(encoding='utf-8').strip()
    if not text or text == '未找到 sif_token':
        return {'exists': False, 'preview': text, 'length': 0}
    preview = f'{text[:20]}…' if len(text) > 20 else text
    return {'exists': True, 'preview': preview, 'length': len(text)}


def _parse_child_ids(raw: str) -> list[str]:
    ids: list[str] = []
    for chunk in (raw or '').replace('\n', ',').split(','):
        s = chunk.strip()
        if s:
            ids.append(s)
    return ids


def read_seller_child_ids() -> list[str]:
    path = seller_child_ids_path()
    if not path.is_file():
        return []
    return _parse_child_ids(path.read_text(encoding='utf-8'))


def write_seller_child_ids(ids: list[str]) -> None:
    cleaned = [str(i).strip() for i in ids if str(i).strip()]
    _write_text(seller_child_ids_path(), ','.join(cleaned))


def read_seller_username() -> str:
    path = seller_username_path()
    if not path.is_file():
        return ''
    return path.read_text(encoding='utf-8').strip()


def write_seller_username(value: str) -> None:
    _write_text(seller_username_path(), value)


def read_seller_password() -> str:
    path = seller_password_path()
    if not path.is_file():
        return ''
    return path.read_text(encoding='utf-8').strip()


def write_seller_password(value: str) -> None:
    _write_text(seller_password_path(), value)


def read_ao_lo_to_n() -> str:
    """网页表单展示：原样读取，不改动用户保存的 Python 字面量。"""
    _ensure_script_path()
    from credentials_loader import read_ao_lo_to_n_raw

    return read_ao_lo_to_n_raw()


def write_ao_lo_to_n(value: str) -> None:
    """原样保存用户输入（如 "\\"5348...=\\""），写入 Cookie 时再求值。"""
    _write_text(ao_lo_to_n_path(), (value or '').strip())


def read_seller_credentials_form() -> dict:
    """供配置页表单展示（不向模板暴露明文密码）。"""
    _ensure_script_path()
    from credentials_loader import read_ao_lo_to_n_raw, resolve_ao_lo_to_n_for_cookie

    child_ids = read_seller_child_ids()
    ao_lo_raw = read_ao_lo_to_n_raw()
    ao_lo_resolved = resolve_ao_lo_to_n_for_cookie(ao_lo_raw) if ao_lo_raw else ''
    username = read_seller_username()
    has_password = bool(read_seller_password())
    checklist = [
        {'label': '子账号 ID', 'done': bool(child_ids)},
        {'label': '登录用户名', 'done': bool(username)},
        {'label': '登录密码', 'done': has_password},
        {'label': 'ao_lo_to_n', 'done': bool(ao_lo_resolved)},
    ]
    done_count = sum(1 for x in checklist if x['done'])
    return {
        'child_ids': ','.join(child_ids),
        'seller_username': username,
        'has_password': has_password,
        'ao_lo_to_n': ao_lo_raw,
        'has_child_ids': bool(child_ids),
        'has_ao_lo_to_n': bool(ao_lo_resolved),
        'seller_ready': bool(child_ids and username and has_password and ao_lo_resolved),
        'checklist': checklist,
        'checklist_done': done_count,
        'checklist_total': len(checklist),
    }


def _mask_secret(text: str, *, head: int = 14, tail: int = 6) -> str:
    if not text:
        return ''
    if len(text) <= head + tail + 3:
        return text[:4] + '…' if len(text) > 4 else text
    return f'{text[:head]}…{text[-tail:]}'


def read_credentials_page_context() -> dict:
    """凭证配置页完整上下文。"""
    auth = read_sif_authorization()
    token_status = read_sif_token_status()
    seller = read_seller_credentials_form()
    return {
        'authorization': auth,
        'has_authorization': bool(auth),
        'authorization_preview': _mask_secret(auth, head=18, tail=8),
        'token_status': token_status,
        'sif_ready': bool(auth) and bool(token_status.get('exists')),
        'seller': seller,
        'ao_lo_preview': _mask_secret(seller.get('ao_lo_to_n') or '', head=12, tail=8),
    }


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
