import pandas as pd
import json
import requests
from django.conf import settings
from django.http import JsonResponse
from django.core.cache import cache
from decimal import Decimal
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.models import User
from django.db.models import Sum, Q
from django.http import HttpResponseForbidden
from .models import SalesRecord, UserProfile, Employee, SalesRecordAAABrokerage, SalesRecordMF
from .analytics import BrokerageAnalytics, DataQuality
from django.contrib.auth import views as auth_views
try:
    import numpy as np
except ImportError:
    np = None

# Placeholder functions needed for urls.py to import successfully
user_login = auth_views.LoginView.as_view(template_name='registration/login.html')
user_logout = auth_views.LogoutView.as_view(next_page='/')


def custom_logout_view(request):
    """Custom logout view that logs out the user and redirects to login page."""
    logout(request)
    return redirect('/accounts/login/')


def mutual_funds_view(request):
    """View for Mutual Funds page."""
    return render(request, 'mutual_funds.html')


def pms_aif_view(request):
    """View for PMS and AIF page."""
    return render(request, 'pms_aif.html')


def sanitize_for_json(obj):
    """Convert Decimal and other non-JSON-serializable types to JSON-friendly formats."""
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(sanitize_for_json(v) for v in obj)
    if obj is None:
        return obj
    if isinstance(obj, Decimal):
        return float(obj)
    if np:
        if isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
    return obj


def get_cached_stock(name: str, timeout: int = 600) -> dict:
    """
    Get stock data for `name`, cached in Django cache for `timeout` seconds.
    """
    cache_key = f"ticker:{name}"
    data = cache.get(cache_key)
    if data is None:
        data = _fetch_stock(name) 
        cache.set(cache_key, data, timeout=3*60*60)
    return data

