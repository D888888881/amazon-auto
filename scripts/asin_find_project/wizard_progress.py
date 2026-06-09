# -*- coding: utf-8 -*-
"""ROI 任务进度：写入 stderr，供 Django 子进程 / Web 轮询捕获。"""
from __future__ import annotations

import sys


def emit_progress(msg: str) -> None:
    text = str(msg or '').strip()
    if text:
        print(f'PROGRESS:{text}', file=sys.stderr, flush=True)
