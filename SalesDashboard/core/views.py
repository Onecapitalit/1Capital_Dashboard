import pandas as pd
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.models import User
from django.db.models import Sum
from .models import SalesRecord, UserProfile
from django.contrib.auth import views as auth_views 
# Placeholder functions needed for urls.py to import successfully
user_login = auth_views.LoginView.as_view(template_name='registration/login.html')
user_logout = auth_views.LogoutView.as_view(next_page='/')

# --- Helper Functions (From models.py, used for hierarchy traversal) ---

def get_direct_reports_users(user_profile):
    """Returns a queryset of User objects who report directly to the given profile."""
    # Find all UserProfiles that report to the given profile, then get their associated User objects
    return User.objects.filter(userprofile__reporting_to=user_profile)

def get_all_downline_users(user_profile):
    """Recursively collects all user objects in the downline of a given profile."""
    all_users = set()
    direct_reports = get_direct_reports_users(user_profile)
    
    for user in direct_reports:
        all_users.add(user)
        try:
            # Recursively call for the direct report's profile
            report_profile = UserProfile.objects.get(user=user)
            all_users.update(get_all_downline_users(report_profile))
        except UserProfile.DoesNotExist:
            # Should not happen if data is clean, but handles edge cases
            pass
            
    return all_users

# --- View Function ---

