import asyncio

import httpx


async def get_seller_wizard_set_cookie(username: str, password: str =''):
    """
    :param username: 用户名称和密码一致，在某一个账户禁用后要重新去卖家精灵重新获取新账号的headers和cookies，因为里面有值是和账户绑定的
    :param password:
    :return:
    """
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "cache-control": "max-age=0",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://www.sellersprite.com",
        "priority": "u=0, i",
        "referer": "https://www.sellersprite.com/cn/w/user/login",
        "sec-ch-ua": "\"Chromium\";v=\"148\", \"Microsoft Edge\";v=\"148\", \"Not/A)Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"
    }
    cookies = {
        "ecookie": "0ZIEHmkUOkj5O0bP_CN",
        "_ga": "GA1.1.1624075988.1775543239",
        "MEIQIA_TRACK_ID": "3AsDAuhuMQUzdUXTUNdrluZiyhZ",
        "MEIQIA_VISIT_ID": "3C1BYbL6GIc5O4LO6RfcmKlXqT9",
        "p_c_size": "50",
        "k_size": "50",
        "current_guest": "PzM5Kow3aWQD_260410-109254",
        "HMACCOUNT": "949CAE7CB69976AC",
        "_fp": "e25cc0d8b415349a3beafac3421bf1ca",
        "e4ad641898d3d0f48da7": "9b8c76bd99e68837048d00c922f59e48",
        "4da9ea78556c2f3e2f9b": "b39b0a4eb591fc1e32e1fe6af3670f57",
        "397dfe035873c8d2315b": "103af19256e18a5bc14914795e62a93c",
        "Hm_lvt_e0dfc78949a2d7c553713cb5c573a486": "1780301940",
        "_clck": "ycfc14%5E2%5Eg6k%5E0%5E2288",
        "_gcl_au": "1.1.1826782346.1775543240.432901189.1780383054.1780383054",
        "ebdde9bd6f45433c1c41": "728a1ac9571cee1f632e823d77c9433c",
        "_gaf_fp": "296aca6530811998e69f96719174e46c",
        "Sprite-X-Token": "eyJhbGciOiJSUzI1NiIsImtpZCI6IjE2Nzk5NjI2YmZlMDQzZTBiYzI5NTEwMTE4ODA3YWExIn0.eyJqdGkiOiJIcGh3eGFCSnlDOUpkdzU0cHJobktnIiwiaWF0IjoxNzgwMzgzNDcwLCJleHAiOjE3ODA0Njk4NzAsIm5iZiI6MTc4MDM4MzQxMCwic3ViIjoieXVueWEiLCJpc3MiOiJyYW5rIiwiYXVkIjoic2VsbGVyU3BhY2UiLCJpZCI6MTgwNTEyMCwicGkiOjEyOTQyNSwibm4iOiJJVEJNMDAwMDY3Iiwic3lzIjoiU1NfQ04iLCJlZCI6Ik4iLCJlbSI6IklUQk0wMDAwNjdAc2VsbGVyc3ByaXRlLmNvbSIsIm1sIjoiViIsImVuZCI6MTc4MjU0MzQ3MDU0Nn0.VqZsxM61yLgBaubJyYUjPoW0mTj-szjg8aPFmOQbtnQBfga017YVuW2OcOcUw4Z1AI5JeVgGFdrzghkWkhydJrdJ6_L7znuAr-DizDuVE7vQecjWWmFmLpFFgjgIsfGVE7B2lLx__cpx7oqw37SmVuJmwu6MwOsqtXVdqZrsO0r_RH4yBFU3SpyZu8L5x8wiGq7UiWLg_6Q9j3S530rlZWMhVWBrzt_dMuflyecdj3JFLGVLqPLwfFYCs3waLYH5INKCV0K3ARoWQ8Aso9A69AKcYDUECV6aNroPBBCQkNO4T-0tlWUe_lCVF221QB5NlDM_bO8bfrp6vNyLKe-duQ",
        "ao_lo_to_n": "\"0701440871A++WqsjzTTKriM3w4ZyMh/1tcut7IaTQO8F8mvI1XB/4dlql0mJxERc2gKUPSxMZu5+vE5ZtUb7J3I/tJAkxAjWpGgvNqjlw0ewC2kv99jA=\"",
        "Hm_lpvt_e0dfc78949a2d7c553713cb5c573a486": "1780383505",
        "_clsk": "1ndt70%5E1780383506130%5E13%5E1%5En.clarity.ms%2Fcollect",
        "JSESSIONID": "EDA07B00E78038AE02C3F1943C40B4B4",
        "_ga_CN0F80S6GL": "GS2.1.s1780383025$o102$g1$t1780383513$j11$l0$h0",
        "_ga_38NCVF2XST": "GS2.1.s1780383025$o60$g1$t1780383513$j11$l0$h1266767465"
    }
    url = "https://www.sellersprite.com/w/user/signin"
    data = {
        "callback": "",
        "auto_login_token": "Y",
        "email": username,
        "password": password,
        "autoLogin": "Y"
    }

    async with httpx.AsyncClient() as client:
        # 设置初始 cookies
        client.cookies.update(cookies)

        # 禁止跟随重定向
        response = await client.post(
            url,
            headers=headers,
            data=data,
            follow_redirects=False
        )

        print("状态码:", response.status_code)

        # 获取所有 Set-Cookie 头
        set_cookies = response.headers.get_list('set-cookie')
        print("\n--- 所有 Set-Cookie ---")
        for cookie in set_cookies:
            print(cookie)

        auth_names = {
            'rank-login-user',
            'rank-login-user-info',
            'Sprite-X-Token',
            'ao_lo_to_n',
            'JSESSIONID',
        }
        user_info = {}
        for cookie in response.cookies.jar:
            if cookie.name not in auth_names:
                continue
            val = cookie.value
            if cookie.name == 'rank-login-user-info':
                val = val.replace('"', '')
            user_info[cookie.name] = val

        return user_info

async def set_cookie_main(username:str,password:str=''):
    result = await get_seller_wizard_set_cookie(username, password)
    print(result)
    return result




if __name__ == '__main__':
    asyncio.run(set_cookie_main("ITBM000067","ITBM000067"))