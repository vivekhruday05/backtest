import pandas as pd
import numpy as np

class PortfolioTracker:
    def __init__(self, initial_capital=1000000.0, slippage_pct=0.0, transaction_fee_pct=0.0):
        self.initial_capital = initial_capital
        self.slippage_pct = slippage_pct
        self.transaction_fee_pct = transaction_fee_pct
        
        self.cash = initial_capital
        self.positions = {}       # symbol -> quantity
        self.entry_prices = {}    # symbol -> avg_entry_price
        self.entry_fees = {}      # symbol -> accumulated_entry_fees (to compute net trade pnl)
        
        self.trades_history = []  # list of trade logs
        self.daily_pnl = {}       # date_str -> daily net pnl
        
    def execute_order(self, symbol, timestamp, price, quantity, action, underlier):
        """
        Executes a trade order, updates portfolio cash and positions, and logs the transaction.
        action: 'BUY' or 'SELL'
        quantity: positive integer
        """
        if quantity <= 0:
            return
            
        fee_rate = self.transaction_fee_pct
        slip_rate = self.slippage_pct
        
        if action == 'BUY':
            execution_price = price * (1.0 + slip_rate)
            gross_value = execution_price * quantity
            fee = gross_value * fee_rate
            total_cost = gross_value + fee
            
            self.cash -= total_cost
            
            # Position accounting
            prev_qty = self.positions.get(symbol, 0)
            prev_entry = self.entry_prices.get(symbol, 0.0)
            prev_fees = self.entry_fees.get(symbol, 0.0)
            
            new_qty = prev_qty + quantity
            if prev_qty == 0:
                self.entry_prices[symbol] = execution_price
                self.entry_fees[symbol] = fee
            else:
                self.entry_prices[symbol] = ((prev_qty * prev_entry) + (quantity * execution_price)) / new_qty
                self.entry_fees[symbol] = prev_fees + fee
                
            self.positions[symbol] = new_qty
            
            trade_log = {
                'timestamp': timestamp,
                'symbol': symbol,
                'underlier': underlier,
                'action': 'BUY',
                'quantity': quantity,
                'market_price': price,
                'execution_price': execution_price,
                'fee': fee,
                'cash_after': self.cash,
                'realized_pnl': 0.0
            }
            self.trades_history.append(trade_log)
            
        elif action == 'SELL':
            # Check if we have position to sell
            curr_qty = self.positions.get(symbol, 0)
            if curr_qty < quantity:
                # Force limit sell to what is held
                quantity = curr_qty
                if quantity == 0:
                    return
            
            execution_price = price * (1.0 - slip_rate)
            gross_value = execution_price * quantity
            fee = gross_value * fee_rate
            total_proceeds = gross_value - fee
            
            self.cash += total_proceeds
            
            # PnL calculations
            entry_price = self.entry_prices.get(symbol, 0.0)
            # Allocate entry fee proportionally
            allocated_entry_fee = (self.entry_fees.get(symbol, 0.0) / curr_qty) * quantity
            raw_trade_pnl = (execution_price - entry_price) * quantity
            net_trade_pnl = raw_trade_pnl - fee - allocated_entry_fee
            
            new_qty = curr_qty - quantity
            if new_qty == 0:
                del self.positions[symbol]
                del self.entry_prices[symbol]
                del self.entry_fees[symbol]
            else:
                self.positions[symbol] = new_qty
                # Reduce entry fees pool
                self.entry_fees[symbol] -= allocated_entry_fee
                
            trade_log = {
                'timestamp': timestamp,
                'symbol': symbol,
                'underlier': underlier,
                'action': 'SELL',
                'quantity': quantity,
                'market_price': price,
                'execution_price': execution_price,
                'fee': fee,
                'cash_after': self.cash,
                'realized_pnl': net_trade_pnl
            }
            self.trades_history.append(trade_log)

    def get_portfolio_value(self, current_prices):
        """
        Computes the current portfolio value (Cash + Market Value of all positions).
        current_prices: dictionary mapping symbol -> current price
        """
        mv = 0.0
        for symbol, qty in self.positions.items():
            price = current_prices.get(symbol, 0.0)
            mv += qty * price
        return self.cash + mv

    def reset_positions(self):
        """
        Closes all positions (without execution, just resets - usually used after closing trades are executed).
        """
        self.positions.clear()
        self.entry_prices.clear()
        self.entry_fees.clear()
