"""ZIP 分片上传到临时目录，供导入冲突检测与确认解压。"""
from __future__ import annotations

import json
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path

from django.conf import settings

MAX_IMPORT_BYTES = int(getattr(settings, 'EXCEL_IMPORT_MAX_BYTES', 550 * 1024 * 1024))


def staging_dir_for(user_id: int, staging_id: str) -> Path:
    # 分片临时文件放在系统临时目录，避免占用 media/file 业务目录空间。
    base = Path(tempfile.gettempdir()) / 'auto_amazon_excel_import_staging'
    p = base.resolve() / str(user_id) / staging_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _meta_path(sdir: Path) -> Path:
    return sdir / 'meta.json'


def load_meta(sdir: Path) -> dict | None:
    mp = _meta_path(sdir)
    if not mp.is_file():
        return None
    try:
        return json.loads(mp.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return None


def save_meta(sdir: Path, meta: dict) -> None:
    _meta_path(sdir).write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')


def init_or_resume_staging(user_id: int, staging_id: str | None, total_chunks: int) -> tuple[Path, dict]:
    sid = (staging_id or '').strip() or str(uuid.uuid4())
    sdir = staging_dir_for(user_id, sid)
    meta = load_meta(sdir)
    if meta is None:
        meta = {
            'user_id': user_id,
            'staging_id': sid,
            'next_chunk': 0,
            'total_chunks': int(total_chunks),
            'bytes_written': 0,
            'status': 'uploading',
        }
        save_meta(sdir, meta)
    elif int(meta.get('total_chunks', 0)) != int(total_chunks):
        raise ValueError('total_chunks 与已存在 staging 不一致')
    return sdir, meta


def append_chunk(
    user_id: int,
    staging_id: str | None,
    chunk_index: int,
    total_chunks: int,
    chunk_bytes: bytes,
) -> tuple[str, dict]:
    """写入分片；完成时生成 upload.zip 并写入 meta['conflicts']。"""
    from .excel_import_utils import list_zip_target_rels

    sdir, meta = init_or_resume_staging(user_id, staging_id, total_chunks)
    if int(meta.get('user_id')) != int(user_id):
        raise PermissionError('staging 不属于当前用户')
    if meta.get('status') == 'ready':
        return meta['staging_id'], meta

    tc = int(meta['total_chunks'])
    if tc != int(total_chunks):
        raise ValueError('total_chunks 与已存在 staging 不一致')
    if chunk_index != int(meta['next_chunk']):
        raise ValueError(f'请按顺序上传分片，期望 {meta["next_chunk"]}，收到 {chunk_index}')
    if chunk_index < 0 or tc <= 0 or chunk_index >= tc:
        raise ValueError('分片索引无效')

    new_bytes = int(meta['bytes_written']) + len(chunk_bytes)
    if new_bytes > MAX_IMPORT_BYTES:
        raise ValueError(f'文件过大（上限 {MAX_IMPORT_BYTES // (1024 * 1024)} MB）')

    bin_path = sdir / 'upload.bin'
    with open(bin_path, 'ab') as f:
        f.write(chunk_bytes)

    meta['bytes_written'] = new_bytes
    meta['next_chunk'] = chunk_index + 1

    if meta['next_chunk'] >= tc:
        zip_path = sdir / 'upload.zip'
        if bin_path.exists():
            bin_path.rename(zip_path)
        if not zipfile.is_zipfile(zip_path):
            meta['status'] = 'error'
            meta['error'] = '上传完成后不是有效的 ZIP 文件'
            save_meta(sdir, meta)
            raise ValueError(meta['error'])

        targets, _skipped = list_zip_target_rels(zip_path)
        if not targets:
            meta['status'] = 'error'
            meta['error'] = 'ZIP 中未找到符合 B0XXXXXXXX 的 ASIN 路径（请确认压缩包内包含 ASIN 文件夹）'
            save_meta(sdir, meta)
            raise ValueError(meta['error'])
        from .media_paths import media_root as _media_root_fn

        _mr = _media_root_fn()
        conflicts = compute_conflicts(_mr, targets)
        meta['status'] = 'ready'
        meta['target_paths'] = targets
        meta['file_count'] = len(targets)
        meta['conflicts'] = conflicts
        save_meta(sdir, meta)
        return meta['staging_id'], meta

    save_meta(sdir, meta)
    return meta['staging_id'], meta


def load_ready_staging(user_id: int, staging_id: str) -> tuple[Path, dict]:
    sdir = staging_dir_for(user_id, staging_id)
    meta = load_meta(sdir)
    if not meta or meta.get('status') != 'ready':
        raise ValueError('staging 未就绪或已失效')
    if int(meta.get('user_id')) != int(user_id):
        raise PermissionError('staging 不属于当前用户')
    zp = sdir / 'upload.zip'
    if not zp.is_file():
        raise FileNotFoundError('上传文件缺失')
    return sdir, meta


def compute_conflicts(media_root: Path, target_rels: list[str]) -> list[str]:
    conflicts: list[str] = []
    for tr in target_rels:
        p = media_root.joinpath(*tr.split('/'))
        if p.exists():
            conflicts.append(tr)
    return sorted(set(conflicts))


def refresh_conflicts_in_meta(media_root: Path, sdir: Path, meta: dict) -> list[str]:
    targets = meta.get('target_paths') or []
    c = compute_conflicts(media_root, targets)
    meta['conflicts'] = c
    save_meta(sdir, meta)
    return c


def cleanup_staging_dir(sdir: Path) -> None:
    try:
        shutil.rmtree(sdir, ignore_errors=True)
    except OSError:
        pass
