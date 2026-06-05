"""按 ASIN 逐个执行 ROI / 广告难度，支持解禁后从失败 ASIN 续算。"""
from __future__ import annotations

from collections.abc import Callable

from .asin_access import normalize_asin
from .asin_wizard import run_ad_difficulty_for_asins, run_seller_wizard


def ordered_unique_asins(asins: list[str] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in asins or []:
        a = normalize_asin(raw)
        if a and a not in seen:
            seen.add(a)
            out.append(a)
    return out


def run_roi_asins_sequential(
    asins: list[str],
    parity: float,
    *,
    cost_overrides: dict | None = None,
    on_stderr_line: Callable[[str], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
    on_asin_done: Callable[[str, dict], None] | None = None,
) -> dict:
    """
    逐个 ASIN 计算 ROI；某个 ASIN 因子账号禁用失败时解禁后从该 ASIN 继续。
    每完成一个 ASIN 可调用 on_asin_done(asin, partial_result) 做增量持久化。
    """
    merged: dict = {}
    total = len(asins)
    for idx, asin in enumerate(asins, start=1):
        if on_progress:
            on_progress(f'进度 {idx}/{total}：开始计算 ROI · {asin}')

        co = {asin: cost_overrides[asin]} if cost_overrides and asin in cost_overrides else None

        part = run_seller_wizard(
            [asin],
            parity,
            cost_overrides=co,
            on_stderr_line=on_stderr_line,
        )
        if isinstance(part, dict):
            merged.update(part)
            if on_asin_done:
                on_asin_done(asin, part)
        if on_progress:
            on_progress(f'进度 {idx}/{total}：{asin} ROI 已完成')
    return merged


def run_ad_difficulty_asins_sequential(
    asins: list[str],
    *,
    on_stderr_line: Callable[[str], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
    on_asin_done: Callable[[str, dict], None] | None = None,
) -> dict:
    """逐个 ASIN 计算广告难度；禁用后解禁并从当前 ASIN 续算。"""
    merged: dict = {}
    total = len(asins)
    for idx, asin in enumerate(asins, start=1):
        if on_progress:
            on_progress(f'进度 {idx}/{total}：开始计算广告难度 · {asin}')

        part = run_ad_difficulty_for_asins([asin], on_stderr_line=on_stderr_line)
        if isinstance(part, dict):
            merged.update(part)
            if on_asin_done:
                on_asin_done(asin, part)
        if on_progress:
            on_progress(f'进度 {idx}/{total}：{asin} 广告难度已完成')
    return merged
