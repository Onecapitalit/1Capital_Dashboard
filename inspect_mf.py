
import pandas as pd
from pathlib import Path

# Path to the MF fact directory
data_dir = Path(r'c:\Users\HP\Downloads\SalesDashboardProject (2) (1)\SalesDashboardProject\data_files\MF_fact')

brokerage_cols = ['BROKERAGE', 'Total Brokerage', 'Brokerage']
turnover_cols = ['AMOUNT', 'Total Turnover', 'Turnover']

print(f"Searching in: {data_dir}")

for file_path in data_dir.glob('*.xlsx'):
    print(f"\nProcessing: {file_path.name}")
    try:
        xls = pd.ExcelFile(file_path)
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            df.columns = df.columns.str.strip()
            
            # Find columns
            brk_col = next((c for c in brokerage_cols if c in df.columns), None)
            
            if brk_col:
                sheet_sum = df[brk_col].sum()
                print(f"  Sheet: {sheet_name}, Col: {brk_col}, Sum: {sheet_sum}, Count: {len(df)}")
            else:
                print(f"  Sheet: {sheet_name}, Missing brokerage columns. Cols: {list(df.columns[:10])}...")
    except Exception as e:
        print(f"  Error: {e}")
