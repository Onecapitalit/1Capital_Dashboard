
import pandas as pd
from pathlib import Path

file_path = Path(r'c:\Users\HP\Downloads\SalesDashboardProject (2) (1)\SalesDashboardProject\data_files\brokerage_fact\F3338Y(Jan 26 brkg).xlsx')

try:
    df = pd.read_excel(file_path)
    df.columns = df.columns.str.strip()
    print("Columns:", list(df.columns))
    print("\nFirst 5 rows:")
    # Print only relevant columns to keep it readable
    cols_to_print = ['Client Code', 'WireCode', 'Cash', 'Futures', 'Options', 'Currency', 'Commodity', 'Total Brokerage']
    cols_to_print = [c for c in cols_to_print if c in df.columns]
    print(df[cols_to_print].head())
    
    # Check if Total Brokerage = Cash + Futures + Options + Currency + Commodity
    segments = ['Cash', 'Futures', 'Options', 'Currency', 'Commodity']
    seg_cols = [c for c in segments if c in df.columns]
    if seg_cols:
        sum_segments = df[seg_cols].sum(axis=1)
        mismatch = df[~((sum_segments - df['Total Brokerage']).abs() < 0.01)]
        if not mismatch.empty:
            print(f"\nFound {len(mismatch)} rows where sum of segments != Total Brokerage")
            print("Sample mismatch:")
            print(mismatch[cols_to_print + ['Calculated Sum']].assign(Calculated_Sum=sum_segments).head())
        else:
            print("\nTotal Brokerage perfectly matches the sum of segments.")
except Exception as e:
    print(f"Error: {e}")
