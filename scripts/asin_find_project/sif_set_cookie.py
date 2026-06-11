from pathlib import Path

import requests

_SCRIPT_DIR = Path(__file__).resolve().parent
_AUTHORIZATION_FILE = _SCRIPT_DIR / 'config_file' / 'sif_authorization.txt'
_TOKEN_FILE = _SCRIPT_DIR / 'config_file' / 'sif_token.txt'


def get_sif_authorization() -> str:
    if not _AUTHORIZATION_FILE.is_file():
        raise FileNotFoundError(
            f'未找到 SIF authorization 配置文件：{_AUTHORIZATION_FILE}，'
            '请在网站「凭证配置」页面填写并保存。'
        )
    value = _AUTHORIZATION_FILE.read_text(encoding='utf-8').strip()
    if not value:
        raise ValueError('SIF authorization 为空，请在网站「凭证配置」页面填写并保存。')
    return value


def get_sif_cookie() -> str | None:
    authorization = get_sif_authorization()
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
        'Connection': 'keep-alive',
        'Referer': 'https://www.sif.com/',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0'
        ),
        'authorization': authorization,
        'sec-ch-ua': '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
    }
    url = 'https://www.sif.com/api/user/conch/info'
    params = {
        'country': 'US',
    }
    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()

    sif_token = response.cookies.get('sif_token')
    _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_TOKEN_FILE, 'w', encoding='utf-8') as f:
        f.write(sif_token if sif_token else '未找到 sif_token')
    return sif_token


if __name__ == '__main__':
    token = get_sif_cookie()
    print('提取的 sif_token:', token)
