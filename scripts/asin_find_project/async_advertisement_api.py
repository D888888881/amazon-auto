import asyncio
import os

import aiohttp
from typing import List, Dict, Any

# from async_read_config import read_main
from seller_account_guard import (
    SellerAccountBannedError,
    apply_login_config,
    apply_login_headers,
    ensure_seller_login,
    looks_like_seller_auth_message,
    parse_sellersprite_api_payload,
)
from sellersprite_market import (
    get_sellersprite_marketplace,
    normalize_sellersprite_marketplace,
    response_matches_sellersprite_marketplace,
    sellersprite_market_code,
    sellersprite_market_com,
    sellersprite_reversing_referer,
)


# ---------- 全局配置 ----------
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "priority": "u=1, i",
    "referer": "https://www.sellersprite.com/v3/reversing/sources?asin=B0F6MTPQVG&marketId=1&date=",
    "sec-ch-ua": "\"Not:A-Brand\";v=\"99\", \"Microsoft Edge\";v=\"145\", \"Chromium\";v=\"145\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0"
}

COOKIES = {
    "ecookie": "a8LU6D5cNXDX9r2v_CN",
    "current_guest": "22Kde9qAjlvY_260313-115007",
    "_ga": "GA1.1.1415896636.1773372235",
    "_gcl_au": "1.1.1596383600.1773372235",
    "MEIQIA_TRACK_ID": "3AsDAuhuMQUzdUXTUNdrluZiyhZ",
    "MEIQIA_VISIT_ID": "3AsDAy4Ce2FXqZL4GNp0dmSGTLc",
    "Hm_lvt_e0dfc78949a2d7c553713cb5c573a486": "1773476579",
    "HMACCOUNT": "1B0FE40093B498DF",
    "4ed1a8aaccdeeb35c17a": "a54b3dae0688431bc4657f86dfe989b6",
    "_fp": "982da2ff9374239947902667704f94ef",
    "3f0397c9881fc7fdbb14": "bc57462cef03a31d18b06476bfd60e7c",
    "_clck": "1mue9jd%5E2%5Eg4i%5E0%5E2263",
    "9442b23c7673059494ce": "921969ad3a72cb2a1e2fe3584a40b3df",
    "_gaf_fp": "bc76cc0d130ff660a08d903c3c22bfbc",
    "rank-login-user": 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
    "rank-login-user-info": 'xxxxxxxxxxxxxxxxxxxxxxxxxx',
    "Sprite-X-Token": "eyJhbGciOiJSUzI1NiIsImtpZCI6IjE2Nzk5NjI2YmZlMDQzZTBiYzI5NTEwMTE4ODA3YWExIn0.eyJqdGkiOiJwUDNqeUo4emJJT1NXVUFaWXNyQ2FRIiwiaWF0IjoxNzczOTczOTcwLCJleHAiOjE3NzQwNjAzNzAsIm5iZiI6MTc3Mzk3MzkxMCwic3ViIjoieXVueWEiLCJpc3MiOiJyYW5rIiwiYXVkIjoic2VsbGVyU3BhY2UiLCJpZCI6MTI5NDI1LCJwaSI6bnVsbCwibm4iOiLmt7HlnLPpmL_mlrnntKLnp5HmioDmnInpmZDlhazlj7giLCJzeXMiOiJTU19DTiIsImVkIjoiTiIsInBobiI6IjEzNzI0MzMzODAzIiwiZW0iOiJxdWlnZW5nbmFAMTI2LmNvbSIsIm1sIjoiViIsImVuZCI6MTc4MjUyNzU3MDc2MH0.F6SSXsRrAY_iOYcpenpasrsUu1_BSUWh6ro0uBhG2DyLh-e6Xc5elaJ2DWyfRWrb8EhhhECdZk8GEMcaaKRaPTtvUc1rVEd-Uu3IoWGGcrEV1iCBG85PuS16DxcIdnadh6xQpmdtOKWz5gKCZ29xYsSCWWUtbWdggdcD_YPx9X15x2ZYkKKHiOAoXCNmOEUnXwXJAVCR1c-eHvDM_jiCACDysP9WV7QdHmdFWpa4E79Ca59JpNGnHqplb27oSKbVyoCspOjbN0Hrn_0SkQ_YYhswzrEuRkRhipRrNQJ8F1nv_5fHm-0cp9u1nArfIaDvuU0ucSdsya2pht7SgMLgJg",
    "ao_lo_to_n": "\"0751304771qHBPbdmVaCga4o/94I3gu/cwDmffSSWZXEIJuK+W9zUOJVB3+55q21H4Ua7OVHgwP4bWLVJ1eTMFpwTm7M2UlPVbS59BDeY/AyXWRgD8dlE=\"",
    "p_c_size": "50",
    "JSESSIONID": "4C18D439064C2193AF6E246B7CA55074",
    "Hm_lpvt_e0dfc78949a2d7c553713cb5c573a486": "1773995424",
    "o_size": "50",
    "_ga_38NCVF2XST": "GS2.1.s1773995366$o23$g1$t1773995926$j60$l0$h125112945",
    "_ga_CN0F80S6GL": "GS2.1.s1773995366$o18$g1$t1773995930$j60$l0$h0",
    "_clsk": "cazfxk%5E1773996993347%5E17%5E1%5Ei.clarity.ms%2Fcollect"
}

