"""
Data Engineering Pipeline for Sales Dashboard
Handles automatic loading of dimensional and fact data from data_files folders
- Employee_dim: RM details and organizational hierarchy
- Client_dim: Client master data with RM assignments
- brokerage_fact: Brokerage transactions
- MF_fact: Mutual Fund transactions
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from django.db import transaction
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class DataPipeline:
    """Main pipeline orchestrator"""
    
    def __init__(self):
        self.project_root = settings.BASE_DIR.parent
        self.data_root = self.project_root / 'data_files'
        self.employee_dim_path = self.data_root / 'Employee_dim'
        self.client_dim_path = self.data_root / 'Client_dim'
        self.brokerage_fact_path = self.data_root / 'brokerage_fact'
        self.mf_fact_path = self.data_root / 'MF_fact'
        self.stats = {}
    
    def prune_stale_records(self):
        """Removes SalesRecord entries whose source file no longer exists on disk."""
        from core.models import SalesRecord
        all_existing_filenames = []
        # Check fact directories for existing files
        for folder in [self.brokerage_fact_path, self.mf_fact_path]:
            if folder.exists():
                all_existing_filenames.extend([f.name for f in folder.glob("*") if f.is_file()])
        
        # Also include dimension files to be safe, although those models are different
        # For now we focus on SalesRecord which is the main dashboard data
        
        stale_records = SalesRecord.objects.all()
        if all_existing_filenames:
            stale_records = stale_records.exclude(file_name__in=all_existing_filenames)
        
        count = stale_records.count()
        if count > 0:
            logger.info(f"Pruning {count} stale records from database (source files deleted).")
            stale_records.delete()
        return count

    def run_full_pipeline(self, clear_existing=False):
        """Execute the complete ETL pipeline"""
        # First, prune any records whose files were manually deleted
        self.prune_stale_records()
        
        logger.info("=" * 80)
        logger.info("STARTING DATA PIPELINE - Full ETL Process")
        logger.info("=" * 80)
        
        try:
            # Step 1: Load employee dimension
            logger.info("\n[1/5] Loading Employee Dimension...")
            employee_count = self._load_employee_dimension(clear_existing)
            self.stats['employees_loaded'] = employee_count
            
            # Step 1b: Build employee hierarchy
            logger.info("\n[1b/5] Building Employee Hierarchy (Manager relationships)...")
            hierarchy_count = self._build_employee_hierarchy()
            self.stats['hierarchy_links'] = hierarchy_count
            
            # Step 2: Load client dimension
            logger.info("\n[2/5] Loading Client Dimension...")
            client_count = self._load_client_dimension(clear_existing)
            self.stats['clients_loaded'] = client_count
            
            # Step 3: Load brokerage facts
            logger.info("\n[3/5] Loading Brokerage Facts...")
            brokerage_count = self._load_brokerage_facts()
            self.stats['brokerage_records_loaded'] = brokerage_count
            
            # Step 4: Load MF facts
            logger.info("\n[4/5] Loading MF Facts...")
            mf_count = self._load_mf_facts()
            self.stats['mf_records_loaded'] = mf_count
            
            # Step 5: Link UserProfile to Employee (optional)
            logger.info("\n[5/5] Linking UserProfile to Employee dimension...")
            profile_count = self._link_userprofile_to_employee()
            self.stats['profiles_linked'] = profile_count
            
            logger.info("\n" + "=" * 80)
            logger.info("PIPELINE COMPLETED SUCCESSFULLY")
            logger.info("=" * 80)
            self._print_summary()
            
            return True
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            return False
    
    def _load_employee_dimension(self, clear_existing=False):
        """Load RM/MA details from Employee_dim folder"""
        from core.models import Employee
        
        if clear_existing:
            Employee.objects.all().delete()
            logger.warning("Cleared existing Employee records")
        
        count = 0
        
        if not self.employee_dim_path.exists():
            logger.warning(f"Employee_dim path does not exist: {self.employee_dim_path}")
            return count
        
        excel_files = list(self.employee_dim_path.glob('*.xlsx'))
        logger.info(f"Found {len(excel_files)} Excel files in Employee_dim")
        
        # Column mapping variations
        wire_code_cols = ['wire code', 'WireCode', 'Wire Code', 'ID', 'employee id']
        rm_name_cols = ['NAME', 'RM_Name', 'RM Name', 'rm_name']
        manager_name_cols = ['RM_Manager_Name', 'RM Manager Name', 'MANAGER NAME', 'MANAGER ID'] # MANAGER ID is often used for manager name in some files
        
        with transaction.atomic():
            for file_path in excel_files:
                try:
                    logger.info(f"  Processing: {file_path.name}")
                    xls = pd.ExcelFile(file_path)
                    
                    for sheet_name in xls.sheet_names:
                        df = pd.read_excel(file_path, sheet_name=sheet_name)
                        df.columns = df.columns.str.strip()
                        
                        logger.info(f"    Processing sheet '{sheet_name}' with {len(df)} rows")
                        
                        for idx, row in df.iterrows():
                            try:
                                # Flexible wire code detection
                                wire_code = None
                                for col in wire_code_cols:
                                    val = row.get(col)
                                    if not pd.isna(val) and str(val).strip():
                                        wire_code = str(val).strip()
                                        break
                                
                                # Flexible RM name detection
                                rm_name = None
                                for col in rm_name_cols:
                                    val = row.get(col)
                                    if not pd.isna(val) and str(val).strip():
                                        rm_name = str(val).strip()
                                        break
                                
                                if not wire_code or not rm_name or wire_code.lower() == 'nan':
                                    continue
                                
                                # Flexible manager name detection
                                manager_name = None
                                for col in manager_name_cols:
                                    val = row.get(col)
                                    if not pd.isna(val) and str(val).strip():
                                        manager_name = str(val).strip()
                                        break

                                Employee.objects.update_or_create(
                                    wire_code=wire_code,
                                    defaults={
                                        'rm_name': rm_name,
                                        'rm_manager_name': manager_name or None,
                                        'ma_name': str(row.get('MA_Name', row.get('MA Name', ''))).strip() or None,
                                        'email': str(row.get('RM_Email', row.get('Email', ''))).strip() or None,
                                        'phone': str(row.get('RM_Ph', row.get('Phone', ''))).strip() or None,
                                        'designation': str(row.get('Designation', row.get('RM_Level', ''))).strip() or None,
                                    }
                                )
                                count += 1
                            except Exception as e:
                                logger.warning(f"    Row {idx} skipped: {e}")
                                continue
                
                except Exception as e:
                    logger.error(f"  Error processing {file_path.name}: {e}")
                    continue
        
        logger.info(f"[OK] Loaded {count} Employee records")
        return count
    
    def _load_client_dimension(self, clear_existing=False):
        """Load client master data from Client_dim folder"""
        from core.models import Client, Employee
        
        if clear_existing:
            Client.objects.all().delete()
            logger.warning("Cleared existing Client records")
        
        count = 0
        
        if not self.client_dim_path.exists():
            logger.warning(f"Client_dim path does not exist: {self.client_dim_path}")
            return count
        
        excel_files = list(self.client_dim_path.glob('*.xlsx'))
        logger.info(f"Found {len(excel_files)} Excel files in Client_dim")
        
        # Column mapping variations
        client_code_cols = ['Client_Code', 'Client Code', 'Client ID/PAN', 'CLIENTID', 'Client ID']
        client_name_cols = ['Client_Name', 'Client Name', 'INVESTORN0', 'INV_NAME']
        rm_name_cols = ['RM_Name', 'RM Name', 'RM', 'RM NAME']
        wire_code_cols = ['WireCode', 'Wire Code', 'wire_code', 'wire code']
        
        with transaction.atomic():
            for file_path in excel_files:
                try:
                    logger.info(f"  Processing: {file_path.name}")
                    xls = pd.ExcelFile(file_path)
                    
                    for sheet_name in xls.sheet_names:
                        df = pd.read_excel(file_path, sheet_name=sheet_name)
                        df.columns = df.columns.str.strip()
                        
                        logger.info(f"    Processing sheet '{sheet_name}' with {len(df)} rows")
                        
                        for idx, row in df.iterrows():
                            try:
                                client_code = None
                                for col in client_code_cols:
                                    val = row.get(col)
                                    if not pd.isna(val) and str(val).strip():
                                        client_code = str(val).strip()
                                        break
                                
                                client_name = None
                                for col in client_name_cols:
                                    val = row.get(col)
                                    if not pd.isna(val) and str(val).strip():
                                        client_name = str(val).strip()
                                        break
                                        
                                rm_name = None
                                for col in rm_name_cols:
                                    val = row.get(col)
                                    if not pd.isna(val) and str(val).strip():
                                        rm_name = str(val).strip()
                                        break
                                
                                if not client_code or not client_name or not rm_name:
                                    continue
                                
                                # Try to detect wire_code
                                wire_code_val = None
                                for col in wire_code_cols:
                                    val = row.get(col)
                                    if not pd.isna(val) and str(val).strip():
                                        wire_code_val = str(val).strip()
                                        break
                                
                                # Try to link to Employee
                                employee = None
                                if wire_code_val:
                                    employee = Employee.objects.filter(wire_code=wire_code_val).first()
                                
                                # If no wire_code, try to find employee by RM Name
                                if not employee:
                                    employee = Employee.objects.filter(rm_name__iexact=rm_name).first()
                                
                                Client.objects.update_or_create(
                                    client_code=client_code,
                                    defaults={
                                        'client_name': client_name,
                                        'wire_code': employee,
                                        'rm_name': rm_name,
                                        'rm_manager_name': str(row.get('RM_Manager_Name', row.get('RM Manager Name', ''))).strip() or None,
                                        'client_type': str(row.get('Client_Type', row.get('Client Type', ''))).strip() or None,
                                        'city': str(row.get('City', '')).strip() or None,
                                        'state': str(row.get('State', '')).strip() or None,
                                    }
                                )
                                count += 1
                            except Exception as e:
                                logger.warning(f"    Row {idx} skipped: {e}")
                                continue
                
                except Exception as e:
                    logger.error(f"  Error processing {file_path.name}: {e}")
                    continue
        
        logger.info(f"[OK] Loaded {count} Client records")
        return count
    
    def _load_brokerage_facts(self):
        """Load brokerage transaction data from brokerage_fact folder"""
        from core.models import SalesRecord, Employee, Client
        
        count = 0
        
        if not self.brokerage_fact_path.exists():
            logger.warning(f"brokerage_fact path does not exist: {self.brokerage_fact_path}")
            return count
        
        excel_files = list(self.brokerage_fact_path.glob('*.xlsx'))
        csv_files = list(self.brokerage_fact_path.glob('*.csv'))
        all_files = excel_files + csv_files
        logger.info(f"Found {len(excel_files)} Excel files and {len(csv_files)} CSV files in brokerage_fact")
        
        rm_name_cols = ['RM_Name', 'RM Name', 'RM', 'RM NAME', 'RMName']
        client_name_cols = ['Client_Name', 'Client Name', 'INVESTORN0', 'INV_NAME', 'ClientName']
        client_code_cols = ['Client Code', 'Client_Code', 'Client ID/PAN', 'CLIENTID', 'ClientCode', 'PAN_NO', 'PAN']
        wire_code_cols = ['WireCode', 'Wire Code', 'wire_code', 'wire code']
        
        with transaction.atomic():
            for file_path in all_files:
                try:
                    logger.info(f"  Processing: {file_path.name}")
                    period = self._extract_period_from_filename(file_path.name)

                    # Clear existing records for this file before re-loading (prevents duplicates)
                    deleted_count, _ = SalesRecord.objects.filter(file_name=file_path.name).delete()
                    if deleted_count:
                        logger.info(f"  Cleared {deleted_count} old records for {file_path.name}")

                    if file_path.suffix.lower() == '.csv':
                        df = pd.read_csv(file_path)
                        sheet_names = [None]
                        dataframes = [df]
                    else:
                        xls = pd.ExcelFile(file_path)
                        sheet_names = xls.sheet_names
                        dataframes = [pd.read_excel(file_path, sheet_name=sheet) for sheet in sheet_names]
                    
                    for sheet_name, df in zip(sheet_names, dataframes):
                        try:
                            df.columns = df.columns.str.strip()
                            
                            for idx, row in df.iterrows():
                                try:
                                    # Detection for linking
                                    wire_code_val = None
                                    for col in wire_code_cols:
                                        val = row.get(col)
                                        if not pd.isna(val) and str(val).strip():
                                            wire_code_val = str(val).strip()
                                            break
                                            
                                    client_code_val = None
                                    for col in client_code_cols:
                                        val = row.get(col)
                                        if not pd.isna(val) and str(val).strip():
                                            client_code_val = str(val).strip()
                                            break

                                    rm_name = None
                                    for col in rm_name_cols:
                                        val = row.get(col)
                                        if not pd.isna(val) and str(val).strip():
                                            rm_name = str(val).strip()
                                            break
                                    
                                    client_name = None
                                    for col in client_name_cols:
                                        val = row.get(col)
                                        if not pd.isna(val) and str(val).strip():
                                            client_name = str(val).strip()
                                            break

                                    # Link to Employee
                                    employee = None
                                    if wire_code_val:
                                        employee = Employee.objects.filter(wire_code=wire_code_val).first()
                                    
                                    if not rm_name and employee:
                                        rm_name = employee.rm_name
                                    
                                    if not employee and rm_name:
                                        employee = Employee.objects.filter(rm_name__iexact=rm_name).first()
                                        
                                    # Link to Client
                                    client = None
                                    if client_code_val:
                                        client = Client.objects.filter(client_code=client_code_val).first()
                                    
                                    if not client_name and client:
                                        client_name = client.client_name
                                        
                                    if not client and client_name:
                                        client = Client.objects.filter(client_name__iexact=client_name).first()

                                    if not rm_name or not client_name:
                                        continue

                                    # Link to Employee
                                    employee = None
                                    if wire_code_val:
                                        employee = Employee.objects.filter(wire_code=wire_code_val).first()
                                    if not employee:
                                        employee = Employee.objects.filter(rm_name__iexact=rm_name).first()
                                        
                                    # Link to Client
                                    client = None
                                    if client_code_val:
                                        client = Client.objects.filter(client_code=client_code_val).first()
                                    if not client:
                                        client = Client.objects.filter(client_name__iexact=client_name).first()

                                    SalesRecord.objects.create(
                                        employee=employee,
                                        client=client,
                                        rm_manager_name=str(row.get('RM_Manager_Name', row.get('RM Manager Name', ''))).strip() or None,
                                        rm_name=rm_name,
                                        ma_name=str(row.get('MA_Name', row.get('MA Name', ''))).strip() or None,
                                        wire_code=wire_code_val or str(row.get('WireCode', row.get('Wire Code', ''))).strip() or None,
                                        client_name=client_name,
                                        total_brokerage=self._safe_decimal(row.get('Sum of Total Brokerage', row.get('Total Brokerage', row.get('Brokerage', row.get('BROKERAGE', row.get('TotalBrokerage', 0)))))),
                                        cash_delivery=self._safe_decimal(row.get('Sum of Cash Delivery', row.get('Cash Delivery', row.get('CashDelivery', 0)))),
                                        cash_intraday=self._safe_decimal(row.get('Sum of Cash Intraday', row.get('Cash Intraday', row.get('CashIntraday', 0)))),
                                        equity_cash_delivery_turnover=self._safe_decimal(row.get('Sum of Equity Cash Delivery Turnover', row.get('Equity Cash Delivery Turnover', 0))),
                                        equity_futures_turnover=self._safe_decimal(row.get('Sum of Equity Futures Turnover', row.get('Equity Futures Turnover', 0))),
                                        equity_options_turnover=self._safe_decimal(row.get('Sum of Equity Options Turnover', row.get('Equity Options Turnover', 0))),
                                        equity_cash_intraday_turnover=self._safe_decimal(row.get('Sum of Equity Cash Intraday Turnover', row.get('Equity Cash Intraday Turnover', 0))),
                                        total_equity_cash_turnover=self._safe_decimal(row.get('Sum of Total Equity Cash Turnover', row.get('Total Equity Cash Turnover', 0))),
                                        total_equity_fno_turnover=self._safe_decimal(row.get('Sum of Total Equity FnO Turnover', row.get('Total Equity FnO Turnover', 0))),
                                        total_equity_turnover=self._safe_decimal(row.get('Sum of Total Equity Turnover', row.get('Total Equity Turnover', 0))),
                                        total_turnover=self._safe_decimal(row.get('Sum of Total Turnover', row.get('Total Turnover', row.get('Turnover', row.get('TURNOVER', row.get('TotalTurnover', 0)))))),
                                        data_source='BROKERAGE',
                                        period=period,
                                        file_name=file_path.name,
                                    )
                                    count += 1
                                except Exception as e:
                                    logger.warning(f"    Row {idx} skipped: {e}")
                                    continue
                        except Exception as e:
                            logger.warning(f"    Sheet '{sheet_name}' error: {e}")
                            continue
                
                except Exception as e:
                    logger.error(f"  Error processing {file_path.name}: {e}")
                    continue
        
        logger.info(f"[OK] Loaded {count} Brokerage records")
        return count
    
    def _load_mf_facts(self):
        """Load MF transaction data from MF_fact folder"""
        from core.models import SalesRecord, Employee, Client
        
        count = 0
        
        if not self.mf_fact_path.exists():
            logger.warning(f"MF_fact path does not exist: {self.mf_fact_path}")
            return count
        
        excel_files = list(self.mf_fact_path.glob('*.xlsx'))
        csv_files = list(self.mf_fact_path.glob('*.csv'))
        all_files = excel_files + csv_files
        logger.info(f"Found {len(excel_files)} Excel files and {len(csv_files)} CSV files in MF_fact")
        
        # MF specific column maps
        client_name_cols = ['INV_NAME', 'INVESTORN0', 'Client Name', 'Client_Name']
        client_code_cols = ['PAN_NO', 'PAN', 'Client Code', 'Client_Code']
        brokerage_cols = ['BROKERAGE', 'Total Brokerage', 'Brokerage']
        turnover_cols = ['AMOUNT', 'Total Turnover', 'Turnover']
        rm_name_cols = ['RM_Name', 'RM Name', 'RM']
        
        with transaction.atomic():
            for file_path in all_files:
                try:
                    logger.info(f"  Processing: {file_path.name}")
                    period = self._extract_period_from_filename(file_path.name)

                    # Clear existing records for this file before re-loading (prevents duplicates)
                    deleted_count, _ = SalesRecord.objects.filter(file_name=file_path.name).delete()
                    if deleted_count:
                        logger.info(f"  Cleared {deleted_count} old MF records for {file_path.name}")

                    if file_path.suffix.lower() == '.csv':
                        df = pd.read_csv(file_path)
                        sheet_names = [None]
                        dataframes = [df]
                    else:
                        xls = pd.ExcelFile(file_path)
                        sheet_names = xls.sheet_names
                        dataframes = [pd.read_excel(file_path, sheet_name=sheet) for sheet in sheet_names]
                    
                    for sheet_name, df in zip(sheet_names, dataframes):
                        try:
                            df.columns = df.columns.str.strip()
                            
                            for idx, row in df.iterrows():
                                try:
                                    client_name = None
                                    for col in client_name_cols:
                                        val = row.get(col)
                                        if not pd.isna(val) and str(val).strip():
                                            client_name = str(val).strip()
                                            break
                                            
                                    if not client_name:
                                        continue
                                        
                                    client_code_val = None
                                    for col in client_code_cols:
                                        val = row.get(col)
                                        if not pd.isna(val) and str(val).strip():
                                            client_code_val = str(val).strip()
                                            break
                                            
                                    rm_name = None
                                    for col in rm_name_cols:
                                        val = row.get(col)
                                        if not pd.isna(val) and str(val).strip():
                                            rm_name = str(val).strip()
                                            break

                                    # Try to link to Client
                                    client = None
                                    if client_code_val:
                                        client = Client.objects.filter(client_code=client_code_val).first()
                                    if not client:
                                        client = Client.objects.filter(client_name__iexact=client_name).first()
                                        
                                    # Try to link to Employee
                                    employee = None
                                    if client and client.wire_code:
                                        employee = client.wire_code
                                    elif rm_name:
                                        employee = Employee.objects.filter(rm_name__iexact=rm_name).first()

                                    # Metrics
                                    brokerage = 0
                                    for col in brokerage_cols:
                                        val = row.get(col)
                                        if not pd.isna(val):
                                            brokerage = val
                                            break
                                            
                                    turnover = 0
                                    for col in turnover_cols:
                                        val = row.get(col)
                                        if not pd.isna(val):
                                            turnover = val
                                            break

                                    SalesRecord.objects.create(
                                        employee=employee,
                                        client=client,
                                        rm_name=rm_name or (client.rm_name if client else None),
                                        client_name=client_name,
                                        mf_brokerage=self._safe_decimal(brokerage),
                                        mf_turnover=self._safe_decimal(turnover),
                                        data_source='MF',
                                        period=period,
                                        file_name=file_path.name,
                                    )
                                    count += 1
                                except Exception as e:
                                    logger.warning(f"    Row {idx} skipped: {e}")
                                    continue
                        except Exception as e:
                            logger.warning(f"    Sheet '{sheet_name}' error: {e}")
                            continue
                
                except Exception as e:
                    logger.error(f"  Error processing {file_path.name}: {e}")
                    continue
        
        logger.info(f"[OK] Loaded {count} MF records")
        return count
    
    @staticmethod
    def _safe_decimal(value):
        """Safely convert value to Decimal"""
        try:
            if pd.isna(value) or value is None or value == '':
                return Decimal('0')
            # Handle string values with commas
            if isinstance(value, str):
                value = value.replace(',', '')
            return Decimal(str(float(value)))
        except:
            return Decimal('0')
    
    @staticmethod
    def _extract_period_from_filename(filename):
        """Extract period info from filename"""
        import re
        
        # Normalize filename
        fn = filename.lower()
        
        # Patterns: "Jan 26", "Jan 2026", "oct25", "oct 25"
        month_pattern = r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)'
        year_pattern = r'(\d{2,4})'
        
        month_match = re.search(month_pattern, fn)
        
        # Try to find year near the month
        if month_match:
            month = month_match.group(1).capitalize()
            # Look for 2 or 4 digits near the month
            content_after = fn[month_match.end():]
            year_match = re.search(year_pattern, content_after)
            if not year_match:
                # Look before
                content_before = fn[:month_match.start()]
                year_match = re.search(year_pattern, content_before)
            
            if year_match:
                year = year_match.group(1)
                if len(year) == 2:
                    year = '20' + year
                return f"{month} {year}"
            
            # Default to 2026 if month found but no year
            return f"{month} 2026"
        
        return None
    
    def _print_summary(self):
        """Print pipeline execution summary"""
        logger.info("\nPIPELINE SUMMARY:")
        logger.info("-" * 80)
        for key, value in self.stats.items():
            logger.info(f"  {key.replace('_', ' ').title()}: {value}")
        
        total_records = (self.stats.get('brokerage_records_loaded', 0) + 
                        self.stats.get('mf_records_loaded', 0))
        logger.info(f"  Total Sales Records: {total_records}")
        logger.info("-" * 80)
    
    def _build_employee_hierarchy(self):
        """
        Build manager relationships (self-join) based on rm_manager_name
        Creates organizational hierarchy
        """
        from core.models import Employee
        
        count = 0
        
        try:
            employees = Employee.objects.all()
            
            for emp in employees:
                if emp.rm_manager_name:
                    try:
                        # Try to find manager by name
                        manager = Employee.objects.filter(
                            rm_name__iexact=emp.rm_manager_name
                        ).first()
                        
                        if manager and manager.wire_code != emp.wire_code:
                            emp.manager = manager
                            emp.save()
                            count += 1
                            logger.info(f"  Linked {emp.rm_name} -> {manager.rm_name}")
                    except Exception as e:
                        logger.warning(f"  Could not link {emp.rm_name}: {e}")
                        continue
            
            logger.info(f"[OK] Built {count} manager relationships")
            return count
            
        except Exception as e:
            logger.error(f"Error building hierarchy: {e}")
            return 0
    
    def _link_userprofile_to_employee(self):
        """
        Link UserProfile records to Employee dimension based on wire_code
        This integrates login/password management with RM data
        """
        from core.models import UserProfile, Employee
        
        count = 0
        try:
            profiles = UserProfile.objects.filter(
                wire_code__isnull=False,
                employee__isnull=True
            )
            
            for profile in profiles:
                try:
                    employee = Employee.objects.get(wire_code=profile.wire_code)
                    profile.employee = employee
                    profile.save()
                    count += 1
                    logger.info(f"  Linked user {profile.user.username} -> {employee.rm_name}")
                except Employee.DoesNotExist:
                    logger.warning(f"  Employee not found for wire_code: {profile.wire_code}")
                except Exception as e:
                    logger.warning(f"  Error linking {profile.user.username}: {e}")
                    continue
            
            logger.info(f"[OK] Linked {count} UserProfile records")
            return count
        except Exception as e:
            logger.error(f"Error linking UserProfile: {e}")
            return 0
