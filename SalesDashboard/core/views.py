import pandas as pd
import json
from decimal import Decimal
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.models import User
from django.db.models import Sum, Q
from django.http import HttpResponseForbidden
from .models import SalesRecord, UserProfile, Employee
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


@login_required
def dashboard_view(request):
    """
    Dashboard supporting filtering by RM_Name and MA_Name with role-based data access.
    - RMs see only their own data
    - MAs see only their own data  
    - Managers see data for their RMs
    - Shows Total Brokerage combining Equity + MF data
    """
    user = request.user
    
    # Get user profile and determine role
    try:
        user_profile = UserProfile.objects.get(user=user)
        user_role = user_profile.role
    except UserProfile.DoesNotExist:
        user_profile = None
        user_role = 'R'  # Default to RM/MA role
    
    # Get filter parameters
    selected_rm = request.GET.get('rm', '').strip()
    selected_ma = request.GET.get('ma', '').strip()
    selected_manager = request.GET.get('manager', '').strip()
    selected_period = request.GET.get('period', '').strip()
    selected_date_from = request.GET.get('date_from', '').strip()
    selected_date_to = request.GET.get('date_to', '').strip()
    
    # Base QuerySet - filter by user role and identity
    records_queryset = SalesRecord.objects.all()
    
    # Role-based filtering
    if user_role == 'L':  # Leader - can see ALL data
        # Leaders have full access to all records
        pass
    elif user_role == 'M':  # Manager - can see data for all RMs
        # Managers can see data from their managed RMs
        # For now, show all data (you can add reporting_to logic later)
        pass
    else:  # RM/MA - can only see their own data
        # Convert username to proper name format (e.g., anil_gavali -> Anil Gavali)
        user_full_name = user.get_full_name() or user.username.replace('_', ' ').title()
        
        # Filter to show only this RM's or MA's data
        records_queryset = records_queryset.filter(
            Q(rm_name=user_full_name) | Q(ma_name=user_full_name)
        )
    
    # Apply additional filters if provided
    if selected_manager:
        # Get all RMs reporting to this manager
        try:
            manager_emp = Employee.objects.get(rm_name=selected_manager)
            subordinate_rms = [selected_manager]
            # Get all direct and indirect reports
            def get_team_rm_names(emp):
                names = [emp.rm_name] if emp.rm_name else []
                for subordinate in Employee.objects.filter(manager=emp):
                    names.extend(get_team_rm_names(subordinate))
                return names
            subordinate_rms = get_team_rm_names(manager_emp)
            records_queryset = records_queryset.filter(rm_name__in=subordinate_rms)
        except Employee.DoesNotExist:
            pass
    
    if selected_rm:
        records_queryset = records_queryset.filter(rm_name=selected_rm)
    
    if selected_ma:
        records_queryset = records_queryset.filter(ma_name=selected_ma)
        
    if selected_period:
        records_queryset = records_queryset.filter(period=selected_period)
    
    # Date range filtering
    if selected_date_from:
        try:
            from datetime import datetime
            date_from = datetime.strptime(selected_date_from, '%Y-%m-%d').date()
            records_queryset = records_queryset.filter(loaded_at__date__gte=date_from)
        except (ValueError, TypeError):
            pass
    
    if selected_date_to:
        try:
            from datetime import datetime
            date_to = datetime.strptime(selected_date_to, '%Y-%m-%d').date()
            records_queryset = records_queryset.filter(loaded_at__date__lte=date_to)
        except (ValueError, TypeError):
            pass
    
    # Get unique RM and MA names available to this user (HIERARCHY-BASED)
    all_managers = []
    all_rms = []
    
    if user_role == 'L':  # Leader - can see ALL RMs and ALL MAs
        all_rms = list(SalesRecord.objects.values_list('rm_name', flat=True).distinct().exclude(rm_name__isnull=True).exclude(rm_name__exact='').order_by('rm_name'))
        # Get all managers (leaders managing RMs)
        all_managers = list(Employee.objects.filter(
            rm_name__in=Employee.objects.filter(manager__isnull=False).values_list('manager__rm_name', flat=True).distinct()
        ).values_list('rm_name', flat=True).distinct().order_by('rm_name'))
        
    elif user_role == 'M':  # Manager - can see only RMs under them
        # Get manager's own name
        user_full_name = user.get_full_name() or user.username.replace('_', ' ').title()
        # Get all RMs reporting to this manager
        try:
            manager_emp = Employee.objects.get(rm_name=user_full_name)
            def get_subordinate_rms(emp):
                names = []
                for subordinate in Employee.objects.filter(manager=emp):
                    names.append(subordinate.rm_name)
                    names.extend(get_subordinate_rms(subordinate))
                return names
            subordinate_rms = get_subordinate_rms(manager_emp)
            all_rms = list(SalesRecord.objects.filter(rm_name__in=subordinate_rms).values_list('rm_name', flat=True).distinct().order_by('rm_name'))
        except Employee.DoesNotExist:
            all_rms = []
        
    else:  # RM/MA only sees their own
        user_full_name = user.get_full_name() or user.username.replace('_', ' ').title()
        all_rms_temp = list(SalesRecord.objects.filter(
            Q(rm_name=user_full_name) | Q(ma_name=user_full_name)
        ).values_list('rm_name', flat=True).distinct().exclude(rm_name__isnull=True).exclude(rm_name__exact='').order_by('rm_name'))
        all_rms = all_rms_temp if all_rms_temp else [user_full_name]
    
    # Filter MAs based on selected RM (SHOW MAs ONLY IF THEY EXIST FOR THAT RM)
    if selected_rm:
        all_mas = list(SalesRecord.objects.filter(
            rm_name=selected_rm
        ).exclude(ma_name__isnull=True).exclude(ma_name__exact='').values_list('ma_name', flat=True).distinct().order_by('ma_name'))
    else:
        # No RM selected - show MAs only from available RMs
        if all_rms:
            all_mas = list(SalesRecord.objects.filter(
                rm_name__in=all_rms
            ).exclude(ma_name__isnull=True).exclude(ma_name__exact='').values_list('ma_name', flat=True).distinct().order_by('ma_name'))
        else:
            all_mas = []
    
    # Get available periods
    available_periods = BrokerageAnalytics.get_available_periods()
    
    # Calculate totals using analytics engine (includes both Equity + MF)
    filters = {
        'rm_name': selected_rm if selected_rm else None,
        'ma_name': selected_ma if selected_ma else None,
        'period': selected_period if selected_period else None,
    }
    
    total_brokerage = BrokerageAnalytics.get_total_brokerage(filters)
    
    # Legacy totals for compatibility (equity only for now)
    totals = records_queryset.aggregate(
        total_brokerage=Sum('total_brokerage'),
        total_mf_brokerage=Sum('mf_brokerage'),
        total_equity_cash=Sum('total_equity_cash_turnover'),
        total_equity_fno=Sum('total_equity_fno_turnover'),
        total_turnover=Sum('total_turnover'),
    )
    
    # Handle None values and add combined total
    totals = {k: (v or 0) for k, v in totals.items()}
    totals['combined_total_brokerage'] = total_brokerage
    
    # Convert to DataFrame for charting
    records_data = list(records_queryset.values())
    
    chart_data = {
        'rms': all_rms,
        'mas': all_mas,
        'periods': available_periods,
        'selected_rm': selected_rm,
        'selected_ma': selected_ma,
        'selected_period': selected_period,
        'totals': totals,
        'rm_performance': {'labels': [], 'brokerage': [], 'mf_brokerage': [], 'combined': [], 'equity_cash': [], 'equity_fno': [], 'total_turnover': []},
        'ma_performance': {'labels': [], 'brokerage': [], 'mf_brokerage': [], 'combined': [], 'equity_cash': [], 'equity_fno': []},
        'top_clients': {'labels': [], 'brokerage': [], 'mf_brokerage': [], 'combined': [], 'rm': []},
        'segment_analysis': {'labels': [], 'cash': [], 'fno': []},
    }
    
    # Build performance metrics
    if records_data:
        df = pd.DataFrame(records_data)
        
        # Convert numeric columns to float
        numeric_cols = ['total_brokerage', 'mf_brokerage', 'cash_delivery', 'equity_cash_delivery_turnover', 
                       'equity_futures_turnover', 'equity_options_turnover', 'total_equity_cash_turnover',
                       'total_equity_fno_turnover', 'total_equity_turnover', 'total_turnover']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # RM performance (top business drivers)
        rm_perf = df.groupby('rm_name').agg({
            'total_brokerage': 'sum',
            'mf_brokerage': 'sum',
            'total_equity_cash_turnover': 'sum',
            'total_equity_fno_turnover': 'sum',
            'total_turnover': 'sum',
        }).reset_index()
        rm_perf['combined_brokerage'] = rm_perf['total_brokerage'] + rm_perf['mf_brokerage']
        rm_perf = rm_perf.sort_values('combined_brokerage', ascending=False)
        
        chart_data['rm_performance'] = {
            'labels': rm_perf['rm_name'].tolist(),
            'brokerage': [float(x) for x in rm_perf['total_brokerage'].tolist()],
            'mf_brokerage': [float(x) for x in rm_perf['mf_brokerage'].tolist()],
            'combined': [float(x) for x in rm_perf['combined_brokerage'].tolist()],
            'equity_cash': [float(x) for x in rm_perf['total_equity_cash_turnover'].tolist()],
            'equity_fno': [float(x) for x in rm_perf['total_equity_fno_turnover'].tolist()],
            'total_turnover': [float(x) for x in rm_perf['total_turnover'].tolist()],
        }
        
        # MA performance (if filtered by RM or show all MAs)
        if 'ma_name' in df.columns:
            if selected_rm:
                ma_data = df[df['rm_name'] == selected_rm]
            else:
                ma_data = df
                
            if not ma_data.empty:
                # Filter out empty ma_name values
                ma_data = ma_data[ma_data['ma_name'].notna() & (ma_data['ma_name'] != '')]
                
                if not ma_data.empty:
                    ma_perf = ma_data.groupby('ma_name').agg({
                        'total_brokerage': 'sum',
                        'mf_brokerage': 'sum',
                        'total_equity_cash_turnover': 'sum',
                        'total_equity_fno_turnover': 'sum',
                    }).reset_index()
                    ma_perf['combined_brokerage'] = ma_perf['total_brokerage'] + ma_perf['mf_brokerage']
                    ma_perf = ma_perf.sort_values('combined_brokerage', ascending=False).head(10)
                    
                    chart_data['ma_performance'] = {
                        'labels': ma_perf['ma_name'].tolist(),
                        'brokerage': [float(x) for x in ma_perf['total_brokerage'].tolist()],
                        'mf_brokerage': [float(x) for x in ma_perf['mf_brokerage'].tolist()],
                        'combined': [float(x) for x in ma_perf['combined_brokerage'].tolist()],
                        'equity_cash': [float(x) for x in ma_perf['total_equity_cash_turnover'].tolist()],
                        'equity_fno': [float(x) for x in ma_perf['total_equity_fno_turnover'].tolist()],
                    }
        
        # Top clients by brokerage
        if 'client_name' in df.columns:
            df['combined_brokerage'] = df['total_brokerage'] + df['mf_brokerage']
            top_clients = df.nlargest(10, 'combined_brokerage')[['client_name', 'rm_name', 'total_brokerage', 'mf_brokerage', 'combined_brokerage', 'total_turnover']]
            
            chart_data['top_clients'] = {
                'labels': top_clients['client_name'].tolist(),
                'brokerage': [float(x) for x in top_clients['total_brokerage'].tolist()],
                'mf_brokerage': [float(x) for x in top_clients['mf_brokerage'].tolist()],
                'combined': [float(x) for x in top_clients['combined_brokerage'].tolist()],
                'rm': top_clients['rm_name'].tolist(),
            }
        
        # Trading segment analysis (if MA data available)
        if 'ma_name' in df.columns:
            segment_perf = df.groupby('ma_name').agg({
                'total_equity_cash_turnover': 'sum',
                'total_equity_fno_turnover': 'sum',
                'total_brokerage': 'sum',
            }).reset_index().sort_values('total_brokerage', ascending=False).head(10)
            
            chart_data['segment_analysis'] = {
                'labels': segment_perf['ma_name'].tolist(),
                'cash': [float(x) for x in segment_perf['total_equity_cash_turnover'].tolist()],
                'fno': [float(x) for x in segment_perf['total_equity_fno_turnover'].tolist()],
            }
    else:
        # No records found - charts will be empty (already initialized above)
        pass
    
    context = {
        'user': user,
        'user_role': user_role,
        'title': 'Sales Dashboard',
        'records': records_queryset.order_by('-total_brokerage')[:100],
        'all_rms': all_rms,
        'all_mas': all_mas,
        'all_managers': all_managers,
        'available_periods': available_periods,
        'selected_rm': selected_rm,
        'selected_ma': selected_ma,
        'selected_manager': selected_manager,
        'selected_period': selected_period,
        'selected_date_from': selected_date_from,
        'selected_date_to': selected_date_to,
        'chart_data': sanitize_for_json(chart_data),
        'totals': sanitize_for_json(totals),
    }
    
    # Add JSON string for template
    context['chart_data_json'] = json.dumps(context['chart_data'])
    context['totals_json'] = json.dumps(context['totals'])
    
    return render(request, 'dashboard.html', context)


