"""数据审核：ZIP/文件夹导入到 media/file，解析 ASIN 子目录。"""
from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

_ASIN = re.compile(r'^B0[A-Z0-9]{8}$', re.IGNORECASE)
# 作为路径段出现的 ASIN（用于 ZIP 内路径在任意前缀目录下的定位）
_ASIN_SEG_BOUND = re.compile(r'(?:^|/)(B0[A-Z0-9]{8})(?:/|$)', re.IGNORECASE)

# cp437 可解码任意字节；B0 ASIN 为 ASCII，中文包通常一次即可识别
_ZIP_FAST_ENCODINGS: tuple[str | None, ...] = ('cp437', 'latin1')
_ZIP_SLOW_ENCODINGS: tuple[str | None, ...] = (None, 'gbk', 'cp936', 'utf-8')


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
    m = _ASIN_SEG_BOUND.search(n)
    if not m:
        return None
    asin = m.group(1).upper()
    tail = n[m.end() :].lstrip('/')
    return f'{asin}/{tail}' if tail else asin


def is_safe_media_rel(rel: str) -> bool:
    r = normalize_rel(rel)
    if not r or '..' in r.split('/'):
        return False
    first = r.split('/')[0].strip().upper()
    return bool(_ASIN.match(first))


def _zip_entry_name(info: zipfile.ZipInfo) -> str | None:
    try:
        return info.filename.replace('\\', '/')
    except (UnicodeDecodeError, UnicodeError):
        return None


def _entry_target_rel(info: zipfile.ZipInfo) -> str | None:
    name = _zip_entry_name(info)
    if not name:
        return None
    if info.is_dir() or name.endswith('/'):
        return target_rel_from_archive_path(name.rstrip('/'))
    tr = target_rel_from_archive_path(name)
    if tr and is_safe_media_rel(tr):
        return tr
    return None


def _open_zip_with_encoding(path: Path, enc: str | None) -> zipfile.ZipFile:
    if enc is None:
        return zipfile.ZipFile(path, 'r')
    try:
        return zipfile.ZipFile(path, 'r', metadata_encoding=enc)
    except TypeError:
        return zipfile.ZipFile(path, 'r')


def _zip_has_asin_target(zf: zipfile.ZipFile) -> bool:
    for info in zf.infolist():
        if _entry_target_rel(info):
            return True
    return False


def _try_open_for_asin_paths(path: Path, enc: str | None) -> zipfile.ZipFile | None:
    try:
        zf = _open_zip_with_encoding(path, enc)
    except zipfile.BadZipFile:
        raise
    except (UnicodeDecodeError, UnicodeError):
        return None
    try:
        if _zip_has_asin_target(zf):
            return zf
    except (UnicodeDecodeError, UnicodeError):
        zf.close()
        return None
    zf.close()
    return None


def open_zipfile_read(path: Path) -> zipfile.ZipFile:
    """
    选择可解析 ASIN 路径的 ZIP 文件名编码。
    先走 cp437 快路径（找到即返回），避免对大 ZIP 重复全量扫描导致 HTTP 超时。
    """
    for enc in _ZIP_FAST_ENCODINGS:
        zf = _try_open_for_asin_paths(path, enc)
        if zf is not None:
            return zf
    for enc in _ZIP_SLOW_ENCODINGS:
        zf = _try_open_for_asin_paths(path, enc)
        if zf is not None:
            return zf
    return _open_zip_with_encoding(path, 'cp437')


def list_zip_target_rels(zip_path: Path) -> tuple[list[str], list[str]]:
    """返回 (目标相对路径列表, 跳过的 zip 内路径说明)。"""
    targets: list[str] = []
    skipped: list[str] = []
    try:
        zf = open_zipfile_read(zip_path)
    except zipfile.BadZipFile as e:
        return [], [f'无效 ZIP：{e}']
    except (UnicodeDecodeError, UnicodeError) as e:
        return [], [f'ZIP 内文件名编码无法识别：{e}']
    try:
        for info in zf.infolist():
            name = _zip_entry_name(info)
            if not name:
                skipped.append('<decode-error>')
                continue
            if info.is_dir() or name.endswith('/'):
                tr = target_rel_from_archive_path(name.rstrip('/'))
                if tr:
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
    """
    written: list[str] = []
    skipped_existing: list[str] = []
    zf = open_zipfile_read(zip_path)
    try:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = _zip_entry_name(info)
            if not name:
                continue
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
