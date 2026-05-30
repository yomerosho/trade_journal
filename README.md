# 📈 0DTE Trade Journal

A private, password-protected Streamlit app that turns your Robinhood activity
CSV into a calendar-style trading journal — daily P&L, trade counts, win rates,
weekly summaries, and a cumulative equity curve.

Built to track your 0DTE options trading (SPY / QQQ / IWM and single names)
month over month. Upload a fresh export a couple of times a week and the
journal updates instantly.

---

## What it shows

- **Monthly header** — net P&L, trading days, total trades, win rate, green days
- **Calendar grid** — each day colored green/red by P&L, with trade count + win %
- **Weekly summary** — P&L per calendar week
- **Equity curve** — cumulative P&L across the month
- **Daily detail table** — exportable as a clean journal CSV

### How P&L is calculated

Each option **contract** (same strike, expiry, and put/call) round-tripped on a
day is treated as one *trade*. Its P&L is the net of every leg that day — buys
(BTO) count as cost, sells (STC) as proceeds, expirations (OEXP) as $0. A *win*
is any contract that closed net-positive. Cash transfers (ACH/RTP), Gold
subscription fees, and the disclaimer footer are ignored.

> Note: numbers are computed directly from your broker export, so they reflect
> realized option P&L exactly as it appears in the file. If you've seen a
> different total in another journaling tool, that tool may scale or match
> trades differently, or cover a different account/date range.

---

## 1. Put it on GitHub

From this folder:

```bash
git init
git add .
git commit -m "0DTE trade journal app"
git branch -M main
git remote add origin https://github.com/<your-username>/trade-journal.git
git push -u origin main
```

The included `.gitignore` keeps your real `secrets.toml` **and any `.csv`
files** out of the repo — your password and brokerage data never get pushed.

---

## 2. Deploy on Streamlit Community Cloud (free)

1. Go to **https://share.streamlit.io** and sign in with GitHub.
2. Click **Create app → Deploy a public app from GitHub**.
3. Pick your `trade-journal` repo, branch `main`, main file `app.py`.
4. Before (or right after) deploying, open **⋮ → Settings → Secrets** and paste:

   ```toml
   app_password = "your-strong-password-here"
   ```

5. Deploy. The app loads to a password screen — only someone with that password
   gets in.

> The repo can be public; your password lives only in Streamlit's encrypted
> Secrets, never in the code.

---

## 3. Run it locally (optional)

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then edit the password
streamlit run app.py
```

Opens at http://localhost:8501.

---

## 4. Weekly workflow (June and beyond)

1. In Robinhood: **Account → Statements & history → Reports & statements →
   Generate report** (or the CSV export of account activity).
2. Each time, export your **full month-to-date** activity and upload that one
   file. It always shows the complete picture, and re-uploading the same file
   is harmless.
3. Switch months with the **Month** dropdown — it defaults to the most recent
   month in your data, so come June it'll land on June automatically.

---

## Files

| File | Purpose |
|------|---------|
| `app.py` | The Streamlit app |
| `requirements.txt` | Python dependencies for Streamlit Cloud |
| `.streamlit/config.toml` | Light theme + 50 MB upload limit |
| `.streamlit/secrets.toml.example` | Template — copy to `secrets.toml` locally |
| `.gitignore` | Keeps secrets and CSVs out of git |
