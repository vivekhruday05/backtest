import os
import pandas as pd
import numpy as np
from datetime import datetime
import logging
from backtest_engine.data_provider import DataProvider
from backtest_engine.portfolio import PortfolioTracker

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BacktestEngine:
    def __init__(self, data_dir="data", output_dir="output", config=None):
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.config = config or {}
        
        # Simulation parameters
        sim_cfg = self.config.get('simulation', {})
        self.start_date_str = sim_cfg.get('start_date', '20221101')
        self.end_date_str = sim_cfg.get('end_date', '20221130')
        self.initial_capital = float(sim_cfg.get('initial_capital', 1000000.0))
        self.slippage_pct = float(sim_cfg.get('slippage_pct', 0.0005))
        self.transaction_fee_pct = float(sim_cfg.get('transaction_fee_pct', 0.0002))
        
        self.data_provider = DataProvider(data_dir=self.data_dir)
        self.portfolio = PortfolioTracker(
            initial_capital=self.initial_capital,
            slippage_pct=self.slippage_pct,
            transaction_fee_pct=self.transaction_fee_pct
        )
        
        # Results logging
        self.history_records = []
        
    def run(self, strategy):
        logger.info(f"Starting backtest from {self.start_date_str} to {self.end_date_str}")
        logger.info(f"Strategy: {strategy.name} - {strategy.description}")
        
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Get date folders and filter by start/end dates
        all_folders = self.data_provider.get_date_folders()
        active_folders = []
        for folder in all_folders:
            date_part = os.path.basename(folder).split("_")[1]
            if self.start_date_str <= date_part <= self.end_date_str:
                active_folders.append((date_part, folder))
                
        active_folders.sort(key=lambda x: x[0])
        logger.info(f"Found {len(active_folders)} trading days in date range.")
        
        if not active_folders:
            logger.warning("No trading days found in the specified range.")
            return None
            
        for date_str, folder in active_folders:
            logger.info(f"Processing trading day: {date_str}")
            trading_date = datetime.strptime(date_str, "%Y%m%d").date()
            
            # Setup data provider cache context
            self.data_provider.clear_cache()
            self.data_provider.cache['current_date_str'] = date_str
            
            # Initialize strategy for the day
            strategy.on_day_start(date_str, trading_date, self.data_provider)
            
            # Run the second-by-second loop
            time_idx_list = self.data_provider.time_index
            day_initial_value = self.portfolio.get_portfolio_value({})
            
            for ts_idx, time_str in enumerate(time_idx_list):
                # Execute strategy logic
                strategy.on_second(ts_idx, time_str, self.data_provider, self.portfolio)
                
                # Check day-end trigger
                if time_str >= strategy.day_end_time:
                    strategy.on_day_end(ts_idx, time_str, self.data_provider, self.portfolio)
                    
                # Collect current prices of held positions to calculate MtM
                current_prices = {}
                for symbol in self.portfolio.positions.keys():
                    parsed = self.data_provider._parse_filename(symbol)
                    if not parsed:
                        continue
                    underlier = parsed['underlier']
                    expiry = parsed['expiry']
                    strike = parsed['strike']
                    otype = parsed['option_type']
                    key = (underlier, expiry, strike, otype)
                    filepath = strategy.opt_files_map.get(underlier, {}).get(key)
                    
                    if filepath:
                        cache_key = (date_str, 'option', os.path.basename(filepath))
                        try:
                            opt_data = self.data_provider.load_option_data(filepath, cache_key)
                            price = opt_data['prices'][ts_idx]
                            # Check for NaN price (e.g. from ffill only with no trades yet)
                            if np.isnan(price):
                                raise ValueError("Price is NaN")
                            current_prices[symbol] = price
                            self.portfolio.last_known_prices[symbol] = price
                        except Exception:
                            # Fallback to last known price from previous second, or entry price
                            price = self.portfolio.last_known_prices.get(symbol, self.portfolio.entry_prices.get(symbol, 0.0))
                            current_prices[symbol] = price
                            
                portfolio_value = self.portfolio.get_portfolio_value(current_prices)
                pnl = portfolio_value - self.initial_capital
                
                # Construct active positions string
                pos_str = "; ".join([f"{sym}:{qty}" for sym, qty in self.portfolio.positions.items()])
                if not pos_str:
                    pos_str = "None"
                    
                self.history_records.append({
                    'timestamp': f"{date_str} {time_str}",
                    'date': date_str,
                    'time': time_str,
                    'portfolio_value': portfolio_value,
                    'cash': self.portfolio.cash,
                    'positions': pos_str,
                    'pnl': pnl,
                    'daily_pnl': portfolio_value - day_initial_value
                })
                
            # Log final daily state
            day_final_value = self.portfolio.get_portfolio_value({})
            daily_net = day_final_value - day_initial_value
            self.portfolio.daily_pnl[date_str] = daily_net
            logger.info(f"End of day {date_str}. Daily PnL: {daily_net:.2f}. Cash: {self.portfolio.cash:.2f}")
            
        logger.info("Backtest execution completed. Saving results...")
        self.save_results()
        logger.info("Results successfully saved.")
        return self.generate_summary()
        
    def save_results(self):
        # Convert history records to DataFrame
        df_hist = pd.DataFrame(self.history_records)
        hist_path = os.path.join(self.output_dir, "portfolio_history.csv")
        df_hist.to_csv(hist_path, index=False)
        
        # Downsample to 1-minute for dashboard plotting
        df_hist['datetime'] = pd.to_datetime(df_hist['timestamp'])
        df_hist_1m = df_hist.set_index('datetime').resample('1min').last().reset_index()
        df_hist_1m = df_hist_1m.drop(columns=['datetime'])
        # Keep non-empty rows (in case resample introduces gaps, drop them)
        df_hist_1m = df_hist_1m.dropna(subset=['timestamp'])
        hist_1m_path = os.path.join(self.output_dir, "portfolio_history_1m.csv")
        df_hist_1m.to_csv(hist_1m_path, index=False)
        
        # Save trades history
        df_trades = pd.DataFrame(self.portfolio.trades_history)
        trades_path = os.path.join(self.output_dir, "trades.csv")
        df_trades.to_csv(trades_path, index=False)
        
        # Save daily pnl
        df_daily = pd.DataFrame(list(self.portfolio.daily_pnl.items()), columns=['date', 'daily_pnl'])
        daily_path = os.path.join(self.output_dir, "daily_pnl.csv")
        df_daily.to_csv(daily_path, index=False)
        
    def generate_summary(self):
        # Calculate statistics
        df_hist = pd.DataFrame(self.history_records)
        df_daily = pd.DataFrame(list(self.portfolio.daily_pnl.items()), columns=['date', 'daily_pnl'])
        df_trades = pd.DataFrame(self.portfolio.trades_history)
        
        total_pnl = self.portfolio.daily_pnl.get(list(self.portfolio.daily_pnl.keys())[-1], 0.0) if self.portfolio.daily_pnl else 0.0
        final_value = self.portfolio.get_portfolio_value({})
        net_return_pct = ((final_value - self.initial_capital) / self.initial_capital) * 100.0
        
        # Compute Sharpe (using daily returns)
        daily_returns = df_daily['daily_pnl'] / self.initial_capital
        mean_return = daily_returns.mean()
        std_return = daily_returns.std()
        # Annualized Sharpe (assuming 252 trading days)
        sharpe = (mean_return / std_return * np.sqrt(252)) if std_return > 0 else 0.0
        
        # Compute Drawdown
        df_hist['cum_max'] = df_hist['portfolio_value'].cummax()
        df_hist['drawdown'] = (df_hist['portfolio_value'] - df_hist['cum_max']) / df_hist['cum_max']
        max_dd = df_hist['drawdown'].min() * 100.0
        
        # Trade metrics
        total_trades = len(df_trades)
        buy_trades = len(df_trades[df_trades['action'] == 'BUY'])
        sell_trades = len(df_trades[df_trades['action'] == 'SELL'])
        total_fees = df_trades['fee'].sum()
        
        # Realized trades metrics (SELL trades report realized PnL)
        sell_records = df_trades[df_trades['action'] == 'SELL']
        winning_trades = len(sell_records[sell_records['realized_pnl'] > 0])
        losing_trades = len(sell_records[sell_records['realized_pnl'] <= 0])
        win_rate = (winning_trades / len(sell_records) * 100.0) if len(sell_records) > 0 else 0.0
        
        summary = {
            'initial_capital': self.initial_capital,
            'final_value': final_value,
            'net_pnl': final_value - self.initial_capital,
            'net_return_pct': net_return_pct,
            'sharpe_ratio': sharpe,
            'max_drawdown_pct': max_dd,
            'total_trades': total_trades,
            'buy_orders': buy_trades,
            'sell_orders': sell_trades,
            'total_fees': total_fees,
            'win_rate_pct': win_rate,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades
        }
        
        # Save summary to json
        import json
        summary_path = os.path.join(self.output_dir, "summary.json")
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=4)
            
        return summary
