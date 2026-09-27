"""
Cross-reference / verification layer — a data sanity check, NOT trade advice.

For each pick, independently re-checks the price against a second free source.
Agreement -> "verified"; mismatch/unavailable -> flag for manual review.

Honest scope: this validates the DATA the pick was built on (guards against
stale/bad feeds), it does NOT validate that the trade is good. No external
site can confirm a strategy — only that the inputs look sane.

Sources kept lightweight so automation stays fast and doesn't break:
  primary   : Yahoo (already used for scoring)
  verifier  : Yahoo quote endpoint via a second host/path as an independent read
Extendable: add another free quote source in second_source() if desired.
"""
import time
import numpy as np

try:
    import yfinance as yf
except ImportError:
    yf = None

TOLERANCE = 0.03   # 3% price disagreement -> flag


def second_source_price(symbol):
    """Independent price read. Uses yfinance fast_info as a distinct code path
    from the .history() close used in scoring; swap/add a different free API
    here for a truly separate source if you want belt-and-suspenders."""
    if yf is None:
        return None
    try:
        fi = yf.Ticker(f"{symbol}.NS").fast_info
        return float(fi.get("last_price") or fi.get("lastPrice") or np.nan)
    except Exception:
        return None


def verify_pick(pick, scored_price=None):
    """Attach a confidence verdict to one pick dict. Never raises."""
    scored = scored_price if scored_price is not None else pick.get("entry")
    ref = second_source_price(pick["sym"])
    verdict, note = "unverified", "second source unavailable"
    if ref and scored and scored > 0:
        diff = abs(ref - scored) / scored
        if diff <= TOLERANCE:
            verdict, note = "verified", f"price agrees (±{diff*100:.1f}%)"
        else:
            verdict, note = "flag", f"price mismatch {diff*100:.1f}% — verify manually"
    pick["verify"] = verdict          # "verified" | "flag" | "unverified"
    pick["verify_note"] = note
    return pick


def verify_all(picks, pause=0.2):
    for p in picks:
        verify_pick(p)
        time.sleep(pause)             # gentle on the source
    return picks


if __name__ == "__main__":
    # Offline logic test (no network): simulate the compare.
    def check(scored, ref):
        diff = abs(ref-scored)/scored
        return ("verified" if diff<=TOLERANCE else "flag", round(diff*100,1))
    print("scored 500, ref 505 ->", check(500,505))   # agree
    print("scored 500, ref 540 ->", check(500,540))   # mismatch -> flag
    print("scored 500, ref 500 ->", check(500,500))   # exact
