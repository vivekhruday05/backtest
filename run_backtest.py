import os
import yaml
import argparse
import matplotlib.pyplot as plt
import pandas as pd
from datetime import datetime
from backtest_engine.core import BacktestEngine
from backtest_engine.strategy import XMLStrategy

def parse_args():
    parser = argparse.ArgumentParser(description="Backtest Engine Runner")
    parser.add_argument(
        "--config", 
        type=str, 
        default="configs/backtest_config.yaml", 
        help="Path to the YAML configuration file"
    )
    return parser.parse_args()

def plot_results(output_dir):
    # Load results
    hist_path = os.path.join(output_dir, "portfolio_history_1m.csv")
    daily_path = os.path.join(output_dir, "daily_pnl.csv")
    
    if not os.path.exists(hist_path) or not os.path.exists(daily_path):
        print("Results files not found. Skipping plot generation.")
        return
        
    df_hist = pd.read_csv(hist_path)
    df_daily = pd.read_csv(daily_path)
    
    # Convert timestamps to datetime
    df_hist['datetime'] = pd.to_datetime(df_hist['timestamp'])
    df_hist = df_hist.sort_values('datetime')
    
    # Setup subplots (3 rows)
    fig, axes = plt.subplots(3, 1, figsize=(12, 18), sharex=False)
    
    # Plot 1: Cumulative Net PnL
    axes[0].plot(df_hist['datetime'], df_hist['pnl'], label='Cumulative Net PnL', color='#2ca02c', linewidth=2)
    axes[0].axhline(0, color='grey', linestyle='--', alpha=0.7)
    axes[0].set_title('Cumulative Net PnL (INR)', fontsize=14, fontweight='bold')
    axes[0].set_ylabel('PnL (INR)', fontsize=12)
    axes[0].grid(True, linestyle=':', alpha=0.6)
    axes[0].legend(loc='upper left')
    
    # Plot 2: Daily PnL Bar Chart
    df_daily['date'] = pd.to_datetime(df_daily['date'], format='%Y%m%d')
    colors = ['#2ca02c' if x >= 0 else '#d62728' for x in df_daily['daily_pnl']]
    axes[1].bar(df_daily['date'], df_daily['daily_pnl'], color=colors, width=0.6, edgecolor='black', alpha=0.8)
    axes[1].axhline(0, color='grey', linestyle='--', alpha=0.7)
    axes[1].set_title('Daily Net PnL (INR)', fontsize=14, fontweight='bold')
    axes[1].set_ylabel('PnL (INR)', fontsize=12)
    axes[1].grid(True, linestyle=':', alpha=0.6)
    
    # Plot 3: Drawdown Curve
    df_hist['cum_max'] = df_hist['portfolio_value'].cummax()
    df_hist['drawdown_pct'] = ((df_hist['portfolio_value'] - df_hist['cum_max']) / df_hist['cum_max']) * 100.0
    axes[2].fill_between(df_hist['datetime'], df_hist['drawdown_pct'], 0, color='#d62728', alpha=0.3, label='Drawdown %')
    axes[2].plot(df_hist['datetime'], df_hist['drawdown_pct'], color='#d62728', linewidth=1)
    axes[2].set_title('Portfolio Drawdown (%)', fontsize=14, fontweight='bold')
    axes[2].set_ylabel('Drawdown (%)', fontsize=12)
    axes[2].grid(True, linestyle=':', alpha=0.6)
    axes[2].legend(loc='lower left')
    
    # Beautify dates formatting
    plt.gcf().autofmt_xdate()
    plt.tight_layout()
    
    # Save figure
    plot_path = os.path.join(output_dir, "backtest_performance.png")
    plt.savefig(plot_path, dpi=300)
    print(f"Performance plots successfully saved to: {plot_path}")
    plt.close()

def main():
    args = parse_args()
    
    # Load configuration
    if not os.path.exists(args.config):
        print(f"Config file not found: {args.config}")
        return
        
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)
        
    data_dir = config.get('data_dir', 'data')
    output_dir = config.get('output_dir', 'output')
    
    # Load XML Strategy
    xml_path = config.get('strategy', {}).get('xml_path', 'strategies/atm_straddle_strategy.xml')
    strategy = XMLStrategy(xml_path=xml_path)
    
    # Initialize and run backtest engine
    engine = BacktestEngine(
        data_dir=data_dir,
        output_dir=output_dir,
        config=config
    )
    
    print("=" * 60)
    print(f"RUNNING BACKTEST SIMULATION")
    print(f"Config File:   {args.config}")
    print(f"Strategy:      {strategy.name}")
    print(f"Initial Cash:  {engine.initial_capital:,.2f} INR")
    print(f"Slippage:      {engine.slippage_pct*100:.3f}%")
    print(f"Brokerage:     {engine.transaction_fee_pct*100:.3f}%")
    print("=" * 60)
    
    start_time = datetime.now()
    summary = engine.run(strategy)
    end_time = datetime.now()
    
    if summary:
        print("\n" + "=" * 60)
        print("BACKTEST SUMMARY RESULTS")
        print("=" * 60)
        print(f"Initial Capital:  {summary['initial_capital']:,.2f} INR")
        print(f"Final Value:      {summary['final_value']:,.2f} INR")
        print(f"Net PnL:          {summary['net_pnl']:+,.2f} INR ({summary['net_return_pct']:+.2f}%)")
        print(f"Annualized Sharpe: {summary['sharpe_ratio']:.2f}")
        print(f"Max Drawdown:     {summary['max_drawdown_pct']:.2f}%")
        print(f"Total Trade Orders:{summary['total_trades']}")
        print(f"Buy Orders:       {summary['buy_orders']}")
        print(f"Sell Orders:      {summary['sell_orders']}")
        print(f"Total Fees Paid:  {summary['total_fees']:.2f} INR")
        print(f"Sell Win Rate:    {summary['win_rate_pct']:.2f}% ({summary['winning_trades']} wins, {summary['losing_trades']} losses)")
        print("=" * 60)
        print(f"Execution took:   {end_time - start_time}")
        print("=" * 60)
        
        # Generate performance charts
        plot_results(output_dir)
        
if __name__ == "__main__":
    main()
