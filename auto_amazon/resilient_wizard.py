"""按 ASIN 逐个执行 ROI / 广告难度，支持解禁后从失败 ASIN 续算。"""
from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from .asin_access import normalize_asin
from .asin_wizard import run_ad_difficulty_for_asins, run_seller_wizard


@dataclass
class AsinFailure:
    asin: str
    error: str
    attempts: int


@dataclass
class BatchRunResult:
    """批量 ROI / 广告难度执行结果。"""

    merged: dict = field(default_factory=dict)
    succeeded: list[str] = field(default_factory=list)
    failures: list[AsinFailure] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.succeeded) + len(self.failures)

    @property
    def success_count(self) -> int:
        return len(self.succeeded)

    @property
    def fail_count(self) -> int:
        return len(self.failures)

    @property
    def failed_asins(self) -> list[str]:
        return [f.asin for f in self.failures]

    def summary_text(self) -> str:
        if not self.failures:
            return f'全部成功（{self.success_count} 个 ASIN）'
        if not self.succeeded:
            return f'全部失败（{self.fail_count}/{self.total} 个 ASIN）'
        return (
            f'部分成功：成功 {self.success_count}，失败 {self.fail_count}'
            f'（共 {self.total} 个 ASIN）'
        )


_NON_RETRIABLE_MARKERS = (
    '未在 ',
    '未找到',
    'parity 必须',
    '未找到脚本',
    '无权访问',
    '未返回有效结果',
)


def roi_asin_max_retries() -> int:
    return max(1, int(os.environ.get('ROI_ASIN_MAX_RETRIES', '3')))


def roi_asin_retry_delay_sec(attempt: int) -> float:
    """attempt 从 1 开始，用于第几次重试前的等待。"""
    base = float(os.environ.get('ROI_ASIN_RETRY_DELAY_SEC', '5'))
    return base * attempt


def is_retriable_asin_error(exc: BaseException) -> bool:
    if isinstance(exc, (ValueError, FileNotFoundError)):
        return False
    msg = f'{type(exc).__name__}: {exc}'
    return not any(marker in msg for marker in _NON_RETRIABLE_MARKERS)


class AsinRunFailed(Exception):
    """单 ASIN 在耗尽重试次数后仍失败。"""

    def __init__(self, cause: BaseException, attempts: int) -> None:
        self.cause = cause
        self.attempts = attempts
        super().__init__(f'{type(cause).__name__}: {cause}')


