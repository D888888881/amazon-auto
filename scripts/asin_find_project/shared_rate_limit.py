"""跨 Worker 的外部 API 并发限制（Redis 信号量）。"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
import time
import uuid
from contextlib import contextmanager

_SLOT_PREFIX = 'roi:api_slot:'


def _redis_client():
    import redis

    host = os.environ.get('REDIS_HOST', '127.0.0.1')
    port = int(os.environ.get('REDIS_PORT', '6379'))
    db = int(os.environ.get('REDIS_DB', '1'))
    password = os.environ.get('REDIS_PASSWORD') or None
    return redis.Redis(
        host=host,
        port=port,
        db=db,
        password=password,
        decode_responses=True,
    )


def _max_slots(name: str) -> int:
    env_map = {
        'sellersprite': 'ROI_SELLERSPRITE_MAX_CONCURRENT',
        'sif': 'ROI_SIF_MAX_CONCURRENT',
        'taobao': 'ROI_TAOBAO_MAX_CONCURRENT',
        'scheduler_asin': 'ROI_SCHEDULER_ASIN_MAX_CONCURRENT',
    }
    key = env_map.get(name, f'ROI_{name.upper()}_MAX_CONCURRENT')
    raw = os.environ.get(key, '')
    if not raw:
        defaults = {'sellersprite': 6, 'sif': 4, 'taobao': 1}
        return defaults.get(name, 2)
    try:
        return max(1, int(raw))
    except ValueError:
        return 2


@contextmanager
def api_slot(name: str, *, max_slots: int | None = None, wait_sec: float = 300):
    """
    获取分布式 API 槽位。max_slots<=0 或未配置 Redis 时直接放行。
    """
    limit = max_slots if max_slots is not None else _max_slots(name)
    if limit <= 0:
        yield
        return

    token = uuid.uuid4().hex
    holders_key = f'{_SLOT_PREFIX}{name}:holders'
    deadline = time.time() + wait_sec
    acquired = False
    r = None

    try:
        r = _redis_client()
        while time.time() < deadline:
            now = time.time()
            r.zremrangebyscore(holders_key, 0, now - 600)
            if r.zcard(holders_key) < limit:
                r.zadd(holders_key, {token: now})
                acquired = True
                break
            time.sleep(0.25 + (time.time() % 0.15))
        if not acquired:
            raise TimeoutError(f'等待 API 槽位 {name} 超时（limit={limit}）')
        yield
    except (ImportError, OSError) as e:
        # 本地无 Redis 时不阻断
        print(f'警告: API 限流不可用 ({name}): {e}')
        yield
    finally:
        if acquired and r is not None:
            try:
                r.zrem(holders_key, token)
            except Exception:
                pass


@asynccontextmanager
async def async_api_slot(name: str, *, max_slots: int | None = None, wait_sec: float = 300):
    """在 async 代码中持有 Redis API 槽位。"""
    holder: dict = {}

    def acquire():
        cm = api_slot(name, max_slots=max_slots, wait_sec=wait_sec)
        holder['cm'] = cm
        cm.__enter__()

    def release():
        cm = holder.get('cm')
        if cm is not None:
            cm.__exit__(None, None, None)

    await asyncio.to_thread(acquire)
    try:
        yield
    finally:
        await asyncio.to_thread(release)


def env_max_concurrent(name: str, default: int) -> int:
    env_map = {
        'sellersprite': 'ROI_SELLERSPRITE_MAX_CONCURRENT',
        'sif': 'ROI_SIF_MAX_CONCURRENT',
        'taobao': 'ROI_TAOBAO_MAX_CONCURRENT',
        'scheduler_asin': 'ROI_SCHEDULER_ASIN_MAX_CONCURRENT',
    }
    key = env_map.get(name, f'ROI_{name.upper()}_MAX_CONCURRENT')
    try:
        return max(1, int(os.environ.get(key, str(default))))
    except ValueError:
        return default
