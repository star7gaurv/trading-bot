import pandas as pd
import json

df = pd.read_feather('freqtrade/user_data/models/finbuddy_v19_asym_1778575138/sub-train-BTC_USDT_USDT-20240101_20250101-0.feather')
print(df.isnull().sum())
