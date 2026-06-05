"""重点关注 ASIN 的定时 ROI / 广告难度任务。"""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db import close_old_connections
from django.utils import timezone

from .asin_access import normalize_asin
from .asin_job_lock import AsinComputeLock
from .asin_wizard import run_ad_difficulty_for_asins, run_seller_wizard
from .exchange_rate import fetch_usd_cny_rate
from .media_paths import media_root
from .models import (
    AsinCatalogItem,
    AsinDashboardRow,
    ImportedMediaPath,
    ScheduledJobLog,
    ScheduledTaskMessage,
)
from .ops_metrics import refresh_row_ops_from_media, row_metrics_snapshot

logger = logging.getLogger(__name__)


def scheduler_enabled() -> bool:
    return getattr(settings, 'SCHEDULER_ENABLED', True)


def roi_interval_days() -> int:
    return int(getattr(settings, 'PRIORITY_ROI_INTERVAL_DAYS', 7))


def ad_interval_days() -> int:
    return int(getattr(settings, 'PRIORITY_AD_INTERVAL_DAYS', 7))


def asin_media_exists(asin: str) -> bool:
    a = normalize_asin(asin)
    if not a:
        return False
    return (media_root() / a).is_dir()


def resolve_asin_message_recipient(asin: str) -> User | None:
    """消息收件人：优先 ASIN 上传者，其次导入者，再看任意看板行归属用户。"""
    a = normalize_asin(asin)
    if not a:
        return None
    cat = (
        AsinCatalogItem.objects.filter(asin=a)
        .select_related('uploaded_by')
        .order_by('-created_at')
        .first()
    )
    if cat and cat.uploaded_by_id:
        return cat.uploaded_by
    imp = (
        ImportedMediaPath.objects.filter(rel_path=a)
        .select_related('user')
        .order_by('-created_at')
        .first()
    )
    if imp and imp.user_id:
        return imp.user
    row = AsinDashboardRow.objects.filter(asin=a).order_by('-created_at').first()
    return row.user if row else None


def dedupe_priority_rows_for_scheduler(rows: list[AsinDashboardRow]) -> list[AsinDashboardRow]:
    by_asin: dict[str, AsinDashboardRow] = {}
    for row in rows:
        key = normalize_asin(row.asin)
        if not key:
            continue
        if key not in by_asin:
            by_asin[key] = row
            continue
        recipient = resolve_asin_message_recipient(key)
        cur = by_asin[key]
        if recipient:
            if cur.user_id != recipient.id and row.user_id == recipient.id:
                by_asin[key] = row
                continue
            if row.user_id == recipient.id and cur.user_id != recipient.id:
                continue
        if row.created_at > cur.created_at:
            by_asin[key] = row
    return list(by_asin.values())


def _is_due(last_at, interval_days: int) -> bool:
    if last_at is None:
        return True
    return timezone.now() - last_at >= timedelta(days=interval_days)


def _format_delta(delta: float | None) -> str:
    if delta is None:
        return ''
    if delta > 0:
        return f'↑{delta:.2f}'
    if delta < 0:
        return f'↓{abs(delta):.2f}'
    return '—'


def _calc_delta(before: float | None, after: float | None) -> float | None:
    if before is None or after is None:
        return None
    return round(after - before, 4)


def compute_alert_status(
    latest_ad_roi: float | None,
    latest_ad_difficulty: float | None,
    latest_ops_difficulty: float | None,
) -> str:
    """任一最新指标触发阈值则开始预警。"""
    if latest_ops_difficulty is not None and latest_ops_difficulty < 10:
        return ScheduledTaskMessage.AlertStatus.ALERT
    if latest_ad_difficulty is not None and latest_ad_difficulty > 50:
        return ScheduledTaskMessage.AlertStatus.ALERT
    if latest_ad_roi is not None and latest_ad_roi < 80:
        return ScheduledTaskMessage.AlertStatus.ALERT
    return ScheduledTaskMessage.AlertStatus.NORMAL


def _build_cost_overrides(row: AsinDashboardRow) -> dict:
    one: dict = {}
    if row.unit_purchase is not None:
        one['unit_purchase'] = float(row.unit_purchase)
    if row.head_distance is not None:
        one['head_distance'] = float(row.head_distance)
    if not one:
        return {}
    return {normalize_asin(row.asin): one}


def _execute_ad_for_row(row: AsinDashboardRow) -> None:
    asin = normalize_asin(row.asin)
    result = run_ad_difficulty_for_asins([asin])
    payload = result.get(asin) or {}
    rp = payload.get('ranking_percent')
    try:
        rp_num = float(rp)
    except (TypeError, ValueError):
        rp_num = 0.0
    AsinDashboardRow.objects.filter(pk=row.pk).update(ranking_percent=rp_num)
    from .views import _touch_asin_updates

    _touch_asin_updates({asin})


def _execute_roi_for_row(row: AsinDashboardRow, parity: float) -> None:
    from .views import _persist_wizard_results

    asin = normalize_asin(row.asin)
    cost_overrides = _build_cost_overrides(row)
    result = run_seller_wizard([asin], parity, cost_overrides=cost_overrides or None)
    _persist_wizard_results(
        row.user_id,
        result,
        parity,
        target_row_ids={asin: row.pk},
    )


