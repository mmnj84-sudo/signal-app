"""
Fundamentals fetch — layered for reliability over an unattended backend.

Layer 1 (automatic): yfinance .info  — ROE, D/E, margins, PE, promoter, growth
Layer 2 (fallback):  missing fields -> None -> scored neutral (never fabricated)
Layer 3 (optional):  a Screener CSV you drop at data/screener.csv OVERRIDES
                     layer 1 for richer, more accurate figures.

Design rule: NEVER invent a number. A missing metric returns None and the
engine's _band() gives it a neutral 3, so a data gap can't fake a strong score.
"""
import os
import csv
import numpy as np

try:
    import yfinance as yf
except ImportError:
    yf = None

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SCREENER_CSV = os.path.join(DATA_DIR, "screener.csv")


def _pct(x):
    return x*100 if (x is not None and x == x) else np.nan


def from_yfinance(symbol):
    """Best-effort fundamentals from Yahoo. Missing -> NaN (never guessed)."""
    if yf is None:
        return {}
    try:
        info = yf.Ticker(f"{symbol}.NS").info
    except Exception:
        return {}
    g = lambda k: info.get(k)
    de = g("debtToEquity")
    return {
        "name": g("shortName") or symbol,
        "roe": _pct(g("returnOnEquity")),
        "de": (de/100.0) if de is not None else np.nan,   # Yahoo gives % form
        "earn_cagr": _pct(g("earningsGrowth")),
        "margin": _pct(g("profitMargins")),
        "pe": g("trailingPE") if g("trailingPE") else np.nan,
        "promoter_pct": _pct(g("heldPercentInsiders")),
        "div_yield": g("dividendYield") or 0,
        "price": g("currentPrice") or g("previousClose"),
    }


def load_screener_overrides():
    """Optional. If data/screener.csv exists, load it as overrides.
    Expected headers (flexible): SYMBOL, ROE, DE/Debt to equity, EarningsGrowth,
    Margin/OPM, PE, Promoter/Promoter holding. Extra columns ignored.
    Map your export's real headers here once and it just works."""
    if not os.path.exists(SCREENER_CSV):
        return {}
    out = {}
    # header aliases -> canonical field
    alias = {
        "roe":"roe", "return on equity":"roe",
        "de":"de", "debt to equity":"de", "debt/equity":"de",
        "earningsgrowth":"earn_cagr", "profit growth":"earn_cagr", "eps growth":"earn_cagr",
        "margin":"margin", "opm":"margin", "npm":"margin", "profit margin":"margin",
        "pe":"pe", "p/e":"pe", "price to earning":"pe",
        "promoter":"promoter_pct", "promoter holding":"promoter_pct",
    }
    with open(SCREENER_CSV, newline="") as f:
        r = csv.DictReader(f)
        norm = {h: alias.get(h.strip().lower()) for h in (r.fieldnames or [])}
        symcol = next((h for h in (r.fieldnames or []) if h.strip().lower() in
                       ("symbol","ticker","nse code","name")), None)
        for row in r:
            sym = (row.get(symcol) or "").strip().upper()
            if not sym:
                continue
            rec = {}
            for h, field in norm.items():
                if field and row.get(h):
                    try: rec[field] = float(str(row[h]).replace("%","").replace(",","").strip())
                    except ValueError: pass
            if rec:
                out[sym] = rec
    return out


def fetch_fundamentals(symbol, overrides=None):
    """yfinance base, then apply any Screener CSV overrides on top."""
    base = from_yfinance(symbol)
    if overrides and symbol.upper() in overrides:
        base.update(overrides[symbol.upper()])   # richer manual data wins
    return base


if __name__ == "__main__":
    # Offline self-test: prove override logic + neutral-on-missing, no network.
    ov = {"TESTCO": {"roe": 21.5, "de": 0.35, "pe": 22.0}}
    # simulate yfinance returning partial data
    def fake_yf(sym):
        return {"name":"Test Co","roe":np.nan,"de":np.nan,"earn_cagr":14.0,
                "margin":np.nan,"pe":np.nan,"promoter_pct":np.nan,"div_yield":0,"price":500}
    base = fake_yf("TESTCO")
    base.update(ov["TESTCO"])
    print("Merged fundamentals (override applied):")
    for k,v in base.items(): print(f"  {k:14s}: {v}")
    missing = [k for k,v in base.items() if isinstance(v,float) and v!=v]
    print("Still-missing (will score neutral, not faked):", missing or "none")
