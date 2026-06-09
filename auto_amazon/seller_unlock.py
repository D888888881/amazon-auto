"""卖家精灵子账号被禁用时自动解禁并重试。"""

from __future__ import annotations



import sys

from collections.abc import Callable

from pathlib import Path

from typing import TypeVar



from django.conf import settings



T = TypeVar('T')





def _script_dir() -> Path:

    return Path(settings.BASE_DIR).resolve() / 'scripts' / 'asin_find_project'





def _ensure_script_path() -> Path:

    script_dir = _script_dir()

    script_path = str(script_dir)

    if script_path not in sys.path:

        sys.path.insert(0, script_path)

    return script_dir





def is_seller_account_banned_error(exc: BaseException) -> bool:

    """子账号被禁用：KeyError rank-login-user 或 SellerAccountBannedError。"""

    _ensure_script_path()

    from seller_account_guard import is_seller_account_banned_error as _is_banned



    return _is_banned(exc)





def unlock_seller_sub_account(*, on_log: Callable[[str], None] | None = None) -> tuple[bool, str]:

    """

    调用 unlock_seller_info.activate_children 解除子账号禁用。

    返回 (是否成功, 说明)。

    """

    script_dir = _ensure_script_path()

    script = script_dir / 'unlock_seller_info.py'

    if not script.is_file():

        return False, f'未找到解禁脚本：{script}'



    if on_log:

        on_log('正在执行卖家精灵子账号解禁程序…')



    try:

        from unlock_seller_info import activate_children



        ok, msg = activate_children()

    except Exception as exc:

        return False, f'解禁脚本执行异常：{exc}'



    if not ok:

        return False, msg



    _ensure_script_path()

    try:

        from seller_account_guard import clear_seller_login_cache

        clear_seller_login_cache()

    except Exception:

        pass



    if on_log:

        on_log('卖家精灵子账号解禁程序执行完成。')

    return True, msg or 'ok'





def execute_with_seller_unlock_retry(

    fn: Callable[[], T],

    *,

    on_log: Callable[[str], None] | None = None,

    max_unlock_attempts: int = 1,

) -> T:

    """执行 fn；若遇 rank-login-user 则解禁后重试（最多 max_unlock_attempts 次）。"""

    unlocks = 0

    while True:

        try:

            return fn()

        except Exception as exc:

            if unlocks >= max_unlock_attempts or not is_seller_account_banned_error(exc):

                raise

            unlocks += 1

            if on_log:

                on_log('检测到卖家精灵子账号被禁用（rank-login-user），正在自动解禁…')

            ok, msg = unlock_seller_sub_account(on_log=on_log)

            if not ok:

                raise RuntimeError(f'自动解禁失败：{msg}') from exc

            if on_log:

                on_log('解禁成功，正在重试当前步骤…')

            continue

