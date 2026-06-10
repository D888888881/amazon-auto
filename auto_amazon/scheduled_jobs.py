"""重点关注 ASIN 的定时 ROI / 广告难度任务。"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db import close_old_connections
from django.utils import timezone

from .asin_access import normalize_asin
from .asin_job_lock import AsinComputeLock
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
from .resilient_wizard import (
    ordered_unique_asins,
    run_ad_difficulty_asins_batch,
    run_roi_asins_batch,
)

logger = logging.getLogger(__name__)


@dataclass
class ScheduledWorkItem:
    row_pk: int
    asin: str
    ad_due: bool
    roi_due: bool
    recipient_id: int | None
    lock_owner: str
    job_log_id: int

    def to_dict(self) -> dict:
        return {
            'row_pk': self.row_pk,
            'asin': self.asin,
            'ad_due': self.ad_due,
            'roi_due': self.roi_due,
            'recipient_id': self.recipient_id,
            'lock_owner': self.lock_owner,
            'job_log_id': self.job_log_id,
        }


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
    """
    双档预警（取最严重一档）：
    - 运营难度：＜15% 开始预警，＜10% 立即淘汰
    - 广告难度：＞30% 开始预警，＞50% 立即淘汰
    - 去广告投产比：＜100% 开始预警，＜80% 立即淘汰
    """
    severity: str | None = None

    def _raise(level: str) -> None:
        nonlocal severity
        if level == 'eliminate':
            severity = 'eliminate'
        elif severity != 'eliminate' and level == 'alert':
            severity = 'alert'

    if latest_ops_difficulty is not None:
        if latest_ops_difficulty <= 10:
            _raise('eliminate')
        elif latest_ops_difficulty <= 15:
            _raise('alert')

    if latest_ad_difficulty is not None:
        if latest_ad_difficulty >= 50:
            _raise('eliminate')
        elif latest_ad_difficulty >= 30:
            _raise('alert')

    if latest_ad_roi is not None:
        if latest_ad_roi <= 80:
            _raise('eliminate')
        elif latest_ad_roi <= 100:
            _raise('alert')

    if severity == 'eliminate':
        return ScheduledTaskMessage.AlertStatus.ELIMINATE
    if severity == 'alert':
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


def _persist_ad_batch_results(
    work_items: list[ScheduledWorkItem],
    rows_by_pk: dict[int, AsinDashboardRow],
    ad_merged: dict,
) -> set[str]:
    from .views import _touch_asin_updates

    row_by_asin = {
        normalize_asin(w.asin): rows_by_pk[w.row_pk]
        for w in work_items
        if w.ad_due and w.row_pk in rows_by_pk
    }
    touched: set[str] = set()
    for asin, payload in ad_merged.items():
        row = row_by_asin.get(normalize_asin(asin))
        if not row:
            continue
        rp = payload.get('ranking_percent')
        try:
            rp_num = float(rp)
        except (TypeError, ValueError):
            rp_num = 0.0
        AsinDashboardRow.objects.filter(pk=row.pk).update(ranking_percent=rp_num)
        touched.add(normalize_asin(asin))
    if touched:
        _touch_asin_updates(touched)
    return touched


def execute_scheduled_batch_worker(work_items: list[ScheduledWorkItem | dict]) -> dict:
    """Worker 内批量执行定时任务（广告难度 / ROI 均并发）。"""
    items: list[ScheduledWorkItem] = []
    for raw in work_items:
        if isinstance(raw, ScheduledWorkItem):
            items.append(raw)
        else:
            items.append(ScheduledWorkItem(**raw))

    if not items:
        return {'messages': 0}

    row_pks = [w.row_pk for w in items]
    rows_by_pk = {
        r.pk: r
        for r in AsinDashboardRow.objects.select_related('user').filter(pk__in=row_pks)
    }

    before_map: dict[int, dict[str, float | None]] = {}
    for w in items:
        row = rows_by_pk.get(w.row_pk)
        if not row:
            continue
        row.refresh_from_db()
        before_map[w.row_pk] = row_metrics_snapshot(row)

    ad_asins = ordered_unique_asins([w.asin for w in items if w.ad_due])
    roi_items = [w for w in items if w.roi_due]
    roi_asins = ordered_unique_asins([w.asin for w in roi_items])

    ad_errors: dict[str, str] = {}
    ad_ok: set[str] = set()
    if ad_asins:
        logger.info('scheduled batch ad difficulty: %d asins', len(ad_asins))
        ad_batch = run_ad_difficulty_asins_batch(ad_asins)
        for failure in ad_batch.failures:
            ad_errors[normalize_asin(failure.asin)] = failure.error
        ad_ok = {normalize_asin(a) for a in ad_batch.succeeded}
        _persist_ad_batch_results(items, rows_by_pk, ad_batch.merged)
        now = timezone.now()
        for w in items:
            if w.ad_due and normalize_asin(w.asin) in ad_ok:
                AsinDashboardRow.objects.filter(pk=w.row_pk).update(last_scheduled_ad_at=now)

    roi_errors: dict[str, str] = {}
    roi_ok: set[str] = set()
    if roi_asins:
        from .views import _merge_cost_overrides_from_db, _persist_wizard_results

        parity = fetch_usd_cny_rate()
        logger.info('scheduled batch roi: %d asins parity=%s', len(roi_asins), parity)
        cost_overrides: dict = {}
        for w in roi_items:
            row = rows_by_pk.get(w.row_pk)
            if not row:
                continue
            co = _build_cost_overrides(row)
            cost_overrides.update(
                _merge_cost_overrides_from_db([normalize_asin(w.asin)], co)
            )

        roi_batch = run_roi_asins_batch(
            roi_asins,
            parity,
            cost_overrides=cost_overrides or None,
        )
        for failure in roi_batch.failures:
            roi_errors[normalize_asin(failure.asin)] = failure.error

        now = timezone.now()
        for w in roi_items:
            asin = normalize_asin(w.asin)
            row = rows_by_pk.get(w.row_pk)
            if not row or asin not in roi_batch.merged:
                continue
            try:
                _persist_wizard_results(
                    row.user_id,
                    {asin: roi_batch.merged[asin]},
                    parity,
                    target_row_ids={asin: row.pk},
                )
                refresh_row_ops_from_media(row)
                AsinDashboardRow.objects.filter(pk=w.row_pk).update(last_scheduled_roi_at=now)
                roi_ok.add(asin)
            except Exception as exc:
                logger.exception('scheduled roi persist failed %s', asin)
                roi_errors[asin] = f'{type(exc).__name__}: {exc}'

    messages_created = 0
    for w in items:
        asin = normalize_asin(w.asin)
        row = rows_by_pk.get(w.row_pk)
        job_log = ScheduledJobLog.objects.filter(pk=w.job_log_id).first()
        if not job_log:
            continue

        if not row:
            job_log.status = ScheduledJobLog.Status.FAILED
            job_log.detail = 'dashboard row not found'
            job_log.finished_at = timezone.now()
            job_log.save(update_fields=['status', 'detail', 'finished_at'])
            continue

        detail_parts: list[str] = []
        item_errors: list[str] = []
        ad_ran = w.ad_due and asin in ad_ok
        roi_ran = w.roi_due and asin in roi_ok

        if w.ad_due:
            if ad_ran:
                detail_parts.append('run ad difficulty')
            elif asin in ad_errors:
                item_errors.append(f'ad: {ad_errors[asin]}')
        if w.roi_due:
            if roi_ran:
                detail_parts.append('run roi')
            elif asin in roi_errors:
                item_errors.append(f'roi: {roi_errors[asin]}')

        ran_any = ad_ran or roi_ran
        if ran_any:
            row.refresh_from_db()
            after = row_metrics_snapshot(row, media_fallback=True)
            recipient = None
            if w.recipient_id:
                recipient = User.objects.filter(pk=w.recipient_id).first()
            if not recipient:
                recipient = resolve_asin_message_recipient(asin) or row.user
            _create_task_message(
                recipient=recipient,
                row=row,
                before=before_map.get(w.row_pk, {}),
                after=after,
                job_log=job_log,
            )
            messages_created += 1

        if not ran_any and item_errors:
            job_log.status = ScheduledJobLog.Status.FAILED
            job_log.detail = '; '.join(item_errors)
        elif item_errors:
            job_log.status = ScheduledJobLog.Status.SUCCESS
            job_log.detail = '; '.join(detail_parts + [f'partial fail: {"; ".join(item_errors)}'])
        elif ran_any:
            job_log.status = ScheduledJobLog.Status.SUCCESS
            job_log.detail = '; '.join(detail_parts)
        else:
            job_log.status = ScheduledJobLog.Status.SKIPPED
            job_log.detail = 'nothing due or skipped'

        job_log.finished_at = timezone.now()
        job_log.save(update_fields=['status', 'detail', 'finished_at'])

    return {'messages': messages_created}


def execute_scheduled_asin_worker(
    *,
    row_pk: int,
    job_log_id: int,
    ad_due: bool,
    roi_due: bool,
    recipient_id: int | None,
) -> None:
    """兼容旧 RQ 单 ASIN 任务入口。"""
    row = AsinDashboardRow.objects.filter(pk=row_pk).only('asin').first()
    if not row:
        ScheduledJobLog.objects.filter(pk=job_log_id).update(
            status=ScheduledJobLog.Status.FAILED,
            detail='dashboard row not found',
            finished_at=timezone.now(),
        )
        return
    execute_scheduled_batch_worker([
        ScheduledWorkItem(
            row_pk=row_pk,
            asin=normalize_asin(row.asin),
            ad_due=ad_due,
            roi_due=roi_due,
            recipient_id=recipient_id,
            lock_owner='',
            job_log_id=job_log_id,
        )
    ])


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


def _collect_work_item(
    row: AsinDashboardRow,
    *,
    due_only: bool,
    dry_run: bool,
    stats: dict,
) -> tuple[ScheduledWorkItem | None, AsinComputeLock | None]:
    asin = normalize_asin(row.asin)
    if not asin:
        stats['skipped'] += 1
        return None, None
    if not asin_media_exists(asin):
        stats['skipped'] += 1
        logger.info('skip %s: media folder missing', asin)
        return None, None

    ad_due = _is_due(row.last_scheduled_ad_at, ad_interval_days())
    roi_due = _is_due(row.last_scheduled_roi_at, roi_interval_days())
    if due_only and not ad_due and not roi_due:
        return None, None

    recipient = resolve_asin_message_recipient(asin) or row.user
    if dry_run:
        stats['processed'] += 1
        logger.info('dry-run would process %s ad_due=%s roi_due=%s', asin, ad_due, roi_due)
        return None, None

    owner = f'scheduler:{asin}:{uuid.uuid4().hex[:8]}'
    lock = AsinComputeLock([asin], owner)
    blocked = lock.acquire()
    if blocked:
        stats['skipped'] += 1
        logger.info('skip %s: locked by another job', asin)
        return None, None

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

    item = ScheduledWorkItem(
        row_pk=row.pk,
        asin=asin,
        ad_due=ad_due,
        roi_due=roi_due,
        recipient_id=recipient.pk if recipient else None,
        lock_owner=owner,
        job_log_id=job_log.pk,
    )
    return item, lock


def _run_work_batch(
    work_items: list[ScheduledWorkItem],
    locks: list[AsinComputeLock],
    *,
    stats: dict,
) -> None:
    from .rq_enqueue import dispatch_scheduled_batch, roi_use_rq

    if not work_items:
        return

    if roi_use_rq():
        try:
            dispatch_scheduled_batch([w.to_dict() for w in work_items])
            stats['enqueued'] = stats.get('enqueued', 0) + len(work_items)
            detail = f'enqueued batch ({len(work_items)} asins) to RQ worker'
            for w in work_items:
                ScheduledJobLog.objects.filter(pk=w.job_log_id).update(detail=detail)
        except Exception as exc:
            logger.exception('enqueue scheduled batch failed')
            now = timezone.now()
            for w in work_items:
                ScheduledJobLog.objects.filter(pk=w.job_log_id).update(
                    status=ScheduledJobLog.Status.FAILED,
                    detail=f'enqueue failed: {exc}',
                    finished_at=now,
                )
            for lock in locks:
                lock.release_all()
            stats['errors'] += len(work_items)
        return

    try:
        result = execute_scheduled_batch_worker(work_items)
        stats['messages'] += int(result.get('messages', 0))
        stats['processed'] += len(work_items)
    except Exception:
        logger.exception('scheduled batch failed')
        stats['errors'] += len(work_items)
    finally:
        for lock in locks:
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

    stats = {
        'enabled': True,
        'processed': 0,
        'skipped': 0,
        'errors': 0,
        'messages': 0,
        'enqueued': 0,
        'candidates': len(rows),
    }

    work_items: list[ScheduledWorkItem] = []
    locks: list[AsinComputeLock] = []
    for row in rows:
        try:
            item, lock = _collect_work_item(row, due_only=due_only, dry_run=dry_run, stats=stats)
            if item and lock:
                work_items.append(item)
                locks.append(lock)
        except Exception:
            logger.exception('unexpected error collecting row pk=%s', row.pk)
            stats['errors'] += 1

    if work_items and not dry_run:
        try:
            _run_work_batch(work_items, locks, stats=stats)
        except Exception:
            logger.exception('unexpected error running scheduled batch')
            stats['errors'] += 1

    return stats
