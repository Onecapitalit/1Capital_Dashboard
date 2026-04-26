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
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.conf import settings
from django.db.models import Q
import logging
import re
import hashlib

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
        any_dir_exists = False
        # Check fact directories for existing files
        for folder in [self.brokerage_fact_path, self.mf_fact_path]:
            if folder.exists():
                any_dir_exists = True
                all_existing_filenames.extend([f.name for f in folder.glob("*") if f.is_file()])
        
        if not any_dir_exists:
            logger.warning("No fact data directories found — skipping prune to prevent accidental mass deletion.")
            return 0
        
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
            
            # New Step: Load specialized facts for the new dashboard
            logger.info("\n[4b/5] Loading Specialized Facts (New Tables)...")
            aaa_count = self._load_aaa_brokerage_facts()
            self.stats['aaa_brokerage_loaded'] = aaa_count
            
            special_mf_count = self._load_specialized_mf_facts()
            self.stats['specialized_mf_loaded'] = special_mf_count

            # Step 4c: Load specialized client dimensions (WealthMagic & PMS/AIF)
            logger.info("\n[4c/5] Loading Specialized Client Dimensions...")
            wm_count = self._load_wealthmagic_clients()
            self.stats['wealthmagic_clients_loaded'] = wm_count
            
            pms_count = self._load_pms_aif_clients()
            self.stats['pms_aif_clients_loaded'] = pms_count

            # Step 4d: Load PMS/AIF sales records
            logger.info("\n[4d/5] Loading PMS/AIF Sales Records...")
            pms_aif_sales_count = self._load_pms_aif_sales_records()
            self.stats['pms_aif_sales_loaded'] = pms_aif_sales_count
            
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
    
    def _parse_wire_codes(self, wire_code_str):
        """Split wire code string into a list of individual codes"""
        if not wire_code_str or pd.isna(wire_code_str) or str(wire_code_str).lower() == 'nan':
            return []
        # Split by comma or slash
        codes = re.split(r'[,/]', str(wire_code_str))
        # Strip whitespace and remove empty strings
        return [c.strip() for c in codes if c.strip()]

    def _parse_aum(self, aum_str):
        """
        Parse AUM string into Decimal.
        Handles:
        - "1.5 cr" -> 15,000,000
        - "20 l"   -> 2,000,000
        - "50 k"   -> 50,000
        """
        if not aum_str or pd.isna(aum_str) or str(aum_str).lower() == 'nan':
            return Decimal('0')
        
        try:
            # Convert to string and clean
            s = str(aum_str).lower().strip()
            # Remove currency symbols and commas
            s = re.sub(r'[^\d\.a-z]', '', s)
            
            multipliers = {
                'cr': Decimal('10000000'),
                'crore': Decimal('10000000'),
                'l': Decimal('100000'),
                'lakh': Decimal('100000'),
                'k': Decimal('1000'),
                'thousand': Decimal('1000'),
            }
            
            # Find multiplier
            multiplier = Decimal('1')
            for unit, mult in multipliers.items():
                if s.endswith(unit):
                    multiplier = mult
                    s = s[:-len(unit)].strip()
                    break
            
            # Convert remaining numeric part
            if not s:
                return Decimal('0')
            
            return Decimal(s) * multiplier
            
        except (ValueError, TypeError, ArithmeticError, InvalidOperation):
            return Decimal('0')

    def _get_col(self, df, possible_names):
        """Helper to find a column name in a dataframe regardless of case or spaces/underscores"""
        normalized_possible = [n.lower().replace(' ', '').replace('_', '') for n in possible_names]
        for col in df.columns:
            norm_col = str(col).lower().replace(' ', '').replace('_', '')
            if norm_col in normalized_possible:
                return col
        return None

    def _load_employee_dimension(self, clear_existing=False):
        """Load RM/MA details from Employee_dim folder."""
        from core.models import Employee, EmployeeWireCode

        if clear_existing:
            Employee.objects.all().delete()
            logger.warning("Cleared existing Employee records")

        count = 0

        if not self.employee_dim_path.exists():
            logger.warning(f"Employee_dim path does not exist: {self.employee_dim_path}")
            return count

        excel_files = list(self.employee_dim_path.glob('*.xlsx'))
        logger.info(f"Found {len(excel_files)} Excel files in Employee_dim")

        # Column families
        wire_code_cols = ['wire code', 'WireCode', 'Wire Code']
        rm_name_cols = ['NAME', 'RM_Name', 'RM Name', 'rm_name']
        pan_cols = ['PAN', 'RM_Pan', 'PAN NO']
        id_cols = ['ID', 'Employee_id']
        manager_id_cols = ['MANAGER ID', 'Manager_ID', 'Manager ID']

        # ── Phase 1: Build ID→metadata lookup from ID-based sheets ──
        id_to_meta = {}
        self._employee_manager_map = {}

        for file_path in excel_files:
            try:
                xls = pd.ExcelFile(file_path)
                for sheet_name in xls.sheet_names:
                    df = pd.read_excel(file_path, sheet_name=sheet_name)
                    df.columns = df.columns.str.strip()

                    id_col = self._get_col(df, id_cols)
                    mgr_id_col = self._get_col(df, manager_id_cols)

                    if not (id_col and mgr_id_col):
                        continue

                    logger.info(f"  [Phase 1] Scanning: {file_path.name} / '{sheet_name}' ({len(df)} rows)")

                    name_col = self._get_col(df, rm_name_cols)
                    wire_col = self._get_col(df, wire_code_cols)
                    pan_col = self._get_col(df, pan_cols)

                    for idx, row in df.iterrows():
                        try:
                            row_id_val = row.get(id_col)
                            if pd.isna(row_id_val): continue
                            row_id = int(row_id_val)

                            name = str(row.get(name_col, '')).strip() if name_col and not pd.isna(row.get(name_col)) else None
                            if not name or name.lower() == 'nan':
                                continue

                            wire_code_str = str(row.get(wire_col, '')).strip() if wire_col and not pd.isna(row.get(wire_col)) else None
                            pan = str(row.get(pan_col, '')).strip() if pan_col and not pd.isna(row.get(pan_col)) else None
                            
                            mgr_id_val = row.get(mgr_id_col)
                            mgr_id = int(mgr_id_val) if not pd.isna(mgr_id_val) and str(mgr_id_val).lower() != 'nan' else None

                            id_to_meta[row_id] = {
                                'name': name, 
                                'wire_code_str': wire_code_str, 
                                'pan': pan, 
                                'manager_id': mgr_id
                            }
                        except:
                            continue

            except Exception as e:
                logger.error(f"  Error scanning {file_path.name}: {e}")

        # ── Phase 2: Create Employee records ──
        with transaction.atomic():
            # Clear all wire codes before re-loading to ensure consistency
            EmployeeWireCode.objects.all().delete()
            
            for row_id, meta in sorted(id_to_meta.items()):
                pan = meta['pan']
                if not pan:
                    logger.warning(f"  Skipping '{meta['name']}' (ID={row_id}): no PAN available")
                    continue

                manager_name = None
                manager_pan = None
                if meta['manager_id'] and meta['manager_id'] in id_to_meta:
                    mgr = id_to_meta[meta['manager_id']]
                    manager_name = mgr['name']
                    manager_pan = mgr.get('pan')

                if manager_pan:
                    self._employee_manager_map[pan] = manager_pan

                # Add primary wire code to employee record for convenience
                wire_codes = self._parse_wire_codes(meta['wire_code_str'])
                primary_wire_code = wire_codes[0] if wire_codes else None

                employee, created = Employee.objects.update_or_create(
                    pan_number=pan,
                    defaults={
                        'rm_name': meta['name'],
                        'rm_manager_name': manager_name,
                        'wire_code': primary_wire_code,
                    }
                )
                
                # Add all wire codes to the many-to-many helper table
                for wc in wire_codes:
                    EmployeeWireCode.objects.get_or_create(
                        employee=employee,
                        wire_code=wc
                    )
                
                count += 1

            # ── Phase 3: Enrich from non-ID sheets ──
            for file_path in excel_files:
                try:
                    xls = pd.ExcelFile(file_path)
                    for sheet_name in xls.sheet_names:
                        df = pd.read_excel(file_path, sheet_name=sheet_name)
                        df.columns = df.columns.str.strip()

                        # Skip sheets already processed in Phase 1
                        if self._get_col(df, id_cols) and self._get_col(df, manager_id_cols):
                            continue

                        pan_col = self._get_col(df, pan_cols)
                        if not pan_col: continue

                        logger.info(f"  [Phase 3] Enriching from: {file_path.name} / '{sheet_name}' ({len(df)} rows)")
                        enriched = 0

                        for idx, row in df.iterrows():
                            try:
                                pan = str(row.get(pan_col, '')).strip()
                                if not pan or pan.lower() == 'nan':
                                    continue

                                try:
                                    emp = Employee.objects.get(pan_number=pan)
                                except Employee.DoesNotExist:
                                    continue

                                updated = False
                                for field, cols in [
                                    ('email', ['RM_Email', 'Email', 'Email ID']),
                                    ('phone', ['RM_Ph', 'Phone', 'Mobile']),
                                    ('designation', ['Designation', 'RM_Level', 'Level']),
                                    ('ma_name', ['MA_Name', 'MA Name', 'MA']),
                                ]:
                                    target_col = self._get_col(df, cols)
                                    if target_col:
                                        val = str(row.get(target_col, '')).strip()
                                        if val and val.lower() != 'nan':
                                            setattr(emp, field, val)
                                            updated = True

                                mgr_target_col = self._get_col(df, ['RM_Manager_Name', 'RM Manager Name', 'Manager Name'])
                                if mgr_target_col:
                                    mgr_val = str(row.get(mgr_target_col, '')).strip()
                                    if mgr_val and mgr_val.lower() != 'nan':
                                        emp.rm_manager_name = mgr_val
                                        updated = True

                                if updated:
                                    emp.save()
                                    enriched += 1

                            except Exception as e:
                                continue

                        logger.info(f"    Enriched {enriched} employees with contact data")

                except Exception as e:
                    logger.error(f"  Error enriching from {file_path.name}: {e}")

            # ── Phase 4: Apply Business Rules for Designations & Hierarchy ──
            logger.info("  [Phase 4] Applying Business Rules for Designations & Hierarchy")
            
            # 1. Leader
            Employee.objects.filter(rm_name='Nitin Mude').update(designation='L')
            nitin = Employee.objects.filter(rm_name='Nitin Mude').first()
            
            # 2. Managers
            managers = ["Harshal Ghatage", "Suhas Tare", "Abhijeet Mane"]
            Employee.objects.filter(rm_name__in=managers).update(designation='M', manager=nitin)
            
            # 3. Mutual Fund Advisors (MA) - those with NULL or empty designation
            # exclude L, M, and L1
            Employee.objects.filter(
                Q(designation__isnull=True) | Q(designation='') | Q(designation='None')
            ).exclude(designation__in=['L', 'M', 'L1']).update(designation='MA')
            
            # 4. Reporting Lines
            # Everyone except Leader should have a manager if possible
            for emp in Employee.objects.exclude(designation='L'):
                if emp.rm_manager_name:
                    mgr = Employee.objects.filter(rm_name__iexact=emp.rm_manager_name).first()
                    if mgr:
                        emp.manager = mgr
                        emp.save()

        logger.info(f"[OK] Loaded {count} Employee records and applied business rules")
        return count
    
    def _find_employee_by_wire_code(self, wire_code):
        """Helper to find Employee by wire code via EmployeeWireCode model"""
        from core.models import EmployeeWireCode, Employee
        if not wire_code:
            return None
        # Exact match
        wc_record = EmployeeWireCode.objects.filter(wire_code=wire_code).first()
        if wc_record:
            return wc_record.employee
        # Case insensitive match
        wc_record = EmployeeWireCode.objects.filter(wire_code__iexact=wire_code).first()
        if wc_record:
            return wc_record.employee
        # Try matching wire_code field on Employee directly
        return Employee.objects.filter(wire_code__iexact=wire_code).first()

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
        client_code_cols = ['Client Code', 'Client_Code', 'Client ID/PAN', 'CLIENTID', 'Client ID', 'Client_ID', 'ClientCode']
        client_name_cols = ['Client Name', 'Client_Name', 'INVESTORN0', 'INV_NAME', 'INVESTOR NAME', 'ClientName']
        rm_name_cols = ['RM Name', 'RM_Name', 'RM', 'RM NAME']
        wire_code_cols = ['WireCode', 'Wire Code', 'wire_code', 'wire code', 'Wire', 'Wire_Code']
        pan_cols = ['PAN NO', 'Client_Pan', 'PAN', 'Client PAN', 'InvPAN', 'Client Pan']
        rm_pan_cols = ['RM_Pan', 'RM PAN', 'RM Pan']
        aum_cols = ['AUM', 'AUM (₹)', 'AUM Amount']
        
        with transaction.atomic():
            for file_path in excel_files:
                try:
                    logger.info(f"  Processing: {file_path.name}")
                    xls = pd.ExcelFile(file_path)
                    
                    for sheet_name in xls.sheet_names:
                        df = pd.read_excel(file_path, sheet_name=sheet_name)
                        df.columns = df.columns.str.strip()
                        
                        client_code_col = self._get_col(df, client_code_cols)
                        pan_col = self._get_col(df, pan_cols)
                        
                        if not client_code_col and not pan_col:
                            continue

                        logger.info(f"    Processing sheet '{sheet_name}' with {len(df)} rows")
                        
                        name_col = self._get_col(df, client_name_cols)
                        rm_col = self._get_col(df, rm_name_cols)
                        wire_col = self._get_col(df, wire_code_cols)
                        rm_pan_col = self._get_col(df, rm_pan_cols)
                        aum_col = self._get_col(df, aum_cols)

                        for idx, row in df.iterrows():
                            try:
                                client_code = str(row.get(client_code_col, '')).strip() if client_code_col else None
                                if not client_code or client_code.lower() == 'nan':
                                    client_code = str(row.get(pan_col, '')).strip() if pan_col else None
                                
                                if not client_code or client_code.lower() == 'nan':
                                    continue
                                
                                client_name = str(row.get(name_col, '')).strip() if name_col and not pd.isna(row.get(name_col)) else None
                                if not client_name or client_name == '-' or client_name.lower() == 'nan':
                                    client_name = f"Client {client_code}"

                                rm_name = str(row.get(rm_col, '')).strip() if rm_col and not pd.isna(row.get(rm_col)) else None
                                wire_code_val = str(row.get(wire_col, '')).strip() if wire_col and not pd.isna(row.get(wire_col)) else None
                                
                                client_pan_val = str(row.get(pan_col, '')).strip() if pan_col and not pd.isna(row.get(pan_col)) else None
                                rm_pan_val = str(row.get(rm_pan_col, '')).strip() if rm_pan_col and not pd.isna(row.get(rm_pan_col)) else None
                                aum_val = self._parse_aum(row.get(aum_col)) if aum_col else Decimal('0')

                                if not rm_name and not wire_code_val:
                                    continue

                                employee = None
                                if wire_code_val and wire_code_val.lower() != 'nan':
                                    employee = self._find_employee_by_wire_code(wire_code_val)
                                
                                if not employee and rm_name and rm_name.lower() != 'nan':
                                    employee = Employee.objects.filter(rm_name__iexact=rm_name).first()
                                
                                final_ma_name = str(row.get('MA_Name', row.get('MA Name', ''))).strip() or None
                                if final_ma_name and final_ma_name.lower() == 'nan':
                                    final_ma_name = None
                                    
                                final_rm_name = rm_name or (employee.rm_name if employee else '')
                                
                                # Title case names for consistency
                                if final_ma_name: final_ma_name = final_ma_name.title()
                                if final_rm_name: final_rm_name = final_rm_name.title()

                                if employee and employee.designation == 'MA':
                                    final_ma_name = employee.rm_name
                                    if employee.manager:
                                        final_rm_name = employee.manager.rm_name
                                    elif employee.rm_manager_name:
                                        final_rm_name = employee.rm_manager_name
                                elif not final_ma_name and rm_name:
                                    ma_emp = Employee.objects.filter(rm_name__iexact=rm_name, designation='MA').first()
                                    if ma_emp:
                                        final_ma_name = ma_emp.rm_name
                                        if ma_emp.manager:
                                            final_rm_name = ma_emp.manager.rm_name
                                        elif ma_emp.rm_manager_name:
                                            final_rm_name = ma_emp.rm_manager_name

                                Client.objects.update_or_create(
                                    client_code=client_code,
                                    defaults={
                                        'client_name': client_name,
                                        'employee': employee,
                                        'wire_code': wire_code_val if wire_code_val and wire_code_val.lower() != 'nan' else None,
                                        'rm_name': final_rm_name,
                                        'ma_name': final_ma_name,
                                        'rm_manager_name': str(row.get('RM_Manager_Name', row.get('RM Manager Name', ''))).strip() or None,
                                        'client_type': str(row.get('Client_Type', row.get('Client Type', ''))).strip() or None,
                                        'city': str(row.get('Client_City', row.get('City', ''))).strip() or None,
                                        'state': str(row.get('Client_State', row.get('State', ''))).strip() or None,
                                        'client_pan': client_pan_val if client_pan_val and client_pan_val.lower() != 'nan' else None,
                                        'rm_pan': rm_pan_val if rm_pan_val and rm_pan_val.lower() != 'nan' else None,
                                        'aum': aum_val,
                                    }
                                )
                                count += 1
                            except Exception as e:
                                continue
                
                except Exception as e:
                    logger.error(f"  Error processing {file_path.name}: {e}")
                    continue
        
        logger.info(f"[OK] Loaded {count} Client records")
        return count
    
    @staticmethod
    def _parse_date(date_val):
        """Parse date from various formats found in Excel/CSV"""
        if pd.isna(date_val) or date_val is None:
            return None

        date_str = str(date_val).strip()
        if not date_str or date_str.lower() == 'nan' or '###' in date_str or date_str == '-':
            return None

        if isinstance(date_val, (datetime, pd.Timestamp)):
            return date_val.date()
        # If it's a number (Excel date)
        if isinstance(date_val, (int, float)):
            try:
                return pd.to_datetime(date_val, unit='D', origin='1899-12-30').date()
            except:
                return None

        # If it's a string
        date_str = str(date_val).strip()
        if not date_str:
            return None
            
        # Try common formats
        formats = [
            '%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y',
            '%d-%b-%Y', '%d-%b-%y', '%b %d, %Y',
            '%Y%m%d', '%d%m%Y'
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        # Try pandas parser as fallback
        try:
            return pd.to_datetime(date_str).date()
        except:
            return None

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
        client_name_cols = ['Client_Name', 'Client Name', 'INVESTORN0', 'INV_NAME', 'ClientName', 'INVESTOR NAME']
        client_code_cols = ['Client Code', 'Client_Code', 'Client ID/PAN', 'CLIENTID', 'ClientCode', 'PAN_NO', 'PAN']
        wire_code_cols = ['WireCode', 'Wire Code', 'wire_code', 'wire code', 'Wire']
        date_cols = ['Date', 'Transaction Date', 'DATE']
        
        with transaction.atomic():
            for file_path in all_files:
                try:
                    logger.info(f"  Processing: {file_path.name}")
                    period = self._extract_period_from_filename(file_path.name)

                    # Clear existing records for this file before re-loading
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
                            
                            wire_col = self._get_col(df, wire_code_cols)
                            client_code_col = self._get_col(df, client_code_cols)
                            rm_col = self._get_col(df, rm_name_cols)
                            client_name_col = self._get_col(df, client_name_cols)
                            date_col = self._get_col(df, date_cols)

                            if not client_code_col and not client_name_col and not wire_col:
                                continue

                            for idx, row in df.iterrows():
                                try:
                                    wire_code_val = str(row.get(wire_col, '')).strip() if wire_col and not pd.isna(row.get(wire_col)) else None
                                    client_code_val = str(row.get(client_code_col, '')).strip() if client_code_col and not pd.isna(row.get(client_code_col)) else None
                                    rm_name = str(row.get(rm_col, '')).strip() if rm_col and not pd.isna(row.get(rm_col)) else None
                                    client_name = str(row.get(client_name_col, '')).strip() if client_name_col and not pd.isna(row.get(client_name_col)) else None
                                    trans_date = self._parse_date(row.get(date_col)) if date_col else None
                                    
                                    # Fallback if date is missing or invalid
                                    if not trans_date and period:
                                        trans_date = self._get_fallback_date_from_period(period)

                                    # Data Lookup/Enrichment
                                    client = None
                                    if client_code_val and client_code_val.lower() != 'nan':
                                        client = Client.objects.filter(client_code=client_code_val).first()
                                    
                                    if not client and client_name and client_name.lower() != 'nan':
                                        client = Client.objects.filter(client_name__iexact=client_name).first()

                                    employee = None
                                    if wire_code_val and wire_code_val.lower() != 'nan':
                                        employee = self._find_employee_by_wire_code(wire_code_val)
                                    
                                    if not employee and client:
                                        employee = client.employee
                                    
                                    if not employee and rm_name and rm_name.lower() != 'nan':
                                        employee = Employee.objects.filter(rm_name__iexact=rm_name).first()

                                    # Fallbacks
                                    if not client_name or client_name.lower() == 'nan':
                                        client_name = client.client_name if client else f"Client {client_code_val}"
                                    
                                    if not rm_name or rm_name.lower() == 'nan':
                                        rm_name = employee.rm_name if employee else (client.rm_name if client else wire_code_val)

                                    if not rm_name or not client_name:
                                        continue

                                    final_ma_name = str(row.get('MA_Name', row.get('MA Name', ''))).strip() or (employee.ma_name if employee else None)
                                    final_rm_name = rm_name
                                    
                                    # If the detected employee is an MA, or the RM name belongs to an MA
                                    if employee and employee.designation == 'MA':
                                        final_ma_name = employee.rm_name
                                        if employee.manager:
                                            final_rm_name = employee.manager.rm_name
                                        elif employee.rm_manager_name:
                                            final_rm_name = employee.rm_manager_name
                                    elif not final_ma_name and rm_name:
                                        ma_emp = Employee.objects.filter(rm_name__iexact=rm_name, designation='MA').first()
                                        if ma_emp:
                                            final_ma_name = ma_emp.rm_name
                                            if ma_emp.manager:
                                                final_rm_name = ma_emp.manager.rm_name
                                            elif ma_emp.rm_manager_name:
                                                final_rm_name = ma_emp.rm_manager_name

                                    SalesRecord.objects.create(
                                        employee=employee,
                                        client=client,
                                        rm_manager_name=str(row.get('RM_Manager_Name', row.get('RM Manager Name', ''))).strip() or (employee.rm_manager_name if employee else None),
                                        rm_name=final_rm_name,
                                        ma_name=final_ma_name,
                                        wire_code=wire_code_val or (client.wire_code if client else None) or (employee.wire_code if employee else None),
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
                                        transaction_date=trans_date
                                    )
                                    count += 1
                                except Exception as e:
                                    continue
                        except Exception as e:
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
        client_name_cols = ['INV_NAME', 'INVESTORN0', 'Client Name', 'Client_Name', 'Investor Name', 'INVESTOR NAME']
        client_code_cols = ['PAN_NO', 'PAN', 'Client Code', 'Client_Code', 'InvPAN', 'INVESTOR PAN']
        brokerage_cols = ['BROKERAGE', 'Total Brokerage', 'Brokerage', 'Brokerage (in Rs.)']
        turnover_cols = ['AMOUNT', 'Total Turnover', 'Turnover', 'Amount (in Rs.)', 'Pur Gross Amount']
        rm_name_cols = ['RM_Name', 'RM Name', 'RM', 'RM NAME']
        wire_code_cols = ['WireCode', 'Wire Code', 'wire_code', 'wire code', 'Wire']
        karvy_date_cols = ['Transaction Date', 'TRANSACTION DATE']
        camp_date_cols = ['Transaction_date', 'TRANSACTION_DATE']
        
        with transaction.atomic():
            for file_path in all_files:
                try:
                    logger.info(f"  Processing: {file_path.name}")
                    period = self._extract_period_from_filename(file_path.name)
                    
                    is_karvy = 'karvy' in file_path.name.lower()
                    is_camp = 'camp' in file_path.name.lower()

                    # Clear existing records for this file before re-loading
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
                            
                            name_col = self._get_col(df, client_name_cols)
                            code_col = self._get_col(df, client_code_cols)
                            rm_col = self._get_col(df, rm_name_cols)
                            wire_col = self._get_col(df, wire_code_cols)
                            brk_col = self._get_col(df, brokerage_cols)
                            trn_col = self._get_col(df, turnover_cols)
                            
                            date_col = None
                            if is_karvy:
                                date_col = self._get_col(df, karvy_date_cols)
                            elif is_camp:
                                date_col = self._get_col(df, camp_date_cols)
                            
                            # Fallback if name based check fails
                            if not date_col:
                                date_col = self._get_col(df, karvy_date_cols + camp_date_cols)

                            if not name_col and not code_col:
                                continue

                            for idx, row in df.iterrows():
                                try:
                                    client_name = str(row.get(name_col, '')).strip() if name_col and not pd.isna(row.get(name_col)) else None
                                    client_code_val = str(row.get(code_col, '')).strip() if code_col and not pd.isna(row.get(code_col)) else None
                                    rm_name = str(row.get(rm_col, '')).strip() if rm_col and not pd.isna(row.get(rm_col)) else None
                                    wire_code_val = str(row.get(wire_col, '')).strip() if wire_col and not pd.isna(row.get(wire_col)) else None
                                    trans_date = self._parse_date(row.get(date_col)) if date_col else None
                                    
                                    # Fallback if date is missing or invalid
                                    if not trans_date and period:
                                        trans_date = self._get_fallback_date_from_period(period)

                                    if not client_name or client_name.lower() == 'nan':
                                        if not client_code_val: continue
                                        client_name = f"Client {client_code_val}"

                                    # Try to link to Client
                                    client = None
                                    if client_code_val and client_code_val.lower() != 'nan':
                                        client = Client.objects.filter(client_code=client_code_val).first()
                                    if not client:
                                        client = Client.objects.filter(client_name__iexact=client_name).first()
                                        
                                    # Try to link to Employee
                                    employee = None
                                    if wire_code_val and wire_code_val.lower() != 'nan':
                                        employee = self._find_employee_by_wire_code(wire_code_val)
                                    
                                    if not employee and client:
                                        employee = client.employee
                                    
                                    if not employee and rm_name and rm_name.lower() != 'nan':
                                        employee = Employee.objects.filter(rm_name__iexact=rm_name).first()

                                    # Metrics
                                    brokerage = row.get(brk_col, 0) if brk_col else 0
                                    turnover = row.get(trn_col, 0) if trn_col else 0

                                    ma_name = None
                                    final_rm_name = rm_name or (client.rm_name if client else None) or (employee.rm_name if employee else None)
                                    
                                    if employee and employee.designation == 'MA':
                                        ma_name = employee.rm_name
                                        # If RM is actually an MA, the RM name should be their manager (L1/M)
                                        if employee.manager:
                                            final_rm_name = employee.manager.rm_name
                                        elif employee.rm_manager_name:
                                            final_rm_name = employee.rm_manager_name
                                            
                                    elif not employee and rm_name:
                                        # If no employee found, but name is in RM column, check if that name belongs to an MA
                                        ma_emp = Employee.objects.filter(rm_name__iexact=rm_name, designation='MA').first()
                                        if ma_emp:
                                            ma_name = ma_emp.rm_name
                                            if ma_emp.manager:
                                                final_rm_name = ma_emp.manager.rm_name
                                            elif ma_emp.rm_manager_name:
                                                final_rm_name = ma_emp.rm_manager_name

                                    SalesRecord.objects.create(
                                        employee=employee,
                                        client=client,
                                        rm_name=final_rm_name,
                                        ma_name=ma_name,
                                        client_name=client_name,
                                        wire_code=wire_code_val or (client.wire_code if client else None) or (employee.wire_code if employee else None),
                                        mf_brokerage=self._safe_decimal(brokerage),
                                        mf_turnover=self._safe_decimal(turnover),
                                        data_source='MF',
                                        period=period,
                                        file_name=file_path.name,
                                        transaction_date=trans_date
                                    )
                                    count += 1
                                except Exception as e:
                                    continue
                        except Exception as e:
                            continue
                
                except Exception as e:
                    logger.error(f"  Error processing {file_path.name}: {e}")
                    continue
        
        logger.info(f"[OK] Loaded {count} MF records")
        return count
    
    @staticmethod
    def _safe_decimal(value):
        """Safely convert value to Decimal without float intermediary"""
        try:
            if pd.isna(value) or value is None or value == '':
                return Decimal('0')
            if isinstance(value, str):
                value = value.replace(',', '').strip()
            return Decimal(str(value))
        except (ValueError, TypeError, ArithmeticError, InvalidOperation) as e:
            return Decimal('0')
    
    @staticmethod
    def _extract_period_from_filename(filename):
        """Extract period info from filename"""
        import re
        fn = filename.lower()
        month_pattern = r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)'
        year_pattern = r'(\d{2,4})'
        month_match = re.search(month_pattern, fn)
        if month_match:
            month = month_match.group(1).capitalize()
            content_after = fn[month_match.end():]
            year_match = re.search(year_pattern, content_after)
            if not year_match:
                content_before = fn[:month_match.start()]
                year_match = re.search(year_pattern, content_before)
            if year_match:
                year = year_match.group(1)
                if len(year) == 2:
                    year = '20' + year
                return f"{month} {year}"
            return f"{month} {datetime.now().year}"
        return None

    @staticmethod
    def _get_fallback_date_from_period(period_str):
        """Convert 'Month YYYY' string to a date object (1st of that month)"""
        if not period_str:
            return None
        try:
            return datetime.strptime(period_str, '%b %Y').date()
        except:
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
        """Build manager relationships using PAN-based mapping"""
        from core.models import Employee
        count = 0
        try:
            employees = {emp.pan_number: emp for emp in Employee.objects.all()}
            mgr_map = getattr(self, '_employee_manager_map', {})
            name_to_pan = {}
            for pan, emp in employees.items():
                if emp.rm_name:
                    name_to_pan[emp.rm_name.lower()] = pan
            for pan, emp in employees.items():
                try:
                    manager = None
                    if pan in mgr_map:
                        mgr_pan = mgr_map[pan]
                        if mgr_pan in employees and mgr_pan != pan:
                            manager = employees[mgr_pan]
                    if not manager and emp.rm_manager_name:
                        mgr_pan = name_to_pan.get(emp.rm_manager_name.lower())
                        if mgr_pan and mgr_pan != pan and mgr_pan in employees:
                            manager = employees[mgr_pan]
                    if manager:
                        emp.manager = manager
                        emp.save()
                        count += 1
                except Exception as e:
                    continue
            logger.info(f"[OK] Built {count} manager relationships")
            return count
        except Exception as e:
            logger.error(f"Error building hierarchy: {e}")
            return 0
    
    def _link_userprofile_to_employee(self):
        """Link UserProfile records to Employee dimension based on wire_code"""
        from core.models import UserProfile, Employee
        count = 0
        try:
            profiles = UserProfile.objects.filter(
                Q(employee__isnull=True) & (Q(wire_code__isnull=False) | Q(user__last_name__isnull=False))
            )
            for profile in profiles:
                try:
                    employee = None
                    if profile.wire_code:
                        employee = self._find_employee_by_wire_code(profile.wire_code)
                    
                    if not employee:
                        # Try name match
                        full_name = profile.user.get_full_name()
                        if full_name:
                            employee = Employee.objects.filter(rm_name__iexact=full_name).first()
                    
                    if employee:
                        profile.employee = employee
                        
                        # Apply role business rules
                        if employee.rm_name == 'Nitin Mude':
                            profile.role = 'L'
                        elif employee.rm_name in ["Harshal Ghatage", "Suhas Tare", "Abhijeet Mane"]:
                            profile.role = 'M'
                        else:
                            profile.role = 'R'
                            
                        profile.save()
                        count += 1
                        logger.info(f"  Linked user {profile.user.username} -> {employee.rm_name} (Role: {profile.role})")
                except Exception as e:
                    continue
            logger.info(f"[OK] Linked {count} UserProfile records")
            return count
        except Exception as e:
            logger.error(f"Error linking UserProfile: {e}")
            return 0

    def _load_aaa_brokerage_facts(self):
        """Load brokerage transaction data into the specialized sales_record_AAA_brokerage table"""
        from core.models import SalesRecordAAABrokerage, Employee, Client
        
        count = 0
        if not self.brokerage_fact_path.exists():
            return count
        
        all_files = list(self.brokerage_fact_path.glob('*.xlsx')) + list(self.brokerage_fact_path.glob('*.csv'))
        
        rm_name_cols = ['RM_Name', 'RM Name', 'RM', 'RM NAME', 'RMName']
        client_name_cols = ['Client_Name', 'Client Name', 'INVESTORN0', 'INV_NAME', 'ClientName', 'INVESTOR NAME']
        client_code_cols = ['Client Code', 'Client_Code', 'Client ID/PAN', 'CLIENTID', 'ClientCode', 'PAN_NO', 'PAN']
        wire_code_cols = ['WireCode', 'Wire Code', 'wire_code', 'wire code', 'Wire']
        date_cols = ['Date', 'Transaction Date', 'DATE']
        
        with transaction.atomic():
            for file_path in all_files:
                try:
                    period = self._extract_period_from_filename(file_path.name)
                    SalesRecordAAABrokerage.objects.filter(file_name=file_path.name).delete()

                    if file_path.suffix.lower() == '.csv':
                        dataframes = [pd.read_csv(file_path)]
                    else:
                        xls = pd.ExcelFile(file_path)
                        dataframes = [pd.read_excel(file_path, sheet_name=sheet) for sheet in xls.sheet_names]
                    
                    for df in dataframes:
                        df.columns = df.columns.str.strip()
                        wire_col = self._get_col(df, wire_code_cols)
                        client_code_col = self._get_col(df, client_code_cols)
                        rm_col = self._get_col(df, rm_name_cols)
                        client_name_col = self._get_col(df, client_name_cols)
                        date_col = self._get_col(df, date_cols)

                        if not client_code_col and not client_name_col and not wire_col:
                            continue

                        for _, row in df.iterrows():
                            try:
                                client_code_val = str(row.get(client_code_col, '')).strip() if client_code_col else None
                                wire_code_val = str(row.get(wire_col, '')).strip() if wire_col and not pd.isna(row.get(wire_col)) else None
                                rm_name = str(row.get(rm_col, '')).strip() if rm_col and not pd.isna(row.get(rm_col)) else None
                                client_name = str(row.get(client_name_col, '')).strip() if client_name_col and not pd.isna(row.get(client_name_col)) else None
                                trans_date = self._parse_date(row.get(date_col)) if date_col else None
                                
                                if not trans_date and period:
                                    trans_date = self._get_fallback_date_from_period(period)

                                client = None
                                if client_code_val and client_code_val.lower() != 'nan':
                                    client = Client.objects.filter(client_code=client_code_val).first()
                                if not client and client_name and client_name.lower() != 'nan':
                                    client = Client.objects.filter(client_name__iexact=client_name).first()

                                employee = None
                                if wire_code_val and wire_code_val.lower() != 'nan':
                                    employee = self._find_employee_by_wire_code(wire_code_val)
                                if not employee and client:
                                    employee = client.employee
                                if not employee and rm_name and rm_name.lower() != 'nan':
                                    employee = Employee.objects.filter(rm_name__iexact=rm_name).first()

                                final_ma_name = str(row.get('MA_Name', row.get('MA Name', ''))).strip() or (employee.ma_name if employee else None)
                                final_rm_name = rm_name or (employee.rm_name if employee else (client.rm_name if client else wire_code_val))
                                
                                if employee and employee.designation == 'MA':
                                    final_ma_name = employee.rm_name
                                    final_rm_name = employee.manager.rm_name if employee.manager else (employee.rm_manager_name or final_rm_name)

                                SalesRecordAAABrokerage.objects.create(
                                    employee=employee,
                                    client=client,
                                    rm_manager_name=str(row.get('RM_Manager_Name', row.get('RM Manager Name', ''))).strip() or (employee.rm_manager_name if employee else None),
                                    rm_name=final_rm_name,
                                    ma_name=final_ma_name,
                                    wire_code=wire_code_val or (client.wire_code if client else None) or (employee.wire_code if employee else None),
                                    client_name=client_name or (client.client_name if client else f"Client {client_code_val}"),
                                    client_pan=client.client_pan if client else None,
                                    client_city=client.city if client else "NO CITY",
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
                                    period=period,
                                    file_name=file_path.name,
                                    transaction_date=trans_date
                                )
                                count += 1
                            except: continue
                except: continue
        return count

    def _load_specialized_mf_facts(self):
        """Load MF transaction data into the specialized sales_record_MF table with specific mappings"""
        from core.models import SalesRecordMF, Employee, Client
        
        count = 0
        if not self.mf_fact_path.exists():
            return count
        
        # Karvy/CAMS mapping requirements:
        # Karvy: "Investor Name", "Broker Code", "GrossBrokerage", "Amount (in Rs.)", "Transaction Date", "InvPAN", "InvCityName"
        # Camp: "Client_Name", "wire_code", "FEE_AMT", "AMOUNT", "Transaction_date", "PAN NO", city: "NO CITY"
        # AAA: "Investor Name", "Main Code", "Brokerage Amount", "Purchase Date", "Sub Code", "ClientPAN"
        
        # Using rglob to find files in subdirectories (like AAA/)
        all_files = list(self.mf_fact_path.rglob('*.xlsx')) + list(self.mf_fact_path.rglob('*.csv'))
        
        with transaction.atomic():
            for file_path in all_files:
                try:
                    period = self._extract_period_from_filename(file_path.name)
                    is_karvy = 'karvy' in file_path.name.lower()
                    is_camp = 'camp' in file_path.name.lower() or 'camp' in str(file_path).lower()
                    is_aaa = 'AAA' in str(file_path)

                    SalesRecordMF.objects.filter(file_name=file_path.name).delete()
                    logger.info(f"  Processing MF File: {file_path.name} (Karvy={is_karvy}, CAMS={is_camp}, AAA={is_aaa})")

                    if file_path.suffix.lower() == '.csv':
                        dataframes = [pd.read_csv(file_path)]
                    else:
                        xls = pd.ExcelFile(file_path)
                        dataframes = [pd.read_excel(file_path, sheet_name=sheet) for sheet in xls.sheet_names]
                    
                    for df in dataframes:
                        df.columns = df.columns.str.strip()
                        
                        # Use self._get_col to find the actual columns in the file
                        id_col = self._get_col(df, ['Transaction ID', 'TRXN_ID', 'TRXN_NO', 'Transaction Number'])
                        name_col = self._get_col(df, ['Investor Name', 'Client_Name', 'INV_NAME', 'INVESTORN0', 'INVESTOR NAME'])
                        wire_col = self._get_col(df, ['Broker Code', 'WireCode', 'wire_code', 'wire code', 'Wire', 'Sub Code'])
                        main_wire_col = self._get_col(df, ['Main Code'])
                        brk_col = self._get_col(df, ['GrossBrokerage', 'FEE_AMT', 'BROKERAGE', 'Total Brokerage', 'Brokerage', 'Brokerage (in Rs.)', 'Brokerage Amount'])
                        trn_col = self._get_col(df, ['Amount (in Rs.)', 'AMOUNT', 'Total Turnover', 'Turnover', 'Pur Gross Amount', 'Brokerage Amount'])
                        date_col = self._get_col(df, ['Transaction Date', 'Transaction_date', 'TRANSACTION DATE', 'TRANSACTION_DATE', 'Purchase Date'])
                        pan_col = self._get_col(df, ['InvPAN', 'PAN NO', 'PAN_NO', 'PAN', 'InvPAN', 'Client_Pan', 'Client PAN', 'ClientPAN'])
                        city_col = self._get_col(df, ['InvCityName', 'City', 'Client_City', 'InvCity'])

                        for i, row in df.iterrows():
                            try:
                                client_pan = str(row.get(pan_col, '')).strip() if pan_col else None
                                if not client_pan or client_pan.lower() == 'nan':
                                    client_pan = "NO PAN"
                                
                                # Metrics (needed for deduplication hash)
                                brokerage = self._safe_decimal(row.get(brk_col, 0))
                                turnover = self._safe_decimal(row.get(trn_col, 0))
                                
                                # Date
                                trans_date = self._parse_date(row.get(date_col)) if date_col else None
                                if not trans_date and period:
                                    trans_date = self._get_fallback_date_from_period(period)

                                wire_code_val = str(row.get(wire_col, '')).strip() if wire_col else None
                                client_name_val = str(row.get(name_col, '')).strip() or None

                                # Transaction ID logic
                                if is_aaa:
                                    # Create a unique 10 character alpha numeric value (deterministic for cross-file deduplication)
                                    unique_str = f"AAA_{client_pan}_{trans_date}_{brokerage}_{wire_code_val}_{client_name_val}"
                                    trxn_id = hashlib.md5(unique_str.encode()).hexdigest()[:10].upper()
                                    
                                    # Deduplication: DO NOT include redundant data
                                    if SalesRecordMF.objects.filter(transaction_id=trxn_id).exists():
                                        continue
                                else:
                                    trxn_id = str(row.get(id_col, '')).strip() if id_col else f"SYN-{file_path.stem[:10]}-{i}"
                                    if (not trxn_id or trxn_id.lower() == 'nan') and not id_col:
                                        trxn_id = f"SYN-{file_path.stem[:10]}-{i}"

                                # Dimensions lookup by PAN
                                client = None
                                if client_pan != "NO PAN":
                                    client = Client.objects.filter(client_pan=client_pan).first()
                                
                                # FALLBACK: if no client by PAN, try by Name (to fix records missing PAN in file but present in dimension)
                                if not client and client_name_val:
                                    client = Client.objects.filter(client_name__iexact=client_name_val).first()
                                    if client and client.client_pan:
                                        client_pan = client.client_pan

                                # RM and Manager Logic
                                if is_aaa:
                                    # Specific lookups for AAA as requested
                                    rm_name = client.rm_name if client else "Nitin Mude"
                                    # lookup rm_manager_name from employee_dimension based on rm_name
                                    emp_for_mgr = Employee.objects.filter(rm_name=rm_name).first()
                                    rm_manager_name = emp_for_mgr.rm_manager_name if emp_for_mgr else None
                                    # lookup city from client_dimension via client_pan
                                    client_city = client.city if client else "NO CITY"
                                    # employee and client FKs
                                    employee = client.employee if client else None
                                    # broker_wire_code is "Main Code"
                                    broker_wire_code_val = str(row.get(main_wire_col, '')).strip() if main_wire_col else None
                                else:
                                    employee = None
                                    if client and client.employee:
                                        employee = client.employee
                                    elif client_pan != "NO PAN":
                                        employee = Employee.objects.filter(pan_number=client_pan).first()

                                    rm_name = "Nitin Mude" # Default as requested
                                    rm_manager_name = None
                                    
                                    if employee:
                                        rm_name = employee.rm_name
                                        rm_manager_name = employee.rm_manager_name
                                    elif client and client.rm_name:
                                        rm_name = client.rm_name
                                        rm_manager_name = client.rm_manager_name
                                    
                                    client_city = str(row.get(city_col, "NO CITY")).strip() if city_col else "NO CITY"
                                    broker_wire_code_val = wire_code_val

                                # Wire code logic for record (use mapped if missing)
                                mapped_wire_code = wire_code_val
                                if not mapped_wire_code or mapped_wire_code.lower() == 'nan':
                                    if client and client.wire_code:
                                        mapped_wire_code = client.wire_code
                                    elif employee and employee.wire_code:
                                        mapped_wire_code = employee.wire_code

                                SalesRecordMF.objects.create(
                                    transaction_id=trxn_id,
                                    client_name=client_name_val or (client.client_name if client else None),
                                    broker_wire_code=broker_wire_code_val,
                                    mf_brokerage=brokerage,
                                    mf_turnover=turnover,
                                    file_name=file_path.name,
                                    transaction_date=trans_date,
                                    period=period,
                                    wire_code=mapped_wire_code,
                                    client_pan=client_pan,
                                    client=client,
                                    employee=employee,
                                    rm_name=rm_name,
                                    rm_manager_name=rm_manager_name,
                                    client_city=client_city
                                )
                                count += 1
                            except Exception as e:
                                if count % 1000 == 0:
                                    logger.error(f"  Error on row {i} of {file_path.name}: {e}")
                                continue
                except Exception as e:
                    logger.error(f"  Critical error processing {file_path.name}: {e}")
                    continue
        return count

    def _load_wealthmagic_clients(self):
        """Load WealthMagic clients from data_files/Client_dim/WealthMagic/"""
        from core.models import ClientWealthMagic, Employee
        count = 0
        path = self.client_dim_path / 'WealthMagic'
        if not path.exists():
            return count
        
        files = list(path.glob('*.xlsx'))
        for file_path in files:
            try:
                df = pd.read_excel(file_path)
                df.columns = df.columns.str.strip()
                
                for _, row in df.iterrows():
                    try:
                        client_code = str(row.get('Client Code', '')).strip()
                        if not client_code or client_code.lower() == 'nan':
                            continue
                            
                        rm_name = str(row.get('RM_Name', '')).strip()
                        emp = Employee.objects.filter(rm_name=rm_name).first()
                        rm_manager = emp.rm_manager_name if emp and emp.rm_manager_name else "Nitin Mude"
                        
                        onboarded = self._parse_date(row.get('Onboarded on'))
                        
                        ClientWealthMagic.objects.update_or_create(
                            client_code=client_code,
                            client_name=str(row.get('Client_Name', '')).strip(),
                            rm_name=rm_name,
                            defaults={
                                'rm_manager_name': rm_manager,
                                'onboarded_on': onboarded,
                                'wire_code': str(row.get('WireCode', '')).strip() if not pd.isna(row.get('WireCode')) else None,
                                'aum': self._safe_decimal(row.get('Aum', 0)),
                                'client_pan': str(row.get('Client_Pan', '')).strip() if not pd.isna(row.get('Client_Pan')) else None,
                                'rm_pan': str(row.get('RM_Pan', '')).strip() if not pd.isna(row.get('RM_Pan')) else None,
                            }
                        )
                        count += 1
                    except: continue
            except: continue
        return count

    def _load_pms_aif_clients(self):
        """Load PMS/AIF clients from data_files/Client_dim/PMS_AIF/"""
        from core.models import ClientPMSAIF, Employee
        count = 0
        path = self.client_dim_path / 'PMS_AIF'
        if not path.exists():
            return count
        
        files = list(path.glob('*.xlsx'))
        for file_path in files:
            try:
                df = pd.read_excel(file_path)
                df.columns = df.columns.str.strip()
                
                for _, row in df.iterrows():
                    try:
                        client_code = str(row.get('Client Code', '')).strip()
                        client_name = str(row.get('Client_Name', '')).strip()

                        # Fallback for missing code to catch all 37 rows
                        if (not client_code or client_code.lower() == 'nan') and client_name:
                            client_code = f"MISSING-{client_name[:10]}"

                        if not client_code or client_code.lower() == 'nan':
                            continue
                            
                        rm_name = str(row.get('RM_Name', '')).strip()
                        emp = Employee.objects.filter(rm_name=rm_name).first()
                        rm_manager = emp.rm_manager_name if emp and emp.rm_manager_name else "Nitin Mude"
                        
                        onboarded = self._parse_date(row.get('Onboarded on'))
                        
                        # PMS/AIF AUM might have "Cr" etc.
                        aum_raw = row.get('AUM (₹)', row.get('Aum', 0))
                        aum_val = self._parse_aum(aum_raw)

                        ClientPMSAIF.objects.update_or_create(
                            client_code=client_code,
                            client_name=str(row.get('Client_Name', '')).strip(),
                            rm_name=rm_name,
                            defaults={
                                'rm_manager_name': rm_manager,
                                'onboarded_on': onboarded,
                                'wire_code': str(row.get('WireCode', '')).strip() if not pd.isna(row.get('WireCode')) else None,
                                'aum': aum_val,
                                'client_pan': str(row.get('Client_Pan', '')).strip() if not pd.isna(row.get('Client_Pan')) else None,
                                'rm_pan': str(row.get('RM_Pan', '')).strip() if not pd.isna(row.get('RM_Pan')) else None,
                                'ma_name': str(row.get('MA_Name', '')).strip() if not pd.isna(row.get('MA_Name')) else None,
                                'ma_pan': str(row.get('MA_PAN', '')).strip() if not pd.isna(row.get('MA_PAN')) else None,
                            }
                        )
                        count += 1
                    except: continue
            except: continue
        return count

    def _load_pms_aif_sales_records(self):
        """Load PMS and AIF sales records from data_files/PMSAIF/"""
        from core.models import SalesRecordPMSAIF, ClientPMSAIF, Employee
        count = 0
        pmsaif_root = self.project_root / 'data_files' / 'PMSAIF'
        if not pmsaif_root.exists():
            return count

        # AIF: "Folio No.", "Investor Name" or "Client Name", "Pan No" or "PAN", "Scheme Name", "Sb Code" or "Broker Code", "AUM", "Final Referral Amt" or "Total Amount", "From Date" or "Date"
        # PMS: "Client code", "Portfolio Name" or "Client Name", "Pan No" or "PAN", "Scheme Name" or "Scheme", "Sb Code", "AUM", "Total" or "Total payable(Including GST)" or "Final Referral Amt", "Inception Date" or "From Date"

        # Folder to type mapping
        sources = [
            (pmsaif_root / 'AIF', 'aif'),
            (pmsaif_root / 'PMS', 'pms')
        ]

        with transaction.atomic():
            for folder, stype in sources:
                if not folder.exists(): continue
                files = list(folder.glob('**/*.csv')) + list(folder.glob('**/*.xlsx'))
                for file_path in files:
                    try:
                        period = self._extract_period_from_filename(file_path.name)
                        SalesRecordPMSAIF.objects.filter(file_name=file_path.name).delete()
                        
                        if file_path.suffix.lower() == '.csv':
                            df = pd.read_csv(file_path)
                        else:
                            df = pd.read_excel(file_path)
                        
                        df.columns = df.columns.str.strip()
                        
                        # Find columns
                        code_cols = ['Folio No.', 'Client code', 'Client Code', 'Folio No']
                        name_cols = ['Investor Name', 'Client Name', 'Portfolio Name', 'Client_Name']
                        pan_cols = ['Pan No', 'PAN', 'PAN No', 'Pan No.']
                        scheme_cols = ['Scheme Name', 'Scheme', 'SCHEME']
                        broker_cols = ['Sb Code', 'Broker Code', 'Broker_Code', 'SB Code']
                        aum_cols = ['AUM', 'Aum']
                        amount_cols = ['Final Referral Amt', 'Total Amount', 'Total', 'Total payable(Including GST)']
                        date_cols = ['From Date', 'Date', 'Inception Date', 'Transaction Date']

                        for _, row in df.iterrows():
                            try:
                                client_pan = str(row.get(self._get_col(df, pan_cols), '')).strip()
                                if not client_pan or client_pan.lower() == 'nan':
                                    client_pan = None
                                
                                # Lookup in client_dimension_PMSAIF
                                client_dim = None
                                if client_pan:
                                    client_dim = ClientPMSAIF.objects.filter(client_pan=client_pan).first()
                                
                                # RM details from dim or employee table
                                rm_pan = client_dim.rm_pan if client_dim else None
                                rm_name = None
                                rm_mgr = None
                                
                                # Attempt lookup by RM PAN if available
                                if rm_pan:
                                    emp = Employee.objects.filter(pan_number=rm_pan).first()
                                    if emp:
                                        rm_name = emp.rm_name
                                        rm_mgr = emp.rm_manager_name
                                
                                # If RM name still missing, try client dimension fallback
                                if not rm_name and client_dim:
                                    rm_name = client_dim.rm_name
                                    rm_mgr = client_dim.rm_manager_name

                                # NEW: Fallback if rm_name is null -> Nitin Mude
                                if not rm_name or rm_name.lower() == 'nan':
                                    rm_name = "Nitin Mude"

                                # NEW: If rm_pan is missing but we have a name (like Bhushan or Nitin), lookup PAN from Employee table
                                if not rm_pan and rm_name:
                                    emp = Employee.objects.filter(rm_name__iexact=rm_name).first()
                                    if emp:
                                        rm_pan = emp.pan_number
                                        rm_mgr = emp.rm_manager_name if not rm_mgr else rm_mgr

                                # Broker code logic
                                broker_code = str(row.get(self._get_col(df, broker_cols), '')).strip()
                                if (not broker_code or broker_code.lower() == 'nan') and rm_pan:
                                    emp = Employee.objects.filter(pan_number=rm_pan).first()
                                    if emp: broker_code = emp.wire_code
                                
                                # AUM logic
                                row_aum = self._safe_decimal(row.get(self._get_col(df, aum_cols), 0))
                                if stype == 'aif':
                                    aif_aum = row_aum
                                    if (not aif_aum or aif_aum == 0) and client_dim:
                                        aif_aum = client_dim.aum
                                    pms_aum = Decimal('0')
                                else:
                                    pms_aum = row_aum
                                    if (not pms_aum or pms_aum == 0) and client_dim:
                                        pms_aum = client_dim.aum
                                    aif_aum = Decimal('0')

                                SalesRecordPMSAIF.objects.create(
                                    client_code=str(row.get(self._get_col(df, code_cols), '')).strip() or None,
                                    client_name=str(row.get(self._get_col(df, name_cols), '')).strip() or None,
                                    client_pan=client_pan,
                                    scheme_name=str(row.get(self._get_col(df, scheme_cols), '')).strip() or None,
                                    broker_code=broker_code if broker_code and broker_code.lower() != 'nan' else None,
                                    type=stype,
                                    rm_pan=rm_pan,
                                    rm_name=rm_name,
                                    rm_manager_name=rm_mgr,
                                    pms_aum=pms_aum,
                                    aif_aum=aif_aum,
                                    total_amount=self._safe_decimal(row.get(self._get_col(df, amount_cols), 0)),
                                    transaction_date=self._parse_date(row.get(self._get_col(df, date_cols))),
                                    file_name=file_path.name,
                                    period=period
                                )
                                count += 1
                            except: continue
                    except Exception as e:
                        logger.error(f"Error loading {file_path}: {e}")
                        continue
        return count

