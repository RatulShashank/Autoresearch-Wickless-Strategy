"""
strategy.py — AGENT'S SANDBOX.

This is the ONLY file the agent modifies.
The agent may change anything here: parameters, extra filters, new indicators,
signal logic extensions. It may NOT modify strategy_core.py.

Usage:
    python strategy.py

Prints a structured results block at the end (grep-parseable):
    score:          1.234567
    profit_factor:  1.450000
    win_rate:       42.50
    max_drawdown:   -8.30
    n_trades:       187
    n_signals:      310
    total_return:   14.20
    avg_rr:         1.820
    sharpe:         0.543
"""

import numpy as np
import pandas as pd
from strategy_core import run_experiment, print_result

# ══════════════════════════════════════════════════════════════════════════════
#  ⚙️  ALL PARAMETERS — AGENT EDITS ONLY BELOW THIS LINE
#  strategy_core.py is frozen. Only modify values in this file.
# ══════════════════════════════════════════════════════════════════════════════

# ── Data ──────────────────────────────────────────────────────────────────────
DATA_PATH    = "BTCUSDT-1m-2025.csv"   # path to local 1m OHLCV CSV
DATETIME_COL = "open_time"                        # datetime column name in CSV

# ── Timeframes ────────────────────────────────────────────────────────────────
LOWER_TF  = "5m"    # trend detection timeframe
HIGHER_TF = "15m"   # entry / wickless candle timeframe

# ── Wickless candle definition ────────────────────────────────────────────────
WICK_TOLERANCE = 1.0   # max wick in USD to count as "wickless" (0 = strict)

# ── Displacement filter ───────────────────────────────────────────────────────
USE_DISPLACEMENT       = True
DISPLACEMENT_THRESHOLD = 0.95   # body-to-range ratio: |close-open|/(high-low)

# ── Trend detection (LTF) ─────────────────────────────────────────────────────
SUPERTREND_PERIOD  = 10
SUPERTREND_MULT = 2.22
EMA_PERIOD         = 14
EMA_SLOPE_LOOKBACK = 3
REQUIRE_EMA_CONFIRM = True    # True = Supertrend AND EMA slope must agree

# ── Entry ─────────────────────────────────────────────────────────────────────
ENTRY_MODE          = "retest"   # "close" | "retest"
RETEST_TIMEOUT_BARS = 5         # bars to wait for retest before cancelling

# ── Stop loss ─────────────────────────────────────────────────────────────────
ATR_PERIOD           = 14
ATR_SL_MULTIPLIER    = 2.0      # SL = entry ± (ATR_SL_MULT × ATR)
MIN_SL_ATR_FRACTION  = 0.5      # floor: SL must be at least this × ATR
SWING_LOOKBACK       = 15       # bars back for swing high/low (on HTF)

# ── Take profit / trailing ────────────────────────────────────────────────────
USE_TRAILING_STOP  = False
RR_RATIO           = 2.0
TRAILING_ATR_MULT  = 2.0

# ── Position sizing & risk ────────────────────────────────────────────────────
RISK_PER_TRADE_PCT = 0.5        # % of capital to risk per trade
COMMISSION_PCT     = 0.05       # per side (0.05% = 5bps)
MAX_TRADES_PER_DAY = 4          # hard cap on daily entries
RUIN_GUARD_PCT     = 10.0       # halt trading below this % of initial capital

# ── Optional custom signal filter ────────────────────────────────────────────
# Set to None to disable, or define a function:
#   def my_filter(df_htf: pd.DataFrame) -> (long_mask: pd.Series, short_mask: pd.Series)
# Both masks are ANDed with the base wickless + trend conditions.
# df_htf has columns: Close, High, Low, Open, atr, b2r, bull_wickless, bear_wickless,
#                     ltf_trend, swing_low, swing_high, displaced, + anything you add.
# IMPORTANT: do not modify strategy_core.py to add indicators — add them here instead
#            by computing on df_htf inside the filter function.
def volume_spike_filter(df_htf):
    avg_vol = df_htf["Volume"].rolling(20).mean()
    vol_spike = df_htf["Volume"] > 1.5 * avg_vol
    return vol_spike, vol_spike   # same filter for long and short
