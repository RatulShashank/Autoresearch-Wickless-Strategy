# wickless-autoresearch

Autonomous hyperparameter and strategy optimisation for the wickless candle scalping strategy on BTCUSDT.

---

## Setup (run once per research session)

1. **Agree on a run tag** based on today's date (e.g. `apr9`). The branch `autoresearch/<tag>` must not already exist.
2. **Create the branch**: `git checkout -b autoresearch/<tag>` from master.
3. **Read these files in full before doing anything else**:
   - `strategy_core.py` — frozen foundation: data loading, indicators, backtest engine, scoring metric. You will NEVER modify this.
   - `strategy.py` — your sandbox. The ONLY file you edit.
   - `README_autoresearch.md` — this file.
4. **Verify data**: Check that the CSV path in `DATA_PATH` inside `strategy.py` exists and is readable. If not, tell the human.
5. **Initialize results.tsv**: Create `results.tsv` with the header row only. The baseline is recorded on the first run.
6. **Confirm setup** with the human, then immediately begin the experiment loop.

---

## The Metric

**SCORE** (higher is better). Defined in `strategy_core.py` as:

```
SCORE = profit_factor × (win_rate / 50) / (1 + |max_drawdown_pct| / 20)
```

- **Profit Factor** is the primary driver. PF > 1 = profitable system.
- **Win Rate** term: normalised around 50%. At 50% WR → factor = 1.0. At 35% → 0.7. At 60% → 1.2.
- **Drawdown penalty**: 20% drawdown halves the score. Keeps you from finding high-return, high-risk solutions.
- **MIN_TRADES = 30**: fewer than 30 trades → score = 0 (statistically invalid).

Typical score ranges:
- Score < 0.3   → Poor
- Score 0.3–0.6 → Baseline territory  
- Score 0.6–1.0 → Good
- Score > 1.0   → Excellent

Extract the key metric from the log:
```bash
grep "^score:" run.log
```

---

## What You CAN Change (strategy.py only)

Everything in `strategy.py` is fair game:

**Timeframe parameters:**
- `LOWER_TF`, `HIGHER_TF` — try "1m"/"15m", "1m"/"1h", "5m"/"1h", "15m"/"4h"

**Wickless candle definition:**
- `WICK_TOLERANCE` — try 0 (strict), 1, 2, 3, 5, 10 USD

**Displacement filter:**
- `USE_DISPLACEMENT`, `DISPLACEMENT_THRESHOLD` — try thresholds 0.70–0.95

**Trend detection:**
- `SUPERTREND_PERIOD` — try 7, 10, 14, 20
- `SUPERTREND_MULT` — try 1.5, 2.0, 2.5, 3.0
- `EMA_PERIOD` — try 14, 21, 50
- `EMA_SLOPE_LOOKBACK` — try 2, 3, 5
- `REQUIRE_EMA_CONFIRM` — True/False

**Entry:**
- `ENTRY_MODE` — "close" or "retest"
- `RETEST_TIMEOUT_BARS` — try 3, 5, 8

**Stop loss:**
- `ATR_SL_MULTIPLIER` — try 1.0, 1.2, 1.5, 2.0
- `MIN_SL_ATR_FRACTION` — try 0.3, 0.5, 0.7
- `SWING_LOOKBACK` — try 5, 8, 10, 15 (on HTF bars)

**Take profit:**
- `RR_RATIO` — try 1.5, 2.0, 2.5, 3.0
- `USE_TRAILING_STOP` — True/False
- `TRAILING_ATR_MULT` — try 1.5, 2.0, 3.0

**Risk management:**
- `MAX_TRADES_PER_DAY` — try 2, 3, 4, 6
- `RISK_PER_TRADE_PCT` — try 0.3, 0.5, 1.0

**Custom signal filter (advanced):**
- Define a `SIGNAL_FILTER_FN` function in `strategy.py` to add extra conditions.
- Example ideas: volume spike filter, session time filter (NY hours only), ADX strength filter.
- The function receives `df_htf` and returns `(long_mask, short_mask)`.
- Compute any new indicators you need on `df_htf` inside the function.
- Do NOT add new indicator functions to `strategy_core.py`.

---

## What You CANNOT Change

- `strategy_core.py` — frozen. Never touch it.
- The scoring metric inside `strategy_core.py`.
- The backtest engine inside `strategy_core.py`.
- The dataset or evaluation period.
- You may not install new packages.

---

## Simplicity Criterion

All else being equal, simpler is better.

- A 0.01 SCORE gain from adding 30 lines of complex filter logic → probably not worth it.
- A 0.01 SCORE gain from changing one parameter → definitely keep.
- Removing a filter and getting equal/better score → always keep (simplification win).
- When evaluating marginal improvements, weigh complexity cost honestly.

---

## Output Format

Every run prints a structured block at the end:

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

Parse with: `grep "^score:\|^profit_factor:\|^win_rate:\|^n_trades:\|^max_drawdown:" run.log`

