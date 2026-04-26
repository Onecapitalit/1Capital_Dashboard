from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce
from decimal import Decimal
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

from .analytics import BrokerageAnalytics
from .models import SalesRecordAAABrokerage, SalesRecordMF, SalesRecordPMSAIF, UserProfile, Employee, Client, ClientWealthMagic, ClientPMSAIF
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
        selected_city = request.query_params.get("city", "").strip()

        # Build filters for analytics engine
        filters = {
            "rm_name": selected_rm or None,
            "ma_name": selected_ma or None,
            "rm_manager_name": selected_manager or None,
            "period": selected_period or None,
            "operational_city": selected_city or None,
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
        # Add city to params for context builder if needed
        # Actually build_dashboard_context uses request.GET
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

        # Get all available operational cities for filtering
        all_cities = list(Employee.objects.exclude(operational_city__isnull=True).exclude(operational_city="").values_list('operational_city', flat=True).distinct().order_by('operational_city'))

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
                    "selected_city": request.query_params.get("city", ""),
                    "selected_date_from": ctx.get("selected_date_from", ""),
                    "selected_date_to": ctx.get("selected_date_to", ""),
                },
                "options": {
                    "all_rms": ctx.get("all_rms", []),
                    "all_mas": ctx.get("all_mas", []),
                    "all_managers": ctx.get("all_managers", []),
                    "all_cities": all_cities,
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
        pms_aif_qs = BrokerageAnalytics._apply_filters(SalesRecordPMSAIF.objects.all(), filters)

        # Apply City Filter (Local to Detail Page)
        if city_filter:
            aaa_qs = aaa_qs.filter(client_city__iexact=city_filter)
            mf_qs = mf_qs.filter(client__city__iexact=city_filter)
            # For PMSAIF, we don't have client_city field in model, but we have rm_name link. 
            # Requirement didn't specify city filtering for PMSAIF, but let's keep consistency if possible.
            # Actually, ClientPMSAIF has ma_name but no city. Let's skip city filter for now for PMSAIF or log warning.

        # Calculate Totals
        equity_total = aaa_qs.aggregate(total=Coalesce(Sum('total_brokerage'), Decimal('0')))['total']
        mf_total = mf_qs.aggregate(total=Coalesce(Sum('mf_brokerage'), Decimal('0')))['total']
        others_total = pms_aif_qs.aggregate(total=Coalesce(Sum('total_amount'), Decimal('0')))['total']

        # Get cities available in current view
        aaa_cities = list(aaa_qs.exclude(client_city__isnull=True).exclude(client_city="").values_list('client_city', flat=True).distinct())
        mf_cities = list(mf_qs.exclude(client__city__isnull=True).exclude(client__city="").values_list('client__city', flat=True).distinct())
        cities = sorted(list(set(aaa_cities + mf_cities)))

        # Detailed Records based on active card
        records = []
        
        if active_card == "equity":
            target_qs = aaa_qs
            if search_query:
                if search_by == "code": target_qs = target_qs.filter(client__client_code__icontains=search_query)
                elif search_by == "pan": target_qs = target_qs.filter(client_pan__icontains=search_query)
                else: target_qs = target_qs.filter(client_name__icontains=search_query)
            
            client_agg = target_qs.values('client__client_code', 'client_name', 'client_pan').annotate(
                val=Sum('total_brokerage')
            ).order_by('-val')[:500]
            
            for r in client_agg:
                records.append({
                    "id": r['client__client_code'] or "-",
                    "name": r['client_name'],
                    "pan": r.get('client_pan') or "-",
                    "val": float(r['val'] or 0)
                })

        elif active_card == "mf":
            target_qs = mf_qs
            if search_query:
                if search_by == "code": target_qs = target_qs.filter(client__client_code__icontains=search_query)
                elif search_by == "pan": target_qs = target_qs.filter(client__client_pan__icontains=search_query)
                else: target_qs = target_qs.filter(client_name__icontains=search_query)
            
            client_agg = target_qs.values('client__client_code', 'client_name', 'client__client_pan').annotate(
                val=Sum('mf_brokerage')
            ).order_by('-val')[:500]
            
            for r in client_agg:
                records.append({
                    "id": r['client__client_code'] or "-",
                    "name": r['client_name'],
                    "pan": r.get('client__client_pan') or "-",
                    "val": float(r['val'] or 0)
                })

        elif active_card == "others":
            target_qs = pms_aif_qs
            if search_query:
                if search_by == "code": target_qs = target_qs.filter(client_code__icontains=search_query)
                elif search_by == "pan": target_qs = target_qs.filter(client_pan__icontains=search_query)
                else: target_qs = target_qs.filter(client_name__icontains=search_query)
            
            client_agg = target_qs.values('client_code', 'client_name', 'client_pan').annotate(
                val=Sum('total_amount')
            ).order_by('-val')[:500]
            
            for r in client_agg:
                records.append({
                    "id": r['client_code'] or "-",
                    "name": r['client_name'],
                    "pan": r['client_pan'] or "-",
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
                "others": float(others_total)
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
        pms_aif_qs = BrokerageAnalytics._apply_filters(SalesRecordPMSAIF.objects.all(), filters)
        
        client_qs = Client.objects.all()
        wm_client_qs = ClientWealthMagic.objects.all()
        pms_client_qs = ClientPMSAIF.objects.all()
        
        # Helper to apply hierarchy to client dimensions
        def apply_client_hierarchy(queryset):
            if view_mode == "self":
                return queryset.filter(rm_name=user_full_name)
            elif user_role == "M" and view_mode == "team":
                if user_employee:
                    subs = user_employee.get_subordinates(recursive=True)
                    sub_names = [s.rm_name for s in subs]
                    return queryset.filter(Q(rm_name=user_full_name) | Q(rm_name__in=sub_names))
                else:
                    return queryset.filter(rm_manager_name=user_full_name)
            elif user_role == "R":
                return queryset.filter(rm_name=user_full_name)
            return queryset

        client_qs = apply_client_hierarchy(client_qs)
        wm_client_qs = apply_client_hierarchy(wm_client_qs)
        pms_client_qs = apply_client_hierarchy(pms_client_qs)

        # 1. Card Metrics (respecting dates)
        aaa_filtered = aaa_qs
        mf_filtered = mf_qs
        pms_aif_filtered = pms_aif_qs
        
        if date_from:
            aaa_filtered = aaa_filtered.filter(transaction_date__gte=date_from)
            mf_filtered = mf_filtered.filter(transaction_date__gte=date_from)
            pms_aif_filtered = pms_aif_filtered.filter(transaction_date__gte=date_from)
        if date_to:
            aaa_filtered = aaa_filtered.filter(transaction_date__lte=date_to)
            mf_filtered = mf_filtered.filter(transaction_date__lte=date_to)
            pms_aif_filtered = pms_aif_filtered.filter(transaction_date__lte=date_to)

        equity_brk = aaa_filtered.aggregate(total=Coalesce(Sum('total_brokerage'), Decimal('0')))['total']
        mf_brk = mf_filtered.aggregate(total=Coalesce(Sum('mf_brokerage'), Decimal('0')))['total']
        pms_aif_brk = pms_aif_filtered.aggregate(total=Coalesce(Sum('total_amount'), Decimal('0')))['total']
        
        # 2. Client Counts
        # Overall clients in view
        total_clients = client_qs.count() + wm_client_qs.count() + pms_client_qs.count()
        # Equity clients (with records)
        equity_clients_count = aaa_filtered.values('client_id').distinct().count()
        # MF clients (with records)
        mf_clients_count = mf_filtered.values('client_id').distinct().count()
        # PMS/AIF clients (with records)
        pms_aif_clients_count = pms_aif_filtered.values('client_code').distinct().count()

        # 3. Bottom Cards (AUM = Turnover sum)
        equity_aum_val = aaa_qs.aggregate(total=Coalesce(Sum('total_turnover'), Decimal('0')))['total']
        mf_aum_val = mf_qs.aggregate(total=Coalesce(Sum('mf_turnover'), Decimal('0')))['total']
        pms_aum_val = pms_aif_qs.aggregate(total=Coalesce(Sum('pms_aum'), Decimal('0')))['total']
        aif_aum_val = pms_aif_qs.aggregate(total=Coalesce(Sum('aif_aum'), Decimal('0')))['total']
        pms_aif_combined_aum = pms_aum_val + aif_aum_val

        # 4. Activity Logic
        twelve_months_ago = datetime.now() - timedelta(days=365)
        active_ids_aaa = set(aaa_qs.filter(transaction_date__gte=twelve_months_ago).values_list('client_id', flat=True))
        active_ids_mf = set(mf_qs.filter(transaction_date__gte=twelve_months_ago).values_list('client_id', flat=True))
        active_ids_pmsaif = set(pms_aif_qs.filter(transaction_date__gte=twelve_months_ago).values_list('client_code', flat=True))
        active_count = len(active_ids_aaa | active_ids_mf | active_ids_pmsaif)

        # Dormant: No transaction in last 24 months
        twenty_four_months_ago = datetime.now() - timedelta(days=730)
        recent_ids_aaa = set(aaa_qs.filter(transaction_date__gte=twenty_four_months_ago).values_list('client_id', flat=True))
        recent_ids_mf = set(mf_qs.filter(transaction_date__gte=twenty_four_months_ago).values_list('client_id', flat=True))
        recent_ids_pmsaif = set(pms_aif_qs.filter(transaction_date__gte=twenty_four_months_ago).values_list('client_code', flat=True))
        recent_ids = recent_ids_aaa | recent_ids_mf | recent_ids_pmsaif
        
        # Clients who exist in view but are NOT in the recent_ids set
        dormant_count = client_qs.exclude(client_code__in=recent_ids).count() + \
                        wm_client_qs.exclude(client_code__in=recent_ids).count() + \
                        pms_client_qs.exclude(client_code__in=recent_ids).count()

        totals = {
            "overall": {
                "aum": float(equity_aum_val + mf_aum_val + pms_aif_combined_aum),
                "brokerage": float(equity_brk + mf_brk + pms_aif_brk),
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
            "pms_aif": {
                "aum": float(pms_aif_combined_aum),
                "brokerage": float(pms_aif_brk),
                "clients": pms_aif_clients_count
            },
            "active_clients": active_count,
            "dormant_clients": dormant_count,
            "equity_aum_detail": float(equity_aum_val),
            "mf_aum_detail": float(mf_aum_val),
            "pms_aum_detail": float(pms_aum_val),
            "aif_aum_detail": float(aif_aum_val)
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
        
        import time
        from django.db import transaction, OperationalError
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with transaction.atomic():
                    UserProfile.objects.update_or_create(
                        user=request.user,
                        defaults={'default_landing_tab': tab}
                    )
                return Response({"success": True, "tab": tab})
            except OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    time.sleep(1) # Wait and retry
                    continue
                logger.error(f"Database locked error on attempt {attempt + 1}: {e}")
                return Response({"error": "Database is busy (Data loading in progress). Please try again in 10 seconds."}, status=503)
            except Exception as e:
                logger.error(f"Error saving user preference: {e}")
                return Response({"error": "An unexpected error occurred."}, status=500)


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

        # Base Querysets
        qs = Client.objects.all()
        wm_qs = ClientWealthMagic.objects.all()
        pmsaif_qs = ClientPMSAIF.objects.all()

        # Hierarchy/Mode Filtering helper
        def apply_client_hierarchy(queryset):
            if view_mode == "self":
                return queryset.filter(rm_name=user_full_name)
            else:
                # TEAM Mode
                if user_role == "L":
                    return queryset # Leader sees everything
                elif user_role == "M":
                    if user_employee:
                        subs = user_employee.get_subordinates(recursive=True)
                        sub_names = [s.rm_name for s in subs]
                        # Handling different field names if necessary, but models seem consistent on rm_name
                        return queryset.filter(Q(rm_name=user_full_name) | Q(rm_name__in=sub_names))
                    else:
                        return queryset.filter(Q(rm_name=user_full_name) | Q(rm_manager_name=user_full_name))
                else:
                    # RM sees only self
                    return queryset.filter(rm_name=user_full_name)

        qs = apply_client_hierarchy(qs)
        wm_qs = apply_client_hierarchy(wm_qs)
        pmsaif_qs = apply_client_hierarchy(pmsaif_qs)

        # City Options (only Client model has city, others use RM lookup if needed, but for now we aggregate from what we have)
        all_cities = qs.exclude(city__isnull=True).exclude(city="").values_list('city', flat=True).distinct().order_by('city')

        # City Filter (Applies primarily to Client model)
        if city_filter:
            qs = qs.filter(city__iexact=city_filter)
            # WealthMagic/PMSAIF don't have city field. If city filter active, they might not show unless we join.
            # For simplicity, if city filter is on, we might restrict to main Client table or empty results for others.

        # Search Filtering
        def apply_search(queryset):
            if not search_query: return queryset
            if search_by == "code":
                return queryset.filter(client_code__icontains=search_query)
            elif search_by == "pan":
                return queryset.filter(client_pan__icontains=search_query)
            elif search_by == "name":
                return queryset.filter(client_name__icontains=search_query)
            elif search_by == "group":
                return queryset.filter(wire_code__icontains=search_query)
            return queryset

        qs = apply_search(qs)
        wm_qs = apply_search(wm_qs)
        pmsaif_qs = apply_search(pmsaif_qs)

        total_count = qs.count() + wm_qs.count() + pmsaif_qs.count()
        
        # Build combined results
        results = []
        for r in qs.values('client_code', 'client_pan', 'client_name', 'wire_code', 'aum', 'city').order_by('client_name')[:500]:
            results.append({
                "code": r['client_code'] or "-",
                "pan": r['client_pan'] or "-",
                "name": r['client_name'] or "-",
                "group": r['wire_code'] or "-",
                "aum": float(r['aum'] or 0),
                "city": r['city'] or "-",
                "source": "Equity/MF"
            })
        
        # Add WealthMagic (Limit to avoid massive response if combined)
        for r in wm_qs.values('client_code', 'client_pan', 'client_name', 'wire_code', 'aum').order_by('client_name')[:200]:
            results.append({
                "code": r['client_code'] or "-",
                "pan": r['client_pan'] or "-",
                "name": r['client_name'] or "-",
                "group": r['wire_code'] or "-",
                "aum": float(r['aum'] or 0),
                "city": "-", # No city in WealthMagic
                "source": "WealthMagic"
            })
            
        for r in pmsaif_qs.values('client_code', 'client_pan', 'client_name', 'wire_code', 'aum').order_by('client_name')[:200]:
            results.append({
                "code": r['client_code'] or "-",
                "pan": r['client_pan'] or "-",
                "name": r['client_name'] or "-",
                "group": r['wire_code'] or "-",
                "aum": float(r['aum'] or 0),
                "city": "-",
                "source": "PMS/AIF"
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
        pms_aif_qs = BrokerageAnalytics._apply_filters(SalesRecordPMSAIF.objects.all(), filters)

        # Totals Aggregation
        equity_aum = aaa_qs.aggregate(total=Coalesce(Sum('total_turnover'), Decimal('0')))['total']
        mf_aum = mf_qs.aggregate(total=Coalesce(Sum('mf_turnover'), Decimal('0')))['total']
        pms_aum_total = pms_aif_qs.aggregate(total=Coalesce(Sum('pms_aum'), Decimal('0')))['total']
        aif_aum_total = pms_aif_qs.aggregate(total=Coalesce(Sum('aif_aum'), Decimal('0')))['total']
        pms_aif_combined_aum = pms_aum_total + aif_aum_total
        overall_aum = equity_aum + mf_aum + pms_aif_combined_aum
        
        # Use segment-specific total for display logic
        if active_card == "equity": display_total = equity_aum
        elif active_card == "mf": display_total = mf_aum
        elif active_card == "pms_aif": display_total = pms_aif_combined_aum
        else: display_total = overall_aum

        # Records logic
        all_records = {
            "overall": [],
            "equity": [],
            "mf": [],
            "pms_aif": []
        }

        # 1. Overall - Group by PAN across all sources
        aaa_cli = aaa_qs.values('client_name', 'client_pan', 'client_id').annotate(equity=Sum('total_turnover'))
        mf_cli = mf_qs.values('client_name', 'client_pan', 'client_id').annotate(mf=Sum('mf_turnover'))
        pms_aif_cli = pms_aif_qs.values('client_name', 'client_pan', 'client_code').annotate(pms=Sum('pms_aum'), aif=Sum('aif_aum'))
        
        cli_data = {}
        for r in aaa_cli:
            pan = r['client_pan'] or r['client_name']
            cli_data[pan] = {
                "code": r['client_id'] or "-", "name": r['client_name'] or "-", "pan": r['client_pan'] or "-",
                "equity": float(r['equity'] or 0), "mf": 0.0, "pms": 0.0, "aif": 0.0
            }
        for r in mf_cli:
            pan = r['client_pan'] or r['client_name']
            if pan not in cli_data:
                cli_data[pan] = {"code": r['client_id'] or "-", "name": r['client_name'] or "-", "pan": r['client_pan'] or "-", "equity": 0.0, "mf": 0.0, "pms": 0.0, "aif": 0.0}
            cli_data[pan]['mf'] += float(r['mf'] or 0)
            if cli_data[pan]['code'] == "-" and r['client_id']:
                cli_data[pan]['code'] = r['client_id']
        for r in pms_aif_cli:
            pan = r['client_pan'] or r['client_name']
            if pan not in cli_data:
                cli_data[pan] = {"code": r['client_code'] or "-", "name": r['client_name'] or "-", "pan": r['client_pan'] or "-", "equity": 0.0, "mf": 0.0, "pms": 0.0, "aif": 0.0}
            cli_data[pan]['pms'] += float(r['pms'] or 0)
            cli_data[pan]['aif'] += float(r['aif'] or 0)
            if cli_data[pan]['code'] == "-" and r['client_code']:
                cli_data[pan]['code'] = r['client_code']
        
        for pan, data in cli_data.items():
            if search_query:
                match = False
                q = search_query.lower()
                if search_by == "pan" and q in data['pan'].lower(): match = True
                elif search_by == "name" and q in data['name'].lower(): match = True
                elif search_by == "code" and q in data['code'].lower(): match = True
                if not match: continue
            
            all_records["overall"].append({
                "code": data['code'], "name": data['name'], "pan": data['pan'],
                "equity": data['equity'], "mf": data['mf'],
                "pms_aum": data['pms'], "aif_aum": data['aif'],
                "total": data['equity'] + data['mf'] + data['pms'] + data['aif']
            })
        all_records["overall"].sort(key=lambda x: x['total'], reverse=True)
        all_records["overall"] = all_records["overall"][:500]

        # 2. Equity
        equity_qs = aaa_qs
        if search_query:
            if search_by == "pan": equity_qs = equity_qs.filter(client_pan__icontains=search_query)
            elif search_by == "name": equity_qs = equity_qs.filter(client_name__icontains=search_query)
            elif search_by == "code": equity_qs = equity_qs.filter(client__client_code__icontains=search_query)
        
        e_items = equity_qs.values('client_name', 'client_pan', 'client_id').annotate(val=Sum('total_turnover')).order_by('-val')
        for r in e_items[:500]:
            all_records["equity"].append({
                "code": r['client_id'] or "-", "name": r['client_name'] or "-", "pan": r['client_pan'] or "-",
                "total": float(r['val'] or 0)
            })

        # 3. MF
        mf_target_qs = mf_qs
        if search_query:
            if search_by == "pan": mf_target_qs = mf_target_qs.filter(client_pan__icontains=search_query)
            elif search_by == "name": mf_target_qs = mf_target_qs.filter(client_name__icontains=search_query)
            elif search_by == "code": mf_target_qs = mf_target_qs.filter(client__client_code__icontains=search_query)
        
        m_items = mf_target_qs.values('client_name', 'client_pan', 'client_id').annotate(val=Sum('mf_turnover')).order_by('-val')
        for r in m_items[:500]:
            all_records["mf"].append({
                "code": r['client_id'] or "-", "name": r['client_name'] or "-", "pan": r['client_pan'] or "-",
                "total": float(r['val'] or 0)
            })
        
        # 4. PMS/AIF
        pa_target_qs = pms_aif_qs
        if search_query:
            if search_by == "code": pa_target_qs = pa_target_qs.filter(client_code__icontains=search_query)
            elif search_by == "pan": pa_target_qs = pa_target_qs.filter(client_pan__icontains=search_query)
            elif search_by == "name": pa_target_qs = pa_target_qs.filter(client_name__icontains=search_query)
        
        pa_items = pa_target_qs.values('client_code', 'client_name', 'client_pan').annotate(
            p_aum=Sum('pms_aum'), a_aum=Sum('aif_aum')
        ).order_by('-p_aum', '-a_aum')
        
        for r in pa_items[:500]:
            all_records["pms_aif"].append({
                "code": r['client_code'] or "-", "name": r['client_name'] or "-", "pan": r['client_pan'] or "-",
                "pms_aum": float(r['p_aum'] or 0), "aif_aum": float(r['a_aum'] or 0),
                "total": float((r['p_aum'] or 0) + (r['a_aum'] or 0))
            })

        return Response({
            "user": {"full_name": user_full_name, "role": user_role},
            "totals": {
                "overall": float(overall_aum),
                "equity_total": float(equity_aum),
                "mf_total": float(mf_aum),
                "pms_aif_total": float(pms_aif_combined_aum)
            },
            "records": all_records,
            "last_updated": datetime.now().strftime("%-m/%-d/%Y %-I:%M:%S %p")
        })
