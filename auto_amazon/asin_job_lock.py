"""ASIN 级计算锁：手动与定时任务共用，避免同一 ASIN 并发计算。"""
from __future__ import annotations

import os

from django.core.cache import cache

from .asin_access import normalize_asin

_PREFIX = 'asin_compute_lock:'


def _ttl() -> int:
    return int(os.environ.get('SCHEDULER_ASIN_LOCK_TTL', '7200'))


def _key(asin: str) -> str:
    return _PREFIX + normalize_asin(asin)


def try_acquire(asin: str, owner: str) -> bool:
    return cache.add(_key(asin), owner, _ttl())


def release(asin: str, owner: str) -> None:
    key = _key(asin)
    if cache.get(key) == owner:
        cache.delete(key)


class AsinComputeLock:
    def __init__(self, asins: list[str] | None, owner: str) -> None:
        self.owner = owner
        self.asins = sorted({normalize_asin(a) for a in (asins or []) if normalize_asin(a)})
        self.locked: list[str] = []

    def acquire(self) -> str | None:
        for asin in self.asins:
            if not try_acquire(asin, self.owner):
                self.release_all()
                return asin
            self.locked.append(asin)
        return None

    def release_all(self) -> None:
        for asin in self.locked:
            release(asin, self.owner)
        self.locked = []
