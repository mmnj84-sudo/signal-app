"""
Scoring engine v2 — full fundamentals + full technicals, with per-engine tilt:
  INTRADAY  -> momentum tilt (buy strength: MACD, ADX, OBV, vol, rel-strength)
  LONG-TERM -> value tilt   (fundamentals gate + buy weakness: Bollinger, Stoch, S/R)

Backtest-informed: `backtest_multiplier` lets a stock's historical
strategy-fit nudge its live score (see engine note + backtest.py).
Look-ahead guard preserved: technicals computed on closed bars only.
"""
import numpy as np
import pandas as pd
import indicators as ind

# ---- INTRADAY: momentum-tilted weights ----
INTRA_W = {
    # price/flow momentum (dominant)
    "macd":0.16, "adx":0.14, "obv":0.12, "vol_spike":0.12, "rel_str":0.10,
    "liquidity":0.12, "volatility":0.10,
    # mean-reversion (minor, for entry timing only)
    "stochastic":0.08, "bollinger":0.06,
}
# ---- LONG-TERM: value-tilted weights (fundamentals + buy-weakness technicals) ----
LONG_W = {
    # fundamentals gate (dominant)
    "roe":0.12, "de":0.10, "earn_cagr":0.12, "margin":0.08, "valuation":0.12, "promoter":0.06,
    # value-timing technicals
    "bollinger":0.10, "support":0.10, "stochastic":0.08,
    # trend confirmation (minor — don't catch a falling knife)
    "adx":0.05, "macd":0.05,
}

def _band(v, cuts, scores):
    if v is None or (isinstance(v,float) and (np.isnan(v))): return 3
    for c,s in zip(cuts,scores):
        if v>=c: return s
    return scores[-1]


def score_intraday(sym, df, name=None, bt_mult=1.0):
    if df is None or len(df) < 30: return None
    c,h,l,v = df["Close"],df["High"],df["Low"],df["Volume"]
    price=float(c.iloc[-1]); turn_cr=price*float(v.iloc[-1])/1e7
    if turn_cr < 50: return None                       # liquidity hard filter
    tech,raw = ind.all_technicals(df)
    vol20=float(v.iloc[-20:].mean()); vx=float(v.iloc[-1])/(vol20 or 1)
    atrp=float(((h-l)/c*100).iloc[-14:].mean())
    ret1w=float(c.iloc[-1]/c.iloc[-6]-1)*100 if len(c)>6 else 0
    s={
      "macd":tech["macd"], "adx":tech["adx"], "obv":tech["obv"],
      "stochastic":tech["stochastic"], "bollinger":tech["bollinger"],
      "vol_spike":_band(vx,[3,2,1.5],[10,8,5,2]),
      "rel_str":_band(ret1w,[3,0,-3],[10,6,4,2]),
      "liquidity":_band(turn_cr,[200,100,50],[10,7,4,0]),
      "volatility":10 if 3<=atrp<=5 else 7 if 2<=atrp<3 else 6 if 5<atrp<=7 else 2,
    }
    comp=sum(s[k]*INTRA_W[k] for k in INTRA_W)*10*bt_mult
    comp=min(comp,100)
    if comp < 62: return None
    grade=["A","a"] if comp>=80 else ["B","b"]
    return dict(sym=sym,name=name or sym,score=round(comp,1),grade=grade,
        entry=round(price,2),exit=round(price*1.038,2),stop=round(price*0.981,2),
        hold="Same day · square off by 15:15",
        factors=[["MACD",s["macd"]],["ADX",s["adx"]],["OBV",s["obv"]],
                 ["Vol spike",s["vol_spike"]],["Rel str",s["rel_str"]],["Stoch",s["stochastic"]]])


def score_long(sym, df, fund, name=None, bt_mult=1.0):
    if df is None or len(df) < 200: return None
    c=df["Close"]; price=float(c.iloc[-1])
    tech,raw = ind.all_technicals(df)
    f=fund or {}
    def g(k,d=np.nan):
        x=f.get(k,d); return x if x is not None else d
    s={
      "roe":_band(g("roe"),[20,15,12],[10,8,5,2]),
      "de":_band(-(g("de") if g("de")==g("de") else 1.5),[-0.3,-0.5,-1],[10,8,4,1]),
      "earn_cagr":_band(g("earn_cagr"),[20,15,10],[10,8,5,2]),
      "margin":_band(g("margin"),[20,12,6],[10,8,5,2]),
      "valuation":_band(-(g("pe") if g("pe") and g("pe")==g("pe") else 40),[-15,-25,-40],[10,6,3,1]),
      "promoter":_band(g("promoter_pct"),[50,40,25],[10,7,5,3]),
      "bollinger":tech["bollinger"], "support":tech["support"],
      "stochastic":tech["stochastic"], "adx":tech["adx"], "macd":tech["macd"],
    }
    comp=sum(s[k]*LONG_W[k] for k in LONG_W)*10*bt_mult
    comp=min(comp,100)
    grade=["Strong Buy","buy"] if comp>=80 else ["Accumulate","acc"] if comp>=65 \
          else ["Hold","hold"] if comp>=50 else None
    if grade is None: return None
    return dict(sym=sym,name=name or (f.get("name") or sym),score=round(comp,1),grade=grade,
        entry=round(price,2),exit=round(price*1.22,2),stop=round(price*0.90,2),
        hold="18–36 months · value + quality" if comp>=80 else "12–24 months · accumulate on dips",
        factors=[["ROE",s["roe"]],["Valuation",s["valuation"]],["Earn CAGR",s["earn_cagr"]],
                 ["Bollinger",s["bollinger"]],["Support",s["support"]],["Stoch",s["stochastic"]]])


def build(fetched, kind="long", top_n=20, bt_mults=None):
    bt_mults=bt_mults or {}
    rows=[]
    for sym,blob in fetched.items():
        m=bt_mults.get(sym,1.0)
        if kind=="intra":
            r=score_intraday(sym, blob.get("daily"), blob.get("name"), m)
        else:
            r=score_long(sym, blob.get("daily"), blob.get("fund"), blob.get("name"), m)
        if r: rows.append(r)
    rows.sort(key=lambda r:r["score"], reverse=True)
    return rows[:top_n]
