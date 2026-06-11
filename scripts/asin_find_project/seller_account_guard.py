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
        from credentials_loader import read_seller_username

        cfg = read_seller_username()
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
        from credentials_loader import read_seller_password

        cfg = read_seller_password()
        if cfg:
            return cfg
    except ImportError:
        pass
    return _FALLBACK_SELLER_PASSWORD

_login_cache: dict[str, tuple[float, dict[str, str]]] = {}
_login_lock = asyncio.Lock()


class SellerAccountBannedError(Exception):
    """子账号被禁用时登录无法返回 rank-login-user。"""


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
        'unauthorized', 'forbidden', 'sprite-x-token', 'token invalid', 'token expired',
        '子账号', '被禁用', '账号禁用', 'account banned', 'account disabled',
        'child-account/unlock', 'unlock', '权限不足', 'permission denied',
        'session expired', 'session invalid', 'err_not_login', 'err_login',
        'data 字段类型异常', '会话失效',
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
    会话失效或子账号禁用时抛出 SellerAccountBannedError。
    """
    if not isinstance(payload, dict):
        raise SellerAccountBannedError(
            f'{api} ASIN {asin} 响应格式异常（非 JSON 对象）'
        )

    if payload.get('error'):
        err_text = str(payload.get('error'))
        if looks_like_seller_auth_message(err_text):
            raise SellerAccountBannedError(f'{api} ASIN {asin}: {err_text}')
        raise SellerAccountBannedError(f'{api} ASIN {asin} 请求失败: {err_text}')

    code = payload.get('code')
    msg = str(payload.get('message') or payload.get('msg') or '')
    ok_codes = {None, 0, '0', 200, '200', 'OK', 'ok', True}
    if code not in ok_codes and str(code) not in ('0', '200', 'OK', 'ok'):
        detail = msg or str(payload.get('data') or '')
        if looks_like_seller_auth_message(f'{code} {detail}'):
            raise SellerAccountBannedError(
                f'{api} ASIN {asin} 会话失效(code={code}): {detail[:300]}'
            )

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

    raise SellerAccountBannedError(
        f'{api} ASIN {asin} data 字段类型异常: {type(data_content).__name__}'
    )


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


def _unlock_sub_account_sync() -> tuple[bool, str]:
    from unlock_seller_info import activate_children

    try:
        from credentials_loader import read_child_ids

        child_ids = read_child_ids()
    except ImportError:
        child_ids = []
    if child_ids:
        return activate_children(child_ids=child_ids)
    return activate_children()


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

    username = resolve_seller_username(username)
    password = resolve_seller_password(password)

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

        config = await set_cookie_main(username, password)
        if config.get('rank-login-user') and config.get('rank-login-user-info'):
            _login_cache[username] = (time.time(), dict(config))
            return config

    # 解禁与递归重试必须在锁外执行，否则 asyncio.Lock 不可重入会导致死锁
    if unlock_attempted:
        clear_seller_login_cache(username)
        raise SellerAccountBannedError(
            f'卖家精灵子账号 {username} 解禁后仍无法登录（缺少 rank-login-user）'
        )

    print(f'检测到子账号 {username} 被禁用，正在调用 unlock_seller_info 解禁…')
    clear_seller_login_cache(username)
    ok, msg = await asyncio.to_thread(_unlock_sub_account_sync)
    if not ok:
        raise SellerAccountBannedError(f'自动解禁失败：{msg}')

    print('解禁完成，正在重新登录子账号…')
    return await ensure_seller_login(
        username, password, unlock_attempted=True, force_refresh=True
    )
