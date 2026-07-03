import os
import re
import glob
import pandas as pd
import numpy as np
from datetime import datetime, time, date

class DataProvider:
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        # Cache for loaded and resampled data: (date_str, asset_type, filename) -> DataFrame
        self.cache = {}
        # List of 1-second times from 09:15:00 to 15:30:00
        self.time_index = [t.strftime("%H:%M:%S") for t in pd.date_range("09:15:00", "15:30:00", freq="1s")]
        
    def _parse_filename(self, filename):
        name = filename.replace('.csv', '')
        if name.startswith('BANKNIFTY'):
            underlier = 'BANKNIFTY'
            expiry = name[9:15]
            rest = name[15:]
        elif name.startswith('FINNIFTY'):
            underlier = 'FINNIFTY'
            expiry = name[8:14]
            rest = name[14:]
        elif name.startswith('MIDCPNIFTY'):
            underlier = 'MIDCPNIFTY'
            expiry = name[10:16]
            rest = name[16:]
        elif name.startswith('NIFTY'):
            underlier = 'NIFTY'
            expiry = name[5:11]
            rest = name[11:]
        else:
            return None
        
        m = re.match(r'^(\d+(?:\.\d+)?)(CE|PE)$', rest)
        if m:
            strike = float(m.group(1))
            option_type = m.group(2)
            return {
                'underlier': underlier,
                'expiry': expiry,
                'strike': strike,
                'option_type': option_type,
                'symbol': name
            }
        return None

    def get_date_folders(self):
        folders = sorted(glob.glob(os.path.join(self.data_dir, "NSE_*")))
        return folders

    def scan_options_for_date(self, date_folder):
        options_dir = os.path.join(date_folder, "Options")
        if not os.path.exists(options_dir):
            return {}, []

        files = os.listdir(options_dir)
        mapping = {}
        parsed_list = []
        
        for f in files:
            parsed = self._parse_filename(f)
            if parsed:
                parsed['filepath'] = os.path.join(options_dir, f)
                # Key: (underlier, expiry_str, strike, option_type)
                key = (parsed['underlier'], parsed['expiry'], parsed['strike'], parsed['option_type'])
                mapping[key] = parsed['filepath']
                parsed_list.append(parsed)
                
        return mapping, parsed_list

    def get_closest_expiry(self, parsed_list, underlier, trading_date):
        # trading_date is datetime.date object
        underlier_opts = [p for p in parsed_list if p['underlier'] == underlier]
        if not underlier_opts:
            return None
            
        unique_exp_strs = list(set([p['expiry'] for p in underlier_opts]))
        exp_dates = []
        for exp in unique_exp_strs:
            try:
                d = datetime.strptime(exp, "%y%m%d").date()
                exp_dates.append((d, exp))
            except ValueError:
                continue
                
        # Filter for expiries >= trading_date
        valid_expiries = [item for item in exp_dates if item[0] >= trading_date]
        if not valid_expiries:
            return None
            
        # Get the minimum (closest)
        valid_expiries.sort(key=lambda x: x[0])
        return valid_expiries[0][1] # Return the expiry string (YYMMDD)

    def load_futures_data(self, date_folder, underlier):
        # Key for cache
        date_str = os.path.basename(date_folder).split("_")[1]
        cache_key = (date_str, 'futures', underlier)
        if cache_key in self.cache:
            return self.cache[cache_key]
            
        futures_file = os.path.join(date_folder, "Futures (Continuous)", f"{underlier}-I.csv")
        if not os.path.exists(futures_file):
            raise FileNotFoundError(f"Futures file not found: {futures_file}")
            
        df = pd.read_csv(futures_file, header=None, names=['date', 'time', 'price', 'volume', 'oi'])
        df_resampled = self._resample_dataframe(df)
        self.cache[cache_key] = df_resampled
        return df_resampled

    def load_option_data(self, filepath, cache_key):
        if cache_key in self.cache:
            return self.cache[cache_key]
            
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Option file not found: {filepath}")
            
        df = pd.read_csv(filepath, header=None, names=['date', 'time', 'price', 'volume', 'oi'])
        df_resampled = self._resample_dataframe(df)
        self.cache[cache_key] = df_resampled
        return df_resampled

    def _resample_dataframe(self, df):
        # Remove duplicate times by taking the last entry (standard tick close behavior)
        df_grouped = df.groupby('time').agg({
            'price': 'last',
            'volume': 'sum',
            'oi': 'last'
        })
        # Reindex to complete 1-second grid
        df_resampled = df_grouped.reindex(self.time_index)
        # Forward fill prices and OI, and backward fill if there are NaNs at the start
        df_resampled['price'] = df_resampled['price'].ffill().bfill()
        df_resampled['volume'] = df_resampled['volume'].fillna(0)
        df_resampled['oi'] = df_resampled['oi'].ffill().bfill()
        
        # Keep prices as numpy array for fast index lookup
        return {
            'prices': df_resampled['price'].values,
            'oi': df_resampled['oi'].values,
            'df': df_resampled
        }

    def clear_cache(self):
        self.cache.clear()
