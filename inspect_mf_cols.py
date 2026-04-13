
import pandas as pd
from pathlib import Path

mf_fact_path = Path('data_files/MF_fact')
for file_path in list(mf_fact_path.glob('*.xlsx')) + list(mf_fact_path.glob('*.csv')):
    print(f"\nFile: {file_path.name}")
    try:
        if file_path.suffix.lower() == '.csv':
            df = pd.read_csv(file_path, nrows=5)
        else:
            df = pd.read_excel(file_path, nrows=5)
        print("Columns:", df.columns.tolist())
    except Exception as e:
        print(f"Error: {e}")
