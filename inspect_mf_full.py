
import pandas as pd
from pathlib import Path

file_path = Path(r'c:\Users\HP\Downloads\SalesDashboardProject (2) (1)\SalesDashboardProject\data_files\MF_fact\Karvy-oct25.xlsx')

try:
    df = pd.read_excel(file_path)
    df.columns = df.columns.str.strip()
    print("Columns:", list(df.columns))
    print("\nSums of potential brokerage columns:")
    for col in df.columns:
        if df[col].dtype in ['float64', 'int64']:
            print(f"  {col}: {df[col].sum():,.2f}")
except Exception as e:
    print(f"Error: {e}")
