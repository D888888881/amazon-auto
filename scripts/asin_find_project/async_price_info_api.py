import asyncio
import aiohttp
import time
import hashlib


def get_timestamp_and_sign(token, app_key, data, timestamp=None):
    """生成时间戳和签名（与原函数相同）"""
    if timestamp is None:
        timestamp = int(time.time() * 1000)
    sign_str = f"{token}&{timestamp}&{app_key}&{data}"
    sign = hashlib.md5(sign_str.encode()).hexdigest()
    return timestamp, sign


async def fetch_keyword_search(keyword="conure bird bath", _m_h5_tk=None, _m_h5_tk_enc=None):
    """异步发起搜索请求"""
    # 固定的请求数据（与同步代码相同）
    data1 = f'{{"bizType":"selectionTool","customerId":"sellerspriteLP","language":"zh","currency":"CNY","searchParam":"{{\\"keyword\\":\\"{keyword}\\",\\"beginPage\\":1,\\"pageSize\\":30,\\"poolId\\":\\"52303046\\",\\"scene\\":\\"home\\"}}"}}'

    # 生成时间戳和签名
    token = _m_h5_tk.split('_')[0]
    app_key = "12574478"
    timestamp, sign = get_timestamp_and_sign(token, app_key, data1)

    # 查询参数
    params = {
        "jsv": "2.7.5",
        "appKey": app_key,
        "t": timestamp,
        "sign": sign,
        "type": "originaljson",
        "v": "1.0",
        "timeout": "20000",
        "ecode": "0",
        "dataType": "json",
        "api": "mtop.com.alibaba.cbu.crossBorder.lp.keywordSearch"
    }

    # 请求体（表单数据）
    data = {
        "data": data1
    }

    # Headers（与同步代码一致）
    headers = {
        "accept": "application/json",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://aibuy.1688.com",
        "priority": "u=1, i",
        "referer": "https://aibuy.1688.com/",
        "sec-ch-ua": "\"Not:A-Brand\";v=\"99\", \"Microsoft Edge\";v=\"145\", \"Chromium\";v=\"145\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0"
    }

    # Cookies（与同步代码相同）
    cookies = {
        "cna": "lAFEIli8aUwCAWgkFDNRTcyd",
        "xlly_s": "1",
        "taklid": "6f25179619c64fe7961aa5c8e256d870",
        "_csrf_token": "1774346840131",
        "_m_h5_c": "df98f40a771200bbc2b3ea59dd422d4d_1774356201456%3B9e276e377b7055d831f923d550031056",
        "cookie1": "AiSi2ue6ZuFnFbf2psWtciGaLFiiBF%2FiVyxgA2gOBwY%3D",
        "cookie2": "16ff12a4e52c45d480b9236ef46f7781",
        "cookie17": "UUphy%2FZ4h63TOALOtw%3D%3D",
        "sgcookie": "E100Q5Wh80u%2BuOpQrDCVj87%2BYBOEZq7vMs69yRrgSjrj5aqQf3ayCaCfR%2FJ7UwZ18QB%2F2UiDPcjD76ATMDMrCGJ2CCa1XeEzRWpxk9WrXFp8JqM%3D",
        "t": "e72105a5019bc73380ad058e2da1d24c",
        "_tb_token_": "547850e3337e6",
        "sg": "752",
        "csg": "f058ff3a",
        "lid": "tb755794817",
        "unb": "2201424244205",
        "uc4": "nk4=0%40FY4Jjt%2FkwvvoNfxM5soEYyvPwoWOMQ%3D%3D&id4=0%40U2grEJGHtPgfSuVxGrdzKyLkAnUpdYW6",
        "_nk_": "tb755794817",
        "last_mid": "b2b-2201424244205c3483",
        "__cn_logon__": "true",
        "__cn_logon_id__": "tb755794817",
        "__last_loginid__": "b2b-2201424244205c3483",
        "__last_memberid__": "b2b-2201424244205c3483",
        "union": "{\"amug_biz\":\"comad\",\"amug_fl_src\":\"other\",\"creative_url\":\"https%3A%2F%2Fre.1688.com%2F\",\"creative_time\":1774418600929}",
        "leftMenuLastMode": "COLLAPSE",
        "leftMenuModeTip": "shown",
        "plugin_home_downLoad_cookie": "%E4%B8%8B%E8%BD%BD%E6%8F%92%E4%BB%B6",
        "_user_vitals_session_data_": "{\"user_line_track\":true,\"ul_session_id\":\"yqds1xhxkhf\",\"last_page_id\":\"s.1688.com%2Fs8a56iw7cfm\"}",
        "mtop_partitioned_detect": "1",
        "_m_h5_tk": _m_h5_tk,
        "_m_h5_tk_enc": _m_h5_tk_enc,
        "tfstk": "gozEoj2S_wQFPKW0gS0Pbyj4r0gKV4WfKzMSZ7VoOvDhvkiyrWMst3YkrlkzIRknPMFSaayaHY1LR6ewaR2aAvqQN3YzQSDINHg3Z02gnHaIFvZwaSeZP8PR9bDuE8k7AG_b9W3-rt_PlZNpCZH_WJonqAxg6bKl1DbjZrzrrt6f5hOiv9guOPha3cViBblkqX2kICcxIbxnr8DijjcX-40uE1kiZXYoZ4DnsccoIY0or8DG_bMit40uE5fZwA1UEJLZQDfUvNp3O91JUxNnQUYu-anZ33wt6DUw3DD4ty5O6_hEYxVnQ9o0fTogw0zJwUoztoe-iJvhUYUasyq0nOtIKolzGuPh-F0QJWqmqrXJqWgsLV430QYu_2rn2zmwLOk0J54xSc_cg54TdWUaNQbo1-Mg9y0Pos3E-v0Z6z69-YrgqyiKypXrePPg-uSykLhic348YLxrxfhZh15a7lrOHL7zFEKJ2cSt_x1AM3K-xfhZh15w23naWfkfMsC..",
        "isg": "BEhINhrRtairydlSoXH8M0uLGbZa8az75C_H5wLYv0K-3cxHrgWoi_qbVbWtbWTT"
    }

    url = "https://h5api.m.1688.com/h5/mtop.com.alibaba.cbu.crossborder.lp.keywordsearch/1.0/"

    async with aiohttp.ClientSession(headers=headers, cookies=cookies) as session:
        # 使用 data 参数发送表单数据（注意不是 json）
        async with session.post(url, params=params, data=data) as resp:
            text = await resp.json()
            return text, resp


