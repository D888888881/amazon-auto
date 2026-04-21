"""ROI-US-pack.xlsx 在线重算：仅依据表内字段，不写外部接口。"""
from __future__ import annotations

import math
from typing import Any


def _cell_val(cell: Any) -> str:
    if isinstance(cell, dict):
        return str(cell.get('v', '') or '').strip()
    if cell is None:
        return ''
    return str(cell).strip()


def _parse_num(s: str) -> float | None:
    t = s.replace(',', '').replace('￥', '').replace('$', '').strip()
    if not t or t.upper() in ('N/A', 'NA', '-', '—'):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _fmt(v: float | None, nd: int = 2) -> str:
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return 'N/A'
    return f'{v:.{nd}f}'


# 三组表头生成的字段名（与 async_seller_wizard_api.save_roi_us_pack 一致）
_LEFT_KEYS = (
    '单件采购',
    '单件头程',
    '平台佣金',
    '退款率',
    'FBA配送',
    '最低售价',
    '产品售价',
    '优惠折扣',
    '折后价格',
    '实际利润',
    '销售回款',
    '实际成本',
    '投产比',
)
_MIDDLE_KEYS = (
    '广告预算',
    '广告cpc',
    '广告点击',
    '转化率',
    '月出单量',
    '出单量',
    '日利润1',
    '日利润2',
    '月利润1',
    '月利润2',
    '广告费占比',
)
_RIGHT_KEYS = (
    '总流量',
    '日自然流量',
    '每单需点击',
    '去广告投产',
    '每单利润',
    '采购总价格',
    '利润率',
    '去广告毛利率',
)
# 左侧第二处「平台佣金」与第一处同义，扫描时合并到同一键
_ALL_FIELD_NAMES = frozenset(_LEFT_KEYS + _MIDDLE_KEYS + _RIGHT_KEYS)


def _collect_field_cells(rows: list[list[Any]]) -> dict[str, list[tuple[int, int]]]:
    """返回 字段名 -> [(0-based 行, 0-based 值列), ...]。"""
    out: dict[str, list[tuple[int, int]]] = {}
    if not rows:
        return out
    for r in range(1, len(rows)):
        row = rows[r]
        if not isinstance(row, list):
            continue
        for base in (0, 3, 6):
            if len(row) <= base + 1:
                continue
            name = _cell_val(row[base])
            if name not in _ALL_FIELD_NAMES:
                continue
            key = '平台佣金' if name == '平台佣金' else name
            out.setdefault(key, []).append((r, base + 1))
    return out


def _read_inputs(rows: list[list[Any]], field_cells: dict[str, list[tuple[int, int]]]) -> dict[str, float | None]:
    """从「值」列读取当前表内数字（含用于推断汇率的日利润）。"""

    def first_val(key: str) -> float | None:
        for r, c in field_cells.get(key, ()):
            if r < len(rows):
                row = rows[r]
                if isinstance(row, list) and c < len(row):
                    return _parse_num(_cell_val(row[c]))
        return None

    raw: dict[str, float | None] = {}
    for key in (
        '单件采购',
        '单件头程',
        '平台佣金',
        '退款率',
        'FBA配送',
        '产品售价',
        '优惠折扣',
        '广告cpc',
        '转化率',
        '出单量',
        '日利润1',
        '日利润2',
        '投产比',
        '实际利润',
    ):
        raw[key] = first_val(key)
    return raw


def _infer_exchange(inp: dict[str, float | None]) -> float:
    d1 = inp.get('日利润1')
    d2 = inp.get('日利润2')
    if d1 is not None and d2 is not None and abs(d1) > 1e-9:
        ex = d2 / d1
        if ex > 0 and ex < 100:
            return ex
    ap = inp.get('实际利润')
    cost = inp.get('单件采购')
    hd = inp.get('单件头程')
    roi_disp = inp.get('投产比')
    if (
        ap is not None
        and abs(ap) > 1e-9
        and roi_disp is not None
        and cost is not None
        and hd is not None
    ):
        csum = cost + hd
        if csum > 0:
            ex = roi_disp * csum / (ap * 100)
            if ex > 0 and ex < 100:
                return ex
    return 7.2


def _set_field(
    rows: list[list[Any]],
    field_cells: dict[str, list[tuple[int, int]]],
    key: str,
    text: str,
) -> None:
    for r, c in field_cells.get(key, ()):
        if r >= len(rows):
            continue
        row = rows[r]
        if not isinstance(row, list) or c >= len(row):
            continue
        cell = row[c]
        if isinstance(cell, dict):
            cell['v'] = text
        else:
            row[c] = text