def ordered_unique_asins(asins: list[str] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in asins or []:
        a = normalize_asin(raw)
        if a and a not in seen:
            seen.add(a)
            out.append(a)
    return out


def use_sequential_roi() -> bool:
    """为 True 时逐个 ASIN 跑完整流程（慢，仅调试/兼容）。"""
    return os.environ.get('ROI_ASIN_SEQUENTIAL', '').lower() in ('1', 'true', 'yes')


def batch_result_from_wizard_output(
    asins: list[str],
    result: dict | None,
    failure_details: list[dict] | None = None,
) -> BatchRunResult:
    """将一次 batch run_seller_wizard 的结果拆成成功/失败 ASIN 列表。"""
    result = result or {}
    failure_map: dict[str, str] = {}
    for row in failure_details or []:
        if not isinstance(row, dict):
            continue
        a = str(row.get('asin') or '').strip().upper()
        if a:
            failure_map[a] = str(row.get('error') or '未知错误')

    out = BatchRunResult()
    for asin in asins:
        key = str(asin).strip().upper()
        data = result.get(key) or result.get(asin)
        if isinstance(data, dict) and data and not str(key).startswith('__'):
            out.merged[key] = data
            out.succeeded.append(key)
        else:
            err = failure_map.get(key) or '未返回 ROI 结果'
            out.failures.append(
                AsinFailure(asin=key, error=err, attempts=1)
            )
    return out


def _run_one_asin_with_retry(
    asin: str,
    *,
    max_retries: int,
    run_fn: Callable[[], dict],
    on_progress: Callable[[str], None] | None,
) -> dict:
    last_exc: BaseException | None = None
    attempts = 0
    for attempt in range(1, max_retries + 1):
        attempts = attempt
        try:
            part = run_fn()
            if not isinstance(part, dict) or not part:
                raise RuntimeError(
                    f'{asin} 未返回有效结果（可能缺少本地 Excel / media 数据）'
                )
            return part
        except Exception as exc:
            last_exc = exc
            can_retry = attempt < max_retries and is_retriable_asin_error(exc)
            if on_progress:
                if can_retry:
                    on_progress(
                        f'{asin} 第 {attempt} 次失败：{type(exc).__name__}: {exc}，'
                        f'{roi_asin_retry_delay_sec(attempt):.0f}s 后重试…'
                    )
                else:
                    on_progress(
                        f'{asin} 失败（已尝试 {attempt} 次）：'
                        f'{type(exc).__name__}: {exc}'
                    )
            if not can_retry:
                break
            time.sleep(roi_asin_retry_delay_sec(attempt))
    assert last_exc is not None
    raise AsinRunFailed(last_exc, attempts) from last_exc


def run_roi_asins_sequential(
    asins: list[str],
    parity: float,
    *,
    cost_overrides: dict | None = None,
    on_stderr_line: Callable[[str], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
    on_asin_done: Callable[[str, dict], None] | None = None,
    on_asin_failed: Callable[[AsinFailure], None] | None = None,
    max_retries: int | None = None,
) -> BatchRunResult:
    """
    逐个 ASIN 计算 ROI；单 ASIN 失败不中断整批。
    遇 rank-login-user 时仍由 run_seller_wizard 内部解禁并重试。
    """
    result = BatchRunResult()
    retries = max_retries if max_retries is not None else roi_asin_max_retries()
    total = len(asins)

    for idx, asin in enumerate(asins, start=1):
        if on_progress:
            on_progress(f'进度 {idx}/{total}：开始计算 ROI · {asin}')

        co = {asin: cost_overrides[asin]} if cost_overrides and asin in cost_overrides else None

        try:
            part = _run_one_asin_with_retry(
                asin,
                max_retries=retries,
                run_fn=lambda: run_seller_wizard(
                    [asin],
                    parity,
                    cost_overrides=co,
                    on_stderr_line=on_stderr_line,
                ),
                on_progress=on_progress,
            )
            result.merged.update(part)
            result.succeeded.append(asin)
            if on_asin_done:
                on_asin_done(asin, part)
            if on_progress:
                on_progress(f'进度 {idx}/{total}：{asin} ROI 已完成')
        except AsinRunFailed as exc:
            failure = AsinFailure(
                asin=asin,
                error=f'{type(exc.cause).__name__}: {exc.cause}',
                attempts=exc.attempts,
            )
            result.failures.append(failure)
            if on_asin_failed:
                on_asin_failed(failure)
        except Exception as exc:
            failure = AsinFailure(
                asin=asin,
                error=f'{type(exc).__name__}: {exc}',
                attempts=1,
            )
            result.failures.append(failure)
            if on_asin_failed:
                on_asin_failed(failure)

    if on_progress and result.total:
        on_progress(result.summary_text())

    return result


def run_roi_asins_batch(
    asins: list[str],
    parity: float,
    *,
    cost_overrides: dict | None = None,
    on_stderr_line: Callable[[str], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
    on_asin_done: Callable[[str, dict], None] | None = None,
    on_asin_failed: Callable[[AsinFailure], None] | None = None,
    max_retries: int | None = None,
) -> BatchRunResult:
    """一次调用批量计算 ROI（内部多 ASIN 并发）；失败 ASIN 单独记录。"""
    asin_list = ordered_unique_asins(asins)
    if not asin_list:
        return BatchRunResult()
    if use_sequential_roi():
        return run_roi_asins_sequential(
            asin_list,
            parity,
            cost_overrides=cost_overrides,
            on_stderr_line=on_stderr_line,
            on_progress=on_progress,
            on_asin_done=on_asin_done,
            on_asin_failed=on_asin_failed,
            max_retries=max_retries,
        )
    if on_progress:
        on_progress(
            f'批量计算 ROI：共 {len(asin_list)} 个 ASIN'
            f'（一次拉取卖家精灵数据）…'
        )
    retries = max_retries if max_retries is not None else roi_asin_max_retries()
    try:
        merged = _run_one_asin_with_retry(
            'batch',
            max_retries=retries,
            run_fn=lambda: run_seller_wizard(
                asin_list,
                parity,
                cost_overrides=cost_overrides,
                on_stderr_line=on_stderr_line,
            ),
            on_progress=on_progress,
        )
    except AsinRunFailed as exc:
        result = BatchRunResult()
        for asin in asin_list:
            failure = AsinFailure(
                asin=asin,
                error=f'{type(exc.cause).__name__}: {exc.cause}',
                attempts=exc.attempts,
            )
            result.failures.append(failure)
            if on_asin_failed:
                on_asin_failed(failure)
        if on_progress:
            on_progress(result.summary_text())
        return result
    except Exception as exc:
        result = BatchRunResult()
        for asin in asin_list:
            failure = AsinFailure(
                asin=asin,
                error=f'{type(exc).__name__}: {exc}',
                attempts=1,
            )
            result.failures.append(failure)
            if on_asin_failed:
                on_asin_failed(failure)
        if on_progress:
            on_progress(result.summary_text())
        return result

    failure_details = None
    if isinstance(merged, dict):
        failure_details = merged.pop('__roi_failures__', None)
    result = batch_result_from_wizard_output(asin_list, merged, failure_details)
    for asin in result.succeeded:
        part = {asin: result.merged[asin]}
        if on_asin_done:
            on_asin_done(asin, part)
    for failure in result.failures:
        if on_asin_failed:
            on_asin_failed(failure)
    if on_progress:
        on_progress(result.summary_text())
    return result


def run_ad_difficulty_asins_sequential(
    asins: list[str],
    *,
    on_stderr_line: Callable[[str], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
    on_asin_done: Callable[[str, dict], None] | None = None,
    on_asin_failed: Callable[[AsinFailure], None] | None = None,
    max_retries: int | None = None,
) -> BatchRunResult:
    """逐个 ASIN 计算广告难度；单 ASIN 失败不中断整批。"""
    result = BatchRunResult()
    retries = max_retries if max_retries is not None else roi_asin_max_retries()
    total = len(asins)

    for idx, asin in enumerate(asins, start=1):
        if on_progress:
            on_progress(f'进度 {idx}/{total}：开始计算广告难度 · {asin}')

        try:
            part = _run_one_asin_with_retry(
                asin,
                max_retries=retries,
                run_fn=lambda: run_ad_difficulty_for_asins(
                    [asin], on_stderr_line=on_stderr_line
                ),
                on_progress=on_progress,
            )
            result.merged.update(part)
            result.succeeded.append(asin)
            if on_asin_done:
                on_asin_done(asin, part)
            if on_progress:
                on_progress(f'进度 {idx}/{total}：{asin} 广告难度已完成')
        except AsinRunFailed as exc:
            failure = AsinFailure(
                asin=asin,
                error=f'{type(exc.cause).__name__}: {exc.cause}',
                attempts=exc.attempts,
            )
            result.failures.append(failure)
            if on_asin_failed:
                on_asin_failed(failure)
        except Exception as exc:
            failure = AsinFailure(
                asin=asin,
                error=f'{type(exc).__name__}: {exc}',
                attempts=1,
            )
            result.failures.append(failure)
            if on_asin_failed:
                on_asin_failed(failure)

    if on_progress and result.total:
        on_progress(result.summary_text())

    return result


def run_ad_difficulty_asins_batch(
    asins: list[str],
    *,
    on_stderr_line: Callable[[str], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
    on_asin_done: Callable[[str, dict], None] | None = None,
    on_asin_failed: Callable[[AsinFailure], None] | None = None,
    max_retries: int | None = None,
    sequential: bool = False,
) -> BatchRunResult:
    """一次调用批量计算广告难度；sequential=True 时供定时任务顺序拉取（无并发）。"""
    asin_list = ordered_unique_asins(asins)
    result = BatchRunResult()
    if not asin_list:
        return result
    if on_progress:
        mode = '顺序' if sequential else '并发'
        on_progress(f'批量计算广告难度：共 {len(asin_list)} 个 ASIN（{mode}）…')
    retries = max_retries if max_retries is not None else roi_asin_max_retries()
    try:
        merged = _run_one_asin_with_retry(
            'batch',
            max_retries=retries,
            run_fn=lambda: run_ad_difficulty_for_asins(
                asin_list,
                on_stderr_line=on_stderr_line,
                sequential=sequential,
            ),
            on_progress=on_progress,
        )
    except AsinRunFailed as exc:
        for asin in asin_list:
            failure = AsinFailure(
                asin=asin,
                error=f'{type(exc.cause).__name__}: {exc.cause}',
                attempts=exc.attempts,
            )
            result.failures.append(failure)
            if on_asin_failed:
                on_asin_failed(failure)
        if on_progress:
            on_progress(result.summary_text())
        return result
    except Exception as exc:
        for asin in asin_list:
            failure = AsinFailure(
                asin=asin,
                error=f'{type(exc).__name__}: {exc}',
                attempts=1,
            )
            result.failures.append(failure)
            if on_asin_failed:
                on_asin_failed(failure)
        if on_progress:
            on_progress(result.summary_text())
        return result

    for asin in asin_list:
        payload = merged.get(asin)
        if isinstance(payload, dict) and payload and not payload.get('error'):
            part = {asin: payload}
            result.merged.update(part)
            result.succeeded.append(asin)
            if on_asin_done:
                on_asin_done(asin, part)
        else:
            err = ''
            if isinstance(payload, dict):
                err = str(payload.get('error') or '无广告难度结果')
            else:
                err = '无广告难度结果'
            failure = AsinFailure(asin=asin, error=err, attempts=1)
            result.failures.append(failure)
            if on_asin_failed:
                on_asin_failed(failure)

    if on_progress:
        on_progress(result.summary_text())
    return result
