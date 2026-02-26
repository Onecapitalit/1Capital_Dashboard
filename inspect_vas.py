
import pandas as pd
from pathlib import Path

# Path to the brokerage fact directory
data_dir = Path(r'c:\Users\HP\Downloads\SalesDashboardProject (2) (1)\SalesDashboardProject\data_files\brokerage_fact')

brokerage_cols = ['Total Brokerage']
vas_cols = ['Total VAS Subscription']

total_brk = 0
total_vas = 0

for file_path in data_dir.glob('*.xlsx'):
    try:
        df = pd.read_excel(file_path)
        df.columns = df.columns.str.strip()
        
        brk_col = next((c for c in brokerage_cols if c in df.columns), None)
        vas_col = next((c for c in vas_cols if c in df.columns), None)
        
        if brk_col:
            total_brk += df[brk_col].sum()
        if vas_col:
            total_vas += df[vas_col].sum()
    except Exception as e:
        print(f"Error {file_path.name}: {e}")

print(f"Total Brokerage: {total_brk}")
print(f"Total VAS Subscription: {total_vas}")
print(f"Combined: {total_brk + total_vas}")
