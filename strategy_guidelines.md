# Developer & Strategy Writing Guide (XML + YAML)

This backtesting engine is designed to be fully **strategy-agnostic** and **pluggable**. It accomplishes this by separating:
1. **Simulation parameters** (capital, slippage, fees, data paths) -> Controlled via **YAML** configuration.
2. **Trading rules and logic** (underliers, expiries, strikes, actions) -> Controlled via **XML** strategy sheets.

This guide provides a comprehensive manual on how the engine processes these configurations, how to extend them by adding new XML tags or YAML parameters, and includes concrete strategy examples.

---

## 🛠️ 1. YAML Configuration Schema

The YAML configuration controls the execution environment. It is loaded at startup inside [run_backtest.py](file:///home/vivek/test/gitrepo/backtest/run_backtest.py) and [app.py](file:///home/vivek/test/gitrepo/backtest/app.py).

### Schema Reference:
```yaml
# Paths
data_dir: "data"          # Path to directory containing NSE_YYYYMMDD folders
output_dir: "output"      # Path to save trade logs and CSV outputs

# Simulation parameters
simulation:
  start_date: "20221101"       # Start date of simulation (YYYYMMDD)
  end_date: "20221130"         # End date of simulation (YYYYMMDD)
  initial_capital: 1000000.0   # Starting cash balance (INR)
  slippage_pct: 0.0005         # 0.05% premium penalty per transaction
  transaction_fee_pct: 0.0002  # 0.02% fee per transaction (brokerage/taxes)

# Strategy settings
strategy:
  xml_path: "strategies/atm_straddle_strategy.xml"  # Path to XML Strategy
```

### ⚙️ How to Add New YAML Parameters
If you want to add a new simulation parameter (for example, a global stop-loss threshold at the portfolio level, say `portfolio_stop_loss_pct`):

1. **Add it to the YAML file** (e.g. `configs/backtest_config.yaml`):
   ```yaml
   simulation:
     initial_capital: 1000000.0
     portfolio_stop_loss_pct: 0.02  # Stop backtest if cumulative loss exceeds 2%
   ```

2. **Load and store it in the engine code**:
   Modify [BacktestEngine.__init__](file:///home/vivek/test/gitrepo/backtest/backtest_engine/core.py) to read this parameter from the dictionary:
   ```python
   # Inside BacktestEngine.__init__
   sim_cfg = self.config.get('simulation', {})
   self.portfolio_stop_loss_pct = float(sim_cfg.get('portfolio_stop_loss_pct', 0.02))
   ```

3. **Incorporate it into the execution logic**:
   Modify the simulation loop in [BacktestEngine.run](file:///home/vivek/test/gitrepo/backtest/backtest_engine/core.py):
   ```python
   # Inside the loop in BacktestEngine.run
   if pnl < -self.portfolio_stop_loss_pct * self.initial_capital:
       logger.warning("Portfolio stop-loss triggered! Liquidating positions and terminating backtest.")
       strategy.on_day_end(ts_idx, time_str, self.data_provider, self.portfolio)
       break
   ```

---

## 📜 2. XML Strategy Schema & Parsing

The XML configuration allows you to define options trading strategies without modifying python files.

### 🔍 How XML Parsing Works
XML parsing is handled by the [XMLStrategy](file:///home/vivek/test/gitrepo/backtest/backtest_engine/strategy.py) class using Python's native `xml.etree.ElementTree` parser.

The parsing steps are:
1. In `XMLStrategy.parse_xml()`, the XML file is parsed into a tree of elements.
2. The code walks the nodes (e.g., `<Universe>`, `<Execution>`, `<Triggers>`) and extracts the text content or attributes.
3. These values are mapped directly to python variables:
   ```python
   # Extracts <Underlier> tags list
   self.underliers = [u.text for u in universe_node.findall('Underlier')]
   
   # Extracts <Action> (e.g. BUY or SELL)
   self.action = exec_node.find('Action').text
   
   # Checks for exit conditions in <Triggers>
   self.exit_on_strike_change = any(ec.attrib.get('type') == 'strike_change' 
                                    for ec in triggers_node.findall('ExitCondition'))
   ```

---

## 🛠️ 3. Extending the XML Schema (Code Modification Guide)

If you want to add new trading capabilities (e.g. trading Out-of-the-Money options by specifying a `<StrikeOffset>` node in the XML), follow these steps:

### Example: Adding a `<StrikeOffset>` Parameter
By default, the engine trades At-the-Money (ATM) options (offset = 0). Let's add a `<StrikeOffset>` tag to allow trading in-the-money (ITM) or out-of-the-money (OTM) options (e.g., buying Call/Put 1 strike offset away from ATM).

#### Step 1: Add the tag to the XML strategy file
Add `<StrikeOffset>` inside the `<Execution>` block:
```xml
<Execution>
    <StrikeSelection>closest_to_futures</StrikeSelection>
    <StrikeOffset>1</StrikeOffset> <!-- +1 strike offset (OTM calls/puts) -->
    <OptionTypes>
        <OptionType>CE</OptionType>
        <OptionType>PE</OptionType>
    </OptionTypes>
</Execution>
```

#### Step 2: Update Python Parser
Modify the `parse_xml` method in [XMLStrategy](file:///home/vivek/test/gitrepo/backtest/backtest_engine/strategy.py):
```python
# In strategy.py -> XMLStrategy.__init__
self.strike_offset = 0  # Default value

# In strategy.py -> XMLStrategy.parse_xml()
exec_node = root.find('Execution')
if exec_node is not None:
    offset_node = exec_node.find('StrikeOffset')
    if offset_node is not None:
        self.strike_offset = int(offset_node.text)
```

#### Step 3: Implement Logic in Strike Finder
Update the strike resolution logic inside [XMLStrategy._find_closest_strike](file:///home/vivek/test/gitrepo/backtest/backtest_engine/strategy.py) to incorporate the offset:
```python
# In strategy.py -> XMLStrategy._find_closest_strike()
def _find_closest_strike(self, underlier, future_price):
    strikes = self.available_strikes.get(underlier)
    if strikes is None or len(strikes) == 0:
        return None
        
    # Binary search for closest strike index
    idx = np.searchsorted(strikes, future_price)
    
    # Resolve closest ATM strike index
    if idx == 0:
        atm_idx = 0
    elif idx == len(strikes):
        atm_idx = len(strikes) - 1
    else:
        d1 = abs(strikes[idx] - future_price)
        d2 = abs(strikes[idx-1] - future_price)
        atm_idx = idx if d1 < d2 else (idx - 1)
        
    # Apply configured XML strike offset
    target_idx = atm_idx + self.strike_offset
    # Keep index within bounds
    target_idx = max(0, min(len(strikes) - 1, target_idx))
    
    return strikes[target_idx]
```

This simple modification instantly expands your XML engine to support **OTM/ITM Straddles and Strangles**!

---

## 💡 4. Concrete Strategy Examples

Below are four XML strategy sheets demonstrating the flexibility of this schema-driven backtesting suite.

### 📈 Example 1: ATM Straddle (Default Long Volatility)
Buys ATM Call and Put options, rolling them continuously as the futures price changes the ATM strike.
```xml
<Strategy name="ATMStraddle" description="ATM Options Straddle Strategy (Long CE + PE) matching closest strike of futures price">
    <Universe>
        <Underlier>NIFTY</Underlier>
        <Underlier>BANKNIFTY</Underlier>
        <ExpirySelection>closest</ExpirySelection>
    </Universe>
    
    <Execution>
        <StrikeSelection>closest_to_futures</StrikeSelection>
        <OptionTypes>
            <OptionType>CE</OptionType>
            <OptionType>PE</OptionType>
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

### 📉 Example 2: Short ATM Straddle (Income Generation)
Sells ATM Call and Put options to collect premium decay (Theta). Rolled upon strike change.
```xml
<Strategy name="ShortATMStraddle" description="Short ATM Options Straddle (Sell CE + PE) to harvest Theta">
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

### 🎯 Example 3: Long Call-Only ATM Bets (Trend Following)
Takes directional long calls, rolling up or down on strike boundary changes.
```xml
<Strategy name="LongCalls" description="Long Call Options only, rolled ATM to trade upside trends">
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

### 🦋 Example 4: OTM Strangle (Long Volatility with Offset)
Requires implementing the `<StrikeOffset>` parameter (detailed in Section 3). It buys Call and Put options $k$ strikes away from ATM (calls offset $+2$, puts offset $-2$) to trade large breakout moves cheaply.
```xml
<Strategy name="OTMStrangle" description="OTM Options Strangle (Long CE + PE 2 strikes away) for breakout trading">
    <Universe>
        <Underlier>NIFTY</Underlier>
        <ExpirySelection>closest</ExpirySelection>
    </Universe>
    
    <Execution>
        <StrikeSelection>closest_to_futures</StrikeSelection>
        <!-- Offset is handled by finding strike +/- index. 
             If we want calls/puts offset separately, we can extend strike_offset logic. -->
        <StrikeOffset>2</StrikeOffset> 
        <OptionTypes>
            <OptionType>CE</OptionType>
            <OptionType>PE</OptionType>
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
