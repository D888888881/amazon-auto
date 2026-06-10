"""ROI / 广告难度异步任务：状态查询、活跃任务占用。"""
from __future__ import annotations

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

WIZARD_JOB_TTL = 7200
STALE_ACTIVE_JOB_SEC = 600
TERMINAL_STATUSES = frozenset({'done', 'error', 'done_with_errors'})

STATUS_LABELS = {
    'queued': '排队中',
    'running': '执行中',
    'done': '已完成',
    'done_with_errors': '部分完成',
    'error': '失败',
    'unknown': '未知',
}


def wizard_job_key(job_id: str) -> str:
    return f'wizard_job_{job_id}'


def user_active_job_key(user_id: int) -> str:
    return f'active_job_user_{user_id}'


def set_user_active_job(user_id: int, job_id: str) -> None:
    cache.set(user_active_job_key(user_id), job_id, WIZARD_JOB_TTL)


def clear_user_active_job(user_id: int, job_id: str) -> None:
    cur = cache.get(user_active_job_key(user_id))
    if cur == job_id:
        cache.delete(user_active_job_key(user_id))


def new_job_entry(
    user_id: int,
    progress: list[str],
    *,
    status: str = 'queued',
    task_type: str | None = None,
    **dispatch_meta,
) -> dict:
    ent = {
        'status': status,
        'user_id': user_id,
        'progress': progress,
        'created_at': timezone.now().isoformat(),
    }
    if task_type:
        ent['task_type'] = task_type
    ent.update(dispatch_meta)
    return ent


def load_job_entry(job_id: str) -> dict | None:
    return cache.get(wizard_job_key(job_id))


def refresh_job_entry(job_id: str) -> dict | None:
    """读取任务并在必要时 rescue 长期 queued 的任务。"""
    from .rq_enqueue import maybe_rescue_stuck_queued_job

    maybe_rescue_stuck_queued_job(job_id)
    return load_job_entry(job_id)


def _queued_wait_seconds(ent: dict) -> int | None:
    raw = ent.get('created_at')
    if not raw:
        return None
    dt = parse_datetime(str(raw))
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return max(0, int((timezone.now() - dt).total_seconds()))


def _status_hint(status: str, ent: dict) -> str:
    if status == 'queued':
        wait = _queued_wait_seconds(ent)
        if wait is not None and wait >= 15:
            return (
                f'排队中（已等待 {wait} 秒）。'
                '未检测到 RQ Worker 时将自动切换为 Web 后台执行；'
                'Docker 环境请确认 worker 容器已启动。'
            )
        return '任务已创建，正在准备执行…'
    if status == 'running':
        prog = ent.get('progress') or []
        if prog:
            return str(prog[-1])[:240]
        mode = ent.get('exec_mode')
        if mode == 'thread':
            return 'Web 后台正在计算，请稍候…'
        return 'Worker 正在计算，请稍候…'
    if status == 'done':
        return '任务已成功完成，可关闭进度窗口或发起新任务。'
    if status == 'done_with_errors':
        return ent.get('error') or '部分 ASIN 计算失败，请查看详情。'
    if status == 'error':
        return ent.get('error') or '任务失败，请查看下方错误信息。'
    return ''


def job_status_payload(job_id: str, ent: dict) -> dict:
    status = ent.get('status') or 'unknown'
    prog = ent.get('progress') or []
    err_tail = ent.get('error_detail') or ''
    if len(err_tail) > 8000:
        err_tail = err_tail[-8000:]
    show_error_detail = status in ('error', 'done_with_errors')
    wait_sec = _queued_wait_seconds(ent) if status == 'queued' else None
    return {
        'job_id': job_id,
        'status': status,
        'status_label': STATUS_LABELS.get(status, status),
        'status_hint': _status_hint(status, ent),
        'queued_seconds': wait_sec,
        'is_terminal': status in TERMINAL_STATUSES,
        'is_blocking': status not in TERMINAL_STATUSES,
        'progress': prog,
        'last_progress': prog[-1] if prog else '',
        'error': ent.get('error'),
        'error_detail': err_tail if show_error_detail else None,
        'rows_written': ent.get('rows_written'),
        'success_count': ent.get('success_count'),
        'fail_count': ent.get('fail_count'),
        'failed_asins': ent.get('failed_asins', []),
        'failures': ent.get('failures', []),
        'created_at': ent.get('created_at'),
        'redirect': ent.get('redirect') or reverse('index'),
    }


def _maybe_expire_stale_active_job(user_id: int, job_id: str, ent: dict) -> dict | None:
    """长期 queued 且无法 rescue 的任务，自动释放占用避免页面永久卡住。"""
    status = ent.get('status') or 'unknown'
    if status != 'queued':
        return ent
    wait = _queued_wait_seconds(ent)
    if wait is None:
        return ent
    if wait >= 120 and not ent.get('task_type') and not ent.get('rescue_dispatched'):
        clear_user_active_job(user_id, job_id)
        try:
            from .rq_enqueue import cancel_rq_jobs_for_wizard_job

            cancel_rq_jobs_for_wizard_job(job_id)
        except Exception:
            pass
        return None
    if wait < STALE_ACTIVE_JOB_SEC:
        return ent
    ent['status'] = 'error'
    ent['error'] = '任务长时间未响应，已自动终止。请重新发起计算。'
    cache.set(wizard_job_key(job_id), ent, 3600)
    clear_user_active_job(user_id, job_id)
    try:
        from .asin_job_lock import release_job_locks

        release_job_locks(user_id, job_id, ent.get('asins'))
    except Exception:
        pass
    try:
        from .rq_enqueue import cancel_rq_jobs_for_wizard_job

        cancel_rq_jobs_for_wizard_job(job_id)
    except Exception:
        pass
    return None


def get_active_job_for_user(user_id: int, *, auto_release_finished: bool = True) -> dict | None:
    """
    返回当前占用中的任务快照；若任务已结束但占用未释放，可选自动清理。
    """
    job_id = cache.get(user_active_job_key(user_id))
    if not job_id:
        return None
    ent = refresh_job_entry(job_id)
    if not ent or ent.get('user_id') != user_id:
        cache.delete(user_active_job_key(user_id))
        return None
    ent = _maybe_expire_stale_active_job(user_id, job_id, ent)
    if not ent:
        return None
    status = ent.get('status') or 'unknown'
    if auto_release_finished and status in TERMINAL_STATUSES:
        clear_user_active_job(user_id, job_id)
        payload = job_status_payload(job_id, ent)
        payload['released'] = True
        return None
    return job_status_payload(job_id, ent)


def dismiss_active_job(user_id: int, job_id: str | None = None) -> tuple[bool, str]:
    """解除「已有任务在运行」占用，便于发起新任务。"""
    cur = job_id or cache.get(user_active_job_key(user_id))
    if not cur:
        return True, '当前无占用中的任务'
    ent = cache.get(wizard_job_key(cur))
    if ent and ent.get('user_id') not in (None, user_id):
        return False, '无权操作该任务'
    try:
        from .rq_enqueue import cancel_rq_jobs_for_wizard_job

        cancel_rq_jobs_for_wizard_job(cur)
    except Exception:
        pass
    released = 0
    try:
        from .asin_job_lock import release_job_locks

        released = release_job_locks(user_id, cur, (ent or {}).get('asins'))
    except Exception:
        pass
    clear_user_active_job(user_id, cur)
    if released:
        return True, f'已解除任务占用并释放 {released} 个 ASIN 计算锁，可以发起新计算'
    return True, '已解除任务占用，可以发起新计算'
