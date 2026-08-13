import asyncio
import os
import re

import aiohttp
from lxml import html
from typing import Optional

from seller_account_guard import apply_login_config, apply_login_headers, ensure_seller_login
from sellersprite_market import (
    apply_sellersprite_station_cookie,
    get_sellersprite_marketplace,
    normalize_sellersprite_marketplace,
    sellersprite_market_id,
)


# ---------- 默认配置 ----------
headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "cache-control": "max-age=0",
    "content-type": "application/x-www-form-urlencoded",
    "origin": "https://www.sellersprite.com",
    "priority": "u=0, i",
    "referer": "https://www.sellersprite.com/v2/market-research",
    "sec-ch-ua": "\"Not:A-Brand\";v=\"99\", \"Microsoft Edge\";v=\"145\", \"Chromium\";v=\"145\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0"
}
cookies = {
    "module-table-market-research": "bsr_sales_nearly",
    "module-station-market-research": "US",
    "ecookie": "a8LU6D5cNXDX9r2v_CN",
    "current_guest": "22Kde9qAjlvY_260313-115007",
    "_ga": "GA1.1.1415896636.1773372235",
    "_gcl_au": "1.1.1596383600.1773372235",
    "MEIQIA_TRACK_ID": "3AsDAuhuMQUzdUXTUNdrluZiyhZ",
    "MEIQIA_VISIT_ID": "3AsDAy4Ce2FXqZL4GNp0dmSGTLc",
    "Hm_lvt_e0dfc78949a2d7c553713cb5c573a486": "1773476579",
    "HMACCOUNT": "1B0FE40093B498DF",
    "_fp": "982da2ff9374239947902667704f94ef",
    "9442b23c7673059494ce": "921969ad3a72cb2a1e2fe3584a40b3df",
    "p_c_size": "50",
    "o_size": "50",
    "t_size": "50",
    "t_order_field": "created_time",
    "t_order_flag": "2",
    "k_size": "50",
    "_clck": "1mue9jd%5E2%5Eg4o%5E0%5E2263",
    "ed595165cfd1f6bc8683": "8762d661a83e7bba47b3d544b203a973",
    "_gaf_fp": "446d18f8171dc955925786036784aa71",
    "rank-login-user": 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
    "rank-login-user-info": 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
    "Sprite-X-Token": "",
    "ao_lo_to_n": "",
    "JSESSIONID": "",
    "_ga_CN0F80S6GL": "GS2.1.s1774509573$o29$g1$t1774509843$j60$l0$h0",
    "Hm_lpvt_e0dfc78949a2d7c553713cb5c573a486": "1774509844",
    "_clsk": "1tig1ea%5E1774509845396%5E7%5E1%5Ei.clarity.ms%2Fcollect",
    "_ga_38NCVF2XST": "GS2.1.s1774509573$o39$g1$t1774509928$j60$l0$h1584007809"
}
BASE_URL = "https://www.sellersprite.com/v2/market-research"
DEFAULT_MONTH_NAME = os.environ.get(
    'SELLER_MARKET_RESEARCH_MONTH',
    'bsr_sales_nearly',
)
FALLBACK_MONTH_NAMES = (
    'bsr_sales_nearly',
    'bsr_sales_monthly_202601',
    'bsr_sales_monthly_202512',
)


def _normalize_rate_text(raw: str) -> str:
    text = str(raw or '').replace('%', '').strip()
    if not text:
        return ''
    m = re.search(r'(\d+(?:\.\d+)?)', text)
    return m.group(1) if m else ''


def _looks_like_login_page(html_content: str) -> bool:
    lowered = (html_content or '').lower()
    return (
        'user/signin' in lowered
        or 'name="password"' in lowered
        or 'rank-login-user' in lowered and 'table-condition-search' not in lowered
    )


def _category_keyword_variants(path: str) -> list[str]:
    """同一路径的多种写法 + 上级类目回落。"""
    path = (path or '').strip()
    if not path:
        return []

    variants: list[str] = []
    seen: set[str] = set()

    def add(p: str) -> None:
        p = (p or '').strip()
        if p and p not in seen:
            seen.add(p)
            variants.append(p)

    add(path)
    if "'" in path:
        add(path.replace("'", "\u2019"))  # ’
        add(path.replace("'", "`"))
    if '&' in path:
        add(path.replace('&', 'and'))

    parts = path.split(':')
    while len(parts) > 1:
        parts = parts[:-1]
        add(':'.join(parts))

    return variants


