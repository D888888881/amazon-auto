"""media 路径：用户目录与全局 MEDIA_ROOT 安全解析。"""
from pathlib import Path

from django.conf import settings


def media_root() -> Path:
    """文件库根目录：<MEDIA_ROOT>/file（与 Excel 浏览、下载等一致）。"""
    root = (Path(settings.MEDIA_ROOT).resolve() / 'file')
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_media_path_global(rel_path: str | None) -> Path | None:
    """
    解析 MEDIA_ROOT 下的绝对路径；rel 为空表示根目录。
    禁止 .. 与越出 MEDIA_ROOT。
    """
    root = media_root()
    if rel_path is None or str(rel_path).strip() == '':
        return root
    rel = str(rel_path).strip().replace('\\', '/')
    if rel.startswith('/') or '..' in rel.split('/'):
        return None
    parts = [p for p in rel.split('/') if p and p != '.']
    for p in parts:
        if p == '..':
            return None
    candidate = root
    for part in parts:
        candidate = candidate / part
    try:
        candidate = candidate.resolve()
    except OSError:
        return None
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def user_upload_root(user_id) -> Path:
    root = (Path(settings.MEDIA_ROOT) / 'uploads' / str(user_id)).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_media_path(user_id, rel_path: str) -> Path | None:
    """
    将相对路径解析为 uploads/<uid>/ 下的绝对路径；禁止 .. 与越界。
    rel_path 使用正斜杠，例如 pair_abc/data.xlsx 或 sub/folder/file.xlsx
    """
    root = user_upload_root(user_id)
    if rel_path is None:
        return root
    rel = str(rel_path).strip().replace('\\', '/')
    if rel.startswith('/') or '..' in rel.split('/'):
        return None
    parts = [p for p in rel.split('/') if p and p != '.']
    for p in parts:
        if p == '..':
            return None
    candidate = root
    for part in parts:
        candidate = candidate / part
    try:
        candidate = candidate.resolve()
    except OSError:
        return None
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def parent_rel(rel_path: str) -> str:
    if not rel_path or not str(rel_path).strip():
        return ''
    p = Path(str(rel_path).replace('\\', '/'))
    par = p.parent
    if str(par) in ('.', ''):
        return ''
    return str(par).replace('\\', '/')
