from freqtrade.strategy import stoploss_from_open

res1 = stoploss_from_open(-0.02, current_profit=0.01, is_short=False)
res2 = stoploss_from_open(-0.02, current_profit=-0.01, is_short=False)
print(f"res1 (profit 1%): {res1}")
print(f"res2 (loss 1%): {res2}")
