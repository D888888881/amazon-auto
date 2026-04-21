import json
from datetime import datetime
import shutil
import threading
import uuid
import zipfile
from io import BytesIO
from pathlib import Path
import re
from collections import defaultdict

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import close_old_connections
from django.db import DatabaseError
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.utils import timezone
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from openpyxl import Workbook, load_workbook

from .asin_wizard import run_ad_difficulty_for_asins, run_seller_wizard
from .excel_io import read_active_sheet_rich, save_sheet_values_preserving_format
from .forms import RegisterForm
from .media_paths import media_root, parent_rel, safe_media_path_global
from .dashboard_ops_filter import run_dashboard_ops_filter
from .asin_access import (
    normalize_asin,
    user_assigned_asin_codes,
    user_can_access_excel_media_path,
    user_imported_asin_codes,
)
from .excel_import_utils import ensure_dir_nodes_registered, extract_zip_to_media_root
from .media_import_staging import (
    append_chunk as import_append_chunk,
    cleanup_staging_dir,
    load_ready_staging,
    refresh_conflicts_in_meta,
)
from .models import (
    AsinDashboardRow,
    AsinDataUpdateStamp,
    AsinFolderAssignment,
    AsinRoiPackVerification,
    ImportedMediaPath,
    UserProfile,
)
from .roi_us_pack_recalc import is_roi_us_pack_filename, recalc_roi_us_pack_rows
from .utils import product_grade_from_monthly_profit1


WIZARD_JOB_TTL = 7200


def _dashboard_per_page(request) -> int:
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


def _compute_roi_per_page(request) -> int:
    raw = (request.GET.get('per_page') or '').strip().lower()
    custom = _get_int(request.GET.get('per_page_custom'))
    if raw == 'custom' and custom is not None:
        return max(1, min(custom, 500))
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 20
    if n in (20, 50, 100):
        return n
    return 20


def _assignment_label_map(asins: set[str]) -> dict[str, str]:
    if not asins:
        return {}
    rows = (
        AsinFolderAssignment.objects.filter(asin__in=asins)
        .prefetch_related('assignees')
        .only('id', 'asin')
    )
    out: dict[str, str] = {}
    for a in rows:
        names = sorted({u.username for u in a.assignees.all()})
        out[normalize_asin(a.asin)] = '、'.join(names) if names else ''
    return out


def _touch_asin_updates(asins: list[str] | set[str]) -> None:
    uniq = sorted({normalize_asin(a) for a in asins if str(a or '').strip()})
    for a in uniq:
        AsinDataUpdateStamp.objects.update_or_create(asin=a, defaults={})


def _parse_dt_local(raw: str | None, end_of_day: bool = False):
    s = (raw or '').strip()
    if not s:
        return None
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(s, fmt)
            if fmt == '%Y-%m-%d' and end_of_day:
                dt = dt.replace(hour=23, minute=59, second=59)
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            return dt
        except ValueError:
            continue
    return None


def _attach_row_assignee_labels(
    rows,
    label_map: dict[str, str],
    viewer_id: int,
    viewer_assigned_asins: set[str],
    viewer_is_superuser: bool,
    roi_verified_asins: set[str] | None = None,
) -> None:
    verified = roi_verified_asins or set()
    for r in rows:
        key = normalize_asin(r.asin)
        r.assignee_display = label_map.get(key) or '—'
        r.ops_readonly = r.user_id != viewer_id
        r.can_open_dir = viewer_is_superuser or (key in viewer_assigned_asins)
        r.roi_pack_verified = key in verified


def _require_superuser_for_excel_audit(request) -> bool:
    return bool(getattr(request.user, 'is_superuser', False))


def _first_word_from_filename(name: str) -> str:
    stem = Path(name).stem.strip()
    if not stem:
        return 'Excel'
    return stem.split()[0]


def _is_search_sheet_filename(name: str) -> bool:
    n = (name or '').lower()
    return n.startswith('search(') and n.endswith('.xlsx')


def _deleted_asin_set_from_data_origin(search_path: Path) -> set[str]:
    """
    对比同目录 *_data_origin.xlsx：
    返回在 Search 中存在、但在 data_origin 中不存在的 asin 集合（视为被清洗删除）。
    """
    try:
        parent = search_path.parent
        origins = sorted(parent.glob('*_data_origin.xlsx'))
        if not origins:
            return set()
        origin_path = origins[0]

        def _asin_set(xlsx: Path) -> set[str]:
            wb = load_workbook(xlsx, read_only=True, data_only=True)
            ws = wb.active
            rows = ws.iter_rows(values_only=True)
            header = next(rows, None)
            if not header:
                wb.close()
                return set()
            idx = -1
            for i, h in enumerate(header):
                if str(h or '').strip().lower() == 'asin':
                    idx = i
                    break
            if idx < 0:
                wb.close()
                return set()
            out: set[str] = set()
            for r in rows:
                if not r or idx >= len(r):
                    continue
                v = str(r[idx] or '').strip().upper()
                if v:
                    out.add(v)
            wb.close()
            return out

        s_set = _asin_set(search_path)
        o_set = _asin_set(origin_path)
        if not s_set:
            return set()
        return {x for x in s_set if x not in o_set}
    except Exception:
        return set()


def _highlight_deleted_rows_for_search(payload: dict, deleted_asins: set[str]) -> None:
    """将 Search 表中命中 deleted_asins 的整行高亮。"""
    if not deleted_asins:
        return
    rows = payload.get('rows')
    if not isinstance(rows, list) or len(rows) < 2:
        return
    head = rows[0] if isinstance(rows[0], list) else []
    asin_col = -1
    for i, c in enumerate(head):
        txt = ''
        if isinstance(c, dict):
            txt = str(c.get('v', '') or '').strip().lower()
        else:
            txt = str(c or '').strip().lower()
        if txt == 'asin':
            asin_col = i
            break
    if asin_col < 0:
        return
    for r in range(1, len(rows)):
        row = rows[r]
        if not isinstance(row, list) or asin_col >= len(row):
            continue
        c = row[asin_col]
        asin = (str(c.get('v', '') if isinstance(c, dict) else c or '')).strip().upper()
        if not asin or asin not in deleted_asins:
            continue
        for j, one in enumerate(row):
            if isinstance(one, dict):
                base_css = str(one.get('css', '') or '')
                if 'background-color' not in base_css:
                    one['css'] = (base_css + ';background-color:#fff3cd').strip(';')
            else:
                row[j] = {'v': str(one or ''), 'style': {}, 'css': 'background-color:#fff3cd'}


