"""
Data Aggregation and Analytics Module
Provides methods to aggregate sales data for dashboard display
"""

from django.db.models import Sum, Count, Q, F, DecimalField
from django.db.models.functions import Coalesce
from decimal import Decimal
import pandas as pd
from .models import SalesRecord, Employee, Client, SalesRecordAAABrokerage, SalesRecordMF


class BrokerageAnalytics:
    """Analytics engine for sales/brokerage data (using specialized tables)"""
    
    @staticmethod
    def _apply_filters(queryset, filters, is_mf=False):
        """Helper to apply common filters to querysets with priority override"""
        if not filters:
            return queryset
            
        # 1. Priority-based Employee Filtering (MA > RM > Manager)
        if filters.get('ma_name'):
            selected_ma = filters['ma_name']
            if is_mf:
                # Robust MA lookup: 1. Client Link, 2. Employee Link, 3. Wire Code Mapping
                # We need to find all wire codes associated with this MA to include them in the filter
                try:
                    ma_emp = Employee.objects.get(rm_name=selected_ma)
                    ma_wire_codes = list(ma_emp.wire_codes.values_list('wire_code', flat=True))
                    if ma_emp.wire_code:
                        ma_wire_codes.append(ma_emp.wire_code)
                    
                    queryset = queryset.filter(
                        Q(client__ma_name=selected_ma) | 
                        Q(employee__rm_name=selected_ma) |
                        Q(wire_code__in=ma_wire_codes)
                    )
                except Employee.DoesNotExist:
                    queryset = queryset.filter(Q(client__ma_name=selected_ma) | Q(employee__rm_name=selected_ma))
            else:
                queryset = queryset.filter(ma_name=selected_ma)
        elif filters.get('rm_name'):
            queryset = queryset.filter(rm_name=filters['rm_name'])
        elif filters.get('rm_manager_name'):
            queryset = queryset.filter(rm_manager_name=filters['rm_manager_name'])

        # 2. Additional Dimensional Filters
        if filters.get('client_name'):
            queryset = queryset.filter(client_name=filters['client_name'])
        
        if filters.get('period'):
            queryset = queryset.filter(period=filters['period'])
            
        if filters.get('wire_code'):
            queryset = queryset.filter(wire_code=filters['wire_code'])

        if filters.get('date_from'):
            queryset = queryset.filter(transaction_date__gte=filters['date_from'])

        if filters.get('date_to'):
            queryset = queryset.filter(transaction_date__lte=filters['date_to'])
            
        return queryset

    @staticmethod
    def get_total_brokerage(filters=None):
        """
        Get total brokerage across all sources (Equity + MF)
        """
        filters = filters or {}
        
        # AAA Brokerage
        aaa_qs = BrokerageAnalytics._apply_filters(SalesRecordAAABrokerage.objects.all(), filters)
        brokerage_total = aaa_qs.aggregate(total=Coalesce(Sum('total_brokerage'), Decimal('0')))['total']
        
        # MF Brokerage
        mf_qs = BrokerageAnalytics._apply_filters(SalesRecordMF.objects.all(), filters, is_mf=True)
        mf_total = mf_qs.aggregate(total=Coalesce(Sum('mf_brokerage'), Decimal('0')))['total']
        
        return brokerage_total + mf_total
    
    @staticmethod
    def get_brokerage_by_rm(filters=None):
        """
        Get brokerage breakdown by RM
        """
        filters = filters or {}
        
        # Get all unique RM names from both tables
        aaa_rms = set(BrokerageAnalytics._apply_filters(SalesRecordAAABrokerage.objects.all(), filters).values_list('rm_name', flat=True).distinct())
        mf_rms = set(BrokerageAnalytics._apply_filters(SalesRecordMF.objects.all(), filters, is_mf=True).values_list('rm_name', flat=True).distinct())
        all_rm_names = aaa_rms.union(mf_rms)
        
        data = []
        for rm_name in all_rm_names:
            # AAA for this RM
            aaa_rm_qs = BrokerageAnalytics._apply_filters(SalesRecordAAABrokerage.objects.filter(rm_name=rm_name), filters)
            brk_total = aaa_rm_qs.aggregate(total=Coalesce(Sum('total_brokerage'), Decimal('0')))['total']
            
            # MF for this RM
            mf_rm_qs = BrokerageAnalytics._apply_filters(SalesRecordMF.objects.filter(rm_name=rm_name), filters, is_mf=True)
            mf_total = mf_rm_qs.aggregate(total=Coalesce(Sum('mf_brokerage'), Decimal('0')))['total']
            
            combined = brk_total + mf_total
            count = aaa_rm_qs.count() + mf_rm_qs.count()
            
            data.append({
                'rm_name': rm_name,
                'brokerage_total': float(brk_total),
                'mf_total': float(mf_total),
                'total_brokerage': float(combined),
                'client_count': count,
            })
        
        data.sort(key=lambda x: x['total_brokerage'], reverse=True)
        return data
    
    @staticmethod
    def get_brokerage_by_rm_manager(filters=None):
        """
        Get brokerage breakdown by RM Manager
        """
        filters = filters or {}
        
        aaa_mgrs = set(BrokerageAnalytics._apply_filters(SalesRecordAAABrokerage.objects.filter(rm_manager_name__isnull=False), filters).values_list('rm_manager_name', flat=True).distinct())
        mf_mgrs = set(BrokerageAnalytics._apply_filters(SalesRecordMF.objects.filter(rm_manager_name__isnull=False), filters, is_mf=True).values_list('rm_manager_name', flat=True).distinct())
        all_manager_names = aaa_mgrs.union(mf_mgrs)
        
        data = []
        for mgr_name in all_manager_names:
            aaa_mgr_qs = BrokerageAnalytics._apply_filters(SalesRecordAAABrokerage.objects.filter(rm_manager_name=mgr_name), filters)
            mf_mgr_qs = BrokerageAnalytics._apply_filters(SalesRecordMF.objects.filter(rm_manager_name=mgr_name), filters, is_mf=True)
            
            brk_total = aaa_mgr_qs.aggregate(total=Coalesce(Sum('total_brokerage'), Decimal('0')))['total']
            mf_total = mf_mgr_qs.aggregate(total=Coalesce(Sum('mf_brokerage'), Decimal('0')))['total']
            
            combined = brk_total + mf_total
            
            # Count unique RMs under this manager
            rm_count = set(aaa_mgr_qs.values_list('rm_name', flat=True).distinct()).union(
                       set(mf_mgr_qs.values_list('rm_name', flat=True).distinct()))
            
            data.append({
                'rm_manager_name': mgr_name,
                'brokerage_total': float(brk_total),
                'mf_total': float(mf_total),
                'total_brokerage': float(combined),
                'rm_count': len(rm_count),
                'client_count': aaa_mgr_qs.count() + mf_mgr_qs.count(),
            })
        
        data.sort(key=lambda x: x['total_brokerage'], reverse=True)
        return data
    
    @staticmethod
    def get_brokerage_by_client(rm_name=None, limit=50):
        """
        Get top clients by brokerage
        """
        filters = {'rm_name': rm_name} if rm_name else {}
        
        # This is a bit complex as we need to group by client across both tables
        # For simplicity, let's get unique clients from both
        aaa_clients = BrokerageAnalytics._apply_filters(SalesRecordAAABrokerage.objects.all(), filters).values('client_name', 'rm_name').distinct()
        mf_clients = BrokerageAnalytics._apply_filters(SalesRecordMF.objects.all(), filters, is_mf=True).values('client_name', 'rm_name').distinct()
        
        # Combine unique client-RM pairs
        unique_clients = {(c['client_name'], c['rm_name']) for c in aaa_clients}.union(
                         {(c['client_name'], c['rm_name']) for c in mf_clients})
        
        data = []
        for client_name, client_rm_name in unique_clients:
            brk_total = SalesRecordAAABrokerage.objects.filter(client_name=client_name, rm_name=client_rm_name).aggregate(total=Coalesce(Sum('total_brokerage'), Decimal('0')))['total']
            mf_total = SalesRecordMF.objects.filter(client_name=client_name, rm_name=client_rm_name).aggregate(total=Coalesce(Sum('mf_brokerage'), Decimal('0')))['total']
            
            combined = brk_total + mf_total
            
            data.append({
                'client_name': client_name,
                'rm_name': client_rm_name,
                'brokerage_total': float(brk_total),
                'mf_total': float(mf_total),
                'total_brokerage': float(combined),
            })
        
        data.sort(key=lambda x: x['total_brokerage'], reverse=True)
        return data[:limit]
    
    @staticmethod
    def get_period_summary(period=None):
        """
        Get summary statistics for a period
        """
        filters = {'period': period} if period else {}
        
        aaa_qs = BrokerageAnalytics._apply_filters(SalesRecordAAABrokerage.objects.all(), filters)
        mf_qs = BrokerageAnalytics._apply_filters(SalesRecordMF.objects.all(), filters, is_mf=True)
        
        brk_total = aaa_qs.aggregate(total=Coalesce(Sum('total_brokerage'), Decimal('0')))['total']
        mf_total = mf_qs.aggregate(total=Coalesce(Sum('mf_brokerage'), Decimal('0')))['total']
        
        unique_clients = set(aaa_qs.values_list('client_name', flat=True).distinct()).union(
                         set(mf_qs.values_list('client_name', flat=True).distinct()))
                         
        unique_rms = set(aaa_qs.values_list('rm_name', flat=True).distinct()).union(
                     set(mf_qs.values_list('rm_name', flat=True).distinct()))
        
        unique_managers = set(aaa_qs.filter(rm_manager_name__isnull=False).values_list('rm_manager_name', flat=True).distinct()).union(
                          set(mf_qs.filter(rm_manager_name__isnull=False).values_list('rm_manager_name', flat=True).distinct()))
        
        return {
            'period': period or 'All Time',
            'brokerage_total': float(brk_total),
            'mf_total': float(mf_total),
            'combined_total': float(brk_total + mf_total),
            'unique_clients': len(unique_clients),
            'unique_rms': len(unique_rms),
            'unique_managers': len(unique_managers),
            'total_records': aaa_qs.count() + mf_qs.count(),
        }
    
    @staticmethod
    def get_available_periods():
        """Get list of all available periods in data"""
        aaa_periods = set(SalesRecordAAABrokerage.objects.filter(period__isnull=False).values_list('period', flat=True).distinct())
        mf_periods = set(SalesRecordMF.objects.filter(period__isnull=False).values_list('period', flat=True).distinct())
        periods = sorted(list(aaa_periods.union(mf_periods)), reverse=True)
        return periods
    
    @staticmethod
    def get_turnover_metrics(filters=None):
        """
        Get turnover breakdown
        """
        filters = filters or {}
        aaa_qs = BrokerageAnalytics._apply_filters(SalesRecordAAABrokerage.objects.all(), filters)
        
        agg = aaa_qs.aggregate(
            total_equity_cash=Coalesce(Sum('total_equity_cash_turnover'), Decimal('0')),
            total_equity_fno=Coalesce(Sum('total_equity_fno_turnover'), Decimal('0')),
            total_turnover=Coalesce(Sum('total_turnover'), Decimal('0')),
        )
        
        return {
            'equity_cash_turnover': float(agg['total_equity_cash']),
            'equity_fno_turnover': float(agg['total_equity_fno']),
            'total_turnover': float(agg['total_turnover']),
        }


