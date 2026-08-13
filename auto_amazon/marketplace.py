"""美国站 / 英国站会话上下文与运营难度区间规则。"""
from __future__ import annotations

from pathlib import Path

MARKETPLACE_US = 'US'
MARKETPLACE_UK = 'UK'
MARKETPLACE_CHOICES = (
    (MARKETPLACE_US, '美国站'),
    (MARKETPLACE_UK, '英国站'),
)
MARKETPLACE_SESSION_KEY = 'marketplace'

_VALID = {MARKETPLACE_US, MARKETPLACE_UK}


def normalize_marketplace(code: str | None) -> str | None:
    c = str(code or '').strip().upper()
    if c in _VALID:
        return c
    return None


def get_marketplace(request) -> str | None:
    return normalize_marketplace(request.session.get(MARKETPLACE_SESSION_KEY))


def require_marketplace(request) -> str:
    """返回已选站点；未选时回落 US（仅用于后台/兼容调用）。"""
    return get_marketplace(request) or MARKETPLACE_US


def set_marketplace(request, code: str) -> str:
    mp = normalize_marketplace(code)
    if not mp:
        raise ValueError(f'无效站点: {code}')
    request.session[MARKETPLACE_SESSION_KEY] = mp
    request.session.modified = True
    return mp


def clear_marketplace(request) -> None:
    request.session.pop(MARKETPLACE_SESSION_KEY, None)
    request.session.modified = True


def marketplace_label(code: str | None) -> str:
    mp = normalize_marketplace(code) or MARKETPLACE_US
    for k, label in MARKETPLACE_CHOICES:
        if k == mp:
            return label
    return mp


def platform_commission_percent(marketplace: str | None) -> float:
    """ROI 平台佣金：美国站 15%，英国站 25%。"""
    mp = normalize_marketplace(marketplace) or MARKETPLACE_US
    return 25.0 if mp == MARKETPLACE_UK else 15.0


def ops_review_bins(marketplace: str | None) -> tuple[list[float], list[str]]:
    """返回 (bins, labels) 供 pd.cut 使用。"""
    import numpy as np

    mp = normalize_marketplace(marketplace) or MARKETPLACE_US
    if mp == MARKETPLACE_UK:
        bins = [0, 10, 30, 50, 100, 150, np.inf]
        labels = ['0-10', '11-30', '31-50', '51-100', '101-150', '150以上']
        return bins, labels
    bins = [0, 30, 50, 100, 200, np.inf]
    labels = ['0-30', '31-50', '51-100', '101-200', '200以上']
    return bins, labels


def ops_ignore_label(marketplace: str | None) -> str:
    mp = normalize_marketplace(marketplace) or MARKETPLACE_US
    return '150以上' if mp == MARKETPLACE_UK else '200以上'


def ops_segment_count(marketplace: str | None) -> int:
    """含末档在内的区间段数。"""
    mp = normalize_marketplace(marketplace) or MARKETPLACE_US
    return 6 if mp == MARKETPLACE_UK else 5


def review_interval_filename(keyword: str, marketplace: str | None) -> str:
    mp = normalize_marketplace(marketplace) or MARKETPLACE_US
    return f'{keyword}_review_interval_analysis_{mp}.xlsx'


def resolve_review_interval_path(kw_dir: Path, marketplace: str | None) -> Path | None:
    """
    按站点解析运营难度 Excel：
    - UK：优先 *_review_interval_analysis_UK.xlsx
    - US：优先 *_US.xlsx，否则回落旧名 *_review_interval_analysis.xlsx
    """
    kw_dir = Path(kw_dir)
    if not kw_dir.is_dir():
        return None
    mp = normalize_marketplace(marketplace) or MARKETPLACE_US
    preferred = sorted(kw_dir.glob(f'*review_interval_analysis_{mp}.xlsx'))
    if preferred:
        return preferred[0]
    if mp == MARKETPLACE_US:
        legacy = sorted(kw_dir.glob('*review_interval_analysis.xlsx'))
        # 排除已带 _US/_UK 后缀的（glob 可能因命名差异单独匹配）
        legacy = [
            p
            for p in legacy
            if not p.name.endswith('_US.xlsx') and not p.name.endswith('_UK.xlsx')
        ]
        if legacy:
            return legacy[0]
    return None
