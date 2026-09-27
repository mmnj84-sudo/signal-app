# Signal — deployment guide (do this at a computer)

A free, automated stock-signal system: a cloud backend generates verified
intraday + long-term picks on a schedule, sends Telegram alerts, and serves an
installable phone app. No broker account, no server cost.

Two parts to set up: **Telegram alerts** (can do on phone now) and **GitHub
deploy** (do at a computer). Follow in order.

---

## PART A — Telegram bot (5 min, phone-friendly, do this first)

1. Open Telegram, search **@BotFather**, start it.
2. Send `/newbot`, follow prompts, pick a name. It replies with a **token**
   like `123456:ABC-DEF...`. Copy it — this is `TELEGRAM_BOT_TOKEN`.
3. Search **@userinfobot**, start it. It replies with your numeric **Id**.
   Copy it — this is `TELEGRAM_CHAT_ID`.
4. Message your new bot once (say "hi") so it's allowed to message you.
5. Keep both values for Part B step 6. Done.

*(Alerts are optional — everything works without them; you just won't get pushes.)*

---

## PART B — GitHub deploy (at a computer, ~30 min)

### 1. Create a GitHub account
github.com → sign up (free) if you don't have one.

### 2. Create a new repository
Top-right **+** → **New repository**. Name it `signal-app`. Set **Public**
(free Actions + Pages need public). Don't add a README. **Create repository**.

### 3. Upload the project
On the empty repo page: **uploading an existing file**. Unzip `signal-app.zip`
on your computer, then drag **all its contents** into the browser:
`backend/`, `app/`, `data/`, `.github/`, `README.md`.
- Make sure the `.github/workflows/update.yml` path is preserved (GitHub keeps
  folder structure when you drag folders).
Commit at the bottom: **Commit changes**.

### 4. Enable GitHub Pages
Repo **Settings** → **Pages** (left menu) → under **Source** pick
**GitHub Actions**. Save.

### 5. Enable Actions write access
Settings → **Actions** → **General** → scroll to **Workflow permissions** →
select **Read and write permissions** → Save. *(Lets the bot commit picks.)*

### 6. Add your Telegram secrets
Settings → **Secrets and variables** → **Actions** → **New repository secret**:
- Name `TELEGRAM_BOT_TOKEN`, value = your token → Add
- Name `TELEGRAM_CHAT_ID`, value = your id → Add

### 7. First run
**Actions** tab → click **Update picks & deploy** → **Run workflow** →
**Run workflow** (green button). Watch it run (~3–5 min). It should go green.
- First run does long-term (works any time). It fetches ~100 stocks, scores,
  writes picks, deploys the page, and sends you a Telegram test of the top picks.

### 8. Open your app
Settings → Pages shows your URL: `https://<username>.github.io/signal-app/`.
Open it on Android → menu → **Add to Home screen**. Done — it's installed.

---

## What happens next (automatic)

- **Daily ~15:35 IST**: long-term picks refresh.
- **Every 30 min, market hours**: intraday watchlist refreshes.
- **Alerts**: new grade-A / Strong Buy picks, target/stop hits, and any degraded
  run get pushed to Telegram.
- **Record**: performance history builds itself over time — visible in the app's
  Record tab.
- You do nothing. Open the app when an alert arrives or when you want to look.

## Verify it's working
- App shows "Updated <time>" and picks with ✓ / ⚠ flags.
- Record tab starts filling after a few days of tracked/closed picks.
- A Telegram message arrived after the first run.

## Tuning later (optional)
- Strategy weights: `backend/engine_v2.py` (INTRA_W / LONG_W).
- Universe: `backend/universe.py` (add tickers, or load full NSE list).
- Richer fundamentals: drop a Screener export at `data/screener.csv`.
- Alert conditions: `backend/alerts.py`.

## Honest limits (unchanged)
- Data is delayed ~15 min → intraday is a watchlist, not live-tick execution.
- Rankings + record measure signal quality, not predictions or real P&L.
- Free Actions minutes are generous but finite; a personal universe stays well
  within them. Very large universes or very frequent runs could exceed them.
- Not investment advice. Validate with backtest.py, paper-trade, then decide.

## Troubleshooting
- **Workflow red?** Open the failed run, read the step that failed. Usually a
  typo in a secret or a transient fetch error (re-run it).
- **App loads but no picks?** Long-term needs the workflow to have run once;
  intraday needs market hours.
- **No Telegram?** Check both secrets are set and you messaged the bot once.
- **Page 404?** Pages can take a few minutes after first deploy; refresh.
