
import os
import sys
import django
import pandas as pd
from pathlib import Path
from decimal import Decimal

# Setup Django
BASE_DIR = Path(__file__).resolve().parent / 'SalesDashboard'
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SalesDashboard.settings')
django.setup()

from core.models import Employee, Client, SalesRecord, EmployeeWireCode
from core.data_pipeline import DataPipeline
from django.db import transaction

def repair():
    print("="*80)
    print("REPAIRING CLIENT DIMENSION (F338y + F447P + FY746)")
    print("="*80)
    
    dp = DataPipeline()
    
    with transaction.atomic():
        # Step 1: Clear current data
        print("\n[1/4] Clearing Client and SalesRecord data...")
        SalesRecord.objects.all().delete()
        Client.objects.all().delete()
        print("      Cleared existing records")
        
        # Step 2: Load F447P and FY746 from their xlsx files
        print("\n[2/4] Loading F447P and FY746 Client files...")
        dp._load_client_dimension()
        
        # Step 3: Load F338y by "Discovering" from brokerage data
        print("\n[3/4] Auto-discovering F338y Clients from Brokerage data...")
        # Mar 26 file
        df_mar = pd.read_excel('data_files/brokerage_fact/F338Y (Mar 26 brkg).xlsx')
        # Jan 26 file
        df_jan = pd.read_excel('data_files/brokerage_fact/F3338Y(Jan 26 brkg).xlsx')
        # Feb 26 file
        df_feb = pd.read_excel('data_files/brokerage_fact/f338y(feb 26 brkg).xlsx')
        
        f338y_mapping = pd.concat([
            df_mar[['Client Code', 'WireCode']], 
            df_jan[['Client Code', 'WireCode']],
            df_feb[['Client Code', 'WireCode']]
        ]).drop_duplicates().dropna()
        
        # Try to find AUM/PAN in F338y client file if it exists
        f338y_client_file = Path('data_files/Client_dim/F338y client code wise RM.xlsx')
        f338y_meta = {}
        if f338y_client_file.exists():
            print(f"      Found F338y meta file: {f338y_client_file.name}")
            df_meta = pd.read_excel(f338y_client_file)
            df_meta.columns = df_meta.columns.str.strip()
            
            c_code_col = dp._get_col(df_meta, ['Client Code', 'Client_Code', 'Client ID/PAN'])
            c_pan_col = dp._get_col(df_meta, ['Client_Pan', 'Client PAN', 'PAN', 'InvPAN'])
            r_pan_col = dp._get_col(df_meta, ['RM_Pan', 'RM PAN', 'RM Pan'])
            aum_col = dp._get_col(df_meta, ['AUM', 'AUM (₹)', 'AUM Amount'])
            c_name_col = dp._get_col(df_meta, ['Client Name', 'Client_Name', 'INVESTOR NAME'])

            if c_code_col:
                for _, mrow in df_meta.iterrows():
                    mcode = str(mrow[c_code_col]).strip()
                    f338y_meta[mcode] = {
                        'client_pan': str(mrow[c_pan_col]).strip() if c_pan_col and not pd.isna(mrow[c_pan_col]) else None,
                        'rm_pan': str(mrow[r_pan_col]).strip() if r_pan_col and not pd.isna(mrow[r_pan_col]) else None,
                        'aum': dp._parse_aum(mrow[aum_col]) if aum_col else Decimal('0'),
                        'client_name': str(mrow[c_name_col]).strip() if c_name_col and not pd.isna(mrow[c_name_col]) else None,
                    }

        added_count = 0
        for _, row in f338y_mapping.iterrows():
            code = str(row['Client Code']).strip()
            wire = str(row['WireCode']).strip()
            
            if not code or code.lower() == 'nan': continue
            
            # Find the RM for this wire code
            employee = dp._find_employee_by_wire_code(wire)
            
            meta = f338y_meta.get(code, {})
            
            Client.objects.update_or_create(
                client_code=code,
                defaults={
                    'client_name': meta.get('client_name') or f"Client {code}",
                    'employee': employee,
                    'wire_code': wire,
                    'rm_name': employee.rm_name if employee else wire,
                    'client_pan': meta.get('client_pan'),
                    'rm_pan': meta.get('rm_pan'),
                    'aum': meta.get('aum', Decimal('0')),
                }
            )
            added_count += 1
            
        print(f"      Discovered and added {added_count} F338y clients")
        
        # Step 4: Reload Sales Records
        print("\n[4/4] Reloading all Sales Records (linking them to newly discovered clients)...")
        dp._load_brokerage_facts()
        dp._load_mf_facts()
        
    print("\n" + "="*80)
    print("CLIENT DIMENSION REPAIR COMPLETED")
    print(f"Total Clients: {Client.objects.count()}")
    print(f"Total SalesRecords: {SalesRecord.objects.count()}")
    print("="*80)

if __name__ == '__main__':
    repair()
