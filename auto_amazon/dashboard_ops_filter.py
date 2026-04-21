"""
ASIN 看板「运营难度」筛选：按运营难度 > 阈值 的区间（完全忽略「200以上」）从 data_origin 表导出匹配行。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from .media_paths import safe_media_path_global

OPS_FILTER_THRESHOLD = 10.0
DATA_ORIGIN_MARK = "data_origin"


def _safe_keyword_folder(name: str) -> bool:
    if not name or len(name) > 240:
        return False
    if ".." in name or "/" in name or "\\" in name:
        return False
    return True


def parse_ops_payload(payload: str) -> tuple[str | None, dict | None]:
    if not payload or not str(payload).strip():
        return None, None
    s = str(payload).strip()
    if not s.startswith("{"):
        return None, None
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(obj, dict) or not obj:
        return None, None
    kw = next(iter(obj.keys()))
    wrap = obj.get(kw)
    if not isinstance(wrap, dict):
        return None, None
    ri = wrap.get("review_interval")
    if not isinstance(ri, dict):
        return None, None
    return kw, ri


def _parse_ops_percent(raw) -> float | None:
    if raw is None:
        return None
    s = str(raw).replace("%", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _is_200_plus_label(label: str) -> bool:
    t = str(label).strip()
    return "200以上" in t or t.replace(" ", "") in ("200+", "200＋")


def interval_label_to_range(label: str) -> tuple[int, int] | None:
    """将「0-30」「31-50」等解析为 reviews 数量的闭区间 [lo, hi]；200以上返回 None。"""
    if _is_200_plus_label(label):
        return None
    m = re.match(r"^(\d+)\s*[-~～]\s*(\d+)$", str(label).strip())
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    lo, hi = min(a, b), max(a, b)
    return lo, hi


def selected_ranges_and_labels(
    review_interval: dict, threshold: float = OPS_FILTER_THRESHOLD
) -> tuple[list[tuple[int, int]], list[str]]:
    """运营难度 > threshold 且完全忽略「200以上」区间；返回 (reviews 闭区间列表, 对应区间文案列表)。"""
    labels = review_interval.get("区间") or []
    ops_vals = review_interval.get("运营难度") or []
    n = min(len(labels), len(ops_vals))
    ranges: list[tuple[int, int]] = []
    picked_labels: list[str] = []
    for i in range(n):
        label = labels[i]
        if _is_200_plus_label(label):
            continue
        pct = _parse_ops_percent(ops_vals[i])
        if pct is None or pct <= threshold:
            continue
        r = interval_label_to_range(str(label))
        if r:
            ranges.append(r)
            picked_labels.append(str(label).strip())
    return ranges, picked_labels


def _sales_levels_for_review_label(label: str) -> list[str]:
    """data_origin 中 sales_level 分箱可能与看板「区间」文案不一致时的别名。"""
    key = str(label).strip()
    aliases = {
        "0-30": ["0-30"],
        "31-50": ["31-50"],
        "51-100": ["51-100"],
        "101-150": ["101-150"],
        "151-200": ["151-200"],
    }
    return aliases.get(key, [key])


def find_data_origin_file(keyword_dir: Path, keyword: str) -> Path | None:
    if not keyword_dir.is_dir():
        return None
    exact = keyword_dir / f"{keyword}_data_origin.xlsx"
    if exact.is_file():
        return exact
    cands = [
        p
        for p in keyword_dir.iterdir()
        if p.is_file()
        and DATA_ORIGIN_MARK in p.name.lower()
        and p.suffix.lower() in (".xlsx", ".xlsm")
    ]
    if not cands:
        return None
    cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0]


def filter_dataframe_by_ops(
    df: pd.DataFrame,
    ranges: list[tuple[int, int]],
    interval_labels: list[str],
) -> pd.DataFrame:
    if df.empty or not ranges:
        return df.iloc[0:0].copy()

    if "reviews" in df.columns:
        rev = pd.to_numeric(df["reviews"], errors="coerce")
        mask = pd.Series(False, index=df.index)
        for lo, hi in ranges:
            mask |= (rev >= lo) & (rev <= hi)
        out = df.loc[mask].copy()
        if not out.empty:
            return out
        # 有 reviews 列且存在有效数值时，以数值区间为准（即使匹配行为 0）
        if rev.notna().any():
            return out

    if "sales_level" not in df.columns:
        return df.iloc[0:0].copy()

    levels: set[str] = set()
    for lb in interval_labels:
        for x in _sales_levels_for_review_label(lb):
            levels.add(x)
    sl = df["sales_level"].astype(str).str.strip()
    return df.loc[sl.isin(levels)].copy()


def run_dashboard_ops_filter(asin: str, ops_payload: str) -> tuple[bool, str]:
    """
    在 media/file/<asin>/<keyword>/ 下查找含 data_origin 的表，按运营难度>10%且忽略「200以上」区间过滤行，另存为新文件。
    返回 (ok, message)。
    """
    kw, ri = parse_ops_payload(ops_payload)
    if not kw or not ri:
        return False, "运营难度数据无效或为空，请先重新计算。"

    if not _safe_keyword_folder(kw):
        return False, "关键词目录名不合法。"

    ranges, selected_labels = selected_ranges_and_labels(ri, OPS_FILTER_THRESHOLD)
    if not ranges:
        return False, f"没有满足「运营难度 > {OPS_FILTER_THRESHOLD:g}%」且非「200以上」的区间，未生成文件。"

    rel = f"{asin}/{kw}".replace("\\", "/")
    base = safe_media_path_global(rel)
    if base is None:
        return False, "路径无效。"
    origin = find_data_origin_file(base, kw)
    if origin is None:
        return False, f"未找到含「{DATA_ORIGIN_MARK}」的数据文件：{rel}"

    try:
        df = pd.read_excel(origin, engine="openpyxl")
    except Exception as e:
        return False, f"读取数据文件失败：{e}"

    out_df = filter_dataframe_by_ops(df, ranges, selected_labels)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = f"{origin.stem}_ops_gt{int(OPS_FILTER_THRESHOLD)}_{ts}{origin.suffix}"
    out_path = origin.parent / out_name
    try:
        out_df.to_excel(out_path, index=False, engine="openpyxl")
    except Exception as e:
        return False, f"保存失败：{e}"

    rel_out = f"{asin}/{kw}/{out_name}".replace("\\", "/")
    return True, f"已生成 {len(out_df)} 行 → {rel_out}"