# =====================================================================
# UPLOAD PORTAL VIEWS (Prerana-only access)
# =====================================================================

UPLOAD_PORTAL_USER = 'prerana'


def upload_portal_login_view(request):
    """Custom login page exclusively for the Data Upload Portal."""
    # If already authenticated as prerana, go to portal
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

    import os
    from django.conf import settings
    from pathlib import Path

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
    from django.conf import settings
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

    # Security: prevent path traversal
    if '/' in file_name or '\\' in file_name or '..' in file_name:
        return json_response({'error': 'Invalid file name.'}, status=400)

    base_dir = Path(settings.BASE_DIR).parent
    file_path = base_dir / 'data_files' / data_type_map[data_type] / file_name

    try:
        db_deleted = 0
        if data_type in ('brokerage', 'mf'):
            db_deleted, _ = SalesRecord.objects.filter(file_name=file_name).delete()

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
    """
    Handle data file uploads to the data_files folder.
    Supports uploading to different data folders based on data_type.
    Only authenticated users can upload data.
    """
    if request.method != 'POST':
        return json_response({'error': 'Method not allowed'}, status=405)
    
    import os
    from django.conf import settings
    from pathlib import Path
    
    try:
        # Get data type from form
        data_type = request.POST.get('data_type', '')
        
        # Map data types to folder paths
        data_type_map = {
            'brokerage': 'brokerage_fact',
            'client': 'Client_dim',
            'employee': 'Employee_dim',
            'mf': 'MF_fact',
        }
        
        if not data_type or data_type not in data_type_map:
            return json_response({'error': 'Invalid data type. Please select a valid data type.'}, status=400)
        
        folder_name = data_type_map[data_type]
        
        # Construct the path to data_files folder
        base_dir = Path(settings.BASE_DIR).parent
        data_folder_path = base_dir / 'data_files' / folder_name
        
        # Create folder if it doesn't exist
        data_folder_path.mkdir(parents=True, exist_ok=True)
        
        # Get uploaded files
        uploaded_files = request.FILES.getlist('data_file')
        
        if not uploaded_files:
            return json_response({'error': 'No files provided. Please select at least one file.'}, status=400)
        
        saved_files = []
        allowed_extensions = {'.csv', '.xlsx', '.xls'}
        
        for uploaded_file in uploaded_files:
            # Validate file size (max 50MB)
            if uploaded_file.size > 50 * 1024 * 1024:
                return json_response({'error': f'File {uploaded_file.name} exceeds 50MB limit'}, status=400)
            
            # Validate file extension
            file_ext = os.path.splitext(uploaded_file.name)[1].lower()
            if file_ext not in allowed_extensions:
                continue  # Skip invalid files in folder upload
            
            # Save the file
            file_path = data_folder_path / uploaded_file.name
            with open(file_path, 'wb') as f:
                for chunk in uploaded_file.chunks():
                    f.write(chunk)
            saved_files.append(uploaded_file.name)
        
        if not saved_files:
            return json_response({'error': 'No valid data files (.csv, .xlsx, .xls) found in the upload.'}, status=400)
        
        # Load data into database if applicable
        message = f'Successfully uploaded {len(saved_files)} files'
        try:
            from .data_pipeline import DataPipeline
            pipeline = DataPipeline()
            
            if data_type == 'brokerage':
                count = pipeline._load_brokerage_facts()
                message += f' - Total brokerage records: {count}'
            elif data_type == 'mf':
                count = pipeline._load_mf_facts()
                message += f' - Total MF records: {count}'
            elif data_type == 'employee':
                message += ' - Employee data updated. Command line sync recommended for hierarchy.'
            elif data_type == 'client':
                message += ' - Client data updated.'
        except Exception as e:
            message += f' (Note: Auto-load warning: {str(e)})'
        
        return json_response({
            'success': True,
            'message': message,
            'files': saved_files,
            'data_type': data_type,
            'folder': str(data_folder_path)
        })
    
    except Exception as e:
        return json_response({'error': f'Upload failed: {str(e)}'}, status=500)


def json_response(data, status=200):
    """Return JSON response with appropriate status code"""
    from django.http import JsonResponse
    return JsonResponse(data, status=status)
