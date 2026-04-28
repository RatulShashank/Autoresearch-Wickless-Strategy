# Wickless Autoresearch

Autonomous hyperparameter and strategy optimization for the **wickless candle scalping strategy** on BTCUSDT 1-minute data.

This framework enables automated research and parameter tuning of a multi-timeframe trading strategy using a fixed, reproducible backtest engine and a composite scoring metric.

## Overview

**Wickless Autoresearch** is a quantitative trading research project that implements:

- **Multi-timeframe analysis**: Lower timeframe (LTF) for trend detection, higher timeframe (HTF) for entry signals
- **Wickless candle detection**: Identifies candles with minimal wicks (tight price action) that indicate strong directional conviction
- **Systematic backtesting**: A frozen, ground-truth backtest engine that ensures all experiments are evaluated consistently
- **Autonomous optimization loop**: An AI agent iteratively refines parameters to maximize a composite performance metric

### Key Features

- **Historical data**: BTCUSDT 1-minute OHLCV bars from 2022–2025
- **Technical indicators**: ATR, Supertrend, EMA, body-to-range ratio, swing detection
- **Risk management**: Position sizing based on ATR, daily trade limits, capital guards
- **Composite scoring**: A metric that balances profit factor, win rate, and drawdown
- **Experiment tracking**: Detailed logging of all parameter experiments and results

## Project Structure

```
.
├── README.md                    # This file
├── strategy_core.py             # Frozen backtest engine (read-only)
├── strategy.py                  # Agent sandbox (parameter tuning only)
├── results.tsv                  # Experiment results log
├── run.log                       # Latest backtest output
├── BTCUSDT-1m-2022.csv         # Historical 1m OHLCV data (2022)
├── BTCUSDT-1m-2023.csv         # Historical 1m OHLCV data (2023)
├── BTCUSDT-1m-2024.csv         # Historical 1m OHLCV data (2024)
├── BTCUSDT-1m-2025.csv         # Historical 1m OHLCV data (2025)
└── .gitignore                   # Excludes results.tsv, run logs, cache
```

## Scoring Metric

The **SCORE** (higher is better) is the primary optimization target:

```
SCORE = profit_factor × (win_rate / 50) / (1 + |max_drawdown_pct| / 20)
```

**Interpretation:**

- **Profit Factor**: Gross wins ÷ Gross losses. PF > 1 = profitable system
- **Win Rate term**: Normalized around 50%. At 50% WR → 1.0. At 60% → 1.2. At 35% → 0.7
- **Drawdown penalty**: A 20% drawdown halves the score. Keeps strategies from being too risky
- **Minimum trades**: Fewer than 30 trades → score = 0 (statistically invalid)

**Typical ranges:**

- Score < 0.3: Poor
- Score 0.3–0.6: Baseline territory
- Score 0.6–1.0: Good
- Score > 1.0: Excellent

## How It Works

### The Backtest Engine (`strategy_core.py`)

A frozen, immutable backtest implementation that provides:

1. **Data loading** and OHLCV resampling to multiple timeframes
2. **Indicator computation**: ATR, Supertrend, EMA slope, wickless detection, swing high/low
3. **Signal generation**: Combining trend filter + wickless candle + displacement filter
4. **Trade execution**: Entry at close or retest, position sizing, exit on SL/TP, trailing stops
5. **Scoring**: Compute profit factor, win rate, drawdown, Sharpe ratio, and composite score

All indicator definitions and the backtest engine are fixed — they never change across experiments.

### The Strategy Sandbox (`strategy.py`)

The agent modifies only `strategy.py` to tune:

**Timeframes:**
- `LOWER_TF`, `HIGHER_TF` — e.g., "1m"/"15m", "5m"/"1h"

**Wickless definition:**
- `WICK_TOLERANCE` — Max wick size (USD) to count as wickless (0–10 USD)

**Trend detection (LTF):**
- `SUPERTREND_PERIOD`, `SUPERTREND_MULT` — Trend filter tightness
- `EMA_PERIOD`, `EMA_SLOPE_LOOKBACK` — Trend confirmation
- `REQUIRE_EMA_CONFIRM` — Require both Supertrend AND EMA to agree

**Entry:**
- `ENTRY_MODE` — "close" (enter on bar close) or "retest" (wait for retest of bar body)
- `RETEST_TIMEOUT_BARS` — Timeout for retest order

**Risk management:**
- `ATR_SL_MULTIPLIER`, `MIN_SL_ATR_FRACTION` — Stop-loss distance
- `SWING_LOOKBACK` — Look back for swing high/low
- `RR_RATIO` — Target risk:reward ratio
- `RISK_PER_TRADE_PCT`, `MAX_TRADES_PER_DAY` — Position sizing and daily limits

**Advanced:**
- `SIGNAL_FILTER_FN` — Custom filtering logic (e.g., volume spikes, session times)

## Running an Experiment

```bash
python strategy.py > run.log 2>&1
```

Extract the score:

```bash
grep "^score:" run.log
```

Full output block (grep-parseable):

```
---
score:          0.612345
profit_factor:  1.340000
win_rate:       42.50
max_drawdown:   -8.30
n_trades:       187
n_signals:      310
total_return:   14.20
avg_rr:         1.820
sharpe:         0.543
final_capital:  11420.00
```

## Typical Research Workflow

