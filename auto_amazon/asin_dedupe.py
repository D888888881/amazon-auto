"""ASIN 去重：剔除系统中已存在于 media/file 的 ASIN。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .asin_access import normalize_asin
from .media_paths import media_root

_ASIN_DIR = re.compile(r'^B0[A-Z0-9]{8}$', re.IGNORECASE)


def parse_asin_text(raw: bytes | str) -> list[str]:
    """从 txt 内容解析 ASIN 列表（每行一个，或逗号/空格分隔）。"""
    if isinstance(raw, bytes):
        text = raw.decode('utf-8', errors='replace')
    else:
        text = str(raw)
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        for part in re.split(r'[,\s]+', s):
            a = normalize_asin(part)
            if a:
                out.append(a)
    return out


def scan_media_asin_dirs() -> set[str]:
    """扫描 media/file 下已有 ASIN 目录（与数据审核页一致）。"""
    existing: set[str] = set()
    root = media_root()
    try:
        for p in root.iterdir():
            if p.name.startswith('.') or not p.is_dir():
                continue
            nm = p.name.strip().upper()
            if _ASIN_DIR.match(nm):
                existing.add(nm)
    except OSError:
        pass
    return existing


def scan_dashboard_asins() -> set[str]:
    from .models import AsinDashboardRow

    return {
        normalize_asin(a)
        for a in AsinDashboardRow.objects.values_list('asin', flat=True)
        if normalize_asin(a)
    }


@dataclass
class AsinDedupeResult:
    total_raw: int
    total_unique: int
    duplicate_lines: int
    existing_count: int
    keep_count: int
    keep: list[str]
    removed: list[str]
    existing_source_count: int

    @property
    def keep_text(self) -> str:
        return '\n'.join(self.keep) + ('\n' if self.keep else '')

    @property
    def removed_text(self) -> str:
        return '\n'.join(self.removed) + ('\n' if self.removed else '')


def filter_new_asins(
    asins: list[str],
    *,
    include_dashboard: bool = False,
) -> AsinDedupeResult:
    existing = scan_media_asin_dirs()
    if include_dashboard:
        existing |= scan_dashboard_asins()

    seen: set[str] = set()
    keep: list[str] = []
    removed: list[str] = []
    dup = 0
    for a in asins:
        if a in seen:
            dup += 1
            continue
        seen.add(a)
        if a in existing:
            removed.append(a)
        else:
            keep.append(a)

    return AsinDedupeResult(
        total_raw=len(asins),
        total_unique=len(seen),
        duplicate_lines=dup,
        existing_count=len(removed),
        keep_count=len(keep),
        keep=keep,
        removed=removed,
        existing_source_count=len(existing),
    )