---

## Logging Results

Log every experiment to `results.tsv` (tab-separated — NO commas in descriptions).

Schema:
```
exp_id	score	n_trades	max_dd	status	description
```

- `exp_id`: sequential integer (1, 2, 3…)
- `score`: the SCORE value (6 decimal places)
- `n_trades`: number of trades executed
- `max_dd`: max_drawdown_pct (e.g. -8.30)
- `status`: `keep`, `discard`, or `crash`
- `description`: short text description of what changed

Example:
```
exp_id	score	n_trades	max_dd	status	description
1	0.312456	89	-12.40	keep	baseline
2	0.341200	102	-11.20	keep	HIGHER_TF 1h→15m + wick_tol 5→3
3	0.298000	74	-15.60	discard	USE_DISPLACEMENT=False (worse)
4	0.000000	0	0.00	crash	LOWER_TF=5m mismatched resample
5	0.388000	134	-9.10	keep	SUPERTREND_MULT 3.0→2.0 + EMA_PERIOD 50→21
```

**Do NOT commit results.tsv** — leave it untracked so it accumulates all attempts including discards.

Git commit every attempt BEFORE running, even if you expect it to fail.

---

## The Experiment Loop

**LOOP FOREVER** — never pause to ask the human if you should continue.

```
1. Check git state (current branch/commit).
2. Pick ONE experimental change. Edit strategy.py.
3. git add strategy.py && git commit -m "<short description of change>"
4. python strategy.py > run.log 2>&1
5. grep "^score:" run.log
   - If empty → CRASH. Run: tail -n 40 run.log (read the traceback, fix if trivial)
6. Log result to results.tsv
7. If score IMPROVED (higher):
     → keep the commit. Branch advances.
   If score EQUAL or WORSE:
     → git reset --hard HEAD~1 (revert to last kept state)
8. Repeat forever.
```

**Timeout**: If a run exceeds 10 minutes, kill it. Log as crash. Revert.

**Crash handling**:
- Trivial bug (typo, wrong column name)? Fix and re-run.
- Fundamentally broken (e.g. n_trades < MIN_TRADES always)? Log crash, revert, try something else.
- Score = 0 but no Python error? Check n_trades — likely fell below MIN_TRADES=30. Try relaxing filters.

---

## Research Strategy

Work systematically. The parameter space is large — don't random-walk. Use this ordering:

**Phase 1 — Establish baseline, then nail the big levers (experiments 1–15)**
1. Run baseline (strategy.py as-is) → record as exp #1
2. Try `HIGHER_TF`: "15m" → better signal quality, fewer but cleaner entries
3. Try `WICK_TOLERANCE` sweep: 0, 1, 2, 3, 5 → find the sweet spot
4. Try `SUPERTREND_MULT`: 2.0 vs 2.5 vs 3.0 → trend filter tightness
5. Try `RR_RATIO`: 1.5 vs 2.0 vs 2.5 → find the realized RR sweet spot
6. Try `ENTRY_MODE`: "retest" → typically improves RR but cuts trade count

**Phase 2 — Refine around best config (experiments 16–40)**
7. Fine-tune `ATR_SL_MULTIPLIER` around the best config
8. Try `SWING_LOOKBACK` variations
9. Try `EMA_PERIOD` and `SUPERTREND_PERIOD` combinations
10. Enable/disable `USE_DISPLACEMENT` and tune `DISPLACEMENT_THRESHOLD`

**Phase 3 — Advanced (experiments 40+)**
11. Add `SIGNAL_FILTER_FN` ideas: session filter, volume filter, ADX filter
12. Try `USE_TRAILING_STOP` combinations
13. Try different `LOWER_TF` for trend (5m instead of 1m — fewer false flips)
14. Try combining best ideas from Phase 1+2

**Key diagnostic checks:**
- If `n_trades` < 50: filters too tight. Relax WICK_TOLERANCE or DISPLACEMENT_THRESHOLD.
- If `n_trades` > 500: filters too loose. Tighten WICK_TOLERANCE or add displacement.
- If `win_rate` < 35%: trend filter is poor. Try different SUPERTREND params or require EMA confirm.
- If `avg_rr` < 1.5: SL too tight or TP unreachable. Loosen MIN_SL_ATR_FRACTION or lower RR_RATIO.
- If `max_drawdown` < -20%: too much risk. Reduce RISK_PER_TRADE_PCT or MAX_TRADES_PER_DAY.

---

## NEVER STOP

Once the experiment loop has started, do NOT pause to ask the human if you should continue. Do NOT ask "is this a good stopping point?" or "should I keep going?". The human may be away. You run until manually interrupted. If you run out of obvious ideas, try combining things that almost worked. Try more radical changes. Re-read strategy_core.py for new angles.

Each experiment takes ~60–90 seconds (no GPU needed — pure Python backtest). At that rate you can run ~50 experiments/hour and ~400 overnight.
