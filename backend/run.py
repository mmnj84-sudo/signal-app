"""
Entry point. Fetches free data, scores, writes picks.json into ../app/
Run modes:
    python run.py long     # long-term only
    python run.py intra    # intraday watchlist only
    python run.py both     # default
"""
import sys, os
from universe import NIFTY_100
import fetch, engine

OUT = os.path.join(os.path.dirname(__file__), "..", "app", "picks.json")

def main(mode="both"):
    long_rows, intra_rows = [], []
    if mode in ("long","both"):
        print("Fetching long-term (fundamentals + daily)…")
        data = fetch.fetch_all(NIFTY_100, kind="long")
        long_rows = engine.build_picks(data, "long", top_n=20)
        print(f"  -> {len(long_rows)} long-term picks")
    if mode in ("intra","both"):
        print("Fetching intraday (delayed bars)…")
        data = fetch.fetch_all(NIFTY_100, kind="intra")
        intra_rows = engine.build_picks(data, "intra", top_n=20)
        print(f"  -> {len(intra_rows)} intraday watchlist picks")
    engine.write_json(long_rows, intra_rows, OUT)
    print(f"Wrote {OUT}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "both")
