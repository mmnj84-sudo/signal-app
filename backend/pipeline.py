"""
pipeline.py — the ONE command the scheduler runs.
Ties every backend piece into a single automated pass:

  run_auto (fetch -> fundamentals -> score -> verify -> health)
    -> record (log, open, update positions, stats)
    -> alerts (notify on new top picks / closes / degraded runs)
    -> merge stats + open positions into app/picks.json for the PWA

Usage:  python pipeline.py [long|intra|both]
Env:    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID  (optional; alerts skip if unset)
"""
import sys, os, json

import run_auto, record, alerts

APP_JSON = os.path.join(os.path.dirname(__file__), "..", "app", "picks.json")


def _current_prices(payload):
    """Latest price per pick (entry == last close from the run) for tracking."""
    px = {}
    for kind in ("intra", "long"):
        for p in payload.get(kind, []):
            px[p["sym"]] = p["entry"]
    return px


def main(mode="both"):
    # 1) generate verified, ranked, health-checked picks
    payload = run_auto.run(mode)

    # 2) update the persistent record (history, positions, stats)
    prices = _current_prices(payload)
    picks_by_kind = {k: payload.get(k, []) for k in ("intra", "long")}
    track = record.record_run(picks_by_kind, prices)

    # 3) fire alerts on genuinely new events
    alerts.run_alerts(payload, track)

    # 4) enrich the app payload with stats + open positions, rewrite it
    stats = record._load(record.STATS, None)
    if stats:
        payload["stats"] = stats
    payload["track_open"] = track.get("open", [])
    with open(APP_JSON, "w") as f:
        json.dump(payload, f, indent=2)
    print("  pipeline complete — app/picks.json updated")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "both")
