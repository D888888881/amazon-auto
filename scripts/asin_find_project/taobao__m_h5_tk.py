import requests

def get_m_h5_tk():


    headers = {
        "accept": "*/*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referer": "https://www.taobao.com/",
        "sec-ch-ua": "\"Chromium\";v=\"142\", \"Microsoft Edge\";v=\"142\", \"Not_A Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "script",
        "sec-fetch-mode": "no-cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0"
    }
    cookies = {
        "havana_lgc_exp": "1796261761606",
        "mtop_partitioned_detect": "1",
        "xlly_s": "1",
        "t": "59a12a874c2c5f75bd232a5c5e0e75c1",
        "_tb_token_": "3eae6b1beab6e",
        "thw": "cn",
        "sca": "fd3d6cb6",
        "cna": "wDo0IaCg/UUCAXuxNYvFAIG/",
        "_samesite_flag_": "true",
        "cookie2": "145f4b181bc97f804a58783a74170dde",
        "isg": "BKioJvUhVX2lSnhiXglsr1hyeZa60QzbeQi2zWLZ1CMWvUgnCuB_amL-tVVNiMSz",
        "tfstk": "gZzEavtoewQFl2v1RR3ygNTt5A3KY4WXLzMSZ7VoOvDHRe9ubSerd_IKRlkzIRk3U7CKZY2uUYZCfZNL943lhb7flWLWTe5U84v7s2hWnZopSZNL94deEsZGla-itRLHqY2oSccIG4cnE0cG_blqE4DnqdxiiADor8YlSNcqNevnt0fasAhorY2or1uiBb0oE80owSF3ZFljx1_JOAeMgPmEnWDwu5UZtqxLtA-BAPrnYxYrQUYu7XPoVzeBugM0Dvij3Rb684PiaRobYt8UU7VYqczyK6w0tJUYqW7Nn2aLtomuoTKu32yrmymwZE3ESA0ZsrfWDAaZd84EjsTqVV4jm2q1X9iS8jyuJJRyr-V_GynTztJiekGxSbzRi3krqg-pefDpwzEeE3on6fkf_1PhfP6wzqsat3K-jqhZh6GB23nn6fkf_1-J2ccx_x1IO"
    }
    url = "https://h5api.m.taobao.com/h5/mtop.tmall.kangaroo.core.service.route.aldlampservicefixedresv2/1.0/"
    params = {
        "jsv": "2.7.2",
        "appKey": "12574478",
        "t": "1765161839641",
        "sign": "2d8c7334cec01b1d55ef88b5de1dcafe",
        "api": "mtop.tmall.kangaroo.core.service.route.AldLampServiceFixedResV2",
        "v": "1.0",
        "timeout": "3000",
        "dataType": "jsonp",
        "valueType": "original",
        "jsonpIncPrefix": "tbpc",
        "ttid": "1@tbwang_windows_1.0.0#pc",
        "type": "originaljsonp",
        "callback": "mtopjsonptbpc1",
        "data": "{\"params\":\"{\\\"resId\\\":\\\"33718589,33972676,33665512,41905558,33667440\\\",\\\"bizId\\\":\\\"443,443,443,443,443\\\"}\"}"
    }
    response = requests.get(url, headers=headers, cookies=cookies, params=params)

    def extract_cookie_value(cookie_str, cookie_name):
        """从set-cookie字符串中提取指定cookie的值"""
        # 按逗号分割不同的cookie
        cookies = cookie_str.split(', ')

        for cookie in cookies:
            # 找到以目标cookie名开头的部分
            if cookie.startswith(f"{cookie_name}="):
                # 提取值（第一个分号之前的部分）
                value_part = cookie.split(';')[0]
                return value_part.split('=', 1)[1]

        return None

    set_cookie_str = response.headers.get('set-cookie', '')

    # 提取需要的cookie值
    _m_h5_tk = extract_cookie_value(set_cookie_str, '_m_h5_tk')
    _m_h5_tk_enc = extract_cookie_value(set_cookie_str, '_m_h5_tk_enc')

    print(f"_m_h5_tk: {_m_h5_tk}")
    print(f"_m_h5_tk_enc: {_m_h5_tk_enc}")
    return {'_m_h5_tk_enc': _m_h5_tk_enc, '_m_h5_tk': _m_h5_tk}

if __name__ == '__main__':
    get_m_h5_tk()