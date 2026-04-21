"""
供 Django 子进程调用：执行 async_seller_wizard_api.seller_wizard_main，向 stdout 输出 JSON。
工作目录需为 scripts/asin_find_project（由调用方设置 cwd）。
stdin JSON: {"asins": ["B0..."], "parity": 6.88}

注意：必须在进程顶层 import async_seller_wizard_api（不能放在 async 函数内）。
该模块在导入时会执行 asyncio.run()；若已在 asyncio.run(_main()) 内部再 import，
会触发「asyncio.run() cannot be called from a running event loop」。
"""
from __future__ import annotations

import asyncio
import io
import json
import sys

from async_seller_wizard_api import seller_wizard_main


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
    payload = json.loads(raw)
    asins = payload.get('asins')
    cost_overrides = payload.get('cost_overrides')
    parity = float(payload.get('parity') or 0)
    if parity <= 0:
        raise ValueError('parity 必须大于 0')

    print(
        'PROGRESS:开始执行 seller_wizard_main（步骤较多，可能需要数分钟至更久）…',
        file=sys.stderr,
        flush=True,
    )
    result = await seller_wizard_main(parity, asins=asins or None, cost_overrides=cost_overrides or None)
    print('PROGRESS:分析完成，正在序列化结果…', file=sys.stderr, flush=True)
    return _to_jsonable(result)


if __name__ == '__main__':
    try:
        # 分析过程中若有库向 stdout 打印，会污染管道里的 JSON；期间先吞掉 stdout
        _stdout_real = sys.stdout
        _stdout_buf = io.StringIO()
        sys.stdout = _stdout_buf
        try:
            out = asyncio.run(_main())
        finally:
            sys.stdout = _stdout_real
        leaked = _stdout_buf.getvalue()
        if leaked.strip():
            sys.stderr.write(
                f'PROGRESS:已忽略分析阶段写入 stdout 的 {len(leaked)} 字符杂项输出，仅输出 JSON。\n'
            )
            sys.stderr.flush()
        print('PROGRESS:正在输出 JSON…', file=sys.stderr, flush=True)
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
        sys.stdout.flush()
    except Exception as e:
        sys.stderr.write(f'{type(e).__name__}: {e}\n')
        sys.exit(1)
