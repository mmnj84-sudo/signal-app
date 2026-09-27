# Signal — live stock picks (intraday watchlist + long-term)

Free online data (Yahoo Finance + NSE), scored into ranked picks with
entry / target / stop / holding, served as a mobile web app. No broker account.

## What updates when
- **Long-term**: once daily after market close (fundamentals move slowly).
- **Intraday watchlist**: every 30 min during market hours — on **delayed
  (~15 min) free data**, so it's a watchlist + level guide, not live execution.

## Files
```
backend/
  universe.py     Nifty 100 tickers (expand to full NSE later)
  fetch.py        Yahoo Finance price + fundamentals
  engine.py       scoring -> ranked picks -> picks.json
  run.py          fetch + score + write app/picks.json
  backtest.py     walk-forward validation (look-ahead-safe)
  requirements.txt
app/
  index.html      the mobile web app (fetches picks.json)
  picks.json      generated output the app reads
.github/workflows/update.yml   scheduled automation
```

## Run locally first (prove real data flows)
```bash
cd backend
pip install -r requirements.txt
python run.py both          # writes ../app/picks.json from live Yahoo data
cd ../app && python -m http.server 8000
# open http://localhost:8000 on your phone (same wifi) or PC
```

## Deploy free on GitHub (auto-updates, public URL)
1. Create a new GitHub repo, push this folder.
2. Repo **Settings → Pages → Source: GitHub Actions**.
3. The workflow runs on schedule (and a manual **Run workflow** button).
   It fetches data, rewrites `app/picks.json`, and redeploys the page.
4. Your app is live at `https://<username>.github.io/<repo>/` — open it on
   Android, add to home screen for an app-like icon.

## Validate before trusting the numbers
```bash
cd backend && python backtest.py     # walk-forward, costs, look-ahead guard
```
Swap the synthetic demo in `backtest.py` for real downloaded daily data to get
a genuine read. Judge by excess-vs-benchmark and Sharpe, not raw return.

## Honest limits
- Free data is delayed ~15 min → true tick intraday needs a paid/broker feed.
- Rankings show how the strategy scored on history; they don't predict returns.
- yfinance fundamentals are occasionally patchy; missing fields score neutral.
- Not investment advice. Validate, paper-trade, then risk real money.

## Expand later
- Full NSE universe: in `universe.py`, load NSE `EQUITY_L.csv` and append `.NS`.
- Richer fundamentals: add a Screener.in export loader or Finnhub free API.
- True real-time intraday: reintroduce a broker feed (e.g. Upstox) for the
  intraday engine only; long-term stays on free data.
