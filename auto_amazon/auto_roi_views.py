"""自动 ROI 页面与 API。"""
from __future__ import annotations

import threading
from datetime import datetime, time as dt_time

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import close_old_connections
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.views.decorators.http import require_GET, require_POST

from .marketplace import MARKETPLACE_US, get_marketplace, marketplace_label, normalize_marketplace
from .models import RoiAutoRun, RoiAutoRunLog
from .roi_site_defaults import config_to_api_dict, ensure_all_site_configs, ensure_site_config
from .wizard_jobs import get_active_job_for_user

_LOG_PAGE_SIZES = {20, 50, 100}


def _parse_log_datetime(raw: str | None, *, end_of_day: bool = False):
    """解析筛选时间；支持 ISO datetime 或 YYYY-MM-DD。"""
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip().replace(' ', 'T')
    # datetime-local 常为 YYYY-MM-DDTHH:MM，补秒便于解析
    if len(s) == 16 and s[10] == 'T':
        s = s + ':00'
    dt = parse_datetime(s)
    if dt is None:
        d = parse_date(s[:10] if len(s) >= 10 else s)
        if d is None:
            return None
        dt = datetime.combine(d, dt_time.max if end_of_day else dt_time.min)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _log_to_dict(log: RoiAutoRunLog) -> dict:
    return {
        'id': log.pk,
        'run_id': log.run_id,
        'asin': log.asin,
        'seq': log.seq,
        'status': log.status,
        'status_label': log.get_status_display(),
        'attempt': log.attempt,
        'account_username': log.account_username,
        'duration_ms': log.duration_ms,
        'error_summary': log.error_summary,
        'error_detail': log.error_detail,
        'created_at': log.created_at.isoformat() if log.created_at else None,
    }


def _active_auto_run(user, marketplace: str) -> RoiAutoRun | None:
    return (
        RoiAutoRun.objects.filter(
            user=user,
            marketplace=marketplace,
            status__in=[RoiAutoRun.Status.RUNNING, RoiAutoRun.Status.PAUSED],
        )
        .order_by('-id')
        .first()
    )


def _run_to_dict(run: RoiAutoRun | None) -> dict | None:
    if not run:
        return None
    remaining = max(0, int(run.total or 0) - int(run.succeeded or 0) - int(run.failed or 0))
    return {
        'id': run.pk,
        'marketplace': run.marketplace,
        'status': run.status,
        'status_label': run.get_status_display(),
        'total': run.total,
        'succeeded': run.succeeded,
        'failed': run.failed,
        'skipped': run.skipped,
        'remaining': remaining,
        'current_asin': run.current_asin,
        'last_account': run.last_account,
        'parity': run.parity,
        'ban_rotations': run.ban_rotations,
        'consecutive_fails': run.consecutive_fails,
        'error_message': run.error_message,
        'started_at': run.started_at.isoformat() if run.started_at else None,
        'finished_at': run.finished_at.isoformat() if run.finished_at else None,
        'updated_at': run.updated_at.isoformat() if run.updated_at else None,
    }


def _dispatch_auto_roi(run_id: int) -> str | None:
    """入队或后台线程启动；返回 rq_job_id（线程模式为 None）。"""
    from .rq_enqueue import should_use_rq_queue
    from django.conf import settings

    queue_name = getattr(settings, 'RQ_QUEUE_ROI_BULK', 'roi_bulk')
    if should_use_rq_queue(queue_name):
        import django_rq

        q = django_rq.get_queue(queue_name)
        job = q.enqueue(
            'auto_amazon.rq_tasks.run_auto_roi_task',
            run_id,
            job_timeout=getattr(settings, 'RQ_JOB_TIMEOUT', 86400),
        )
        return str(job.id)

    def _thread_target():
        close_old_connections()
        try:
            from .auto_roi_runner import run_auto_roi

            run_auto_roi(run_id)
        finally:
            close_old_connections()

    threading.Thread(target=_thread_target, daemon=True, name=f'auto-roi-{run_id}').start()
    return None


