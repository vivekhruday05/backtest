# Guide to Writing Strategies (XML + YAML)

The Antigravity backtesting engine decouples **simulation parameters** (specified in YAML) from **trading logic and rules** (defined in XML). This guide outlines how to write, customize, and plug in new strategies.

---

## 🛠️ 1. YAML Configuration Schema

The YAML configuration controls the **environment, simulation period, capital, and friction parameters**. It is loaded when launching a backtest.

### YAML Fields Description:
- `data_dir` (string): The path to the directory containing date folders (`NSE_YYYYMMDD`).
- `output_dir` (string): Path to save trade logs, daily PnL, and performance curves.
- `simulation.start_date` / `end_date` (string `YYYYMMDD`): The date range for the backtest.
- `simulation.initial_capital` (float): Starting portfolio cash value (INR).
- `simulation.slippage_pct` (float): Execution price slippage. A value of `0.0005` translates to `0.05%` premium penalty on entry and exit.
- `simulation.transaction_fee_pct` (float): Transaction commissions, exchange fees, and taxes. A value of `0.0002` translates to `0.02%` of the trade value.
- `strategy.xml_path` (string): Path to the XML strategy file.

### Example YAML (`configs/backtest_config.yaml`):
```yaml
data_dir: "data"
output_dir: "output"

simulation:
  start_date: "20221101"
  end_date: "20221130"
  initial_capital: 1000000.0
  slippage_pct: 0.0005
  transaction_fee_pct: 0.0002

strategy:
  xml_path: "strategies/atm_straddle_strategy.xml"
```

---

## 📜 2. XML Strategy Schema

The XML file specifies the **universe selection, contract properties, trade action, and roll/exit triggers**.

### Schema Reference:

| XML Tag / Element | Value Options | Description |
| :--- | :--- | :--- |
| `<Strategy name="..." description="...">` | Attributes | Metadata identifying the strategy. |
| `<Universe>` | Child Elements | Defines assets and expiry parameters. |
| `<Universe>/<Underlier>` | `NIFTY`, `BANKNIFTY`, `FINNIFTY` | The indices to monitor and trade. Multiple `<Underlier>` nodes can be specified. |
| `<Universe>/<ExpirySelection>` | `closest` | How to choose the options contract. `closest` selects the nearest expiry $\ge$ current date. |
| `<Execution>` | Child Elements | Dictates how trades are priced and executed. |
| `<Execution>/<StrikeSelection>` | `closest_to_futures` | Rule to match options strike. `closest_to_futures` selects ATM options. |
| `<Execution>/<OptionTypes>` | Parent container | Contains option contract type nodes. |
| `<Execution>/<OptionTypes>/<OptionType>` | `CE`, `PE` | Options types to trade. List both for a Straddle, or one for a directional bet. |
| `<Execution>/<Action>` | `BUY`, `SELL` | Directs whether to go Long (`BUY`) or Short (`SELL`) the option premium. |
| `<Execution>/<MaxPositionPerInstrument>` | Integer (e.g. `1`) | Position cap (in units of contracts) per specific symbol. |
| `<Triggers>` | Child Elements | Roll and exit configurations. |
| `<Triggers>/<ExitCondition type="...">` | `strike_change` | Event triggering position close. `strike_change` closes current options when the ATM strike shifts. |
| `<Triggers>/<DayEndExit time="...">` | Time (`HH:MM:SS`) | Forces liquidating all open positions before market close (e.g., `15:30:00`). |

---

## 💡 3. Creating Custom Strategies

By changing the XML file, you can immediately test different strategies without modifying a single line of python code.

### Example A: Short ATM Straddle
To implement a yield-generating Short Straddle (selling both ATM Call and Put options to capture theta decay), set the action to `SELL`:

Create `strategies/short_straddle.xml`:
```xml
<Strategy name="ShortATMStraddle" description="Short ATM Options Straddle (Sell CE + PE) rolled on strike change">
    <Universe>
        <Underlier>NIFTY</Underlier>
        <ExpirySelection>closest</ExpirySelection>
    </Universe>
    
    <Execution>
        <StrikeSelection>closest_to_futures</StrikeSelection>
        <OptionTypes>
            <OptionType>CE</OptionType>
            <OptionType>PE</OptionType>
        </OptionTypes>
        <Action>SELL</Action>
        <MaxPositionPerInstrument>1</MaxPositionPerInstrument>
    </Execution>
    
    <Triggers>
        <ExitCondition type="strike_change" />
        <DayEndExit time="15:30:00" />
    </Triggers>
</Strategy>
```

### Example B: Long Call-Only ATM Trend Follower
To trade Call options only, looking to capture upward index moves, omit the `PE` type:

Create `strategies/nifty_long_calls.xml`:
```xml
<Strategy name="LongCalls" description="Long Call Options only, rolled ATM">
    <Universe>
        <Underlier>NIFTY</Underlier>
        <ExpirySelection>closest</ExpirySelection>
    </Universe>
    
    <Execution>
        <StrikeSelection>closest_to_futures</StrikeSelection>
        <OptionTypes>
            <OptionType>CE</OptionType>
        </OptionTypes>
        <Action>BUY</Action>
        <MaxPositionPerInstrument>1</MaxPositionPerInstrument>
    </Execution>
    
    <Triggers>
        <ExitCondition type="strike_change" />
        <DayEndExit time="15:30:00" />
    </Triggers>
</Strategy>
```

---

## ⚙️ 4. Pluggable Logic Extension in Python
To implement rules that XML cannot describe (e.g. trading based on Technical Indicators like MACD, RSI, or Moving Averages), inherit from `BaseStrategy` inside [strategy.py](file:///home/vivek/test/gitrepo/backtest/backtest_engine/strategy.py):

```python
from backtest_engine.strategy import BaseStrategy

class MovingAverageCross(BaseStrategy):
    def __init__(self, fast_period=10, slow_period=50):
        super().__init__()
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.name = "MA_Cross"
        
    def on_second(self, ts_idx, time_str, data_provider, portfolio):
        # 1. Fetch futures price series
        fut_data = data_provider.load_futures_data(...)
        prices = fut_data['prices'][:ts_idx + 1] # Historical prices up to now
        
        # 2. Check indicators
        if len(prices) > self.slow_period:
            fast_ma = prices[-self.fast_period:].mean()
            slow_ma = prices[-self.slow_period:].mean()
            
            # 3. Trigger trade execution
            if fast_ma > slow_ma and not portfolio.positions:
                # Execute buy logic...
                pass
```

You can register this class inside [run_backtest.py](file:///home/vivek/test/gitrepo/backtest/run_backtest.py) and select it as an alternative runtime strategy!
