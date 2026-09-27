"""
Backtest with WALK-FORWARD validation + look-ahead guard + costs.

Honest-testing rules baked in:
  * Look-ahead guard: on each rebalance date, only bars strictly BEFORE that
    date are used to score. Never uses the outcome period's data to decide.
  * Walk-forward: tune window then a separate untouched test window.
  * Survivorship: pass a universe that INCLUDES delisted tickers for a true
    test (yfinance keeps many delisted .NS symbols; add them to the list).
  * Costs: brokerage + STT + slippage subtracted from every trade.

This runs on downloaded daily data (long-term/swing horizon).
Fill `download()` with real yfinance pulls when running locally.
"""
import numpy as np
import pandas as pd

COSTS = 0.0018  # ~0.18% round-trip (brokerage+STT+slippage), tune to your broker

def walk_forward_windows(dates, train_days=378, test_days=126, step=126):
    """Yield (train_slice, test_slice) index ranges, rolling forward."""
    i = 0
    while i + train_days + test_days <= len(dates):
        yield (slice(i, i+train_days), slice(i+train_days, i+train_days+test_days))
        i += step

def score_asof(daily_dict, asof_idx):
    """Score every stock using ONLY bars before asof_idx (look-ahead guard)."""
    scores = {}
    for sym, df in daily_dict.items():
        hist = df.iloc[:asof_idx]          # strict cut — nothing at/after asof
        if len(hist) < 200:
            continue
        c = hist["Close"]
        mom = c.iloc[-1]/c.iloc[-126]-1
        trend = 1 if c.iloc[-1] > c.rolling(200).mean().iloc[-1] else 0
        scores[sym] = 0.6*mom + 0.4*trend
    return scores

def forward_return(df, start_idx, hold=126):
    c = df["Close"]
    if start_idx+hold >= len(c): return None
    return c.iloc[start_idx+hold]/c.iloc[start_idx]-1 - COSTS

def backtest(daily_dict, top_n=10):
    any_df = next(iter(daily_dict.values()))
    dates = any_df.index
    port, bench = [], []
    for train, test in walk_forward_windows(dates):
        asof = test.start                    # decide at test-window open
        sc = score_asof(daily_dict, asof)    # look-ahead-safe
        if not sc: continue
        ranked = sorted(sc, key=sc.get, reverse=True)[:top_n]
        rets = [r for s in ranked if (r:=forward_return(daily_dict[s], asof)) is not None]
        allr = [r for s in sc if (r:=forward_return(daily_dict[s], asof)) is not None]
        if rets: port.append(np.mean(rets))
        if allr: bench.append(np.mean(allr))
    port, bench = np.array(port), np.array(bench)
    return {
        "windows": len(port),
        "strategy_avg_%": round(port.mean()*100,2) if len(port) else None,
        "benchmark_avg_%": round(bench.mean()*100,2) if len(bench) else None,
        "excess_%": round((port.mean()-bench.mean())*100,2) if len(port) else None,
        "win_rate_%": round((port>0).mean()*100,1) if len(port) else None,
        "sharpe": round(port.mean()/(port.std()+1e-9),2) if len(port) else None,
    }

if __name__ == "__main__":
    # Demo with synthetic multi-stock data to prove the walk-forward loop.
    rng = np.random.default_rng(3)
    dd = {}
    for i in range(20):
        n=760; idx=pd.date_range("2022-01-01",periods=n,freq="D")
        drift = rng.normal(0.0004,0.0002)      # some stocks genuinely trend
        px = 100*(1+np.cumsum(rng.normal(drift,0.015,n)))
        dd[f"S{i}"]=pd.DataFrame({"Close":px}, index=idx)
    print("Walk-forward backtest (synthetic):")
    for k,v in backtest(dd).items():
        print(f"  {k:18s}: {v}")
