"""ROI / 广告难度 / 定时任务入队。"""

from __future__ import annotations



import logging

import threading

from datetime import datetime, timezone as dt_tz

from typing import Any



from django.conf import settings



logger = logging.getLogger(__name__)



RESCUE_QUEUED_AFTER_SEC = 15

WORKER_HEARTBEAT_MAX_AGE_SEC = 120





def roi_use_rq() -> bool:

    return getattr(settings, 'ROI_USE_RQ', True)





def _job_timeout() -> int | str:

    return getattr(settings, 'RQ_JOB_TIMEOUT', 86400)





def _queue(name: str):

    import django_rq



    return django_rq.get_queue(name)





def _worker_is_alive(worker) -> bool:

    hb = getattr(worker, 'last_heartbeat', None)

    if hb is None:

        return False

    try:

        now = datetime.now(dt_tz.utc)

        if getattr(hb, 'tzinfo', None) is None:

            hb = hb.replace(tzinfo=dt_tz.utc)

        age = (now - hb.astimezone(dt_tz.utc)).total_seconds()

        return age <= WORKER_HEARTBEAT_MAX_AGE_SEC

    except Exception:

        return False





def rq_workers_available(queue_name: str | None = None) -> bool:

    """当前是否有存活的 RQ Worker 在监听指定队列。"""

    try:

        from rq.worker import Worker



        qname = queue_name or settings.RQ_QUEUE_ROI_HIGH

        q = _queue(qname)

        for worker in Worker.all(connection=q.connection):

            if not _worker_is_alive(worker):

                continue

            names = worker.queue_names() if hasattr(worker, 'queue_names') else []

            if not names and getattr(worker, 'queues', None):

                names = [qn.name for qn in worker.queues]

            if qname in names:

                return True

        return False

    except Exception as exc:

        logger.warning('rq_workers_available failed: %s', exc)

        return False





def should_use_rq_queue(queue_name: str | None = None) -> bool:

    return roi_use_rq() and rq_workers_available(queue_name)





def _append_job_note(job_id: str, line: str, **extra: Any) -> None:

    from django.core.cache import cache



    from .wizard_jobs import WIZARD_JOB_TTL, wizard_job_key



    key = wizard_job_key(job_id)

    ent = cache.get(key) or {}

    prog = list(ent.get('progress') or [])

    if line:

        prog.append(line)

    ent['progress'] = prog

    ent.update(extra)

    cache.set(key, ent, WIZARD_JOB_TTL)





def _set_job_rq_job_id(job_id: str, rq_job_id: str | None) -> None:

    if not rq_job_id:

        return

    _append_job_note(job_id, '', rq_job_id=rq_job_id, exec_mode='rq')





def _cancel_rq_job(rq_job_id: str, queue_name: str | None = None) -> None:

    try:

        from rq.job import Job



        qname = queue_name or settings.RQ_QUEUE_ROI_HIGH

        q = _queue(qname)

        job = Job.fetch(rq_job_id, connection=q.connection)

        status = job.get_status(refresh=True)

        if status in ('queued', 'deferred'):

            job.cancel()

            logger.info('cancelled queued rq job %s', rq_job_id)

    except Exception as exc:

        logger.warning('cancel rq job %s failed: %s', rq_job_id, exc)





def cancel_rq_jobs_for_wizard_job(job_id: str) -> None:

    """解除占用时取消尚未执行的 RQ 任务。"""

    from django.core.cache import cache



    from .wizard_jobs import wizard_job_key



    ent = cache.get(wizard_job_key(job_id)) or {}

    rq_job_id = ent.get('rq_job_id')

    if rq_job_id:

        _cancel_rq_job(rq_job_id)

        return

    inferred = _infer_dispatch_from_rq_queue(job_id)

    if inferred and inferred.get('rq_job_id'):

        _cancel_rq_job(inferred['rq_job_id'])





def _start_wizard_thread(

    job_id: str,

    user_id: int,

    asins: list[str] | None,

    parity: float,

    cost_overrides: dict | None = None,

    target_row_ids: dict[str, int] | None = None,

) -> None:

    from .views import _run_wizard_job



    t = threading.Thread(

        target=_run_wizard_job,

        args=(job_id, user_id, asins, parity),

        kwargs={

            'cost_overrides': cost_overrides,

            'target_row_ids': target_row_ids,

        },

        daemon=True,

    )

    t.start()





