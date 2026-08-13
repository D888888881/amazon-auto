"""数据审核页根目录浏览索引（缓存 + 先筛选分页再补全详情）。"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING

from django.core.cache import cache
from django.utils import timezone

from .asin_access import normalize_asin, user_assigned_asin_codes, user_imported_asin_codes
from .media_paths import media_root

if TYPE_CHECKING:
    from django.contrib.auth.models import User

_ASIN_DIR = re.compile(r'^B0[A-Z0-9]{8}$', re.IGNORECASE)
_CACHE_TTL = 90
_META_VERSION_KEY = 'excel_browse:meta_version'


def bust_excel_browse_cache() -> None:
    """导入/删除媒体后调用，使根目录索引与站点 ASIN 缓存失效。"""
    from .asin_access import bust_marketplace_asin_cache

    try:
        ver = str(media_root().stat().st_mtime)
    except OSError:
        ver = str(timezone.now().timestamp())
    cache.set(_META_VERSION_KEY, ver, _CACHE_TTL * 4)
    bust_marketplace_asin_cache()


def _cache_version() -> str:
    ver = cache.get(_META_VERSION_KEY)
    if ver is not None:
        return str(ver)
    try:
        ver = str(media_root().stat().st_mtime)
    except OSError:
        ver = '0'
    cache.set(_META_VERSION_KEY, ver, _CACHE_TTL)
    return ver


def cached_fs_asin_dirs() -> set[str]:
    """media/file 顶层 ASIN 目录名集合（复用审核页 FS 缓存，避免重复 iterdir）。"""
    entries = _fs_root_entries(_cache_version())
    return {
        str(e.get('name') or '').strip().upper()
        for e in entries
        if e.get('is_asin_dir') and str(e.get('name') or '').strip()
    }


def warm_excel_root_index_async(user_id: int, *, is_super: bool, marketplace: str) -> None:
    """后台预热审核页根索引，壳页可秒开。"""
    import threading

    def _run() -> None:
        from django.contrib.auth.models import User
        from django.db import close_old_connections

        close_old_connections()
        try:
            user = User.objects.filter(pk=user_id).first()
            if not user:
                return
            # 先热站点集合与 FS，再热整表索引
            from .asin_access import asins_for_marketplace

            asins_for_marketplace(marketplace)
            cached_fs_asin_dirs()
            build_root_index_items(user, is_super=is_super, marketplace=marketplace)
        except Exception:
            pass
        finally:
            close_old_connections()

    threading.Thread(target=_run, daemon=True).start()


def _fs_root_entries(version: str) -> list[dict]:
    key = f'excel_browse:fs:{version}'
    hit = cache.get(key)
    if hit is not None:
        return hit
    out: list[dict] = []
    try:
        for p in media_root().iterdir():
            if p.name.startswith('.') or not p.is_dir():
                continue
            nm = p.name.strip().upper()
            out.append({'name': p.name, 'is_asin_dir': bool(_ASIN_DIR.match(nm))})
    except OSError:
        pass
    cache.set(key, out, _CACHE_TTL)
    return out


def _global_asin_meta(version: str, *, marketplace: str) -> dict:
    key = f'excel_browse:meta:{version}:{marketplace}'
    hit = cache.get(key)
    if hit is not None:
        return hit
    from .models import (
        AsinDashboardRow,
        AsinDataUpdateStamp,
        AsinFolderAssignment,
        AsinRoiPackVerification,
        ImportedMediaPath,
    )

    dashboard = {
        normalize_asin(a)
        for a in AsinDashboardRow.objects.filter(marketplace=marketplace).values_list(
            'asin', flat=True
        )
    }
    roi = {normalize_asin(a) for a in AsinRoiPackVerification.objects.values_list('asin', flat=True)}
    updated = {
        normalize_asin(a): t for a, t in AsinDataUpdateStamp.objects.values_list('asin', 'updated_at')
    }
    assign_map: dict[str, list[str]] = {}
    for obj in AsinFolderAssignment.objects.prefetch_related('assignees').only('asin', 'id'):
        assign_map[normalize_asin(obj.asin)] = sorted({u.username for u in obj.assignees.all()})
    uploaders: dict[str, list[str]] = defaultdict(set)
    for rpath, uname in ImportedMediaPath.objects.filter(marketplace=marketplace).values_list(
        'rel_path', 'user__username'
    ):
        rp = str(rpath).replace('\\', '/').strip('/')
        if not rp:
            continue
        seg = rp.split('/')[0].strip().upper()
        if _ASIN_DIR.match(seg):
            uploaders[seg].add(uname)
    hit = {
        'dashboard': dashboard,
        'roi': roi,
        'updated': updated,
        'assign': assign_map,
        'uploaders': {k: sorted(v) for k, v in uploaders.items()},
    }
    cache.set(key, hit, _CACHE_TTL)
    return hit


def _user_root_access(user: User, *, marketplace: str | None = None) -> dict:
    key = f'excel_browse:access:{user.id}:{marketplace or "ALL"}'
    hit = cache.get(key)
    if hit is not None:
        return hit
    assigned = {normalize_asin(a) for a in user_assigned_asin_codes(user)}
    imported = set(user_imported_asin_codes(user, marketplace=marketplace))
    hit = {'assigned': assigned, 'imported': imported}
    cache.set(key, hit, _CACHE_TTL)
    return hit


def _user_owned_root_asins(user: User, *, marketplace: str | None = None) -> set[str]:
    key = f'excel_browse:owned_roots:{user.id}:{marketplace or "ALL"}'
    hit = cache.get(key)
    if hit is not None:
        return set(hit)
    from .models import ImportedMediaPath

    qs = ImportedMediaPath.objects.filter(user=user)
    if marketplace:
        qs = qs.filter(marketplace=marketplace)
    roots: set[str] = set()
    for rp in qs.values_list('rel_path', flat=True):
        seg = str(rp).replace('\\', '/').strip('/').split('/')[0].strip().upper()
        if _ASIN_DIR.match(seg):
            roots.add(seg)
    cache.set(key, sorted(roots), _CACHE_TTL)
    return roots


def build_root_index_items(
    user: User,
    *,
    is_super: bool,
    marketplace: str | None = None,
) -> list[dict]:
    from .asin_access import asins_for_marketplace
    from .marketplace import MARKETPLACE_US, normalize_marketplace

    mp = normalize_marketplace(marketplace) or MARKETPLACE_US
    version = _cache_version()
    role = 'super' if is_super else f'u{user.id}'
    index_key = f'excel_browse:index:{version}:{role}:{mp}'
    cached = cache.get(index_key)
    if cached is not None:
        return cached

    entries = _fs_root_entries(version)
    meta = _global_asin_meta(version, marketplace=mp)
    access = None if is_super else _user_root_access(user, marketplace=mp)
    import_roots = access['imported'] if access else set()
    site_roots = asins_for_marketplace(mp)

    items: list[dict] = []
    for ent in entries:
        if not ent['is_asin_dir']:
            continue
        nm = ent['name'].strip().upper()
        if nm not in site_roots:
            continue
        if access is not None and nm not in access['assigned'] and nm not in import_roots:
            continue
        assignees = meta['assign'].get(nm, [])
        updated_at = meta['updated'].get(nm)
        updated_label = (
            timezone.localtime(updated_at).strftime('%Y-%m-%d %H:%M:%S') if updated_at else ''
        )
        items.append(
            {
                'name': ent['name'],
                'type': 'dir',
                'calculated': nm in meta['dashboard'],
                'is_asin_dir': True,
                'assigned': bool(assignees),
                'assignees': assignees,
                'roi_verified': nm in meta['roi'],
                'updated_at': updated_label,
                'updated_at_ts': int(updated_at.timestamp() * 1000) if updated_at else 0,
                'imported_by_me': nm in import_roots,
                'uploaders': meta['uploaders'].get(nm, []),
                'can_delete': True,
            }
        )
    items.sort(
        key=lambda it: (
            it.get('type') != 'dir',
            not bool(it.get('is_asin_dir')),
            -(it.get('updated_at_ts') or 0),
            str(it.get('name') or '').lower(),
        )
    )
    cache.set(index_key, items, _CACHE_TTL)
    return items


def apply_root_filters(items: list[dict], fp: dict) -> list[dict]:
    out: list[dict] = []
    for it in items:
        if fp['q'] and fp['q'] not in str(it.get('name') or '').lower():
            continue
        if fp['calc'] != 'all':
            calc = bool(it.get('calculated'))
            if fp['calc'] == 'yes' and not calc:
                continue
            if fp['calc'] == 'no' and calc:
                continue
        if fp['roi_verified'] != 'all':
            rv = bool(it.get('roi_verified'))
            if fp['roi_verified'] == 'yes' and not rv:
                continue
            if fp['roi_verified'] == 'no' and rv:
                continue
        if fp['updated_from_ms'] or fp['updated_to_ms']:
            ts = int(it.get('updated_at_ts') or 0)
            if fp['updated_from_ms'] and ts < fp['updated_from_ms']:
                continue
            if fp['updated_to_ms'] and ts > fp['updated_to_ms']:
                continue
        if fp['assign_status'] != 'all':
            has_a = bool(it.get('assignees'))
            if fp['assign_status'] == 'yes' and not has_a:
                continue
            if fp['assign_status'] == 'no' and has_a:
                continue
        if fp['assignee']:
            names = it.get('assignees') or []
            if fp['assignee'] not in names:
                continue
        if fp['uploaded_by']:
            upl = set(it.get('uploaders') or [])
            if fp['uploaded_by'] not in upl:
                continue
        out.append(it)
    return out


def enrich_root_page_delete_flags(
    user: User,
    *,
    is_super: bool,
    items: list[dict],
    marketplace: str | None = None,
) -> None:
    if is_super:
        for it in items:
            it['can_delete'] = True
        return
    owned = _user_owned_root_asins(user, marketplace=marketplace)
    assigned = {normalize_asin(a) for a in user_assigned_asin_codes(user)}
    for it in items:
        nm = str(it.get('name') or '').strip().upper()
        it['can_delete'] = nm in owned or nm in assigned


def build_root_page(
    user: User,
    *,
    is_super: bool,
    marketplace: str | None,
    fp: dict,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    """
    按页构建审核根目录（基于 MarketplaceAsinRoot），避免先建全量索引再切片。
    返回 (page_items, total)。
    """
    from datetime import datetime

    from django.contrib.auth.models import User as AuthUser
    from django.db.models import Count, Exists, F, OuterRef, Q, Subquery

    from .marketplace import MARKETPLACE_US, normalize_marketplace
    from .models import (
        AsinDashboardRow,
        AsinDataUpdateStamp,
        AsinFolderAssignment,
        AsinRoiPackVerification,
        ImportedMediaPath,
        MarketplaceAsinRoot,
    )

    mp = normalize_marketplace(marketplace) or MARKETPLACE_US
    qs = MarketplaceAsinRoot.objects.filter(marketplace=mp)

    if not is_super:
        access = _user_root_access(user, marketplace=mp)
        allowed = access['assigned'] | access['imported']
        if not allowed:
            return [], 0
        qs = qs.filter(asin__in=allowed)

    q = (fp.get('q') or '').strip()
    if q:
        qs = qs.filter(asin__icontains=q)

    qs = qs.annotate(
        calculated=Exists(
            AsinDashboardRow.objects.filter(asin=OuterRef('asin'), marketplace=mp)
        ),
        roi_verified=Exists(
            AsinRoiPackVerification.objects.filter(asin=OuterRef('asin'))
        ),
        stamp_at=Subquery(
            AsinDataUpdateStamp.objects.filter(asin=OuterRef('asin')).values('updated_at')[:1]
        ),
        assign_count=Subquery(
            AsinFolderAssignment.objects.filter(asin=OuterRef('asin'))
            .annotate(n=Count('assignees'))
            .values('n')[:1]
        ),
    )

    calc = fp.get('calc') or 'all'
    if calc == 'yes':
        qs = qs.filter(calculated=True)
    elif calc == 'no':
        qs = qs.filter(calculated=False)

    roi_f = fp.get('roi_verified') or 'all'
    if roi_f == 'yes':
        qs = qs.filter(roi_verified=True)
    elif roi_f == 'no':
        qs = qs.filter(roi_verified=False)

    assign_status = fp.get('assign_status') or 'all'
    if assign_status == 'yes':
        qs = qs.filter(assign_count__gt=0)
    elif assign_status == 'no':
        qs = qs.filter(Q(assign_count__isnull=True) | Q(assign_count=0))

    if fp.get('assignee'):
        asins = AsinFolderAssignment.objects.filter(
            assignees__username=fp['assignee']
        ).values_list('asin', flat=True)
        qs = qs.filter(asin__in=asins)

    if fp.get('uploaded_by'):
        upl = AuthUser.objects.filter(username=fp['uploaded_by'], is_active=True).first()
        if not upl:
            return [], 0
        up_roots = user_imported_asin_codes(upl, marketplace=mp)
        qs = qs.filter(asin__in=up_roots)

    from_ms = int(fp.get('updated_from_ms') or 0)
    to_ms = int(fp.get('updated_to_ms') or 0)
    tz = timezone.get_current_timezone()
    if from_ms:
        qs = qs.exclude(stamp_at__isnull=True).filter(
            stamp_at__gte=datetime.fromtimestamp(from_ms / 1000.0, tz=tz)
        )
    if to_ms:
        qs = qs.exclude(stamp_at__isnull=True).filter(
            stamp_at__lte=datetime.fromtimestamp(to_ms / 1000.0, tz=tz)
        )

    qs = qs.order_by(F('stamp_at').desc(nulls_last=True), 'asin')
    total = qs.count()
    if total == 0 or limit <= 0:
        return [], total

    page_rows = list(qs[offset : offset + limit])
    page_asins = [normalize_asin(r.asin) for r in page_rows]
    page_asin_set = set(page_asins)

    assign_map: dict[str, list[str]] = {}
    if page_asins:
        for obj in AsinFolderAssignment.objects.filter(asin__in=page_asins).prefetch_related(
            'assignees'
        ):
            assign_map[normalize_asin(obj.asin)] = sorted(
                {u.username for u in obj.assignees.all()}
            )

    uploaders: dict[str, list[str]] = defaultdict(set)
    if page_asins:
        q_up = Q()
        for a in page_asins:
            q_up |= Q(rel_path=a) | Q(rel_path__startswith=f'{a}/')
        for rpath, uname in (
            ImportedMediaPath.objects.filter(marketplace=mp)
            .filter(q_up)
            .values_list('rel_path', 'user__username')
        ):
            seg = str(rpath).replace('\\', '/').strip('/').split('/')[0].strip().upper()
            if seg in page_asin_set and uname:
                uploaders[seg].add(uname)

    import_roots: set[str] = set()
    if not is_super:
        import_roots = _user_root_access(user, marketplace=mp)['imported']

    items: list[dict] = []
    for r in page_rows:
        nm = normalize_asin(r.asin)
        updated_at = getattr(r, 'stamp_at', None)
        updated_label = (
            timezone.localtime(updated_at).strftime('%Y-%m-%d %H:%M:%S') if updated_at else ''
        )
        assignees = assign_map.get(nm, [])
        items.append(
            {
                'name': nm,
                'type': 'dir',
                'calculated': bool(getattr(r, 'calculated', False)),
                'is_asin_dir': True,
                'assigned': bool(assignees),
                'assignees': assignees,
                'roi_verified': bool(getattr(r, 'roi_verified', False)),
                'updated_at': updated_label,
                'updated_at_ts': int(updated_at.timestamp() * 1000) if updated_at else 0,
                'imported_by_me': nm in import_roots,
                'uploaders': sorted(uploaders.get(nm, [])),
                'can_delete': True,
            }
        )
    return items, total
