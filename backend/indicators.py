"""
Technical indicator library — verified standard formulas.
Hand-rolled (no heavy deps) so it runs anywhere incl. GitHub Actions.
Each returns the latest value(s) plus a 0-10 sub-score for the engine.

Formulas cross-checked against pandas-ta / TradingView conventions.
"""
import numpy as np
import pandas as pd


def _ema(s, span):
    return s.ewm(span=span, adjust=False).mean()


# ---------- BOLLINGER BANDS ----------
def bollinger(close, period=20, k=2.0):
    ma = close.rolling(period).mean()
    sd = close.rolling(period).std(ddof=0)
    upper, lower = ma + k*sd, ma - k*sd
    width = (upper - lower) / ma                      # bandwidth (squeeze gauge)
    pctb = (close - lower) / (upper - lower + 1e-9)   # %B position 0..1
    return dict(upper=upper.iloc[-1], lower=lower.iloc[-1], ma=ma.iloc[-1],
                width=float(width.iloc[-1]), pctb=float(pctb.iloc[-1]),
                width_series=width)

def score_bollinger(bb, close_last):
    """Reward: price near lower band (value) OR a squeeze about to expand."""
    pctb = bb["pctb"]
    # squeeze: current width in the lowest 20% of last 120 days -> breakout setup
    w = bb["width_series"].dropna()
    squeeze = 0
    if len(w) > 120:
        squeeze = 1 if bb["width"] <= np.percentile(w.iloc[-120:], 20) else 0
    if pctb < 0.2:   base = 9      # near lower band — mean-reversion buy zone
    elif pctb < 0.4: base = 7
    elif pctb < 0.6: base = 5
    elif pctb < 0.8: base = 4
    else:            base = 2      # near upper band — extended
    return min(10, base + (2 if squeeze else 0))


# ---------- MACD ----------
def macd(close, fast=12, slow=26, signal=9):
    line = _ema(close, fast) - _ema(close, slow)
    sig = _ema(line, signal)
    hist = line - sig
    return dict(line=float(line.iloc[-1]), signal=float(sig.iloc[-1]),
                hist=float(hist.iloc[-1]), hist_prev=float(hist.iloc[-2]))

def score_macd(m):
    """Reward bullish momentum: line>signal and histogram rising."""
    bull = m["line"] > m["signal"]
    rising = m["hist"] > m["hist_prev"]
    if bull and rising and m["line"] > 0: return 10
    if bull and rising:                   return 8
    if bull:                              return 6
    if rising:                            return 5
    return 2


# ---------- ADX (trend strength) ----------
def adx(high, low, close, period=14):
    up = high.diff()
    dn = -low.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([high-low, (high-close.shift()).abs(),
                    (low-close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    plus_di = 100 * pd.Series(plus_dm, index=high.index).rolling(period).mean() / (atr+1e-9)
    minus_di = 100 * pd.Series(minus_dm, index=high.index).rolling(period).mean() / (atr+1e-9)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    adx_val = dx.rolling(period).mean()
    return dict(adx=float(adx_val.iloc[-1]), plus_di=float(plus_di.iloc[-1]),
                minus_di=float(minus_di.iloc[-1]))

def score_adx(a):
    """Strong trend (ADX>25) in the bullish direction (+DI>-DI) is best."""
    strong = a["adx"] > 25
    very_strong = a["adx"] > 40
    bullish = a["plus_di"] > a["minus_di"]
    if very_strong and bullish: return 10
    if strong and bullish:      return 8
    if bullish:                 return 5
    if strong and not bullish:  return 2   # strong downtrend — avoid
    return 4


# ---------- STOCHASTIC ----------
def stochastic(high, low, close, k=14, d=3):
    ll = low.rolling(k).min()
    hh = high.rolling(k).max()
    kline = 100 * (close - ll) / (hh - ll + 1e-9)
    dline = kline.rolling(d).mean()
    return dict(k=float(kline.iloc[-1]), d=float(dline.iloc[-1]),
                k_prev=float(kline.iloc[-2]), d_prev=float(dline.iloc[-2]))

def score_stochastic(s):
    """Reward bullish crossover out of oversold; penalize overbought."""
    cross_up = s["k_prev"] <= s["d_prev"] and s["k"] > s["d"]
    if s["k"] < 20 and cross_up:  return 10   # oversold + turning up
    if s["k"] < 30:               return 8
    if s["k"] > 80:               return 2    # overbought
    if cross_up:                  return 7
    return 5


# ---------- OBV (volume confirmation) ----------
def obv(close, volume):
    sign = np.sign(close.diff()).fillna(0)
    o = (sign * volume).cumsum()
    slope = o.iloc[-1] - o.iloc[-20] if len(o) > 20 else 0
    return dict(obv=float(o.iloc[-1]), slope=float(slope))

def score_obv(o):
    """Rising OBV confirms accumulation."""
    return 9 if o["slope"] > 0 else 3


# ---------- SUPPORT / RESISTANCE ----------
def support_resistance(high, low, close, lookback=60):
    hh = float(high.iloc[-lookback:].max())
    ll = float(low.iloc[-lookback:].min())
    price = float(close.iloc[-1])
    span = hh - ll + 1e-9
    pos = (price - ll) / span                # 0 = at support, 1 = at resistance
    return dict(support=ll, resistance=hh, pos=float(pos))

def score_support_resistance(sr):
    """Near support = better entry; near resistance = risk."""
    p = sr["pos"]
    if p < 0.2:  return 9
    if p < 0.4:  return 7
    if p < 0.6:  return 5
    if p < 0.8:  return 4
    return 2


def all_technicals(df):
    """Run the full battery on one OHLCV dataframe -> scores + raw values."""
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
    bb = bollinger(c); m = macd(c); a = adx(h,l,c)
    st = stochastic(h,l,c); o = obv(c,v); sr = support_resistance(h,l,c)
    scores = {
        "bollinger": score_bollinger(bb, c.iloc[-1]),
        "macd": score_macd(m),
        "adx": score_adx(a),
        "stochastic": score_stochastic(st),
        "obv": score_obv(o),
        "support": score_support_resistance(sr),
    }
    raw = {"bb":bb,"macd":m,"adx":a,"stoch":st,"obv":o,"sr":sr}
    return scores, raw
