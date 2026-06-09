# -*- coding: utf-8 -*-
"""卖家精灵子账号禁用检测与自动解禁。"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any

RANK_LOGIN_USER_MARKER = 'rank-login-user'
DEFAULT_SELLER_USERNAME = os.environ.get('SELLER_WIZARD_USERNAME', 'ITBM000067')
DEFAULT_SELLER_PASSWORD = os.environ.get('SELLER_WIZARD_PASSWORD', 'ITBM000067')
LOGIN_CACHE_TTL_SEC = int(os.environ.get('SELLER_LOGIN_CACHE_TTL_SEC', '1800'))

_login_cache: dict[str, tuple[float, dict[str, str]]] = {}
_login_lock = asyncio.Lock()


class SellerAccountBannedError(Exception):
    """子账号被禁用时登录无法返回 rank-login-user。"""


def is_seller_account_banned_error(exc: BaseException) -> bool:
    if isinstance(exc, SellerAccountBannedError):
        return True
    if isinstance(exc, KeyError) and RANK_LOGIN_USER_MARKER in str(exc.args):
        return True
    text = f'{type(exc).__name__}: {exc}'
    if RANK_LOGIN_USER_MARKER in text:
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

    username = username or DEFAULT_SELLER_USERNAME
    password = password if password is not None else DEFAULT_SELLER_PASSWORD

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