def register(request):
    if request.user.is_authenticated:
        return redirect('index')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                '注册申请已提交，请等待超级管理员审核。审核通过后即可使用账号登录。',
            )
            return redirect('login')
    else:
        form = RegisterForm()
    return render(request, 'registration/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)
    next_url = request.GET.get('next') or ''
    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        password = request.POST.get('password') or ''
        next_url = (request.POST.get('next') or '').strip() or next_url
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            messages.error(request, '用户名或密码不正确。')
            return render(request, 'registration/login.html', {'next': next_url})
        if not user.check_password(password):
            messages.error(request, '用户名或密码不正确。')
            return render(request, 'registration/login.html', {'next': next_url})
        if not user.is_active:
            try:
                st = user.profile.registration_status
            except UserProfile.DoesNotExist:
                st = UserProfile.Status.PENDING
            if st == UserProfile.Status.REJECTED:
                messages.error(request, '您的注册申请已被拒绝，无法登录。')
            else:
                messages.warning(request, '您的账号尚未通过管理员审核，请耐心等待。')
            return render(request, 'registration/login.html', {'next': next_url})
        auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return redirect(next_url or settings.LOGIN_REDIRECT_URL)
    return render(request, 'registration/login.html', {'next': next_url})


@login_required
@user_passes_test(lambda u: u.is_superuser)
def pending_registrations(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        action = request.POST.get('action')
        if not user_id or action not in ('approve', 'reject'):
            messages.error(request, '请求无效。')
            return redirect('pending_registrations')
        try:
            target = User.objects.get(pk=int(user_id))
        except (User.DoesNotExist, ValueError):
            messages.error(request, '用户不存在。')
            return redirect('pending_registrations')
        if target.is_superuser:
            messages.error(request, '不能审核超级管理员账号。')
            return redirect('pending_registrations')
        try:
            profile = target.profile
        except UserProfile.DoesNotExist:
            profile = UserProfile.objects.create(
                user=target,
                registration_status=UserProfile.Status.PENDING,
            )
        if profile.registration_status != UserProfile.Status.PENDING:
            messages.warning(request, f'用户「{target.username}」当前不是待审核状态。')
            return redirect('pending_registrations')
        now = timezone.now()
        if action == 'approve':
            with transaction.atomic():
                target.is_active = True
                target.save(update_fields=['is_active'])
                profile.registration_status = UserProfile.Status.APPROVED
                profile.reviewed_at = now
                profile.reviewed_by = request.user
                profile.save(
                    update_fields=['registration_status', 'reviewed_at', 'reviewed_by'],
                )
            messages.success(request, f'已通过用户「{target.username}」的注册申请。')
        else:
            with transaction.atomic():
                target.is_active = False
                target.save(update_fields=['is_active'])
                profile.registration_status = UserProfile.Status.REJECTED
                profile.reviewed_at = now
                profile.reviewed_by = request.user
                profile.save(
                    update_fields=['registration_status', 'reviewed_at', 'reviewed_by'],
                )
            messages.success(request, f'已拒绝用户「{target.username}」的注册申请。')
        return redirect('pending_registrations')

    pending = (
        UserProfile.objects.filter(registration_status=UserProfile.Status.PENDING)
        .select_related('user')
        .order_by('user__date_joined')
    )
    hist_base = (
        UserProfile.objects.filter(
            registration_status__in=(
                UserProfile.Status.APPROVED,
                UserProfile.Status.REJECTED,
            ),
            reviewed_at__isnull=False,
        )
        .select_related('user', 'reviewed_by')
        .order_by('-reviewed_at')
    )
    review_history_total = hist_base.count()
    review_history = hist_base[:100]
    return render(
        request,
        'auto_amazon/pending_registrations.html',
        {
            'pending': pending,
            'pending_count': pending.count(),
            'review_history': review_history,
            'review_history_total': review_history_total,
        },
    )


@login_required
@user_passes_test(lambda u: u.is_superuser)
def user_management(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        action = request.POST.get('action')

        if not user_id or action not in ('disable', 'enable', 'delete'):
            messages.error(request, '请求无效。')
            return redirect('user_management')

        try:
            target = User.objects.get(pk=int(user_id))
        except (User.DoesNotExist, ValueError):
            messages.error(request, '用户不存在。')
            return redirect('user_management')

        # 安全保护：不能操作其它超级管理员、不能对自己操作。
        if target.is_superuser:
            messages.error(request, '不能操作超级管理员账号。')
            return redirect('user_management')
        if target == request.user:
            messages.error(request, '不能对自己执行该操作。')
            return redirect('user_management')

        if action == 'disable':
            if target.is_active:
                target.is_active = False
                target.save(update_fields=['is_active'])
                messages.success(request, f'已禁用用户「{target.username}」。')
            else:
                messages.warning(request, f'用户「{target.username}」当前已处于禁用状态。')
        elif action == 'enable':
            if not target.is_active:
                target.is_active = True
                target.save(update_fields=['is_active'])
                messages.success(request, f'已启用用户「{target.username}」。')
            else:
                messages.warning(request, f'用户「{target.username}」当前已处于启用状态。')
        else:  # delete
            target.delete()
            messages.success(request, '用户已删除。')

        return redirect('user_management')

    # GET 请求部分保持不变
    users_qs = User.objects.filter(is_superuser=False).order_by('-date_joined')
    users_count = users_qs.count()
    active_count = users_qs.filter(is_active=True).count()
    inactive_count = users_qs.filter(is_active=False).count()

    return render(
        request,
        'auto_amazon/user_manage.html',
        {
            'users': users_qs,
            'users_count': users_count,
            'active_count': active_count,
            'inactive_count': inactive_count,
        },
    )


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
}


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


def _parse_ops_json(raw: str) -> list[tuple[str, float]]:
    """从运营难度 JSON 中提取(区间, 百分比)；忽略「200以上」区间。"""
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

    # 新格式：严格 JSON
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
                            # 规则：200以上不参与；若没有标签信息，兜底忽略第5段(索引4)
                            if '200以上' in label or i == 4:
                                continue
                            v = _to_num(x)
                            if v is not None:
                                out.append((label, v))
                        if out:
                            return out

    # 兼容旧格式文本：兜底提取百分比，按前4段参与筛选（第5段通常是200以上）
    nums = re.findall(r'(\d+(?:\.\d+)?)\s*[%％]', s)
    for i, n in enumerate(nums):
        if i >= 4:
            break
        out.append((f'idx-{i}', float(n)))
    return out


def _ops_match(raw: str, lo: float | None, hi: float | None) -> bool:
    pairs = _parse_ops_json(raw)
    if not pairs:
        return False
    for _, v in pairs:
        if lo is not None and v < lo:
            continue
        if hi is not None and v > hi:
            continue
        return True
    return False


@login_required
def index(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'delete_batch':
            ids = request.POST.getlist('row_ids')
            if ids:
                AsinDashboardRow.objects.filter(user=request.user, pk__in=ids).delete()
                messages.success(request, f'已删除 {len(ids)} 条记录。')
        elif action == 'calc_roi_selected':
            ids = request.POST.getlist('row_ids')
            if not ids:
                messages.error(request, '请先勾选需要计算 ROI 的 ASIN。')
                return redirect('index')
            active = cache.get(_user_active_job_key(request.user.id))
            if active:
                messages.error(request, '已有任务在运行中，请等待当前任务完成后再发起新的计算。')
                return redirect(f"{reverse('compute_roi')}?job_id={active}")
            parity, err = _parse_compute_local_form(request)
            if err:
                messages.error(request, err)
                return redirect('index')
            rows_sel = list(
                AsinDashboardRow.objects.filter(user=request.user, pk__in=ids).only(
                    'pk', 'asin', 'unit_purchase', 'head_distance'
                )
            )
            asins = sorted({r.asin for r in rows_sel if r.asin})
            if not asins:
                messages.error(request, '未找到可计算的 ASIN。')
                return redirect('index')
            cost_overrides: dict = {}
            for r in rows_sel:
                up_in = _get_float(request.POST.get(f'unit_purchase_{r.pk}'))
                hd_in = _get_float(request.POST.get(f'head_distance_{r.pk}'))
                up_val = up_in if up_in is not None else r.unit_purchase
                hd_val = hd_in if hd_in is not None else r.head_distance
                updates = {}
                if up_in is not None:
                    updates['unit_purchase'] = up_in
                if hd_in is not None:
                    updates['head_distance'] = hd_in
                if up_val is not None and hd_val is not None:
                    updates['head_actual_total'] = round(up_val + hd_val, 2)
                if updates:
                    AsinDashboardRow.objects.filter(user=request.user, pk=r.pk).update(**updates)
                one = {}
                if up_val is not None:
                    one['unit_purchase'] = float(up_val)
                if hd_val is not None:
                    one['head_distance'] = float(hd_val)
                if one:
                    cost_overrides[r.asin] = one
            jid = str(uuid.uuid4())
            key = _wizard_job_key(jid)
            _set_user_active_job(request.user.id, jid)
            cache.set(
                key,
                {
                    'status': 'running',
                    'user_id': request.user.id,
                    'progress': [
                        '看板 ROI 计算任务已创建，正在启动分析子进程…',
                        f'当前汇率：{parity}。',
                        f'本次勾选 ASIN：{len(asins)} 个。',
                    ],
                },
                WIZARD_JOB_TTL,
            )
            t = threading.Thread(
                target=_run_wizard_job,
                args=(jid, request.user.id, asins, parity, cost_overrides),
                daemon=True,
            )
            t.start()
            messages.success(request, f'已开始计算 {len(asins)} 个 ASIN 的 ROI，已跳转到进度页。')
            return redirect(f"{reverse('compute_roi')}?job_id={jid}")
        elif action == 'calc_ranking_selected':
            ids = request.POST.getlist('row_ids')
            if not ids:
                messages.error(request, '请先勾选需要计算广告难度的 ASIN。')
                return redirect('index')
            active = cache.get(_user_active_job_key(request.user.id))
            if active:
                messages.error(request, '已有任务在运行中，请等待当前任务完成后再发起新的计算。')
                return redirect(f"{reverse('compute_roi')}?job_id={active}")
            rows_sel = list(AsinDashboardRow.objects.filter(user=request.user, pk__in=ids).only('asin'))
            asins = sorted({r.asin for r in rows_sel if r.asin})
            if not asins:
                messages.error(request, '未找到可计算的记录。')
                return redirect('index')
            jid = str(uuid.uuid4())
            key = _wizard_job_key(jid)
            _set_user_active_job(request.user.id, jid)
            cache.set(
                key,
                {
                    'status': 'running',
                    'user_id': request.user.id,
                    'progress': [
                        '广告难度计算任务已创建，正在启动分析子进程…',
                        f'本次勾选 ASIN：{len(asins)} 个。',
                    ],
                },
                WIZARD_JOB_TTL,
            )
            t = threading.Thread(
                target=_run_ad_difficulty_job,
                args=(jid, request.user.id, asins),
                daemon=True,
            )
            t.start()
            messages.success(request, f'已开始计算 {len(asins)} 个 ASIN 的广告难度，已跳转到进度页。')
            return redirect(f"{reverse('compute_roi')}?job_id={jid}")
        elif action == 'delete_one':
            rid = request.POST.get('row_id')
            if rid:
                AsinDashboardRow.objects.filter(user=request.user, pk=rid).delete()
                messages.success(request, '已删除该条记录。')
        return redirect('index')

    sort_key = request.GET.get('sort', 'updated_at')
    direction = request.GET.get('dir', 'desc')
    if direction not in ('asc', 'desc'):
        direction = 'desc'
    field = DASHBOARD_SORT_FIELDS.get(sort_key, 'updated_at')
    order_prefix = '-' if direction == 'desc' else ''
    order_by = f'{order_prefix}{field}'

    assigned_codes = user_assigned_asin_codes(request.user)
    assigned_set = {normalize_asin(a) for a in assigned_codes}
    viewer_is_superuser = bool(request.user.is_superuser)
    rows_qs = AsinDashboardRow.objects.filter(
        Q(user=request.user) | Q(asin__in=assigned_codes)
    ).distinct()
    updated_stamp_map = {
        normalize_asin(a): t
        for a, t in AsinDataUpdateStamp.objects.values_list('asin', 'updated_at')
    }
    asin_kw = (request.GET.get('asin_kw') or '').strip()
    if asin_kw:
        rows_qs = rows_qs.filter(asin__icontains=asin_kw)

    assignee_username = (request.GET.get('assignee_user') or '').strip()
    if assignee_username:
        u = User.objects.filter(username__iexact=assignee_username, is_active=True).first()
        if u:
            asins_for_u = AsinFolderAssignment.objects.filter(assignees=u).values_list('asin', flat=True)
            rows_qs = rows_qs.filter(asin__in=list(asins_for_u))

    # 更新时间筛选
    updated_from = _parse_dt_local(request.GET.get('updated_from'))
    updated_to = _parse_dt_local(request.GET.get('updated_to'), end_of_day=True)
    if updated_from or updated_to:
        filtered_asins = set()
        for a, dt in updated_stamp_map.items():
            if dt is None:
                continue
            if updated_from and dt < updated_from:
                continue
            if updated_to and dt > updated_to:
                continue
            filtered_asins.add(a)
        rows_qs = rows_qs.filter(asin__in=list(filtered_asins))

    # 数值区间筛选
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

    # 产品等级筛选（A-E，多选）
    grades = [g.upper() for g in request.GET.getlist('product_grade') if str(g).strip()]
    allowed = [g for g in grades if g in ('A', 'B', 'C', 'D', 'E')]
    if allowed:
        rows_qs = rows_qs.filter(product_grade__in=allowed)

    roi_verified_f = (request.GET.get('roi_verified') or '').strip().lower()
    if roi_verified_f in ('yes', 'no'):
        verified_codes = list(AsinRoiPackVerification.objects.values_list('asin', flat=True))
        if roi_verified_f == 'yes':
            rows_qs = rows_qs.filter(asin__in=verified_codes)
        else:
            rows_qs = rows_qs.exclude(asin__in=verified_codes)

    if field == 'updated_at':
        rows = list(rows_qs)
        rows.sort(
            key=lambda r: updated_stamp_map.get(normalize_asin(r.asin)) or timezone.make_aware(
                datetime(1970, 1, 1), timezone.get_current_timezone()
            ),
            reverse=(direction == 'desc'),
        )
    else:
        rows_qs = rows_qs.order_by(order_by)
        rows = rows_qs

    # 运营难度筛选（列选择 + 区间）
    ops_slot = (request.GET.get('ops_slot') or 'any').strip()
    ops_range = (request.GET.get('ops_range') or 'all').strip()
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

    if field != 'updated_at':
        rows = rows_qs
    if ops_range != 'all':
        if ops_slot == '1':
            fields = ('ops_difficulty_1',)
        elif ops_slot == '2':
            fields = ('ops_difficulty_2',)
        elif ops_slot == '3':
            fields = ('ops_difficulty_3',)
        else:
            fields = ('ops_difficulty_1', 'ops_difficulty_2', 'ops_difficulty_3')
        filtered = []
        src_rows = rows if field == 'updated_at' else rows_qs
        for r in src_rows:
            hit = False
            for fn in fields:
                if _ops_match(getattr(r, fn, ''), ops_min, ops_max):
                    hit = True
                    break
            if hit:
                filtered.append(r)
        rows = filtered

    page_num = request.GET.get('page') or 1
    per_page = _dashboard_per_page(request)
    paginator = Paginator(rows, per_page)
    page_obj = paginator.get_page(page_num)
    rows = page_obj.object_list
    asins_on_page = {normalize_asin(r.asin) for r in rows}
    verified_norm = {
        normalize_asin(a)
        for a in AsinRoiPackVerification.objects.filter(asin__in=list(asins_on_page)).values_list(
            'asin', flat=True
        )
    }
    _attach_row_assignee_labels(
        rows,
        _assignment_label_map(asins_on_page),
        request.user.id,
        assigned_set,
        viewer_is_superuser,
        roi_verified_asins=verified_norm,
    )
    for r in rows:
        r.data_updated_at = updated_stamp_map.get(normalize_asin(r.asin))
    page_start = page_obj.number
    page_end = min(paginator.num_pages, page_start + 9)
    page_numbers = list(range(page_start, page_end + 1))

    kept = request.GET.copy()
    kept.pop('sort', None)
    kept.pop('dir', None)
    kept.pop('page', None)
    kept.pop('_rv', None)
    filter_qs = kept.urlencode()
    assignee_choices = list(
        User.objects.filter(is_active=True).order_by('username').values_list('username', flat=True)
    )
    return render(
        request,
        'auto_amazon/asin_dashboard.html',
        {
            'rows': rows,
            'page_obj': page_obj,
            'page_numbers': page_numbers,
            'sort': sort_key,
            'dir': direction,
            'filter_qs': filter_qs,
            'per_page': per_page,
            'assignee_choices': assignee_choices,
            'filters': {
                'ops_slot': ops_slot,
                'ops_range': ops_range,
                'selected_grades': allowed,
                'roi_verified': roi_verified_f if roi_verified_f in ('yes', 'no') else '',
                'updated_from': (request.GET.get('updated_from') or '').strip(),
                'updated_to': (request.GET.get('updated_to') or '').strip(),
            },
        },
    )


@login_required
@require_POST
def dashboard_ops_filter(request):
    """按运营难度列 JSON 筛选 data_origin 并写入同目录新文件。"""
    row_id = (request.POST.get('row_id') or '').strip()
    slot = (request.POST.get('slot') or '1').strip()
    field_map = {'1': 'ops_difficulty_1', '2': 'ops_difficulty_2', '3': 'ops_difficulty_3'}
    field = field_map.get(slot)
    if not field or not row_id.isdigit():
        messages.error(request, '参数无效。')
        return redirect('index')
    row = AsinDashboardRow.objects.filter(pk=int(row_id)).first()
    if not row or row.user_id != request.user.id:
        messages.error(request, '只能操作本人导入的数据行。')
        return redirect('index')
    payload = getattr(row, field, '') or ''
    ok, msg = run_dashboard_ops_filter(row.asin, payload)
    if ok:
        messages.success(request, msg)
    else:
        messages.error(request, msg)
    return redirect('index')



def _wizard_job_key(job_id: str) -> str:
    return f'wizard_job_{job_id}'


def _user_active_job_key(user_id: int) -> str:
    return f'active_job_user_{user_id}'


def _set_user_active_job(user_id: int, job_id: str) -> None:
    cache.set(_user_active_job_key(user_id), job_id, WIZARD_JOB_TTL)


def _clear_user_active_job(user_id: int, job_id: str) -> None:
    cur = cache.get(_user_active_job_key(user_id))
    if cur == job_id:
        cache.delete(_user_active_job_key(user_id))


def _json_sanitize(obj):
    """写入 DB 前把 numpy 等转为可 JSON 序列化的原生类型。"""
    try:
        import numpy as np

        if isinstance(obj, (np.floating, np.float32, np.float64)):
            return float(obj)
        if isinstance(obj, (np.integer, np.int32, np.int64)):
            return int(obj)
    except ImportError:
        pass
    if isinstance(obj, dict):
        return {k: _json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_sanitize(x) for x in obj]
    return obj


def _ops_cell_json(keyword: str, review_inner: dict) -> str:
    """
    一个关键词对应一个运营难度字段，结构为：
    { "关键词文本": { "review_interval": { 区间[], 平均销量[], 运营难度[] } } }
    整体作为一块数据，供前端图形化展示，不拆行展示区间。
    """
    inner = _json_sanitize(review_inner)
    payload = {keyword: {'review_interval': inner}}
    return json.dumps(payload, ensure_ascii=False)


def _ops_difficulty_three_fields(data: dict, asin: str) -> tuple[str, str, str]:
    """
    运营难度1/2/3 = 前三个关键词，每个字段存该关键词下完整 review_interval（见 _ops_cell_json）。
    """
    ri_outer = data.get('review_interval')
    if not isinstance(ri_outer, dict):
        return '', '', ''

    asin_node = ri_outer.get(asin)
    if not isinstance(asin_node, dict):
        if len(ri_outer) == 1:
            asin_node = next(iter(ri_outer.values()))
        else:
            return '', '', ''
    if not isinstance(asin_node, dict):
        return '', '', ''

    out: list[str] = []
    for kw in asin_node.keys():
        inner = asin_node.get(kw)
        if not isinstance(inner, dict):
            continue
        block = inner.get('review_interval')
        if not isinstance(block, dict):
            continue
        out.append(_ops_cell_json(kw, block))
        if len(out) >= 3:
            break

    while len(out) < 3:
        out.append('')
    return out[0], out[1], out[2]


def _persist_wizard_results(user_id: int, result: dict, parity: float) -> int:
    """按 (user, asin) 覆盖写入：已存在则 update，不新增重复行。"""

    def _to_float(v):
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    n = 0
    touched_asins: set[str] = set()
    for asin, data in result.items():
        if not isinstance(data, dict):
            continue
        mr = _to_float(data.get('monthly_results'))
        pm = _to_float(data.get('profit_margin'))
        up = _to_float(data.get('unit_purchase'))
        mp1 = _to_float(data.get('monthly_profit1'))
        ppo = _to_float(data.get('profit_per_order'))
        rp = _to_float(data.get('ranking_percent'))
        hd = _to_float(data.get('head_distance'))
        ac = _to_float(data.get('actual_cost'))
        ad_roi = _to_float(data.get('ad_removed_roi'))

        existing = AsinDashboardRow.objects.filter(user_id=user_id, asin=asin).first()
        ranking_to_store = rp
        if existing is not None and existing.ranking_percent is not None:
            try:
                if float(existing.ranking_percent) != 0.0:
                    ranking_to_store = existing.ranking_percent
            except (TypeError, ValueError):
                pass

        # mst = None
        # if mr is not None and ppo is not None:
        #     mst = round(mr * ppo, 2)
        hat = None
        if hd is not None and up is not None:
            hat = round(hd + up, 2)

        o1, o2, o3 = _ops_difficulty_three_fields(data, asin)

        AsinDashboardRow.objects.update_or_create(
            user_id=user_id,
            asin=asin,
            defaults={
                'profit_margin': pm,
                'ranking_percent': ranking_to_store,
                'ops_difficulty_1': o1,
                'ops_difficulty_2': o2,
                'ops_difficulty_3': o3,
                'unit_purchase': up,
                'monthly_results': mr,
                'profit_per_order': ppo,
                'monthly_profit1': mp1,
                'monthly_sales_total': mp1,
                'head_distance': hd,
                'actual_cost': ac,
                'head_actual_total': hat,
                'ad_removed_roi': ad_roi*100,
                'product_grade': product_grade_from_monthly_profit1(mp1),
                'sales_trend_json': '',
                'exchange_rate': parity,
            },
        )
        n += 1
        touched_asins.add(asin)
    _touch_asin_updates(touched_asins)
    return n


def _run_wizard_job(
        job_id: str,
        user_id: int,
        asins: list[str] | None,
        parity: float,
        cost_overrides: dict | None = None,
) -> None:
    key = _wizard_job_key(job_id)
    close_old_connections()
    try:

        def on_line(line: str) -> None:
            ent = cache.get(key) or {}
            prog = ent.get('progress', [])
            short = line[:500] if len(line) > 500 else line
            prog.append(short)
            if len(prog) > 160:
                prog = prog[-160:]
            ent['progress'] = prog
            ent['status'] = 'running'
            ent['user_id'] = user_id
            cache.set(key, ent, WIZARD_JOB_TTL)

        result = run_seller_wizard(asins, parity, cost_overrides=cost_overrides, on_stderr_line=on_line)
        n = _persist_wizard_results(user_id, result, parity)

        ent = cache.get(key) or {}
        ent['status'] = 'done'
        ent['rows_written'] = n
        ent['redirect'] = reverse('index')
        ent['user_id'] = user_id
        cache.set(key, ent, 900)
    except Exception as e:
        import traceback

        tb = traceback.format_exc()
        ent = cache.get(key) or {}
        ent['status'] = 'error'
        ent['error'] = f'{type(e).__name__}: {e}'
        ent['error_detail'] = tb[-6000:] if len(tb) > 6000 else tb
        ent['user_id'] = user_id
        cache.set(key, ent, 3600)
    finally:
        _clear_user_active_job(user_id, job_id)
        close_old_connections()


def _run_ad_difficulty_job(job_id: str, user_id: int, asins: list[str]) -> None:
    key = _wizard_job_key(job_id)
    close_old_connections()
    try:
        def on_line(line: str) -> None:
            ent = cache.get(key) or {}
            prog = ent.get('progress', [])
            short = line[:500] if len(line) > 500 else line
            prog.append(short)
            if len(prog) > 160:
                prog = prog[-160:]
            ent['progress'] = prog
            ent['status'] = 'running'
            ent['user_id'] = user_id
            cache.set(key, ent, WIZARD_JOB_TTL)

        result = run_ad_difficulty_for_asins(asins, on_stderr_line=on_line)
        rows_sel = list(
            AsinDashboardRow.objects.filter(user_id=user_id, asin__in=asins).only('pk', 'asin')
        )
        updated = 0
        for r in rows_sel:
            payload = result.get(r.asin) or {}
            rp = payload.get('ranking_percent')
            try:
                rp_num = float(rp)
            except (TypeError, ValueError):
                rp_num = 0.0
            AsinDashboardRow.objects.filter(user_id=user_id, pk=r.pk).update(ranking_percent=rp_num)
            updated += 1
        _touch_asin_updates({r.asin for r in rows_sel})

        ent = cache.get(key) or {}
        ent['status'] = 'done'
        ent['rows_written'] = updated
        ent['redirect'] = reverse('index')
        ent['user_id'] = user_id
        cache.set(key, ent, 900)
    except Exception as e:
        import traceback

        tb = traceback.format_exc()
        ent = cache.get(key) or {}
        ent['status'] = 'error'
        ent['error'] = f'{type(e).__name__}: {e}'
        ent['error_detail'] = tb[-6000:] if len(tb) > 6000 else tb
        ent['user_id'] = user_id
        cache.set(key, ent, 3600)
    finally:
        _clear_user_active_job(user_id, job_id)
        close_old_connections()


def _parse_compute_local_form(request):
    """计算本地数据：仅要求汇率，ASIN 由本地逻辑决定。"""
    parity_raw = (request.POST.get('exchange_rate') or '').strip()

    try:
        parity = float(parity_raw)
    except ValueError:
        return None, '请输入有效汇率（数字）。'
    if parity <= 0:
        return None, '汇率必须大于 0。'
    return parity, None


def _discover_local_asins(force_recompute: bool) -> tuple[list[str], list[str]]:
    """
    扫描 media/file 下 ASIN 目录。
    - force_recompute=False: 跳过目录根下已有 *ROI-US-pack*.xlsx 的 ASIN
    - force_recompute=True: 全部纳入
    返回 (待计算 asins, 被跳过 asins)。
    """
    root = media_root()
    pending: list[str] = []
    skipped: list[str] = []
    for p in root.iterdir():
        if not p.is_dir():
            continue
        asin = p.name.strip().upper()
        if not re.match(r'^B0[A-Z0-9]{8}$', asin):
            continue
        has_roi = any(
            c.is_file() and 'ROI-US-pack' in c.name and c.suffix.lower() in ('.xlsx', '.xlsm')
            for c in p.iterdir()
        )
        if has_roi and not force_recompute:
            skipped.append(asin)
            continue
        pending.append(asin)
    return sorted(pending), sorted(skipped)


@login_required
@require_POST
def upload_start(request):
    active = cache.get(_user_active_job_key(request.user.id))
    if active:
        return JsonResponse(
            {
                'ok': False,
                'error': '已有任务在运行中，请等待完成后再发起新任务。',
                'job_id': active,
            },
            status=400,
        )
    parity, err = _parse_compute_local_form(request)
    if err:
        return JsonResponse({'ok': False, 'error': err}, status=400)
    selected = [normalize_asin(x) for x in request.POST.getlist('asins') if str(x).strip()]
    if not selected:
        return JsonResponse({'ok': False, 'error': '请先勾选至少一个待计算 ASIN。'}, status=400)
    include_recomputed = str(request.POST.get('recompute_existing') or '').lower() in ('1', 'true', 'on', 'yes')
    pending, skipped = _discover_local_asins(force_recompute=include_recomputed)
    allowed_set = set(pending)
    asins = sorted({a for a in selected if a in allowed_set})
    if not asins:
        return JsonResponse(
            {
                'ok': False,
                'error': '勾选的 ASIN 不在当前可计算列表中，请刷新页面后重试。',
            },
            status=400,
        )
    job_id = uuid.uuid4()
    jid = str(job_id)
    key = _wizard_job_key(jid)
    _set_user_active_job(request.user.id, jid)
    prog = [
        '本地计算任务已创建，正在启动分析子进程…',
        f'当前汇率：{parity}。',
        f'本次待计算 ASIN：{len(asins)} 个。',
    ]
    if skipped and not include_recomputed:
        prog.append(f'当前未计算列表之外（已存在 ROI-US-pack）：{len(skipped)} 个。')
    cache.set(
        key,
        {
            'status': 'running',
            'user_id': request.user.id,
            'progress': prog,
        },
        WIZARD_JOB_TTL,
    )
    t = threading.Thread(
        target=_run_wizard_job,
        args=(jid, request.user.id, asins, parity),
        daemon=True,
    )
    t.start()
    return JsonResponse({'ok': True, 'job_id': jid, 'selected_count': len(asins), 'skipped_count': len(skipped)})


@login_required
def upload_job_status(request, job_id):
    key = _wizard_job_key(str(job_id))
    ent = cache.get(key)
    if not ent:
        return JsonResponse({'ok': False, 'error': '任务不存在或已过期'}, status=404)
    if ent.get('user_id') != request.user.id:
        return JsonResponse({'ok': False, 'error': '无权访问该任务'}, status=403)
    err_tail = ent.get('error_detail') or ''
    if len(err_tail) > 8000:
        err_tail = err_tail[-8000:]
    return JsonResponse(
        {
            'ok': True,
            'status': ent.get('status'),
            'progress': ent.get('progress', []),
            'error': ent.get('error'),
            'error_detail': err_tail if ent.get('status') == 'error' else None,
            'rows_written': ent.get('rows_written'),
            'redirect': ent.get('redirect') or reverse('index'),
        }
    )


@login_required
def upload_page(request):
    return redirect('compute_roi')


@login_required
def compute_roi_page(request):
    include_recomputed = str(request.GET.get('recompute_existing') or '').lower() in ('1', 'true', 'on', 'yes')
    pending_asins, skipped_asins = _discover_local_asins(force_recompute=False)
    all_asins = sorted(set(pending_asins + skipped_asins)) if include_recomputed else pending_asins
    asin_kw = (request.GET.get('asin_kw') or '').strip().upper()
    if asin_kw:
        all_asins = [a for a in all_asins if asin_kw in a]
    per_page = _compute_roi_per_page(request)
    paginator = Paginator(all_asins, per_page)
    page_obj = paginator.get_page(request.GET.get('page') or 1)
    kept = request.GET.copy()
    kept.pop('page', None)
    filter_qs = kept.urlencode()
    return render(
        request,
        'auto_amazon/compute_roi.html',
        {
            'rows': list(page_obj.object_list),
            'page_obj': page_obj,
            'per_page': per_page,
            'filter_qs': filter_qs,
            'asin_kw': asin_kw,
            'total_pending': len(pending_asins),
            'total_all': len(all_asins),
            'include_recomputed': include_recomputed,
        },
    )


@login_required
@user_passes_test(lambda u: bool(getattr(u, 'is_superuser', False)))
def fetch_data_page(request):
    return render(request, 'auto_amazon/fetch_data.html')


@login_required
def excel_page(request):
    assignable_users = list(
        User.objects.filter(is_active=True).order_by('username').values('id', 'username')
    )
    uploader_user_ids = ImportedMediaPath.objects.values_list('user_id', flat=True).distinct()
    uploader_users = list(
        User.objects.filter(id__in=uploader_user_ids, is_active=True)
        .order_by('username')
        .values('id', 'username')
    )
    return render(
        request,
        'auto_amazon/excel.html',
        {
            'assignable_users': assignable_users,
            'assignable_users_json': json.dumps(assignable_users, ensure_ascii=False),
            'uploader_users_json': json.dumps(uploader_users, ensure_ascii=False),
            'is_superuser': bool(request.user.is_superuser),
        },
    )


@login_required
def excel_editor_page(request):
    if request.GET.get('local') == '1':
        return render(
            request,
            'auto_amazon/excel_editor.html',
            {'rel_path': '', 'local_mode': True, 'page_title': 'Excel', 'read_only_excel': False},
        )
    rel = (request.GET.get('path') or '').strip().replace('\\', '/')
    excel_home = 'excel' if _require_superuser_for_excel_audit(request) else 'index'
    if not rel:
        messages.error(request, '请从文件库选择要打开的文件。')
        return redirect(excel_home)
    path = safe_media_path_global(rel)
    if path is None or not path.is_file():
        messages.error(request, '文件不存在或路径无效。')
        return redirect(excel_home)
    if path.suffix.lower() not in ('.xlsx', '.xlsm'):
        messages.error(request, '仅支持 .xlsx / .xlsm 文件。')
        return redirect(excel_home)
    if not _require_superuser_for_excel_audit(request) and not user_can_access_excel_media_path(
        request.user, rel
    ):
        messages.error(request, '无权打开该文件（需由管理员将对应 ASIN 文件夹分配给您）。')
        return redirect('index')
    return render(
        request,
        'auto_amazon/excel_editor.html',
        {
            'rel_path': rel,
            'local_mode': False,
            'page_title': _first_word_from_filename(path.name),
            'read_only_excel': False,
        },
    )


@login_required
@require_GET
def excel_browse(request):
    rel = request.GET.get('path', '').strip().replace('\\', '/')
    is_super = _require_superuser_for_excel_audit(request)
    if not is_super and rel:
        if not user_can_access_excel_media_path(request.user, rel):
            return JsonResponse({'ok': False, 'error': '无权限访问该目录'}, status=403)
    target = safe_media_path_global(rel)
    if target is None:
        return JsonResponse({'ok': False, 'error': '路径非法'}, status=400)
    if not target.exists():
        return JsonResponse({'ok': False, 'error': '路径不存在'}, status=404)
    if not target.is_dir():
        return JsonResponse({'ok': False, 'error': '不是文件夹'}, status=400)
    try:
        dashboard_asins = {
            normalize_asin(a) for a in AsinDashboardRow.objects.values_list('asin', flat=True)
        }
        roi_verified_asins = {
            normalize_asin(a) for a in AsinRoiPackVerification.objects.values_list('asin', flat=True)
        }
        updated_map = {
            normalize_asin(a): t
            for a, t in AsinDataUpdateStamp.objects.values_list('asin', 'updated_at')
        }
        assign_map: dict[str, list[str]] = {}
        for obj in AsinFolderAssignment.objects.prefetch_related('assignees').all():
            assign_map[normalize_asin(obj.asin)] = sorted(
                {u.username for u in obj.assignees.all()}
            )
        assigned_set = set(user_assigned_asin_codes(request.user)) if not is_super else set()
        import_roots = user_imported_asin_codes(request.user) if not is_super else set()
        owned_paths = set()
        if not is_super:
            oq = ImportedMediaPath.objects.filter(user=request.user)
            if rel:
                owned_paths = set(
                    oq.filter(Q(rel_path=rel) | Q(rel_path__startswith=f'{rel}/')).values_list(
                        'rel_path', flat=True
                    )
                )
            else:
                owned_paths = set(oq.values_list('rel_path', flat=True))
        uploaders_by_asin: dict[str, set[str]] = defaultdict(set)
        for rpath, uname in ImportedMediaPath.objects.values_list('rel_path', 'user__username'):
            rp = str(rpath).replace('\\', '/').strip('/')
            if not rp:
                continue
            seg = rp.split('/')[0].strip().upper()
            if re.match(r'^B0[A-Z0-9]{8}$', seg):
                uploaders_by_asin[seg].add(uname)
    except DatabaseError as e:
        return JsonResponse(
            {
                'ok': False,
                'error': (
                    '数据库未就绪：请在服务器项目目录执行 python manage.py migrate 后再试。'
                    f' 详情：{e}'
                ),
            },
            status=503,
        )
    uploaded_by_filter = (request.GET.get('uploaded_by') or '').strip()
    items = []
    try:
        entries = sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except OSError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)
    path_batch: list[str] = []
    for p in entries:
        if p.name.startswith('.'):
            continue
        cr = f'{rel}/{p.name}' if rel else p.name
        cr = cr.replace('\\', '/').strip('/')
        path_batch.append(cr)
    uploader_by_rel_file: dict[str, str] = {}
    if path_batch:
        uploader_by_rel_file = dict(
            ImportedMediaPath.objects.filter(rel_path__in=path_batch).values_list(
                'rel_path', 'user__username'
            )
        )
    for p in entries:
        if p.name.startswith('.'):
            continue
        child_rel = f'{rel}/{p.name}' if rel else p.name
        child_rel = child_rel.replace('\\', '/').strip('/')
        can_delete_item = True if is_super else (child_rel in owned_paths)
        if p.is_dir():
            nm = p.name.strip().upper()
            is_asin_dir = re.match(r'^B0[A-Z0-9]{8}$', nm) is not None
            if not is_super:
                if rel == '':
                    if not is_asin_dir:
                        continue
                    if nm not in assigned_set and nm not in import_roots:
                        continue
                elif not user_can_access_excel_media_path(request.user, child_rel):
                    continue
            uploaders_list = sorted(uploaders_by_asin.get(nm, [])) if is_asin_dir else []
            if rel == '' and uploaded_by_filter and is_asin_dir:
                if uploaded_by_filter not in uploaders_by_asin.get(nm, set()):
                    continue
            assignees = assign_map.get(nm, []) if is_asin_dir else []
            updated_at = updated_map.get(nm)
            updated_label = timezone.localtime(updated_at).strftime('%Y-%m-%d %H:%M:%S') if updated_at else ''
            if is_asin_dir:
                dir_uploaders = uploaders_list
            else:
                ud = uploader_by_rel_file.get(child_rel)
                dir_uploaders = [ud] if ud else []
            items.append(
                {
                    'name': p.name,
                    'type': 'dir',
                    'calculated': bool(is_asin_dir and nm in dashboard_asins),
                    'is_asin_dir': bool(is_asin_dir),
                    'assigned': bool(assignees),
                    'assignees': assignees,
                    'roi_verified': bool(is_asin_dir and nm in roi_verified_asins),
                    'updated_at': updated_label,
                    'updated_at_ts': int(updated_at.timestamp() * 1000) if updated_at else 0,
                    'imported_by_me': bool(is_asin_dir and nm in import_roots),
                    'uploaders': dir_uploaders,
                    'can_delete': can_delete_item,
                }
            )
        else:
            if not is_super and not user_can_access_excel_media_path(request.user, child_rel):
                continue
            try:
                st = p.stat()
                size = st.st_size
            except OSError:
                size = 0
            fu_file = uploader_by_rel_file.get(child_rel)
            items.append({
                'name': p.name,
                'type': 'file',
                'ext': p.suffix.lower() or '',
                'size': size,
                'calculated': None,
                'is_asin_dir': False,
                'assigned': False,
                'assignees': [],
                'updated_at': '',
                'updated_at_ts': 0,
                'imported_by_me': bool(child_rel in owned_paths),
                'uploaders': [fu_file] if fu_file else [],
                'can_delete': can_delete_item,
            })
    if rel == '':
        items.sort(
            key=lambda it: (
                it.get('type') != 'dir',
                not bool(it.get('is_asin_dir')),
                -(it.get('updated_at_ts') or 0),
                str(it.get('name') or '').lower(),
            )
        )
    parent = parent_rel(rel) if rel else None
    return JsonResponse({
        'ok': True,
        'path': rel,
        'parent': parent,
        'items': items,
    })


@login_required
@require_GET
def excel_download(request):
    rel = (request.GET.get('path') or '').strip().replace('\\', '/')
    if not rel:
        raise Http404
    if not _require_superuser_for_excel_audit(request) and not user_can_access_excel_media_path(
        request.user, rel
    ):
        raise Http404
    path = safe_media_path_global(rel)
    if path is None or not path.is_file():
        raise Http404
    try:
        fh = open(path, 'rb')
    except OSError:
        raise Http404
    return FileResponse(fh, as_attachment=True, filename=path.name)


@login_required
@require_POST
def excel_delete(request):
    is_super = _require_superuser_for_excel_audit(request)
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': '无效的 JSON'}, status=400)
    paths = payload.get('paths')
    if not isinstance(paths, list):
        one = payload.get('path')
        paths = [one] if one else []
    paths = [str(p).strip().replace('\\', '/') for p in paths if p is not None and str(p).strip()]
    if not paths:
        return JsonResponse({'ok': False, 'error': '缺少 path(s)'}, status=400)
    root = media_root()
    for rel in paths:
        if not rel:
            return JsonResponse({'ok': False, 'error': '不能删除根目录'}, status=400)
        path = safe_media_path_global(rel)
        if path is None:
            return JsonResponse({'ok': False, 'error': f'非法路径: {rel}'}, status=400)
        try:
            path.relative_to(root)
        except ValueError:
            return JsonResponse({'ok': False, 'error': f'非法路径: {rel}'}, status=400)
        if path == root:
            return JsonResponse({'ok': False, 'error': '不能删除根目录'}, status=400)
        if not is_super:
            if not user_can_access_excel_media_path(request.user, rel):
                return JsonResponse({'ok': False, 'error': '无权限删除该路径'}, status=403)
            if not ImportedMediaPath.objects.filter(user=request.user, rel_path=rel).exists():
                return JsonResponse(
                    {'ok': False, 'error': '只能删除本人通过「导入」上传的文件或文件夹（管理员分配的资料无删除权限）'},
                    status=403,
                )
            if path.is_dir():
                for fp in path.rglob('*'):
                    if not fp.is_file():
                        continue
                    sub_rel = str(fp.relative_to(root)).replace('\\', '/')
                    if not ImportedMediaPath.objects.filter(user=request.user, rel_path=sub_rel).exists():
                        return JsonResponse(
                            {
                                'ok': False,
                                'error': f'文件夹内存在非本人导入的文件，无法整夹删除：{sub_rel}',
                            },
                            status=403,
                        )
        try:
            if is_super:
                ImportedMediaPath.objects.filter(Q(rel_path=rel) | Q(rel_path__startswith=f'{rel}/')).delete()
            else:
                ImportedMediaPath.objects.filter(user=request.user).filter(
                    Q(rel_path=rel) | Q(rel_path__startswith=f'{rel}/')
                ).delete()
        except DatabaseError as e:
            return JsonResponse(
                {
                    'ok': False,
                    'error': (
                        '数据库未就绪或表缺失：请在项目目录执行 python manage.py migrate 后再试。'
                        f' 详情：{e}'
                    ),
                },
                status=503,
            )
        try:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.is_file():
                path.unlink()
        except OSError as e:
            return JsonResponse({'ok': False, 'error': str(e)}, status=400)
    return JsonResponse({'ok': True})


@login_required
@require_POST
def excel_import_chunk(request):
    """分片上传 ZIP（用于大文件，避免单次请求内存过大）。"""
    try:
        chunk_index = int(request.POST.get('chunk_index', '-1'))
        total_chunks = int(request.POST.get('total_chunks', '0'))
    except ValueError:
        return JsonResponse({'ok': False, 'error': '分片参数无效'}, status=400)
    staging_id = (request.POST.get('staging_id') or '').strip()
    blob = request.FILES.get('file')
    if not blob:
        return JsonResponse({'ok': False, 'error': '缺少分片数据'}, status=400)
    data = b''.join(blob.chunks())
    try:
        sid, meta = import_append_chunk(request.user.id, staging_id or None, chunk_index, total_chunks, data)
    except PermissionError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=403)
    except ValueError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)
    out: dict = {
        'ok': True,
        'staging_id': sid,
        'next_chunk': meta.get('next_chunk'),
        'total_chunks': meta.get('total_chunks'),
    }
    if meta.get('status') == 'ready':
        out['ready'] = True
        out['conflicts'] = meta.get('conflicts') or []
        out['file_count'] = meta.get('file_count', 0)
    return JsonResponse(out)


