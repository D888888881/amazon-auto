import asyncio
import aiohttp
# from async_read_config import read_main

from seller_account_guard import (
    SellerAccountBannedError,
    apply_login_config,
    apply_login_headers,
    ensure_seller_login,
    parse_sellersprite_api_payload,
)
from sellersprite_market import (
    apply_sellersprite_station_cookie,
    get_sellersprite_marketplace,
    normalize_sellersprite_marketplace,
    response_matches_sellersprite_marketplace,
    sellersprite_market_id,
)


"""异步发起单个 ASIN 的 FBA 计算请求"""
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
        "rank-login-user": 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        "rank-login-user-info": 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        "Sprite-X-Token": "",
        "ao_lo_to_n": "",
        "_ga_CN0F80S6GL": "GS2.1.s1774509573$o29$g1$t1774509843$j60$l0$h0",
        "Hm_lpvt_e0dfc78949a2d7c553713cb5c573a486": "1774509844",
        "_clsk": "1tig1ea%5E1774509845396%5E7%5E1%5Ei.clarity.ms%2Fcollect",
        "JSESSIONID": "",
        "_ga_38NCVF2XST": "GS2.1.s1774509573$o39$g1$t1774509928$j60$l0$h1584007809"
    }

async def fetch_fba_search(asin, *, marketplace: str | None = None):

    url = "https://www.sellersprite.com/v3/api/tools/fba-calculator"
    mp = normalize_sellersprite_marketplace(marketplace or get_sellersprite_marketplace())
    params = {
        "marketId": sellersprite_market_id(mp),
        "asin": asin,
        "type": "fba"
    }
    req_cookies = dict(cookies)
    apply_sellersprite_station_cookie(req_cookies, mp)
    async with aiohttp.ClientSession(headers=headers, cookies=req_cookies) as session:
        async with session.post(url, params=params) as resp:
            return await resp.json()


def _parse_fba_fee(raw) -> float | None:
    if raw is None:
        return None
    try:
        s = str(raw).replace('$', '').replace('£', '').replace(',', '').strip()
        if not s:
            return None
        n = float(s)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


async def process_asin(asin, *, marketplace: str | None = None):
    """
    处理单个 ASIN，返回 (asin, result) 元组，result 包含 FBA 费用和头程费用
    若失败则返回 (asin, None)
    """
    mp = normalize_sellersprite_marketplace(marketplace or get_sellersprite_marketplace())
    try:
        response_json = await fetch_fba_search(asin, marketplace=mp)
        data = parse_sellersprite_api_payload(response_json, asin=asin, api='FBA')
        if not response_matches_sellersprite_marketplace(data, mp):
            print(
                f"处理 ASIN {asin} 失败: FBA 返回站点与请求不符"
                f"（期望 {mp}/marketId={sellersprite_market_id(mp)}），已丢弃"
            )
            return asin, None
        fba_val = _parse_fba_fee(data.get('fba'))
        if fba_val is None:
            raise ValueError(f"FBA 费用无效: {data.get('fba')!r}")
        pkgDimensions = data['pkgDimensions']
        weight_raw = str(data.get('pkgWeight') or '')
        if 'kg' in weight_raw.lower():
            pkgWeight = float(
                weight_raw.lower().replace('kg', '').replace(',', '').strip() or '0'
            )
        else:
            pkgWeight = float(weight_raw.replace('pounds', '').replace(',', '').strip()) * 0.45359237
        dims = pkgDimensions.split('x')
        h = float(dims[0].strip()) * 2.54          # 高 cm
        w = float(dims[1].strip()) * 2.54          # 宽 cm
        i = float(dims[2].replace('inches', '').replace('cm', '').strip()) * 2.54  # 长 cm
        volume_weight = h * w * i / 6000
        chargeable_weight = volume_weight if volume_weight > pkgWeight else pkgWeight
        head_distance = chargeable_weight * 5
        result = {
            "FBA": fba_val,
            "head_distance": head_distance
        }
        return asin, result
    except SellerAccountBannedError:
        raise
    except Exception as e:
        print(f"处理 ASIN {asin} 失败: {e}")
        return asin, None

async def async_fba_batch(asin_list, max_concurrent=5, *, marketplace: str | None = None):
    """
    并发处理多个 ASIN。
    marketplace=US|UK：决定 marketId 与 module-station-market-research。
    """
    mp = normalize_sellersprite_marketplace(marketplace or get_sellersprite_marketplace())
    config = await ensure_seller_login()
    apply_login_config(cookies, config)
    apply_sellersprite_station_cookie(cookies, mp)
    apply_login_headers(headers, config)
    semaphore = asyncio.Semaphore(max_concurrent)

    async def bounded_process(asin):
        async with semaphore:
            return await process_asin(asin, marketplace=mp)

    tasks = [bounded_process(asin) for asin in asin_list]
    results = await asyncio.gather(*tasks)
    return dict(results)


if __name__ == "__main__":
    asins = ["B0GQVXM199"]
    result = asyncio.run(async_fba_batch(asins, max_concurrent=3))
    print(result)
