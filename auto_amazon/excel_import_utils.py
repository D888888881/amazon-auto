"""数据审核：ZIP/文件夹导入到 media/file，解析 ASIN 子目录。"""
from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

_ASIN = re.compile(r'^B0[A-Z0-9]{8}$', re.IGNORECASE)
# 作为路径段出现的 ASIN（用于 ZIP 内路径在任意前缀目录下的定位）
_ASIN_SEG_BOUND = re.compile(r'(?:^|/)(B0[A-Z0-9]{8})(?:/|$)', re.IGNORECASE)


def normalize_rel(rel: str) -> str:
    return str(rel or '').strip().replace('\\', '/').strip('/')


def target_rel_from_archive_path(archive_name: str) -> str | None:
    """
    从 zip 内路径或文件夹相对路径中，截取第一个 ASIN 段及其后路径。
    例：Outer/pack/B0XXXXXXXX/a.xlsx -> B0XXXXXXXX/a.xlsx
    例：文件夹/B0XXXXXXXX/portable bidet/a.xlsx -> B0XXXXXXXX/portable bidet/a.xlsx
    """
    n = normalize_rel(archive_name).replace('\\', '/')
    if not n:
        return None
    parts = [p for p in n.split('/') if p and p != '.']
    for i, p in enumerate(parts):
        seg = p.strip().upper()
        if _ASIN.match(seg):
            return '/'.join([seg] + [x.strip() for x in parts[i + 1 :]])
    # 兜底：部分压缩工具/编码下分段异常时，仍按「路径段中的 B0XXXXXXXX」定位
    m = _ASIN_SEG_BOUND.search(n)
    if not m:
        return None
    asin = m.group(1).upper()
    tail = n[m.end() :].lstrip('/')
    return f'{asin}/{tail}' if tail else asin


def open_zipfile_read(path: Path):
    """优先使用 UTF-8 元数据解码 ZIP 内路径（中文文件夹名等）。"""
    try:
        return zipfile.ZipFile(path, 'r', metadata_encoding='utf-8')
    except TypeError:
        return zipfile.ZipFile(path, 'r')


def is_safe_media_rel(rel: str) -> bool:
    r = normalize_rel(rel)
    if not r or '..' in r.split('/'):
        return False
    first = r.split('/')[0].strip().upper()
    return bool(_ASIN.match(first))


def list_zip_target_rels(zip_path: Path) -> tuple[list[str], list[str]]:
    """返回 (目标相对路径列表, 跳过的 zip 内路径说明)。"""
    targets: list[str] = []
    skipped: list[str] = []
    try:
        zf = open_zipfile_read(zip_path)
    except zipfile.BadZipFile as e:
        return [], [f'无效 ZIP：{e}']
    try:
        for info in zf.infolist():
            name = info.filename.replace('\\', '/')
            if info.is_dir() or name.endswith('/'):
                tr = target_rel_from_archive_path(name.rstrip('/'))
                if tr:
                    # 目录在提取时由文件创建；跳过纯目录条目避免重复
                    continue
                skipped.append(name)
                continue
            tr = target_rel_from_archive_path(name)
            if not tr or not is_safe_media_rel(tr):
                skipped.append(name)
                continue
            targets.append(tr)
    finally:
        zf.close()
    return sorted(set(targets)), skipped


def extract_zip_to_media_root(
    zip_path: Path,
    media_root: Path,
    *,
    skip_if_exists: bool = False,
) -> tuple[list[str], list[str]]:
    """
    将 zip 内文件解压到 media_root，仅允许落入 B0XXXXXXXX/... 下。
    返回 (已写入的相对路径列表, 因已存在而跳过的路径列表)（均为文件路径）。
    skip_if_exists 为 True 时：目标已存在则跳过该文件（不覆盖），其余照常写入。
    """
    written: list[str] = []
    skipped_existing: list[str] = []
    zf = open_zipfile_read(zip_path)
    try:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace('\\', '/')
            tr = target_rel_from_archive_path(name)
            if not tr or not is_safe_media_rel(tr):
                continue
            dest = media_root.joinpath(*tr.split('/'))
            if skip_if_exists and dest.exists():
                skipped_existing.append(tr)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, 'r') as src, open(dest, 'wb') as out:
                shutil.copyfileobj(src, out, length=1024 * 1024)
            written.append(tr)
    finally:
        zf.close()
    return written, skipped_existing


def ensure_dir_nodes_registered(rel_paths: list[str]) -> list[str]:
    """为文件路径补充父目录路径（去重），用于 ImportedMediaPath。"""
    out: set[str] = set()
    for r in rel_paths:
        r = normalize_rel(r)
        if not r:
            continue
        parts = r.split('/')
        for i in range(1, len(parts) + 1):
            out.add('/'.join(parts[:i]))
    return sorted(out)
