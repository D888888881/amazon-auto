"""Search 表行恢复到 data_origin：列名映射与 sales_level 计算（与 seller_wizard 清洗逻辑对齐）。"""
from __future__ import annotations

import math
from typing import Any

# 与 scripts/asin_find_project/async_seller_wizard_api.COLUMN_MAPPING_EXCEL_TO_API 保持一致
COLUMN_MAPPING_EXCEL_TO_API: dict[str, str] = {
    'ASIN': 'asin',
    '父ASIN': 'parent',
    'SKU': 'sku',
    '品牌': 'brand',
    '品牌链接': 'brandUrl',
    '搜索排名': 'lqs',
    '商品标题': 'title',
    '商品详情页链接': 'asinUrl',
    '商品主图': 'imageUrl',
    '类目路径': 'nodeLabelPath',
    '节点标签路径': 'nodeLabelPath',
    '节点路径': 'nodeLabelPath',
    '大类目': 'categoryName',
    '大类BSR': 'bsrRank',
    '小类目': 'bsrLabel',
    '小类BSR': 'subcategories',
    '月销量': 'totalUnits',
    '月销量增长率': 'totalUnitsGrowth',
    '月销售额($)': 'totalAmount',
    '子体销量': 'fbaUnits',
    '子体销售额($)': 'fbaAmount',
    '变体数': 'variations',
    '价格($)': 'price',
    'Prime价格($)': 'primeExclusivePrice',
    'Coupon': 'coupon',
    'Q&A数': 'questions',
    '评分数': 'reviews',
    '月新增评分数': 'reviewsIncreasement',
    '评分': 'rating',
    '留评率': 'reviewsRate',
    'FBA($)': 'fba',
    '毛利率': 'profit',
    '上架时间': 'availableDate',
    '上架天数': 'availableDays',
    'LQS': 'lqs',
    '卖家数': 'sellers',
    'Best Seller标识': 'bestSeller',
    "Amazon's Choice": 'amazonChoice',
    'New Release标识': 'newRelease',
    '商品重量': 'weight',
    '商品尺寸': 'dimensions',
    '包装重量': 'pkgWeight',
    '包装尺寸': 'pkgDimensions',
    '图片链接': 'imageUrl',
}

_SALES_BINS = (0, 30, 60, 100, 150, 200)
_SALES_LABELS = ('0-30', '31-50', '51-100', '101-150', '151-200', '200以上')


def _norm_header(h: Any) -> str:
    return str(h or '').strip()


def _cell_str(v: Any) -> str:
    if v is None:
        return ''
    s = str(v).strip()
    if s.lower() in ('nan', 'none'):
        return ''
    return s


def _parse_float(v: Any) -> float | None:
    s = _cell_str(v).replace(',', '')
    if not s or s.upper() in ('N/A', 'NA', '-', '—'):
        return None
    try:
        n = float(s)
        if math.isnan(n) or math.isinf(n):
            return None
        return n
    except (TypeError, ValueError):
        return None


def search_row_to_api_record(search_header: list[str], search_row: list[str]) -> dict[str, str]:
    """Search 表一行 → API 字段 dict（与 normalize_excel_dataframe 一致）。"""
    record: dict[str, str] = {}
    for i, raw_h in enumerate(search_header):
        h = _norm_header(raw_h)
        if not h:
            continue
        api_key = COLUMN_MAPPING_EXCEL_TO_API.get(h, h)
        val = _cell_str(search_row[i] if i < len(search_row) else '')
        if api_key not in record or not record[api_key]:
            record[api_key] = val
    return record


def compute_sales_level(reviews_val: Any) -> str:
    n = _parse_float(reviews_val)
    if n is None:
        return ''
    for idx, upper in enumerate(_SALES_BINS[1:]):
        if n <= upper:
            return _SALES_LABELS[idx]
    return _SALES_LABELS[-1]


def build_origin_row_from_search(
    search_header: list[str],
    search_row: list[str],
    origin_header: list[str],
) -> list[str]:
    """按 data_origin 表头顺序，从 Search 行生成完整数据行。"""
    record = search_row_to_api_record(search_header, search_row)

    if not record.get('sales_level'):
        sl = compute_sales_level(record.get('reviews'))
        if sl:
            record['sales_level'] = sl

    # 小写键索引，便于与 origin 英文字段匹配
    lower_index: dict[str, str] = {}
    for k, v in record.items():
        lk = str(k).strip().lower()
        if lk and (lk not in lower_index or not lower_index[lk]):
            lower_index[lk] = v

    out: list[str] = []
    for oh in origin_header:
        key = _norm_header(oh)
        if not key:
            out.append('')
            continue
        val = record.get(key)
        if val in (None, ''):
            val = lower_index.get(key.lower(), '')
        out.append(_cell_str(val))
    return out