@login_required
@require_POST
def excel_import_commit(request):
    """确认解压：与现有文件冲突时返回 409，前端可选择覆盖或仅跳过已存在项。"""
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': '无效的 JSON'}, status=400)
    staging_id = (payload.get('staging_id') or '').strip()
    overwrite = bool(payload.get('overwrite'))
    skip_existing = bool(payload.get('skip_existing'))
    if not staging_id:
        return JsonResponse({'ok': False, 'error': '缺少 staging_id'}, status=400)
    if overwrite and skip_existing:
        return JsonResponse({'ok': False, 'error': '不能同时选择覆盖与跳过已存在文件'}, status=400)
    try:
        sdir, meta = load_ready_staging(request.user.id, staging_id)
    except PermissionError as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=403)
    except (ValueError, FileNotFoundError) as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=400)
    mr = media_root()
    conflicts = refresh_conflicts_in_meta(mr, sdir, meta)
    if conflicts and not overwrite and not skip_existing:
        return JsonResponse(
            {
                'ok': False,
                'need_choice': True,
                'conflicts': conflicts,
                'staging_id': staging_id,
            },
            status=409,
        )
    zip_path = sdir / 'upload.zip'
    skip_if_exists = skip_existing and not overwrite
    try:
        written, skipped_existing = extract_zip_to_media_root(zip_path, mr, skip_if_exists=skip_if_exists)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': f'解压失败：{e}'}, status=400)
    try:
        for rp in ensure_dir_nodes_registered(written):
            ImportedMediaPath.objects.update_or_create(rel_path=rp, defaults={'user': request.user})
        asins = {normalize_asin(x.split('/')[0]) for x in written if x}
        _touch_asin_updates(asins)
    except DatabaseError as e:
        cleanup_staging_dir(sdir)
        return JsonResponse(
            {
                'ok': False,
                'error': (
                    'ZIP 已解压到 media/file，但写入导入记录失败；请执行 python manage.py migrate 后刷新。'
                    f' 详情：{e}'
                ),
                'written': len(written),
            },
            status=503,
        )
    cleanup_staging_dir(sdir)
    return JsonResponse(
        {
            'ok': True,
            'written': len(written),
            'skipped_existing': len(skipped_existing),
        }
    )


