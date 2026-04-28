"""
strategy_core.py — FROZEN FOUNDATION. DO NOT MODIFY.

This is the ground-truth evaluator for the wickless candle scalping strategy.
It contains:
  - Data loading and resampling
  - All indicator functions (ATR, Supertrend, EMA, wickless detection, B2R, swings)
  - The backtest execution engine
  - The composite scoring metric (SCORE — higher is better)
  - A run_experiment() entry point that strategy.py calls

The agent (strategy.py) may NEVER touch this file.
Changing this file invalidates all prior results.

FIXED CONSTANTS (do not change):
  EVAL_YEAR      — the fixed dataset year used for all scoring
  MIN_TRADES     — minimum trades required for a valid score
  SCORE()        — composite metric: Profit Factor × Win Rate / |Max Drawdown|
"""

# ── DO NOT MODIFY — frozen baseline ─────────────────────────────────────────

import math
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── Fixed evaluation constants ───────────────────────────────────────────────
EVAL_YEAR   = 2025       # fixed dataset year — every run evaluates the same data
MIN_TRADES  = 30         # minimum trades for result to be valid (not noise)
INITIAL_CAPITAL = 10_000 # fixed starting capital for all experiments


# ── Data loading ─────────────────────────────────────────────────────────────

TF_MAP = {
    "1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
    "1h": "1h",   "4h": "4h",   "1d": "1D"
}

def load_data(local_path: str, datetime_col: str = "open_time") -> pd.DataFrame:
    """Load 1m OHLCV CSV. Returns df with DatetimeIndex (UTC)."""
    df = pd.read_csv(local_path)
    df[datetime_col] = pd.to_datetime(df[datetime_col], unit="ms", utc=True)
    df = df.set_index(datetime_col)
    df.columns = [c.strip().title() for c in df.columns]
    df = df[["Open", "High", "Low", "Close", "Volume"]]
    return df


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {"Open": "first", "High": "max", "Low": "min",
           "Close": "last", "Volume": "sum"}
    return df.resample(rule).agg(agg).dropna()


# ── Indicators (signatures fixed — implementations must not change) ──────────

def compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
    hi, lo, cl = df["High"], df["Low"], df["Close"]
    prev_cl = cl.shift(1)
    tr = pd.concat([(hi - lo), (hi - prev_cl).abs(), (lo - prev_cl).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def compute_supertrend(df: pd.DataFrame, period: int, multiplier: float):
    """Returns (supertrend_line, direction) where direction +1=bull, -1=bear."""
    hi, lo, cl = df["High"], df["Low"], df["Close"]
    atr = compute_atr(df, period)
    hl2 = (hi + lo) / 2
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr
    upper = basic_upper.copy()
    lower = basic_lower.copy()
    supertrend = pd.Series(np.nan, index=df.index)
    direction  = pd.Series(0, index=df.index)
    for i in range(1, len(df)):
        upper.iloc[i] = basic_upper.iloc[i] if (basic_upper.iloc[i] < upper.iloc[i-1] or cl.iloc[i-1] > upper.iloc[i-1]) else upper.iloc[i-1]
        lower.iloc[i] = basic_lower.iloc[i] if (basic_lower.iloc[i] > lower.iloc[i-1] or cl.iloc[i-1] < lower.iloc[i-1]) else lower.iloc[i-1]
        if supertrend.iloc[i-1] == upper.iloc[i-1]:
            direction.iloc[i] = -1 if cl.iloc[i] <= upper.iloc[i] else 1
        else:
            direction.iloc[i] = 1 if cl.iloc[i] >= lower.iloc[i] else -1
        supertrend.iloc[i] = lower.iloc[i] if direction.iloc[i] == 1 else upper.iloc[i]
    return supertrend, direction


def compute_ema_slope(df: pd.DataFrame, period: int, lookback: int):
    """Returns (slope_series, ema_series) where slope +1=rising, -1=falling."""
    ema = df["Close"].ewm(span=period, adjust=False).mean()
    delta = ema - ema.shift(lookback)
    slope = pd.Series(np.where(delta > 0, 1, np.where(delta < 0, -1, 0)), index=df.index).fillna(0).astype(int)
    return slope, ema


def detect_wickless(df: pd.DataFrame, tolerance: float):
    """
    Returns (bull_wickless, bear_wickless, bottom_wick, top_wick).
    Bull wickless: no bottom wick (bullish candle, bottom_wick <= tolerance).
    Bear wickless: no top wick (bearish candle, top_wick <= tolerance).
    """
    bottom_wick = df[["Open", "Close"]].min(axis=1) - df["Low"]
    top_wick    = df["High"] - df[["Open", "Close"]].max(axis=1)
    bull_wickless = (bottom_wick <= tolerance) & (df["Close"] > df["Open"])
    bear_wickless = (top_wick    <= tolerance) & (df["Close"] < df["Open"])
    return bull_wickless, bear_wickless, bottom_wick, top_wick


def compute_b2r(df: pd.DataFrame) -> pd.Series:
    """Body-to-Range ratio: |close-open| / (high-low). 0 for doji."""
    body   = (df["Close"] - df["Open"]).abs()
    range_ = df["High"] - df["Low"]
    return (body / range_.replace(0, np.nan)).fillna(0)


def compute_swings(df: pd.DataFrame, lookback: int):
    """Returns (swing_low, swing_high) as rolling min/max over lookback bars."""
    n = len(df)
    swing_low  = pd.Series(np.nan, index=df.index)
    swing_high = pd.Series(np.nan, index=df.index)
    lows  = df["Low"].values
    highs = df["High"].values
    for i in range(lookback, n):
        swing_low.iloc[i]  = np.min(lows[i-lookback:i])
        swing_high.iloc[i] = np.max(highs[i-lookback:i])
    return swing_low, swing_high


# ── Backtest engine (GROUND TRUTH — never modify) ────────────────────────────

def run_backtest(df: pd.DataFrame, params: dict) -> tuple:
    """
    Fixed bar-by-bar backtest engine.

    Args:
        df         : OHLCV dataframe with columns:
                     Close, High, Low, Open, atr, raw_signal, swing_low, swing_high
                     (plus any extra columns the strategy adds)
        params     : dict with required keys:
                     ATR_SL_MULTIPLIER, MIN_SL_ATR_FRACTION, RR_RATIO,
                     USE_TRAILING_STOP, TRAILING_ATR_MULT, ENTRY_MODE,
                     RETEST_TIMEOUT_BARS, RISK_PER_TRADE_PCT, COMMISSION_PCT,
                     MAX_TRADES_PER_DAY, RUIN_GUARD_PCT

    Returns:
        (trades: list[dict], equity_curve: pd.Series)
    """
    ATR_SL_MULTIPLIER   = params["ATR_SL_MULTIPLIER"]
    MIN_SL_ATR_FRACTION = params["MIN_SL_ATR_FRACTION"]
    RR_RATIO            = params["RR_RATIO"]
    USE_TRAILING_STOP   = params["USE_TRAILING_STOP"]
    TRAILING_ATR_MULT   = params["TRAILING_ATR_MULT"]
    ENTRY_MODE          = params["ENTRY_MODE"]
    RETEST_TIMEOUT_BARS = params["RETEST_TIMEOUT_BARS"]
    RISK_PER_TRADE_PCT  = params["RISK_PER_TRADE_PCT"]
    COMMISSION_PCT      = params["COMMISSION_PCT"]
    MAX_TRADES_PER_DAY  = params["MAX_TRADES_PER_DAY"]
    RUIN_GUARD_PCT      = params["RUIN_GUARD_PCT"]

    capital             = INITIAL_CAPITAL
    commission_per_side = COMMISSION_PCT / 100
    ruin_threshold      = INITIAL_CAPITAL * (RUIN_GUARD_PCT / 100)

    trades, equity = [], []

    in_trade = False
    direction = entry_price = sl_price = tp_price = trail_stop = position_size = sl_distance = 0.0
    entry_time = None
    entry_idx  = 0

    pending_signal = pending_body_hi = pending_body_lo = pending_atr = pending_bar = 0

    current_day  = None
    trades_today = 0

    close_arr  = df["Close"].values
    high_arr   = df["High"].values
    low_arr    = df["Low"].values
    open_arr   = df["Open"].values
    signal_arr = df["raw_signal"].values
    atr_arr    = df["atr"].values
    swl_arr    = df["swing_low"].values
    swh_arr    = df["swing_high"].values
    idx_arr    = df.index

    def _sl_dist(entry, sig, atr, swl, swh):
        atr_dist    = ATR_SL_MULTIPLIER * atr
        min_sl_dist = MIN_SL_ATR_FRACTION * atr
        if sig == 1:
            swing_dist = entry - swl if (not np.isnan(swl) and swl > 0) else atr_dist
        else:
            swing_dist = swh - entry if (not np.isnan(swh) and swh > 0) else atr_dist
        return max(min(atr_dist, max(swing_dist, min_sl_dist)), min_sl_dist)

    for i in range(1, len(df)):
        c, h, l, o = close_arr[i], high_arr[i], low_arr[i], open_arr[i]
        atr_val, sig, bar_dt = atr_arr[i], signal_arr[i], idx_arr[i]

        equity.append(capital)
        if capital <= ruin_threshold:
            continue

        bar_day = bar_dt.date() if hasattr(bar_dt, "date") else str(bar_dt)[:10]
        if bar_day != current_day:
            current_day = bar_day
            trades_today = 0

        # ── Manage open trade ─────────────────────────────────────────────────
        if in_trade:
            hit_sl = hit_tp = False
            exit_p = np.nan
            if USE_TRAILING_STOP:
                trail_dist = TRAILING_ATR_MULT * atr_val
                if direction == 1:
                    trail_stop = max(trail_stop, c - trail_dist)
                    if l <= trail_stop: hit_sl = True; exit_p = trail_stop
                else:
                    trail_stop = min(trail_stop, c + trail_dist)
                    if h >= trail_stop: hit_sl = True; exit_p = trail_stop
            else:
                if direction == 1:
                    if l <= sl_price:   hit_sl = True; exit_p = sl_price
                    elif h >= tp_price: hit_tp = True; exit_p = tp_price
                else:
                    if h >= sl_price:   hit_sl = True; exit_p = sl_price
                    elif l <= tp_price: hit_tp = True; exit_p = tp_price

            if hit_sl or hit_tp:
                pnl_pts   = (exit_p - entry_price) * direction
                pnl_usd   = pnl_pts * position_size
                comm_total = commission_per_side * (entry_price + exit_p) * position_size
                net_pnl   = pnl_usd - comm_total
                capital  += net_pnl
                trades.append({
                    "entry_time": entry_time, "exit_time": bar_dt,
                    "direction": "LONG" if direction == 1 else "SHORT",
                    "entry_price": round(entry_price, 2), "exit_price": round(exit_p, 2),
                    "sl_distance": round(sl_distance, 2), "position_size": round(position_size, 6),
                    "pnl_usd": round(net_pnl, 2), "commission": round(comm_total, 4),
                    "result": "WIN" if net_pnl > 0 else "LOSS",
                    "bars_held": i - entry_idx,
                    "exit_reason": "TP" if hit_tp else ("TRAIL_SL" if USE_TRAILING_STOP else "SL"),
                    "capital_after": round(capital, 2),
                })
                in_trade = False
            continue

        # ── Pending retest ────────────────────────────────────────────────────
        if ENTRY_MODE == "retest" and pending_signal != 0:
            bars_since = i - pending_bar
            entered = False
            if pending_signal == 1:
                if l <= pending_body_hi and h >= pending_body_lo:
                    entry_price = pending_body_hi; entered = True
            else:
                if h >= pending_body_lo and l <= pending_body_hi:
                    entry_price = pending_body_lo; entered = True
            if entered:
                direction     = pending_signal
                sl_dist       = _sl_dist(entry_price, direction, pending_atr, swl_arr[i], swh_arr[i])
                sl_distance   = sl_dist
                sl_price      = entry_price - direction * sl_dist
                tp_price      = entry_price + direction * RR_RATIO * sl_dist
                risk_amt      = min(capital * (RISK_PER_TRADE_PCT / 100), capital * 0.5)
                position_size = risk_amt / sl_dist
                trail_stop    = entry_price - direction * TRAILING_ATR_MULT * pending_atr
                entry_time    = bar_dt; entry_idx = i; in_trade = True; trades_today += 1
                pending_signal = 0
            elif bars_since >= RETEST_TIMEOUT_BARS:
                pending_signal = 0
            continue

        # ── New signal ────────────────────────────────────────────────────────
        if sig != 0 and not in_trade and trades_today < MAX_TRADES_PER_DAY:
            if ENTRY_MODE == "close":
                direction     = sig
                entry_price   = c
                sl_dist       = _sl_dist(entry_price, direction, atr_val, swl_arr[i], swh_arr[i])
                sl_distance   = sl_dist
                sl_price      = entry_price - direction * sl_dist
                tp_price      = entry_price + direction * RR_RATIO * sl_dist
                risk_amt      = min(capital * (RISK_PER_TRADE_PCT / 100), capital * 0.5)
                position_size = risk_amt / sl_dist
                trail_stop    = entry_price - direction * TRAILING_ATR_MULT * atr_val
                entry_time    = bar_dt; entry_idx = i; in_trade = True; trades_today += 1
            elif ENTRY_MODE == "retest":
                pending_signal  = sig
                pending_body_hi = max(o, c)
                pending_body_lo = min(o, c)
                pending_atr     = atr_val
                pending_bar     = i

    while len(equity) < len(df):
        equity.append(capital)
    return trades, pd.Series(equity[: len(df)], index=df.index)


# ── Composite scoring metric (GROUND TRUTH — never modify) ───────────────────

def compute_score(trades: list, equity: pd.Series) -> dict:
    """
    Compute the composite strategy score and all sub-metrics.

    Primary optimisation target: SCORE (higher is better).

    SCORE formula:
        SCORE = profit_factor * (win_rate / 50) / (1 + abs(max_drawdown_pct) / 20)

    Rationale:
        - Profit Factor (PF) is the primary driver. PF > 1 = profitable.
        - Win rate term normalises around 50% (1.0 at 50% WR).
        - Drawdown penalty: a 20% DD halves the score.
        - MIN_TRADES guard: fewer than MIN_TRADES returns score = 0.

    Returns dict with: score, profit_factor, win_rate, max_drawdown_pct,
                       expectancy_usd, total_return_pct, n_trades, avg_rr,
                       sharpe, calmar, final_capital
    """
    if len(trades) < MIN_TRADES:
        return {
            "score": 0.0, "profit_factor": 0.0, "win_rate": 0.0,
            "max_drawdown_pct": 0.0, "expectancy_usd": 0.0,
            "total_return_pct": 0.0, "n_trades": len(trades),
            "avg_rr": 0.0, "sharpe": 0.0, "calmar": 0.0,
            "final_capital": INITIAL_CAPITAL,
            "note": f"INVALID: fewer than {MIN_TRADES} trades",
        }

    df_t   = pd.DataFrame(trades)
    wins   = df_t[df_t["result"] == "WIN"]
    losses = df_t[df_t["result"] == "LOSS"]
    n      = len(df_t)

    win_rate = len(wins) / n * 100
    avg_win  = wins["pnl_usd"].mean()  if len(wins)  > 0 else 0.0
    avg_loss = losses["pnl_usd"].mean() if len(losses) > 0 else 0.0
    gross_win  = wins["pnl_usd"].sum()
    gross_loss = abs(losses["pnl_usd"].sum())

    profit_factor = gross_win / gross_loss if gross_loss > 0 else (np.inf if gross_win > 0 else 0.0)
    profit_factor = min(profit_factor, 10.0)  # cap at 10 to avoid inf distorting the score

    expectancy = (win_rate / 100) * avg_win + (1 - win_rate / 100) * avg_loss
    total_return_pct = (equity.iloc[-1] / INITIAL_CAPITAL - 1) * 100

    roll_max  = equity.cummax()
    drawdown  = (equity - roll_max) / roll_max * 100
    max_dd    = drawdown.min()

    daily_ret = equity.pct_change().dropna()
    sharpe = (daily_ret.mean() / daily_ret.std() * math.sqrt(252 * 1440)) if daily_ret.std() > 0 else 0.0
    calmar = total_return_pct / abs(max_dd) if max_dd != 0 else 0.0
    avg_rr = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0

    # Composite score
    wr_factor  = win_rate / 50.0
    dd_penalty = 1 + abs(max_dd) / 20.0
    score      = (profit_factor * wr_factor) / dd_penalty
    score      = max(score, 0.0)

    return {
        "score":              round(score, 6),
        "profit_factor":      round(profit_factor, 4),
        "win_rate":           round(win_rate, 2),
        "max_drawdown_pct":   round(max_dd, 2),
        "expectancy_usd":     round(expectancy, 4),
        "total_return_pct":   round(total_return_pct, 2),
        "n_trades":           n,
        "avg_rr":             round(avg_rr, 3),
        "sharpe":             round(sharpe, 3),
        "calmar":             round(calmar, 3),
        "final_capital":      round(equity.iloc[-1], 2),
    }


# ── Master entry point called by strategy.py ─────────────────────────────────

def run_experiment(params: dict, data_path: str) -> dict:
    """
    Full pipeline: load → build TFs → indicators → signals → backtest → score.

    Args:
        params    : full parameter dict from strategy.py (see strategy.py for keys)
        data_path : path to local 1m OHLCV CSV

    Returns:
        results dict with 'score', all sub-metrics, and 'n_signals'
    """
    # ── Load data ─────────────────────────────────────────────────────────────
    df_raw = load_data(data_path, params.get("DATETIME_COL", "open_time"))
    df_ltf = df_raw.copy()
    htf_rule = TF_MAP.get(params["HIGHER_TF"], params["HIGHER_TF"])
    df_htf   = resample_ohlcv(df_ltf, htf_rule)

    # ── LTF: trend detection ──────────────────────────────────────────────────
    _, st_dir_ltf = compute_supertrend(df_ltf, params["SUPERTREND_PERIOD"], params["SUPERTREND_MULT"])
    ema_slope_ltf, _ = compute_ema_slope(df_ltf, params["EMA_PERIOD"], params["EMA_SLOPE_LOOKBACK"])
    df_ltf["st_direction"] = st_dir_ltf
    df_ltf["ema_slope"]    = ema_slope_ltf
    if params["REQUIRE_EMA_CONFIRM"]:
        df_ltf["ltf_trend"] = np.where(
            (df_ltf["st_direction"] == 1)  & (df_ltf["ema_slope"] == 1),  1,
            np.where((df_ltf["st_direction"] == -1) & (df_ltf["ema_slope"] == -1), -1, 0))
    else:
        df_ltf["ltf_trend"] = df_ltf["st_direction"]

    # ── HTF: wickless detection + SL indicators ───────────────────────────────
    df_htf["atr"]         = compute_atr(df_htf, params["ATR_PERIOD"])
    df_htf["b2r"]         = compute_b2r(df_htf)
    bull_wl, bear_wl, _, _ = detect_wickless(df_htf, params["WICK_TOLERANCE"])
    df_htf["bull_wickless"] = bull_wl
    df_htf["bear_wickless"] = bear_wl
    df_htf["displaced"]     = df_htf["b2r"] >= params["DISPLACEMENT_THRESHOLD"] if params["USE_DISPLACEMENT"] else True
    df_htf["swing_low"], df_htf["swing_high"] = compute_swings(df_htf, params["SWING_LOOKBACK"])

    # ── Merge LTF trend onto HTF ──────────────────────────────────────────────
    ltf_trend_df = df_ltf[["ltf_trend"]].reset_index()
    ltf_trend_df.columns = ["timestamp", "ltf_trend"]
    htf_reset = df_htf.reset_index()
    htf_reset.columns.values[0] = "timestamp"
    merged = pd.merge_asof(
        htf_reset.sort_values("timestamp"),
        ltf_trend_df.sort_values("timestamp"),
        on="timestamp", direction="backward"
    ).set_index("timestamp")
    df_htf = merged

    # ── Signal generation ─────────────────────────────────────────────────────
    disp_filter = df_htf["displaced"] if params["USE_DISPLACEMENT"] else pd.Series(True, index=df_htf.index)
    long_cond   = df_htf["bull_wickless"] & disp_filter & (df_htf["ltf_trend"] == 1)
    short_cond  = df_htf["bear_wickless"] & disp_filter & (df_htf["ltf_trend"] == -1)

    # ── Optional extra filters injected by strategy.py ───────────────────────
    # strategy.py may add a 'SIGNAL_FILTER_FN' key: a callable(df_htf) → (long_mask, short_mask)
    if "SIGNAL_FILTER_FN" in params and params["SIGNAL_FILTER_FN"] is not None:
        try:
            extra_long, extra_short = params["SIGNAL_FILTER_FN"](df_htf)
            long_cond  = long_cond  & extra_long
            short_cond = short_cond & extra_short
        except Exception as e:
            print(f"  WARNING: SIGNAL_FILTER_FN raised {e} — ignoring extra filter")

    df_htf["raw_signal"] = 0
    df_htf.loc[long_cond,  "raw_signal"] =  1
    df_htf.loc[short_cond, "raw_signal"] = -1

    n_signals = int((long_cond | short_cond).sum())

    # ── Run backtest ──────────────────────────────────────────────────────────
    trades, equity = run_backtest(df_htf, params)

    # ── Score ─────────────────────────────────────────────────────────────────
    result = compute_score(trades, equity)
    result["n_signals"] = n_signals
    return result


# ── Print helpers (for strategy.py to use) ────────────────────────────────────

def print_result(result: dict, label: str = ""):
    tag = f" [{label}]" if label else ""
    print(f"\n{'─'*55}")
    print(f"  RESULT{tag}")
    print(f"{'─'*55}")
    for k, v in result.items():
        print(f"  {k:<22} {v}")
    print(f"{'─'*55}\n")
