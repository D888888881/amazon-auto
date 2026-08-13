"""全站模板上下文。"""

from __future__ import annotations

from .wizard_jobs import get_active_job_for_user


def wizard_job_context(request):
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {'active_job': None}
    return {'active_job': get_active_job_for_user(request.user.id)}


def marketplace_context(request):
    from .marketplace import (
        MARKETPLACE_CHOICES,
        MARKETPLACE_UK,
        MARKETPLACE_US,
        get_marketplace,
        marketplace_label,
    )

    mp = get_marketplace(request) if getattr(request, 'user', None) and request.user.is_authenticated else None
    return {
        'current_marketplace': mp,
        'current_marketplace_label': marketplace_label(mp) if mp else '',
        'marketplace_choices': MARKETPLACE_CHOICES,
        'MARKETPLACE_US': MARKETPLACE_US,
        'MARKETPLACE_UK': MARKETPLACE_UK,
    }


def sif_auth_alert_context(request):
    """登录用户可见：SIF JWT 过期 / 即将过期横幅。"""
    user = getattr(request, 'user', None)
    if not user or not getattr(user, 'is_authenticated', False):
        return {'sif_auth_alert': None}
    try:
        from django.core.cache import cache

        from .credentials_config import sif_authorization_expiry_info

        key = 'sif:jwt_alert:v1'
        info = cache.get(key)
        if info is None:
            info = sif_authorization_expiry_info()
            # 缓存短一点，过期后尽快提示
            ttl = 60
            if info.get('seconds_left') is not None and info['seconds_left'] > 0:
                ttl = min(300, max(30, int(info['seconds_left'] // 10)))
            # 只缓存可序列化字段
            info = {
                'status': info.get('status'),
                'expired': bool(info.get('expired')),
                'expiring_soon': bool(info.get('expiring_soon')),
                'message': info.get('message') or '',
                'expires_at_label': info.get('expires_at_label') or '',
                'ok_for_roi': bool(info.get('ok_for_roi')),
            }
            cache.set(key, info, ttl)
        if info.get('status') in ('expired', 'expiring_soon'):
            return {'sif_auth_alert': info}
    except Exception:
        pass
    return {'sif_auth_alert': None}

