from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce
from decimal import Decimal
from datetime import datetime, timedelta

from .analytics import BrokerageAnalytics
from .models import SalesRecordAAABrokerage, SalesRecordMF, UserProfile, Employee, Client
from .views import sanitize_for_json, build_dashboard_context


class DashboardSummaryView(APIView):
    """
    Returns aggregated dashboard metrics and chart data similar to `dashboard_view`,
    but as JSON for the React frontend.
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        user = request.user
        try:
            user_profile = UserProfile.objects.get(user=user)
            user_role = user_profile.role
        except UserProfile.DoesNotExist:
            user_profile = None
            user_role = "R"

        selected_rm = request.query_params.get("rm", "").strip()
        selected_ma = request.query_params.get("ma", "").strip()
        selected_manager = request.query_params.get("manager", "").strip()
        selected_period = request.query_params.get("period", "").strip()

        # Build filters for analytics engine
        filters = {
            "rm_name": selected_rm or None,
            "ma_name": selected_ma or None,
            "rm_manager_name": selected_manager or None,
            "period": selected_period or None,
        }

        # Handle role-based restrictions if not leader
        if user_role != "L":
            user_full_name = user.get_full_name() or user.username.replace("_", " ").title()
            if user_role == "M":
                # Manager sees their own team
                filters["rm_manager_name"] = user_full_name
            else:
                # RM/MA sees only their own
                filters["rm_name"] = user_full_name

        # Aggregate using refined Analytics engine
        total_brokerage = BrokerageAnalytics.get_total_brokerage(filters)
        
        # Manually aggregate other totals from specialized tables
        aaa_qs = BrokerageAnalytics._apply_filters(SalesRecordAAABrokerage.objects.all(), filters)
        mf_qs = BrokerageAnalytics._apply_filters(SalesRecordMF.objects.all(), filters, is_mf=True)
        
        aaa_totals = aaa_qs.aggregate(
            total_brokerage=Sum("total_brokerage"),
            total_equity_cash=Sum("total_equity_cash_turnover"),
            total_equity_fno=Sum("total_equity_fno_turnover"),
            total_turnover=Sum("total_turnover"),
        )
        
        mf_totals = mf_qs.aggregate(
            total_mf_brokerage=Sum("mf_brokerage"),
            total_mf_turnover=Sum("mf_turnover")
        )
        
        totals = {
            "total_brokerage": aaa_totals.get("total_brokerage") or 0,
            "total_mf_brokerage": mf_totals.get("total_mf_brokerage") or 0,
            "total_equity_cash": aaa_totals.get("total_equity_cash") or 0,
            "total_equity_fno": aaa_totals.get("total_equity_fno") or 0,
            "total_turnover": (aaa_totals.get("total_turnover") or 0) + (mf_totals.get("total_mf_turnover") or 0),
            "combined_total_brokerage": total_brokerage
        }

        return Response(
            {
                "user_role": user_role,
                "filters": {
                    "rm": selected_rm,
                    "ma": selected_ma,
                    "manager": selected_manager,
                    "period": selected_period,
                },
                "totals": sanitize_for_json(totals),
            }
        )


class DashboardFullView(APIView):
    """
    Returns the full data used by `core/templates/dashboard.html` so the React SPA
    can replicate the dashboard exactly (filters, totals, chart series, records).
    """

    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        ctx = build_dashboard_context(user=request.user, params=request.GET)

        # Build normalized records list for frontend display
        records = []
        for r in ctx.get("records", []):
            # Check which model instance this is to handle field names
            is_mf = hasattr(r, 'mf_brokerage')
            
            records.append(
                {
                    "client_name": r.client_name,
                    "rm_name": r.rm_name,
                    "ma_name": getattr(r, 'ma_name', None),
                    "total_brokerage": float((r.mf_brokerage if is_mf else r.total_brokerage) or 0),
                    "total_equity_cash_turnover": float(getattr(r, 'total_equity_cash_turnover', 0)),
                    "total_equity_fno_turnover": float(getattr(r, 'total_equity_fno_turnover', 0)),
                    "total_turnover": float((r.mf_turnover if is_mf else r.total_turnover) or 0),
                    "type": "MF" if is_mf else "AAA",
                    "client_city": getattr(r, 'client_city', 'NO CITY')
                }
            )

        return Response(
            {
                "title": ctx.get("title", "Sales Dashboard"),
                "user": {
                    "username": request.user.username,
                    "full_name": request.user.get_full_name() or "User",
                },
                "filters": {
                    "selected_rm": ctx.get("selected_rm", ""),
                    "selected_ma": ctx.get("selected_ma", ""),
                    "selected_manager": ctx.get("selected_manager", ""),
                    "selected_date_from": ctx.get("selected_date_from", ""),
                    "selected_date_to": ctx.get("selected_date_to", ""),
                },
                "options": {
                    "all_rms": ctx.get("all_rms", []),
                    "all_mas": ctx.get("all_mas", []),
                    "all_managers": ctx.get("all_managers", []),
                },
                "totals": ctx.get("totals", {}),
                "chart_data": ctx.get("chart_data", {}),
                "records": records,
            }
        )


class BrokerageDetailsView(APIView):
    """
    API for BrokerageDetailsPage.
    Provides totals and client-wise brokerage list with support for Equity/MF toggle and City filtering.
    """
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        user = request.user
        # Use existing context builder to get hierarchy options and chart data logic
        # We'll adapt it to respect our specific BrokerageDetailsPage needs
        ctx = build_dashboard_context(user=user, params=request.GET)
        
        try:
            profile = UserProfile.objects.get(user=user)
            user_role = profile.role
            user_employee = profile.employee
            user_full_name = user_employee.rm_name if user_employee else (user.get_full_name() or user.username)
        except UserProfile.DoesNotExist:
            user_role = "R"
            user_employee = None
            user_full_name = user.get_full_name() or user.username

        # Parameters
        view_mode = request.query_params.get("mode", "team")
        active_card = request.query_params.get("card", "equity")
        search_query = request.query_params.get("q", "").strip()
        search_by = request.query_params.get("search_by", "code")
        city_filter = request.query_params.get("city", "").strip()
        date_from = request.query_params.get("date_from", "")
        date_to = request.query_params.get("date_to", "")
        
        # Additional Filters from DashboardPage
        selected_manager = request.query_params.get("manager", "").strip()
        selected_rm = request.query_params.get("rm", "").strip()
        selected_ma = request.query_params.get("ma", "").strip()

        # Prepare filters for unified analytics engine
        filters = {
            'ma_name': selected_ma or None,
            'rm_name': selected_rm or None,
            'rm_manager_name': selected_manager or None,
            'date_from': date_from or None,
            'date_to': date_to or None,
        }

        # Handle Detail Page specific Mode/Hierarchy
        if view_mode == "self":
            filters['rm_name'] = user_full_name
            filters['rm_manager_name'] = None # Override manager filter in self mode
            filters['ma_name'] = None
        else:
            # TEAM Mode - Role based restrictions if not leader
            if user_role != "L":
                if not any([selected_ma, selected_rm, selected_manager]):
                    if user_role == "M":
                        filters['rm_manager_name'] = user_full_name
                    else:
                        filters['rm_name'] = user_full_name

        # Apply unified filters using BrokerageAnalytics engine
        aaa_qs = BrokerageAnalytics._apply_filters(SalesRecordAAABrokerage.objects.all(), filters)
        mf_qs = BrokerageAnalytics._apply_filters(SalesRecordMF.objects.all(), filters, is_mf=True)

        # Apply City Filter (Local to Detail Page)
        if city_filter:
            aaa_qs = aaa_qs.filter(client_city__iexact=city_filter)
            mf_qs = mf_qs.filter(client__city__iexact=city_filter)

        # Calculate Totals
        equity_total = aaa_qs.aggregate(total=Coalesce(Sum('total_brokerage'), Decimal('0')))['total']
        mf_total = mf_qs.aggregate(total=Coalesce(Sum('mf_brokerage'), Decimal('0')))['total']

        # Get cities available in current view
        aaa_cities = list(aaa_qs.exclude(client_city__isnull=True).exclude(client_city="").values_list('client_city', flat=True).distinct())
        mf_cities = list(mf_qs.exclude(client__city__isnull=True).exclude(client__city="").values_list('client__city', flat=True).distinct())
        cities = sorted(list(set(aaa_cities + mf_cities)))

        # Detailed Records based on active card
        records = []
        target_qs = aaa_qs if active_card == "equity" else mf_qs
        
        if active_card != "others":
            if search_query:
                if search_by == "code":
                    target_qs = target_qs.filter(client__client_code__icontains=search_query)
                elif search_by == "pan":
                    if active_card == "equity":
                        target_qs = target_qs.filter(client_pan__icontains=search_query)
                    else:
                        target_qs = target_qs.filter(client__client_pan__icontains=search_query)
                else:
                    target_qs = target_qs.filter(client_name__icontains=search_query)
            
            # Fields vary slightly between models
            if active_card == "equity":
                client_agg = target_qs.values('client__client_code', 'client_name', 'client_pan').annotate(
                    val=Sum('total_brokerage')
                ).order_by('-val')[:500]
            else:
                client_agg = target_qs.values('client__client_code', 'client_name', 'client__client_pan').annotate(
                    val=Sum('mf_brokerage')
                ).order_by('-val')[:500]
            
            for r in client_agg:
                records.append({
                    "id": r['client__client_code'] or "-",
                    "name": r['client_name'],
                    "pan": r.get('client_pan') or r.get('client__client_pan') or "-",
                    "val": float(r['val'] or 0)
                })

        return Response({
            "user": {
                "full_name": user_full_name,
                "role": user_role
            },
            "options": {
                "all_managers": ctx.get("all_managers", []),
                "all_rms": ctx.get("all_rms", []),
                "all_mas": ctx.get("all_mas", []),
            },
            "totals": {
                "equity": float(equity_total),
                "mf": float(mf_total),
                "others": 0
            },
            "chart_data": ctx.get("chart_data", {}),
            "cities": cities,
            "records": records,
            "last_updated": datetime.now().strftime("%-m/%-d/%Y %-I:%M:%S %p")
        })


class LandingPageSummaryView(APIView):
    """
    API for NewLandingPage.
    Provides high-level summary (AUM, Brokerage, Clients) with Team/Self toggle and activity logic.
    """
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        user = request.user
        try:
            profile = UserProfile.objects.get(user=user)
            user_role = profile.role
            user_employee = profile.employee
            user_full_name = user_employee.rm_name if user_employee else (user.get_full_name() or user.username)
            default_tab = profile.default_landing_tab or "Overall"
        except UserProfile.DoesNotExist:
            user_role = "R"
            user_employee = None
            user_full_name = user.get_full_name() or user.username
            default_tab = "Overall"

        # Parameters
        view_mode = request.query_params.get("mode", "team")
        date_from = request.query_params.get("date_from", "")
        date_to = request.query_params.get("date_to", "")

        # Current Year YTD
        current_year = datetime.now().year
        ytd_start = datetime(current_year, 1, 1).date()

        # Prepare filters
        filters = {}
        if view_mode == "self":
            filters['rm_name'] = user_full_name
        else:
            if user_role != "L":
                if user_role == "M":
                    filters['rm_manager_name'] = user_full_name
                else:
                    filters['rm_name'] = user_full_name

        # Base Querysets
        aaa_qs = BrokerageAnalytics._apply_filters(SalesRecordAAABrokerage.objects.all(), filters)
        mf_qs = BrokerageAnalytics._apply_filters(SalesRecordMF.objects.all(), filters, is_mf=True)
        client_qs = Client.objects.all()
        
        # FIX: Implement recursive hierarchy for client_qs to match fact table counts
        if view_mode == "self":
            client_qs = client_qs.filter(rm_name=user_full_name)
        elif user_role == "M" and view_mode == "team":
            if user_employee:
                subs = user_employee.get_subordinates(recursive=True)
                sub_names = [s.rm_name for s in subs]
                sub_pans = [s.pan_number for s in subs]
                client_qs = client_qs.filter(Q(rm_name=user_full_name) | Q(rm_name__in=sub_names) | Q(employee_id__in=sub_pans))
            else:
                client_qs = client_qs.filter(rm_manager_name=user_full_name)
        elif user_role == "R":
            client_qs = client_qs.filter(rm_name=user_full_name)
        # Leader (L) in TEAM mode sees all, no filter needed

        # 1. Card Metrics (respecting dates)
        aaa_filtered = aaa_qs
        mf_filtered = mf_qs
        if date_from:
            aaa_filtered = aaa_filtered.filter(transaction_date__gte=date_from)
            mf_filtered = mf_filtered.filter(transaction_date__gte=date_from)
        if date_to:
            aaa_filtered = aaa_filtered.filter(transaction_date__lte=date_to)
            mf_filtered = mf_filtered.filter(transaction_date__lte=date_to)

        equity_brk = aaa_filtered.aggregate(total=Coalesce(Sum('total_brokerage'), Decimal('0')))['total']
        mf_brk = mf_filtered.aggregate(total=Coalesce(Sum('mf_brokerage'), Decimal('0')))['total']
        
        # 2. Client Counts
        # Overall clients in view
        total_clients = client_qs.count()
        # Equity clients (with records)
        equity_clients_count = aaa_filtered.values('client_id').distinct().count()
        # MF clients (with records)
        mf_clients_count = mf_filtered.values('client_id').distinct().count()

        # 3. Bottom Cards (AUM = Turnover sum)
        # Equity AUM = Sum of total_turnover
        equity_aum_val = aaa_qs.aggregate(total=Coalesce(Sum('total_turnover'), Decimal('0')))['total']
        # MF AUM = Sum of mf_turnover
        mf_aum_val = mf_qs.aggregate(total=Coalesce(Sum('mf_turnover'), Decimal('0')))['total']

        # 4. Activity Logic
        # Active: Transacted in last 12 months
        twelve_months_ago = datetime.now() - timedelta(days=365)
        active_ids_aaa = set(aaa_qs.filter(transaction_date__gte=twelve_months_ago).values_list('client_id', flat=True))
        active_ids_mf = set(mf_qs.filter(transaction_date__gte=twelve_months_ago).values_list('client_id', flat=True))
        active_count = len(active_ids_aaa | active_ids_mf)

        # Dormant: No transaction in last 24 months
        twenty_four_months_ago = datetime.now() - timedelta(days=730)
        recent_ids_aaa = set(aaa_qs.filter(transaction_date__gte=twenty_four_months_ago).values_list('client_id', flat=True))
        recent_ids_mf = set(mf_qs.filter(transaction_date__gte=twenty_four_months_ago).values_list('client_id', flat=True))
        recent_ids = recent_ids_aaa | recent_ids_mf
        
        # Clients who exist in view but are NOT in the recent_ids set
        dormant_count = client_qs.exclude(client_code__in=recent_ids).count()

        totals = {
            "overall": {
                "aum": float(equity_aum_val + mf_aum_val),
                "brokerage": float(equity_brk + mf_brk),
                "clients": total_clients
            },
            "equity": {
                "aum": float(equity_aum_val),
                "brokerage": float(equity_brk),
                "clients": equity_clients_count
            },
            "mf": {
                "aum": float(mf_aum_val),
                "brokerage": float(mf_brk),
                "clients": mf_clients_count
            },
            "active_clients": active_count,
            "dormant_clients": dormant_count,
            "equity_aum_detail": float(equity_aum_val),
            "mf_aum_detail": float(mf_aum_val)
        }

        return Response({
            "user": {
                "full_name": user_full_name,
                "role": user_role,
                "default_tab": default_tab
            },
            "totals": totals,
            "last_updated": datetime.now().strftime("%-m/%-d/%Y %-I:%M:%S %p")
        })


class UserPreferenceView(APIView):
    """API to save user UI preferences like default tab."""
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        tab = request.data.get('default_landing_tab')
        if not tab:
            return Response({"error": "Tab name required"}, status=400)
        
        profile = request.user.profile
        profile.default_landing_tab = tab
        profile.save()
        return Response({"success": True, "tab": tab})


class ClientListView(APIView):
    """
    API for ClientsListPage.
    Provides filtered list of clients from Client dimension table.
    """
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        user = request.user
        try:
            profile = UserProfile.objects.get(user=user)
            user_role = profile.role
            user_employee = profile.employee
            # Use RM Name from Employee record if available, else fallback
            user_full_name = user_employee.rm_name if user_employee else (user.get_full_name() or user.username)
        except UserProfile.DoesNotExist:
            user_role = "R"
            user_employee = None
            user_full_name = user.get_full_name() or user.username

        # Parameters
        view_mode = request.query_params.get("mode", "team")
        search_query = request.query_params.get("q", "").strip()
        search_by = request.query_params.get("search_by", "code") 
        city_filter = request.query_params.get("city", "").strip()

        # Base Queryset
        qs = Client.objects.all()

        # Hierarchy/Mode Filtering
        if view_mode == "self":
            qs = qs.filter(rm_name=user_full_name)
        else:
            # TEAM Mode
            if user_role == "L":
                pass # Leader sees everything
            elif user_role == "M":
                if user_employee:
                    subs = user_employee.get_subordinates(recursive=True)
                    sub_names = [s.rm_name for s in subs]
                    sub_pans = [s.pan_number for s in subs]
                    qs = qs.filter(Q(rm_name=user_full_name) | Q(rm_name__in=sub_names) | Q(employee_id__in=sub_pans))
                else:
                    qs = qs.filter(Q(rm_name=user_full_name) | Q(rm_manager_name=user_full_name))
            else:
                # RM sees only self
                qs = qs.filter(rm_name=user_full_name)

        # City Options
        all_cities = qs.exclude(city__isnull=True).exclude(city="").values_list('city', flat=True).distinct().order_by('city')

        # City Filter
        if city_filter:
            qs = qs.filter(city__iexact=city_filter)

        # Search Filtering
        if search_query:
            if search_by == "code":
                qs = qs.filter(client_code__icontains=search_query)
            elif search_by == "pan":
                qs = qs.filter(client_pan__icontains=search_query)
            elif search_by == "name":
                qs = qs.filter(client_name__icontains=search_query)
            elif search_by == "group":
                qs = qs.filter(wire_code__icontains=search_query)

        total_count = qs.count()
        records = qs.values('client_code', 'client_pan', 'client_name', 'wire_code', 'aum', 'city').order_by('client_name')

        results = []
        for r in records[:500]: 
            results.append({
                "code": r['client_code'] or "-",
                "pan": r['client_pan'] or "-",
                "name": r['client_name'] or "-",
                "group": r['wire_code'] or "-",
                "aum": float(r['aum'] or 0),
                "city": r['city'] or "-"
            })

        return Response({
            "user": {
                "full_name": user_full_name,
                "role": user_role
            },
            "count": total_count,
            "cities": list(all_cities),
            "records": results,
            "last_updated": datetime.now().strftime("%-m/%-d/%Y %-I:%M:%S %p")
        })


class HierarchyListView(APIView):
    """
    API to fetch direct reporting Managers, RMs, and MAs based on Employee hierarchy.
    """
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        user = request.user
        try:
            profile = UserProfile.objects.get(user=user)
            user_employee = profile.employee
            user_role = profile.role
        except UserProfile.DoesNotExist:
            user_employee = None
            user_role = "R"

        # If user is a Leader but has no employee record (e.g. superuser)
        # We try to find the Leader record by name
        if not user_employee and user_role == "L":
            user_employee = Employee.objects.filter(designation="Leader").first()

        if not user_employee:
            return Response({"managers": [], "rms": [], "mas": []})

        # Get only DIRECT reports
        direct_reports = Employee.objects.filter(manager=user_employee)

        managers = []
        rms = []
        mas = []

        for emp in direct_reports:
            # L=Leader, M=Managers, L1=RMs, MA=Advisors
            desig = (emp.designation or "").upper()
            if desig == "M" or desig == "L":
                managers.append(emp.rm_name)
            elif desig == "L1":
                rms.append(emp.rm_name)
            elif desig == "MA":
                mas.append(emp.rm_name)
            else:
                # Fallback
                rms.append(emp.rm_name)

        return Response({
            "managers": sorted(managers),
            "rms": sorted(rms),
            "mas": sorted(mas)
        })


class AumDetailsView(APIView):
    """
    API for AumDetailsPage.
    Provides hierarchical AUM data (Equity from total_turnover, MF from mf_turnover).
    """
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        user = request.user
        try:
            profile = UserProfile.objects.get(user=user)
            user_role = profile.role
            user_employee = profile.employee
            # Use RM Name from Employee record if available, else fallback
            user_full_name = user_employee.rm_name if user_employee else (user.get_full_name() or user.username)
        except UserProfile.DoesNotExist:
            user_role = "R"
            user_employee = None
            user_full_name = user.get_full_name() or user.username

        # Parameters
        view_mode = request.query_params.get("mode", "team")
        active_card = request.query_params.get("card", "overall") # overall, equity, mf
        search_query = request.query_params.get("q", "").strip()
        search_by = request.query_params.get("search_by", "code") # code, pan, name, group

        # Prepare filters for unified analytics engine
        filters = {}
        if view_mode == "self":
            filters['rm_name'] = user_full_name
        else:
            if user_role != "L":
                if user_role == "M":
                    filters['rm_manager_name'] = user_full_name
                else:
                    filters['rm_name'] = user_full_name

        # Apply filters using unified engine
        aaa_qs = BrokerageAnalytics._apply_filters(SalesRecordAAABrokerage.objects.all(), filters)
        mf_qs = BrokerageAnalytics._apply_filters(SalesRecordMF.objects.all(), filters, is_mf=True)

        # Totals Aggregation
        equity_aum = aaa_qs.aggregate(total=Coalesce(Sum('total_turnover'), Decimal('0')))['total']
        mf_aum = mf_qs.aggregate(total=Coalesce(Sum('mf_turnover'), Decimal('0')))['total']
        overall_aum = equity_aum + mf_aum

        # Records logic
        records = []
        if active_card == "overall":
            # Group by client across both sources
            aaa_cli = aaa_qs.values('client__client_code', 'client_name', 'client_pan').annotate(equity=Sum('total_turnover'))
            mf_cli = mf_qs.values('client__client_code', 'client_name', 'client__client_pan').annotate(mf=Sum('mf_turnover'))
            
            cli_data = {}
            for r in aaa_cli:
                code = r['client__client_code'] or "-"
                cli_data[code] = {
                    "code": code,
                    "name": r['client_name'] or "-",
                    "pan": r['client_pan'] or "-",
                    "equity": float(r['equity'] or 0),
                    "mf": 0.0
                }
            for r in mf_cli:
                code = r['client__client_code'] or "-"
                if code not in cli_data:
                    cli_data[code] = {"code": code, "name": r['client_name'] or "-", "pan": r['client__client_pan'] or "-", "equity": 0.0, "mf": 0.0}
                cli_data[code]['mf'] += float(r['mf'] or 0)
            
            # Apply search filter manually on combined results if query exists
            for code, data in cli_data.items():
                if search_query:
                    match = False
                    q = search_query.lower()
                    if search_by == "code" and q in data['code'].lower(): match = True
                    elif search_by == "pan" and q in data['pan'].lower(): match = True
                    elif search_by == "name" and q in data['name'].lower(): match = True
                    if not match: continue
                
                records.append({
                    "code": data['code'],
                    "name": data['name'],
                    "pan": data['pan'],
                    "equity": data['equity'],
                    "mf": data['mf'],
                    "total": data['equity'] + data['mf']
                })
            records.sort(key=lambda x: x['total'], reverse=True)

        elif active_card == "equity":
            target_qs = aaa_qs
            if search_query:
                if search_by == "code": target_qs = target_qs.filter(client__client_code__icontains=search_query)
                elif search_by == "pan": target_qs = target_qs.filter(client_pan__icontains=search_query)
                elif search_by == "name": target_qs = target_qs.filter(client_name__icontains=search_query)
                elif search_by == "group": target_qs = target_qs.filter(wire_code__icontains=search_query)
            
            items = target_qs.values('client__client_code', 'client_name', 'client_pan').annotate(val=Sum('total_turnover')).order_by('-val')
            for r in items[:500]:
                records.append({
                    "code": r['client__client_code'] or "-",
                    "name": r['client_name'] or "-",
                    "pan": r['client_pan'] or "-",
                    "total": float(r['val'] or 0)
                })

        elif active_card == "mf":
            target_qs = mf_qs
            if search_query:
                if search_by == "code": target_qs = target_qs.filter(client__client_code__icontains=search_query)
                elif search_by == "pan": target_qs = target_qs.filter(client__client_pan__icontains=search_query)
                elif search_by == "name": target_qs = target_qs.filter(client_name__icontains=search_query)
                elif search_by == "group": target_qs = target_qs.filter(wire_code__icontains=search_query)
            
            items = target_qs.values('client__client_code', 'client_name', 'client__client_pan').annotate(val=Sum('mf_turnover')).order_by('-val')
            for r in items[:500]:
                records.append({
                    "code": r['client__client_code'] or "-",
                    "name": r['client_name'] or "-",
                    "pan": r['client__client_pan'] or "-",
                    "total": float(r['val'] or 0)
                })

        return Response({
            "user": {"full_name": user_full_name, "role": user_role},
            "totals": {
                "overall": float(overall_aum),
                "equity": float(equity_aum),
                "mf": float(mf_aum)
            },
            "records": records[:500],
            "last_updated": datetime.now().strftime("%-m/%-d/%Y %-I:%M:%S %p")
        })
