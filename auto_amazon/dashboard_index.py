"""首页看板：数据库筛选、按 ASIN 去重、分页（避免全量加载大字段行）。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.core.paginator import Paginator
from django.db.models import (
    Case,
    Exists,
    F,
    IntegerField,
    OuterRef,
    QuerySet,
    Subquery,
    Value,
    When,
    Window,
)
from django.db.models.functions import RowNumber

from .asin_access import (
    dedupe_dashboard_rows,
    normalize_asin,
    user_dashboard_rows_qs,
    user_imported_asin_codes,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from django.http import HttpRequest

DASHBOARD_SORT_FIELDS = {
    'asin': 'asin',
    'profit_margin': 'profit_margin',
    'ranking_percent': 'ranking_percent',
    'unit_purchase': 'unit_purchase',
    'monthly_results': 'monthly_results',
    'profit_per_order': 'profit_per_order',
    'monthly_sales_total': 'monthly_sales_total',
    'ad_removed_roi': 'ad_removed_roi',
    'head_actual_total': 'head_actual_total',
    'monthly_profit1': 'monthly_profit1',
    'product_grade': 'monthly_profit1',
    'created_at': 'created_at',
    'updated_at': 'updated_at',
    'follow_status': 'follow_status',
}

OPS_REVIEW_INTERVAL_OPTIONS_US = ('0-30', '31-50', '51-100', '101-200', '200以上')
OPS_REVIEW_INTERVAL_OPTIONS_UK = ('0-10', '11-30', '31-50', '51-100', '101-150', '150以上')
OPS_REVIEW_INTERVAL_OPTIONS = OPS_REVIEW_INTERVAL_OPTIONS_US


def ops_review_interval_options(marketplace: str | None = None) -> tuple[str, ...]:
    from .marketplace import MARKETPLACE_UK, normalize_marketplace

    if normalize_marketplace(marketplace) == MARKETPLACE_UK:
        return OPS_REVIEW_INTERVAL_OPTIONS_UK
    return OPS_REVIEW_INTERVAL_OPTIONS_US


_DEDUPE_FIELDS = (
    'pk',
    'asin',
    'user_id',
    'created_at',
    'monthly_results',
    'profit_margin',
    'ad_removed_roi',
    'monthly_profit1',
)
_SORT_EXTRA_FIELDS = tuple(
    f for f in set(DASHBOARD_SORT_FIELDS.values()) if f != 'updated_at'
)
_LIST_ONLY_FIELDS = tuple(dict.fromkeys(_DEDUPE_FIELDS + _SORT_EXTRA_FIELDS))
_OPS_FIELDS = ('ops_difficulty_1', 'ops_difficulty_2', 'ops_difficulty_3')


def _get_float(val: str | None):
    if val is None:
        return None
    s = str(val).strip()
    if s == '':
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _get_int(val: str | None):
    if val is None:
        return None
    s = str(val).strip()
    if s == '':
        return None
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


def dashboard_per_page(request: HttpRequest) -> int:
    raw = (request.GET.get('per_page') or '').strip().lower()
    custom = _get_int(request.GET.get('per_page_custom'))
    if raw == 'custom' and custom is not None:
        return max(1, min(custom, 500))
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 10
    if n in (10, 20, 40, 100):
        return n
    return 10


def _is_200_plus_review_label(label: str) -> bool:
    t = str(label).strip()
    return (
        '200以上' in t
        or '150以上' in t
        or t.replace(' ', '') in ('200+', '200＋', '150+', '150＋')
    )


def _review_labels_equivalent(selected: str, actual: str) -> bool:
    sel = str(selected).strip()
    act = str(actual).strip()
    if not sel or not act:
        return False
    if sel == act:
        return True
    if sel == '101-200' and act in ('101-150', '151-200'):
        return True
    if sel == '150以上' and ('150以上' in act or act.replace(' ', '') in ('150+', '150＋')):
        return True
    if sel == '200以上' and _is_200_plus_review_label(act) and '200' in act:
        return True
    return False


def _parse_ops_json(raw: str) -> list[tuple[str, float]]:
    if not raw or not str(raw).strip():
        return []
    s = str(raw).strip()
    out: list[tuple[str, float]] = []

    def _to_num(x):
        t = str(x).replace('%', '').replace('％', '').strip()
        if not t:
            return None
        try:
            return float(t)
        except (TypeError, ValueError):
            m = re.search(r'(\d+(?:\.\d+)?)', t)
            if m:
                return float(m.group(1))
            return None

    if s.startswith('{'):
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict) and obj:
            kw = next(iter(obj.keys()))
            wrap = obj.get(kw)
            if isinstance(wrap, dict):
                ri = wrap.get('review_interval')
                if isinstance(ri, dict):
                    labels = list(ri.get('区间') or [])
                    ops = list(ri.get('运营难度') or [])
                    if ops:
                        for i, x in enumerate(ops):
                            label = str(labels[i]).strip() if i < len(labels) else f'idx-{i}'
                            v = _to_num(x)
                            if v is not None:
                                out.append((label, v))
                        if out:
                            return out

    fallback_labels = ['0-30', '31-50', '51-100', '101-200', '200以上']
    nums = re.findall(r'(\d+(?:\.\d+)?)\s*[%％]', s)
    for i, n in enumerate(nums):
        label = fallback_labels[i] if i < len(fallback_labels) else f'idx-{i}'
        out.append((label, float(n)))
    return out


def _ops_match(
    raw: str,
    lo: float | None,
    hi: float | None,
    *,
    review_interval: str = 'all',
) -> bool:
    pairs = _parse_ops_json(raw)
    if not pairs:
        return False
    for label, v in pairs:
        if review_interval == 'all':
            if _is_200_plus_review_label(label):
                continue
        elif not _review_labels_equivalent(review_interval, label):
            continue
        if lo is not None and v < lo:
            continue
        if hi is not None and v > hi:
            continue
        return True
    return False


def _parse_ops_filter_params(request: HttpRequest, *, marketplace: str | None = None) -> dict:
    ops_slot = (request.GET.get('ops_slot') or 'any').strip()
    ops_range = (request.GET.get('ops_range') or 'all').strip()
    allowed = ops_review_interval_options(marketplace)
    ops_review_interval = (request.GET.get('ops_review_interval') or 'all').strip()
    if ops_review_interval not in allowed and ops_review_interval != 'all':
        ops_review_interval = 'all'
    ops_min = None
    ops_max = None
    preset = {
        '0-5': (0.0, 5.0),
        '5-10': (5.0, 10.0),
        '10-20': (10.0, 20.0),
        '30-100': (30.0, 100.0),
    }
    if ops_range in preset:
        ops_min, ops_max = preset[ops_range]
    elif ops_range == 'custom':
        ops_min = _get_float(request.GET.get('ops_custom_min'))
        ops_max = _get_float(request.GET.get('ops_custom_max'))
    return {
        'ops_slot': ops_slot,
        'ops_range': ops_range,
        'ops_review_interval': ops_review_interval,
        'ops_min': ops_min,
        'ops_max': ops_max,
        'active': ops_range != 'all',
    }


def _ops_fields_for_slot(slot: str) -> tuple[str, ...]:
    if slot == '1':
        return ('ops_difficulty_1',)
    if slot == '2':
        return ('ops_difficulty_2',)
    if slot == '3':
        return ('ops_difficulty_3',)
    return _OPS_FIELDS


def _row_passes_ops_filter(row, ops: dict) -> bool:
    if not ops['active']:
        return True
    for fn in _ops_fields_for_slot(ops['ops_slot']):
        if _ops_match(
            getattr(row, fn, ''),
            ops['ops_min'],
            ops['ops_max'],
            review_interval=ops['ops_review_interval'],
        ):
            return True
    return False


def _apply_roi_verified_filter(qs: QuerySet, roi_verified_f: str) -> QuerySet:
    from .models import AsinRoiPackVerification

    if roi_verified_f not in ('yes', 'no'):
        return qs
    verified = AsinRoiPackVerification.objects.filter(asin=OuterRef('asin'))
    if roi_verified_f == 'yes':
        return qs.filter(Exists(verified))
    return qs.filter(~Exists(verified))


def _apply_updated_stamp_range_filter(
    qs: QuerySet,
    updated_from,
    updated_to,
) -> QuerySet:
    if not updated_from and not updated_to:
        return qs
    from .models import AsinDataUpdateStamp

    stamp_qs = AsinDataUpdateStamp.objects.all()
    if updated_from:
        stamp_qs = stamp_qs.filter(updated_at__gte=updated_from)
    if updated_to:
        stamp_qs = stamp_qs.filter(updated_at__lte=updated_to)
    return qs.filter(asin__in=stamp_qs.values('asin'))


def stamp_map_for_asins(asins: set[str]) -> dict[str, object]:
    if not asins:
        return {}
    from .models import AsinDataUpdateStamp

    return {
        normalize_asin(a): t
        for a, t in AsinDataUpdateStamp.objects.filter(asin__in=asins).values_list(
            'asin', 'updated_at'
        )
    }


def _build_filtered_queryset(
    user: User,
    request: HttpRequest,
    *,
    parse_dt_local,
) -> tuple[QuerySet, dict]:
    from django.contrib.auth import get_user_model

    from .models import AsinCatalogItem, AsinDashboardRow, AsinFolderAssignment

    User = get_user_model()
    from .marketplace import MARKETPLACE_US, get_marketplace

    mp = get_marketplace(request) or MARKETPLACE_US
    rows_qs = user_dashboard_rows_qs(user, marketplace=mp)

    asin_kw = (request.GET.get('asin_kw') or '').strip()
    if asin_kw:
        rows_qs = rows_qs.filter(asin__icontains=asin_kw)

    assignee_username = (request.GET.get('assignee_user') or '').strip()
    if assignee_username:
        u = User.objects.filter(username__iexact=assignee_username, is_active=True).first()
        if u:
            asins_for_u = AsinFolderAssignment.objects.filter(assignees=u).values_list(
                'asin', flat=True
            )
            rows_qs = rows_qs.filter(asin__in=list(asins_for_u))

    uploaded_by_username = (request.GET.get('uploaded_by') or '').strip()
    if uploaded_by_username:
        upl = User.objects.filter(username__iexact=uploaded_by_username, is_active=True).first()
        if upl:
            uploaded_asins = user_imported_asin_codes(upl, marketplace=mp)
            catalog_asins = {
                normalize_asin(a)
                for a in AsinCatalogItem.objects.filter(
                    uploaded_by=upl, **({'marketplace': mp} if mp else {})
                ).values_list('asin', flat=True)
            }
            rows_qs = rows_qs.filter(asin__in=list(uploaded_asins | catalog_asins))

    updated_from = parse_dt_local(request.GET.get('updated_from'))
    updated_to = parse_dt_local(request.GET.get('updated_to'), end_of_day=True)
    rows_qs = _apply_updated_stamp_range_filter(rows_qs, updated_from, updated_to)

    numeric_fields = [
        ('profit_margin_min', 'profit_margin__gte'),
        ('profit_margin_max', 'profit_margin__lte'),
        ('ad_removed_roi_min', 'ad_removed_roi__gte'),
        ('ad_removed_roi_max', 'ad_removed_roi__lte'),
        ('monthly_results_min', 'monthly_results__gte'),
        ('monthly_results_max', 'monthly_results__lte'),
        ('profit_per_order_min', 'profit_per_order__gte'),
        ('profit_per_order_max', 'profit_per_order__lte'),
        ('monthly_sales_total_min', 'monthly_sales_total__gte'),
        ('monthly_sales_total_max', 'monthly_sales_total__lte'),
        ('unit_purchase_min', 'unit_purchase__gte'),
        ('unit_purchase_max', 'unit_purchase__lte'),
        ('head_actual_total_min', 'head_actual_total__gte'),
        ('head_actual_total_max', 'head_actual_total__lte'),
        ('ranking_percent_min', 'ranking_percent__gte'),
        ('ranking_percent_max', 'ranking_percent__lte'),
    ]
    for key, lookup in numeric_fields:
        v = _get_float(request.GET.get(key))
        if v is not None:
            rows_qs = rows_qs.filter(**{lookup: v})

    grades = [g.upper() for g in request.GET.getlist('product_grade') if str(g).strip()]
    allowed = [g for g in grades if g in ('A', 'B', 'C', 'D', 'E')]
    if allowed:
        rows_qs = rows_qs.filter(product_grade__in=allowed)

    roi_verified_f = (request.GET.get('roi_verified') or '').strip().lower()
    rows_qs = _apply_roi_verified_filter(rows_qs, roi_verified_f)

    follow_f = (request.GET.get('follow_filter') or '').strip()
    if follow_f == AsinDashboardRow.FollowStatus.NORMAL:
        rows_qs = rows_qs.filter(follow_status=AsinDashboardRow.FollowStatus.NORMAL)
    elif follow_f == AsinDashboardRow.FollowStatus.PRIORITY:
        rows_qs = rows_qs.filter(follow_status=AsinDashboardRow.FollowStatus.PRIORITY)

    meta = {
        'allowed_grades': allowed,
        'roi_verified_f': roi_verified_f,
        'follow_f': follow_f,
        'updated_from': (request.GET.get('updated_from') or '').strip(),
        'updated_to': (request.GET.get('updated_to') or '').strip(),
    }
    return rows_qs, meta


def _list_only_fields(ops_active: bool) -> tuple[str, ...]:
    if ops_active:
        return tuple(dict.fromkeys(_LIST_ONLY_FIELDS + _OPS_FIELDS))
    return _LIST_ONLY_FIELDS


def _metric_score_annotation():
    """与 _row_metric_rank 对齐：已写入 ROI 相关字段越多分越高。"""
    score = Value(0, output_field=IntegerField())
    for field in ('monthly_results', 'profit_margin', 'ad_removed_roi', 'monthly_profit1'):
        score = score + Case(
            When(**{f'{field}__isnull': False}, then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        )
    return score


def _owner_rank_annotation(viewer_id: int, assigned_set: set[str]):
    """
    去重偏好：
    - 被分配 ASIN：优先他人行（共享源数据）
    - 其他：优先本人行
    """
    assigned_list = [a for a in assigned_set if a]
    whens = []
    if assigned_list:
        whens.append(
            When(asin__in=assigned_list, user_id=viewer_id, then=Value(0))
        )
        whens.append(When(asin__in=assigned_list, then=Value(1)))
    whens.append(When(user_id=viewer_id, then=Value(1)))
    return Case(*whens, default=Value(0), output_field=IntegerField())


def _ordered_deduped_pks_legacy(
    rows_qs: QuerySet,
    *,
    viewer_id: int,
    assigned_set: set[str],
    sort_field: str,
    direction: str,
    ops: dict,
) -> list[int]:
    """运营难度筛选用：需读 TextField，保留内存去重路径。"""
    only_fields = _list_only_fields(ops['active'])
    qs = rows_qs.only(*only_fields)

    if sort_field == 'updated_at':
        from .models import AsinDataUpdateStamp

        stamp_subq = AsinDataUpdateStamp.objects.filter(asin=OuterRef('asin')).values(
            'updated_at'
        )[:1]
        order_prefix = '-' if direction == 'desc' else ''
        slim_rows = list(
            qs.annotate(_stamp_sort=Subquery(stamp_subq)).order_by(
                f'{order_prefix}_stamp_sort', 'pk'
            )
        )
    else:
        order_prefix = '-' if direction == 'desc' else ''
        slim_rows = list(qs.order_by(f'{order_prefix}{sort_field}', 'pk'))

    if ops['active']:
        slim_rows = [r for r in slim_rows if _row_passes_ops_filter(r, ops)]

    deduped = dedupe_dashboard_rows(slim_rows, viewer_id, assigned_set)
    return [r.pk for r in deduped]


def _preferred_pks_page(
    rows_qs: QuerySet,
    *,
    viewer_id: int,
    assigned_set: set[str],
    sort_field: str,
    direction: str,
    offset: int,
    limit: int,
) -> tuple[list[int], int]:
    """
    SQL 窗口函数按 ASIN 去重后真正分页，只取当前页 pk。
    返回 (page_pks, total_distinct_asins)。
    """
    from .models import AsinDataUpdateStamp

    total = rows_qs.values('asin').distinct().count()
    if total == 0 or limit <= 0:
        return [], total

    order_prefix = '-' if direction == 'desc' else ''
    ranked = rows_qs.annotate(
        _metric=_metric_score_annotation(),
        _owner_rank=_owner_rank_annotation(viewer_id, assigned_set),
        _rn=Window(
            expression=RowNumber(),
            partition_by=[F('asin')],
            order_by=[
                F('_metric').desc(),
                F('_owner_rank').desc(),
                F('created_at').desc(),
                F('pk').desc(),
            ],
        ),
    )
    # Django 将 window + filter 编译为子查询，适配 MySQL 8
    preferred = ranked.filter(_rn=1)
    if sort_field == 'updated_at':
        stamp_subq = AsinDataUpdateStamp.objects.filter(asin=OuterRef('asin')).values(
            'updated_at'
        )[:1]
        preferred = preferred.annotate(_stamp_sort=Subquery(stamp_subq)).order_by(
            f'{order_prefix}_stamp_sort', 'pk'
        )
    else:
        preferred = preferred.order_by(f'{order_prefix}{sort_field}', 'pk')

    page_pks = list(preferred.values_list('pk', flat=True)[offset : offset + limit])
    return page_pks, total


def _ordered_deduped_pks(
    rows_qs: QuerySet,
    *,
    viewer_id: int,
    assigned_set: set[str],
    sort_field: str,
    direction: str,
    ops: dict,
    marketplace: str | None = None,
) -> list[int]:
    """兼容旧调用：返回全部去重 pk（运营难度筛选或回落）。"""
    return _ordered_deduped_pks_legacy(
        rows_qs,
        viewer_id=viewer_id,
        assigned_set=assigned_set,
        sort_field=sort_field,
        direction=direction,
        ops=ops,
    )


def _fetch_rows_by_pks(ordered_pks: list[int]) -> list:
    from .models import AsinDashboardRow

    if not ordered_pks:
        return []
    by_pk = {r.pk: r for r in AsinDashboardRow.objects.filter(pk__in=ordered_pks)}
    return [by_pk[pk] for pk in ordered_pks if pk in by_pk]


@dataclass
class DashboardPageResult:
    rows: list
    page_obj: object
    page_numbers: list[int]
    sort_key: str
    direction: str
    filter_meta: dict
    ops_params: dict


def build_dashboard_page(
    user: User,
    request: HttpRequest,
    *,
    assigned_set: set[str],
    parse_dt_local,
) -> DashboardPageResult:
    sort_key = request.GET.get('sort', 'updated_at')
    direction = request.GET.get('dir', 'desc')
    if direction not in ('asc', 'desc'):
        direction = 'desc'
    sort_field = DASHBOARD_SORT_FIELDS.get(sort_key, 'updated_at')

    rows_qs, filter_meta = _build_filtered_queryset(user, request, parse_dt_local=parse_dt_local)
    from .marketplace import MARKETPLACE_US, get_marketplace

    mp = get_marketplace(request) or MARKETPLACE_US
    ops_params = _parse_ops_filter_params(request, marketplace=mp)
    per_page = dashboard_per_page(request)
    page_num = _get_int(request.GET.get('page')) or 1
    page_num = max(1, page_num)

    if ops_params.get('active'):
        ordered_pks = _ordered_deduped_pks_legacy(
            rows_qs,
            viewer_id=user.id,
            assigned_set=assigned_set,
            sort_field=sort_field,
            direction=direction,
            ops=ops_params,
        )
        paginator = Paginator(ordered_pks, per_page)
        page_obj = paginator.get_page(page_num)
        page_pks = list(page_obj.object_list)
    else:
        offset = (page_num - 1) * per_page
        page_pks, total = _preferred_pks_page(
            rows_qs,
            viewer_id=user.id,
            assigned_set=assigned_set,
            sort_field=sort_field,
            direction=direction,
            offset=offset,
            limit=per_page,
        )
        # 用占位序列构造分页器，避免把全量 pk 载入内存
        paginator = Paginator(range(total), per_page)
        page_obj = paginator.get_page(page_num)
        page_obj.object_list = page_pks

    rows = _fetch_rows_by_pks(page_pks)

    page_start = page_obj.number
    page_end = min(paginator.num_pages, page_start + 9)
    page_numbers = list(range(page_start, page_end + 1))

    return DashboardPageResult(
        rows=rows,
        page_obj=page_obj,
        page_numbers=page_numbers,
        sort_key=sort_key,
        direction=direction,
        filter_meta=filter_meta,
        ops_params=ops_params,
    )


def verified_asins_on_page(asins: set[str]) -> set[str]:
    from .models import AsinRoiPackVerification

    if not asins:
        return set()
    return {
        normalize_asin(a)
        for a in AsinRoiPackVerification.objects.filter(asin__in=asins).values_list(
            'asin', flat=True
        )
    }
