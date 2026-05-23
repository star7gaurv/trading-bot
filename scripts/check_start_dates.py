import pandas as pd
import glob
from pathlib import Path

def check():
    path = '/home/ubuntu/var/www/html/trade/freqtrade/user_data/data/binance/futures/*-1d-futures.feather'
    files = glob.glob(path)
    results = []
    for f in sorted(files):
        try:
            df = pd.read_feather(f)
            min_date = df['date'].min()
            max_date = df['date'].max()
            num_rows = len(df)
            results.append((Path(f).name, min_date, max_date, num_rows))
        except Exception as e:
            print(f"Error reading {f}: {e}")
    
    print(f"{'File Name':50s} | {'Earliest Date':19s} | {'Latest Date':19s} | {'Rows'}")
    print("-" * 100)
    for r in results:
        print(f"{r[0]:50s} | {str(r[1])[:19]} | {str(r[2])[:19]} | {r[3]}")

if __name__ == '__main__':
    check()
