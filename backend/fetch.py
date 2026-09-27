"""
Data fetch layer — free online sources, no broker account.
  - Prices/volume  -> Yahoo Finance via yfinance (daily + delayed intraday)
  - Fundamentals   -> yfinance .info (ROE, D/E, margins, etc.)

NOTE ON "REAL-TIME": Yahoo data is delayed ~15 min. Fine for long-term and
for a delayed intraday WATCHLIST; not tradeable for true tick-level intraday.

To expand universe to full NSE, replace universe list with:
    pd.read_csv("https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv")
    -> use the SYMBOL column, append ".NS"
"""
import time
import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None  # allows import without the dep for offline testing


def _rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - 100 / (1 + rs)


def _atr_pct(df, period=14):
    hl = df["High"] - df["Low"]
    hc = (df["High"] - df["Close"].shift()).abs()
    lc = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return (atr / df["Close"] * 100)


def fetch_daily(symbol, period="2y"):
    """Daily OHLCV + derived technicals for one NSE symbol."""
    t = yf.Ticker(f"{symbol}.NS")
    df = t.history(period=period, interval="1d", auto_adjust=True)
    if df.empty:
        return None
    df["RSI"] = _rsi(df["Close"])
    df["ATR%"] = _atr_pct(df)
    df["VOL20"] = df["Volume"].rolling(20).mean()
    return df


def fetch_intraday(symbol, period="5d", interval="5m"):
    """Delayed intraday bars (~15 min lag) for the watchlist engine."""
    t = yf.Ticker(f"{symbol}.NS")
    df = t.history(period=period, interval=interval, auto_adjust=True)
    return None if df.empty else df


def fetch_fundamentals(symbol):
    """Fundamentals from yfinance .info. Free but sometimes patchy —
    missing fields are returned as NaN and the scorer handles them."""
    info = yf.Ticker(f"{symbol}.NS").info
    g = lambda k: info.get(k, np.nan)
    return {
        "roe": (g("returnOnEquity") or np.nan) * 100 if g("returnOnEquity") else np.nan,
        "de": g("debtToEquity") / 100 if g("debtToEquity") else np.nan,
        "earn_cagr": (g("earningsGrowth") or np.nan) * 100 if g("earningsGrowth") else np.nan,
        "margin": (g("profitMargins") or np.nan) * 100 if g("profitMargins") else np.nan,
        "pe": g("trailingPE"),
        "peg": g("pegRatio"),
        "promoter_pct": (g("heldPercentInsiders") or np.nan) * 100 if g("heldPercentInsiders") else np.nan,
        "div_yield": (g("dividendYield") or 0),
        "name": g("shortName") or symbol,
        "price": g("currentPrice") or g("previousClose"),
    }


def fetch_all(symbols, kind="long", pause=0.4):
    """Loop the universe with polite pauses (Yahoo rate-limits bursts)."""
    out = {}
    for s in symbols:
        try:
            if kind == "long":
                out[s] = {"fund": fetch_fundamentals(s), "daily": fetch_daily(s)}
            else:
                out[s] = {"intra": fetch_intraday(s), "daily": fetch_daily(s, period="3mo")}
        except Exception as e:
            print(f"  ! {s}: {e}")
        time.sleep(pause)
    return out