class DataQuality:
    """Data quality checks and validation"""
    
    @staticmethod
    def get_data_summary():
        """Get data quality summary"""
        summary = {
            'total_aaa_records': SalesRecordAAABrokerage.objects.count(),
            'total_mf_records': SalesRecordMF.objects.count(),
            'total_employees': Employee.objects.count(),
            'total_clients': Client.objects.count(),
            'orphaned_clients_aaa': SalesRecordAAABrokerage.objects.filter(client__isnull=True).count(),
            'orphaned_clients_mf': SalesRecordMF.objects.filter(client__isnull=True).count(),
        }
        return summary
    
    @staticmethod
    def get_rm_coverage():
        """Check if all RMs in specialized tables exist in Employee table"""
        aaa_rms = set(SalesRecordAAABrokerage.objects.values_list('rm_name', flat=True).distinct())
        mf_rms = set(SalesRecordMF.objects.values_list('rm_name', flat=True).distinct())
        sales_rms = aaa_rms.union(mf_rms)
        
        employee_rms = set(Employee.objects.values_list('rm_name', flat=True).distinct())
        unmapped_rms = sales_rms - employee_rms
        
        return {
            'total_sales_rms': len(sales_rms),
            'total_employee_rms': len(employee_rms),
            'unmapped_rms': list(unmapped_rms),
            'unmapped_count': len(unmapped_rms),
        }

