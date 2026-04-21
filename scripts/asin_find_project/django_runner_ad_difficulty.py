"""
供 Django 子进程调用：按勾选 ASIN 计算广告难度 ranking_percent。
stdin JSON: {"asins": ["B0..."]}
"""
from __future__ import annotations

import asyncio
import io
import json
import sys

from async_seller_wizard_api import calculate_ad_difficulty_for_asins


def _to_jsonable(obj):
    import numpy as np

    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, (np.floating, np.float32, np.float64)):
        return float(obj)
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    if isinstance(obj, (float, int, str, bool)) or obj is None:
        return obj
    return str(obj)


async def _main():
    raw = sys.stdin.read()
    payload = json.loads(raw or '{}')
    asins = payload.get('asins') or []
    asins = [str(x).strip().upper() for x in asins if str(x).strip()]
    print('PROGRESS:开始计算广告难度…', file=sys.stderr, flush=True)
    result = await calculate_ad_difficulty_for_asins(asins if asins else None)
    print('PROGRESS:计算完成，正在输出 JSON…', file=sys.stderr, flush=True)
    return _to_jsonable(result)


if __name__ == '__main__':
    try:
        _stdout_real = sys.stdout
        _stdout_buf = io.StringIO()
        sys.stdout = _stdout_buf
        try:
            out = asyncio.run(_main())
        finally:
            sys.stdout = _stdout_real
        leaked = _stdout_buf.getvalue()
        if leaked.strip():
            sys.stderr.write(f'PROGRESS:已忽略阶段性 stdout 杂项输出 {len(leaked)} 字符\n')
            sys.stderr.flush()
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
        sys.stdout.flush()
    except Exception as e:
        sys.stderr.write(f'{type(e).__name__}: {e}\n')
        sys.exit(1)