### Phase 1: Baseline & Big Levers (Experiments 1–15)

1. Run baseline (no changes)
2. Try `HIGHER_TF` sweep: "1h" → "15m" → "5m" (signal quality trade-off)
3. Try `WICK_TOLERANCE` sweep: 0, 1, 2, 3, 5 USD
4. Try `SUPERTREND_MULT`: 2.0 vs 2.5 vs 3.0 (trend filter tightness)
5. Try `RR_RATIO`: 1.5 vs 2.0 vs 2.5
6. Try `ENTRY_MODE`: "close" vs "retest"

### Phase 2: Refinement (Experiments 16–40)

7. Fine-tune `ATR_SL_MULTIPLIER` around best config
8. Try `SWING_LOOKBACK` variations
9. Try `EMA_PERIOD` and `SUPERTREND_PERIOD` combinations
10. Test `USE_DISPLACEMENT` and `DISPLACEMENT_THRESHOLD`

### Phase 3: Advanced Tactics (Experiments 40+)

11. Add custom `SIGNAL_FILTER_FN`: volume spikes, session filters, ADX strength
12. Try `USE_TRAILING_STOP` combinations
13. Try different `LOWER_TF` (5m instead of 1m for fewer false trend flips)
14. Combine best ideas from Phase 1+2

### Diagnostic Checks

- **Too few trades** (< 50): Filters too tight. Relax `WICK_TOLERANCE` or `DISPLACEMENT_THRESHOLD`
- **Too many trades** (> 500): Filters too loose. Tighten parameters or add displacement filter
- **Low win rate** (< 35%): Poor trend filter. Try different Supertrend params or require EMA confirm
- **Low average RR** (< 1.5): SL too tight or TP unreachable. Loosen `MIN_SL_ATR_FRACTION` or lower `RR_RATIO`
- **Large drawdown** (< -20%): Too much risk. Reduce `RISK_PER_TRADE_PCT` or `MAX_TRADES_PER_DAY`

## Experiment Logging

Every run is logged to `results.tsv` (tab-separated):

```
exp_id	score	n_trades	max_dd	status	description
1	0.312456	89	-12.40	keep	baseline
2	0.341200	102	-11.20	keep	HIGHER_TF 1h→15m + wick_tol 5→3
3	0.298000	74	-15.60	discard	USE_DISPLACEMENT=False (worse)
4	0.388000	134	-9.10	keep	SUPERTREND_MULT 3.0→2.0 + EMA_PERIOD 50→21
```

**Columns:**

- `exp_id`: Sequential experiment number
- `score`: SCORE value (6 decimal places)
- `n_trades`: Number of completed trades
- `max_dd`: Maximum drawdown percentage
- `status`: "keep", "discard", or "crash"
- `description`: Brief change description

**Note:** `results.tsv` is intentionally untracked (see `.gitignore`) so it accumulates all attempts including discards. Commits are made BEFORE each run to track parameter changes.

## Constraints

### What You Cannot Change

- ❌ `strategy_core.py` — Frozen. Never modify.
- ❌ The scoring metric
- ❌ The backtest engine
- ❌ The dataset or evaluation period
- ❌ Install new packages

### Simplicity Principle

All else being equal, simpler is better.

- A 0.01 score gain from adding 30 lines of complex logic → probably not worth it
- A 0.01 score gain from changing one parameter → definitely keep
- Removing a filter and getting equal/better score → always a simplification win

Trade complexity against marginal gains honestly.

## Dependencies

- **Python 3.7+**
- **numpy**, **pandas** (included in most Python distributions)

No external trading libraries or APIs required — pure backtest.

## Data Source

Historical BTCUSDT 1-minute OHLCV data is provided in CSV format:

- `BTCUSDT-1m-2022.csv`, `BTCUSDT-1m-2023.csv`, `BTCUSDT-1m-2024.csv`, `BTCUSDT-1m-2025.csv`
- Format: `open_time` (milliseconds UTC), `Open`, `High`, `Low`, `Close`, `Volume`

## Example: Custom Signal Filter

Add a volume spike filter to `strategy.py`:

```python
def volume_spike_filter(df_htf):
    """Require volume to be above 20-bar average."""
    avg_vol = df_htf["Volume"].rolling(20).mean()
    vol_spike = df_htf["Volume"] > 1.5 * avg_vol
    return vol_spike, vol_spike  # same condition for long and short

SIGNAL_FILTER_FN = volume_spike_filter
```

The filter receives `df_htf` with columns: `Open`, `High`, `Low`, `Close`, `Volume`, `atr`, `b2r`, `bull_wickless`, `bear_wickless`, `ltf_trend`, `swing_low`, `swing_high`, plus anything you compute.

## Citation & License

This research framework is part of quantitative trading research on scalping strategies. All code is provided as-is for educational and research purposes.

## Getting Started

1. **Ensure data files exist**: Check that CSV files are in the project root and readable
2. **Run baseline**: `python strategy.py > run.log 2>&1` and check `grep "^score:" run.log`
3. **Create `results.tsv`** with header: `exp_id	score	n_trades	max_dd	status	description`
4. **Modify `strategy.py`** with a single parameter change
5. **Commit before running**: `git add strategy.py && git commit -m "description of change"`
6. **Log results** to `results.tsv` with status (keep/discard/crash)
7. **Repeat** for systematic optimization

---

**Last updated:** April 2026