def recalc_roi_us_pack_rows(rows: list[list[Any]]) -> tuple[bool, str]:
    """
    就地重算 ROI-US-pack 网格（与 excel 编辑器相同的 rows 结构）。
    返回 (ok, error_message)。
    """
    if not rows or len(rows) < 2:
        return False, '表格数据不足'

    first = rows[0]
    if not isinstance(first, list) or len(first) < 9:
        return False, '不是标准的 ROI-US-pack 九列布局'

    field_cells = _collect_field_cells(rows)
    if not field_cells.get('单件采购'):
        return False, '未识别到 ROI-US-pack 字段列（缺少「单件采购」）'

    inp = _read_inputs(rows, field_cells)
    ex = _infer_exchange(inp)

    unit_p = inp['单件采购']
    head = inp['单件头程']
    comm = inp['平台佣金']
    refund_r = inp['退款率']
    fba = inp['FBA配送']
    price = inp['产品售价']
    disc_pct = inp['优惠折扣'] or 0.0
    ad_cpc = inp['广告cpc'] or 0.0
    conv_display = inp['转化率']
    daily_orders = inp['出单量']

    cost_cny = None
    if unit_p is not None and head is not None:
        cost_cny = unit_p + head

    conv_frac = None
    if conv_display is not None and conv_display > 0:
        conv_frac = conv_display / 100.0

    lowest = None
    if cost_cny is not None and ex > 0 and fba is not None and comm is not None and refund_r is not None:
        denom = 1.0 - (comm + refund_r) / 100.0
        if denom > 1e-9:
            lowest = (cost_cny / ex + fba) / denom

    disc_price = None
    if price is not None:
        disc_price = price * (1.0 - disc_pct / 100.0)

    sales_ret = act_profit = act_cost = None
    if (
        price is not None
        and disc_price is not None
        and refund_r is not None
        and comm is not None
        and fba is not None
        and cost_cny is not None
        and ex > 0
    ):
        refund_amt = price * (refund_r / 100.0)
        comm_amt = disc_price * (comm / 100.0)
        sales_ret = disc_price - refund_amt - comm_amt - fba
        cost_usd = cost_cny / ex
        act_profit = sales_ret - cost_usd
        act_cost = disc_price - act_profit

    roi_disp = None
    if act_profit is not None and cost_cny is not None and cost_cny > 1e-9:
        roi_disp = (act_profit * ex / cost_cny) * 100.0

    total_traffic = ad_clicks = nat = ad_budget = None
    if daily_orders is not None and conv_frac is not None and conv_frac > 1e-9:
        total_traffic = daily_orders / conv_frac
        ad_clicks = total_traffic / 2.0
        nat = total_traffic / 2.0
        if ad_cpc > 0:
            ad_budget = ad_clicks * ad_cpc
        else:
            ad_budget = 0.0

    clicks_per_order = None
    if conv_display is not None and conv_display > 1e-9:
        clicks_per_order = 100.0 / conv_display

    daily_p1 = daily_p2 = mp1 = mp2 = None
    if act_profit is not None and daily_orders is not None and ad_budget is not None:
        daily_p1 = act_profit * daily_orders - ad_budget
        daily_p2 = daily_p1 * ex
        mp1 = daily_p1 * 30.0
        mp2 = daily_p2 * 30.0

    ad_ratio = None
    if (
        ad_budget is not None
        and disc_price is not None
        and disc_price > 1e-9
        and daily_orders is not None
        and daily_orders > 1e-9
    ):
        ad_ratio = ad_budget / (disc_price * daily_orders) * 100.0

    ad_removed = None
    if (
        daily_p1 is not None
        and cost_cny is not None
        and cost_cny > 1e-9
        and daily_orders is not None
        and daily_orders > 1e-9
    ):
        ad_removed = daily_p1 * ex / (cost_cny * daily_orders) * 100.0

    ppo = None
    if daily_p2 is not None and daily_orders is not None and daily_orders > 1e-9:
        ppo = daily_p2 / daily_orders

    pm = None
    if act_profit is not None and disc_price is not None and disc_price > 1e-9:
        pm = act_profit / disc_price * 100.0

    ad_gross = None
    if pm is not None and ad_ratio is not None:
        ad_gross = pm - ad_ratio

    monthly_vol = None
    if daily_orders is not None:
        monthly_vol = daily_orders * 30.0

    _set_field(rows, field_cells, '最低售价', _fmt(lowest))
    _set_field(rows, field_cells, '折后价格', _fmt(disc_price))
    _set_field(rows, field_cells, '实际利润', _fmt(act_profit))
    _set_field(rows, field_cells, '销售回款', _fmt(sales_ret))
    _set_field(rows, field_cells, '实际成本', _fmt(act_cost))
    _set_field(rows, field_cells, '投产比', _fmt(roi_disp))

    _set_field(rows, field_cells, '广告预算', _fmt(ad_budget))
    _set_field(rows, field_cells, '广告点击', _fmt(ad_clicks))
    _set_field(rows, field_cells, '月出单量', _fmt(monthly_vol))
    _set_field(rows, field_cells, '日利润1', _fmt(daily_p1))
    _set_field(rows, field_cells, '日利润2', _fmt(daily_p2))
    _set_field(rows, field_cells, '月利润1', _fmt(mp1))
    _set_field(rows, field_cells, '月利润2', _fmt(mp2))
    _set_field(rows, field_cells, '广告费占比', _fmt(ad_ratio))

    _set_field(rows, field_cells, '总流量', _fmt(total_traffic))
    _set_field(rows, field_cells, '日自然流量', _fmt(nat))
    _set_field(rows, field_cells, '每单需点击', _fmt(clicks_per_order))
    _set_field(rows, field_cells, '去广告投产', _fmt(ad_removed))
    _set_field(rows, field_cells, '每单利润', _fmt(ppo))
    _set_field(rows, field_cells, '采购总价格', _fmt(cost_cny))
    _set_field(rows, field_cells, '利润率', _fmt(pm))
    _set_field(rows, field_cells, '去广告毛利率', _fmt(ad_gross))

    return True, ''


def is_roi_us_pack_filename(name: str) -> bool:
    n = (name or '').lower()
    return 'roi-us-pack' in n and n.endswith('.xlsx')
