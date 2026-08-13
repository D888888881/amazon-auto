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

