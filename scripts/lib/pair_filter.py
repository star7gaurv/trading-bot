import json
import os
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

def filter_pairs_for_timerange(base_config_path: str, train_start: datetime, output_dir: str = '/home/ubuntu/var/www/html/trade/freqtrade/user_data') -> str:
    base_path = Path(base_config_path)
    if not base_path.exists():
        raise FileNotFoundError(f'Config file not found: {base_config_path}')
        
    with open(base_config_path, 'r') as f:
        config = json.load(f)
        
    whitelist = config.get('exchange', {}).get('pair_whitelist', [])
    if not whitelist:
        return base_path.name
        
    filtered_whitelist = []
    cutoff_date = train_start - timedelta(days=95)
    data_dir = Path('/home/ubuntu/var/www/html/trade/freqtrade/user_data/data/binance/futures')
    
    for pair in whitelist:
        feather_name = pair.replace('/', '_').replace(':', '_') + '-1d-futures.feather'
        feather_path = data_dir / feather_name
        
        keep = True
        if not feather_path.exists():
            print(f'[pair_filter] Filtered out {pair} - daily feather file {feather_name} does not exist.')
            keep = False
        else:
            try:
                df = pd.read_feather(feather_path)
                if df.empty or 'date' not in df.columns:
                    print(f'[pair_filter] Filtered out {pair} - feather file empty or invalid.')
                    keep = False
                else:
                    min_date = df['date'].min()
                    if pd.notna(min_date):
                        if hasattr(min_date, 'to_pydatetime'):
                            min_date_dt = min_date.to_pydatetime()
                        else:
                            min_date_dt = pd.to_datetime(min_date).to_pydatetime()
                            
                        if min_date_dt.tzinfo is not None:
                            min_date_dt = min_date_dt.replace(tzinfo=None)
                            
                        if min_date_dt > cutoff_date:
                            print(f'[pair_filter] Filtered out {pair} - data starts {min_date_dt.strftime("%Y-%m-%d")} (cutoff {cutoff_date.strftime("%Y-%m-%d")})')
                            keep = False
                    else:
                        print(f'[pair_filter] Filtered out {pair} - earliest date in feather is NaN.')
                        keep = False
            except Exception as e:
                print(f'[pair_filter] Error reading feather for {pair}, filtering out: {e}')
                keep = False
                
        if keep:
            filtered_whitelist.append(pair)
            
    if len(filtered_whitelist) < len(whitelist):
        config['exchange']['pair_whitelist'] = filtered_whitelist
        temp_name = f'tmp_wf_config_{int(datetime.now().timestamp())}.json'
        temp_path = Path(output_dir) / temp_name
        with open(temp_path, 'w') as f:
            json.dump(config, f, indent=2)
        print(f'[pair_filter] Generated filtered config with {len(filtered_whitelist)}/{len(whitelist)} pairs: {temp_name}')
        return temp_name
    else:
        print(f'[pair_filter] All {len(whitelist)} pairs have adequate historical data.')
        return base_path.name
