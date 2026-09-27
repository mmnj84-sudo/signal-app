"""
Persistent record — the memory of the system, auto-maintained each run.

Two jobs:
  1. LOG every day's picks (append-only history) so nothing is lost.
  2. TRACK how past picks performed — mark entry price + date, then on later
     runs update each open pick with its current return, and CLOSE it when it
     hits target, stop, or max-hold — building a real track record.

Storage: plain JSON files in data/ (no database needed — automation-friendly,
diffable in git, survives on the free tier). The app reads these directly.

Files:
  data/history.json    append-only log: every pick ever shown (with date)
  data/track.json      open + closed positions with outcomes (the track record)
  data/stats.json      rolled-up performance summary the app displays

Honest note: this is PAPER tracking of the signals (did the pick move as
scored?), not your real brokerage P&L. It measures the strategy, not your
account. Entry = the price when first shown; no costs modeled here (the
backtest models costs — this tracks raw signal quality).
"""
import os, json
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
HISTORY = os.path.join(DATA_DIR, "history.json")
TRACK   = os.path.join(DATA_DIR, "track.json")
STATS   = os.path.join(DATA_DIR, "stats.json")

MAX_HOLD_DAYS = {"intra": 1, "long": 540}   # auto-close horizon per engine


def _load(path, default):
    try:
        with open(path) as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def _save(path, obj):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w") as f: json.dump(obj, f, indent=2)


def _today():
    return datetime.now(IST).strftime("%Y-%m-%d")


def log_picks(picks, kind):
    """Append today's picks to the immutable history log."""
    hist = _load(HISTORY, [])
    day = _today()
    for p in picks:
        hist.append({"date": day, "kind": kind, "sym": p["sym"],
                     "score": p["score"], "grade": p["grade"][0],
                     "entry": p["entry"], "target": p["exit"], "stop": p["stop"],
                     "verify": p.get("verify", "unverified")})
    _save(HISTORY, hist)
    return len(hist)


def open_positions(picks, kind):
    """Open a tracked position for any NEW top pick not already open.
    Only tracks grade A / Strong Buy / Accumulate to keep the record focused."""
    track = _load(TRACK, {"open": [], "closed": []})
    open_syms = {(o["sym"], o["kind"]) for o in track["open"]}
    day = _today()
    watch_grades = {"A", "Strong Buy", "Accumulate"}
    for p in picks:
        if p["grade"][0] in watch_grades and (p["sym"], kind) not in open_syms:
            track["open"].append({
                "sym": p["sym"], "kind": kind, "opened": day,
                "entry": p["entry"], "target": p["exit"], "stop": p["stop"],
                "score_at_open": p["score"], "peak": p["entry"], "status": "open"})
    _save(TRACK, track)
    return track


def update_positions(current_prices):
    """current_prices: {sym: latest_price}. Updates open positions, closes on
    target/stop/max-hold, and refreshes stats. Called each run."""
    track = _load(TRACK, {"open": [], "closed": []})
    still_open = []
    for pos in track["open"]:
        px = current_prices.get(pos["sym"])
        if px is None:
            still_open.append(pos); continue
        pos["last"] = round(px, 2)
        pos["ret_pct"] = round((px / pos["entry"] - 1) * 100, 2)
        pos["peak"] = round(max(pos.get("peak", pos["entry"]), px), 2)
        held = (datetime.now(IST).date() -
                datetime.strptime(pos["opened"], "%Y-%m-%d").date()).days
        reason = None
        if px >= pos["target"]: reason = "target"
        elif px <= pos["stop"]: reason = "stop"
        elif held >= MAX_HOLD_DAYS.get(pos["kind"], 540): reason = "max-hold"
        if reason:
            pos["status"] = reason
            pos["closed"] = _today()
            pos["final_ret_pct"] = pos["ret_pct"]
            track["closed"].append(pos)
        else:
            still_open.append(pos)
    track["open"] = still_open
    _save(TRACK, track)
    _recompute_stats(track)
    return track


def _recompute_stats(track):
    closed = track["closed"]
    n = len(closed)
    wins = [c for c in closed if c.get("final_ret_pct", 0) > 0]
    def avg(xs): return round(sum(xs)/len(xs), 2) if xs else 0.0
    stats = {
        "updated": _today(),
        "open_count": len(track["open"]),
        "closed_count": n,
        "win_rate": round(len(wins)/n*100, 1) if n else None,
        "avg_return": avg([c.get("final_ret_pct", 0) for c in closed]),
        "avg_win": avg([c["final_ret_pct"] for c in wins]),
        "avg_loss": avg([c.get("final_ret_pct", 0) for c in closed if c.get("final_ret_pct", 0) <= 0]),
        "best": max([c.get("final_ret_pct", 0) for c in closed], default=0),
        "worst": min([c.get("final_ret_pct", 0) for c in closed], default=0),
        "by_reason": {r: sum(1 for c in closed if c["status"] == r)
                      for r in ("target", "stop", "max-hold")},
    }
    _save(STATS, stats)
    return stats


def record_run(picks_by_kind, current_prices):
    """One call from the runner: log, open, update, refresh stats."""
    for kind, picks in picks_by_kind.items():
        log_picks(picks, kind)
        open_positions(picks, kind)
    return update_positions(current_prices)


if __name__ == "__main__":
    # Offline self-test: simulate 3 runs across days to show tracking + stats.
    import shutil, tempfile
    _d = tempfile.mkdtemp()
    DATA_DIR = _d
    HISTORY=os.path.join(_d,"history.json"); TRACK=os.path.join(_d,"track.json"); STATS=os.path.join(_d,"stats.json")

    picks=[{"sym":"AAA","grade":["Strong Buy","buy"],"score":85,"entry":100,"exit":122,"stop":90,"verify":"verified"},
           {"sym":"BBB","grade":["Accumulate","acc"],"score":70,"entry":200,"exit":244,"stop":180,"verify":"verified"}]
    log_picks(picks,"long"); open_positions(picks,"long")
    print("opened positions.")
    # run 2: AAA rises toward target, BBB dips
    update_positions({"AAA":118,"BBB":190})
    print("after move:", _load(TRACK,{})["open"])
    # run 3: AAA hits target -> closes
    t=update_positions({"AAA":125,"BBB":205})
    print("closed:", [(c['sym'],c['status'],c['final_ret_pct']) for c in t["closed"]])
    print("stats:", json.dumps(_load(STATS,{}), indent=1))
    shutil.rmtree(DATA_DIR)
