"""
Scoring engine -> ranked picks with entry/exit/holding/rank -> picks.json
Consumes fetch.py output. Weights in CONFIG (tune after backtest).

GUARDS:
 - look-ahead: technicals use .iloc[-1] (last CLOSED bar) only; never today's
   unfinished bar for a decision meant for tomorrow.
 - survivorship: universe should include delisted names when backtesting
   (see backtest.py note). Live scoring uses the current universe by design.
"""
import json
import math
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

IST = timezone(timedelta(hours=5, minutes=30))

LT_WEIGHTS = {"roe":0.15,"de":0.12,"earn_cagr":0.15,"margin":0.10,
              "valuation":0.15,"promoter":0.08,"dividend":0.05,
              "momentum":0.10,"trend":0.10}
INTRA_WEIGHTS = {"liquidity":0.20,"volatility":0.18,"vol_spike":0.15,
                 "vwap":0.15,"rsi":0.12,"rel_str":0.12,"range_pos":0.08}
RISK = {"lt_stop":0.08,"lt_target":0.22,"intra_stop":0.019,"intra_target":0.038}


def _band(v, cuts, scores):
    if v is None or (isinstance(v,float) and math.isnan(v)):
        return 3  # neutral for missing data
    for c,s in zip(cuts,scores):
        if v >= c: return s
    return scores[-1]


# ---------------- LONG-TERM ----------------
def score_long(sym, blob):
    f = blob["fund"]; d = blob["daily"]
    s = {}
    s["roe"]       = _band(f["roe"], [20,15,12], [10,8,5,2])
    s["de"]        = _band(-(f["de"] if f["de"]==f["de"] else 1.5), [-0.3,-0.5,-1], [10,8,4,1])
    s["earn_cagr"] = _band(f["earn_cagr"], [20,15,10], [10,8,5,2])
    s["margin"]    = _band(f["margin"], [20,12,6], [10,8,5,2])
    pe = f.get("pe")
    s["valuation"] = _band(-(pe if pe and pe==pe else 40), [-15,-25,-40], [10,6,3,1])
    s["promoter"]  = _band(f["promoter_pct"], [50,40,25], [10,7,5,3])
    s["dividend"]  = 10 if (f["div_yield"] or 0) > 0.01 else 4
    # price-based confirmation (uses last closed bars only)
    if d is not None and len(d) > 200:
        close = d["Close"]
        ret6m = close.iloc[-1]/close.iloc[-126]-1
        s["momentum"] = _band(ret6m*100, [20,8,0], [10,7,4,2])
        sma200 = close.rolling(200).mean().iloc[-1]
        s["trend"] = 10 if close.iloc[-1] > sma200 else 3
        price = float(close.iloc[-1])
    else:
        s["momentum"]=s["trend"]=5
        price = f.get("price") or 0
    composite = sum(s[k]*LT_WEIGHTS[k] for k in LT_WEIGHTS)*10
    entry = round(price,2)
    target = round(price*(1+RISK["lt_target"]),2)
    stop = round(price*(1-RISK["lt_stop"]),2)
    grade = ("Strong Buy","buy") if composite>=80 else ("Accumulate","acc") if composite>=65 \
            else ("Hold","hold") if composite>=50 else ("Avoid","hold")
    hold = "18–36 months · quality compounder" if composite>=80 else "12–24 months · growth/value"
    return dict(sym=sym, name=f["name"], score=round(composite,1), grade=list(grade),
                entry=entry, exit=target, stop=stop, hold=hold,
                factors=[["ROE",s["roe"]],["Debt/Eq",s["de"]],["Earn CAGR",s["earn_cagr"]],
                         ["Margin",s["margin"]],["Valuation",s["valuation"]],["Momentum",s["momentum"]]])


# ---------------- INTRADAY (delayed watchlist) ----------------
def score_intra(sym, blob):
    d = blob["daily"]; itr = blob.get("intra")
    if d is None or len(d) < 25:
        return None
    last = d.iloc[-1]
    turnover_cr = float(last["Close"]*last["Volume"]/1e7)
    if turnover_cr < 50:  # hard liquidity filter
        return None
    s = {}
    s["liquidity"]  = _band(turnover_cr, [200,100,50], [10,7,4,0])
    atr = float(last["ATR%"]) if last["ATR%"]==last["ATR%"] else 2
    s["volatility"] = 10 if 3<=atr<=5 else 7 if 2<=atr<3 else 6 if 5<atr<=7 else 2
    vx = float(last["Volume"]/ (last["VOL20"] or last["Volume"]))
    s["vol_spike"]  = _band(vx, [3,2,1.5], [10,8,5,2])
    # VWAP from intraday if available, else prior close proxy
    if itr is not None and len(itr)>5:
        vwap = float((itr["Close"]*itr["Volume"]).sum()/ (itr["Volume"].sum()+1e-9))
        s["vwap"] = 10 if last["Close"]>vwap else 4
    else:
        s["vwap"] = 5
    s["rsi"]      = 10 if 55<=last["RSI"]<=70 else 6 if 45<=last["RSI"]<55 else 3
    ret1w = float(d["Close"].iloc[-1]/d["Close"].iloc[-6]-1) if len(d)>6 else 0
    s["rel_str"]  = _band(ret1w*100, [3,0,-3], [10,6,4,2])
    rng = (last["Close"]-last["Low"])/((last["High"]-last["Low"])+1e-9)
    s["range_pos"]= _band(rng, [0.6,0.4], [9,6,3])
    composite = sum(s[k]*INTRA_WEIGHTS[k] for k in INTRA_WEIGHTS)*10
    price = float(last["Close"])
    grade = ("A","a") if composite>=80 else ("B","b") if composite>=65 else ("Drop","hold")
    if composite < 65:  # only show watchable names
        return None
    return dict(sym=sym, name=blob.get("name",sym), score=round(composite,1), grade=list(grade),
                entry=round(price,2), exit=round(price*(1+RISK["intra_target"]),2),
                stop=round(price*(1-RISK["intra_stop"]),2),
                hold="Same day · square off by 15:15",
                factors=[["Liquidity",s["liquidity"]],["Volatility",s["volatility"]],
                         ["Vol spike",s["vol_spike"]],["VWAP",s["vwap"]],
                         ["RSI",s["rsi"]],["Rel str",s["rel_str"]]])


def build_picks(fetched, kind="long", top_n=15):
    fn = score_long if kind=="long" else score_intra
    rows = [r for s,b in fetched.items() if (r:=fn(s,b))]
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows[:top_n]


def write_json(long_rows, intra_rows, path="picks.json"):
    payload = {
        "asof": datetime.now(IST).strftime("%d %b %Y, %H:%M IST"),
        "long": long_rows, "intra": intra_rows,
    }
    with open(path,"w") as f:
        json.dump(payload, f, indent=2)
    return payload
