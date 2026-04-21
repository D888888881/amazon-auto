import asyncio
import aiohttp
from lxml import html
from typing import Optional, Dict, Any
from seller_wizard_set_cookie import set_cookie_main


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
    "Sprite-X-Token": "eyJhbGciOiJSUzI1NiIsImtpZCI6IjE2Nzk5NjI2YmZlMDQzZTBiYzI5NTEwMTE4ODA3YWExIn0.eyJqdGkiOiJObTNjYmpmVXRuVG1lX0hWRzdocFp3IiwiaWF0IjoxNzc0NTA5NTk1LCJleHAiOjE3NzQ1OTU5OTUsIm5iZiI6MTc3NDUwOTUzNSwic3ViIjoieXVueWEiLCJpc3MiOiJyYW5rIiwiYXVkIjoic2VsbGVyU3BhY2UiLCJpZCI6MTI5NDI1LCJwaSI6bnVsbCwibm4iOiLmt7HlnLPpmL_mlrnntKLnp5HmioDmnInpmZDlhazlj7giLCJzeXMiOiJTU19DTiIsImVkIjoiTiIsInBobiI6IjEzNzI0MzMzODAzIiwiZW0iOiJxdWlnZW5nbmFAMTI2LmNvbSIsIm1sIjoiViIsImVuZCI6MTc4MjU0NDc5NTg2OH0.WSErMY_l_7JOxDOFXM0uOaRAxHVxlcmebSa1rfsa3hdy1NX1ChTW-Wmt6h2WDjrLXqu_TVB1O-cKeY53Wnp7QvGh1Ex-MEZkoHpWnXQBI3tQrgBeDO70P6T8e0l-dMHWV-YOXerrQ8wZh7z7kGNTz4qkNCt6_idSPnyEbD2Zr4IIOOYaEBCt11Kdb_bSOmmHjl9Aix8POfe-e5t2jDcuUPdwOvbntcN2yEKdoEGC-h3BxW5WqcdXl_-zfwHyMDSLF0M9JYcOieQbMOatASBn4Vlqb6r116wcp-S2meH9UKDZwhJaDN3vXo2El18R8fD0oXvWOBOkEuSUtxTwM9tRrg",
    "ao_lo_to_n": "\"5917654771sTlVc5v9oyTCeXLRrg0WdYpTS2iYglYvULffNNNMBcyHnQMKABbi8gc20FarG0A5qB1vaKgTD4Qow5Xanaje96PAVd71/f+h3p9Ry7rrE4U=\"",
    "_ga_CN0F80S6GL": "GS2.1.s1774509573$o29$g1$t1774509843$j60$l0$h0",
    "Hm_lpvt_e0dfc78949a2d7c553713cb5c573a486": "1774509844",
    "_clsk": "1tig1ea%5E1774509845396%5E7%5E1%5Ei.clarity.ms%2Fcollect",
    "JSESSIONID": "2DA1183136557EA50651E0A7E3FEA475",
    "_ga_38NCVF2XST": "GS2.1.s1774509573$o39$g1$t1774509928$j60$l0$h1584007809"
}
BASE_URL = "https://www.sellersprite.com/v2/market-research"







async def extract_table_value(html_content: str) -> str:
    """
    从 SellerSprite 市场调研返回的 HTML 中提取指定 XPath 的文本内容
    XPath: //*[@id="table-condition-search"]/tbody/tr[1]/td[14]/div/div[1]/text()
    """
    # 解析 HTML
    tree = html.fromstring(html_content)
    # 执行 XPath 查询，返回元素列表（此处 text() 会返回文本节点列表）
    elements = tree.xpath('//*[@id="table-condition-search"]/tbody/tr[1]/td[14]/div/div[1]/text()')
    if elements:
        # 如果有多个文本节点，通常取第一个，或合并所有
        return elements[0].strip() if elements[0] else ""
    else:
        return ""  # 或 None，根据需求


async def fetch_market_research(
    session: Optional[aiohttp.ClientSession] = None,
    market_id: str = "1",
    department_keyword: str = "Health & Household:Health Care:Over-the-Counter Medication:Pain Relievers:Hot & Cold Therapies:Heating Pads",
    topn: str = "10",
    new_release_num: str = "6",
    order_field: str = "total_sales",
    order_desc: str = "true",
    tab: str = "1",
    month_name: str = "bsr_sales_monthly_202512",
    **extra_data
) -> str:
    """
    异步发送 POST 请求到 sellerSprite 市场调研接口

    :param session: 可选的 aiohttp.ClientSession，如果为 None 则内部创建
    :param market_id: 市场ID，默认 "1" (美国)
    :param department_keyword: 类目关键词路径
    :param topn: TOP N 数量
    :param new_release_num: New Release 数量
    :param order_field: 排序字段
    :param order_desc: 排序方向
    :param tab: 标签页
    :param month_name: 月份名称
    :param extra_data: 其他可选参数，会合并到表单数据中
    :return: 响应文本
    """
    # 构建表单数据
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
        # 以下为大量空字段（可根据需要覆盖）
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
        # 允许额外参数覆盖或补充
        **extra_data
    }

    async def _request(sess: aiohttp.ClientSession) -> str:
        async with sess.post(BASE_URL, data=data) as resp:
            text = await resp.text()
            return text

    if session:
        return await _request(session)
    else:
        async with aiohttp.ClientSession(headers=headers, cookies=cookies) as new_session:
            return await _request(new_session)


async def async_return_rale_main(department_keyword: str)->str:
    config = await set_cookie_main('ITBM000001', 'ITBM000001')
    cookies['rank-login-user'] = config['rank-login-user']
    cookies['rank-login-user-info'] = config['rank-login-user-info']

    async with aiohttp.ClientSession(headers=headers, cookies=cookies) as session:
        result2 = await fetch_market_research(session=session, department_keyword=department_keyword)

        target_value = await extract_table_value(result2)
        return target_value


if __name__ == "__main__":
    keyword = "Health & Household:Health Care:Sleep & Snoring:Sleeping Masks"
    print(asyncio.run(async_return_rale_main(keyword)))