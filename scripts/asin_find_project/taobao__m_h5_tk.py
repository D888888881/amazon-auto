import json
import time
from pathlib import Path

import requests

_SCRIPT_DIR = Path(__file__).resolve().parent
TAOBAO_COOKIES_PATH = _SCRIPT_DIR / 'config_file' / 'taobao_cookies.json'


def _load_taobao_config_from_file() -> dict | None:
    if not TAOBAO_COOKIES_PATH.is_file():
        return None
    try:
        with open(TAOBAO_COOKIES_PATH, encoding='utf-8') as f:
            config = json.load(f)
        result: dict[str, str] = {}
        for item in config:
            name = item.get('name')
            if name in ('_m_h5_tk', '_m_h5_tk_enc'):
                value = str(item.get('value') or '').strip()
                if value:
                    result[name] = value
        if result.get('_m_h5_tk') and result.get('_m_h5_tk_enc'):
            return result
    except (OSError, json.JSONDecodeError, TypeError) as e:
        print(f'读取本地淘宝 cookie 失败: {e}')
    return None


def get_m_h5_tk(retries: int = 3, timeout: float = 15.0) -> dict:
    headers = {
        "accept": "*/*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referer": "https://www.taobao.com/",
        "sec-ch-ua": '"Chromium";v="142", "Microsoft Edge";v="142", "Not_A Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "script",
        "sec-fetch-mode": "no-cors",
        "sec-fetch-site": "same-site",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0"
        ),
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
        "tfstk": (
            "gZzEavtoewQFl2v1RR3ygNTt5A3KY4WXLzMSZ7VoOvDHRe9ubSerd_IKRlkzIRk3U7CKZY2uUYZCfZNL943lhb7flWLWTe5U84v7s2hWnZopSZNL94deEsZGla-itRLHqY2oSccIG4cnE0cG_blqE4DnqdxiiADor8YlSNcqNevnt0fasAhorY2or1uiBb0oE80owSF3ZFljx1_JOAeMgPmEnWDwu5UZtqxLtA-BAPrnYxYrQUYu7XPoVzeBugM0Dvij3Rb684PiaRobYt8UU7VYqczyK6w0tJUYqW7Nn2aLtomuoTKu32yrmymwZE3ESA0ZsrfWDAaZd84EjsTqVV4jm2q1X9iS8jyuJJRyr-V_GynTztJiekGxSbzRi3krqg-pefDpwzEeE3on6fkf_1PhfP6wzqsat3K-jqhZh6GB23nn6fkf_1-J2ccx_x1IO"
        ),
    }
    url = (
        "https://h5api.m.taobao.com/h5/mtop.tmall.kangaroo.core.service.route."
        "aldlampservicefixedresv2/1.0/"
    )
    params = {
        "jsv": "2.7.2",
        "appKey": "12574478",
        "t": str(int(time.time() * 1000)),
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
        "data": (
            '{"params":"{\\"resId\\":\\"33718589,33972676,33665512,41905558,33667440\\",'
            '\\"bizId\\":\\"443,443,443,443,443\\"}"}'
        ),
    }

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(
                url,
                headers=headers,
                cookies=cookies,
                params=params,
                timeout=timeout,
            )
            response.raise_for_status()
            set_cookie_str = response.headers.get('set-cookie', '')
            _m_h5_tk = _extract_cookie_value(set_cookie_str, '_m_h5_tk')
            _m_h5_tk_enc = _extract_cookie_value(set_cookie_str, '_m_h5_tk_enc')
            if not _m_h5_tk or not _m_h5_tk_enc:
                raise RuntimeError('淘宝响应中未返回 _m_h5_tk / _m_h5_tk_enc')
            print(f"_m_h5_tk: {_m_h5_tk}")
            print(f"_m_h5_tk_enc: {_m_h5_tk_enc}")
            return {'_m_h5_tk_enc': _m_h5_tk_enc, '_m_h5_tk': _m_h5_tk}
        except (requests.RequestException, RuntimeError) as e:
            last_err = e
            if attempt < retries:
                wait = attempt * 2
                print(f'获取淘宝 token 失败（第 {attempt}/{retries} 次）: {e}，{wait}s 后重试…')
                time.sleep(wait)
    raise RuntimeError(f'无法从淘宝 API 获取 token: {last_err}') from last_err


def _extract_cookie_value(cookie_str: str, cookie_name: str) -> str | None:
    for cookie in cookie_str.split(', '):
        if cookie.startswith(f"{cookie_name}="):
            value_part = cookie.split(';')[0]
            return value_part.split('=', 1)[1]
    return None


def get_taobao_tokens(*, prefer_network: bool = False) -> dict:
    """
    获取淘宝 _m_h5_tk / _m_h5_tk_enc。
    默认优先读 config_file/taobao_cookies.json，避免模块导入或任务启动时因网络失败而中断。
    """
    if not prefer_network:
        cached = _load_taobao_config_from_file()
        if cached:
            print('使用本地 config_file/taobao_cookies.json 中的淘宝 token')
            return cached

    try:
        fresh = get_m_h5_tk()
    except RuntimeError as e:
        cached = _load_taobao_config_from_file()
        if cached:
            print(f'网络获取淘宝 token 失败，回退本地配置: {e}')
            return cached
        raise RuntimeError(
            '无法获取淘宝 token：网络请求失败且本地 config_file/taobao_cookies.json 不可用。'
            '请检查网络/代理，或更新 taobao_cookies.json 中的 _m_h5_tk、_m_h5_tk_enc。'
        ) from e

    _save_taobao_tokens_to_file(fresh)
    return fresh


def _save_taobao_tokens_to_file(tokens: dict) -> None:
    if not TAOBAO_COOKIES_PATH.is_file():
        return
    try:
        with open(TAOBAO_COOKIES_PATH, encoding='utf-8') as f:
            config = json.load(f)
        updated = False
        for item in config:
            name = item.get('name')
            if name in tokens:
                item['value'] = tokens[name]
                updated = True
        if updated:
            with open(TAOBAO_COOKIES_PATH, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            print(f'已更新 {TAOBAO_COOKIES_PATH.name} 中的淘宝 token')
    except (OSError, json.JSONDecodeError, TypeError) as e:
        print(f'写回本地淘宝 cookie 失败: {e}')


if __name__ == '__main__':
    print(get_taobao_tokens(prefer_network=True))
