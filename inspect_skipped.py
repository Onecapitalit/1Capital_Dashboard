
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

print("Skipped Rows Inspection:")

for file_path in data_dir.glob('*.xlsx'):
    try:
        df = pd.read_excel(file_path)
        df.columns = df.columns.str.strip()
        
        wire_col = next((c for c in wire_code_cols if c in df.columns), None)
        client_col = next((c for c in client_code_cols if c in df.columns), None)
        brk_col = next((c for c in brokerage_cols if c in df.columns), None)
        
        for idx, row in df.iterrows():
            wire_val = str(row.get(wire_col)).strip() if wire_col else None
            client_val = str(row.get(client_col)).strip() if client_col else None
            brk_val = row.get(brk_col, 0)
            
            emp_exists = Employee.objects.filter(wire_code=wire_val).exists() if wire_val else False
            client_exists = Client.objects.filter(client_code=client_val).exists() if client_val else False
            
            if not emp_exists or not client_exists:
                reason = "No WireCode Match" if not emp_exists else "No ClientCode Match"
                print(f"File: {file_path.name:25} | Row: {idx:3} | Code: {wire_val:10} | Client: {client_val:10} | Brk: {brk_val:10.2f} | Reason: {reason}")
                
    except Exception as e:
        print(f"Error {file_path.name}: {e}")
