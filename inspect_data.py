
import pandas as pd
from pathlib import Path

# Path to the brokerage fact directory
data_dir = Path(r'c:\Users\HP\Downloads\SalesDashboardProject (2) (1)\SalesDashboardProject\data_files\brokerage_fact')

brokerage_cols = ['Sum of Total Brokerage', 'Total Brokerage', 'Brokerage', 'BROKERAGE', 'TotalBrokerage']

total_rows = 0
total_sum = 0

for file_path in data_dir.glob('*.xlsx'):
    try:
        xls = pd.ExcelFile(file_path)
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            total_rows += len(df)
            
            df.columns = df.columns.str.strip()
            brk_col = next((c for c in brokerage_cols if c in df.columns), None)
            if brk_col:
                total_sum += df[brk_col].sum()
    except Exception as e:
        print(f"Error {file_path.name}: {e}")

print(f"Total rows: {total_rows}")
print(f"Total sum: {total_sum}")