@login_required
@require_POST
def excel_batch_download(request):
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': '无效的 JSON'}, status=400)
    paths = payload.get('paths')
    if not isinstance(paths, list) or not paths:
        return JsonResponse({'ok': False, 'error': '缺少 paths'}, status=400)
    root = media_root()
    buf = BytesIO()
    added = 0
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for rel in paths:
            rel = str(rel).strip().replace('\\', '/')
            if not rel:
                continue
            if not _require_superuser_for_excel_audit(request) and not user_can_access_excel_media_path(
                request.user, rel
            ):
                continue
            path = safe_media_path_global(rel)
            if path is None or not path.is_file():
                continue
            try:
                arc = str(path.relative_to(root)).replace('\\', '/')
            except ValueError:
                continue
            zf.write(path, arcname=arc)
            added += 1
    if added == 0:
        return JsonResponse({'ok': False, 'error': '没有可打包的文件'}, status=400)
    buf.seek(0)
    return FileResponse(
        buf,
        as_attachment=True,
        filename='download.zip',
        content_type='application/zip',
    )


@login_required
@require_POST
def excel_load_media(request):
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': '无效的 JSON'}, status=400)
    rel = (payload.get('path') or '').strip().replace('\\', '/')
    if not _require_superuser_for_excel_audit(request) and not user_can_access_excel_media_path(
        request.user, rel
    ):
        return JsonResponse({'ok': False, 'error': '无权限读取该文件'}, status=403)
    path = safe_media_path_global(rel)
    if path is None or not path.is_file():
        return JsonResponse({'ok': False, 'error': '文件不存在或路径非法'}, status=400)
    if path.suffix.lower() not in ('.xlsx', '.xlsm'):
        return JsonResponse({'ok': False, 'error': '仅支持 .xlsx / .xlsm'}, status=400)
    payload, err = read_active_sheet_rich(path)
    if err:
        # openpyxl 常见报错：xlsx 内部 XML 非法 / 工作表 XML 解析失败
        msg = str(err)
        hint = ''
        low = msg.lower()
        if 'invalid xml' in low or 'could not read worksheets' in low or 'unable to read workbook' in low:
            hint = (
                '（通常是 Excel 文件内部 XML 损坏或由非标准工具生成导致）\n'
                '建议：1) 用 Excel/WPS 打开该文件，选择“打开并修复/修复”，然后“另存为”新的 .xlsx；\n'
                '2) 若无法打开，重新导出/重新生成该文件；\n'
                '3) 也可尝试先下载到本地用 Excel 修复后再上传。'
            )
        return JsonResponse({'ok': False, 'error': f'无法读取 Excel：{msg}{hint}'}, status=400)
    if _is_search_sheet_filename(path.name):
        deleted_asins = _deleted_asin_set_from_data_origin(path)
        _highlight_deleted_rows_for_search(payload, deleted_asins)
    if is_roi_us_pack_filename(path.name):
        parent = path.parent.name.strip().upper()
        if re.match(r'^B0[A-Z0-9]{8}$', parent):
            a = normalize_asin(parent)
            payload['roi_pack_verified'] = AsinRoiPackVerification.objects.filter(asin=a).exists()
    payload['ok'] = True
    payload['path'] = rel
    return JsonResponse(payload)


