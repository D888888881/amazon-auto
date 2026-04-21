import asyncio
import json
import time
import hashlib
import aiohttp
from async_imageBase64_api import convert_to_jpeg_base64_async



class AsyncImageSearchAPI:
    def __init__(self,_m_h5_tk, _m_h5_tk_enc,new_sign,image_path):
        self.image_path = image_path
        self.new_sign = new_sign
        # 原始请求头（保持不变）
        self.headers = {
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

        self.cookies = {
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
            "tfstk": "gpYsoEciXR26ggctHRlUOx_ZpCQjTXurWS1vZIUaMNQOlq9XN5SAXsFL999cQG793ZtXEds2QZoghr6pBOSZsN3XcQ950r7N0qpBiIWwu1kGMtBBBrSw3Et3lQAD7fbqsNAGoZHrU4yXsCb03k1B3E_dJsfquPBADNbdoQIKM4uysCFN6bRKzhWouSCfHZIODkCdK1aYXKUA9X1AgREABKdKO9f4WsEOXwBdasNOkZpv9X1cp1QAXKdKOsXdHbx8dso1MCGYe7OyuJJX69aYkF3cfTadp6fBR2sOUCL_krhc1G6J69M12HkfvIjXoS4fcCKkn_pTBx6DRBL92LHUbOK5GQ-X6VUd7FA92iL-nodN8O_pW3NYkB_6XiYAARMCeFAprwIEybOp-dRMRIPxk6JPpCYOl4hl5NBOR6YqKPBXvnLNjZ2thtYB9FKf4HaPF0JYcWsul66rOXZ0mI8W_XJbzsdPX6ftzXGQdojOt66rOXZ0mGCh63lIOJZc.",
            "isg": "BPb2HDH7g4IlOHcYg9eqyYlVRyz4FzpR5iEpLWDfVll0o5Q9yKPEYAoVu3_PCzJp"
        }


    def get_timestamp_and_sign(self, app_key, data, token,timestamp=None):
        """同步工具函数，生成时间戳和签名"""
        if timestamp is None:
            timestamp = int(time.time() * 1000)
        sign_str = f"{token}&{timestamp}&{app_key}&{data}"
        sign = hashlib.md5(sign_str.encode()).hexdigest()
        return timestamp, sign


    async def get_images_id(self,session: aiohttp.ClientSession):
        """异步获取图片 ID"""
        url = "https://h5api.m.1688.com/h5/mtop.com.alibaba.cbu.crossborder.getimageid/1.0/"

        # 原始 data1 JSON 字符串（占位符）
        data1 = '{"bizType":"selectionTool","customerId":"sellerspriteLP","language":"zh","currency":"CNY","imageBase64":"images"}'

        # 调用异步函数获取图片 Base64 信息
        # 注意：images_base64_main 应该是异步函数，返回 JSON 字符串
        image_info_json = await convert_to_jpeg_base64_async(self.image_path)   # 假设返回字符串
        image_info = json.loads(image_info_json)                  # 转换为字典

        # 替换 data1 中的 imageBase64
        data_dict = json.loads(data1)
        data_dict["imageBase64"] = image_info["imageBase64"]
        new_data1 = json.dumps(data_dict, separators=(',', ':'))

        # 生成签名
        timestamp, sign = self.get_timestamp_and_sign(
            "12574478",
            new_data1,
            self.new_sign,

        )

        # 请求参数
        params = {
            "jsv": "2.7.5",
            "appKey": "12574478",
            "t": timestamp,
            "sign": sign,
            "type": "originaljson",
            "v": "1.0",
            "timeout": "20000",
            "ecode": "0",
            "dataType": "json",
            "api": "mtop.com.alibaba.cbu.crossBorder.getImageId"
        }

        data = {"data": new_data1}

        # POST 数据
        async with session.post(url, headers=self.headers, cookies=self.cookies, params=params, data=data) as resp:
            response_text = await resp.text()
            print(response_text,'22222')

            return await resp.json()


    async def get_price_info(self):
        """异步获取价格信息"""
        url = "https://h5api.m.1688.com/h5/mtop.com.alibaba.cbu.crossborder.lp.imagesearch/1.0/"

        # 创建 ClientSession
        async with aiohttp.ClientSession() as session:
            # 1. 获取 imageId
            image_id_data = await self.get_images_id(session)  # 注意：传入 session 以便复用连接
            image_id = image_id_data['data']['result']
            # 2. 构建 searchParam 内部字典
            search_param_dict = {
                "imageId": image_id,
                "beginPage": 1,
                "pageSize": 30,
                "poolId": "52303046"
            }
            search_param_str = json.dumps(search_param_dict, separators=(',', ':'))

            # 3. 构建整个请求数据字典
            data_dict = {
                "bizType": "selectionTool",
                "customerId": "sellerspriteLP",
                "language": "zh",
                "currency": "CNY",
                "searchParam": search_param_str
            }

            # 4. 序列化为 JSON 字符串
            new_data1 = json.dumps(data_dict, separators=(',', ':'))

            # 5. 生成签名
            timestamp, sign = self.get_timestamp_and_sign(
                "12574478",
                new_data1,
                self.new_sign
            )

            # 6. 请求参数
            params = {
                "jsv": "2.7.5",
                "appKey": "12574478",
                "t": timestamp,
                "sign": sign,
                "type": "originaljson",
                "v": "1.0",
                "timeout": "20000",
                "ecode": "0",
                "dataType": "json",
                "api": "mtop.com.alibaba.cbu.crossBorder.lp.imageSearch"
            }

            # 7. POST 数据
            data = {"data": new_data1}

            async with session.post(url, headers=self.headers, cookies=self.cookies, params=params, data=data) as resp:
                response_text = await resp.text()
                print(response_text)
                print(resp)
                print(data)
                return await resp.json()



async def async_price_info_main(image_path, _m_h5_tk, _m_h5_tk_enc):
    try:
        new_sign = _m_h5_tk.split('_')[0]
        print(new_sign)
        global result_price
        search_object = AsyncImageSearchAPI(_m_h5_tk,_m_h5_tk_enc,new_sign,image_path)
        response_json = await search_object.get_price_info()
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
    asyncio.run(async_price_info_main("images/B0FWJ8HNCB.jpg", "cf27941be4bdc812d693957f03dfcd73_1776050110991", "0a6e88ee9b532cd5de05daf00d3e36bc"))