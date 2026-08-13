"""从 data_origin 生成站点运营难度表，并回写看板 ops 字段。"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

import pandas as pd
from django.contrib.auth import get_user_model
from django.db import close_old_connections

from .asin_access import asin_importer_user_ids, normalize_asin, user_is_assigned_to_asin
from .marketplace import MARKETPLACE_UK, MARKETPLACE_US, normalize_marketplace
from .media_paths import media_root
from .models import AsinDashboardRow
from .ops_metrics import scan_ops_fields_from_media
from .wizard_runtime import asin_script_cwd

logger = logging.getLogger(__name__)
User = get_user_model()


def _find_data_origin(kw_dir: Path) -> Path | None:
    cands = sorted(kw_dir.glob('*_data_origin.xlsx'))
    return cands[0] if cands else None


def iter_asin_keyword_origins(asin: str) -> list[tuple[str, Path]]:
    root = media_root() / normalize_asin(asin)
    if not root.is_dir():
        return []
    out: list[tuple[str, Path]] = []
    for kw_dir in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not kw_dir.is_dir():
            continue
        origin = _find_data_origin(kw_dir)
        if origin is None:
            continue
        out.append((kw_dir.name, origin))
    return out


async def _save_review_for_keyword(
    df: pd.DataFrame,
    keyword: str,
    asin: str,
    marketplace: str,
) -> dict | None:
    from async_seller_wizard_api import save_review_interval_analysis_to_excel

    if df is None or df.empty:
        return None
    return await save_review_interval_analysis_to_excel(
        df, keyword, asin, marketplace=marketplace
    )


def generate_ops_tables_for_asin(
    asin: str,
    marketplace: str,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> int:
    """
    读取各关键词 data_origin，按站点 bins 写出 review_interval_analysis_{US|UK}.xlsx。
    返回成功写出的关键词数量。
    """
    a = normalize_asin(asin)
    mp = normalize_marketplace(marketplace) or MARKETPLACE_US
    pairs = iter_asin_keyword_origins(a)
    if not pairs:
        if on_progress:
            on_progress(f'{a}: 未找到 data_origin，跳过')
        return 0

    written = 0
    with asin_script_cwd():

        async def _run_all() -> int:
            n = 0
            for keyword, origin in pairs:
                try:
                    df = pd.read_excel(origin, engine='openpyxl')
                except Exception as e:
                    logger.warning('read data_origin failed %s: %s', origin, e)
                    if on_progress:
                        on_progress(f'{a}/{keyword}: 读取 data_origin 失败')
                    continue
                try:
                    result = await _save_review_for_keyword(df, keyword, a, mp)
                except Exception as e:
                    logger.exception('save review interval failed asin=%s kw=%s', a, keyword)
                    if on_progress:
                        on_progress(f'{a}/{keyword}: 生成运营难度失败 — {e}')
                    continue
                if result:
                    n += 1
                    if on_progress:
                        on_progress(f'{a}/{keyword}: 已写入 {mp} 运营难度表')
            return n

        written = asyncio.run(_run_all())
    return written


def resolve_ops_row_owner_id(user: User, asin: str) -> int:
    a = normalize_asin(asin)
    if user_is_assigned_to_asin(user, a):
        importer_ids = asin_importer_user_ids(a)
        if importer_ids:
            return int(importer_ids[0])
    return int(user.id)


def upsert_ops_dashboard_row(
    user: User,
    asin: str,
    marketplace: str,
) -> bool:
    """
    从 media 扫描运营难度并 get_or_create 看板行。
    UK 行仅写 ops 字段；其它指标保持空/原值。
    """
    a = normalize_asin(asin)
    mp = normalize_marketplace(marketplace) or MARKETPLACE_UK
    o1, o2, o3 = scan_ops_fields_from_media(a, marketplace=mp)
    if not (o1 or o2 or o3):
        return False
    owner_id = resolve_ops_row_owner_id(user, a)
    row, created = AsinDashboardRow.objects.get_or_create(
        user_id=owner_id,
        asin=a,
        marketplace=mp,
        defaults={
            'product_grade': '',
            'ops_difficulty_1': o1 or '',
            'ops_difficulty_2': o2 or '',
            'ops_difficulty_3': o3 or '',
        },
    )
    if not created:
        AsinDashboardRow.objects.filter(pk=row.pk).update(
            ops_difficulty_1=o1 or '',
            ops_difficulty_2=o2 or '',
            ops_difficulty_3=o3 or '',
        )
    return True


def compute_ops_difficulty_for_asins(
    user_id: int,
    asins: list[str],
    marketplace: str,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[list[str], list[dict]]:
    """
    批量计算运营难度。
    返回 (成功 ASIN 列表, 失败 [{asin, error}] )。
    """
    mp = normalize_marketplace(marketplace) or MARKETPLACE_UK
    close_old_connections()
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        return [], [{'asin': '', 'error': f'用户不存在: {user_id}'}]

    succeeded: list[str] = []
    failures: list[dict] = []
    for raw in asins:
        a = normalize_asin(raw)
        if not a:
            continue
        close_old_connections()
        try:
            n = generate_ops_tables_for_asin(a, mp, on_progress=on_progress)
            if n <= 0:
                failures.append({'asin': a, 'error': '无可用 data_origin 或生成失败'})
                continue
            ok = upsert_ops_dashboard_row(user, a, mp)
            if not ok:
                failures.append({'asin': a, 'error': '已生成文件但未能回写看板'})
                continue
            succeeded.append(a)
            if on_progress:
                on_progress(f'{a}: 看板运营难度已更新（{mp}）')
        except Exception as e:
            logger.exception('ops difficulty failed asin=%s', a)
            failures.append({'asin': a, 'error': str(e)[:400]})
    return succeeded, failures
