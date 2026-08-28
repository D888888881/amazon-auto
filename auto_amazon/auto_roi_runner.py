"""自动 ROI 稳态串行执行引擎。"""
from __future__ import annotations

import logging
import os
import random
import time
import traceback

from django.db import close_old_connections, transaction
from django.utils import timezone

from .asin_product_image import asin_has_local_image
from .asin_wizard import run_seller_wizard
from .marketplace import MARKETPLACE_US, normalize_marketplace
from .models import RoiAutoRun, RoiAutoRunLog
from .roi_routing import ad_difficulty_credential_profile_context
from .roi_site_defaults import ensure_site_config, roi_defaults_dict
from .seller_unlock import is_seller_account_banned_error, unlock_seller_sub_account

logger = logging.getLogger(__name__)

_MAX_IMAGE_RETRIES = max(1, int(os.environ.get('AUTO_ROI_IMAGE_MAX_RETRIES', '3')))


def _now():
    return timezone.now()


def _seller_username() -> str:
    try:
        import sys
        from pathlib import Path

        from django.conf import settings

        script = str(Path(settings.BASE_DIR) / 'scripts' / 'asin_find_project')
        if script not in sys.path:
            sys.path.insert(0, script)
        from seller_account_guard import resolve_seller_username

        return str(resolve_seller_username() or '')
    except Exception:
        return ''


def _rotate_bulk_account(pending_asins: list[str], banned_username: str | None = None) -> tuple[bool, str]:
    try:
        import sys
        from pathlib import Path

        from django.conf import settings

        script = str(Path(settings.BASE_DIR) / 'scripts' / 'asin_find_project')
        if script not in sys.path:
            sys.path.insert(0, script)
        from bulk_account_pool import rotate_bulk_account_after_ban

        ok, msg, _cfg = rotate_bulk_account_after_ban(
            banned_username,
            pending_asins=pending_asins,
            pending_task='roi',
        )
        return bool(ok), str(msg or '')
    except Exception as exc:
        return False, f'{type(exc).__name__}: {exc}'


def _clear_seller_session() -> None:
    try:
        import sys
        from pathlib import Path

        from django.conf import settings

        script = str(Path(settings.BASE_DIR) / 'scripts' / 'asin_find_project')
        if script not in sys.path:
            sys.path.insert(0, script)
        from seller_account_guard import clear_seller_login_cache

        clear_seller_login_cache()
    except Exception:
        pass


def _is_transient_seller_error(exc: BaseException) -> bool:
    try:
        import sys
        from pathlib import Path

        from django.conf import settings

        script = str(Path(settings.BASE_DIR) / 'scripts' / 'asin_find_project')
        if script not in sys.path:
            sys.path.insert(0, script)
        from seller_account_guard import SellerSpriteTransientError

        return isinstance(exc, SellerSpriteTransientError)
    except Exception:
        return 'SellerSpriteTransientError' in type(exc).__name__


def _extract_image_meta(part: dict | None, asin: str) -> dict:
    if not isinstance(part, dict):
        return {}
    meta_all = part.get('__image_meta__') or {}
    if not isinstance(meta_all, dict):
        return {}
    key = str(asin).strip().upper()
    row = meta_all.get(key) or meta_all.get(asin) or {}
    return row if isinstance(row, dict) else {}


def _image_miss_summary(meta: dict) -> str:
    parts = [
        f"ad_data={'是' if meta.get('ad_data') else '否'}",
        f"source={meta.get('image_source') or 'none'}",
    ]
    url = str(meta.get('image_url') or '').strip()
    if url:
        parts.append(f'url={url[:120]}')
    return '主图缺失（' + '，'.join(parts) + '）'


def _write_log(
    run: RoiAutoRun,
    *,
    asin: str,
    status: str,
    attempt: int = 1,
    duration_ms: int | None = None,
    error_summary: str = '',
    error_detail: str = '',
    account_username: str = '',
) -> None:
    seq = (run.succeeded or 0) + (run.failed or 0) + 1
    RoiAutoRunLog.objects.create(
        run=run,
        asin=asin,
        seq=seq,
        status=status,
        attempt=attempt,
        account_username=account_username or run.last_account or '',
        duration_ms=duration_ms,
        error_summary=(error_summary or '')[:500],
        error_detail=(error_detail or '')[-8000:],
    )


def _refresh(run_id: int) -> RoiAutoRun:
    close_old_connections()
    return RoiAutoRun.objects.get(pk=run_id)


