import asyncio
import random

import aiohttp
from typing import List, Dict, Any

# from async_read_config import read_main
from seller_wizard_set_cookie import set_cookie_main


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
    "market": "COM",
    "pageNo": "1",
    "pageSize": "50",
    "order": "1",
    "desc": "true",
    "month": " "
}

# monthName: "bsr_sales_monthly_202510"
data_totalUnits = {
    "market": "US",
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
    """随机延迟：模拟真人操作，核心反检测"""
    delay = random.uniform(1, 2)
    await asyncio.sleep(delay)


async def fetch_source(session: aiohttp.ClientSession, asin: str, retries: int = 2, timeout: int = 10) -> Dict[
    str, Any]:
    """
    异步获取单个 ASIN 的 source 数据，支持重试和超时
    """
    params = BASE_PARAMS.copy()
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




async def fetch_multiple_asins(asin_list: List[str], max_concurrent: int = 1) -> Dict[str, Any]:
    """
    并发获取多个 ASIN 的数据，并对每个 ASIN 的所有 items 进行聚合：
    - 计算 ADS、HIGHLY_RATED、SPONSOR_VIDEO、SPONSOR_BRAND 的总和
    - 计算平均价格和平均评论数
    - 忽略 imageUrl（因为多个 item 无法合并为单个）
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def bounded_fetch(asin: str):
        async with semaphore:
            result = await fetch_source(session, asin)
            print(f'{asin},请求广告值成功')
            await random_sleep()  # 每次请求后等待 1 秒
            return asin, result

    async with aiohttp.ClientSession(headers=HEADERS, cookies=COOKIES) as session:
        tasks = [bounded_fetch(asin) for asin in asin_list]
        results = await asyncio.gather(*tasks)

    results_dict = {}
    for asin, data in results:
        if "error" in data:
            print(f"ASIN {asin} 请求失败: {data['error']}")
            continue

        data_content = data.get('data')
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
            image_url = items_list[0].get('imageUrl','')
        except Exception as e:
            print(f"ASIN {asin} <UNK> imageUrl <UNK> {e}")
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
        results_dict[asin] = {
            'ads': total_ads,
            'highly_rated': total_highly_rated,
            'sponsor_video': total_sponsor_video,
            'sponsor_brand': total_sponsor_brand,
            'avg_price': avg_price,
            'avg_reviews': avg_reviews,
            'item_count': item_count,  # 可选，便于调试
            'imageUrl': image_url,
        }
        # 如果需要保留第一个 imageUrl 作为示例，可添加：
        # results_dict[asin]['imageUrl'] = items_list[0].get('imageUrl', '') if items_list else ''

    return results_dict


async def fetch_source_totalUnits(session: aiohttp.ClientSession, asin: str, retries: int = 2, timeout: int = 10) -> Dict[str, Any]:
    """
    异步获取单个 ASIN 的 source 数据，支持重试和超时
    """
    payload = data_totalUnits.copy()
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


async def fetch_multiple_asins_totalUnits(asin_list: List[str], max_concurrent: int = 1) -> Dict[str, Any]:
    """
    并发获取多个 ASIN 的数据，并计算每个 ASIN 的最大广告计数
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def bounded_fetch(asin: str):
        async with semaphore:
            result = await fetch_source_totalUnits(session, asin)
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
        try:
            items = item[1]['data']['items']
            bast_totalUnits = -1
            for value in items:
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
        except Exception as e:
            print(f"ASIN {asin} <不好，出问题了> {e}")
    # print(results_dict)
    return results_dict


# ---------- 使用示例 ----------
async def advertisement_main(asins: List[str], max_concurrent: int = 1) -> Dict[str, Any]:
    # 假设要查询的 ASIN 列表
    config =  await set_cookie_main('ITBM000001', 'ITBM000001')
    COOKIES['rank-login-user'] = config['rank-login-user']
    COOKIES['rank-login-user-info'] = config['rank-login-user-info']
    # totalUnits_dict = await fetch_multiple_asins_totalUnits(asins, max_concurrent=max_concurrent)
    result_dict = await fetch_multiple_asins(asins, max_concurrent=max_concurrent)
    # for asin, value in totalUnits_dict.items():
    #     try:
    #         result_dict[asin]['totalUnits'] = value['totalUnits']
    #         result_dict[asin]['salesTrend'] = value['salesTrend']
    #     except Exception as e:
    #         print(f"ASIN {asin} 数据出现问题 {e}")
    # # print(result_dict)
    return result_dict


if __name__ == "__main__":
    # asins = ["B0F6MTPQVG","B0F9WW826V",'B0FWJ8HNCB','B0FY5S16DK','B0C62HMMCJ']
    # asins = ['B0FWJ8HNCB', 'B0D3M1WHQ6','B0D6XKFPF1','B0DXF3TQRD','B0DFH5Z3JB','B08HJR2RL2', 'B0D3M1WHQ6','B0DXF3TQRD','B0DFH5Z3JB','B0GCCXBK14','B0DGKTRZN2','B0D299X6KN','B0CSJZVHKX','B0DR2LC897','B0D6XKFPF1','B0C3QQJ8YF','B093QZ6V3S','B0DT4JGZY5']
    asins = ['B0FWJ8HNCB', 'B0F6MTPQVG']
    # result = asyncio.run(fetch_multiple_asins(asins))
    # result = asyncio.run(fetch_multiple_asins(asins,1))
    result = asyncio.run(advertisement_main(asins))
    print(result)
