import pandas as pd
from pathlib import Path

_CSV_PATH = Path(__file__).resolve().parent / "한국도로공사_교통사고통계_20241231.csv"

class DoroReader:
    def __init__(self):
        pass

    
    def get_data(self):
        df = pd.read_csv(_CSV_PATH,encoding="cp949")
        return df.iloc[[1]].astype(object).where(df.iloc[[1]].notna(), None)

