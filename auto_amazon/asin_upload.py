"""ASIN 批量上传：解析、去重、入库。"""
from __future__ import annotations

from django.contrib.auth.models import User
from django.db import transaction

from .asin_access import normalize_asin
from .models import AsinCatalogItem, AsinUploadBatch
from .utils import extract_asins_from_upload


ALLOWED_UPLOAD_EXTS = {'.txt', '.csv', '.xlsx', '.xls'}


def _normalize_ext(filename: str) -> str:
    name = (filename or '').lower().strip()
    for ext in ALLOWED_UPLOAD_EXTS:
        if name.endswith(ext):
            return ext
    return ''


@transaction.atomic
def ingest_asin_upload(user: User, filename: str, raw: bytes) -> tuple[AsinUploadBatch, str | None]:
    """
    解析上传文件，与全局 ASIN 库去重后写入。
    返回 (批次, 错误信息)；错误时批次为 None。
    """
    ext = _normalize_ext(filename)
    if not ext:
        return None, '仅支持 .txt、.csv、.xlsx、.xls 格式'

    parsed = extract_asins_from_upload(ext, raw)
    if not parsed:
        return None, '文件中未识别到有效 ASIN（每行一个或表格单元格均可）'

    existing = set(AsinCatalogItem.objects.filter(asin__in=parsed).values_list('asin', flat=True))
    new_asins = [a for a in parsed if a not in existing]
    skipped = len(parsed) - len(new_asins)

    batch = AsinUploadBatch.objects.create(
        user=user,
        source_filename=(filename or '')[:255],
        total_in_file=len(parsed),
        new_count=len(new_asins),
        skipped_count=skipped,
    )

    if new_asins:
        AsinCatalogItem.objects.bulk_create(
            [
                AsinCatalogItem(
                    asin=normalize_asin(a) or a,
                    batch=batch,
                    uploaded_by=user,
                )
                for a in new_asins
            ],
            batch_size=500,
        )

    return batch, None


def batch_asin_lines(batch: AsinUploadBatch) -> list[str]:
    return list(batch.items.order_by('asin').values_list('asin', flat=True))
