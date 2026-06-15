"""ASIN 产品主图路径解析与看板展示辅助。"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from django.conf import settings
from django.urls import reverse

from .asin_access import normalize_asin, user_dashboard_rows_qs

IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp')


def asin_images_dir() -> Path:
    return (
        Path(settings.BASE_DIR).resolve()
        / 'scripts'
        / 'asin_find_project'
        / 'images'
    )


def find_asin_image_file(asin: str) -> Path | None:
    a = normalize_asin(asin)
    if not a:
        return None
    base = asin_images_dir()
    for ext in IMAGE_EXTS:
        path = base / f'{a}{ext}'
        if path.is_file():
            return path
    return None


def asins_with_image_files(asins: set[str]) -> set[str]:
    base = asin_images_dir()
    if not base.is_dir():
        return set()
    out: set[str] = set()
    for raw in asins:
        a = normalize_asin(raw)
        if not a:
            continue
        for ext in IMAGE_EXTS:
            if (base / f'{a}{ext}').is_file():
                out.add(a)
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
    return user_dashboard_rows_qs(user).filter(asin=a).exists()


def guess_image_content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or 'image/jpeg'
