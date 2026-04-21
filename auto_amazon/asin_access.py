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
    from .models import ImportedMediaPath

    if ImportedMediaPath.objects.filter(user=user, rel_path__startswith=f'{root}/').exists():
        return True
    return ImportedMediaPath.objects.filter(user=user, rel_path=root).exists()


def user_imported_asin_codes(user: User) -> set[str]:
    """当前用户在 file 库下导入过的 ASIN 根目录集合。"""
    from .models import ImportedMediaPath

    out: set[str] = set()
    for rp in ImportedMediaPath.objects.filter(user=user).values_list('rel_path', flat=True):
        seg = str(rp).split('/')[0].strip().upper()
        if _ASIN_DIR.match(seg):
            out.add(seg)
    return out
