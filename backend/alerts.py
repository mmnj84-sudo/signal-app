"""
Alert engine — decides WHAT is worth telling you, and sends it.

Alert conditions (tuned for a hands-off "tell me when to look" tool):
  * NEW high-conviction pick entering the top ranks (grade A / Strong Buy)
  * TARGET or STOP hit on a tracked position (a close — you may want to act)
  * HEALTH warning when a run is DEGRADED (don't trust stale picks silently)

De-duplication: a state file remembers what was already alerted, so the same
pick doesn't re-notify every 20 minutes. Only genuinely NEW events fire.

Delivery: Telegram (robust, free, no browser push needed). The send_* channel
is isolated — swap in ntfy/email/PWA-push without touching the logic.
Secrets come from env vars (set once in GitHub repo settings), never hardcoded.
"""
import os, json
from datetime import datetime, timezone, timedelta

try:
    import requests
except ImportError:
    requests = None

IST = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
ALERT_STATE = os.path.join(DATA_DIR, "alert_state.json")

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")


# ---------- delivery channel (isolated) ----------
def send_telegram(text):
    """Send one message. Returns True on success. No-op if unconfigured."""
    if not (TG_TOKEN and TG_CHAT and requests):
        print("  [alert] Telegram not configured — would send:\n   ", text.replace("\n","\n    "))
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                          json={"chat_id": TG_CHAT, "text": text,
                                "parse_mode": "HTML", "disable_web_page_preview": True},
                          timeout=15)
        return r.ok
    except Exception as e:
        print("  [alert] send failed:", e); return False


# ---------- state (de-dup) ----------
def _load_state():
    try:
        with open(ALERT_STATE) as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"alerted": {}}

def _save_state(s):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ALERT_STATE, "w") as f: json.dump(s, f, indent=2)

def _key(kind, sym, event, day):
    return f"{day}:{kind}:{sym}:{event}"


# ---------- verdict icon ----------
def _vmark(v):
    return {"verified":"✓","flag":"⚠","unverified":"?"}.get(v, "?")


# ---------- alert conditions ----------
def evaluate(payload, track):
    """Return list of (event, text) for NEW alert-worthy things this run."""
    state = _load_state()
    day = datetime.now(IST).strftime("%Y-%m-%d")
    out = []

    def fire(kind, sym, event, text):
        k = _key(kind, sym, event, day)
        if k in state["alerted"]:
            return
        state["alerted"][k] = datetime.now(IST).isoformat()
        out.append((event, text))

    # 1) health
    if not payload.get("health", {}).get("ok", True):
        fire("sys", "-", "degraded",
             "⚠️ <b>Signal run DEGRADED</b> — data may be incomplete, verify before acting.\n"
             + "\n".join(payload["health"].get("notes", [])))

    # 2) new high-conviction picks
    top_grades = {"A", "Strong Buy"}
    for kind in ("intra", "long"):
        for p in payload.get(kind, [])[:10]:
            if p["grade"][0] in top_grades:
                fire(kind, p["sym"], "new-top",
                     f"🔔 <b>{p['sym']}</b> {_vmark(p.get('verify'))} — {p['grade'][0]} "
                     f"({p['score']}) [{kind}]\n"
                     f"Entry ₹{p['entry']} · Target ₹{p['exit']} · Stop ₹{p['stop']}\n"
                     f"Hold: {p['hold']}")

    # 3) closes (target/stop) from freshly closed positions today
    for c in track.get("closed", []):
        if c.get("closed") == day and c["status"] in ("target", "stop"):
            emoji = "✅" if c["status"] == "target" else "🛑"
            fire(c["kind"], c["sym"], f"close-{c['status']}",
                 f"{emoji} <b>{c['sym']}</b> hit {c['status'].upper()} "
                 f"({c.get('final_ret_pct',0):+.1f}%) [{c['kind']}]")

    _save_state(state)
    return out


def run_alerts(payload, track):
    events = evaluate(payload, track)
    sent = 0
    for event, text in events:
        if send_telegram(text): sent += 1
    if events:
        print(f"  [alert] {len(events)} new event(s), {sent} sent")
    else:
        print("  [alert] nothing new to alert")
    return events


if __name__ == "__main__":
    # Offline test: verify condition detection + de-dup (no network send).
    import tempfile
    ALERT_STATE = os.path.join(tempfile.mkdtemp(), "alert_state.json")
    payload = {"health":{"ok":True},
        "intra":[{"sym":"TATASTEEL","grade":["A","a"],"score":86,"entry":172,"exit":178,"stop":169,"hold":"Same day","verify":"verified"}],
        "long":[{"sym":"BAJFINANCE","grade":["Strong Buy","buy"],"score":88,"entry":742,"exit":905,"stop":681,"hold":"18-36 mo","verify":"flag"}]}
    track = {"closed":[{"sym":"TITAN","kind":"long","status":"target","closed":datetime.now(IST).strftime("%Y-%m-%d"),"final_ret_pct":22.0}]}
    print("First run (should fire 3):")
    e1 = run_alerts(payload, track)
    print("\nSecond run (should fire 0 — de-dup):")
    e2 = run_alerts(payload, track)
    print(f"\nRun1={len(e1)} events, Run2={len(e2)} events (dedup working: {len(e2)==0})")
