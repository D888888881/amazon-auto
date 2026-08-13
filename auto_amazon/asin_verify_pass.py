"""ROI 校验（按人）与已通过（全局）辅助。"""
from __future__ import annotations

from collections import defaultdict

from django.contrib.auth import get_user_model

from .asin_access import normalize_asin
from .marketplace import MARKETPLACE_US, normalize_marketplace
from .models import AsinPassedFlag, AsinRoiPackVerification

User = get_user_model()


def mark_asins_verified(
    user,
    asins: list[str] | set[str],
    *,
    marketplace: str | None,
) -> int:
    mp = normalize_marketplace(marketplace) or MARKETPLACE_US
    n = 0
    for raw in asins:
        a = normalize_asin(raw)
        if not a:
            continue
        _, created = AsinRoiPackVerification.objects.update_or_create(
            user=user,
            asin=a,
            marketplace=mp,
            defaults={},
        )
        n += 1
    return n


def mark_asins_passed(
    user,
    asins: list[str] | set[str],
    *,
    marketplace: str | None,
) -> int:
    mp = normalize_marketplace(marketplace) or MARKETPLACE_US
    n = 0
    for raw in asins:
        a = normalize_asin(raw)
        if not a:
            continue
        AsinPassedFlag.objects.update_or_create(
            asin=a,
            marketplace=mp,
            defaults={'passed_by': user},
        )
        n += 1
    return n


def unmark_asins_passed(
    asins: list[str] | set[str],
    *,
    marketplace: str | None,
) -> int:
    mp = normalize_marketplace(marketplace) or MARKETPLACE_US
    norms = [normalize_asin(a) for a in asins if normalize_asin(a)]
    if not norms:
        return 0
    deleted, _ = AsinPassedFlag.objects.filter(asin__in=norms, marketplace=mp).delete()
    return deleted


def verification_labels_for_asins(
    asins: set[str],
    *,
    marketplace: str | None,
    viewer_id: int | None = None,
) -> dict[str, dict]:
    """
    返回 {asin: {my_verified: bool, labels: 'a、b', names: [..]}}
    仅查当前页 ASIN。
    """
    mp = normalize_marketplace(marketplace) or MARKETPLACE_US
    norms = {normalize_asin(a) for a in asins if normalize_asin(a)}
    out = {
        a: {'my_verified': False, 'labels': '—', 'names': []}
        for a in norms
    }
    if not norms:
        return out
    rows = (
        AsinRoiPackVerification.objects.filter(asin__in=norms, marketplace=mp)
        .select_related('user')
        .order_by('verified_at')
    )
    names_map: dict[str, list[str]] = defaultdict(list)
    my_set: set[str] = set()
    for r in rows:
        a = normalize_asin(r.asin)
        uname = getattr(r.user, 'username', '') or str(r.user_id)
        if uname and uname not in names_map[a]:
            names_map[a].append(uname)
        if viewer_id is not None and r.user_id == viewer_id:
            my_set.add(a)
    for a, names in names_map.items():
        out[a] = {
            'my_verified': a in my_set,
            'labels': '、'.join(names) if names else '—',
            'names': names,
        }
    return out


def passed_asins_on_page(asins: set[str], *, marketplace: str | None) -> set[str]:
    mp = normalize_marketplace(marketplace) or MARKETPLACE_US
    norms = {normalize_asin(a) for a in asins if normalize_asin(a)}
    if not norms:
        return set()
    return {
        normalize_asin(a)
        for a in AsinPassedFlag.objects.filter(asin__in=norms, marketplace=mp).values_list(
            'asin', flat=True
        )
    }