@login_required
@require_GET
def auto_roi_page(request):
    ensure_all_site_configs()
    mp = normalize_marketplace(get_marketplace(request)) or MARKETPLACE_US
    cfg = ensure_site_config(mp)
    run = _active_auto_run(request.user, mp)
    from .views import _default_exchange_rate_for_form, _discover_local_asins, _compute_allowed_asins_for_user

    pending, _ = _discover_local_asins(force_recompute=False, marketplace=mp)
    allowed = _compute_allowed_asins_for_user(request.user, marketplace=mp)
    if allowed is not None:
        pending = [a for a in pending if a in allowed]
    parity_default = cfg.exchange_rate_override
    if parity_default is None:
        try:
            parity_default = float(_default_exchange_rate_for_form())
        except (TypeError, ValueError):
            parity_default = 7.2

    return render(
        request,
        'auto_amazon/auto_roi.html',
        {
            'current_marketplace': mp,
            'current_site_label': marketplace_label(mp),
            'pending_count': len(pending),
            'config': config_to_api_dict(cfg),
            'active_run': _run_to_dict(run),
            'default_parity': parity_default,
            'wizard_busy': bool(get_active_job_for_user(request.user.id)),
        },
    )


@login_required
@require_GET
def auto_roi_status(request):
    mp = normalize_marketplace(get_marketplace(request)) or MARKETPLACE_US
    run_id = request.GET.get('run_id')
    if run_id:
        run = RoiAutoRun.objects.filter(pk=run_id, user=request.user).first()
    else:
        run = _active_auto_run(request.user, mp)
        if not run:
            run = (
                RoiAutoRun.objects.filter(user=request.user, marketplace=mp)
                .order_by('-id')
                .first()
            )
    from .views import _discover_local_asins, _compute_allowed_asins_for_user

    pending, _ = _discover_local_asins(force_recompute=False, marketplace=mp)
    allowed = _compute_allowed_asins_for_user(request.user, marketplace=mp)
    if allowed is not None:
        pending = [a for a in pending if a in allowed]
    cfg = ensure_site_config(mp)
    return JsonResponse(
        {
            'ok': True,
            'marketplace': mp,
            'pending_count': len(pending),
            'run': _run_to_dict(run),
            'config': config_to_api_dict(cfg),
        }
    )


@login_required
@require_GET
def auto_roi_logs(request):
    """执行日志：筛选 + 分页（当前用户、当前站点）。"""
    mp = normalize_marketplace(get_marketplace(request)) or MARKETPLACE_US
    run_ids = list(
        RoiAutoRun.objects.filter(user=request.user, marketplace=mp).values_list('id', flat=True)
    )
    qs = RoiAutoRunLog.objects.filter(run_id__in=run_ids).select_related('run')

    run_id_raw = (request.GET.get('run_id') or '').strip()
    if run_id_raw.isdigit():
        rid = int(run_id_raw)
        if rid in set(run_ids):
            qs = qs.filter(run_id=rid)

    asin_kw = (request.GET.get('asin') or request.GET.get('asin_kw') or '').strip().upper()
    if asin_kw:
        qs = qs.filter(asin__icontains=asin_kw)

    account = (request.GET.get('account') or '').strip()
    if account:
        qs = qs.filter(account_username__icontains=account)

    status = (request.GET.get('status') or '').strip().lower()
    if status in {
        RoiAutoRunLog.Status.SUCCESS,
        RoiAutoRunLog.Status.FAILED,
        RoiAutoRunLog.Status.RETRY,
        RoiAutoRunLog.Status.BANNED_ROTATED,
    }:
        qs = qs.filter(status=status)
    elif status == 'ok':
        qs = qs.filter(status=RoiAutoRunLog.Status.SUCCESS)
    elif status == 'fail':
        qs = qs.filter(status=RoiAutoRunLog.Status.FAILED)
    elif status == 'other':
        qs = qs.filter(
            status__in=[RoiAutoRunLog.Status.RETRY, RoiAutoRunLog.Status.BANNED_ROTATED]
        )

    t_from = _parse_log_datetime(request.GET.get('time_from') or request.GET.get('from'))
    t_to = _parse_log_datetime(
        request.GET.get('time_to') or request.GET.get('to'),
        end_of_day=True,
    )
    if t_from:
        qs = qs.filter(created_at__gte=t_from)
    if t_to:
        qs = qs.filter(created_at__lte=t_to)

    try:
        per_page = int(request.GET.get('per_page') or 50)
    except (TypeError, ValueError):
        per_page = 50
    if per_page not in _LOG_PAGE_SIZES:
        per_page = 50
    try:
        page = max(1, int(request.GET.get('page') or 1))
    except (TypeError, ValueError):
        page = 1

    qs = qs.order_by('-created_at', '-id')
    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(page)

    accounts = list(
        RoiAutoRunLog.objects.filter(run_id__in=run_ids)
        .exclude(Q(account_username='') | Q(account_username__isnull=True))
        .values_list('account_username', flat=True)
        .distinct()
        .order_by('account_username')[:200]
    )

    return JsonResponse(
        {
            'ok': True,
            'marketplace': mp,
            'count': paginator.count,
            'page': page_obj.number,
            'num_pages': paginator.num_pages or 1,
            'per_page': per_page,
            'has_previous': page_obj.has_previous(),
            'has_next': page_obj.has_next(),
            'previous_page': page_obj.previous_page_number() if page_obj.has_previous() else None,
            'next_page': page_obj.next_page_number() if page_obj.has_next() else None,
            'filters': {
                'asin': asin_kw,
                'account': account,
                'status': status,
                'time_from': request.GET.get('time_from') or request.GET.get('from') or '',
                'time_to': request.GET.get('time_to') or request.GET.get('to') or '',
                'run_id': run_id_raw if run_id_raw.isdigit() else '',
            },
            'accounts': accounts,
            'results': [_log_to_dict(log) for log in page_obj.object_list],
        }
    )


