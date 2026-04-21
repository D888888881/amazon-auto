import asyncio
import aiohttp
# from async_read_config import read_main

from seller_wizard_set_cookie import set_cookie_main


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
        "rank-login-user": 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',              # 从配置读取
        "rank-login-user-info": 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',   # 从配置读取
        "Sprite-X-Token": "eyJhbGciOiJSUzI1NiIsImtpZCI6IjE2Nzk5NjI2YmZlMDQzZTBiYzI5NTEwMTE4ODA3YWExIn0.eyJqdGkiOiJObTNjYmpmVXRuVG1lX0hWRzdocFp3IiwiaWF0IjoxNzc0NTA5NTk1LCJleHAiOjE3NzQ1OTU5OTUsIm5iZiI6MTc3NDUwOTUzNSwic3ViIjoieXVueWEiLCJpc3MiOiJyYW5rIiwiYXVkIjoic2VsbGVyU3BhY2UiLCJpZCI6MTI5NDI1LCJwaSI6bnVsbCwibm4iOiLmt7HlnLPpmL_mlrnntKLnp5HmioDmnInpmZDlhazlj7giLCJzeXMiOiJTU19DTiIsImVkIjoiTiIsInBobiI6IjEzNzI0MzMzODAzIiwiZW0iOiJxdWlnZW5nbmFAMTI2LmNvbSIsIm1sIjoiViIsImVuZCI6MTc4MjU0NDc5NTg2OH0.WSErMY_l_7JOxDOFXM0uOaRAxHVxlcmebSa1rfsa3hdy1NX1ChTW-Wmt6h2WDjrLXqu_TVB1O-cKeY53Wnp7QvGh1Ex-MEZkoHpWnXQBI3tQrgBeDO70P6T8e0l-dMHWV-YOXerrQ8wZh7z7kGNTz4qkNCt6_idSPnyEbD2Zr4IIOOYaEBCt11Kdb_bSOmmHjl9Aix8POfe-e5t2jDcuUPdwOvbntcN2yEKdoEGC-h3BxW5WqcdXl_-zfwHyMDSLF0M9JYcOieQbMOatASBn4Vlqb6r116wcp-S2meH9UKDZwhJaDN3vXo2El18R8fD0oXvWOBOkEuSUtxTwM9tRrg",
        "ao_lo_to_n": "\"5917654771sTlVc5v9oyTCeXLRrg0WdYpTS2iYglYvULffNNNMBcyHnQMKABbi8gc20FarG0A5qB1vaKgTD4Qow5Xanaje96PAVd71/f+h3p9Ry7rrE4U=\"",
        "_ga_CN0F80S6GL": "GS2.1.s1774509573$o29$g1$t1774509843$j60$l0$h0",
        "Hm_lpvt_e0dfc78949a2d7c553713cb5c573a486": "1774509844",
        "_clsk": "1tig1ea%5E1774509845396%5E7%5E1%5Ei.clarity.ms%2Fcollect",
        "JSESSIONID": "2DA1183136557EA50651E0A7E3FEA475",
        "_ga_38NCVF2XST": "GS2.1.s1774509573$o39$g1$t1774509928$j60$l0$h1584007809"
    }

async def fetch_fba_search(asin):

    url = "https://www.sellersprite.com/v3/api/tools/fba-calculator"
    params = {
        "marketId": "1",
        "asin": asin,
        "type": "fba"
    }
    async with aiohttp.ClientSession(headers=headers, cookies=cookies) as session:
        async with session.post(url, params=params) as resp:
            return await resp.json()

async def process_asin(asin):
    """
    处理单个 ASIN，返回 (asin, result) 元组，result 包含 FBA 费用和头程费用
    若失败则返回 (asin, None)
    """
    try:
        response_json = await fetch_fba_search(asin)
        # 提取尺寸和重量
        pkgDimensions = response_json['data']['pkgDimensions']
        pkgWeight = float(response_json['data']['pkgWeight'].replace('pounds', '').strip()) * 0.45359237  # 转为 kg
        # 解析尺寸（英寸）
        dims = pkgDimensions.split('x')
        h = float(dims[0].strip()) * 2.54          # 高 cm
        w = float(dims[1].strip()) * 2.54          # 宽 cm
        i = float(dims[2].replace('inches', '').strip()) * 2.54  # 长 cm
        # 体积重 (kg)
        volume_weight = h * w * i / 6000
        # 计费重量 = max(实际重, 体积重)
        chargeable_weight = volume_weight if volume_weight > pkgWeight else pkgWeight
        # 头程费用（假设单价 5 元/kg）
        head_distance = chargeable_weight * 5
        result = {
            "FBA": response_json['data']['fba'],
            "head_distance": head_distance
        }
        return asin, result
    except Exception as e:
        print(f"处理 ASIN {asin} 失败: {e}")
        return asin, None

async def async_fba_batch(asin_list, max_concurrent=5):
    """
    并发处理多个 ASIN
    :param asin_list: ASIN 列表
    :param max_concurrent: 最大并发数
    :return: 字典，键为 ASIN，值为 {"FBA": ..., "head_distance": ...} 或 None
    """
    config = await set_cookie_main('ITBM000001', 'ITBM000001')
    cookies['rank-login-user'] = config['rank-login-user']
    cookies['rank-login-user-info'] = config['rank-login-user-info']
    semaphore = asyncio.Semaphore(max_concurrent)

    async def bounded_process(asin):
        async with semaphore:
            return await process_asin(asin)

    tasks = [bounded_process(asin) for asin in asin_list]
    results = await asyncio.gather(*tasks)
    return dict(results)


if __name__ == "__main__":
    # 示例：多个 ASIN 并发处理
    asins = ["B0F6MTPQVG"]
    result = asyncio.run(async_fba_batch(asins, max_concurrent=3))
    print(result)

    # 也可以使用原有的单 ASIN 函数
    # single = asyncio.run(async_fba_main("B01KVYTV7M"))
    # print(single)