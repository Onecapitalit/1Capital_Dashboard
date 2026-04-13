
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

from core.models import SalesRecord
from django.db.models import Sum

def validate():
    print("="*80)
    print("VALIDATING Q1 2026 DATA (Jan, Feb, Mar)")
    print("="*80)
    
    project_root = Path(__file__).resolve().parent
    data_dir = project_root / 'data_files' / 'brokerage_fact'
    
    # 1. Calculate totals from Excel files
    excel_total = Decimal('0')
    excel_rows = 0
    
    brokerage_cols = ['Sum of Total Brokerage', 'Total Brokerage', 'Brokerage', 'BROKERAGE', 'TotalBrokerage']
    
    print("\n[1/2] Reading Excel files from brokerage_fact...")
    for file_path in data_dir.glob('*.xlsx'):
        try:
            xls = pd.ExcelFile(file_path)
            file_rows = 0
            file_sum = Decimal('0')
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                df.columns = df.columns.str.strip()
                
                brk_col = next((c for c in brokerage_cols if c in df.columns), None)
                if brk_col:
                    # Filter out NaN and convert to string for Decimal safely
                    valid_vals = df[brk_col].dropna()
                    sheet_sum = sum(Decimal(str(v)) for v in valid_vals)
                    file_sum += sheet_sum
                    file_rows += len(df)
            
            print(f"      {file_path.name:30}: {file_rows:5} rows, Sum: Rs.{file_sum:,.2f}")
            excel_total += file_sum
            excel_rows += file_rows
        except Exception as e:
            print(f"      Error reading {file_path.name}: {e}")
            
    # 2. Query totals from Database
    print("\n[2/2] Querying database for BROKERAGE data...")
    db_total = SalesRecord.objects.filter(data_source='BROKERAGE').aggregate(
        total=Sum('total_brokerage')
    )['total'] or Decimal('0')
    db_rows = SalesRecord.objects.filter(data_source='BROKERAGE').count()
    
    print(f"      Database Total Rows: {db_rows}")
    print(f"      Database Total Sum : Rs.{db_total:,.2f}")
    
    # 3. Comparison
    print("\n" + "-"*80)
    print("SUMMARY COMPARISON (Brokerage Fact)")
    print("-"*80)
    print(f"Metric          | Excel Files     | Database        | Difference")
    print(f"Rows            | {excel_rows:15} | {db_rows:15} | {excel_rows - db_rows:15}")
    print(f"Total Brokerage | Rs.{float(excel_total):12,.2f} | Rs.{float(db_total):12,.2f} | Rs.{float(excel_total - db_total):12,.2f}")
    
    if abs(excel_total - db_total) < 0.01 and excel_rows == db_rows:
        print("\n[SUCCESS] Database matches Excel totals exactly!")
    else:
        print("\n[WARNING] Discrepancy detected. Check for duplicate loads or skipped rows.")
    print("="*80)

if __name__ == '__main__':
    validate()
