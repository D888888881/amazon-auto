"""ASIN 媒体路径与文件夹分配相关的权限与解析。"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.contrib.auth.models import User

_ASIN_DIR = re.compile(r'^B0[A-Z0-9]{8}$', re.IGNORECASE)


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
    return list(
        AsinFolderAssignment.objects.filter(assignees=user).values_list('asin', flat=True)
    )


def user_is_assigned_to_asin(user: User, asin: str | None) -> bool:
    a = normalize_asin(asin)
    if not a:
        return False
    from .models import AsinFolderAssignment

    return AsinFolderAssignment.objects.filter(asin=a, assignees=user).exists()


def user_can_access_excel_media_path(user: User, rel_path: str) -> bool:
    """非超管：可访问已分配给自己的 ASIN 目录，或本人曾导入过的 ASIN 目录下路径。"""
    if getattr(user, 'is_superuser', False):
        return True
    root = asin_root_from_rel_path(rel_path)
    if not root:
        return False
    if user_is_assigned_to_asin(user, root):
        return True
    from .models import AsinDashboardRow

    if AsinDashboardRow.objects.filter(user=user, asin=root).exists():
        return True
    from .models import ImportedMediaPath

    if ImportedMediaPath.objects.filter(user=user, rel_path__startswith=f'{root}/').exists():
        return True
    return ImportedMediaPath.objects.filter(user=user, rel_path=root).exists()


def user_dashboard_rows_qs(user: User):
    """首页看板可见行：本人数据 + 被分配的 ASIN。"""
    from django.db.models import Q

    from .models import AsinDashboardRow

    if not getattr(user, 'is_authenticated', False):
        return AsinDashboardRow.objects.none()
    assigned = user_assigned_asin_codes(user)
    return AsinDashboardRow.objects.filter(Q(user=user) | Q(asin__in=assigned)).distinct()


def user_can_operate_dashboard_row(user: User, row) -> bool:
    """可勾选、计算 ROI/广告难度、导出、编辑采购价等（不含删除）。"""
    if getattr(user, 'is_superuser', False):
        return True
    if row.user_id == user.id:
        return True
    return user_is_assigned_to_asin(user, row.asin)


def user_can_delete_dashboard_row(user: User, row) -> bool:
    """看板行删除：仅数据归属者或超管；被分配用户不可删。"""
    if getattr(user, 'is_superuser', False):
        return True
    return row.user_id == user.id


def resolve_dashboard_row_for_persist(
    user: User,
    asin: str,
    target_row_ids: dict[str, int] | None = None,
):
    """ROI 结果写入时定位看板行：勾选行 > 被分配共享行 > 本人行。"""
    from .models import AsinDashboardRow

    a = normalize_asin(asin)
    if not a or not getattr(user, 'is_authenticated', False):
        return None
    id_map = {normalize_asin(k): v for k, v in (target_row_ids or {}).items()}
    row_pk = id_map.get(a)
    if row_pk:
        row = AsinDashboardRow.objects.filter(pk=row_pk).first()
        if row:
            return row
    if user_is_assigned_to_asin(user, a):
        shared = (
            AsinDashboardRow.objects.filter(asin=a)
            .exclude(user_id=user.id)
            .order_by('-created_at')
            .first()
        )
        if shared:
            return shared
    return AsinDashboardRow.objects.filter(user_id=user.id, asin=a).first()


def pick_preferred_dashboard_row(row_a, row_b, viewer_id: int, assigned_asins: set[str]):
    """同一 ASIN 多行时：被分配 ASIN 优先展示/保留管理员共享行，否则优先本人行。"""
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


def user_imported_asin_codes(user: User) -> set[str]:
    """当前用户在 file 库下导入过的 ASIN 根目录集合。"""
    from .models import ImportedMediaPath

    out: set[str] = set()
    for rp in ImportedMediaPath.objects.filter(user=user).values_list('rel_path', flat=True):
        seg = str(rp).split('/')[0].strip().upper()
        if _ASIN_DIR.match(seg):
            out.add(seg)
    return out


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

    return len(valid), assignee_labels