@login_required
@require_POST
def excel_save_media(request):
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': '无效的 JSON'}, status=400)
    rel = (payload.get('path') or '').strip().replace('\\', '/')
    if not _require_superuser_for_excel_audit(request) and not user_can_access_excel_media_path(
        request.user, rel
    ):
        return JsonResponse({'ok': False, 'error': '无权限保存该文件'}, status=403)
    rows = payload.get('rows')
    if not isinstance(rows, list):
        return JsonResponse({'ok': False, 'error': '缺少 rows'}, status=400)
    path = safe_media_path_global(rel)
    if path is None or not path.is_file():
        return JsonResponse({'ok': False, 'error': '文件不存在或路径非法'}, status=400)
    if path.suffix.lower() not in ('.xlsx', '.xlsm'):
        return JsonResponse({'ok': False, 'error': '仅支持 .xlsx / .xlsm'}, status=400)
    ok, err = save_sheet_values_preserving_format(path, rows)
    if not ok:
        return JsonResponse({'ok': False, 'error': err or '保存失败'}, status=400)
    parent_asin = normalize_asin(path.parent.name)
    if re.match(r'^B0[A-Z0-9]{8}$', parent_asin):
        _touch_asin_updates({parent_asin})
    return JsonResponse({'ok': True, 'path': rel})