BASE_URL = "https://www.sellersprite.com/v3/api/relation/ta/source"
BASE_URL_totalUnits = "https://www.sellersprite.com/v3/api/competing-lookup"
BASE_PARAMS = {
    "market": "COM",  # US=COM；UK=UK（运行时按站点覆盖；勿用 CO.UK）
    "pageNo": "1",
    "pageSize": "50",
    "order": "1",
    "desc": "true",
    "month": " "
}

# monthName: "bsr_sales_monthly_202510"
data_totalUnits = {
    "market": "US",  # competing-lookup：US / UK
    "monthName": "bsr_sales_nearly",
    "asins": [
        "B0F6MTPQVG"
    ],
    "page": 1,
    "nodeIdPaths": [],
    "symbolFlag": False,
    "size": 60,
    "order": {
        "field": "amz_unit",
        "desc": True
    },
    "lowPrice": "N"
}


async def random_sleep():
    """批量模式下默认不延迟；可通过 ROI_AD_REQUEST_DELAY_SEC 恢复节流。"""
    delay = float(os.environ.get('ROI_AD_REQUEST_DELAY_SEC', '0'))
    if delay > 0:
        await asyncio.sleep(delay)


async def fetch_source(
    session: aiohttp.ClientSession,
    asin: str,
    retries: int = 3,
    timeout: int = 20,
    *,
    marketplace: str | None = None,
) -> Dict[str, Any]:
    """
    异步获取单个 ASIN 的 source 数据，支持重试和超时。
    默认 timeout=20、retries=3，降低大批量时偶发超时导致静默丢 ASIN。
    market：US→COM，UK→UK（不要用 CO.UK，会被服务端忽略并回落美国站）。
    """
    mp = normalize_sellersprite_marketplace(marketplace or get_sellersprite_marketplace())
    params = BASE_PARAMS.copy()
    params["market"] = sellersprite_market_com(mp)
    params["keywordOrAsin"] = asin

    for attempt in range(retries + 1):
        try:
            async with session.get(BASE_URL, params=params, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status != 200:
                    # 非 200 状态码，可重试
                    if attempt < retries:
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    return {"error": f"HTTP {resp.status}", "asin": asin}

                try:
                    data = await resp.json()
                    return data
                except aiohttp.ContentTypeError:
                    text = await resp.text()
                    if attempt < retries:
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    return {"error": "Invalid JSON", "text": text, "asin": asin}
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            if attempt < retries:
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            return {"error": f"Request failed: {str(e)}", "asin": asin}
    return {"error": "Max retries exceeded", "asin": asin}




async def fetch_multiple_asins(
    asin_list: List[str],
    max_concurrent: int = 1,
    *,
    on_progress: Any = None,
    marketplace: str | None = None,
) -> Dict[str, Any]:
    """
    并发获取多个 ASIN 的数据，并对每个 ASIN 的所有 items 进行聚合：
    - 计算 ADS、HIGHLY_RATED、SPONSOR_VIDEO、SPONSOR_BRAND 的总和
    - 计算平均价格和平均评论数
    - imageUrl 取 items 中第一条非空
    """
    mp = normalize_sellersprite_marketplace(marketplace or get_sellersprite_marketplace())
    semaphore = asyncio.Semaphore(max_concurrent)

    results_dict = {}
    total = len(asin_list)
    done_count = 0
    progress_lock = asyncio.Lock()

    async def bounded_fetch(asin: str):
        nonlocal done_count
        async with semaphore:
            result = await fetch_source(session, asin, marketplace=mp)
            print(result)
            print(f'{asin},请求广告值成功')
            await random_sleep()  # 每次请求后等待 1 秒
            async with progress_lock:
                done_count += 1
                current = done_count
            if on_progress:
                try:
                    on_progress(current, total, asin)
                except Exception:
                    pass
            return asin, result

    req_headers = dict(HEADERS)
    req_headers['referer'] = sellersprite_reversing_referer(
        asin_list[0] if asin_list else '', mp
    )
    async with aiohttp.ClientSession(headers=req_headers, cookies=COOKIES) as session:
        tasks = [bounded_fetch(asin) for asin in asin_list]
        results = await asyncio.gather(*tasks)

    for asin, data in results:
        if "error" in data:
            err = str(data['error'])
            if looks_like_seller_auth_message(err) or 'HTTP 401' in err or 'HTTP 403' in err:
                raise SellerAccountBannedError(f'广告 API ASIN {asin}: {err}')
            print(f"ASIN {asin} 请求失败: {err}")
            continue

        data_content = parse_sellersprite_api_payload(data, asin=asin, api='广告')
        if not data_content:
            print(f"ASIN {asin} 的 data 为空")
            continue

        pager = data_content.get('pager')
        if not pager:
            print(f"ASIN {asin} 的 pager 为空")
            continue

        items_list = pager.get('items', [])
        if not items_list:
            print(f"ASIN {asin} 的 items 列表为空")
            continue

        # 防止错误 market 参数被服务端回落成其它站点数据
        sample = next((x for x in items_list if isinstance(x, dict)), None)
        if sample is not None and not response_matches_sellersprite_marketplace(
            sample, mp
        ):
            print(
                f"ASIN {asin} 广告数据站点不匹配（期望 {mp}），已丢弃"
            )
            continue

        # 初始化累加器
        total_ads = 0
        total_highly_rated = 0
        total_sponsor_video = 0
        total_sponsor_brand = 0
        total_price = 0.0
        total_reviews = 0
        avg_price = 0
        avg_reviews = 0
        item_count = len(items_list)
        image_url = ''
        try:
            # 取第一条非空 imageUrl（首条常为广告位，可能无图）
            for item in items_list:
                if not isinstance(item, dict):
                    continue
                cand = str(item.get('imageUrl') or '').strip()
                if cand and cand.upper() not in ('N/A', 'NA', 'NAN'):
                    image_url = cand
                    break
        except Exception as e:
            print(f"ASIN {asin} 解析 imageUrl 失败: {e}")
        try:
            for item in items_list:
                counter = item.get('counter', {})
                total_ads += counter.get('ADS', 0)
                total_highly_rated += counter.get('HIGHLY_RATED', 0)
                total_sponsor_video += counter.get('SPONSOR_VIDEO', 0)
                total_sponsor_brand += counter.get('SPONSOR_BRAND', 0)
                total_price += item.get('price', 0.0)
                total_reviews += item.get('reviews', 0)
        except Exception as e:
            print(f"不好数据出错了1 {asin}  {e}")
        # 计算平均值

        try:
            avg_price = total_price / item_count if item_count > 0 else 0.0
            avg_reviews = total_reviews / item_count if item_count > 0 else 0
        except Exception as e:
            print(f"不好数据出错了2 {asin}  {e}")
        key = str(asin).strip().upper()
        results_dict[key] = {
            'ads': total_ads,
            'highly_rated': total_highly_rated,
            'sponsor_video': total_sponsor_video,
            'sponsor_brand': total_sponsor_brand,
            'avg_price': avg_price,
            'avg_reviews': avg_reviews,
            'item_count': item_count,  # 可选，便于调试
            'imageUrl': image_url,
        }

    return results_dict


async def ensure_ads_cached(
    cache: Dict[str, Any],
    asins: List[str],
    max_concurrent: int = 6,
    *,
    on_progress: Any = None,
    marketplace: str | None = None,
) -> Dict[str, Any]:
    """批量拉取广告数据，仅请求 cache 中尚未存在的 ASIN。"""
    needed: list[str] = []
    seen: set[str] = set()
    for raw in asins or []:
        key = str(raw or '').strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        if key not in cache:
            needed.append(key)
    if not needed:
        return cache
    config = await ensure_seller_login()
    apply_login_config(COOKIES, config)
    apply_login_headers(HEADERS, config)
    fetched = await fetch_multiple_asins(
        needed,
        max_concurrent,
        on_progress=on_progress,
        marketplace=marketplace,
    )
    cache.update(fetched)
    return cache


async def ensure_ads_cached_robust(
    cache: Dict[str, Any],
    asins: List[str],
    max_concurrent: int = 6,
    *,
    max_rounds: int = 3,
    pause_sec: float = 2.0,
    on_progress: Any = None,
    marketplace: str | None = None,
) -> Dict[str, Any]:
    """多次尝试拉取广告数据，直至全部命中 cache 或达到 max_rounds。"""
    pending: list[str] = []
    seen: set[str] = set()
    for raw in asins or []:
        key = str(raw or '').strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        pending.append(key)
    for round_i in range(max(1, max_rounds)):
        missing = [a for a in pending if not ads_cache_get(cache, a)]
        if not missing:
            break
        await ensure_ads_cached(
            cache,
            missing,
            max_concurrent=max_concurrent,
            on_progress=on_progress,
            marketplace=marketplace,
        )
        still = [a for a in missing if not ads_cache_get(cache, a)]
        if not still:
            break
        pending = still
        if round_i + 1 < max_rounds and pause_sec > 0:
            await asyncio.sleep(pause_sec)
    return cache


def ads_cache_get(cache: dict | None, asin: str) -> dict | None:
    if not cache:
        return None
    key = str(asin or '').strip().upper()
    row = cache.get(key)
    if isinstance(row, dict):
        return row
    return cache.get(asin) if isinstance(cache.get(asin), dict) else None


async def fetch_source_totalUnits(
    session: aiohttp.ClientSession,
    asin: str,
    retries: int = 2,
    timeout: int = 10,
    *,
    marketplace: str | None = None,
) -> Dict[str, Any]:
    """
    异步获取单个 ASIN 的 source 数据，支持重试和超时。
    competing-lookup 的 market 使用 US / UK。
    """
    mp = normalize_sellersprite_marketplace(marketplace or get_sellersprite_marketplace())
    payload = data_totalUnits.copy()
    payload["market"] = sellersprite_market_code(mp)
    payload["asins"] = [asin]

    for attempt in range(retries + 1):
        try:
            async with session.post(BASE_URL_totalUnits, json=payload,
                                    timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status != 200:
                    # 非 200 状态码，可重试
                    if attempt < retries:
                        await random_sleep()
                        continue
                    return {"error": f"HTTP {resp.status}", "asin": asin}

                try:
                    data = await resp.json()
                    return data
                except aiohttp.ContentTypeError:
                    text = await resp.text()
                    if attempt < retries:
                        await random_sleep()
                        continue
                    return {"error": "Invalid JSON", "text": text, "asin": asin}
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            if attempt < retries:
                await random_sleep()
                continue
            return {"error": f"Request failed: {str(e)}", "asin": asin}
    return {"error": "Max retries exceeded", "asin": asin}


async def fetch_multiple_asins_totalUnits(
    asin_list: List[str],
    max_concurrent: int = 1,
    *,
    marketplace: str | None = None,
) -> Dict[str, Any]:
    """
    并发获取多个 ASIN 的数据，并计算每个 ASIN 的最大广告计数
    competing-lookup 的 market 为 US / UK。
    """
    mp = normalize_sellersprite_marketplace(marketplace or get_sellersprite_marketplace())
    semaphore = asyncio.Semaphore(max_concurrent)

    async def bounded_fetch(asin: str):
        async with semaphore:
            result = await fetch_source_totalUnits(session, asin, marketplace=mp)
            # print(result)
            await random_sleep()  # 每次请求后等待 1 秒
            return asin, result

    async with aiohttp.ClientSession(headers=HEADERS, cookies=COOKIES) as session:
        tasks = [bounded_fetch(asin) for asin in asin_list]
        results = await asyncio.gather(*tasks)
    # print(results)
    results_dict = {}
    for item in results:
        asin = item[0]
        payload = item[1]
        if isinstance(payload, dict) and payload.get('error'):
            err = str(payload['error'])
            if looks_like_seller_auth_message(err) or 'HTTP 401' in err or 'HTTP 403' in err:
                raise SellerAccountBannedError(f'销量 API ASIN {asin}: {err}')
        try:
            data_content = parse_sellersprite_api_payload(payload, asin=asin, api='销量')
            items = data_content.get('items') or []
            bast_totalUnits = -1
            for value in items:
                if not response_matches_sellersprite_marketplace(value, mp):
                    continue
                totalUnits = value.get('totalUnits', 0)
                if totalUnits is None:
                    totalUnits = 0
                try:
                    if totalUnits > bast_totalUnits:
                        bast_totalUnits = totalUnits
                        results_dict[asin] = {'totalUnits': totalUnits}
                        results_dict[asin].update({'salesTrend': value.get('salesTrend', 0)})
                except Exception as e:
                    print(f"ASIN {asin} 数据比较出现问题 {e}")
        except SellerAccountBannedError:
            raise
        except Exception as e:
            print(f"ASIN {asin} <不好，出问题了> {e}")
    # print(results_dict)
    return results_dict


# ---------- 使用示例 ----------
async def advertisement_main(
    asins: List[str],
    max_concurrent: int = 1,
    *,
    marketplace: str | None = None,
) -> Dict[str, Any]:
    mp = normalize_sellersprite_marketplace(marketplace or get_sellersprite_marketplace())
    config = await ensure_seller_login()
    print(config)
    apply_login_config(COOKIES, config)
    apply_login_headers(HEADERS, config)
    HEADERS['referer'] = sellersprite_reversing_referer(asins[0] if asins else '', mp)
    result_dict = await fetch_multiple_asins(
        asins, max_concurrent=max_concurrent, marketplace=mp
    )
    return result_dict


if __name__ == "__main__":
    # asins = ["B0F6MTPQVG","B0F9WW826V",'B0FWJ8HNCB','B0FY5S16DK','B0C62HMMCJ']
    # asins = ['B0FWJ8HNCB', 'B0D3M1WHQ6','B0D6XKFPF1','B0DXF3TQRD','B0DFH5Z3JB','B08HJR2RL2', 'B0D3M1WHQ6','B0DXF3TQRD','B0DFH5Z3JB','B0GCCXBK14','B0DGKTRZN2','B0D299X6KN','B0CSJZVHKX','B0DR2LC897','B0D6XKFPF1','B0C3QQJ8YF','B093QZ6V3S','B0DT4JGZY5']
    asins = ['B0H14TCNSV']
    # result = asyncio.run(fetch_multiple_asins(asins))
    # result = asyncio.run(fetch_multiple_asins(asins,1))
    result = asyncio.run(advertisement_main(asins))
    print(result)
