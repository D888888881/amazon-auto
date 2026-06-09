import requests


def get_sif_cookie():
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Connection": "keep-alive",
        "Referer": "https://www.sif.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0",
        "authorization": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ3ZWNoYXRpZCI6Im90SkwwNXc4MzRhenJ0Z3NRTVJDV0x5NmsxQjgiLCJ1c2VyU2FsdCI6IkxMdGxiZEg0IiwiZXhwIjoxNzgwODAyNTI5LCJ1c2VyaWQiOiJqbXhOMTRiMW45NDMzM3BRNzAzSUFld3EiLCJwbGF0Zm9ybSI6Im9mZmljaWFsIn0.dirjjLnGCXb4P4JexSV3ZIGC7Pkwij0dNAgoVtJx9cg",
        "sec-ch-ua": "\"Chromium\";v=\"148\", \"Microsoft Edge\";v=\"148\", \"Not/A)Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\""
    }
    cookies = {
        "_clck": "q0cuqr%5E2%5Eg56%5E0%5E2291",
        "Hm_lvt_8d71bef53342fdb284ff83594f3b97ff": "1778479892",
        "Hm_lpvt_8d71bef53342fdb284ff83594f3b97ff": "1780370660"
    }
    url = "https://www.sif.com/api/user/conch/info"
    params = {
        "country": "US",
        "_t": "1780370660029",
        "_m": "Sif_d88a-a869-4154-b5dd-3ed9-1773713262017"
    }
    response = requests.get(url, headers=headers, cookies=cookies, params=params)

    # 直接从响应 cookies 中获取 sif_token 的值
    sif_token = response.cookies.get("sif_token")
    print("提取的 sif_token:", sif_token)

    with open("config_file/sif_token.txt", "w") as f:
        f.write(sif_token if sif_token else "未找到 sif_token")
    # 如果你想看完整的响应内容
    # print(response.text)
    # return sif_token


if __name__ == '__main__':
    get_sif_cookie()