@login_required
def dashboard_view(request):
    user = request.user
    
    try:
        profile = user.userprofile
        user_role = profile.role
    except UserProfile.DoesNotExist:
        user_role = 'R'  # Default to RM if profile is missing
    
    # Handle date filtering (raw strings from GET)
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    # Manager and RM slicers (optional)
    selected_manager = request.GET.get('manager')
    selected_rm = request.GET.get('rm')
    
    # Base QuerySet starts with all records
    records_queryset = SalesRecord.objects.all()
    
    # We'll build lists for the template below (managers and rms)
    # Defensive defaults to avoid UnboundLocalError in later branches
    selected_manager_name = None
    rms_filtered = User.objects.filter(userprofile__role='R')

    # Determine which records the user can see based on role
    if user_role == 'R':
        # Role R (RM): Only sees their own records
        # Ensure UI shows RM as preselected
        if not selected_rm:
            selected_rm = str(user.id)
        viewable_records = records_queryset.filter(relationship_manager=user)
        title = f"RM Dashboard: {user.username}"
        reports_summary = None

    elif user_role == 'M':
        # Role M (Manager): Sees their own RMs' (downline) records
        downline_users = get_all_downline_users(profile)
        # Filter for sales records linked to any user in their downline
        viewable_records = records_queryset.filter(relationship_manager__in=list(downline_users))
        title = f"Manager Dashboard: {user.username}"
        
        # Calculate summary for direct reports
        reports = get_direct_reports_users(profile)
        reports_summary = []
        for report in reports:
            report_records = records_queryset.filter(relationship_manager=report)
            report_sales = report_records.aggregate(
                total_equity=Sum('brokerage_equity'),
                total_mf=Sum('brokerage_mf')
            )
            equity = report_sales['total_equity'] or 0
            mf = report_sales['total_mf'] or 0
            total = equity + mf
            reports_summary.append({
                'username': report.username,
                'role': 'RM',
                'equity': equity,
                'mf': mf,
                'total': total
            })
        reports_summary.sort(key=lambda x: x['total'], reverse=True)
            
    elif user_role == 'L':
        # Role L (Leader): Sees all records
        viewable_records = records_queryset
        title = "Leader Dashboard (All Data)"
        
        # Calculate summary for direct reports (Managers)
        reports = get_direct_reports_users(profile)
        reports_summary = []
        for report in reports:
            # For a Leader's direct report (Manager), aggregate all sales under that Manager's downline
            manager_records = records_queryset.filter(
                relationship_manager__in=list(get_all_downline_users(report.userprofile))
            )
            downline_sales = manager_records.aggregate(
                total_equity=Sum('brokerage_equity'),
                total_mf=Sum('brokerage_mf')
            )
            equity = downline_sales['total_equity'] or 0
            mf = downline_sales['total_mf'] or 0
            total = equity + mf
            reports_summary.append({
                'username': report.username,
                'role': 'Manager',
                'equity': equity,
                'mf': mf,
                'total': total
            })
        reports_summary.sort(key=lambda x: x['total'], reverse=True)
    
    else:
        # Fallback for unassigned role
        viewable_records = SalesRecord.objects.none()
        title = "Access Denied"
        reports_summary = None
    
    # Calculate Grand Total for the viewable data
    # Before aggregating grand totals, apply any manager/rm slicer
    # If selected_manager provided, filter by manager's user id
    if selected_manager:
        try:
            mgr_user = User.objects.get(id=int(selected_manager))
            try:
                mgr_profile = mgr_user.userprofile
                downline_users_for_mgr = list(get_all_downline_users(mgr_profile))
                # include the manager themselves
                downline_users_for_mgr.append(mgr_user)
                viewable_records = viewable_records.filter(relationship_manager__in=downline_users_for_mgr)
            except UserProfile.DoesNotExist:
                # if no profile, at least filter by manager user
                viewable_records = viewable_records.filter(relationship_manager=mgr_user)
        except Exception:
            # ignore invalid manager id
            pass

    if selected_rm:
        try:
            rm_user = User.objects.get(id=int(selected_rm))
            viewable_records = viewable_records.filter(relationship_manager=rm_user)
        except Exception:
            pass

    # ------------------
    # Robust date handling
    # ------------------
    # Parse provided date strings (ISO yyyy-mm-dd). Use dynamic defaults if one side missing.
    from datetime import date
    parsed_start = None
    parsed_end = None
    try:
        if start_date:
            parsed_start = date.fromisoformat(start_date)
        if end_date:
            parsed_end = date.fromisoformat(end_date)
    except Exception:
        # invalid date format -> ignore
        parsed_start = None
        parsed_end = None


    # Always determine min/max date in the current viewable_records for filter UI
    dates_qs = viewable_records.values_list('created_at', flat=True)
    try:
        dates_list = list(dates_qs)
    except Exception:
        dates_list = []

    if dates_list:
        min_date = min(dt.date() for dt in dates_list)
        max_date = max(dt.date() for dt in dates_list)
    else:
        min_date = None
        max_date = None

    # If we have no parsed dates, we can keep the full range. If only one side provided, compute the other from data.
    if parsed_start or parsed_end:
        if parsed_start is None and parsed_end is not None:
            # user supplied only end -> set start to earliest available or same day
            parsed_start = min_date or parsed_end
        if parsed_end is None and parsed_start is not None:
            # user supplied only start -> set end to latest available or same day
            parsed_end = max_date or parsed_start

        # Only apply filter if parsed_start and parsed_end are valid
        if parsed_start and parsed_end:
            # filter by date portion to avoid time-of-day exclusion
            viewable_records = viewable_records.filter(created_at__date__gte=parsed_start, created_at__date__lte=parsed_end)

    grand_totals = viewable_records.aggregate(
        total_equity=Sum('brokerage_equity'),
        total_mf=Sum('brokerage_mf')
    )
    
    equity_total = grand_totals['total_equity'] or 0
    mf_total = grand_totals['total_mf'] or 0
    total = equity_total + mf_total

    # Convert QuerySet to DataFrame for analysis
    records_df = pd.DataFrame(list(viewable_records.values(
        'created_at', 'brokerage_equity', 'brokerage_mf', 
        'relationship_manager', 'relationship_manager__username',
        'client_name', 'client_id'
    )))
    
    if not records_df.empty:
        # Daily totals and growth trend
        records_df['date'] = pd.to_datetime(records_df['created_at']).dt.date
        records_df['total'] = records_df['brokerage_equity'] + records_df['brokerage_mf']

        # Debug: print unique dates and row count
        import logging
        logger = logging.getLogger("dashboard_debug")
        unique_dates = records_df['date'].unique()
        logger.warning(f"Dashboard DataFrame: {len(records_df)} rows, {len(unique_dates)} unique dates: {unique_dates[:10]}")

        daily_totals = records_df.groupby('date').agg({
            'brokerage_equity': 'sum',
            'brokerage_mf': 'sum',
            'total': 'sum'
        }).reset_index()

        # Sort by date to ensure proper cumulative calculations
        daily_totals = daily_totals.sort_values('date')

        # Calculate cumulative totals
        daily_totals['cumulative_equity'] = daily_totals['brokerage_equity'].cumsum()
        daily_totals['cumulative_mf'] = daily_totals['brokerage_mf'].cumsum()
        daily_totals['cumulative_total'] = daily_totals['total'].cumsum()

        # RM-wise performance
        rm_performance = records_df.groupby('relationship_manager__username').agg({
            'brokerage_equity': 'sum',
            'brokerage_mf': 'sum',
            'total': 'sum'
        }).reset_index()
        rm_performance = rm_performance.sort_values('total', ascending=False)

        chart_data = {
            'dates': [d.isoformat() for d in daily_totals['date']],
            'daily': {
                'equity': daily_totals['brokerage_equity'].tolist(),
                'mf': daily_totals['brokerage_mf'].tolist(),
                'total': daily_totals['total'].tolist()
            },
            'cumulative': {
                'equity': daily_totals['cumulative_equity'].tolist(),
                'mf': daily_totals['cumulative_mf'].tolist(),
                'total': daily_totals['cumulative_total'].tolist()
            },
            'rm_performance': {
                'labels': rm_performance['relationship_manager__username'].tolist(),
                'equity': rm_performance['brokerage_equity'].tolist(),
                'mf': rm_performance['brokerage_mf'].tolist(),
                'total': rm_performance['total'].tolist()
            }
        }
    else:
        chart_data = {
            'dates': [],
            'daily': {'equity': [], 'mf': [], 'total': []},
            'cumulative': {'equity': [], 'mf': [], 'total': []},
            'rm_performance': {'labels': [], 'equity': [], 'mf': [], 'total': []}
        }

    # Helper to sanitize objects for JSON serialization (convert Decimal/numpy types)
    def _sanitize(obj):
        from decimal import Decimal
        try:
            import numpy as _np
        except Exception:
            _np = None

        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize(v) for v in obj]
        if isinstance(obj, tuple):
            return tuple(_sanitize(v) for v in obj)
        if obj is None:
            return obj
        # Decimals to float
        if isinstance(obj, Decimal):
            return float(obj)
        # numpy numeric types
        if _np is not None:
            if isinstance(obj, (_np.integer, _np.int64, _np.int32)):
                return int(obj)
            if isinstance(obj, (_np.floating, _np.float64, _np.float32)):
                return float(obj)
        return obj

    # Format data for template
    context = {
        'user': user,
        'user_role': user_role,
        'title': title,
        'viewable_records': viewable_records.order_by('-created_at')[:50],  # Limit to latest 50 records
        'grand_totals': {
            'equity': equity_total,
            'mf': mf_total,
            'total': total
        },
        'reports_summary': reports_summary,
        'chart_data': chart_data
    }

    # Build slicer lists for template (Managers and RMs)
    # Managers are users with role 'M'
    managers = User.objects.filter(userprofile__role='M')
    # If a manager is selected, restrict RM list to that manager's downline
    if selected_manager:
        try:
            sel_mgr = User.objects.get(id=int(selected_manager))
            selected_manager_name = sel_mgr.username
            try:
                sel_mgr_profile = sel_mgr.userprofile
                downline = list(get_all_downline_users(sel_mgr_profile))
                rms_filtered = User.objects.filter(id__in=[u.id for u in downline], userprofile__role='R')
            except UserProfile.DoesNotExist:
                rms_filtered = User.objects.filter(userprofile__role='R')
        except Exception:
            rms_filtered = User.objects.filter(userprofile__role='R')
    elif user_role == 'M':
        # Manager sees only their RMs
        try:
            mgr_downline = list(get_all_downline_users(profile))
            rms_filtered = User.objects.filter(id__in=[u.id for u in mgr_downline], userprofile__role='R')
        except Exception:
            rms_filtered = User.objects.filter(userprofile__role='R')
    else:
        rms_filtered = User.objects.filter(userprofile__role='R')
        selected_manager_name = None

    # selected RM name
    selected_rm_name = None
    if selected_rm:
        try:
            sel_rm = User.objects.get(id=int(selected_rm))
            selected_rm_name = sel_rm.username
        except Exception:
            selected_rm_name = None
    # Show parsed/defaulted dates in the template inputs so the filter UI is dynamic
    display_start = None
    display_end = None
    if 'parsed_start' in locals() and parsed_start:
        display_start = parsed_start.isoformat()
    else:
        display_start = start_date or ''

    if 'parsed_end' in locals() and parsed_end:
        display_end = parsed_end.isoformat()
    else:
        display_end = end_date or ''

    context.update({
        'start_date': display_start,
        'end_date': display_end,
        'selected_manager': selected_manager,
        'selected_rm': selected_rm,
        'selected_manager_name': selected_manager_name,
        'selected_rm_name': selected_rm_name,
        'managers': managers,
        'rms': rms_filtered,
        'min_date': min_date.isoformat() if min_date else '',
        'max_date': max_date.isoformat() if max_date else '',
    })

    # Add JSON-serialized chart data to avoid template/JS lint issues
    try:
        import json
        context['chart_data_json'] = json.dumps(_sanitize(chart_data))
    except Exception:
        context['chart_data_json'] = '{}'
    try:
        import json as _json
        context['grand_totals_json'] = _json.dumps(_sanitize(context['grand_totals']))
    except Exception:
        context['grand_totals_json'] = '{}'

    return render(request, 'dashboard.html', context)