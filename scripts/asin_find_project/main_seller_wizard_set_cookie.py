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
        "397dfe035873c8d2315b": "103af19256e18a5bc14914795e62a93c",
        "Hm_lvt_e0dfc78949a2d7c553713cb5c573a486": "1780301940",
        "ebdde9bd6f45433c1c41": "728a1ac9571cee1f632e823d77c9433c",
        "a3cb590d50a15f47bf06": "691f1356d177cee13417a452cfbada3e",
        "_clck": "ycfc14%5E2%5Eg6n%5E0%5E2288",
        "_gcl_au": "1.1.1826782346.1775543240.1260390763.1780628411.1780628411",
        "_gaf_fp": "655bf6e86e45741b3613afa142d3aaef",
        "Sprite-X-Token": "eyJhbGciOiJSUzI1NiIsImtpZCI6IjE2Nzk5NjI2YmZlMDQzZTBiYzI5NTEwMTE4ODA3YWExIn0.eyJqdGkiOiJBaWZhaUFsU0lNeVFiWTNTQVhTeW1nIiwiaWF0IjoxNzgwNjUxMzI1LCJleHAiOjE3ODA3Mzc3MjUsIm5iZiI6MTc4MDY1MTI2NSwic3ViIjoieXVueWEiLCJpc3MiOiJyYW5rIiwiYXVkIjoic2VsbGVyU3BhY2UiLCJpZCI6MTI5NDI1LCJwaSI6bnVsbCwibm4iOiLmt7HlnLPpmL_mlrnntKLnp5HmioDmnInpmZDlhazlj7giLCJzeXMiOiJTU19DTiIsImVkIjoiTiIsInBobiI6IjEzNzI0MzMzODAzIiwiZW0iOiJxdWlnZW5nbmFAMTI2LmNvbSIsIm1sIjoiViIsImVuZCI6MTc4MjU1MjEyNTMxMn0.FIWT17XFv_FuE4p48mdx4s8fU4XXlcVVJKbpCXUG_ke2NnX3TrW2xh4jbF_PafUcabgfg47ZRkwPeYAndLHwzQi21cqLJdnF_UesECwKETGye3Hen9xdYQu2I37LKcUD_2OqkIGYcf9EsOXi0Vn-FebC-hDc0yQKuOK13OO7VrgVZBNWusawz6Tv0l2V4XeRxl6EaDYzqjBI5w6lYgaQ2m6W_K942i1FmVCIKTWWQFkfxQHLEkJZFsNks2b6GqTEHuN1x2qDY0IDxKNOmLsUn8pBodi1ixcThp2hez5aHKXB4SJFdud2nH1oC0COojarYF-OrS_Dn8klOwew_5OKFA",
        "ao_lo_to_n": "\"5298070871dYrxuIs+yQhx1FCbIRyedHjyVVvlnhwtVSkqUVvL1j09fA6SxlnGvljJ2cRvPO3ZUi3r6SHdIhkRzuEUEjkx7oaqUUZJMOoFkXkvSlURoEg=\"",
        "Hm_lpvt_e0dfc78949a2d7c553713cb5c573a486": "1780651353",
        "_clsk": "1sdgtp0%5E1780651353328%5E7%5E1%5En.clarity.ms%2Fcollect",
        "JSESSIONID": "5E25C4F471EA21DA328A3393AFF1E345",
        "_ga_38NCVF2XST": "GS2.1.s1780649811$o64$g1$t1780651357$j60$l0$h327677933",
        "_ga_CN0F80S6GL": "GS2.1.s1780649811$o106$g1$t1780651357$j60$l0$h0"
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

        user_info = {}
        found_count = 0

        # 从响应 cookies 中提取需要的字段
        for cookie in response.cookies.jar:
            if cookie.name == 'rank-login-user-info':
                user_info['rank-login-user-info'] = cookie.value.replace('"', '')  # 去掉引号
                found_count += 1
            elif cookie.name == 'rank-login-user':
                user_info['rank-login-user'] = cookie.value
                found_count += 1

            if found_count == 2:
                break

        return user_info

async def set_cookie_main(username:str,password:str=''):
    result = await get_seller_wizard_set_cookie(username, password)
    print(result)
    return result




if __name__ == '__main__':
    asyncio.run(set_cookie_main("13724333803"))