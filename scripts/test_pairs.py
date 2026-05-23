import urllib.request
import json
import datetime

def test():
    url = 'https://fapi.binance.com/fapi/v1/exchangeInfo'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        print('Error fetching exchangeInfo:', e)
        return

    symbols = {s['symbol']: s for s in data['symbols']}
    candidates = [
        'BNBUSDT', 'MATICUSDT', 'POLUSDT', '1000SHIBUSDT', '1000PEPEUSDT',
        'WIFUSDT', 'FETUSDT', 'RNDRUSDT', 'RENDERUSDT', 'AAVEUSDT',
        'MKRUSDT', 'INJUSDT', 'HBARUSDT', 'FILUSDT'
    ]

    for sym in candidates:
        if sym not in symbols:
            print(sym, 'NOT LISTED')
            continue
        s = symbols[sym]
        ts = s.get('onboardDate', 0) / 1000.0
        od = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).date() if ts else '?'
        print(sym, 'status=' + s['status'], 'contract=' + s['contractType'], 'onboard=' + str(od))

if __name__ == '__main__':
    test()