def extract_table_value(html_content: str) -> str:
    """
    从 SellerSprite 市场调研 HTML 提取退款率/退货率。
    优先按表头定位列，再回退到历史 XPath / 首行百分比扫描。
    """
    if not html_content or _looks_like_login_page(html_content):
        return ''
    if 'table-condition-search' not in html_content:
        return ''

    tree = html.fromstring(html_content)
    table = tree.xpath('//*[@id="table-condition-search"]')
    if not table:
        return ''

    header_cells = table[0].xpath('.//thead//th')
    target_idx = None
    for idx, th in enumerate(header_cells, start=1):
        label = ''.join(th.itertext()).strip()
        lowered = label.lower()
        if (
            '退款' in label
            or '退货' in label
            or 'return rate' in lowered
            or 'refund rate' in lowered
            or (('return' in lowered or 'refund' in lowered) and 'rate' in lowered)
        ):
            target_idx = idx
            break

    row_cells = table[0].xpath('.//tbody/tr[1]/td')
    if not row_cells:
        return ''

    candidates: list[str] = []
    if target_idx and target_idx <= len(row_cells):
        candidates.append(''.join(row_cells[target_idx - 1].itertext()))

    legacy = tree.xpath(
        '//*[@id="table-condition-search"]/tbody/tr[1]/td[14]//text()'
    )
    if legacy:
        candidates.append(''.join(legacy))

    # 首行中带 % 的单元格（表头改版时的兜底）
    for td in row_cells:
        text = ''.join(td.itertext()).strip()
        if '%' in text:
            candidates.append(text)

    for raw in candidates:
        val = _normalize_rate_text(raw)
        if val:
            try:
                num = float(val)
                if 0 < num < 100:
                    return val
            except ValueError:
                continue
    return ''


async def fetch_market_research(
    session: Optional[aiohttp.ClientSession] = None,
    market_id: str | None = None,
    department_keyword: str = "Health & Household:Health Care:Over-the-Counter Medication:Pain Relievers:Hot & Cold Therapies:Heating Pads",
    topn: str = "10",
    new_release_num: str = "6",
    order_field: str = "total_sales",
    order_desc: str = "true",
    tab: str = "1",
    month_name: str | None = None,
    *,
    marketplace: str | None = None,
    **extra_data
) -> str:
    mp = normalize_sellersprite_marketplace(marketplace or get_sellersprite_marketplace())
    if market_id is None:
        market_id = sellersprite_market_id(mp)
    month_name = month_name or DEFAULT_MONTH_NAME
    data = {
        "marketId": market_id,
        "nodeIdPath": "",
        "sampleNumber": "1",
        "topn": topn,
        "newReleaseNum": new_release_num,
        "order.field": order_field,
        "order.desc": order_desc,
        "tab": tab,
        "monthName": month_name,
        "newReleaseNumSelect": new_release_num,
        "topNSelect": topn,
        "departmentKeyword": department_keyword,
        "minAvgSales": "",
        "maxAvgSales": "",
        "minAvgBsr": "",
        "maxAvgBsr": "",
        "minAvgWeight": "",
        "maxAvgWeight": "",
        "minHeadListingAvgBsr": "",
        "maxHeadListingAvgBsr": "",
        "minTotalProducts": "",
        "maxTotalProducts": "",
        "minAvgRevenue": "",
        "maxAvgRevenue": "",
        "minAvgPrice": "",
        "maxAvgPrice": "",
        "minAvgVolume": "",
        "maxAvgVolume": "",
        "minHeadListingAvgSales": "",
        "maxHeadListingAvgSales": "",
        "minAvgReviews": "",
        "maxAvgReviews": "",
        "minAvgRating": "",
        "maxAvgRating": "",
        "minAvgProfit": "",
        "maxAvgProfit": "",
        "minHeadListingAvgRevenue": "",
        "maxHeadListingAvgRevenue": "",
        "minBrands": "",
        "maxBrands": "",
        "minHeadListingProductCrn": "",
        "maxHeadListingProductCrn": "",
        "minEbcRatio": "",
        "maxEbcRatio": "",
        "minAmzRatio": "",
        "maxAmzRatio": "",
        "minSellers": "",
        "maxSellers": "",
        "minHeadListingBrandCrn": "",
        "maxHeadListingBrandCrn": "",
        "minFbaRatio": "",
        "maxFbaRatio": "",
        "sellerNations": "",
        "minAvgSellers": "",
        "maxAvgSellers": "",
        "minHeadListingSellerCrn": "",
        "maxHeadListingSellerCrn": "",
        "minFbmRatio": "",
        "maxFbmRatio": "",
        "minNewRatio": "",
        "maxNewRatio": "",
        "minNewAvgPrice": "",
        "maxNewAvgPrice": "",
        "minNewAvgRevenue": "",
        "maxNewAvgRevenue": "",
        "minNewCount": "",
        "maxNewCount": "",
        "minNewAvgRating": "",
        "maxNewAvgRating": "",
        "minNewAvgReviews": "",
        "maxNewAvgReviews": "",
        "minNewAvgSales": "",
        "maxNewAvgSales": "",
        **extra_data
    }

    async def _request(sess: aiohttp.ClientSession) -> str:
        async with sess.post(BASE_URL, data=data) as resp:
            return await resp.text()

    if session:
        return await _request(session)
    async with aiohttp.ClientSession(headers=headers, cookies=cookies) as new_session:
        return await _request(new_session)


