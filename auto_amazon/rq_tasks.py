"""RQ Worker 执行入口（字符串路径供 queue.enqueue 使用）。"""
from __future__ import annotations

import logging

from django.db import close_old_connections

logger = logging.getLogger(__name__)


def run_wizard_job_task(
    job_id: str,
    user_id: int,
    asins: list[str] | None,
    parity: float,
    cost_overrides: dict | None = None,
    target_row_ids: dict[str, int] | None = None,
) -> None:
    from .views import _run_wizard_job

    close_old_connections()
    try:
        _run_wizard_job(
            job_id,
            user_id,
            asins,
            parity,
            cost_overrides=cost_overrides,
            target_row_ids=target_row_ids,
        )
    finally:
        close_old_connections()


def run_ad_difficulty_job_task(
    job_id: str,
    user_id: int,
    asins: list[str],
    target_row_pks: list[int] | None = None,
) -> None:
    from .views import _run_ad_difficulty_job

    close_old_connections()
    try:
        _run_ad_difficulty_job(job_id, user_id, asins, target_row_pks)
    finally:
        close_old_connections()


def run_scheduled_asin_task(
    row_pk: int,
    asin: str,
    lock_owner: str,
    job_log_id: int,
    ad_due: bool,
    roi_due: bool,
    recipient_id: int | None,
) -> None:
    from .asin_job_lock import release
    from .scheduled_jobs import execute_scheduled_asin_worker

    close_old_connections()
    try:
        execute_scheduled_asin_worker(
            row_pk=row_pk,
            job_log_id=job_log_id,
            ad_due=ad_due,
            roi_due=roi_due,
            recipient_id=recipient_id,
        )
    except Exception:
        logger.exception('scheduled RQ task failed row_pk=%s asin=%s', row_pk, asin)
        raise
    finally:
        release(asin, lock_owner)
        close_old_connections()