@login_required
@require_POST
def excel_import_data_origin(request):
    """将上传 Excel 的数据行追加导入到当前 *_data_origin.xlsx。"""
    rel = (request.POST.get('path') or '').strip().replace('\\', '/')
    if not rel:
        return JsonResponse({'ok': False, 'error': '缺少 path'}, status=400)
    if not _require_superuser_for_excel_audit(request) and not user_can_access_excel_media_path(
        request.user, rel
    ):
        return JsonResponse({'ok': False, 'error': '无权限导入到该文件'}, status=403)
    path = safe_media_path_global(rel)
    if path is None or not path.is_file():
        return JsonResponse({'ok': False, 'error': '目标文件不存在或路径非法'}, status=400)
    if not path.name.lower().endswith('_data_origin.xlsx'):
        return JsonResponse({'ok': False, 'error': '仅支持导入到 *_data_origin.xlsx'}, status=400)

    up = request.FILES.get('file')
    if up is None:
        return JsonResponse({'ok': False, 'error': '缺少上传文件'}, status=400)
    up_name = (getattr(up, 'name', '') or '').lower()
    if not (up_name.endswith('.xlsx') or up_name.endswith('.xlsm')):
        return JsonResponse({'ok': False, 'error': '仅支持上传 .xlsx / .xlsm'}, status=400)
    skip_header = str(request.POST.get('skip_header', '1')).strip() != '0'
    try:
        import_wb = load_workbook(up, read_only=True, data_only=True)
        import_ws = import_wb.active
        imported_rows = []
        max_cols = 0
        for i, row in enumerate(import_ws.iter_rows(values_only=True)):
            if skip_header and i == 0:
                continue
            vals = ['' if v is None else str(v) for v in (row or ())]
            while vals and vals[-1] == '':
                vals.pop()
            if not vals:
                continue
            imported_rows.append(vals)
            if len(vals) > max_cols:
                max_cols = len(vals)
        import_wb.close()
    except Exception as e:
        return JsonResponse({'ok': False, 'error': f'读取上传文件失败：{e}'}, status=400)

    if not imported_rows:
        return JsonResponse({'ok': False, 'error': '上传文件没有可导入的数据行'}, status=400)

    current_payload, err = read_active_sheet_rich(path)
    if err:
        return JsonResponse({'ok': False, 'error': f'读取目标文件失败：{err}'}, status=400)
    current_rows = current_payload.get('rows') or []
    target_cols = 0
    for r in current_rows:
        if isinstance(r, list) and len(r) > target_cols:
            target_cols = len(r)
    final_cols = max(target_cols, max_cols, 1)

    normalized_current = []
    for r in current_rows:
        if not isinstance(r, list):
            r = [r]
        one = []
        for c in r:
            if isinstance(c, dict):
                one.append(c.get('v', ''))
            else:
                one.append(c if c is not None else '')
        while len(one) < final_cols:
            one.append('')
        normalized_current.append(one[:final_cols])

    normalized_import = []
    for r in imported_rows:
        one = list(r)
        while len(one) < final_cols:
            one.append('')
        normalized_import.append(one[:final_cols])

    merged_rows = normalized_current + normalized_import
    ok, save_err = save_sheet_values_preserving_format(path, merged_rows)
    if not ok:
        return JsonResponse({'ok': False, 'error': save_err or '导入保存失败'}, status=400)

    parent_asin = normalize_asin(path.parent.name)
    if re.match(r'^B0[A-Z0-9]{8}$', parent_asin):
        _touch_asin_updates({parent_asin})
    return JsonResponse({'ok': True, 'path': rel, 'imported_rows': len(normalized_import)})


