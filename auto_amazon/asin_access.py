"""ASIN 媒体路径与文件夹分配相关的权限与解析。"""
from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from django.core.cache import cache

if TYPE_CHECKING:
    from django.contrib.auth.models import User

_ASIN_DIR = re.compile(r'^B0[A-Z0-9]{8}$', re.IGNORECASE)

# 站点 ASIN 根集合缓存（导入/删除时与 excel 浏览索引一并 bust）
_MP_ASIN_CACHE_TTL = 300
_MP_ASIN_VER_KEY = 'mp_asin:ver'


def bust_marketplace_asin_cache() -> None:
    """导入/删除后使站点 ASIN 集合缓存失效。"""
    cache.set(_MP_ASIN_VER_KEY, str(time.time()), _MP_ASIN_CACHE_TTL * 4)


def _mp_asin_cache_ver() -> str:
    ver = cache.get(_MP_ASIN_VER_KEY)
    if ver is None:
        ver = '0'
        cache.set(_MP_ASIN_VER_KEY, ver, _MP_ASIN_CACHE_TTL * 4)
    return str(ver)


def normalize_asin(s: str | None) -> str:
    return (s or '').strip().upper()


def asin_root_from_rel_path(rel: str | None) -> str | None:
    """取相对路径第一段，若为 ASIN 目录名则返回大写 ASIN。"""
    if not rel or not str(rel).strip():
        return None
    first = str(rel).strip().replace('\\', '/').split('/')[0].strip()
    if not first:
        return None
    up = first.upper()
    return up if _ASIN_DIR.match(up) else None


def user_assigned_asin_codes(user: User) -> list[str]:
    from .models import AsinFolderAssignment

    if not getattr(user, 'is_authenticated', False):
        return []
    uid = getattr(user, 'id', None)
    if uid is None:
        return []
    ver = _mp_asin_cache_ver()
    key = f'mp_asin:assigned:{ver}:{uid}'
    hit = cache.get(key)
    if hit is not None:
        return list(hit)
    codes = list(
        AsinFolderAssignment.objects.filter(assignees=user).values_list('asin', flat=True)
    )
    cache.set(key, codes, _MP_ASIN_CACHE_TTL)
    return codes


def user_is_assigned_to_asin(user: User, asin: str | None) -> bool:
    a = normalize_asin(asin)
    if not a:
        return False
    return a in {normalize_asin(x) for x in user_assigned_asin_codes(user)}


def user_can_access_excel_media_path(user: User, rel_path: str) -> bool:
    """非超管：可访问已分配给自己的 ASIN 目录，或本人曾导入过的 ASIN 目录下路径。"""
    if getattr(user, 'is_superuser', False):
        return True
    root = asin_root_from_rel_path(rel_path)
    if not root:
        return False
    if user_is_assigned_to_asin(user, root):
        return True
    if root in user_imported_asin_codes(user):
        return True
    from .models import AsinDashboardRow

    if AsinDashboardRow.objects.filter(user=user, asin=root).exists():
        return True
    from .models import ImportedMediaPath

    if ImportedMediaPath.objects.filter(user=user, rel_path__startswith=f'{root}/').exists():
        return True
    return ImportedMediaPath.objects.filter(user=user, rel_path=root).exists()


def user_can_access_asin_root(
    user: User,
    asin: str | None,
    *,
    assigned_set: set[str] | None = None,
    import_roots: set[str] | None = None,
) -> bool:
    """批量场景下按 ASIN 根判定权限（避免子目录逐文件查库）。"""
    if getattr(user, 'is_superuser', False):
        return True
    a = normalize_asin(asin)
    if not a:
        return False
    assigned = assigned_set if assigned_set is not None else {
        normalize_asin(x) for x in user_assigned_asin_codes(user)
    }
    if a in assigned:
        return True
    imported = import_roots if import_roots is not None else user_imported_asin_codes(user)
    return a in imported


