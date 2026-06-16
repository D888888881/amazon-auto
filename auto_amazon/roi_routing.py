"""ROI 任务路由：按 ASIN 数量选择队列与卖家精灵凭证档位。"""
from __future__ import annotations

import os
from contextlib import contextmanager

from django.conf import settings


def count_wizard_asins(asins: list[str] | None) -> int:
    seen: set[str] = set()
    for raw in asins or []:
        a = str(raw or '').strip().upper()
        if a and a not in seen:
            seen.add(a)
    return len(seen)


def bulk_asin_threshold() -> int:
    try:
        return max(1, int(getattr(settings, 'ROI_BULK_ASIN_THRESHOLD', 20)))
    except (TypeError, ValueError):
        return 20


def is_bulk_wizard_job(asins: list[str] | None) -> bool:
    return count_wizard_asins(asins) >= bulk_asin_threshold()


def wizard_credential_profile(asins: list[str] | None) -> str:
    return 'bulk' if is_bulk_wizard_job(asins) else 'single'


def wizard_queue_name(asins: list[str] | None) -> str:
    if is_bulk_wizard_job(asins):
        return getattr(settings, 'RQ_QUEUE_ROI_BULK', 'roi_bulk')
    return getattr(settings, 'RQ_QUEUE_ROI_SINGLE', 'roi_single')


def wizard_route_label(asins: list[str] | None) -> str:
    n = count_wizard_asins(asins)
    th = bulk_asin_threshold()
    if n >= th:
        return f'大批量队列（{n} 个 ASIN ≥ {th}，专用账号 + Worker）'
    return f'单次队列（{n} 个 ASIN < {th}，专用账号 + Worker）'


@contextmanager
def wizard_credential_profile_context(asins: list[str] | None):
    """Web 后台线程执行时临时绑定凭证档位（Worker 容器用环境变量）。"""
    profile = wizard_credential_profile(asins)
    prev = os.environ.get('SELLER_CREDENTIAL_PROFILE')
    os.environ['SELLER_CREDENTIAL_PROFILE'] = profile
    try:
        yield profile
    finally:
        if prev is None:
            os.environ.pop('SELLER_CREDENTIAL_PROFILE', None)
        else:
            os.environ['SELLER_CREDENTIAL_PROFILE'] = prev


def ad_difficulty_credential_profile() -> str:
    """广告难度统一使用批量账号池。"""
    return 'bulk'


def ad_difficulty_queue_name() -> str:
    return getattr(settings, 'RQ_QUEUE_ROI_BULK', 'roi_bulk')


def ad_difficulty_route_label(asin_count: int) -> str:
    return f'大批量队列（{asin_count} 个 ASIN，批量账号池 + Worker）'


@contextmanager
def ad_difficulty_credential_profile_context():
    """广告难度任务绑定 bulk 凭证（Web 线程模式）。"""
    prev = os.environ.get('SELLER_CREDENTIAL_PROFILE')
    os.environ['SELLER_CREDENTIAL_PROFILE'] = ad_difficulty_credential_profile()
    try:
        yield ad_difficulty_credential_profile()
    finally:
        if prev is None:
            os.environ.pop('SELLER_CREDENTIAL_PROFILE', None)
        else:
            os.environ['SELLER_CREDENTIAL_PROFILE'] = prev


def scheduled_credential_profile() -> str:
    """定时任务（ROI + 广告难度）统一使用批量账号池。"""
    return 'bulk'


@contextmanager
def scheduled_credential_profile_context():
    """定时任务 Worker / Web 线程模式绑定 bulk 凭证。"""
    prev = os.environ.get('SELLER_CREDENTIAL_PROFILE')
    os.environ['SELLER_CREDENTIAL_PROFILE'] = scheduled_credential_profile()
    try:
        yield scheduled_credential_profile()
    finally:
        if prev is None:
            os.environ.pop('SELLER_CREDENTIAL_PROFILE', None)
        else:
            os.environ['SELLER_CREDENTIAL_PROFILE'] = prev
