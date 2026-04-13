
import pandas as pd
from pathlib import Path

mf_fact_path = Path('data_files/MF_fact')
for file_path in mf_fact_path.glob('*.xlsx'):
    try:
        df = pd.read_excel(file_path)
        col = 'TRXN_ID' if 'TRXN_ID' in df.columns else ('TRXN_NO' if 'TRXN_NO' in df.columns else None)
        if col:
            print(f"{file_path.name}: Unique {col}: {df[col].nunique()} / {len(df)}")
        else:
            print(f"{file_path.name}: No TRXN_ID/TRXN_NO found, total rows {len(df)}")
    except Exception as e:
        print(f"Error: {e}")