def _create_task_message(
    *,
    recipient: User,
    row: AsinDashboardRow,
    before: dict[str, float | None],
    after: dict[str, float | None],
    job_log: ScheduledJobLog | None,
) -> ScheduledTaskMessage:
    d_roi = _calc_delta(before.get('ad_roi'), after.get('ad_roi'))
    d_ad = _calc_delta(before.get('ad_difficulty'), after.get('ad_difficulty'))
    d_ops = _calc_delta(before.get('ops_difficulty'), after.get('ops_difficulty'))
    alert = compute_alert_status(
        after.get('ad_roi'),
        after.get('ad_difficulty'),
        after.get('ops_difficulty'),
    )
    return ScheduledTaskMessage.objects.create(
        recipient=recipient,
        asin=normalize_asin(row.asin),
        dashboard_row=row,
        curr_ad_roi=before.get('ad_roi'),
        curr_ad_difficulty=before.get('ad_difficulty'),
        curr_ops_difficulty=before.get('ops_difficulty'),
        latest_ad_roi=after.get('ad_roi'),
        latest_ad_difficulty=after.get('ad_difficulty'),
        latest_ops_difficulty=after.get('ops_difficulty'),
        delta_ad_roi=d_roi,
        delta_ad_difficulty=d_ad,
        delta_ops_difficulty=d_ops,
        delta_ad_roi_text=_format_delta(d_roi),
        delta_ad_difficulty_text=_format_delta(d_ad),
        delta_ops_difficulty_text=_format_delta(d_ops),
        alert_status=alert,
        job_log=job_log,
    )


def _process_one_row(
    row: AsinDashboardRow,
    *,
    due_only: bool,
    dry_run: bool,
    stats: dict,
) -> None:
    asin = normalize_asin(row.asin)
    if not asin:
        stats['skipped'] += 1
        return
    if not asin_media_exists(asin):
        stats['skipped'] += 1
        logger.info('skip %s: media folder missing', asin)
        return

    ad_due = _is_due(row.last_scheduled_ad_at, ad_interval_days())
    roi_due = _is_due(row.last_scheduled_roi_at, roi_interval_days())
    if due_only and not ad_due and not roi_due:
        return

    recipient = resolve_asin_message_recipient(asin) or row.user
    if dry_run:
        stats['processed'] += 1
        logger.info('dry-run would process %s ad_due=%s roi_due=%s', asin, ad_due, roi_due)
        return

    owner = f'scheduler:{asin}:{uuid.uuid4().hex[:8]}'
    lock = AsinComputeLock([asin], owner)
    blocked = lock.acquire()
    if blocked:
        stats['skipped'] += 1
        logger.info('skip %s: locked by another job', asin)
        return

    job_type = ScheduledJobLog.JobType.COMBINED
    if ad_due and not roi_due:
        job_type = ScheduledJobLog.JobType.AD_DIFFICULTY
    elif roi_due and not ad_due:
        job_type = ScheduledJobLog.JobType.ROI

    job_log = ScheduledJobLog.objects.create(
        job_type=job_type,
        status=ScheduledJobLog.Status.SUCCESS,
        asin_list=[asin],
        detail='',
    )
    detail_lines: list[str] = []
    ran_any = False

    try:
        row.refresh_from_db()
        before = row_metrics_snapshot(row)

        if ad_due:
            detail_lines.append('run ad difficulty')
            _execute_ad_for_row(row)
            AsinDashboardRow.objects.filter(pk=row.pk).update(last_scheduled_ad_at=timezone.now())
            ran_any = True

        row.refresh_from_db()

        if roi_due:
            parity = fetch_usd_cny_rate()
            detail_lines.append(f'run roi parity={parity}')
            _execute_roi_for_row(row, parity)
            refresh_row_ops_from_media(row)
            AsinDashboardRow.objects.filter(pk=row.pk).update(last_scheduled_roi_at=timezone.now())
            ran_any = True

        if ran_any:
            row.refresh_from_db()
            after = row_metrics_snapshot(row, media_fallback=True)
            _create_task_message(
                recipient=recipient,
                row=row,
                before=before,
                after=after,
                job_log=job_log,
            )
            stats['messages'] += 1
            stats['processed'] += 1
        else:
            job_log.status = ScheduledJobLog.Status.SKIPPED
            stats['skipped'] += 1

        job_log.detail = '; '.join(detail_lines)
        job_log.finished_at = timezone.now()
        job_log.save(update_fields=['status', 'detail', 'finished_at'])
    except Exception as exc:
        logger.exception('scheduled job failed for %s', asin)
        job_log.status = ScheduledJobLog.Status.FAILED
        job_log.detail = f'{type(exc).__name__}: {exc}'
        job_log.finished_at = timezone.now()
        job_log.save(update_fields=['status', 'detail', 'finished_at'])
        stats['errors'] += 1
    finally:
        lock.release_all()
        close_old_connections()


def run_scheduled_asin_jobs(*, due_only: bool = True, dry_run: bool = False) -> dict:
    if not scheduler_enabled():
        return {'enabled': False, 'processed': 0, 'skipped': 0, 'errors': 0, 'messages': 0}

    rows = list(
        AsinDashboardRow.objects.filter(
            follow_status=AsinDashboardRow.FollowStatus.PRIORITY,
        ).select_related('user')
    )
    rows = dedupe_priority_rows_for_scheduler(rows)

    stats = {'enabled': True, 'processed': 0, 'skipped': 0, 'errors': 0, 'messages': 0, 'candidates': len(rows)}
    for row in rows:
        try:
            _process_one_row(row, due_only=due_only, dry_run=dry_run, stats=stats)
        except Exception:
            logger.exception('unexpected error processing row pk=%s', row.pk)
            stats['errors'] += 1
    return stats
