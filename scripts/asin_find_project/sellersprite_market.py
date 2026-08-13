"""卖家精灵站点参数映射（market / marketId / station 分接口使用）。

实测（relation/ta/source、fba-calculator、competing-lookup）：
- marketId：US=1，UK=3（注意不是 2；2 会导致 FBA 静默回落美国站）
- 广告反查 market：US=COM，UK=UK（CO.UK 会被忽略并回落美国站）
- competing-lookup market：US / UK
- cookie module-station-market-research：US / UK
"""
from __future__ import annotations

from contextvars import ContextVar, Token

_VALID = frozenset({'US', 'UK'})
_current: ContextVar[str] = ContextVar('sellersprite_marketplace', default='US')

# 数值 marketId：FBA 计算器、市场调研、referer 等
_MARKET_ID = {'US': '1', 'UK': '3'}
# cookie module-station-market-research
_STATION = {'US': 'US', 'UK': 'UK'}
# relation/ta/source：US 用 COM，UK 必须用 UK（不是 CO.UK）
_MARKET_SOURCE = {'US': 'COM', 'UK': 'UK'}
# competing-lookup 等 JSON body 的 market：US / UK
_MARKET_CODE = {'US': 'US', 'UK': 'UK'}
_AMAZON_HOST = {'US': 'www.amazon.com', 'UK': 'www.amazon.co.uk'}


def normalize_sellersprite_marketplace(code: str | None) -> str:
    c = str(code or 'US').strip().upper()
    return c if c in _VALID else 'US'


def set_sellersprite_marketplace(marketplace: str | None) -> Token:
    return _current.set(normalize_sellersprite_marketplace(marketplace))


def reset_sellersprite_marketplace(token: Token) -> None:
    _current.reset(token)


def get_sellersprite_marketplace() -> str:
    return normalize_sellersprite_marketplace(_current.get())


def sellersprite_market_id(marketplace: str | None = None) -> str:
    """FBA / market-research / referer 用的数字 marketId。"""
    mp = normalize_sellersprite_marketplace(marketplace or get_sellersprite_marketplace())
    return _MARKET_ID[mp]


def sellersprite_market_id_int(marketplace: str | None = None) -> int:
    return int(sellersprite_market_id(marketplace))


def sellersprite_station(marketplace: str | None = None) -> str:
    """cookie：module-station-market-research。"""
    mp = normalize_sellersprite_marketplace(marketplace or get_sellersprite_marketplace())
    return _STATION[mp]


def sellersprite_market_com(marketplace: str | None = None) -> str:
    """relation/ta/source 查询参数 market：US→COM，UK→UK。"""
    mp = normalize_sellersprite_marketplace(marketplace or get_sellersprite_marketplace())
    return _MARKET_SOURCE[mp]


def sellersprite_market_code(marketplace: str | None = None) -> str:
    """competing-lookup 等 JSON body 的 market：US / UK。"""
    mp = normalize_sellersprite_marketplace(marketplace or get_sellersprite_marketplace())
    return _MARKET_CODE[mp]


def sellersprite_amazon_host(marketplace: str | None = None) -> str:
    mp = normalize_sellersprite_marketplace(marketplace or get_sellersprite_marketplace())
    return _AMAZON_HOST[mp]


def sellersprite_amazon_dp_url(asin: str, marketplace: str | None = None) -> str:
    host = sellersprite_amazon_host(marketplace)
    a = str(asin or '').strip().upper()
    return f'https://{host}/dp/{a}'


def sellersprite_reversing_referer(asin: str = '', marketplace: str | None = None) -> str:
    mid = sellersprite_market_id(marketplace)
    a = str(asin or '').strip().upper() or 'B000000000'
    return (
        f'https://www.sellersprite.com/v3/reversing/sources'
        f'?asin={a}&marketId={mid}&date='
    )


def apply_sellersprite_station_cookie(cookies: dict, marketplace: str | None = None) -> None:
    """写入/覆盖站点 cookie，供市场调研与 FBA 等页面态接口使用。"""
    if not isinstance(cookies, dict):
        return
    cookies['module-station-market-research'] = sellersprite_station(marketplace)


def response_matches_sellersprite_marketplace(
    payload: dict | None,
    marketplace: str | None = None,
    *,
    market_id_keys: tuple[str, ...] = ('marketId',),
) -> bool:
    """
    校验响应是否属于目标站点，避免错误 market 参数或服务端回落导致串站。
    支持扁平字段，或 FBA 的 taskStation.marketId / publicCode。
    """
    if not isinstance(payload, dict):
        return False
    mp = normalize_sellersprite_marketplace(marketplace or get_sellersprite_marketplace())
    want = sellersprite_market_id_int(mp)

    candidates: list = []
    for key in market_id_keys:
        if key in payload and payload.get(key) is not None:
            candidates.append(payload.get(key))
    ts = payload.get('taskStation')
    if isinstance(ts, dict):
        if ts.get('marketId') is not None:
            candidates.append(ts.get('marketId'))
        pub = str(ts.get('publicCode') or '').strip().upper()
        if pub:
            return pub == mp
        code = str(ts.get('code') or '').strip().upper()
        if code in ('COM', 'US') and mp == 'US':
            return True
        if code in ('UK', 'CO.UK') and mp == 'UK':
            return True

    for raw in candidates:
        try:
            if int(raw) == want:
                return True
        except (TypeError, ValueError):
            continue
    # 无站点字段时不做误杀（部分接口不回 marketId）
    return not candidates and not isinstance(ts, dict)