def _start_ad_difficulty_thread(

    job_id: str,

    user_id: int,

    asins: list[str],

    target_row_pks: list[int] | None = None,

) -> None:

    from .views import _run_ad_difficulty_job



    t = threading.Thread(

        target=_run_ad_difficulty_job,

        args=(job_id, user_id, asins),

        kwargs={'target_row_pks': target_row_pks},

        daemon=True,

    )

    t.start()





def _enqueue(queue_name: str, func_path: str, *args, **kwargs) -> str | None:

    q = _queue(queue_name)

    job = q.enqueue(

        func_path,

        *args,

        **kwargs,

        job_timeout=_job_timeout(),

        result_ttl=3600,

        failure_ttl=86400,

    )

    return job.id





def _rq_job_still_queued(rq_job_id: str, queue_name: str | None = None) -> bool:

    try:

        from rq.job import Job



        qname = queue_name or settings.RQ_QUEUE_ROI_HIGH

        q = _queue(qname)

        job = Job.fetch(rq_job_id, connection=q.connection)

        return job.get_status(refresh=True) in ('queued', 'deferred')

    except Exception:

        return False





def _infer_dispatch_from_rq_queue(job_id: str) -> dict | None:

    """从 RQ 队列反查已入队但 cache 未存 dispatch 元数据的任务。"""

    try:

        from rq.job import Job



        q = _queue(settings.RQ_QUEUE_ROI_HIGH)

        for rq_id in q.job_ids:

            job = Job.fetch(rq_id, connection=q.connection)

            func = job.func_name or ''

            if not job.args or job.args[0] != job_id:

                continue

            if func.endswith('run_wizard_job_task'):

                return {

                    'task_type': 'wizard',

                    'rq_job_id': rq_id,

                    'user_id': job.args[1],

                    'asins': job.args[2],

                    'parity': job.args[3],

                    'cost_overrides': job.args[4] if len(job.args) > 4 else None,

                    'target_row_ids': job.args[5] if len(job.args) > 5 else None,

                }

            if func.endswith('run_ad_difficulty_job_task'):

                return {

                    'task_type': 'ad_difficulty',

                    'rq_job_id': rq_id,

                    'user_id': job.args[1],

                    'asins': job.args[2],

                    'target_row_pks': job.args[3] if len(job.args) > 3 else None,

                }

    except Exception as exc:

        logger.warning('infer dispatch from rq failed: %s', exc)

    return None





def maybe_rescue_stuck_queued_job(job_id: str) -> None:

    """

    任务长期 queued 时，取消 RQ 队列中的任务并改为 Web 后台线程执行。

    """

    from django.core.cache import cache



    from .wizard_jobs import WIZARD_JOB_TTL, _queued_wait_seconds, wizard_job_key



    key = wizard_job_key(job_id)

    ent = cache.get(key)

    if not ent or ent.get('status') != 'queued':

        return

    if ent.get('thread_dispatched') or ent.get('rescue_dispatched'):

        return



    wait = _queued_wait_seconds(ent)

    if wait is None or wait < RESCUE_QUEUED_AFTER_SEC:

        return



    task_type = ent.get('task_type')

    if not task_type:

        inferred = _infer_dispatch_from_rq_queue(job_id)

        if inferred:

            ent.update(inferred)

            task_type = ent.get('task_type')

            cache.set(key, ent, WIZARD_JOB_TTL)



    rq_job_id = ent.get('rq_job_id')

    if rq_job_id and not _rq_job_still_queued(rq_job_id):

        return



    if task_type not in ('wizard', 'ad_difficulty'):

        return



    ent['rescue_dispatched'] = True

    ent['thread_dispatched'] = True

    ent['exec_mode'] = 'thread'

    prog = list(ent.get('progress') or [])

    prog.append('任务长时间未执行，已切换为 Web 后台线程…')

    ent['progress'] = prog

    cache.set(key, ent, WIZARD_JOB_TTL)



    if rq_job_id:

        _cancel_rq_job(rq_job_id)



    user_id = int(ent['user_id'])

    asins = ent.get('asins')



    if task_type == 'wizard':

        _start_wizard_thread(

            job_id,

            user_id,

            asins,

            float(ent['parity']),

            cost_overrides=ent.get('cost_overrides'),

            target_row_ids=ent.get('target_row_ids'),

        )

    else:

        _start_ad_difficulty_thread(

            job_id,

            user_id,

            list(asins or []),

            target_row_pks=ent.get('target_row_pks'),

        )

    logger.warning('rescued stuck queued job %s -> thread (%s)', job_id, task_type)





