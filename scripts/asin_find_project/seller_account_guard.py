# -*- coding: utf-8 -*-
"""卖家精灵子账号禁用检测与自动解禁。"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any

RANK_LOGIN_USER_MARKER = 'rank-login-user'
_FALLBACK_SELLER_USERNAME = 'ITBM000066'
_FALLBACK_SELLER_PASSWORD = 'ITBM000066'
LOGIN_CACHE_TTL_SEC = int(os.environ.get('SELLER_LOGIN_CACHE_TTL_SEC', '1800'))


def resolve_seller_username(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    env = os.environ.get('SELLER_WIZARD_USERNAME', '').strip()
    if env:
        return env
    try:
        from credentials_loader import credential_profile, read_seller_username

        cfg = read_seller_username(profile=credential_profile())
        if cfg:
            return cfg
    except ImportError:
        pass
    return _FALLBACK_SELLER_USERNAME


def resolve_seller_password(explicit: str | None = None) -> str:
    if explicit is not None and explicit != '':
        return explicit
    env = os.environ.get('SELLER_WIZARD_PASSWORD', '').strip()
    if env:
        return env
    try:
        from credentials_loader import credential_profile, read_seller_password

        cfg = read_seller_password(profile=credential_profile())
        if cfg:
            return cfg
    except ImportError:
        pass
    return _FALLBACK_SELLER_PASSWORD

_login_cache: dict[str, tuple[float, dict[str, str]]] = {}
_login_lock = asyncio.Lock()


class SellerAccountBannedError(Exception):
    """子账号被禁用时登录无法返回 rank-login-user。"""

    def __init__(
        self,
        message: str = '',
        *,
        partial_results: dict | None = None,
        ban_pending: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.partial_results = partial_results or {}
        self.ban_pending = [
            str(a).strip().upper() for a in (ban_pending or []) if str(a).strip()
        ]


def looks_like_seller_auth_message(text: str) -> bool:
    """API/登录响应文本是否像会话失效或子账号被禁。"""
    if not text:
        return False
    lowered = str(text).lower()
    markers = (
        RANK_LOGIN_USER_MARKER,
        'selleraccountbannederror',
        '请先登录', '请登录', '未登录', '登录失效', '登录过期', '会话失效', '会话过期',
        'sign in', 'signin', 'not login', 'not logged', 'login required',
        'unauthorized', 'sprite-x-token', 'token invalid', 'token expired',
        '子账号被禁', '子账号禁用', '账号被禁', '账号禁用', 'account banned', 'account disabled',
        'child-account/unlock', '权限不足', 'permission denied',
        'session expired', 'session invalid', 'err_not_login', 'err_login',
    )
    return any(m in lowered for m in markers)


def parse_sellersprite_api_payload(
    payload: Any,
    *,
    asin: str = '',
    api: str = '',
) -> dict[str, Any]:
    """
    从卖家精灵 API 顶层 JSON 提取 data dict。
    仅会话失效/子账号禁用时抛出 SellerAccountBannedError；普通业务错误返回空 dict。
    """
    if not isinstance(payload, dict):
        print(f'{api} ASIN {asin} 响应格式异常（非 JSON 对象）')
        return {}

    if payload.get('error'):
        err_text = str(payload.get('error'))
        if looks_like_seller_auth_message(err_text):
            raise SellerAccountBannedError(f'{api} ASIN {asin}: {err_text}')
        print(f'{api} ASIN {asin} 业务错误（非禁号）: {err_text[:200]}')
        return {}

    code = payload.get('code')
    msg = str(payload.get('message') or payload.get('msg') or '')
    ok_codes = {None, 0, '0', 200, '200', 'OK', 'ok', True}
    if code not in ok_codes and str(code) not in ('0', '200', 'OK', 'ok'):
        detail = msg or str(payload.get('data') or '')
        if looks_like_seller_auth_message(f'{code} {detail}'):
            raise SellerAccountBannedError(
                f'{api} ASIN {asin} 会话失效(code={code}): {detail[:300]}'
            )
        print(f'{api} ASIN {asin} 业务 code={code}: {detail[:200]}')
        return {}

    if looks_like_seller_auth_message(msg):
        raise SellerAccountBannedError(f'{api} ASIN {asin}: {msg[:300]}')

    data_content = payload.get('data')
    if data_content is None:
        return {}
    if isinstance(data_content, dict):
        return data_content
    if isinstance(data_content, str):
        text = data_content.strip()
        if not text:
            return {}
        if looks_like_seller_auth_message(text):
            raise SellerAccountBannedError(
                f'{api} ASIN {asin} 会话失效: {text[:300]}'
            )
        print(f'{api} ASIN {asin} data 为字符串（非对象）: {text[:120]}')
        return {}

    print(f'{api} ASIN {asin} data 字段类型异常: {type(data_content).__name__}')
    return {}


def is_seller_account_banned_error(exc: BaseException) -> bool:
    if isinstance(exc, SellerAccountBannedError):
        return True
    if isinstance(exc, KeyError) and RANK_LOGIN_USER_MARKER in str(exc.args):
        return True
    cause = exc.__cause__
    if cause is not None and cause is not exc and is_seller_account_banned_error(cause):
        return True
    text = f'{type(exc).__name__}: {exc}'
    if RANK_LOGIN_USER_MARKER in text:
        return True
    if 'SellerAccountBannedError' in text:
        return True
    if looks_like_seller_auth_message(text):
        return True
    lowered = text.lower()
    for marker in ('子账号', '被禁用', 'child-account/unlock', 'account banned', 'account disabled'):
        if marker in lowered:
            return True
    return False


def clear_seller_login_cache(username: str | None = None) -> None:
    """解禁或登录失效后清除缓存。"""
    if username is None:
        _login_cache.clear()
        return
    _login_cache.pop(username, None)


def apply_login_config(cookies: dict[str, Any], config: dict[str, Any]) -> None:
    """将登录结果写入 cookies/headers 依赖的会话字段。"""
    if not config.get('rank-login-user') or not config.get('rank-login-user-info'):
        raise SellerAccountBannedError(
            '卖家精灵子账号被禁用，登录未返回 rank-login-user'
        )
    for key in (
        'rank-login-user',
        'rank-login-user-info',
        'Sprite-X-Token',
        'ao_lo_to_n',
        'JSESSIONID',
    ):
        val = config.get(key)
        if val:
            cookies[key] = val


def apply_login_headers(headers: dict[str, Any], config: dict[str, Any]) -> None:
    """部分接口除 Cookie 外还要求 Sprite-X-Token 请求头。"""
    token = config.get('Sprite-X-Token') or headers.get('Sprite-X-Token')
    if token:
        headers['Sprite-X-Token'] = token


def _unlock_sub_account_sync(child_ids: list[str] | None = None) -> tuple[bool, str]:
    from unlock_seller_info import activate_children

    try:
        if child_ids is None:
            from credentials_loader import credential_profile, read_child_ids

            child_ids = read_child_ids(profile=credential_profile())
    except ImportError:
        child_ids = child_ids or []
    if child_ids:
        return activate_children(child_ids=child_ids)
    return activate_children()


async def handle_bulk_account_ban(
    banned_username: str | None,
    *,
    pending_asins: list[str] | None = None,
    pending_task: str = 'roi',
) -> dict[str, str]:
    """批量账号被禁：解禁当前账号 → 冷却 → 切换最久未用账号 → 登录新账号。"""
    from wizard_progress import emit_progress

    from bulk_account_pool import rotate_bulk_account_after_ban

    clear_seller_login_cache()
    banned = resolve_seller_username(banned_username)
    banned_acc = None
    try:
        from bulk_account_pool import get_active_account

        cur = get_active_account()
        if cur and cur.get('username') == banned:
            banned_acc = cur
    except ImportError:
        pass

    if banned_acc and banned_acc.get('child_id'):
        emit_progress(f'正在解禁批量账号 {banned}（子账号 ID {banned_acc["child_id"]}）…')
        ok, msg = await asyncio.to_thread(
            _unlock_sub_account_sync,
            [banned_acc['child_id']],
        )
        if not ok:
            raise SellerAccountBannedError(f'批量账号 {banned} 解禁失败：{msg}')

    ok, msg, new_acc = await asyncio.to_thread(
        rotate_bulk_account_after_ban,
        banned,
        pending_asins=pending_asins,
        pending_task=pending_task if pending_task in ('roi', 'ad') else 'roi',
    )
    if not ok or not new_acc:
        raise SellerAccountBannedError(msg or '批量账号轮换失败')

    pending_n = len(pending_asins or [])
    if pending_n:
        emit_progress(f'{msg}；续算 {pending_n} 个因禁号未完成的 ASIN…')
    else:
        emit_progress(msg)

    clear_seller_login_cache()
    return await ensure_seller_login(
        new_acc['username'],
        new_acc.get('password') or '',
        force_refresh=True,
    )


async def bulk_rotate_if_available(
    pending_asins: list[str] | None,
    *,
    banned_username: str | None = None,
    rotation_state: dict | None = None,
    pending_task: str = 'roi',
) -> bool:
    """批量任务遇禁号时轮换账号；返回是否已切换。"""
    try:
        from credentials_loader import credential_profile

        if credential_profile() != 'bulk':
            return False
        from bulk_account_pool import list_bulk_accounts

        if len(list_bulk_accounts()) < 2:
            return False
    except ImportError:
        return False

    state = rotation_state if rotation_state is not None else {}
    count = int(state.get('count') or 0) + 1
    state['count'] = count
    max_rot = int(state.get('max') or os.environ.get('ROI_BULK_MAX_ROTATIONS', '16'))
    if count > max_rot:
        raise SellerAccountBannedError(f'批量账号轮换次数已达上限（{max_rot}）')

    await handle_bulk_account_ban(
        banned_username,
        pending_asins=pending_asins or [],
        pending_task=pending_task,
    )
    return True


async def ensure_seller_login(
    username: str | None = None,
    password: str | None = None,
    *,
    unlock_attempted: bool = False,
    force_refresh: bool = False,
) -> dict[str, str]:
    """
    获取子账号登录 cookie（带进程内缓存）。
    若被禁用则自动调用 unlock_seller_info 解禁后重试一次。
    """
    from seller_wizard_set_cookie import set_cookie_main
    from wizard_progress import emit_progress

    username = resolve_seller_username(username)
    password = resolve_seller_password(password)
    login_timeout = float(os.environ.get('SELLER_LOGIN_TIMEOUT_SEC', '90'))

    if not force_refresh and not unlock_attempted:
        cached = _login_cache.get(username)
        if cached and (time.time() - cached[0]) < LOGIN_CACHE_TTL_SEC:
            cfg = dict(cached[1])
            if cfg.get('rank-login-user') and cfg.get('Sprite-X-Token'):
                return cfg

    async with _login_lock:
        if not force_refresh and not unlock_attempted:
            cached = _login_cache.get(username)
            if cached and (time.time() - cached[0]) < LOGIN_CACHE_TTL_SEC:
                cfg = dict(cached[1])
                if cfg.get('rank-login-user') and cfg.get('Sprite-X-Token'):
                    return cfg

        emit_progress(f'正在登录卖家精灵子账号 {username}…')
        try:
            config = await asyncio.wait_for(
                set_cookie_main(username, password),
                timeout=login_timeout,
            )
        except asyncio.TimeoutError as exc:
            raise SellerAccountBannedError(
                f'登录卖家精灵超时（{login_timeout:.0f}s），请检查服务器能否访问 www.sellersprite.com'
            ) from exc
        if config.get('rank-login-user') and config.get('rank-login-user-info'):
            _login_cache[username] = (time.time(), dict(config))
            try:
                from credentials_loader import credential_profile

                if credential_profile() == 'bulk':
                    from bulk_account_pool import mark_account_used

                    mark_account_used()
            except ImportError:
                pass
            return config

    # 解禁与轮换必须在锁外执行，否则 asyncio.Lock 不可重入会导致死锁
    if unlock_attempted:
        clear_seller_login_cache(username)
        raise SellerAccountBannedError(
            f'卖家精灵子账号 {username} 解禁后仍无法登录（缺少 rank-login-user）'
        )

    try:
        from credentials_loader import credential_profile

        is_bulk = credential_profile() == 'bulk'
    except ImportError:
        is_bulk = False

    if is_bulk:
        try:
            from bulk_account_pool import list_bulk_accounts

            if len(list_bulk_accounts()) >= 2:
                return await handle_bulk_account_ban(username)
        except ImportError:
            pass

    emit_progress(f'检测到子账号 {username} 被禁用，正在调用 unlock_seller_info 解禁…')
    clear_seller_login_cache(username)
    ok, msg = await asyncio.to_thread(_unlock_sub_account_sync)
    if not ok:
        raise SellerAccountBannedError(f'自动解禁失败：{msg}')

    emit_progress('解禁完成，正在重新登录子账号…')
    return await ensure_seller_login(
        username, password, unlock_attempted=True, force_refresh=True
    )