def user_dashboard_rows_qs(user: User, *, marketplace: str | None = None):
    """首页看板可见行：超管全部；否则本人 + 被分配 + 本人导入的 ASIN。

    指定站点时：只显示该站看板行，且 ASIN 必须在该站有过导入记录
    （避免英国站误显示旧运营难度占位行等孤儿数据）。
    """
    from django.db.models import Q

    from .marketplace import normalize_marketplace
    from .models import AsinDashboardRow

    if not getattr(user, 'is_authenticated', False):
        return AsinDashboardRow.objects.none()
    mp = normalize_marketplace(marketplace)
    if getattr(user, 'is_superuser', False):
        qs = AsinDashboardRow.objects.all()
    else:
        assigned = user_assigned_asin_codes(user)
        imported = user_imported_asin_codes(user, marketplace=mp)
        qs = AsinDashboardRow.objects.filter(
            Q(user=user) | Q(asin__in=assigned) | Q(asin__in=imported)
        ).distinct()
    if mp:
        qs = qs.filter(marketplace=mp)
        site_asins = asins_for_marketplace(mp)
        if not site_asins:
            return AsinDashboardRow.objects.none()
        qs = qs.filter(asin__in=site_asins)
    return qs


def user_can_operate_dashboard_row(user: User, row) -> bool:
    """可勾选、计算 ROI/广告难度、导出、编辑采购价等（不含删除）。"""
    if getattr(user, 'is_superuser', False):
        return True
    if row.user_id == user.id:
        return True
    return user_is_assigned_to_asin(user, row.asin)


def user_can_delete_dashboard_row(user: User, row) -> bool:
    """看板行删除：超管、数据归属者或被分配用户。"""
    if getattr(user, 'is_superuser', False):
        return True
    if row.user_id == user.id:
        return True
    return user_is_assigned_to_asin(user, row.asin)


def user_can_delete_asin_media_folder(user: User, asin: str | None) -> bool:
    """是否可删除 media/file/<ASIN> 整目录。"""
    if getattr(user, 'is_superuser', False):
        return True
    a = normalize_asin(asin)
    if not a:
        return False
    if user_is_assigned_to_asin(user, a):
        return True
    from .models import ImportedMediaPath

    return ImportedMediaPath.objects.filter(user=user, rel_path=a).exists()


def user_can_delete_excel_media_path(user: User, rel_path: str) -> bool:
    """数据审核页删除：超管、被分配 ASIN 下任意路径，或本人导入的路径。"""
    if getattr(user, 'is_superuser', False):
        return True
    if not user_can_access_excel_media_path(user, rel_path):
        return False
    root = asin_root_from_rel_path(rel_path)
    if root and user_is_assigned_to_asin(user, root):
        return True
    from .models import ImportedMediaPath

    return ImportedMediaPath.objects.filter(user=user, rel_path=rel_path).exists()


def uploader_label_map(asins: set[str]) -> dict[str, str]:
    """批量解析 ASIN 上传者显示名（与定时消息收件人规则一致）。"""
    if not asins:
        return {}
    from .models import AsinCatalogItem, ImportedMediaPath

    norm = {normalize_asin(a) for a in asins if normalize_asin(a)}
    out: dict[str, str] = {}
    for a, uname in (
        AsinCatalogItem.objects.filter(asin__in=norm)
        .select_related('uploaded_by')
        .values_list('asin', 'uploaded_by__username')
    ):
        key = normalize_asin(a)
        if uname and key not in out:
            out[key] = uname
    missing = norm - set(out.keys())
    if missing:
        for rp, uname in (
            ImportedMediaPath.objects.filter(rel_path__in=missing)
            .select_related('user')
            .values_list('rel_path', 'user__username')
        ):
            key = normalize_asin(rp)
            if uname and key not in out:
                out[key] = uname
    still = norm - set(out.keys())
    if still:
        from .models import AsinDashboardRow

        for a, uname in (
            AsinDashboardRow.objects.filter(asin__in=still)
            .select_related('user')
            .order_by('-created_at')
            .values_list('asin', 'user__username')
        ):
            key = normalize_asin(a)
            if uname and key not in out:
                out[key] = uname
    return out


def resolve_dashboard_row_for_persist(
    user: User,
    asin: str,
    target_row_ids: dict[str, int] | None = None,
    *,
    marketplace: str | None = None,
):
    """ROI 结果写入时定位看板行：勾选行 > 上传者行 > 其他共享行 > 本人行（默认美国站）。"""
    from .marketplace import MARKETPLACE_US, normalize_marketplace
    from .models import AsinDashboardRow

    a = normalize_asin(asin)
    if not a or not getattr(user, 'is_authenticated', False):
        return None
    mp = normalize_marketplace(marketplace) or MARKETPLACE_US
    id_map = {normalize_asin(k): v for k, v in (target_row_ids or {}).items()}
    row_pk = id_map.get(a)
    if row_pk:
        row = AsinDashboardRow.objects.filter(pk=row_pk).first()
        if row:
            return row
    base = AsinDashboardRow.objects.filter(asin=a, marketplace=mp)
    if user_is_assigned_to_asin(user, a):
        importer_ids = asin_importer_user_ids(a, marketplace=mp)
        if importer_ids:
            upl = base.filter(user_id__in=importer_ids).order_by('-created_at').first()
            if upl:
                return upl
        shared = base.exclude(user_id=user.id).order_by('-created_at').first()
        if shared:
            return shared
    return base.filter(user_id=user.id).first()