@login_required
@require_POST
def excel_recalc_roi_media(request):
    """仅对 ROI-US-pack.xlsx：按表内数据重算指标并写回文件（保留格式与图片）。"""
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': '无效的 JSON'}, status=400)
    rel = (payload.get('path') or '').strip().replace('\\', '/')
    if not _require_superuser_for_excel_audit(request) and not user_can_access_excel_media_path(
        request.user, rel
    ):
        return JsonResponse({'ok': False, 'error': '无权限重算该文件'}, status=403)
    path = safe_media_path_global(rel)
    if path is None or not path.is_file():
        return JsonResponse({'ok': False, 'error': '文件不存在或路径非法'}, status=400)
    if path.suffix.lower() not in ('.xlsx', '.xlsm'):
        return JsonResponse({'ok': False, 'error': '仅支持 .xlsx / .xlsm'}, status=400)
    if not is_roi_us_pack_filename(path.name):
        return JsonResponse({'ok': False, 'error': '仅支持文件名包含 ROI-US-pack 的 ROI 表'}, status=400)

    sheet_payload, err = read_active_sheet_rich(path)
    if err:
        return JsonResponse({'ok': False, 'error': f'无法读取 Excel：{err}'}, status=400)
    rows = sheet_payload.get('rows') or []
    ok, msg = recalc_roi_us_pack_rows(rows)
    if not ok:
        return JsonResponse({'ok': False, 'error': msg or '重算失败'}, status=400)
    save_ok, save_err = save_sheet_values_preserving_format(path, rows)
    if not save_ok:
        return JsonResponse({'ok': False, 'error': save_err or '保存失败'}, status=400)
    parent_asin = normalize_asin(path.parent.name)
    if re.match(r'^B0[A-Z0-9]{8}$', parent_asin):
        _touch_asin_updates({parent_asin})
    return JsonResponse({'ok': True, 'path': rel})