SIGNAL_FILTER_FN = volume_spike_filter

# Example: add a volume spike filter
# def volume_spike_filter(df_htf):
#     avg_vol = df_htf["Volume"].rolling(20).mean()
#     vol_spike = df_htf["Volume"] > 1.5 * avg_vol
#     return vol_spike, vol_spike   # same filter for long and short
# SIGNAL_FILTER_FN = volume_spike_filter

# ══════════════════════════════════════════════════════════════════════════════
#  END OF PARAMETERS — do not modify below unless adding new indicator logic
# ══════════════════════════════════════════════════════════════════════════════

params = dict(
    DATA_PATH            = DATA_PATH,
    DATETIME_COL         = DATETIME_COL,
    LOWER_TF             = LOWER_TF,
    HIGHER_TF            = HIGHER_TF,
    WICK_TOLERANCE       = WICK_TOLERANCE,
    USE_DISPLACEMENT     = USE_DISPLACEMENT,
    DISPLACEMENT_THRESHOLD = DISPLACEMENT_THRESHOLD,
    SUPERTREND_PERIOD    = SUPERTREND_PERIOD,
    SUPERTREND_MULT      = SUPERTREND_MULT,
    EMA_PERIOD           = EMA_PERIOD,
    EMA_SLOPE_LOOKBACK   = EMA_SLOPE_LOOKBACK,
    REQUIRE_EMA_CONFIRM  = REQUIRE_EMA_CONFIRM,
    ENTRY_MODE           = ENTRY_MODE,
    RETEST_TIMEOUT_BARS  = RETEST_TIMEOUT_BARS,
    ATR_PERIOD           = ATR_PERIOD,
    ATR_SL_MULTIPLIER    = ATR_SL_MULTIPLIER,
    MIN_SL_ATR_FRACTION  = MIN_SL_ATR_FRACTION,
    SWING_LOOKBACK       = SWING_LOOKBACK,
    USE_TRAILING_STOP    = USE_TRAILING_STOP,
    RR_RATIO             = RR_RATIO,
    TRAILING_ATR_MULT    = TRAILING_ATR_MULT,
    RISK_PER_TRADE_PCT   = RISK_PER_TRADE_PCT,
    COMMISSION_PCT       = COMMISSION_PCT,
    MAX_TRADES_PER_DAY   = MAX_TRADES_PER_DAY,
    RUIN_GUARD_PCT       = RUIN_GUARD_PCT,
    SIGNAL_FILTER_FN     = SIGNAL_FILTER_FN,
)

if __name__ == "__main__":
    print(f"Running experiment: LTF={LOWER_TF} HTF={HIGHER_TF} "
          f"wick_tol={WICK_TOLERANCE} disp={USE_DISPLACEMENT}@{DISPLACEMENT_THRESHOLD} "
          f"ST={SUPERTREND_PERIOD}/{SUPERTREND_MULT} entry={ENTRY_MODE}")

    result = run_experiment(params, DATA_PATH)

    # ── Structured output block (grep-parseable by program.md loop) ──────────
    print("---")
    print(f"score:          {result['score']:.6f}")
    print(f"profit_factor:  {result['profit_factor']:.6f}")
    print(f"win_rate:       {result['win_rate']:.2f}")
    print(f"max_drawdown:   {result['max_drawdown_pct']:.2f}")
    print(f"n_trades:       {result['n_trades']}")
    print(f"n_signals:      {result['n_signals']}")
    print(f"total_return:   {result['total_return_pct']:.2f}")
    print(f"avg_rr:         {result['avg_rr']:.3f}")
    print(f"sharpe:         {result['sharpe']:.3f}")
    print(f"final_capital:  {result['final_capital']:.2f}")
    if "note" in result:
        print(f"note:           {result['note']}")