def dispatch_wizard_job(

    job_id: str,

    user_id: int,

    asins: list[str] | None,

    parity: float,

    cost_overrides: dict | None = None,

    target_row_ids: dict[str, int] | None = None,

) -> str | None:

    """入队 ROI 任务；无 Worker 或 ROI_USE_RQ=false 时在 Web 进程后台线程执行。"""
    from .roi_routing import wizard_queue_name, wizard_route_label

    queue_name = wizard_queue_name(asins)

    if not should_use_rq_queue(queue_name):

        _append_job_note(

            job_id,

            '已在 Web 后台线程执行（本地无需单独启动 Worker）。',

            exec_mode='thread',

            thread_dispatched=True,

        )

        _start_wizard_thread(

            job_id,

            user_id,

            asins,

            parity,

            cost_overrides=cost_overrides,

            target_row_ids=target_row_ids,

        )

        return None



    rq_job_id = _enqueue(

        queue_name,

        'auto_amazon.rq_tasks.run_wizard_job_task',

        job_id,

        user_id,

        asins,

        parity,

        cost_overrides,

        target_row_ids,

    )

    _set_job_rq_job_id(job_id, rq_job_id)

    _append_job_note(job_id, f'已加入 Worker 队列（{wizard_route_label(asins)}），等待执行…')

    logger.info('enqueued wizard job %s -> %s rq:%s', job_id, queue_name, rq_job_id)

    return rq_job_id





def dispatch_ad_difficulty_job(

    job_id: str,

    user_id: int,

    asins: list[str],

    target_row_pks: list[int] | None = None,

) -> str | None:

    if not should_use_rq_queue(settings.RQ_QUEUE_ROI_HIGH):

        _append_job_note(

            job_id,

            '已在 Web 后台线程执行（本地无需单独启动 Worker）。',

            exec_mode='thread',

            thread_dispatched=True,

        )

        _start_ad_difficulty_thread(job_id, user_id, asins, target_row_pks=target_row_pks)

        return None



    rq_job_id = _enqueue(

        settings.RQ_QUEUE_ROI_HIGH,

        'auto_amazon.rq_tasks.run_ad_difficulty_job_task',

        job_id,

        user_id,

        asins,

        target_row_pks,

    )

    _set_job_rq_job_id(job_id, rq_job_id)

    _append_job_note(job_id, '已加入 Worker 队列，等待执行…')

    logger.info('enqueued ad difficulty job %s -> rq:%s', job_id, rq_job_id)

    return rq_job_id





def dispatch_scheduled_asin(

    *,

    row_pk: int,

    asin: str,

    lock_owner: str,

    job_log_id: int,

    ad_due: bool,

    roi_due: bool,

    recipient_id: int | None,

) -> str | None:

    if not should_use_rq_queue(settings.RQ_QUEUE_ROI_SCHEDULED):

        from .asin_job_lock import release

        from .scheduled_jobs import execute_scheduled_asin_worker



        try:

            execute_scheduled_asin_worker(

                row_pk=row_pk,

                job_log_id=job_log_id,

                ad_due=ad_due,

                roi_due=roi_due,

                recipient_id=recipient_id,

            )

        finally:

            release(asin, lock_owner)

        return None



    rq_job_id = _enqueue(

        settings.RQ_QUEUE_ROI_SCHEDULED,

        'auto_amazon.rq_tasks.run_scheduled_asin_task',

        row_pk,

        asin,

        lock_owner,

        job_log_id,

        ad_due,

        roi_due,

        recipient_id,

    )

    logger.info('enqueued scheduled asin %s row_pk=%s -> rq:%s', asin, row_pk, rq_job_id)

    return rq_job_id


def dispatch_scheduled_batch(work_items: list[dict]) -> str | None:
    """将一批到期 ASIN 合并为单个 RQ 任务（批量并发计算）。"""
    if not work_items:
        return None

    if not should_use_rq_queue(settings.RQ_QUEUE_ROI_SCHEDULED):
        from .asin_job_lock import release
        from .scheduled_jobs import execute_scheduled_batch_worker

        try:
            execute_scheduled_batch_worker(work_items)
        finally:
            for w in work_items:
                release(w['asin'], w['lock_owner'])
        return None

    rq_job_id = _enqueue(
        settings.RQ_QUEUE_ROI_SCHEDULED,
        'auto_amazon.rq_tasks.run_scheduled_batch_task',
        work_items,
    )
    asins = [w.get('asin') for w in work_items]
    logger.info('enqueued scheduled batch %s -> rq:%s', asins, rq_job_id)
    return rq_job_id