@login_required
@require_POST
def excel_confirm_roi_verify(request):
    """在 ROI-US-pack 编辑器中确认校验：将对应 ASIN 在看板与数据审核中标记为「是」。"""
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': '无效的 JSON'}, status=400)
    rel = (payload.get('path') or '').strip().replace('\\', '/')
    if not rel:
        return JsonResponse({'ok': False, 'error': '缺少 path'}, status=400)
    if not _require_superuser_for_excel_audit(request) and not user_can_access_excel_media_path(
        request.user, rel
    ):
        return JsonResponse({'ok': False, 'error': '无权限'}, status=403)
    path = safe_media_path_global(rel)
    if path is None or not path.is_file():
        return JsonResponse({'ok': False, 'error': '文件不存在或路径非法'}, status=400)
    if not is_roi_us_pack_filename(path.name):
        return JsonResponse({'ok': False, 'error': '仅支持 ROI-US-pack 表确认校验'}, status=400)
    parent = path.parent.name.strip().upper()
    if not re.match(r'^B0[A-Z0-9]{8}$', parent):
        return JsonResponse({'ok': False, 'error': '文件须位于 ASIN 文件夹下'}, status=400)
    asin = normalize_asin(parent)
    AsinRoiPackVerification.objects.update_or_create(
        asin=asin,
        defaults={'verified_by': request.user},
    )
    return JsonResponse({'ok': True, 'asin': asin})


@login_required
@require_POST
def excel_assign_folders(request):
    """超级管理员：将 ASIN 文件夹分配给若干用户（覆盖该 ASIN 下的分配名单）。"""
    if not _require_superuser_for_excel_audit(request):
        return JsonResponse({'ok': False, 'error': '无权限'}, status=403)
    try:
        body = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': '无效的 JSON'}, status=400)
    asins_raw = body.get('asins') or []
    user_ids = body.get('user_ids') or []
    if not isinstance(asins_raw, list) or not asins_raw:
        return JsonResponse({'ok': False, 'error': '缺少 asins'}, status=400)
    if not isinstance(user_ids, list):
        user_ids = []
    uid_set = {int(x) for x in user_ids if str(x).isdigit()}
    users = list(User.objects.filter(pk__in=uid_set, is_active=True))
    updated = 0
    for raw in asins_raw:
        a = normalize_asin(str(raw))
        if not re.match(r'^B0[A-Z0-9]{8}$', a):
            continue
        obj, _created = AsinFolderAssignment.objects.get_or_create(asin=a)
        obj.assignees.set(users)
        obj.assigned_by = request.user
        obj.save()
        updated += 1
    return JsonResponse({'ok': True, 'updated': updated})


@login_required
@require_POST
def dashboard_export_excel(request):
    """导出勾选看板行为 Excel（本人数据 + 已分配共享行）。"""
    ids = [int(x) for x in request.POST.getlist('row_ids') if str(x).isdigit()]
    if not ids:
        messages.error(request, '请先勾选要导出的记录。')
        return redirect('index')
    assigned = user_assigned_asin_codes(request.user)
    rows = list(
        AsinDashboardRow.objects.filter(pk__in=ids)
        .filter(Q(user=request.user) | Q(asin__in=assigned))
        .select_related('user')
        .order_by('asin')
    )
    if not rows:
        messages.error(request, '没有可导出的数据。')
        return redirect('index')
    label_map = _assignment_label_map({normalize_asin(r.asin) for r in rows})
    headers = [
        'ASIN',
        '数据归属用户',
        '分配人',
        '去广告毛利率%',
        '去广告投产比%',
        '体量',
        '利润额￥',
        '(体量*利润额)$',
        '采购价￥',
        '(采购价+头程)￥',
        '广告难度%',
        '产品等级',
    ]
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ak = normalize_asin(r.asin)
        assign_txt = label_map.get(ak) or ''
        ws.append(
            [
                r.asin,
                r.user.username if r.user_id else '',
                assign_txt,
                round(r.profit_margin, 2) if r.profit_margin is not None else '',
                round(r.ad_removed_roi, 2) if r.ad_removed_roi is not None else '',
                int(r.monthly_results) if r.monthly_results is not None else '',
                round(r.profit_per_order, 2) if r.profit_per_order is not None else '',
                round(r.monthly_sales_total, 2) if r.monthly_sales_total is not None else '',
                round(r.unit_purchase, 2) if r.unit_purchase is not None else '',
                round(r.head_actual_total, 2) if r.head_actual_total is not None else '',
                round(r.ranking_percent, 3) if r.ranking_percent is not None else '',
                r.product_grade or '',
            ]
        )
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    fn = f'asin_dashboard_{timezone.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    return FileResponse(
        buf,
        as_attachment=True,
        filename=fn,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@login_required
@require_POST
def excel_load(request):
    f = request.FILES.get('file')
    if not f:
        return JsonResponse({'ok': False, 'error': '未选择文件'}, status=400)
    if not f.name.lower().endswith(('.xlsx', '.xlsm')):
        return JsonResponse({'ok': False, 'error': '请上传 .xlsx 或 .xlsm 文件'}, status=400)

    try:
        raw = f.read()
        wb = load_workbook(BytesIO(raw), read_only=True, data_only=True)
    except Exception as e:
        return JsonResponse({'ok': False, 'error': f'无法读取 Excel：{e}'}, status=400)

    ws = wb.active
    sheet_title = ws.title
    rows = []
    for row in ws.iter_rows(values_only=True):
        rows.append([_cell_to_str(c) for c in row])
    wb.close()

    if not rows:
        rows = [['']]

    return JsonResponse({'ok': True, 'sheet_name': sheet_title, 'rows': rows})


def _cell_to_str(value):
    if value is None:
        return ''
    return str(value)


@login_required
@require_POST
def excel_save(request):
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': '无效的 JSON'}, status=400)

    rows = payload.get('rows')
    if not isinstance(rows, list):
        return JsonResponse({'ok': False, 'error': '缺少 rows 数组'}, status=400)

    wb = Workbook()
    ws = wb.active
    for row in rows:
        if not isinstance(row, list):
            row = [row]
        ws.append([_cell_to_str(c) for c in row])

    out = Path(settings.MEDIA_ROOT) / 'excel_exports'
    out.mkdir(parents=True, exist_ok=True)
    filename = f'export_{uuid.uuid4().hex}.xlsx'
    path = out / filename
    wb.save(path)

    return FileResponse(
        open(path, 'rb'),
        as_attachment=True,
        filename='edited.xlsx',
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
