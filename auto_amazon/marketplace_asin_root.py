"""站点 × ASIN 根物化表维护。"""
from __future__ import annotations

import re
from typing import Iterable

from django.db import transaction
from django.utils import timezone

_ASIN_DIR = re.compile(r'^B0[A-Z0-9]{8}$', re.IGNORECASE)


def _norm_asin(s: str | None) -> str | None:
    a = (s or '').strip().upper()
    return a if a and _ASIN_DIR.match(a) else None


def ensure_marketplace_asin_roots(
    asins: Iterable[str],
    marketplace: str,
) -> int:
    """导入后写入/刷新站点 ASIN 根；返回新增条数。"""
    from .asin_access import bust_marketplace_asin_cache
    from .marketplace import MARKETPLACE_US, normalize_marketplace
    from .models import MarketplaceAsinRoot

    mp = normalize_marketplace(marketplace) or MARKETPLACE_US
    uniq = sorted({a for a in (_norm_asin(x) for x in asins) if a})
    if not uniq:
        return 0
    now = timezone.now()
    existing = set(
        MarketplaceAsinRoot.objects.filter(marketplace=mp, asin__in=uniq).values_list(
            'asin', flat=True
        )
    )
    to_create = [
        MarketplaceAsinRoot(marketplace=mp, asin=a, first_imported_at=now, updated_at=now)
        for a in uniq
        if a not in existing
    ]
    with transaction.atomic():
        if to_create:
            MarketplaceAsinRoot.objects.bulk_create(to_create, ignore_conflicts=True)
        if existing:
            MarketplaceAsinRoot.objects.filter(marketplace=mp, asin__in=list(existing)).update(
                updated_at=now
            )
    bust_marketplace_asin_cache()
    return len(to_create)


def prune_marketplace_asin_roots(
    asins: Iterable[str],
    marketplace: str,
) -> int:
    """删除媒体后：若该站已无任何导入路径，则移除根记录。"""
    from django.db.models import Q

    from .asin_access import bust_marketplace_asin_cache, normalize_asin
    from .marketplace import MARKETPLACE_US, normalize_marketplace
    from .models import ImportedMediaPath, MarketplaceAsinRoot

    mp = normalize_marketplace(marketplace) or MARKETPLACE_US
    uniq = sorted({normalize_asin(x) for x in asins if normalize_asin(x)})
    if not uniq:
        return 0
    still: set[str] = set()
    for a in uniq:
        if ImportedMediaPath.objects.filter(marketplace=mp).filter(
            Q(rel_path=a) | Q(rel_path__startswith=f'{a}/')
        ).exists():
            still.add(a)
    to_delete = [a for a in uniq if a not in still]
    if not to_delete:
        return 0
    deleted, _ = MarketplaceAsinRoot.objects.filter(marketplace=mp, asin__in=to_delete).delete()
    bust_marketplace_asin_cache()
    return deleted


def rebuild_marketplace_asin_roots(*, marketplace: str | None = None) -> int:
    """从 ImportedMediaPath 全量重建（运维/纠偏）。"""
    from .asin_access import bust_marketplace_asin_cache
    from .marketplace import MARKETPLACE_US, MARKETPLACE_UK, normalize_marketplace
    from .models import ImportedMediaPath, MarketplaceAsinRoot

    mps = []
    mp = normalize_marketplace(marketplace)
    if mp:
        mps = [mp]
    else:
        mps = [MARKETPLACE_US, MARKETPLACE_UK]

    total = 0
    for m in mps:
        asins: set[str] = set()
        for rp in ImportedMediaPath.objects.filter(marketplace=m).values_list('rel_path', flat=True):
            a = _norm_asin(str(rp).replace('\\', '/').strip('/').split('/')[0])
            if a:
                asins.add(a)
        MarketplaceAsinRoot.objects.filter(marketplace=m).exclude(asin__in=asins).delete()
        total += ensure_marketplace_asin_roots(asins, m)
    bust_marketplace_asin_cache()
    return total
