"""
Automated runner — the single entry point the scheduler calls.
Ties together every backend piece into one hands-off pass:

  fetch prices -> fetch fundamentals -> score (dual-tilt) -> cross-verify
  -> write picks.json (+ health status) for the app.

Usage (called by GitHub Actions or cron):
    python run_auto.py long
    python run_auto.py intra
    python run_auto.py both

Design for automation:
  - never crashes the whole run on one bad stock (per-symbol try/except)
  - writes a health block so silent failure is visible in the app
  - fabricates nothing; missing data -> neutral score upstream
"""
import sys, os, json, time, traceback
from datetime import datetime, timezone, timedelta

from universe import NIFTY_100
import fetch, fundamentals, engine_v2 as engine, verify

IST = timezone(timedelta(hours=5, minutes=30))
APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")
OUT = os.path.join(APP_DIR, "picks.json")


def gather(symbols, kind):
    """Fetch price (+fundamentals for long) per symbol, fault-isolated."""
    overrides = fundamentals.load_screener_overrides()   # {} if none — fully auto
    fetched, errors = {}, 0
    for s in symbols:
        try:
            daily = fetch.fetch_daily(s, period="2y" if kind == "long" else "3mo")
            if daily is None:
                errors += 1; continue
            blob = {"daily": daily, "name": s}
            if kind == "long":
                blob["fund"] = fundamentals.fetch_fundamentals(s, overrides)
                blob["name"] = blob["fund"].get("name", s)
            fetched[s] = blob
        except Exception:
            errors += 1
        time.sleep(0.4)                                  # polite pacing
    return fetched, errors


def run(mode="both"):
    started = datetime.now(IST)
    health = {"ok": True, "notes": []}
    long_rows, intra_rows = [], []

    try:
        if mode in ("long", "both"):
            data, err = gather(NIFTY_100, "long")
            long_rows = engine.build(data, "long", top_n=20)
            long_rows = verify.verify_all(long_rows)
            health["notes"].append(f"long: {len(data)} fetched, {err} errors, {len(long_rows)} picks")
            if len(data) < len(NIFTY_100) * 0.6:
                health["ok"] = False
                health["notes"].append("long: >40% of universe failed to fetch")

        if mode in ("intra", "both"):
            data, err = gather(NIFTY_100, "intra")
            intra_rows = engine.build(data, "intra", top_n=20)
            intra_rows = verify.verify_all(intra_rows)
            health["notes"].append(f"intra: {len(data)} fetched, {err} errors, {len(intra_rows)} picks")
    except Exception as e:
        health["ok"] = False
        health["notes"].append(f"fatal: {e}")
        traceback.print_exc()

    payload = {
        "asof": started.strftime("%d %b %Y, %H:%M IST"),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "health": health,
        "long": long_rows,
        "intra": intra_rows,
    }
    os.makedirs(APP_DIR, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=2)

    status = "OK" if health["ok"] else "DEGRADED"
    print(f"[{status}] {payload['asof']}")
    for n in health["notes"]:
        print("  -", n)
    print(f"  wrote {OUT}")
    return payload


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "both")