async def price_info_main(keyword="conure bird bath", _m_h5_tk=None, _m_h5_tk_enc=None):
    try:
        global result_price
        response_json, response_obj = await fetch_keyword_search(keyword, _m_h5_tk, _m_h5_tk_enc)
        price_list = []
        # 收集所有价格
        price_list = [float(i['price']) for i in response_json['data']['result']['data']]
        print(price_list)

        # 计算平均值
        price_avg = sum(price_list) / len(price_list) if price_list else 0
        print("最初", price_avg)

        # 筛选：保留在 [price_avg/2, price_avg*1.5] 范围内的价格
        filtered_prices = [p for p in price_list if not ((price_avg / 2) >= p or (price_avg * 1.5) <= p)]

        print('--------------------------------------------------------------------')
        print(filtered_prices)

        if filtered_prices:
            result_price = sum(filtered_prices) / (len(filtered_prices) + 1)
            print("筛选后", round(result_price, 2))
        else:
            print("筛选后无数据")
        return round(result_price, 2)
    except Exception as e:
        print(e, '令牌过期')
        return None


if __name__ == "__main__":
    keyword = "conure bird bath"
    _m_h5_tk = "88b38449f50fbebf000e88bd1c8ae5d5_1774587898919"
    _m_h5_tk_enc = "d9d00ba54e9b4030ce9585fb3f646cdc"
    asyncio.run(price_info_main(keyword, _m_h5_tk, _m_h5_tk_enc))