def _fetch_stock(name: str) -> dict:
    """
    Call Indian API /stock endpoint for a given name.
    """
    base_url = getattr(settings, "INDIAN_STOCK_API_BASE_URL", "https://stock.indianapi.in")
    api_key = settings.INDIAN_STOCK_API_KEY

    try:
        resp = requests.get(
            f"{base_url}/stock",
            params={"name": name},
            headers={"x-api-key": api_key},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()

        # Prefer NSE price if present, fallback to BSE or reusable price
        price = None
        if data.get("currentPrice"):
            price = data["currentPrice"].get("NSE") or data["currentPrice"].get("BSE")
        if price is None and data.get("stockDetailsReusableData"):
            price = data["stockDetailsReusableData"].get("price")

        # Prefer more reliable percentChange field
        percent_change = data.get("percentChange")
        if percent_change is None and data.get("stockDetailsReusableData"):
            percent_change = data["stockDetailsReusableData"].get("percentChange")

        return {
            "company_name": data.get("companyName"),
            "value": float(price) if price not in (None, "-", "") else None,
            "change": float(percent_change) if percent_change not in (None, "-", "") else None,
            "raw": data,
        }
    except Exception:
        return {"company_name": name, "value": 0, "change": 0}


def market_ticker(request):
    """
    Returns JSON with Sensex, Nifty 50, Gold, and Alpha Strategy values.
    """
    try:
        index_map = getattr(settings, "INDEX_NAME_MAP", {})

        sensex = get_cached_stock(index_map.get("sensex", "Sensex"))
        nifty50 = get_cached_stock(index_map.get("nifty50", "Nifty 50"))
        gold = get_cached_stock(index_map.get("gold", "Gold"))
        alpha = get_cached_stock(index_map.get("alpha_strategy", "ITBEES"))

        payload = {
            "sensex": {"value": sensex["value"], "change": sensex["change"]},
            "nifty50": {"value": nifty50["value"], "change": nifty50["change"]},
            "gold": {"value": gold["value"], "change": gold["change"]},
            "alpha_strategy": {"value": alpha["value"], "change": alpha["change"]},
        }
        return JsonResponse({"error": None, "data": payload})
    except Exception as e:
        return JsonResponse({"error": str(e), "data": None}, status=500)


@login_required
def dashboard_view(request):
    context = build_dashboard_context(user=request.user, params=request.GET)
    return render(request, 'dashboard.html', context)


def build_dashboard_context(user, params):
    """
    Shared dashboard context builder using specialized fact tables.
    """
    # Get user profile and determine role
    try:
        user_profile = UserProfile.objects.get(user=user)
        user_role = user_profile.role
    except UserProfile.DoesNotExist:
        user_role = 'R'  # Default to RM/MA role

    # Get filter parameters
    selected_rm = (params.get('rm', '') or '').strip()
    selected_ma = (params.get('ma', '') or '').strip()
    selected_manager = (params.get('manager', '') or '').strip()
    selected_period = (params.get('period', '') or '').strip()
    selected_date_from = (params.get('date_from', '') or '').strip()
    selected_date_to = (params.get('date_to', '') or '').strip()

    # --- Dropdown Option Population (HIERARCHY-BASED) ---
    all_managers = []
    all_rms = []
    all_mas = []

    # 1. Populating Manager List (only if Leader)
    if user_role == 'L':
        all_managers = list(
            Employee.objects.filter(designation='M')
            .values_list('rm_name', flat=True)
            .distinct()
            .order_by('rm_name')
        )
    
    # 2. Populating RM List
    if user_role == 'L':
        if selected_manager:
            all_rms = list(
                Employee.objects.filter(
                    Q(manager__rm_name=selected_manager) | Q(rm_manager_name=selected_manager),
                    designation__in=['L1', 'R']
                )
                .values_list('rm_name', flat=True)
                .distinct()
                .order_by('rm_name')
            )
        else:
            all_rms = list(
                Employee.objects.filter(designation__in=['L1', 'R'])
                .values_list('rm_name', flat=True)
                .distinct()
                .order_by('rm_name')
            )
    elif user_role == 'M':
        user_full_name = user.get_full_name() or user.username.replace('_', ' ').title()
        all_rms = list(
            Employee.objects.filter(
                Q(manager__rm_name=user_full_name) | Q(rm_manager_name=user_full_name),
                designation__in=['L1', 'R']
            )
            .values_list('rm_name', flat=True)
            .distinct()
            .order_by('rm_name')
        )
    elif user_role == 'R':
        user_full_name = user.get_full_name() or user.username.replace('_', ' ').title()
        all_rms = [user_full_name]

    # 3. Populating MA List
    if selected_rm:
        all_mas = list(
            Employee.objects.filter(
                Q(manager__rm_name=selected_rm) | Q(rm_manager_name=selected_rm),
                designation='MA'
            )
            .values_list('rm_name', flat=True)
            .distinct()
            .order_by('rm_name')
        )
    elif selected_manager:
        all_mas = list(
            Employee.objects.filter(
                Q(manager__rm_name=selected_manager) | 
                Q(manager__manager__rm_name=selected_manager) | 
                Q(manager__rm_manager_name=selected_manager),
                designation='MA'
            )
            .values_list('rm_name', flat=True)
            .distinct()
            .order_by('rm_name')
        )
    else:
        if user_role == 'L':
            all_mas = list(Employee.objects.filter(designation='MA').values_list('rm_name', flat=True).distinct().order_by('rm_name'))
        elif user_role == 'M':
            user_full_name = user.get_full_name() or user.username.replace('_', ' ').title()
            all_mas = list(
                Employee.objects.filter(
                    Q(manager__rm_name=user_full_name) |
                    Q(manager__manager__rm_name=user_full_name) | 
                    Q(manager__rm_manager_name=user_full_name),
                    designation='MA'
                )
                .values_list('rm_name', flat=True)
                .distinct()
                .order_by('rm_name')
            )
        elif user_role == 'R':
            user_full_name = user.get_full_name() or user.username.replace('_', ' ').title()
            all_mas = [user_full_name]

    # --- Data Filtering Logic (Dual-Table) ---
    filters = {
        'rm_name': selected_rm if selected_rm else None,
        'ma_name': selected_ma if selected_ma else None,
        'rm_manager_name': selected_manager if selected_manager else None,
        'period': selected_period if selected_period else None,
        'date_from': selected_date_from if selected_date_from else None,
        'date_to': selected_date_to if selected_date_to else None,
    }

    # Role-based default filtering
    if user_role == 'M' and not any([selected_rm, selected_ma, selected_manager]):
        user_full_name = user.get_full_name() or user.username.replace('_', ' ').title()
        filters['rm_manager_name'] = user_full_name
    elif user_role == 'R' and not any([selected_rm, selected_ma]):
        user_full_name = user.get_full_name() or user.username.replace('_', ' ').title()
        filters['rm_name'] = user_full_name

    # Apply filters using Analytics helper
    aaa_qs = BrokerageAnalytics._apply_filters(SalesRecordAAABrokerage.objects.all(), filters)
    mf_qs = BrokerageAnalytics._apply_filters(SalesRecordMF.objects.all(), filters, is_mf=True)

    # Aggregation
    aaa_totals = aaa_qs.aggregate(
        total_brokerage=Sum('total_brokerage'),
        total_equity_cash=Sum('total_equity_cash_turnover'),
        total_equity_fno=Sum('total_equity_fno_turnover'),
        total_turnover=Sum('total_turnover'),
    )
    mf_totals = mf_qs.aggregate(
        total_mf_brokerage=Sum('mf_brokerage'),
        total_mf_turnover=Sum('mf_turnover'),
    )

    totals = {
        'total_brokerage': aaa_totals.get('total_brokerage') or 0,
        'total_mf_brokerage': mf_totals.get('total_mf_brokerage') or 0,
        'total_equity_cash': aaa_totals.get('total_equity_cash') or 0,
        'total_equity_fno': aaa_totals.get('total_equity_fno') or 0,
        'total_turnover': (aaa_totals.get('total_turnover') or 0) + (mf_totals.get('total_mf_turnover') or 0),
        'combined_total_brokerage': BrokerageAnalytics.get_total_brokerage(filters)
    }

    # --- OPTIMIZED Aggregation for Charts (Database Level) ---
    chart_data = {
        'rms': all_rms,
        'mas': all_mas,
        'periods': BrokerageAnalytics.get_available_periods(),
        'selected_rm': selected_rm,
        'selected_ma': selected_ma,
        'selected_period': selected_period,
        'totals': totals,
        'rm_performance': {'labels': [], 'brokerage': [], 'mf_brokerage': [], 'combined': [], 'equity_cash': [], 'equity_fno': [], 'total_turnover': []},
        'ma_performance': {'labels': [], 'brokerage': [], 'mf_brokerage': [], 'combined': [], 'equity_cash': [], 'equity_fno': []},
        'top_clients': {'labels': [], 'brokerage': [], 'mf_brokerage': [], 'combined': [], 'rm': []},
        'segment_analysis': {'labels': [], 'cash': [], 'fno': []},
    }

    # 1. RM Performance (Optimized)
    aaa_rm = aaa_qs.values('rm_name').annotate(
        brk=Sum('total_brokerage'),
        cash=Sum('total_equity_cash_turnover'),
        fno=Sum('total_equity_fno_turnover'),
        trn=Sum('total_turnover')
    )
    mf_rm = mf_qs.values('rm_name').annotate(
        brk=Sum('mf_brokerage'),
        trn=Sum('mf_turnover')
    )
    
    rm_map = {}
    for r in aaa_rm:
        name = r['rm_name']
        rm_map[name] = {'brk': float(r['brk'] or 0), 'mf': 0.0, 'cash': float(r['cash'] or 0), 'fno': float(r['fno'] or 0), 'trn': float(r['trn'] or 0)}
    for r in mf_rm:
        name = r['rm_name']
        if name not in rm_map: rm_map[name] = {'brk': 0.0, 'mf': 0.0, 'cash': 0.0, 'fno': 0.0, 'trn': 0.0}
        rm_map[name]['mf'] += float(r['brk'] or 0)
        rm_map[name]['trn'] += float(r['trn'] or 0)
    
    sorted_rms = sorted(rm_map.items(), key=lambda x: x[1]['brk'] + x[1]['mf'], reverse=True)
    for name, vals in sorted_rms:
        chart_data['rm_performance']['labels'].append(name)
        chart_data['rm_performance']['brokerage'].append(vals['brk'])
        chart_data['rm_performance']['mf_brokerage'].append(vals['mf'])
        chart_data['rm_performance']['combined'].append(vals['brk'] + vals['mf'])
        chart_data['rm_performance']['equity_cash'].append(vals['cash'])
        chart_data['rm_performance']['equity_fno'].append(vals['fno'])
        chart_data['rm_performance']['total_turnover'].append(vals['trn'])

    # 2. MA Performance (Optimized)
    aaa_ma = aaa_qs.exclude(ma_name__isnull=True).exclude(ma_name="").values('ma_name').annotate(
        brk=Sum('total_brokerage'), cash=Sum('total_equity_cash_turnover'), fno=Sum('total_equity_fno_turnover')
    )
    # For MF, we join with client to get ma_name
    mf_ma = mf_qs.exclude(client__ma_name__isnull=True).exclude(client__ma_name="").values('client__ma_name').annotate(
        brk=Sum('mf_brokerage')
    )
    
    ma_map = {}
    for r in aaa_ma:
        name = r['ma_name']
        ma_map[name] = {'brk': float(r['brk'] or 0), 'mf': 0.0, 'cash': float(r['cash'] or 0), 'fno': float(r['fno'] or 0)}
    for r in mf_ma:
        name = r['client__ma_name']
        if name not in ma_map: ma_map[name] = {'brk': 0.0, 'mf': 0.0, 'cash': 0.0, 'fno': 0.0}
        ma_map[name]['mf'] += float(r['brk'] or 0)
        
    sorted_mas = sorted(ma_map.items(), key=lambda x: x[1]['brk'] + x[1]['mf'], reverse=True)[:15]
    for name, vals in sorted_mas:
        chart_data['ma_performance']['labels'].append(name)
        chart_data['ma_performance']['brokerage'].append(vals['brk'])
        chart_data['ma_performance']['mf_brokerage'].append(vals['mf'])
        chart_data['ma_performance']['combined'].append(vals['brk'] + vals['mf'])
        chart_data['ma_performance']['equity_cash'].append(vals['cash'])
        chart_data['ma_performance']['equity_fno'].append(vals['fno'])

    # 3. Top Clients (Optimized)
    aaa_cli = aaa_qs.values('client_name', 'rm_name').annotate(brk=Sum('total_brokerage'))
    mf_cli = mf_qs.values('client_name', 'rm_name').annotate(brk=Sum('mf_brokerage'))
    
    cli_map = {}
    for r in aaa_cli:
        key = (r['client_name'], r['rm_name'])
        cli_map[key] = {'brk': float(r['brk'] or 0), 'mf': 0.0}
    for r in mf_cli:
        key = (r['client_name'], r['rm_name'])
        if key not in cli_map: cli_map[key] = {'brk': 0.0, 'mf': 0.0}
        cli_map[key]['mf'] += float(r['brk'] or 0)
        
    sorted_cli = sorted(cli_map.items(), key=lambda x: x[1]['brk'] + x[1]['mf'], reverse=True)[:15]
    for (name, rm), vals in sorted_cli:
        chart_data['top_clients']['labels'].append(name)
        chart_data['top_clients']['brokerage'].append(vals['brk'])
        chart_data['top_clients']['mf_brokerage'].append(vals['mf'])
        chart_data['top_clients']['combined'].append(vals['brk'] + vals['mf'])
        chart_data['top_clients']['rm'].append(rm)

    # Combined records for table view
    combined_records = list(aaa_qs.order_by('-total_brokerage')[:50]) + list(mf_qs.order_by('-mf_brokerage')[:50])
    combined_records.sort(key=lambda x: (getattr(x, 'total_brokerage', 0) or getattr(x, 'mf_brokerage', 0)), reverse=True)

    # Combined records for table view
    combined_records = list(aaa_qs.order_by('-total_brokerage')[:50]) + list(mf_qs.order_by('-mf_brokerage')[:50])
    combined_records.sort(key=lambda x: (getattr(x, 'total_brokerage', 0) or getattr(x, 'mf_brokerage', 0)), reverse=True)

    context = {
        'user': user,
        'user_role': user_role,
        'title': 'Sales Dashboard',
        'records': combined_records[:100],
        'all_rms': all_rms,
        'all_mas': all_mas,
        'all_managers': all_managers,
        'available_periods': BrokerageAnalytics.get_available_periods(),
        'selected_rm': selected_rm,
        'selected_ma': selected_ma,
        'selected_manager': selected_manager,
        'selected_period': selected_period,
        'selected_date_from': selected_date_from,
        'selected_date_to': selected_date_to,
        'chart_data': sanitize_for_json(chart_data),
        'totals': sanitize_for_json(totals),
    }
    context['chart_data_json'] = json.dumps(context['chart_data'])
    context['totals_json'] = json.dumps(context['totals'])
    return context


# =====================================================================
# UPLOAD PORTAL VIEWS (Prerana-only access)
# =====================================================================

UPLOAD_PORTAL_USER = 'prerana'


def upload_portal_login_view(request):
    """Custom login page exclusively for the Data Upload Portal."""
    if request.user.is_authenticated and request.user.username == UPLOAD_PORTAL_USER:
        return redirect('upload_portal')

    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        user = authenticate(request, username=username, password=password)
        if user is not None and user.username == UPLOAD_PORTAL_USER:
            login(request, user)
            return redirect('upload_portal')
        else:
            error = 'Invalid credentials. Only authorized users can access this portal.'

    return render(request, 'upload_portal_login.html', {'error': error})


def upload_portal_view(request):
    """Data Upload Portal - accessible only to the prerana user."""
    if not request.user.is_authenticated or request.user.username != UPLOAD_PORTAL_USER:
        return redirect(f'/upload-portal/login/?next=/upload-portal/')

    base_dir = Path(settings.BASE_DIR).parent
    data_folders = {
        'brokerage': base_dir / 'data_files' / 'brokerage_fact',
        'mf': base_dir / 'data_files' / 'MF_fact',
        'client': base_dir / 'data_files' / 'Client_dim',
        'employee': base_dir / 'data_files' / 'Employee_dim',
    }

    folder_files = {}
    for dtype, folder_path in data_folders.items():
        if folder_path.exists():
            files = []
            for f in sorted(folder_path.iterdir()):
                if f.is_file() and f.suffix.lower() in ['.xlsx', '.xls', '.csv']:
                    files.append({
                        'name': f.name,
                        'size': round(f.stat().st_size / 1024, 1),  # KB
                        'data_type': dtype,
                    })
            folder_files[dtype] = files
        else:
            folder_files[dtype] = []

    context = {
        'folder_files': folder_files,
        'user': request.user,
    }
    return render(request, 'upload_portal.html', context)


@login_required
def delete_file_view(request):
    """Delete a data file from disk and remove its records from the database."""
    if request.user.username != UPLOAD_PORTAL_USER:
        return json_response({'error': 'Access denied.'}, status=403)

    if request.method != 'POST':
        return json_response({'error': 'Method not allowed'}, status=405)

    import os
    from pathlib import Path

    data_type = request.POST.get('data_type', '')
    file_name = request.POST.get('file_name', '').strip()

    data_type_map = {
        'brokerage': 'brokerage_fact',
        'client': 'Client_dim',
        'employee': 'Employee_dim',
        'mf': 'MF_fact',
    }

    if not data_type or data_type not in data_type_map or not file_name:
        return json_response({'error': 'Invalid request parameters.'}, status=400)

    if '/' in file_name or '\\' in file_name or '..' in file_name:
        return json_response({'error': 'Invalid file name.'}, status=400)

    base_dir = Path(settings.BASE_DIR).parent
    file_path = base_dir / 'data_files' / data_type_map[data_type] / file_name

    try:
        db_deleted = 0
        if data_type == 'brokerage':
            db_deleted, _ = SalesRecordAAABrokerage.objects.filter(file_name=file_name).delete()
        elif data_type == 'mf':
            db_deleted, _ = SalesRecordMF.objects.filter(file_name=file_name).delete()

        file_existed = file_path.exists()
        if file_existed:
            os.remove(str(file_path))

        return json_response({
            'success': True,
            'message': f'Deleted {file_name}. Removed {db_deleted} database records.',
            'db_records_deleted': db_deleted,
            'file_deleted': file_existed,
        })
    except Exception as e:
        return json_response({'error': f'Delete failed: {str(e)}'}, status=500)


@login_required
def data_upload_view(request):
    """Handle data file uploads to the data_files folder."""
    if request.method != 'POST':
        return json_response({'error': 'Method not allowed'}, status=405)
    
    import os
    from pathlib import Path
    
    try:
        data_type = request.POST.get('data_type', '')
        data_type_map = {
            'brokerage': 'brokerage_fact',
            'client': 'Client_dim',
            'employee': 'Employee_dim',
            'mf': 'MF_fact',
        }
        
        if not data_type or data_type not in data_type_map:
            return json_response({'error': 'Invalid data type.'}, status=400)
        
        folder_name = data_type_map[data_type]
        base_dir = Path(settings.BASE_DIR).parent
        data_folder_path = base_dir / 'data_files' / folder_name
        data_folder_path.mkdir(parents=True, exist_ok=True)
        
        uploaded_files = request.FILES.getlist('data_file')
        if not uploaded_files:
            return json_response({'error': 'No files provided.'}, status=400)
        
        saved_files = []
        allowed_extensions = {'.csv', '.xlsx', '.xls'}
        
        for uploaded_file in uploaded_files:
            if uploaded_file.size > 50 * 1024 * 1024:
                return json_response({'error': f'File {uploaded_file.name} too large'}, status=400)
            
            file_ext = os.path.splitext(uploaded_file.name)[1].lower()
            if file_ext not in allowed_extensions:
                continue
            
            file_path = data_folder_path / uploaded_file.name
            with open(file_path, 'wb') as f:
                for chunk in uploaded_file.chunks():
                    f.write(chunk)
            saved_files.append(uploaded_file.name)
        
        if not saved_files:
            return json_response({'error': 'No valid files found.'}, status=400)
        
        message = f'Successfully uploaded {len(saved_files)} files'
        try:
            from .data_pipeline import DataPipeline
            pipeline = DataPipeline()
            if data_type == 'brokerage':
                count = pipeline._load_aaa_brokerage_facts()
                message += f' - Total brokerage records: {count}'
            elif data_type == 'mf':
                count = pipeline._load_specialized_mf_facts()
                message += f' - Total MF records: {count}'
        except Exception as e:
            message += f' (Auto-load warning: {str(e)})'
        
        return json_response({'success': True, 'message': message})
    except Exception as e:
        return json_response({'error': f'Upload failed: {str(e)}'}, status=500)


def json_response(data, status=200):
    """Return JSON response with appropriate status code"""
    from django.http import JsonResponse
    return JsonResponse(data, status=status)
