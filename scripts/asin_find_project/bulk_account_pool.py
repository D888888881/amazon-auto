# -*- coding: utf-8 -*-
"""大批量 ROI 卖家精灵子账号池：轮换、冷却、禁号 ASIN 续算。"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

PendingTask = Literal['roi', 'ad']

_PENDING_FIELD = {
    'roi': 'ban_pending_asins',
    'ad': 'ad_ban_pending_asins',
}

_POOL_FILE = Path(__file__).resolve().parent / 'config_file' / 'seller_bulk_accounts.json'
_LOCK = threading.Lock()
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _fmt_dt(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def cooldown_days() -> int:
    try:
        return max(1, int(os.environ.get('ROI_BULK_ACCOUNT_COOLDOWN_DAYS', '3')))
    except (TypeError, ValueError):
        return 3


def _default_pool() -> dict[str, Any]:
    return {
        'cooldown_days': cooldown_days(),
        'accounts': [],
        'runtime': {
            'active_key': '',
            'ban_pending_asins': [],
            'ad_ban_pending_asins': [],
        },
    }


def _account_key(username: str, child_id: str = '') -> str:
    u = str(username or '').strip()
    if u:
        return u
    return str(child_id or '').strip() or 'unknown'


def _normalize_account(raw: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    username = str(raw.get('username') or '').strip()
    child_id = str(raw.get('child_id') or '').strip()
    password = str(raw.get('password') or '').strip()
    ao_lo_to_n = str(raw.get('ao_lo_to_n') or '').strip()
    if not username or not child_id:
        return None
    key = str(raw.get('key') or '').strip() or _account_key(username, child_id)
    return {
        'key': key,
        'child_id': child_id,
        'username': username,
        'password': password,
        'ao_lo_to_n': ao_lo_to_n,
        'last_used_at': raw.get('last_used_at'),
        'cooldown_until': raw.get('cooldown_until'),
        'last_banned_at': raw.get('last_banned_at'),
    }


def _migrate_legacy_into_pool(pool: dict[str, Any]) -> dict[str, Any]:
    if pool.get('accounts'):
        return pool
    cfg = Path(__file__).resolve().parent / 'config_file'
    username = (cfg / 'seller_bulk_username.txt').read_text(encoding='utf-8').strip() if (cfg / 'seller_bulk_username.txt').is_file() else ''
    password = (cfg / 'seller_bulk_password.txt').read_text(encoding='utf-8').strip() if (cfg / 'seller_bulk_password.txt').is_file() else ''
    ao_lo = (cfg / 'seller_bulk_ao_lo_to_n.txt').read_text(encoding='utf-8').strip() if (cfg / 'seller_bulk_ao_lo_to_n.txt').is_file() else ''
    child_raw = (cfg / 'seller_bulk_child_ids.txt').read_text(encoding='utf-8').strip() if (cfg / 'seller_bulk_child_ids.txt').is_file() else ''
    child_id = child_raw.replace('\n', ',').split(',')[0].strip() if child_raw else ''
    if username and child_id:
        acc = _normalize_account(
            {
                'username': username,
                'password': password,
                'ao_lo_to_n': ao_lo,
                'child_id': child_id,
            }
        )
        if acc:
            pool['accounts'] = [acc]
            pool['runtime']['active_key'] = acc['key']
    return pool


def load_pool(*, migrate_legacy: bool = True) -> dict[str, Any]:
    with _LOCK:
        if not _POOL_FILE.is_file():
            pool = _default_pool()
            if migrate_legacy:
                pool = _migrate_legacy_into_pool(pool)
            return pool
        try:
            raw = json.loads(_POOL_FILE.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            raw = {}
        pool = _default_pool()
        if isinstance(raw, dict):
            pool['cooldown_days'] = int(raw.get('cooldown_days') or cooldown_days())
            runtime = raw.get('runtime') if isinstance(raw.get('runtime'), dict) else {}
            pool['runtime'] = {
                'active_key': str(runtime.get('active_key') or '').strip(),
                'ban_pending_asins': [
                    str(x).strip().upper()
                    for x in (runtime.get('ban_pending_asins') or [])
                    if str(x).strip()
                ],
                'ad_ban_pending_asins': [
                    str(x).strip().upper()
                    for x in (runtime.get('ad_ban_pending_asins') or [])
                    if str(x).strip()
                ],
            }
            accounts: list[dict[str, Any]] = []
            for item in raw.get('accounts') or []:
                acc = _normalize_account(item)
                if acc:
                    accounts.append(acc)
            pool['accounts'] = accounts
        if migrate_legacy and not pool['accounts']:
            pool = _migrate_legacy_into_pool(pool)
        if pool['accounts'] and not pool['runtime'].get('active_key'):
            pool['runtime']['active_key'] = pool['accounts'][0]['key']
        return pool


def save_pool(pool: dict[str, Any]) -> None:
    with _LOCK:
        _POOL_FILE.parent.mkdir(parents=True, exist_ok=True)
        out = {
            'cooldown_days': int(pool.get('cooldown_days') or cooldown_days()),
            'accounts': pool.get('accounts') or [],
            'runtime': pool.get('runtime') or {
                'active_key': '',
                'ban_pending_asins': [],
                'ad_ban_pending_asins': [],
            },
        }
        _POOL_FILE.write_text(
            json.dumps(out, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )
        _sync_legacy_txt_from_active(out)


def _sync_legacy_txt_from_active(pool: dict[str, Any]) -> None:
    """兼容仍读 txt 的旧逻辑：同步当前活跃账号到 bulk 单文件。"""
    active = _find_account(pool, pool.get('runtime', {}).get('active_key'))
    cfg = _POOL_FILE.parent
    if not active:
        return
    (cfg / 'seller_bulk_child_ids.txt').write_text(active['child_id'] + '\n', encoding='utf-8')
    (cfg / 'seller_bulk_username.txt').write_text(active['username'] + '\n', encoding='utf-8')
    if active.get('password'):
        (cfg / 'seller_bulk_password.txt').write_text(active['password'] + '\n', encoding='utf-8')
    if active.get('ao_lo_to_n') is not None:
        (cfg / 'seller_bulk_ao_lo_to_n.txt').write_text(
            (active.get('ao_lo_to_n') or '') + ('\n' if active.get('ao_lo_to_n') else ''),
            encoding='utf-8',
        )


def _find_account(pool: dict[str, Any], key: str | None) -> dict[str, Any] | None:
    if not key:
        return None
    for acc in pool.get('accounts') or []:
        if acc.get('key') == key:
            return acc
    return None


def list_bulk_accounts() -> list[dict[str, Any]]:
    return list(load_pool().get('accounts') or [])


def get_active_account() -> dict[str, Any] | None:
    pool = load_pool()
    env_key = os.environ.get('SELLER_BULK_ACCOUNT_KEY', '').strip()
    key = env_key or pool.get('runtime', {}).get('active_key')
    acc = _find_account(pool, key)
    if acc:
        return dict(acc)
    accounts = pool.get('accounts') or []
    return dict(accounts[0]) if accounts else None


def get_active_account_credentials() -> dict[str, str] | None:
    acc = get_active_account()
    if not acc:
        return None
    return {
        'key': acc['key'],
        'child_id': acc['child_id'],
        'username': acc['username'],
        'password': acc.get('password') or '',
        'ao_lo_to_n': acc.get('ao_lo_to_n') or '',
    }


def _is_in_cooldown(acc: dict[str, Any], now: datetime | None = None) -> bool:
    now = now or _utc_now()
    until = _parse_dt(acc.get('cooldown_until'))
    return bool(until and until > now)


def pick_least_recently_used_account(*, exclude_keys: set[str] | None = None) -> dict[str, Any] | None:
    """选最久未使用的可用账号（从未使用优先）。"""
    pool = load_pool()
    exclude = exclude_keys or set()
    now = _utc_now()
    candidates: list[tuple[datetime, dict[str, Any]]] = []
    fallback: list[tuple[datetime, dict[str, Any]]] = []
    for acc in pool.get('accounts') or []:
        if acc.get('key') in exclude:
            continue
        last = _parse_dt(acc.get('last_used_at')) or _EPOCH
        if _is_in_cooldown(acc, now):
            fallback.append((last, acc))
        else:
            candidates.append((last, acc))
    pick_from = candidates if candidates else fallback
    if not pick_from:
        return None
    pick_from.sort(key=lambda x: x[0])
    return dict(pick_from[0][1])


def set_active_account(key: str) -> None:
    pool = load_pool()
    if not _find_account(pool, key):
        raise ValueError(f'未知 bulk 账号 key: {key}')
    pool.setdefault('runtime', {})['active_key'] = key
    save_pool(pool)
    os.environ['SELLER_BULK_ACCOUNT_KEY'] = key


def mark_account_used(key: str | None = None) -> None:
    pool = load_pool()
    k = key or pool.get('runtime', {}).get('active_key')
    acc = _find_account(pool, k)
    if not acc:
        return
    acc['last_used_at'] = _fmt_dt(_utc_now())
    pool['runtime']['active_key'] = acc['key']
    save_pool(pool)


def _pending_field(task: PendingTask = 'roi') -> str:
    return _PENDING_FIELD.get(task) or _PENDING_FIELD['roi']


def record_ban_pending_asins(
    asins: list[str],
    *,
    task: PendingTask = 'roi',
) -> list[str]:
    pool = load_pool()
    runtime = pool.setdefault('runtime', {})
    field = _pending_field(task)
    existing = {
        str(x).strip().upper()
        for x in runtime.get(field) or []
        if str(x).strip()
    }
    for raw in asins or []:
        a = str(raw or '').strip().upper()
        if a:
            existing.add(a)
    merged = sorted(existing)
    runtime[field] = merged
    save_pool(pool)
    return merged


def pop_ban_pending_asins(*, task: PendingTask = 'roi') -> list[str]:
    pool = load_pool()
    runtime = pool.setdefault('runtime', {})
    field = _pending_field(task)
    pending = list(runtime.get(field) or [])
    runtime[field] = []
    save_pool(pool)
    return pending


def get_ban_pending_asins(*, task: PendingTask = 'roi') -> list[str]:
    pool = load_pool()
    return list(pool.get('runtime', {}).get(_pending_field(task)) or [])


def rotate_bulk_account_after_ban(
    banned_username: str | None,
    *,
    pending_asins: list[str] | None = None,
    pending_task: PendingTask = 'roi',
) -> tuple[bool, str, dict[str, Any] | None]:
    """
    解禁当前账号 → 进入冷却 → 切换到最久未使用账号。
    返回 (成功, 说明, 新账号 dict)。
    """
    pool = load_pool()
    accounts = pool.get('accounts') or []
    if len(accounts) < 2:
        return False, '批量账号池少于 2 个，无法轮换', None

    banned_key = None
    if banned_username:
        for acc in accounts:
            if acc.get('username') == banned_username:
                banned_key = acc['key']
                break
    if not banned_key:
        banned_key = pool.get('runtime', {}).get('active_key')

    banned = _find_account(pool, banned_key)
    if not banned:
        return False, '无法定位被禁批量账号', None

    now = _utc_now()
    days = int(pool.get('cooldown_days') or cooldown_days())
    banned['last_banned_at'] = _fmt_dt(now)
    banned['cooldown_until'] = _fmt_dt(now + timedelta(days=days))

    if pending_asins:
        record_ban_pending_asins(pending_asins, task=pending_task)

    next_acc = pick_least_recently_used_account(exclude_keys={banned['key']})
    if not next_acc:
        save_pool(pool)
        return False, '没有可切换的批量账号（均在冷却或未配置）', None

    pool = load_pool()
    banned = _find_account(pool, banned['key'])
    if banned:
        banned['last_banned_at'] = _fmt_dt(now)
        banned['cooldown_until'] = _fmt_dt(now + timedelta(days=days))
    pool['runtime']['active_key'] = next_acc['key']
    save_pool(pool)
    os.environ['SELLER_BULK_ACCOUNT_KEY'] = next_acc['key']

    msg = (
        f'已解禁 {banned.get("username") if banned else "?"} 并进入 {days} 天冷却；'
        f'切换至最久未用账号 {next_acc.get("username")}'
    )
    return True, msg, dict(next_acc)


def write_accounts_from_form(
    accounts: list[dict[str, Any]],
    *,
    cooldown_days_value: int | None = None,
) -> None:
    pool = load_pool()
    old_by_key = {a['key']: a for a in pool.get('accounts') or []}
    normalized: list[dict[str, Any]] = []
    for raw in accounts:
        acc = _normalize_account(raw)
        if not acc:
            continue
        prev = old_by_key.get(acc['key'])
        if prev:
            if not acc.get('password') and prev.get('password'):
                acc['password'] = prev['password']
            for field in ('last_used_at', 'cooldown_until', 'last_banned_at'):
                if not acc.get(field) and prev.get(field):
                    acc[field] = prev[field]
        normalized.append(acc)
    pool['accounts'] = normalized
    if cooldown_days_value is not None:
        pool['cooldown_days'] = max(1, int(cooldown_days_value))
    active = pool.get('runtime', {}).get('active_key')
    if not _find_account(pool, active) and normalized:
        pool['runtime']['active_key'] = normalized[0]['key']
    save_pool(pool)