def _interruptible_sleep(run_id: int, seconds: float) -> str:
    """分段睡眠；返回当前 status（running/paused/stopped/...）。"""
    end = time.monotonic() + max(0.0, float(seconds))
    while True:
        run = _refresh(run_id)
        if run.status != RoiAutoRun.Status.RUNNING:
            return run.status
        left = end - time.monotonic()
        if left <= 0:
            return run.status
        time.sleep(min(0.5, left))


def _pending_queue(run: RoiAutoRun) -> list[str]:
    from .views import _compute_allowed_asins_for_user, _discover_local_asins

    pending, _skipped = _discover_local_asins(force_recompute=False, marketplace=run.marketplace)
    allowed = _compute_allowed_asins_for_user(run.user, marketplace=run.marketplace)
    done = {str(a).strip().upper() for a in (run.done_asins or []) if str(a).strip()}
    out = []
    for a in pending:
        a = str(a).strip().upper()
        if not a or a in done:
            continue
        if allowed is not None and a not in allowed:
            continue
        out.append(a)
    return out


def _persist_one(user_id: int, asin: str, part: dict, parity: float, marketplace: str) -> None:
    from .views import _persist_wizard_results

    if not isinstance(part, dict):
        return
    _persist_wizard_results(user_id, part, parity, marketplace=marketplace)


def run_auto_roi(run_id: int) -> None:
    """RQ / 线程入口：单线程稳态跑完或直到暂停/停止。"""
    close_old_connections()
    run = _refresh(run_id)
    if run.status != RoiAutoRun.Status.RUNNING:
        return

    mp = normalize_marketplace(run.marketplace) or MARKETPLACE_US
    cfg = ensure_site_config(mp)
    defaults = roi_defaults_dict(mp)
    parity = float(run.parity or 7.2)

    with ad_difficulty_credential_profile_context():
        try:
            _auto_roi_loop(run_id, mp=mp, cfg=cfg, defaults=defaults, parity=parity)
        except Exception as exc:
            logger.exception('auto roi run %s crashed', run_id)
            close_old_connections()
            RoiAutoRun.objects.filter(pk=run_id).update(
                status=RoiAutoRun.Status.ERROR,
                error_message=f'{type(exc).__name__}: {exc}',
                finished_at=_now(),
                current_asin='',
            )


def _auto_roi_loop(run_id: int, *, mp: str, cfg, defaults: dict, parity: float) -> None:
    from .credentials_config import assert_sif_authorization_usable
    from .views import _merge_cost_overrides_from_db

    os.environ.setdefault('ROI_AD_REQUEST_DELAY_SEC', '1')

    try:
        assert_sif_authorization_usable(for_auto_roi=True)
    except ValueError as exc:
        RoiAutoRun.objects.filter(pk=run_id).update(
            status=RoiAutoRun.Status.ERROR,
            error_message=str(exc),
            finished_at=_now(),
            current_asin='',
        )
        return

    while True:
        run = _refresh(run_id)
        if run.status != RoiAutoRun.Status.RUNNING:
            return

        try:
            assert_sif_authorization_usable(for_auto_roi=True)
        except ValueError as exc:
            RoiAutoRun.objects.filter(pk=run_id).update(
                status=RoiAutoRun.Status.ERROR,
                error_message=str(exc),
                finished_at=_now(),
                current_asin='',
            )
            return

        cfg = ensure_site_config(mp)
        defaults = roi_defaults_dict(mp)
        queue = _pending_queue(run)
        if not queue:
            RoiAutoRun.objects.filter(pk=run_id).update(
                status=RoiAutoRun.Status.DONE,
                finished_at=_now(),
                current_asin='',
                total=run.succeeded + run.failed,
            )
            return

        batch_size = max(1, int(cfg.batch_size or 20))
        batch = queue[:batch_size]
        RoiAutoRun.objects.filter(pk=run_id).update(total=len(queue) + len(run.done_asins or []))

        for i, asin in enumerate(batch):
            run = _refresh(run_id)
            if run.status != RoiAutoRun.Status.RUNNING:
                return

            account = _seller_username()
            RoiAutoRun.objects.filter(pk=run_id).update(
                current_asin=asin,
                last_account=account or run.last_account,
            )

            ok = _process_one_asin(
                run_id,
                asin=asin,
                parity=parity,
                marketplace=mp,
                defaults=defaults,
                cfg=cfg,
                merge_cost=_merge_cost_overrides_from_db,
            )
            if not ok:
                # paused / stopped / error inside
                run = _refresh(run_id)
                if run.status != RoiAutoRun.Status.RUNNING:
                    return

            run = _refresh(run_id)
            if run.status != RoiAutoRun.Status.RUNNING:
                return

            # ASIN 间隔（最后一个 ASIN 仍 sleep，批间再另 sleep）
            dmin = float(cfg.asin_delay_min_sec or 1)
            dmax = float(cfg.asin_delay_max_sec or 3)
            if dmax < dmin:
                dmin, dmax = dmax, dmin
            st = _interruptible_sleep(run_id, random.uniform(dmin, dmax))
            if st != RoiAutoRun.Status.RUNNING:
                return

        # 批间等待
        run = _refresh(run_id)
        if run.status != RoiAutoRun.Status.RUNNING:
            return
        bmin = float(cfg.batch_delay_min_sec or 4)
        bmax = float(cfg.batch_delay_max_sec or 8)
        if bmax < bmin:
            bmin, bmax = bmax, bmin
        st = _interruptible_sleep(run_id, random.uniform(bmin, bmax))
        if st != RoiAutoRun.Status.RUNNING:
            return


