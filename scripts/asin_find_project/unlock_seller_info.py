# -*- coding: utf-8 -*-

"""卖家精灵子账号激活：POST /v2/child-account/unlock"""



from __future__ import annotations



import json

from pathlib import Path

from typing import Any

import asyncio



import requests



# ========== 按需修改 ==========

PARENT_ID = "129425"

CHILD_IDS = ["1805120"]  # 待激活的子账号 id，可填多个

PARENT_LOGIN = "13724333803"

COOKIE_FILE = Path(__file__).with_name("sellersprite_cookies.json")



BASE_HEADERS = {

    "accept": "application/json, text/plain, */*",

    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",

    "origin": "https://www.sellersprite.com",

    "referer": "https://www.sellersprite.com/v3/child-account",

    "sec-ch-ua": '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',

    "sec-ch-ua-mobile": "?0",

    "sec-ch-ua-platform": '"Windows"',

    "sec-fetch-dest": "empty",

    "sec-fetch-mode": "cors",

    "sec-fetch-site": "same-origin",

    "user-agent": (

        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "

        "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0"

    ),

}



# 从浏览器 DevTools 复制最新 Cookie；或写入 sellersprite_cookies.json

DEFAULT_COOKIES = {

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

    "_gaf_fp": "41bce98fda7875332834648b60b7990e",

    "rank-login-user": "0814860871C9FkCZxDgbIiAg5Ab0Nf5j11KWlX9I67RQYy5PKoy2dyasHfFTqxkw0fUALNJ8BG",

    "rank-login-user-info": (

        "eyJuaWNrbmFtZSI6ImFubmEiLCJpc0FkbWluIjpmYWxzZSwiYWNjb3VudCI6IjEzNyoqKiozODAzIiwidG9rZW4iOiIwODE0ODYwODcxQzlGa0NaeERnYklpQWc1QWIwTmY1ajExS1dsWDlJNjdSUVl5NVBLb3kyZHlhc0hmRlRxeGt3MGZVQUxOSjhCRyJ9"

    ),

    "Sprite-X-Token": (

        "eyJhbGciOiJSUzI1NiIsImtpZCI6IjE2Nzk5NjI2YmZlMDQzZTBiYzI5NTEwMTE4ODA3YWExIn0."

        "eyJqdGkiOiJkTkRqRjdRdThHV3NTc2wzaFNDb2JnIiwiaWF0IjoxNzgwNjI2NTgwLCJleHAiOjE3ODA3MTI5ODAsIm5iZiI6MTc4MDYyNjUyMCwic3ViIjoieXVueWEiLCJpc3MiOiJyYW5rIiwiYXVkIjoic2VsbGVyU3BhY2UiLCJpZCI6MTI5NDI1LCJwaSI6bnVsbCwibm4iOiLmt7HlnLPpmL_mlrnntKLnp5HmioDmnInpmZDlhazlj7giLCJzeXMiOiJTU19DTiIsImVkIjoiTiIsInBobiI6IjEzNzI0MzMzODAzIiwiZW0iOiJxdWlnZW5nbmFAMTI2LmNvbSIsIm1sIjoiViIsImVuZCI6MTc4MjUyNzM4MDE1Nn0."

        "ar6YV7GTeDbTX61gRUv2tiPoI9RZe0UFtSG_T8-VSBRXvMq5StJ9ve3rQ9iCQl1XD1krIGCNysmh6xkunZlT8VaGBMmH-mkUlKeoDhem5z2jlSS3bxYVNUeOApKzrP20tiNkv4JypPc7WUTYzKkbXAXZigsxpmGJEDumPohoVtvMxtQ0vUzbxgbQqccR0c5fJY2k8j6aNDxcnTTzd7eqe1kDme-LQRceScpApvsvx5FYxAeGYoka5StiVGC08x9Y_RiS0f-RkqlnA7f0F378bbgV6q1w-kbUGM8gQXimo7iD5IGkEkx-4qQiHCLH47H2jbzVPCL7TubocMJTW4ZWJw"

    ),

    "ao_lo_to_n": (

        '"0814860871C9FkCZxDgbIiAg5Ab0Nf5p+j0SONd6z6/JD68hvA5Eg5PdolsLUEWcoDTCxyb2uMt/TIbYj6HHAjexjC55FsWYrwJKpT8vMz8FdNWyRiaC0="'

    ),

    "JSESSIONID": "D4B1AD953670A1BDCD52C0B7A15ACF86",

    "Hm_lpvt_e0dfc78949a2d7c553713cb5c573a486": "1780628409",

    "_gcl_au": "1.1.1826782346.1775543240.1260390763.1780628411.1780628411",

    "_ga_38NCVF2XST": "GS2.1.s1780626572$o63$g1$t1780628613$j59$l0$h889234456",

    "_ga_CN0F80S6GL": "GS2.1.s1780626572$o105$g1$t1780628613$j59$l0$h0",

    "_clsk": "8rpbkd%5E1780629363405%5E14%5E1%5En.clarity.ms%2Fcollect",

}





def refresh_parent_cookies(cookies: dict[str, str] | None = None) -> dict[str, str]:

    """用父账号登录刷新 rank-login-user 等 Cookie。"""

    from main_seller_wizard_set_cookie import set_cookie_main



    base = dict(cookies or load_cookies())

    config = asyncio.run(set_cookie_main(PARENT_LOGIN))

    print('父账号登录结果:', config)

    if config.get('rank-login-user'):

        base['rank-login-user'] = config['rank-login-user']

    if config.get('rank-login-user-info'):

        base['rank-login-user-info'] = config['rank-login-user-info']

    return base





