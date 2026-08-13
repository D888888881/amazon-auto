"""自动 ROI 页面与 API。"""
from __future__ import annotations

import threading

from django.contrib.auth.decorators import login_required
from django.db import close_old_connections
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .marketplace import MARKETPLACE_US, get_marketplace, marketplace_label, normalize_marketplace
from .models import RoiAutoRun, RoiAutoRunLog
from .roi_site_defaults import config_to_api_dict, ensure_all_site_configs, ensure_site_config
from .wizard_jobs import get_active_job_for_user


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
    after_id = int(request.GET.get('after_id') or 0)
    logs_qs = RoiAutoRunLog.objects.none()
    if run:
        logs_qs = run.logs.filter(id__gt=after_id).order_by('id')[:80]
    logs = [
        {
            'id': log.pk,
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
        for log in logs_qs
    ]
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
            'logs': logs,
            'config': config_to_api_dict(cfg),
        }
    )


@login_required
@require_POST
def auto_roi_start(request):
    mp = normalize_marketplace(get_marketplace(request)) or MARKETPLACE_US
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

    return JsonResponse({'ok': True, 'run': _run_to_dict(run)})


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