@login_required
@require_POST
def auto_roi_start(request):
    mp = normalize_marketplace(get_marketplace(request)) or MARKETPLACE_US
    try:
        from .credentials_config import assert_sif_authorization_usable, sif_authorization_expiry_info

        assert_sif_authorization_usable(for_auto_roi=True)
        jwt_info = sif_authorization_expiry_info()
    except ValueError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)

    if get_active_job_for_user(request.user.id):
        return JsonResponse(
            {'ok': False, 'error': '当前有手动计算 ROI 任务进行中，请先完成或解除后再开启自动 ROI。'},
            status=409,
        )
    existing = _active_auto_run(request.user, mp)
    if existing and existing.status == RoiAutoRun.Status.RUNNING:
        return JsonResponse(
            {'ok': False, 'error': '本站已有自动 ROI 在运行。', 'run': _run_to_dict(existing)},
            status=409,
        )

    cfg = ensure_site_config(mp)
    parity_raw = (request.POST.get('parity') or request.POST.get('exchange_rate') or '').strip()
    if parity_raw:
        try:
            parity = float(parity_raw)
        except ValueError:
            return JsonResponse({'ok': False, 'error': '汇率无效'}, status=400)
    elif cfg.exchange_rate_override is not None:
        parity = float(cfg.exchange_rate_override)
    else:
        from .views import _default_exchange_rate_for_form

        try:
            parity = float(_default_exchange_rate_for_form())
        except (TypeError, ValueError):
            parity = 7.2
    if parity <= 0:
        return JsonResponse({'ok': False, 'error': '汇率必须大于 0'}, status=400)

    from .views import _discover_local_asins, _compute_allowed_asins_for_user

    pending, _ = _discover_local_asins(force_recompute=False, marketplace=mp)
    allowed = _compute_allowed_asins_for_user(request.user, marketplace=mp)
    if allowed is not None:
        pending = [a for a in pending if a in allowed]
    if not pending and not (existing and existing.status == RoiAutoRun.Status.PAUSED):
        return JsonResponse({'ok': False, 'error': '当前站点没有待计算 ASIN。'}, status=400)

    if existing and existing.status == RoiAutoRun.Status.PAUSED:
        existing.status = RoiAutoRun.Status.RUNNING
        existing.parity = parity
        existing.error_message = ''
        existing.finished_at = None
        existing.consecutive_fails = 0
        existing.save(
            update_fields=[
                'status',
                'parity',
                'error_message',
                'finished_at',
                'consecutive_fails',
                'updated_at',
            ]
        )
        run = existing
    else:
        run = RoiAutoRun.objects.create(
            user=request.user,
            marketplace=mp,
            status=RoiAutoRun.Status.RUNNING,
            total=len(pending),
            parity=parity,
        )

    rq_id = _dispatch_auto_roi(run.pk)
    if rq_id:
        run.rq_job_id = rq_id
        run.save(update_fields=['rq_job_id', 'updated_at'])

    payload = {'ok': True, 'run': _run_to_dict(run)}
    if jwt_info.get('expiring_soon'):
        payload['warning'] = jwt_info.get('message')
    return JsonResponse(payload)


