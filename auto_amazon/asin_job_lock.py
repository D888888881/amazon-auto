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


def get_lock_owner(asin: str) -> str | None:
    owner = cache.get(_key(asin))
    return str(owner) if owner else None


def force_release_asin(asin: str) -> bool:
    """强制释放 ASIN 锁（不校验 owner）。"""
    key = _key(asin)
    if cache.get(key) is None:
        return False
    cache.delete(key)
    return True


def release_job_locks(user_id: int, job_id: str, asins: list[str] | None) -> int:
    """释放某 ROI/广告任务持有的 ASIN 锁。"""
    owner = f'user:{user_id}:{job_id}'
    released = 0
    for raw in asins or []:
        a = normalize_asin(raw)
        if not a:
            continue
        if cache.get(_key(a)) == owner:
            cache.delete(_key(a))
            released += 1
    return released


def _maybe_release_stale_lock(asin: str) -> bool:
    """任务已结束但锁未释放时自动清理。"""
    owner = get_lock_owner(asin)
    if not owner or not str(owner).startswith('user:'):
        return False
    parts = str(owner).split(':', 2)
    if len(parts) != 3:
        return False
    job_id = parts[2]
    try:
        from .wizard_jobs import TERMINAL_STATUSES, load_job_entry

        ent = load_job_entry(job_id)
    except Exception:
        ent = None
    if ent is None:
        return force_release_asin(asin)
    if ent.get('status') in TERMINAL_STATUSES:
        return force_release_asin(asin)
    return False


def try_acquire(asin: str, owner: str) -> bool:
    if cache.add(_key(asin), owner, _ttl()):
        return True
    if _maybe_release_stale_lock(asin):
        return cache.add(_key(asin), owner, _ttl())
    return False


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