def load_cookies() -> dict[str, str]:

    if COOKIE_FILE.exists():

        data = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))

        if isinstance(data, dict):

            return {str(k): str(v) for k, v in data.items()}

    return dict(DEFAULT_COOKIES)





def build_headers(cookies: dict[str, str]) -> dict[str, str]:

    headers = dict(BASE_HEADERS)

    token = cookies.get("Sprite-X-Token")

    if token:

        headers["Sprite-X-Token"] = token

    return headers





def request_json(

    method: str,

    url: str,

    *,

    cookies: dict[str, str],

    params: dict | None = None,

    files: dict | None = None,

    timeout: int = 30,

) -> tuple[int, Any]:

    resp = requests.request(

        method,

        url,

        headers=build_headers(cookies),

        cookies=cookies,

        params=params,

        files=files,

        timeout=timeout,

    )

    try:

        body: Any = resp.json()

    except ValueError:

        body = resp.text

    return resp.status_code, body





def quota(cookies: dict[str, str] | None = None) -> tuple[int, Any]:

    """仅检查登录态，不能代表子账号已激活。"""

    cookies = cookies or load_cookies()

    return request_json(

        "GET",

        "https://www.sellersprite.com/v3/api/client/quota",

        cookies=cookies,

    )





def info_list(

    parent_id: str = PARENT_ID,

    cookies: dict[str, str] | None = None,

) -> tuple[int, Any]:

    cookies = cookies or load_cookies()

    return request_json(

        "GET",

        "https://www.sellersprite.com/v3/api/sub-client",

        cookies=cookies,

        params={"parentId": parent_id, "page": "1", "size": "50"},

    )





def unlock(

    child_ids: list[str] | str,

    parent_id: str = PARENT_ID,

    cookies: dict[str, str] | None = None,

) -> tuple[int, Any]:

    """激活/解锁子账号。必须用 multipart/form-data 提交。"""

    cookies = cookies or load_cookies()

    if isinstance(child_ids, str):

        ids_value = child_ids

    else:

        ids_value = ",".join(str(i).strip() for i in child_ids if str(i).strip())



    files = {

        "ids": (None, ids_value),

        "parentId": (None, str(parent_id)),

        "currentId": (None, str(parent_id)),

    }

    return request_json(

        "POST",

        "https://www.sellersprite.com/v2/child-account/unlock",

        cookies=cookies,

        files=files,

    )





def extract_child_rows(payload: Any) -> list[dict[str, Any]]:

    if not isinstance(payload, dict):

        return []

    data = payload.get("data")

    if isinstance(data, dict):

        for key in ("list", "records", "items", "rows"):

            rows = data.get(key)

            if isinstance(rows, list):

                return [r for r in rows if isinstance(r, dict)]

    if isinstance(data, list):

        return [r for r in data if isinstance(r, dict)]

    return []





def print_child_summary(label: str, payload: Any, focus_ids: set[str] | None = None) -> None:

    print(f"\n===== {label} =====")

    if not isinstance(payload, dict):

        print(payload)

        return



    code = payload.get("code")

    message = payload.get("message")

    print(f"code={code!r}, message={message!r}")



    rows = extract_child_rows(payload)

    if not rows:

        print(json.dumps(payload, ensure_ascii=False, indent=2))

        return



    for row in rows:

        cid = str(row.get("id") or row.get("clientId") or row.get("subClientId") or "")

        if focus_ids and cid and cid not in focus_ids:

            continue

        status = row.get("status") or row.get("lockStatus") or row.get("state")

        account = row.get("account") or row.get("phone") or row.get("email") or row.get("nickname")

        print(f"  id={cid}  status={status!r}  account={account!r}")





def activate_children(

    child_ids: list[str] | None = None,

    parent_id: str = PARENT_ID,

) -> tuple[bool, str]:

    """

    激活子账号。

    返回 (是否成功, 说明)。

    """

    child_ids = [str(i) for i in (child_ids or CHILD_IDS)]

    focus = set(child_ids)

    cookies = refresh_parent_cookies()



    print("1) 检查登录态 (quota，仅表示 Cookie 是否有效)...")

    q_status, q_body = quota(cookies)

    print(f"   HTTP {q_status} -> {q_body}")

    if q_status != 200:

        return False, f'父账号登录态异常 HTTP {q_status}：{q_body}'



    print("\n2) 激活前子账号列表...")

    before_status, before_body = info_list(parent_id, cookies)

    print(f"   HTTP {before_status}")

    print_child_summary("激活前", before_body, focus)



    print("\n3) 调用 unlock 激活...")

    u_status, u_body = unlock(child_ids, parent_id, cookies)

    print(f"   HTTP {u_status} -> {u_body}")

    if u_status != 200:

        return False, f'unlock HTTP {u_status}：{u_body}'

    if isinstance(u_body, dict) and u_body.get("code") not in (None, "OK", 0, "0"):

        return False, f'unlock 业务失败：{u_body}'



    print("\n4) 激活后子账号列表...")

    after_status, after_body = info_list(parent_id, cookies)

    print(f"   HTTP {after_status}")

    print_child_summary("激活后", after_body, focus)

    print("\n完成。请以「激活后」列表中的 status 是否变化为准，quota 的 OK 不代表激活成功。")

    return True, '子账号解禁完成'





if __name__ == "__main__":

    ok, msg = activate_children()

    if not ok:

        raise SystemExit(msg)

    print(msg)