@login_required
@require_POST
def auto_roi_pause(request):
    mp = normalize_marketplace(get_marketplace(request)) or MARKETPLACE_US
    run = _active_auto_run(request.user, mp)
    if not run or run.status != RoiAutoRun.Status.RUNNING:
        return JsonResponse({'ok': False, 'error': '没有运行中的自动 ROI。'}, status=400)
    run.status = RoiAutoRun.Status.PAUSED
    run.save(update_fields=['status', 'updated_at'])
    return JsonResponse({'ok': True, 'run': _run_to_dict(run)})


@login_required
@require_POST
def auto_roi_stop(request):
    mp = normalize_marketplace(get_marketplace(request)) or MARKETPLACE_US
    run = _active_auto_run(request.user, mp)
    if not run:
        return JsonResponse({'ok': False, 'error': '没有可停止的自动 ROI。'}, status=400)
    run.status = RoiAutoRun.Status.STOPPED
    run.finished_at = timezone.now()
    run.current_asin = ''
    run.save(update_fields=['status', 'finished_at', 'current_asin', 'updated_at'])
    return JsonResponse({'ok': True, 'run': _run_to_dict(run)})


@login_required
@require_POST
def auto_roi_save_config(request):
    mp = normalize_marketplace(request.POST.get('marketplace') or get_marketplace(request)) or MARKETPLACE_US
    cfg = ensure_site_config(mp)

    def _f(name, cast=float, default=None):
        raw = request.POST.get(name)
        if raw is None or str(raw).strip() == '':
            return default
        return cast(raw)

    try:
        cfg.platform_commission = _f('platform_commission', float, cfg.platform_commission)
        cfg.default_refund_rate = _f('default_refund_rate', float, cfg.default_refund_rate)
        cfg.default_fba_fee = _f('default_fba_fee', float, cfg.default_fba_fee)
        cfg.default_unit_purchase = _f('default_unit_purchase', float, cfg.default_unit_purchase)
        cfg.batch_size = max(1, int(_f('batch_size', float, cfg.batch_size)))
        cfg.asin_delay_min_sec = _f('asin_delay_min_sec', float, cfg.asin_delay_min_sec)
        cfg.asin_delay_max_sec = _f('asin_delay_max_sec', float, cfg.asin_delay_max_sec)
        cfg.batch_delay_min_sec = _f('batch_delay_min_sec', float, cfg.batch_delay_min_sec)
        cfg.batch_delay_max_sec = _f('batch_delay_max_sec', float, cfg.batch_delay_max_sec)
        cfg.max_ban_rotations_per_run = max(
            1, int(_f('max_ban_rotations_per_run', float, cfg.max_ban_rotations_per_run))
        )
        cfg.consecutive_fail_pause = max(
            1, int(_f('consecutive_fail_pause', float, cfg.consecutive_fail_pause))
        )
        cfg.max_ban_retries_per_asin = max(
            1, int(_f('max_ban_retries_per_asin', float, cfg.max_ban_retries_per_asin))
        )
        er = request.POST.get('exchange_rate_override')
        if er is None or str(er).strip() == '':
            cfg.exchange_rate_override = None
        else:
            cfg.exchange_rate_override = float(er)
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'error': '定值格式无效'}, status=400)

    if cfg.asin_delay_max_sec < cfg.asin_delay_min_sec:
        cfg.asin_delay_min_sec, cfg.asin_delay_max_sec = (
            cfg.asin_delay_max_sec,
            cfg.asin_delay_min_sec,
        )
    if cfg.batch_delay_max_sec < cfg.batch_delay_min_sec:
        cfg.batch_delay_min_sec, cfg.batch_delay_max_sec = (
            cfg.batch_delay_max_sec,
            cfg.batch_delay_min_sec,
        )
    cfg.save()
    return JsonResponse({'ok': True, 'config': config_to_api_dict(cfg)})
