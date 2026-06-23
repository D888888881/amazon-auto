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
    """导入/删除媒体后调用，使根目录索引失效。"""
    try:
        ver = str(media_root().stat().st_mtime)
    except OSError:
        ver = str(timezone.now().timestamp())
    cache.set(_META_VERSION_KEY, ver, _CACHE_TTL * 4)


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


def _global_asin_meta(version: str) -> dict:
    key = f'excel_browse:meta:{version}'
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

    dashboard = {normalize_asin(a) for a in AsinDashboardRow.objects.values_list('asin', flat=True)}
    roi = {normalize_asin(a) for a in AsinRoiPackVerification.objects.values_list('asin', flat=True)}
    updated = {
        normalize_asin(a): t for a, t in AsinDataUpdateStamp.objects.values_list('asin', 'updated_at')
    }
    assign_map: dict[str, list[str]] = {}
    for obj in AsinFolderAssignment.objects.prefetch_related('assignees').only('asin', 'id'):
        assign_map[normalize_asin(obj.asin)] = sorted({u.username for u in obj.assignees.all()})
    uploaders: dict[str, list[str]] = defaultdict(set)
    for rpath, uname in ImportedMediaPath.objects.values_list('rel_path', 'user__username'):
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


def _user_root_access(user: User) -> dict:
    key = f'excel_browse:access:{user.id}'
    hit = cache.get(key)
    if hit is not None:
        return hit
    assigned = {normalize_asin(a) for a in user_assigned_asin_codes(user)}
    imported = set(user_imported_asin_codes(user))
    hit = {'assigned': assigned, 'imported': imported}
    cache.set(key, hit, _CACHE_TTL)
    return hit


def _user_owned_root_asins(user: User) -> set[str]:
    key = f'excel_browse:owned_roots:{user.id}'
    hit = cache.get(key)
    if hit is not None:
        return set(hit)
    from .models import ImportedMediaPath

    roots: set[str] = set()
    for rp in ImportedMediaPath.objects.filter(user=user).values_list('rel_path', flat=True):
        seg = str(rp).replace('\\', '/').strip('/').split('/')[0].strip().upper()
        if _ASIN_DIR.match(seg):
            roots.add(seg)
    cache.set(key, sorted(roots), _CACHE_TTL)
    return roots


def build_root_index_items(user: User, *, is_super: bool) -> list[dict]:
    version = _cache_version()
    role = 'super' if is_super else f'u{user.id}'
    index_key = f'excel_browse:index:{version}:{role}'
    cached = cache.get(index_key)
    if cached is not None:
        return cached

    entries = _fs_root_entries(version)
    meta = _global_asin_meta(version)
    access = None if is_super else _user_root_access(user)
    import_roots = access['imported'] if access else set()

    items: list[dict] = []
    for ent in entries:
        if not ent['is_asin_dir']:
            continue
        nm = ent['name'].strip().upper()
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


def enrich_root_page_delete_flags(user: User, *, is_super: bool, items: list[dict]) -> None:
    if is_super:
        for it in items:
            it['can_delete'] = True
        return
    owned = _user_owned_root_asins(user)
    assigned = {normalize_asin(a) for a in user_assigned_asin_codes(user)}
    for it in items:
        nm = str(it.get('name') or '').strip().upper()
        it['can_delete'] = nm in owned or nm in assigned
