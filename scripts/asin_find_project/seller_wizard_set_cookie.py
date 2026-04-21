import asyncio

import httpx


async def get_seller_wizard_set_cookie(username: str, password: str):
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "cache-control": "max-age=0",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://www.sellersprite.com",
        "priority": "u=0, i",
        "referer": "https://www.sellersprite.com/cn/w/user/login",
        "sec-ch-ua": "\"Chromium\";v=\"146\", \"Not-A.Brand\";v=\"24\", \"Microsoft Edge\";v=\"146\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0"
    }
    cookies = {
        "ecookie": "0ZIEHmkUOkj5O0bP_CN",
        "_ga": "GA1.1.1624075988.1775543239",
        "MEIQIA_TRACK_ID": "3AsDAuhuMQUzdUXTUNdrluZiyhZ",
        "MEIQIA_VISIT_ID": "3C1BYbL6GIc5O4LO6RfcmKlXqT9",
        "_fp": "982da2ff9374239947902667704f94ef",
        "p_c_size": "50",
        "k_size": "50",
        "84a0e9f391fc41713ea0": "9228a761243f38b52daae44d4964b30c",
        "7581a0c6f4f448143b7f": "f241ca4b26b555b93a8ad142f7cce275",
        "current_guest": "PzM5Kow3aWQD_260410-109254",
        "7c1fe404463799b52b80": "0d66dc0ebdd249548da407caa9131b40",
        "40c1a24ba65ba29f5c8b": "39653a56e4c20c5aa8a6bd3d386c8d9b",
        "Hm_lvt_e0dfc78949a2d7c553713cb5c573a486": "1775729639,1775786924,1776042652,1776160657",
        "HMACCOUNT": "949CAE7CB69976AC",
        "_gcl_au": "1.1.1826782346.1775543240.933927248.1776160688.1776160688",
        "_gaf_fp": "b0c03df54705ada0312a329e5350d323",
        "Sprite-X-Token": "eyJhbGciOiJSUzI1NiIsImtpZCI6IjE2Nzk5NjI2YmZlMDQzZTBiYzI5NTEwMTE4ODA3YWExIn0.eyJqdGkiOiJybjloSGRKX0Rjd2paYUc3SkZxRExBIiwiaWF0IjoxNzc2MTYwNzcyLCJleHAiOjE3NzYyNDcxNzIsIm5iZiI6MTc3NjE2MDcxMiwic3ViIjoieXVueWEiLCJpc3MiOiJyYW5rIiwiYXVkIjoic2VsbGVyU3BhY2UiLCJpZCI6MTY5ODc4MiwicGkiOjEyOTQyNSwibm4iOiJJVEJNMDAwMDAxIiwic3lzIjoiU1NfQ04iLCJlZCI6Ik4iLCJlbSI6IklUQk0wMDAwMDFAc2VsbGVyc3ByaXRlLmNvbSIsIm1sIjoiViIsImVuZCI6MTc4MjU1NDM3MjgxNH0.gvaHXrm7dXwfEapYS2IAko6XIGMhEOWdnz0VjQtB0RR9KkFqZUjJt3oqjqzdi2a2CbUsR15hdZAewf42Yd9oHBDA_Rk0_1n_VHlBXIFT-f0xzuI5pqE2RIG6rR0vqPRV9je7e-BozPAgg2fzc9sChFnjp3UNLMPpTSJU-Df8wA2GOlD22Gj5hL-gYrh_EYPbfPLMj1-c_eRRn77LRU9-5BTVRKbaoxWwOaxfpLrEePahh5eG1GQ4NcW3BYGrRStIiiO0odoU7gcnNeIGnI5s-0PmE6irnsoTUrW8miV77ETChH1aG6GUafzbNVH86mY5HERDuIHWzksbMjQx3AukKQ",
        "ao_lo_to_n": "\"2738126771wgRGBR8tGt6M09SwNJGVPSkOpk0LOEhVhr1KbThaeu3kSeNoG+OuJtHRX93iETDjC/H6X+e9LMf/rmy657w/CzgHUdwjOBlZQX7eXE6z2wc=\"",
        "Hm_lpvt_e0dfc78949a2d7c553713cb5c573a486": "1776161013",
        "_clck": "ycfc14%5E2%5Eg58%5E0%5E2288",
        "_ga_CN0F80S6GL": "GS2.1.s1776237929$o76$g0$t1776237929$j60$l0$h0",
        "_clsk": "ijt3oe%5E1776237931471%5E2%5E1%5El.clarity.ms%2Fcollect",
        "4b576630834ee8190509": "c32875d8e6a75f835e5ece4baa1c7cd5",
        "JSESSIONID": "F1CB347F579BE2D03496A964265BA28A",
        "_ga_38NCVF2XST": "GS2.1.s1776237929$o27$g1$t1776237962$j27$l0$h1857658276"
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

async def set_cookie_main(username:str,password:str):
    result = await get_seller_wizard_set_cookie(username, password)
    print(result)
    return result

if __name__ == '__main__':
    asyncio.run(set_cookie_main("ITBM000001","ITBM000001"))