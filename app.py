import streamlit as st
import pandas as pd
import numpy as np
import os
import yaml
import json
import glob
import subprocess
from datetime import datetime
from backtest_engine.core import BacktestEngine
from backtest_engine.strategy import XMLStrategy

# Set page layout and aesthetics
st.set_page_config(
    page_title="Antigravity Backtesting Suite",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom premium styling
st.markdown("""
    <style>
        .reportview-container {
            background-color: #0f172a;
        }
        .main {
            background-color: #0f172a;
            color: #f8fafc;
        }
        /* Custom card styling */
        .metric-card {
            background-color: #1e293b;
            border: 1px solid #334155;
            padding: 1.5rem;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1);
            text-align: center;
            margin-bottom: 1rem;
        }
        .metric-title {
            color: #94a3b8;
            font-size: 0.875rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.5rem;
        }
        .metric-value {
            color: #f8fafc;
            font-size: 1.875rem;
            font-weight: 700;
        }
        .metric-value-green {
            color: #10b981;
            font-size: 1.875rem;
            font-weight: 700;
        }
        .metric-value-red {
            color: #ef4444;
            font-size: 1.875rem;
            font-weight: 700;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 24px;
        }
        .stTabs [data-baseweb="tab"] {
            height: 50px;
            white-space: pre-wrap;
            background-color: transparent;
            border-radius: 4px 4px 0px 0px;
            gap: 9px;
            font-weight: 600;
            color: #94a3b8;
        }
        .stTabs [aria-selected="true"] {
            color: #38bdf8;
            border-bottom-color: #38bdf8;
        }
    </style>
""", unsafe_allow_html=True)

# Helper function to load outputs
OUTPUT_DIR = "output"

def load_summary():
    summary_path = os.path.join(OUTPUT_DIR, "summary.json")
    if os.path.exists(summary_path):
        with open(summary_path, 'r') as f:
            return json.load(f)
    return None

def load_daily_pnl():
    daily_path = os.path.join(OUTPUT_DIR, "daily_pnl.csv")
    if os.path.exists(daily_path):
        df = pd.read_csv(daily_path)
        df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
        return df
    return None

def load_portfolio_history():
    hist_path = os.path.join(OUTPUT_DIR, "portfolio_history_1m.csv")
    if os.path.exists(hist_path):
        df = pd.read_csv(hist_path)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    return None

def load_trades():
    trades_path = os.path.join(OUTPUT_DIR, "trades.csv")
    if os.path.exists(trades_path):
        return pd.read_csv(trades_path)
    return None

# Sidebar - Settings and Runner
st.sidebar.title("⚡ Backtest Controller")
st.sidebar.markdown("Configure and run strategy-agnostic backtests.")

# Strategy selector
strategy_files = glob.glob("strategies/*.xml")
strategy_names = [os.path.basename(f) for f in strategy_files]

if not strategy_names:
    st.sidebar.error("No XML strategy files found in strategies/ folder.")
    selected_strategy_file = None
else:
    selected_strategy_file = st.sidebar.selectbox("Select XML Strategy", strategy_names)

# Configuration overrides
st.sidebar.subheader("Simulation Parameters")
start_date = st.sidebar.date_input("Start Date", datetime(2022, 11, 1)).strftime("%Y%m%d")
end_date = st.sidebar.date_input("End Date", datetime(2022, 11, 30)).strftime("%Y%m%d")
initial_capital = st.sidebar.number_input("Initial Capital (INR)", min_value=10000, value=1000000, step=50000)
slippage_pct = st.sidebar.slider("Slippage (%)", min_value=0.0, max_value=0.5, value=0.05, step=0.01) / 100.0
fee_pct = st.sidebar.slider("Transaction Fees (%)", min_value=0.0, max_value=0.2, value=0.02, step=0.01) / 100.0

run_button = st.sidebar.button("🚀 Run Backtest", use_container_width=True)

if run_button and selected_strategy_file:
    # 1. Update/write temp config file
    config_dict = {
        'data_dir': 'data',
        'output_dir': 'output',
        'simulation': {
            'start_date': start_date,
            'end_date': end_date,
            'initial_capital': float(initial_capital),
            'slippage_pct': float(slippage_pct),
            'transaction_fee_pct': float(fee_pct)
        },
        'strategy': {
            'xml_path': os.path.join('strategies', selected_strategy_file)
        }
    }
    
    with open('configs/backtest_config.yaml', 'w') as f:
        yaml.dump(config_dict, f)
        
    # 2. Run engine
    with st.spinner("Processing backtest simulation..."):
        try:
            # We can instantiate and run directly in streamlit process for instant feedback
            xml_path = os.path.join('strategies', selected_strategy_file)
            strategy = XMLStrategy(xml_path=xml_path)
            engine = BacktestEngine(data_dir="data", output_dir="output", config=config_dict)
            summary = engine.run(strategy)
            
            # Replot static matplotlib chart for CLI reference
            # Run plot update
            # We can import and run the plotting script
            from run_backtest import plot_results
            plot_results("output")
            
            st.sidebar.success("Backtest Completed Successfully!")
        except Exception as e:
            st.sidebar.error(f"Error executing backtest: {e}")
            import traceback
            st.sidebar.code(traceback.format_exc())

# Main Panel layout
st.title("📈 Antigravity Institutional Options Backtester")
st.markdown("A robust, strategy-agnostic engine validating modular logic with microsecond resolution.")

summary = load_summary()
df_hist = load_portfolio_history()
df_daily = load_daily_pnl()
df_trades = load_trades()

if summary is None or df_hist is None:
    st.warning("No backtest results found. Please configure the parameters on the sidebar and click **Run Backtest**.")
else:
    # 1. KPI Cards Row
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    
    net_pnl = summary['net_pnl']
    pnl_class = "metric-value-green" if net_pnl >= 0 else "metric-value-red"
    pnl_prefix = "+" if net_pnl >= 0 else ""
    
    with kpi1:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Net PnL (INR)</div>
                <div class="{pnl_class}">{pnl_prefix}{net_pnl:,.2f} ({pnl_prefix}{summary['net_return_pct']:.2f}%)</div>
            </div>
        """, unsafe_allow_html=True)
        
    with kpi2:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Annualized Sharpe</div>
                <div class="metric-value">{summary['sharpe_ratio']:.2f}</div>
            </div>
        """, unsafe_allow_html=True)
        
    with kpi3:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Max Drawdown</div>
                <div class="metric-value-red">{summary['max_drawdown_pct']:.2f}%</div>
            </div>
        """, unsafe_allow_html=True)
        
    with kpi4:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Win Rate (Sells)</div>
                <div class="metric-value">{summary['win_rate_pct']:.2f}%</div>
            </div>
        """, unsafe_allow_html=True)

    # 2. Main Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Performance Charts", "📝 Trade Ledger", "🛠️ Strategy Specs", "📋 System Logs"])
    
    with tab1:
        st.subheader("Cumulative Portfolio Value Over Time")
        # Format df_hist for st.line_chart
        df_hist_line = df_hist.set_index('timestamp')[['portfolio_value']]
        st.line_chart(df_hist_line, y="portfolio_value", color="#38bdf8")
        
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.subheader("Daily Net Returns")
            if df_daily is not None:
                df_daily_bar = df_daily.set_index('date')[['daily_pnl']]
                st.bar_chart(df_daily_bar, y="daily_pnl", color="#10b981")
        with col_c2:
            st.subheader("Portfolio Drawdown %")
            df_hist['cum_max'] = df_hist['portfolio_value'].cummax()
            df_hist['drawdown_pct'] = ((df_hist['portfolio_value'] - df_hist['cum_max']) / df_hist['cum_max']) * 100.0
            df_hist_dd = df_hist.set_index('timestamp')[['drawdown_pct']]
            st.area_chart(df_hist_dd, y="drawdown_pct", color="#ef4444")
            
    with tab2:
        st.subheader("Executed Trade History")
        if df_trades is not None and not df_trades.empty:
            # Filters
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                underlier_filter = st.multiselect("Filter Underlier", options=df_trades['underlier'].unique(), default=df_trades['underlier'].unique())
            with col_f2:
                action_filter = st.multiselect("Filter Action", options=['BUY', 'SELL'], default=['BUY', 'SELL'])
            with col_f3:
                search_symbol = st.text_input("Search Symbol")
                
            filtered_trades = df_trades[
                (df_trades['underlier'].isin(underlier_filter)) &
                (df_trades['action'].isin(action_filter))
            ]
            if search_symbol:
                filtered_trades = filtered_trades[filtered_trades['symbol'].str.contains(search_symbol, case=False)]
                
            st.dataframe(filtered_trades, use_container_width=True)
            
            # Download CSV
            csv_data = filtered_trades.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Filtered Trades as CSV",
                data=csv_data,
                file_name="backtest_trades.csv",
                mime="text/csv"
            )
        else:
            st.info("No trades were executed during this backtest.")
            
    with tab3:
        st.subheader("Active Strategy XML Definition")
        if selected_strategy_file:
            xml_path = os.path.join('strategies', selected_strategy_file)
            if os.path.exists(xml_path):
                with open(xml_path, 'r') as f:
                    xml_content = f.read()
                st.code(xml_content, language='xml')
            else:
                st.error("XML file not found.")
                
        # Guidelines summary
        st.markdown("""
        ### How to define XML strategies
        - **`<Universe>`**: Defines the traded symbols and expiry selector rule.
        - **`<Execution>`**: Configures option action types, entry rules, and strike matching algorithms.
        - **`<Triggers>`**: Defines roll/exit criteria like strike change or day end close parameters.
        """)
        
    with tab4:
        st.subheader("Backtest Run Details")
        st.json(summary)
        
        st.subheader("Static Chart Output File")
        static_chart_path = os.path.join(OUTPUT_DIR, "backtest_performance.png")
        if os.path.exists(static_chart_path):
            st.image(static_chart_path, caption="Backtest Matplotlib Performance Summary (Saved in output/ folder)", use_container_width=True)
