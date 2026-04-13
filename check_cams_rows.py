
import pandas as pd
from pathlib import Path

mf_fact_path = Path('data_files/MF_fact')
for file_path in mf_fact_path.glob('*.xlsx'):
    try:
        df = pd.read_excel(file_path)
        print(f"{file_path.name}: {len(df)}")
    except Exception as e:
        print(f"Error: {e}")
