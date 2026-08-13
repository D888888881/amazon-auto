"""登录后未选择站点时强制进入选站页。"""
from __future__ import annotations

from django.shortcuts import redirect
from django.urls import Resolver404, resolve


class MarketplaceRequiredMiddleware:
    """业务页要求 session 中已选 US/UK；白名单除外。"""

    ALLOW_PREFIXES = (
        '/static/',
        '/media/',
        '/admin/',
        '/django-rq/',
    )
    ALLOW_NAMES = frozenset(
        {
            'login',
            'logout',
            'register',
            'select_site',
            'select_site_switch',
        }
    )
    # path 兜底：resolve 失败时仍放行选站相关 URL
    ALLOW_PATH_MARKERS = (
        '/select-site',
        '/login',
        '/logout',
        '/register',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._should_redirect(request):
            return redirect('select_site')
        return self.get_response(request)

    def _url_name(self, request) -> str | None:
        match = getattr(request, 'resolver_match', None)
        if match and match.url_name:
            return match.url_name
        try:
            return resolve(request.path_info).url_name
        except Resolver404:
            return None

    def _path_allowed(self, path: str) -> bool:
        p = (path or '').lower()
        return any(marker in p for marker in self.ALLOW_PATH_MARKERS)

    def _should_redirect(self, request) -> bool:
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            return False
        path = request.path or ''
        for prefix in self.ALLOW_PREFIXES:
            if path.startswith(prefix):
                return False
        if self._path_allowed(path):
            return False
        url_name = self._url_name(request)
        if url_name in self.ALLOW_NAMES:
            return False
        if url_name is None and path.rstrip('/').endswith('favicon.ico'):
            return False
        from .marketplace import get_marketplace

        return get_marketplace(request) is None
