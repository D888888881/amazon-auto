"""USD → CNY 汇率自动获取（带 Redis 缓存与 fallback）。"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_CACHE_KEY = 'usd_cny_exchange_rate'


def _fallback_rate() -> float:
    return float(getattr(settings, 'USD_CNY_RATE_FALLBACK', 7.2))


def _cache_seconds() -> int:
    return int(getattr(settings, 'USD_CNY_RATE_CACHE_SECONDS', 21600))


def _fetch_from_api() -> float | None:
    url = getattr(
        settings,
        'USD_CNY_RATE_API_URL',
        'https://api.exchangerate-api.com/v4/latest/USD',
    )
    req = urllib.request.Request(url, headers={'User-Agent': 'auto-amazon-scheduler/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        logger.warning('fetch USD/CNY rate failed: %s', exc)
        return None
    rates = payload.get('rates') if isinstance(payload, dict) else None
    if not isinstance(rates, dict):
        return None
    cny = rates.get('CNY')
    try:
        val = float(cny)
    except (TypeError, ValueError):
        return None
    if val <= 0:
        return None
    return round(val, 4)


def fetch_usd_cny_rate(*, force_refresh: bool = False) -> float:
    """
    获取美元兑人民币汇率。
    优先读缓存，失败时使用环境变量 fallback（默认 7.2）。
    """
    if not force_refresh:
        cached = cache.get(_CACHE_KEY)
        if cached is not None:
            try:
                return float(cached)
            except (TypeError, ValueError):
                pass

    rate = _fetch_from_api()
    if rate is None:
        rate = _fallback_rate()
        logger.warning('using fallback USD/CNY rate: %s', rate)
    else:
        cache.set(_CACHE_KEY, rate, _cache_seconds())
    return rate


if __name__ == '__main__':
    print(fetch_usd_cny_rate())