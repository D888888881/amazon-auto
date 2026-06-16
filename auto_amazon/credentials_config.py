"""凭证配置读写（SIF + 卖家精灵单次/大批量子账号，与 config_file 共用）。"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

from django.conf import settings

CredentialProfile = Literal['single', 'bulk']


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


def _profile_paths(profile: CredentialProfile) -> dict[str, Path]:
    if profile == 'bulk':
        return {
            'child_ids': config_dir() / 'seller_bulk_child_ids.txt',
            'username': config_dir() / 'seller_bulk_username.txt',
            'password': config_dir() / 'seller_bulk_password.txt',
            'ao_lo_to_n': config_dir() / 'seller_bulk_ao_lo_to_n.txt',
        }
    return {
        'child_ids': config_dir() / 'seller_child_ids.txt',
        'username': config_dir() / 'seller_username.txt',
        'password': config_dir() / 'seller_password.txt',
        'ao_lo_to_n': config_dir() / 'ao_lo_to_n.txt',
    }


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


def read_seller_child_ids(profile: CredentialProfile = 'single') -> list[str]:
    path = _profile_paths(profile)['child_ids']
    if not path.is_file():
        return []
    return _parse_child_ids(path.read_text(encoding='utf-8'))


def write_seller_child_ids(ids: list[str], profile: CredentialProfile = 'single') -> None:
    cleaned = [str(i).strip() for i in ids if str(i).strip()]
    _write_text(_profile_paths(profile)['child_ids'], ','.join(cleaned))


def read_seller_username(profile: CredentialProfile = 'single') -> str:
    path = _profile_paths(profile)['username']
    if not path.is_file():
        return ''
    return path.read_text(encoding='utf-8').strip()


def write_seller_username(value: str, profile: CredentialProfile = 'single') -> None:
    _write_text(_profile_paths(profile)['username'], value)


def read_seller_password(profile: CredentialProfile = 'single') -> str:
    path = _profile_paths(profile)['password']
    if not path.is_file():
        return ''
    return path.read_text(encoding='utf-8').strip()


def write_seller_password(value: str, profile: CredentialProfile = 'single') -> None:
    _write_text(_profile_paths(profile)['password'], value)


def read_ao_lo_to_n(profile: CredentialProfile = 'single') -> str:
    """网页表单展示：原样读取。"""
    _ensure_script_path()
    from credentials_loader import read_ao_lo_to_n_raw

    return read_ao_lo_to_n_raw(profile=profile)


def write_ao_lo_to_n(value: str, profile: CredentialProfile = 'single') -> None:
    _write_text(_profile_paths(profile)['ao_lo_to_n'], (value or '').strip())


def bulk_accounts_pool_path() -> Path:
    return config_dir() / 'seller_bulk_accounts.json'


def _format_pool_dt(raw: str | None) -> str:
    if not raw:
        return '—'
    s = str(raw).strip()
    if not s:
        return '—'
    try:
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        from datetime import datetime

        dt = datetime.fromisoformat(s)
        return dt.strftime('%Y-%m-%d %H:%M')
    except ValueError:
        return s[:16]


def read_bulk_accounts_form() -> dict:
    """大批量账号池（供配置页展示）。"""
    _ensure_script_path()
    try:
        from bulk_account_pool import get_ban_pending_asins, load_pool, _is_in_cooldown

        pool = load_pool()
    except ImportError:
        return {
            'accounts': [],
            'cooldown_days': 3,
            'active_key': '',
            'ban_pending_count': 0,
            'ad_ban_pending_count': 0,
            'ready_count': 0,
            'total_count': 0,
        }

    active_key = str(pool.get('runtime', {}).get('active_key') or '').strip()
    accounts: list[dict] = []
    ready_count = 0
    for acc in pool.get('accounts') or []:
        ao_raw = acc.get('ao_lo_to_n') or ''
        from credentials_loader import resolve_ao_lo_to_n_for_cookie

        ao_ok = bool(resolve_ao_lo_to_n_for_cookie(ao_raw)) if ao_raw else False
        has_password = bool(acc.get('password'))
        child_id = str(acc.get('child_id') or '').strip()
        username = str(acc.get('username') or '').strip()
        ready = bool(child_id and username and has_password and ao_ok)
        if ready:
            ready_count += 1
        cooldown_until = acc.get('cooldown_until')
        accounts.append(
            {
                'key': acc.get('key') or '',
                'child_id': child_id,
                'username': username,
                'has_password': has_password,
                'ao_lo_to_n': ao_raw,
                'has_ao_lo_to_n': ao_ok,
                'ready': ready,
                'is_active': acc.get('key') == active_key,
                'last_used_at': acc.get('last_used_at'),
                'last_used_label': _format_pool_dt(acc.get('last_used_at')),
                'cooldown_until': cooldown_until,
                'cooldown_label': _format_pool_dt(cooldown_until),
                'last_banned_at': acc.get('last_banned_at'),
                'in_cooldown': _is_in_cooldown(acc),
            }
        )

    return {
        'accounts': accounts,
        'cooldown_days': int(pool.get('cooldown_days') or 3),
        'active_key': active_key,
        'ban_pending_count': len(get_ban_pending_asins(task='roi')),
        'ad_ban_pending_count': len(get_ban_pending_asins(task='ad')),
        'ready_count': ready_count,
        'total_count': len(accounts),
    }


def write_bulk_accounts_from_form(
    accounts: list[dict],
    *,
    cooldown_days_value: int | None = None,
) -> None:
    _ensure_script_path()
    from bulk_account_pool import write_accounts_from_form

    write_accounts_from_form(accounts, cooldown_days_value=cooldown_days_value)


def read_seller_credentials_form(profile: CredentialProfile = 'single') -> dict:
    """供配置页表单展示（不向模板暴露明文密码）。"""
    if profile == 'bulk':
        pool = read_bulk_accounts_form()
        accounts = pool.get('accounts') or []
        if accounts:
            label = '大批量计算（≥20 ASIN）'
            ready_count = int(pool.get('ready_count') or 0)
            total_count = int(pool.get('total_count') or 0)
            checklist = [
                {'label': f'可用账号 {ready_count}/{total_count}', 'done': ready_count > 0},
                {'label': '账号池 ≥2（可轮换）', 'done': total_count >= 2},
            ]
            first = accounts[0]
            return {
                'profile': profile,
                'profile_label': label,
                'child_ids': first.get('child_id') or '',
                'seller_username': first.get('username') or '',
                'has_password': bool(first.get('has_password')),
                'ao_lo_to_n': first.get('ao_lo_to_n') or '',
                'has_child_ids': bool(first.get('child_id')),
                'has_ao_lo_to_n': bool(first.get('has_ao_lo_to_n')),
                'seller_ready': ready_count > 0,
                'checklist': checklist,
                'checklist_done': sum(1 for x in checklist if x['done']),
                'checklist_total': len(checklist),
            }

    _ensure_script_path()
    from credentials_loader import read_ao_lo_to_n_raw, resolve_ao_lo_to_n_for_cookie

    label = '单次计算（<20 ASIN）' if profile == 'single' else '大批量计算（≥20 ASIN）'
    child_ids = read_seller_child_ids(profile)
    ao_lo_raw = read_ao_lo_to_n_raw(profile=profile)
    ao_lo_resolved = resolve_ao_lo_to_n_for_cookie(ao_lo_raw) if ao_lo_raw else ''
    username = read_seller_username(profile)
    has_password = bool(read_seller_password(profile))
    checklist = [
        {'label': '子账号 ID', 'done': bool(child_ids)},
        {'label': '登录用户名', 'done': bool(username)},
        {'label': '登录密码', 'done': has_password},
        {'label': 'ao_lo_to_n', 'done': bool(ao_lo_resolved)},
    ]
    done_count = sum(1 for x in checklist if x['done'])
    return {
        'profile': profile,
        'profile_label': label,
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
    seller = read_seller_credentials_form('single')
    seller_bulk = read_seller_credentials_form('bulk')
    bulk_pool = read_bulk_accounts_form()
    bulk_threshold = int(getattr(settings, 'ROI_BULK_ASIN_THRESHOLD', 20))
    return {
        'authorization': auth,
        'has_authorization': bool(auth),
        'authorization_preview': _mask_secret(auth, head=18, tail=8),
        'token_status': token_status,
        'sif_ready': bool(auth) and bool(token_status.get('exists')),
        'seller': seller,
        'seller_bulk': seller_bulk,
        'bulk_pool': bulk_pool,
        'bulk_asin_threshold': bulk_threshold,
        'bulk_cooldown_days': int(getattr(settings, 'ROI_BULK_ACCOUNT_COOLDOWN_DAYS', 3)),
        'ao_lo_preview': _mask_secret(seller.get('ao_lo_to_n') or '', head=12, tail=8),
        'bulk_ao_lo_preview': _mask_secret(seller_bulk.get('ao_lo_to_n') or '', head=12, tail=8),
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
