# -*- coding: utf-8 -*-
"""ROI 任务进度：写入 stderr，供 Django 子进程 / Web 轮询捕获。"""
from __future__ import annotations

import sys


def emit_progress(msg: str) -> None:
    text = str(msg or '').strip()
    if text:
        print(f'PROGRESS:{text}', file=sys.stderr, flush=True)


def emit_progress_throttled(msg: str, *, key: str, interval_sec: float = 10.0) -> None:
    """同一 key 在 interval_sec 内只输出一次，避免刷屏。"""
    import time

    store = getattr(emit_progress_throttled, '_last', None)
    if store is None:
        store = {}
        emit_progress_throttled._last = store  # type: ignore[attr-defined]
    now = time.time()
    last = store.get(key, 0.0)
    if now - last >= interval_sec:
        store[key] = now
        emit_progress(msg)
