"""ASIN 产品主图路径解析与看板展示辅助。"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from django.conf import settings
from django.urls import reverse

from .asin_access import normalize_asin, user_dashboard_rows_qs

IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp')


def asin_images_dir() -> Path:
    """主图写入/优先读取目录：默认 MEDIA_ROOT/images，可用 ASIN_IMAGES_ROOT 覆盖。"""
    root = getattr(settings, 'ASIN_IMAGES_ROOT', None)
    if root:
        return Path(root).resolve()
    return (Path(settings.MEDIA_ROOT) / 'images').resolve()


def asin_images_legacy_dirs() -> list[Path]:
    """兼容旧路径：仓库内 scripts/asin_find_project/images（仅读取回退）。"""
    return [
        (
            Path(settings.BASE_DIR).resolve()
            / 'scripts'
            / 'asin_find_project'
            / 'images'
        )
    ]


def _candidate_image_dirs() -> list[Path]:
    dirs = [asin_images_dir()]
    for d in asin_images_legacy_dirs():
        if d not in dirs:
            dirs.append(d)
    return dirs


def find_asin_image_file(asin: str) -> Path | None:
    a = normalize_asin(asin)
    if not a:
        return None
    for base in _candidate_image_dirs():
        for ext in IMAGE_EXTS:
            path = base / f'{a}{ext}'
            if path.is_file():
                return path
    return None


def asins_with_image_files(asins: set[str]) -> set[str]:
    dirs = [d for d in _candidate_image_dirs() if d.is_dir()]
    if not dirs:
        return set()
    out: set[str] = set()
    for raw in asins:
        a = normalize_asin(raw)
        if not a:
            continue
        for base in dirs:
            found = False
            for ext in IMAGE_EXTS:
                if (base / f'{a}{ext}').is_file():
                    out.add(a)
                    found = True
                    break
            if found:
                break
    return out


def attach_product_image_urls(rows) -> None:
    """为看板行附加 product_image_url（无图则为空字符串）。"""
    asins = {normalize_asin(r.asin) for r in rows}
    has_image = asins_with_image_files(asins)
    for row in rows:
        ak = normalize_asin(row.asin)
        if ak in has_image:
            row.product_image_url = reverse('asin_product_image', kwargs={'asin': ak})
        else:
            row.product_image_url = ''


def user_can_view_asin_product_image(user, asin: str) -> bool:
    if getattr(user, 'is_superuser', False):
        return True
    a = normalize_asin(asin)
    if not a:
        return False
    if user_dashboard_rows_qs(user).filter(asin=a).exists():
        return True
    from .asin_access import user_assigned_asin_codes, user_imported_asin_codes

    if a in {normalize_asin(x) for x in user_assigned_asin_codes(user)}:
        return True
    if a in user_imported_asin_codes(user):
        return True
    return False


def guess_image_content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or 'image/jpeg'
