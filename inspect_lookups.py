
import os
import django
import sys
import pandas as pd
from pathlib import Path

# Add the project directory to sys.path
sys.path.append(r'c:\Users\HP\Downloads\SalesDashboardProject (2) (1)\SalesDashboardProject\SalesDashboard')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SalesDashboard.settings')
django.setup()

from core.models import Employee, Client

# Path to the brokerage fact directory
data_dir = Path(r'c:\Users\HP\Downloads\SalesDashboardProject (2) (1)\SalesDashboardProject\data_files\brokerage_fact')

wire_code_cols = ['WireCode', 'Wire Code', 'wire_code', 'wire code']
client_code_cols = ['Client Code', 'Client_Code', 'Client ID/PAN', 'CLIENTID', 'ClientCode', 'PAN_NO', 'PAN']
brokerage_cols = ['Total Brokerage', 'Brokerage', 'BROKERAGE', 'Sum of Total Brokerage']

total_rows = 0
skipped_no_wire = 0
skipped_no_client = 0
sum_skipped = 0
sum_loaded = 0

for file_path in data_dir.glob('*.xlsx'):
    print(f"Checking {file_path.name}")
    try:
        df = pd.read_excel(file_path)
        df.columns = df.columns.str.strip()
        
        wire_col = next((c for c in wire_code_cols if c in df.columns), None)
        client_col = next((c for c in client_code_cols if c in df.columns), None)
        brk_col = next((c for c in brokerage_cols if c in df.columns), None)
        
        for idx, row in df.iterrows():
            total_rows += 1
            wire_val = str(row.get(wire_col)).strip() if wire_col else None
            client_val = str(row.get(client_col)).strip() if client_col else None
            brk_val = row.get(brk_col, 0)
            
            emp_exists = Employee.objects.filter(wire_code=wire_val).exists() if wire_val else False
            client_exists = Client.objects.filter(client_code=client_val).exists() if client_val else False
            
            if not emp_exists:
                skipped_no_wire += 1
                sum_skipped += brk_val
            elif not client_exists:
                skipped_no_client += 1
                sum_skipped += brk_val
            else:
                sum_loaded += brk_val
                
    except Exception as e:
        print(f"Error {file_path.name}: {e}")

print(f"\nTotal Rows: {total_rows}")
print(f"Skipped (No WireCode Match): {skipped_no_wire}")
print(f"Skipped (No ClientCode Match): {skipped_no_client}")
print(f"Total Sum Loaded: {sum_loaded}")
print(f"Total Sum Skipped: {sum_skipped}")
print(f"Grand Total: {sum_loaded + sum_skipped}")