async def fetch_refund_rate_for_path(
    department_keyword: str,
    session: aiohttp.ClientSession | None = None,
    *,
    marketplace: str | None = None,
) -> str:
    """
    拉取类目退款率；尝试路径变体、上级类目、多种 monthName。
    失败返回空字符串，不抛异常。
    """
    mp = normalize_sellersprite_marketplace(marketplace or get_sellersprite_marketplace())
    keywords = _category_keyword_variants(department_keyword)
    if not keywords:
        return ''

    owns_session = session is None
    if owns_session:
        config = await ensure_seller_login()
        apply_login_config(cookies, config)
        apply_sellersprite_station_cookie(cookies, mp)
        req_headers = dict(headers)
        apply_login_headers(req_headers, config)
        session = aiohttp.ClientSession(headers=req_headers, cookies=cookies)

    assert session is not None
    try:
        for kw in keywords:
            for month_name in FALLBACK_MONTH_NAMES:
                html_text = await fetch_market_research(
                    session=session,
                    department_keyword=kw,
                    month_name=month_name,
                    marketplace=mp,
                )
                target_value = extract_table_value(html_text)
                if target_value:
                    if kw != department_keyword.strip():
                        print(f'退款率回落成功: {department_keyword[:50]}… -> {kw[:50]}…')
                    return target_value
                if os.environ.get('ROI_DEBUG_REFUND_HTML') == '1':
                    snippet = (html_text or '')[:500].replace('\n', ' ')
                    print(f'退款率空 ({kw[:40]}… month={month_name}): {snippet}')
        return ''
    finally:
        if owns_session and session is not None:
            await session.close()


async def async_return_rale_main(department_keyword: str, *, marketplace: str | None = None) -> str:
    return await fetch_refund_rate_for_path(department_keyword, marketplace=marketplace)


async def prefetch_refund_rates_batch(
    paths: list[str],
    *,
    max_concurrent: int = 6,
    marketplace: str | None = None,
) -> tuple[dict[str, float], list[dict[str, str]]]:
    """
    批量预取退款率；单类目失败不中断整批。
    返回 (path->rate, 失败列表)。
    """
    mp = normalize_sellersprite_marketplace(marketplace or get_sellersprite_marketplace())
    unique: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        path = (raw or '').strip()
        if path and path not in seen:
            seen.add(path)
            unique.append(path)
    if not unique:
        return {}, []

    config = await ensure_seller_login()
    apply_login_config(cookies, config)
    apply_sellersprite_station_cookie(cookies, mp)
    req_headers = dict(headers)
    apply_login_headers(req_headers, config)

    out: dict[str, float] = {}
    failures: list[dict[str, str]] = []
    sem = asyncio.Semaphore(max(1, max_concurrent))

    async with aiohttp.ClientSession(headers=req_headers, cookies=cookies) as session:
        async def _one(path: str) -> None:
            async with sem:
                text = await fetch_refund_rate_for_path(
                    path, session=session, marketplace=mp
                )
                if not text:
                    failures.append({
                        'path': path,
                        'error': '卖家精灵退款率接口无数据',
                    })
                    print(f'警告: 类目退款率无数据: {path[:80]}…')
                    return
                try:
                    val = float(text)
                except ValueError:
                    failures.append({
                        'path': path,
                        'error': f'退款率无效: {text!r}',
                    })
                    return
                if val <= 0:
                    failures.append({
                        'path': path,
                        'error': f'退款率无效: {val}',
                    })
                    return
                out[path] = val

        await asyncio.gather(*[_one(p) for p in unique], return_exceptions=False)

    return out, failures


if __name__ == "__main__":
    keyword = (
        "Health & Household:Health Care:Sleep & Snoring:Sleeping Masks"
    )
    val = asyncio.run(async_return_rale_main(keyword))
    print('退货率:', val or '为空')