def _process_one_asin(
    run_id: int,
    *,
    asin: str,
    parity: float,
    marketplace: str,
    defaults: dict,
    cfg,
    merge_cost,
) -> bool:
    """返回 False 表示 Run 已非 running（暂停/停止/出错）。"""
    max_ban = max(1, int(cfg.max_ban_retries_per_asin or 3))
    attempt = 0
    ban_attempts = 0
    image_miss = 0

    while True:
        attempt += 1
        run = _refresh(run_id)
        if run.status != RoiAutoRun.Status.RUNNING:
            return False

        account = _seller_username()
        t0 = time.monotonic()
        try:
            cost_overrides = merge_cost([asin], None)
            co = {asin: cost_overrides[asin]} if cost_overrides and asin in cost_overrides else None
            part = run_seller_wizard(
                [asin],
                parity,
                cost_overrides=co,
                marketplace=marketplace,
                roi_defaults=defaults,
            )
            duration_ms = int((time.monotonic() - t0) * 1000)
            img_meta = _extract_image_meta(part if isinstance(part, dict) else {}, asin)
            if not asin_has_local_image(asin):
                image_miss += 1
                miss_summary = _image_miss_summary(img_meta)
                _clear_seller_session()
                if image_miss >= 2:
                    unlock_seller_sub_account()
                    _rotate_bulk_account([asin], banned_username=account or None)
                if image_miss >= _MAX_IMAGE_RETRIES:
                    raise RuntimeError(
                        f'{miss_summary}；已重试 {_MAX_IMAGE_RETRIES} 次仍无本地主图'
                    )
                with transaction.atomic():
                    run = RoiAutoRun.objects.select_for_update().get(pk=run_id)
                    run.consecutive_fails = int(run.consecutive_fails or 0) + 1
                    run.last_account = account or run.last_account
                    run.current_asin = asin
                    pause_now = run.consecutive_fails >= int(cfg.consecutive_fail_pause or 10)
                    if pause_now:
                        run.status = RoiAutoRun.Status.PAUSED
                        run.error_message = (
                            f'连续 {run.consecutive_fails} 次主图/接口异常，已自动暂停。'
                        )
                    run.save(
                        update_fields=[
                            'consecutive_fails',
                            'last_account',
                            'current_asin',
                            'status',
                            'error_message',
                            'updated_at',
                        ]
                    )
                _write_log(
                    run,
                    asin=asin,
                    status=RoiAutoRunLog.Status.RETRY,
                    attempt=attempt,
                    duration_ms=duration_ms,
                    error_summary=f'{miss_summary}；刷新会话后重试（{image_miss}/{_MAX_IMAGE_RETRIES}）',
                    account_username=account,
                )
                run = _refresh(run_id)
                if run.status != RoiAutoRun.Status.RUNNING:
                    return False
                time.sleep(min(3.0, 1.0 + image_miss * 0.5))
                continue

            _persist_one(run.user_id, asin, part if isinstance(part, dict) else {}, parity, marketplace)

            ok_note = ''
            src = str(img_meta.get('image_source') or '').strip()
            if src and src not in ('none', 'ad_api', 'local_existing'):
                ok_note = f'主图来源: {src}'

            with transaction.atomic():
                run = RoiAutoRun.objects.select_for_update().get(pk=run_id)
                done = list(run.done_asins or [])
                if asin not in done:
                    done.append(asin)
                run.done_asins = done
                run.succeeded = int(run.succeeded or 0) + 1
                run.consecutive_fails = 0
                run.last_account = account or run.last_account
                run.current_asin = ''
                run.save(
                    update_fields=[
                        'done_asins',
                        'succeeded',
                        'consecutive_fails',
                        'last_account',
                        'current_asin',
                        'updated_at',
                    ]
                )
            _write_log(
                run,
                asin=asin,
                status=RoiAutoRunLog.Status.SUCCESS,
                attempt=attempt,
                duration_ms=duration_ms,
                error_summary=ok_note,
                account_username=account,
            )
            return True
        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            detail = traceback.format_exc()
            summary = f'{type(exc).__name__}: {exc}'

            if _is_transient_seller_error(exc):
                _clear_seller_session()
                run = _refresh(run_id)
                _write_log(
                    run,
                    asin=asin,
                    status=RoiAutoRunLog.Status.RETRY,
                    attempt=attempt,
                    duration_ms=duration_ms,
                    error_summary=f'卖家精灵限流/会话异常：{summary}'[:500],
                    error_detail=detail,
                    account_username=account,
                )
                time.sleep(2.5)
                continue

            if is_seller_account_banned_error(exc):
                ban_attempts += 1
                run = _refresh(run_id)
                if ban_attempts > max_ban or int(run.ban_rotations or 0) >= int(
                    cfg.max_ban_rotations_per_run or 30
                ):
                    _write_log(
                        run,
                        asin=asin,
                        status=RoiAutoRunLog.Status.FAILED,
                        attempt=attempt,
                        duration_ms=duration_ms,
                        error_summary='禁号换号次数超限：' + summary[:400],
                        error_detail=detail,
                        account_username=account,
                    )
                    RoiAutoRun.objects.filter(pk=run_id).update(
                        status=RoiAutoRun.Status.PAUSED,
                        error_message='禁号换号次数超限，已自动暂停。请检查账号池后继续。',
                        current_asin=asin,
                    )
                    return False

                unlock_seller_sub_account()
                ok_rot, rot_msg = _rotate_bulk_account([asin], banned_username=account or None)
                new_account = _seller_username()
                with transaction.atomic():
                    run = RoiAutoRun.objects.select_for_update().get(pk=run_id)
                    run.ban_rotations = int(run.ban_rotations or 0) + 1
                    run.last_account = new_account or run.last_account
                    run.save(update_fields=['ban_rotations', 'last_account', 'updated_at'])
                _write_log(
                    run,
                    asin=asin,
                    status=RoiAutoRunLog.Status.BANNED_ROTATED,
                    attempt=attempt,
                    duration_ms=duration_ms,
                    error_summary=f'禁号已解禁{"并换号" if ok_rot else ""}：{rot_msg or summary}'[:500],
                    error_detail=detail,
                    account_username=account,
                )
                _write_log(
                    run,
                    asin=asin,
                    status=RoiAutoRunLog.Status.RETRY,
                    attempt=attempt + 1,
                    error_summary='换号后重试同一 ASIN',
                    account_username=new_account or account,
                )
                continue

            # 普通失败：记失败，继续下一个
            with transaction.atomic():
                run = RoiAutoRun.objects.select_for_update().get(pk=run_id)
                done = list(run.done_asins or [])
                if asin not in done:
                    done.append(asin)
                run.done_asins = done
                run.failed = int(run.failed or 0) + 1
                run.consecutive_fails = int(run.consecutive_fails or 0) + 1
                run.last_account = account or run.last_account
                run.current_asin = ''
                pause_now = run.consecutive_fails >= int(cfg.consecutive_fail_pause or 10)
                if pause_now:
                    run.status = RoiAutoRun.Status.PAUSED
                    run.error_message = f'连续失败 {run.consecutive_fails} 次，已自动暂停。'
                run.save(
                    update_fields=[
                        'done_asins',
                        'failed',
                        'consecutive_fails',
                        'last_account',
                        'current_asin',
                        'status',
                        'error_message',
                        'updated_at',
                    ]
                )
            _write_log(
                run,
                asin=asin,
                status=RoiAutoRunLog.Status.FAILED,
                attempt=attempt,
                duration_ms=duration_ms,
                error_summary=summary,
                error_detail=detail,
                account_username=account,
            )
            return run.status == RoiAutoRun.Status.RUNNING