def pick_preferred_dashboard_row(row_a, row_b, viewer_id: int, assigned_asins: set[str]):
    """同一 ASIN 多行时：优先有 ROI 数据的行，再按分配/归属规则取舍。"""
    ra, rb = _row_metric_rank(row_a), _row_metric_rank(row_b)
    if ra != rb:
        return row_a if ra > rb else row_b
    key = normalize_asin(row_a.asin)
    if key in assigned_asins:
        if row_a.user_id != viewer_id and row_b.user_id == viewer_id:
            return row_a
        if row_b.user_id != viewer_id and row_a.user_id == viewer_id:
            return row_b
    if row_a.user_id == viewer_id and row_b.user_id != viewer_id:
        return row_a
    if row_b.user_id == viewer_id and row_a.user_id != viewer_id:
        return row_b
    return row_b if row_b.created_at > row_a.created_at else row_a


def dedupe_dashboard_rows(rows, viewer_id: int, assigned_asins: set[str]):
    """首页看板按 ASIN 去重，避免被分配用户计算 ROI 后出现重复行。"""
    by_asin: dict[str, object] = {}
    order: list[str] = []
    for row in rows:
        key = normalize_asin(row.asin)
        if key not in by_asin:
            by_asin[key] = row
            order.append(key)
        else:
            by_asin[key] = pick_preferred_dashboard_row(
                by_asin[key], row, viewer_id, assigned_asins
            )
    return [by_asin[k] for k in order]


def _extract_asin_roots_from_rel_paths(rel_paths) -> set[str]:
    out: set[str] = set()
    for rp in rel_paths:
        seg = str(rp).replace('\\', '/').strip('/').split('/')[0].strip().upper()
        if _ASIN_DIR.match(seg):
            out.add(seg)
    return out


def user_imported_asin_codes(user: User, *, marketplace: str | None = None) -> set[str]:
    """当前用户在 file 库下导入过的 ASIN 根目录集合；可按站点过滤（带缓存）。"""
    from .marketplace import normalize_marketplace
    from .models import ImportedMediaPath

    if not getattr(user, 'is_authenticated', False):
        return set()
    uid = getattr(user, 'id', None)
    if uid is None:
        return set()
    mp = normalize_marketplace(marketplace)
    ver = _mp_asin_cache_ver()
    key = f'mp_asin:user_imp:{ver}:{uid}:{mp or "ALL"}'
    hit = cache.get(key)
    if hit is not None:
        return set(hit)

    qs = ImportedMediaPath.objects.filter(user=user)
    if mp:
        qs = qs.filter(marketplace=mp)
    out = _extract_asin_roots_from_rel_paths(qs.values_list('rel_path', flat=True))
    cache.set(key, sorted(out), _MP_ASIN_CACHE_TTL)
    return out


def asins_for_marketplace(marketplace: str | None) -> set[str]:
    """任一用户在该站点导入过的 ASIN 根目录（物化表 + 缓存）。"""
    from .marketplace import MARKETPLACE_US, normalize_marketplace
    from .models import MarketplaceAsinRoot

    mp = normalize_marketplace(marketplace) or MARKETPLACE_US
    ver = _mp_asin_cache_ver()
    key = f'mp_asin:site:{ver}:{mp}'
    hit = cache.get(key)
    if hit is not None:
        return set(hit)

    out = {
        normalize_asin(a)
        for a in MarketplaceAsinRoot.objects.filter(marketplace=mp).values_list('asin', flat=True)
        if normalize_asin(a)
    }
    # 物化表为空时回落扫路径并回填，避免迁移未跑完时空白
    if not out:
        from .models import ImportedMediaPath

        out = _extract_asin_roots_from_rel_paths(
            ImportedMediaPath.objects.filter(marketplace=mp).values_list('rel_path', flat=True)
        )
        if out:
            try:
                from .marketplace_asin_root import ensure_marketplace_asin_roots

                ensure_marketplace_asin_roots(out, mp)
            except Exception:
                pass
    cache.set(key, sorted(out), _MP_ASIN_CACHE_TTL)
    return out


