import os
import xml.etree.ElementTree as ET
import numpy as np
from datetime import datetime

class BaseStrategy:
    def __init__(self):
        pass
        
    def on_day_start(self, date_str, trading_date, data_provider):
        """
        Called at the start of each trading day.
        """
        pass
        
    def on_second(self, ts_idx, time_str, data_provider, portfolio):
        """
        Called at every second during the trading day.
        """
        pass
        
    def on_day_end(self, ts_idx, time_str, data_provider, portfolio):
        """
        Called at the end of each trading day.
        """
        pass

class XMLStrategy(BaseStrategy):
    def __init__(self, xml_path):
        super().__init__()
        self.xml_path = xml_path
        self.name = ""
        self.description = ""
        self.underliers = []
        self.expiry_selection = "closest"
        self.strike_selection = "closest_to_futures"
        self.option_types = []
        self.action = "BUY"
        self.max_position = 1
        self.exit_on_strike_change = False
        self.day_end_time = "15:30:00"
        
        self.parse_xml()
        
        # State variables updated per day
        self.expiry_strs = {}      # underlier -> expiry_str for the day
        self.available_strikes = {} # underlier -> sorted list of strikes
        self.opt_files_map = {}    # underlier -> mapping dictionary
        
        # Positions state tracking
        # underlier -> currently held strike
        self.held_strike = {}
        # underlier -> dict of symbol -> qty
        self.held_symbols = {}

    def parse_xml(self):
        if not os.path.exists(self.xml_path):
            raise FileNotFoundError(f"XML strategy file not found: {self.xml_path}")
            
        tree = ET.parse(self.xml_path)
        root = tree.getroot()
        
        self.name = root.attrib.get('name', 'XMLStrategy')
        self.description = root.attrib.get('description', '')
        
        # Universe parsing
        universe_node = root.find('Universe')
        if universe_node is not None:
            self.underliers = [u.text for u in universe_node.findall('Underlier')]
            exp_node = universe_node.find('ExpirySelection')
            if exp_node is not None:
                self.expiry_selection = exp_node.text
                
        # Execution parsing
        exec_node = root.find('Execution')
        if exec_node is not None:
            strike_node = exec_node.find('StrikeSelection')
            if strike_node is not None:
                self.strike_selection = strike_node.text
                
            opt_types_node = exec_node.find('OptionTypes')
            if opt_types_node is not None:
                self.option_types = [ot.text for ot in opt_types_node.findall('OptionType')]
                
            action_node = exec_node.find('Action')
            if action_node is not None:
                self.action = action_node.text
                
            max_pos_node = exec_node.find('MaxPositionPerInstrument')
            if max_pos_node is not None:
                self.max_pos = int(max_pos_node.text)
                
        # Triggers parsing
        triggers_node = root.find('Triggers')
        if triggers_node is not None:
            exit_conds = triggers_node.findall('ExitCondition')
            for ec in exit_conds:
                if ec.attrib.get('type') == 'strike_change':
                    self.exit_on_strike_change = True
                    
            day_end_node = triggers_node.find('DayEndExit')
            if day_end_node is not None:
                self.day_end_time = day_end_node.attrib.get('time', '15:30:00')

    def on_day_start(self, date_str, trading_date, data_provider):
        self.expiry_strs.clear()
        self.available_strikes.clear()
        self.opt_files_map.clear()
        self.held_strike.clear()
        self.held_symbols.clear()
        
        # Scan options directory and pre-parse
        mapping, parsed_list = data_provider.scan_options_for_date(os.path.join(data_provider.data_dir, f"NSE_{date_str}"))
        
        for underlier in self.underliers:
            expiry_str = data_provider.get_closest_expiry(parsed_list, underlier, trading_date)
            if not expiry_str:
                continue
                
            self.expiry_strs[underlier] = expiry_str
            
            # Filter options for this underlier and expiry, group by strike to ensure we have both CE and PE
            underlier_expiry_opts = [p for p in parsed_list if p['underlier'] == underlier and p['expiry'] == expiry_str]
            
            # Find strikes that have both option types requested
            strike_groups = {}
            for opt in underlier_expiry_opts:
                strike_groups.setdefault(opt['strike'], []).append(opt['option_type'])
                
            valid_strikes = []
            for strike, types in strike_groups.items():
                # Check if all requested option types exist for this strike
                if all(t in types for t in self.option_types):
                    valid_strikes.append(strike)
                    
            valid_strikes.sort()
            self.available_strikes[underlier] = np.array(valid_strikes)
            self.opt_files_map[underlier] = mapping
            
            self.held_strike[underlier] = None
            self.held_symbols[underlier] = {}

    def _find_closest_strike(self, underlier, future_price):
        strikes = self.available_strikes.get(underlier)
        if strikes is None or len(strikes) == 0:
            return None
            
        # Binary search for closest strike
        idx = np.searchsorted(strikes, future_price)
        if idx == 0:
            return strikes[0]
        elif idx == len(strikes):
            return strikes[-1]
        else:
            d1 = abs(strikes[idx] - future_price)
            d2 = abs(strikes[idx-1] - future_price)
            return strikes[idx] if d1 < d2 else strikes[idx-1]

    def on_second(self, ts_idx, time_str, data_provider, portfolio):
        for underlier in self.underliers:
            if underlier not in self.expiry_strs or underlier not in self.available_strikes:
                continue
                
            # Get current futures price
            try:
                fut_data = data_provider.load_futures_data(
                    os.path.join(data_provider.data_dir, f"NSE_{data_provider.cache.get('current_date_str', '')}"), 
                    underlier
                )
                fut_price = fut_data['prices'][ts_idx]
                import numpy as np
                if np.isnan(fut_price):
                    raise ValueError("Futures price is NaN")
            except Exception:
                continue
                
            # Get closest strike
            closest_strike = self._find_closest_strike(underlier, fut_price)
            if closest_strike is None:
                continue
                
            held_s = self.held_strike[underlier]
            
            # Scenario 1: No position held yet - enter position
            if held_s is None:
                self._enter_positions(underlier, closest_strike, ts_idx, time_str, data_provider, portfolio)
                
            # Scenario 2: Position held, but strike has changed
            elif self.exit_on_strike_change and closest_strike != held_s:
                # Sell old, buy new
                self._exit_positions(underlier, ts_idx, time_str, data_provider, portfolio)
                self._enter_positions(underlier, closest_strike, ts_idx, time_str, data_provider, portfolio)

    def on_day_end(self, ts_idx, time_str, data_provider, portfolio):
        # Close all active positions
        for underlier in self.underliers:
            if underlier in self.held_strike and self.held_strike[underlier] is not None:
                self._exit_positions(underlier, ts_idx, time_str, data_provider, portfolio)

    def _enter_positions(self, underlier, strike, ts_idx, time_str, data_provider, portfolio):
        expiry = self.expiry_strs[underlier]
        mapping = self.opt_files_map[underlier]
        
        symbols_to_buy = {}
        prices_to_buy = {}
        
        # Verify and load all data before executing orders
        for otype in self.option_types:
            key = (underlier, expiry, strike, otype)
            filepath = mapping.get(key)
            if not filepath:
                return # Can't trade if any file missing
                
            cache_key = (data_provider.cache.get('current_date_str', ''), 'option', os.path.basename(filepath))
            try:
                opt_data = data_provider.load_option_data(filepath, cache_key)
                price = opt_data['prices'][ts_idx]
                import numpy as np
                if np.isnan(price):
                    raise ValueError("Price is NaN")
                symbol = os.path.basename(filepath).replace('.csv', '')
                symbols_to_buy[otype] = symbol
                prices_to_buy[symbol] = price
            except Exception:
                return # Error reading file or NaN price, abort entry
                
        # Execute BUY orders
        for otype, symbol in symbols_to_buy.items():
            price = prices_to_buy[symbol]
            portfolio.execute_order(
                symbol=symbol,
                timestamp=time_str,
                price=price,
                quantity=self.max_pos,
                action='BUY',
                underlier=underlier
            )
            self.held_symbols[underlier][symbol] = self.max_pos
            
        self.held_strike[underlier] = strike

    def _exit_positions(self, underlier, ts_idx, time_str, data_provider, portfolio):
        held_syms = list(self.held_symbols[underlier].keys())
        expiry = self.expiry_strs[underlier]
        strike = self.held_strike[underlier]
        mapping = self.opt_files_map[underlier]
        
        for symbol in held_syms:
            # Parse symbol to retrieve filepath
            # format e.g. NIFTY22110318000CE
            # find matching key
            # Let's extract otype from symbol
            otype = symbol[-2:] # CE or PE
            key = (underlier, expiry, strike, otype)
            filepath = mapping.get(key)
            if not filepath:
                continue
                
            cache_key = (data_provider.cache.get('current_date_str', ''), 'option', os.path.basename(filepath))
            try:
                opt_data = data_provider.load_option_data(filepath, cache_key)
                price = opt_data['prices'][ts_idx]
                import numpy as np
                if np.isnan(price):
                    raise ValueError("Price is NaN")
            except Exception:
                # Fallback to last known price from previous second, or entry price
                price = portfolio.last_known_prices.get(symbol, portfolio.entry_prices.get(symbol, 0.0))
                
            qty = self.held_symbols[underlier][symbol]
            portfolio.execute_order(
                symbol=symbol,
                timestamp=time_str,
                price=price,
                quantity=qty,
                action='SELL',
                underlier=underlier
            )
            
        self.held_symbols[underlier].clear()
        self.held_strike[underlier] = None