def calculated_roi_asins_for_marketplace(marketplace: str | None) -> set[str]:
    """当前站点看板已写入 ROI 的 ASIN 集合（短缓存）。"""
    from .marketplace import MARKETPLACE_US, normalize_marketplace
    from .models import AsinDashboardRow

    mp = normalize_marketplace(marketplace) or MARKETPLACE_US
    ver = _mp_asin_cache_ver()
    key = f'mp_asin:roi_done:{ver}:{mp}'
    hit = cache.get(key)
    if hit is not None:
        return set(hit)
    out = {
        normalize_asin(a)
        for a in AsinDashboardRow.objects.filter(
            marketplace=mp,
            ad_removed_roi__isnull=False,
        ).values_list('asin', flat=True)
        if normalize_asin(a)
    }
    cache.set(key, sorted(out), min(90, _MP_ASIN_CACHE_TTL))
    return out


def invalidate_calculated_roi_asins(marketplace: str | None = None) -> None:
    """ROI 写入后使「已计算」集合失效（不 bump 全站版本）。"""
    from .marketplace import MARKETPLACE_US, MARKETPLACE_UK, normalize_marketplace

    ver = _mp_asin_cache_ver()
    mps = []
    mp = normalize_marketplace(marketplace)
    if mp:
        mps = [mp]
    else:
        mps = [MARKETPLACE_US, MARKETPLACE_UK]
    for m in mps:
        cache.delete(f'mp_asin:roi_done:{ver}:{m}')


def asin_importer_user_ids(asin: str | None, *, marketplace: str | None = None) -> list[int]:
    """曾导入过该 ASIN 媒体目录的用户 id（含根目录或子路径）。"""
    from django.db.models import Q

    from .marketplace import normalize_marketplace
    from .models import ImportedMediaPath

    a = normalize_asin(asin)
    if not a:
        return []
    qs = ImportedMediaPath.objects.filter(Q(rel_path=a) | Q(rel_path__startswith=f'{a}/'))
    mp = normalize_marketplace(marketplace)
    if mp:
        qs = qs.filter(marketplace=mp)
    return list(qs.values_list('user_id', flat=True).distinct())



def _row_metric_rank(row) -> int:
    """已写入 ROI 的字段越多，排名越高（去重时优先展示有数据的行）。"""
    n = 0
    for field in ('monthly_results', 'profit_margin', 'ad_removed_roi', 'monthly_profit1'):
        if getattr(row, field, None) is not None:
            n += 1
    return n


def bulk_assign_asin_folders(
    asins: list[str],
    users,
    *,
    assigned_by=None,
) -> tuple[int, list[str]]:
    """批量设置 ASIN 文件夹分配（覆盖各 ASIN 的被分配人列表）。"""
    from django.db import transaction

    from .models import AsinFolderAssignment

    valid: list[str] = []
    seen: set[str] = set()
    for raw in asins:
        a = normalize_asin(str(raw))
        if not a or not _ASIN_DIR.match(a) or a in seen:
            continue
        seen.add(a)
        valid.append(a)
    if not valid:
        return 0, []

    user_list = list(users)
    user_ids = sorted({int(u.id) for u in user_list})
    assignee_labels = sorted({u.username for u in user_list})
    through = AsinFolderAssignment.assignees.through

    with transaction.atomic():
        existing = set(
            AsinFolderAssignment.objects.filter(asin__in=valid).values_list('asin', flat=True)
        )
        missing = [a for a in valid if a not in existing]
        if missing:
            AsinFolderAssignment.objects.bulk_create(
                [
                    AsinFolderAssignment(asin=a, assigned_by=assigned_by)
                    for a in missing
                ],
                batch_size=500,
            )

        id_by_asin = dict(
            AsinFolderAssignment.objects.filter(asin__in=valid).values_list('asin', 'id')
        )
        assignment_ids = list(id_by_asin.values())
        through.objects.filter(asinfolderassignment_id__in=assignment_ids).delete()

        if user_ids:
            rows = [
                through(asinfolderassignment_id=id_by_asin[a], user_id=uid)
                for a in valid
                if a in id_by_asin
                for uid in user_ids
            ]
            through.objects.bulk_create(rows, batch_size=1000)

        if assigned_by is not None:
            AsinFolderAssignment.objects.filter(asin__in=valid).update(assigned_by=assigned_by)

    bust_marketplace_asin_cache()
    return len(valid), assignee_labels
