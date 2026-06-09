"""
Trade Journal — Streamlit app
----------------------------------
Calendar-style trading journal that ingests Robinhood-style brokerage
activity CSV exports and computes daily P&L, trade counts, and win rates.

Deploy on Streamlit Community Cloud (see README.md).
Password is read from st.secrets["app_password"].
"""

import hmac
import calendar
import datetime as dt

import pandas as pd
import streamlit as st

# --------------------------------------------------------------------------- #
#  Page config
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="Trade Journal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

TRADE_CODES = ["BTO", "STC", "BTC", "STO", "OEXP", "OASGN"]  # option open/close/expire/assign

# --------------------------------------------------------------------------- #
#  Themes — two palettes, switchable at runtime from the sidebar
# --------------------------------------------------------------------------- #
LIGHT = {
    "app_bg": "#ffffff",
    "panel": "#ffffff",
    "panel_2": "#f7f7f9",
    "border": "#e8e8ee",
    "text": "#2b2b3a",
    "muted": "#8a8a9e",
    "green": "#1aa260",
    "red": "#e2575b",
    "accent": "#1aa260",
    "green_rgb": "26,162,96",
    "red_rgb": "226,87,91",
    "cell_empty_bg": "#f4f4f6",
    "cell_empty_border": "#ececf0",
    "day_num": "#a0a0b0",
    "amt_colored": False,        # light: charcoal amounts (bg signals win/loss)
    "amt_text": "#1f2430",
    "pill_bg": "#eceaf6",
    "th_bg": "#ffffff",
    "th_border": "#ececf0",
    "shadow": "0 1px 2px rgba(0,0,0,0.03)",
    "input_bg": "#ffffff",
}

# Softer dark — a comfortable slate, not near-black
DARK = {
    "app_bg": "#1c2030",
    "panel": "#262b3a",
    "panel_2": "#2e3447",
    "border": "rgba(255,255,255,0.10)",
    "text": "#e6e9ef",
    "muted": "#9aa1b5",
    "green": "#2bd49a",
    "red": "#ff6b81",
    "accent": "#2bd49a",
    "green_rgb": "43,212,154",
    "red_rgb": "255,107,129",
    "cell_empty_bg": "#262b3a",
    "cell_empty_border": "rgba(255,255,255,0.08)",
    "day_num": "#7b8294",
    "amt_colored": True,         # dark: colored amounts read better than charcoal
    "amt_text": "#e6e9ef",
    "pill_bg": "rgba(255,255,255,0.08)",
    "th_bg": "#262b3a",
    "th_border": "rgba(255,255,255,0.10)",
    "shadow": "0 1px 2px rgba(0,0,0,0.20)",
    "input_bg": "#262b3a",
}


def get_palette() -> dict:
    return DARK if st.session_state.get("theme") == "Dark" else LIGHT


def global_css(P: dict) -> str:
    """Theme-aware global CSS, incl. overrides for Streamlit chrome so the
    runtime toggle recolors the whole app (background, sidebar, inputs)."""
    return f"""
<style>
  .stApp {{ background:{P['app_bg']}; }}
  /* recolor core chrome so the toggle affects the whole page */
  .stApp, .stApp p, .stApp label, .stApp span, .stApp h1, .stApp h2,
  .stApp h3, .stApp h4 {{ color:{P['text']}; }}
  section[data-testid="stSidebar"] {{ background:{P['panel_2']}; }}
  div[data-baseweb="select"] > div {{
      background:{P['input_bg']}; border-color:{P['border']}; color:{P['text']};
  }}
  div[data-testid="stExpander"] {{
      border:1px solid {P['border']}; border-radius:12px; background:{P['panel']};
  }}
  hr {{ border-color:{P['border']}; }}
  /* Summary strip */
  .gex-strip {{
      display:flex; flex-wrap:wrap; gap:0; background:{P['panel']};
      border:1px solid {P['border']}; border-radius:14px; overflow:hidden;
      margin-bottom:18px; font-family:-apple-system,Segoe UI,Roboto,sans-serif;
      box-shadow:{P['shadow']};
  }}
  .gex-cell {{
      flex:1 1 14%; min-width:120px; padding:11px 16px;
      border-right:1px solid {P['border']};
  }}
  .gex-cell:last-child {{ border-right:none; }}
  .gex-cell .lbl {{ color:{P['muted']}; font-size:10.5px; text-transform:uppercase;
      letter-spacing:.07em; margin-bottom:3px; }}
  .gex-cell .val {{ font-size:18px; font-weight:700; font-variant-numeric:tabular-nums;
      color:{P['text']}; }}
  h1,h2,h3,h4 {{ letter-spacing:-.01em; }}
</style>
"""


def gex_strip(items: list[tuple[str, str, str]]) -> str:
    """Render the horizontal label/value summary strip.
    items = [(label, value, color_hex_or_empty), ...]"""
    cells = ""
    for lbl, val, color in items:
        style = f"color:{color};" if color else ""
        cells += (
            f"<div class='gex-cell'><div class='lbl'>{lbl}</div>"
            f"<div class='val' style='{style}'>{val}</div></div>"
        )
    return f"<div class='gex-strip'>{cells}</div>"


# --------------------------------------------------------------------------- #
#  Password gate
# --------------------------------------------------------------------------- #
def check_password() -> bool:
    """Return True once the user has entered the correct password."""

    def password_entered():
        expected = st.secrets.get("app_password", None)
        if expected is None:
            st.session_state["password_correct"] = False
            st.session_state["password_missing"] = True
            return
        if hmac.compare_digest(st.session_state.get("password", ""), str(expected)):
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't keep it around
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False):
        return True

    # Login screen
    st.markdown("<div style='height:8vh'></div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        st.markdown("## 📈 Trade Journal")
        st.caption("Private — authorized access only.")
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        if st.session_state.get("password_missing"):
            st.error(
                "No password configured. Add `app_password` to your Streamlit "
                "secrets (see README)."
            )
        elif "password_correct" in st.session_state and not st.session_state["password_correct"]:
            st.error("😕 Incorrect password.")
    return False


# --------------------------------------------------------------------------- #
#  Data loading / parsing
# --------------------------------------------------------------------------- #
def parse_money(x) -> float:
    """Convert '$1,234.56' or '($90.94)' -> float. Blank/NaN -> 0.0"""
    if pd.isna(x):
        return 0.0
    s = str(x).strip().replace("$", "").replace(",", "")
    if s == "":
        return 0.0
    neg = s.startswith("(")
    s = s.replace("(", "").replace(")", "")
    try:
        v = float(s)
    except ValueError:
        return 0.0
    return -v if neg else v


PARSED_COLS = ["date", "instrument", "description", "trans_code", "quantity", "price", "amount"]


def _to_float(x) -> float:
    try:
        return float(str(x).strip())
    except (ValueError, TypeError):
        return 0.0


def _parse_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Parse a single uploaded frame into the parsed-schema trades frame.
    Accepts either a Robinhood export or a previously-downloaded backup CSV."""
    lower = {c.lower() for c in df.columns}

    # Already-parsed backup CSV (downloaded from this app)
    if {"date", "trans_code", "amount"}.issubset(lower):
        d = df.copy()
        d.columns = [c.lower() for c in d.columns]
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        d["amount"] = pd.to_numeric(d["amount"], errors="coerce").fillna(0.0)
        d["price"] = pd.to_numeric(d.get("price"), errors="coerce")
        if "quantity" in d.columns:
            d["quantity"] = pd.to_numeric(d["quantity"], errors="coerce")
        else:
            d["quantity"] = pd.NA
        # Reconstruct quantity for older backups that lacked it:
        # amount ≈ price × qty × 100, so qty ≈ |amount| / (price × 100)
        miss = d["quantity"].isna() & d["price"].notna() & (d["price"] > 0)
        d.loc[miss, "quantity"] = (d.loc[miss, "amount"].abs() / (d.loc[miss, "price"] * 100)).round()
        d["quantity"] = d["quantity"].fillna(0.0)
        for c in PARSED_COLS:
            if c not in d.columns:
                d[c] = pd.NA
        return d.dropna(subset=["date"])[PARSED_COLS]

    # Robinhood activity export
    needed = ["Activity Date", "Instrument", "Description", "Trans Code", "Quantity", "Price", "Amount"]
    for col in needed:
        if col not in df.columns:
            df[col] = pd.NA
    df = df.dropna(subset=["Activity Date", "Trans Code"])
    df = df[df["Activity Date"].astype(str).str.strip() != ""]
    df["amount"] = df["Amount"].apply(parse_money)
    df["quantity"] = df["Quantity"].apply(_to_float)
    df["price"] = pd.to_numeric(df["Price"].astype(str).str.replace("$", "", regex=False), errors="coerce")
    df["date"] = pd.to_datetime(df["Activity Date"], errors="coerce")
    df = df.dropna(subset=["date"])
    trades = df[df["Trans Code"].isin(TRADE_CODES)].copy()
    trades = trades.rename(
        columns={
            "Instrument": "instrument",
            "Description": "description",
            "Trans Code": "trans_code",
        }
    )
    return trades[PARSED_COLS].reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_trades(file_bytes_list: list[bytes]) -> pd.DataFrame:
    """
    Parse one or more uploaded CSVs (Robinhood exports or this app's own backup
    files) into a clean trades frame. Whole identical files are de-duplicated,
    and when several files OVERLAP (e.g. a full-history export plus a recent
    one), each calendar date's trades come from a single file — later-listed
    files win — so overlapping dates are never counted twice. Genuine identical
    fills within a single file are preserved.
    """
    from io import BytesIO
    import hashlib

    seen, parsed = set(), []
    for raw in file_bytes_list:
        h = hashlib.md5(raw).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        parsed.append(_parse_frame(pd.read_csv(BytesIO(raw), on_bad_lines="skip")))

    if not parsed:
        return pd.DataFrame(columns=PARSED_COLS)

    # Fold files together by date: a date present in a later file replaces the
    # same date from an earlier file rather than being appended to it.
    combined = parsed[0]
    for frame in parsed[1:]:
        combined = merge_by_date(combined, frame)
    return combined.reset_index(drop=True)


# --------------------------------------------------------------------------- #
#  Persistence — best-effort local store that the app reloads on startup
# --------------------------------------------------------------------------- #
import os

DATA_DIR = "data"
MASTER_FILE = os.path.join(DATA_DIR, "master_trades.csv")


def load_master() -> pd.DataFrame:
    """Load the accumulated trades saved from previous uploads (if any)."""
    if os.path.exists(MASTER_FILE):
        try:
            return _parse_frame(pd.read_csv(MASTER_FILE)).reset_index(drop=True)
        except Exception:
            return pd.DataFrame(columns=PARSED_COLS)
    return pd.DataFrame(columns=PARSED_COLS)


def save_master(trades: pd.DataFrame) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    out = trades.copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(MASTER_FILE, index=False)


def merge_by_date(master: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Accumulate uploads. Any date present in `new` replaces that date's rows
    in `master`; dates only in `master` are kept. This makes both incremental
    (one new day) and cumulative (full month) uploads correct, and avoids both
    double-counting and collapsing identical same-day fills."""
    if master is None or master.empty:
        return new.copy()
    if new is None or new.empty:
        return master.copy()
    new_dates = set(new["date"].dt.normalize())
    kept = master[~master["date"].dt.normalize().isin(new_dates)]
    return pd.concat([kept, new], ignore_index=True)


def backup_csv(trades: pd.DataFrame) -> str:
    out = trades.copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return out.to_csv(index=False)


@st.cache_data(show_spinner=False)
def build_journal(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate to a daily journal using realized P&L.

    Each option contract (instrument + description = strike + expiry + put/call)
    is tracked with an average cost basis. Opens (BTO/STO) add to the basis;
    closes (STC/BTC) realize P&L = proceeds − average cost of the quantity
    closed, attributed to the *closing* day. Expirations (OEXP) realize the
    remaining basis as a loss. This is correct for both same-day (0DTE) trades
    and positions held across multiple days. A "trade" for a given day is a
    contract that had a realized close (or expiry) that day; a win is realized
    P&L > 0. Positions still open contribute no realized P&L until closed.
    """
    if trades.empty:
        return pd.DataFrame(columns=["date", "pnl", "trades", "wins", "win_rate"])

    t = trades.copy()
    t["quantity"] = pd.to_numeric(t["quantity"], errors="coerce").fillna(0.0)
    t["amount"] = pd.to_numeric(t["amount"], errors="coerce").fillna(0.0)
    t = t.sort_values("date", kind="stable")

    rows = []  # (date, realized_pnl) per contract-day that had a realized close
    for _, g in t.groupby(["instrument", "description"], dropna=False):
        carry_q = 0.0   # open contracts carried across days
        carry_c = 0.0   # cost basis of those carried contracts
        for dt, gd in g.groupby("date"):
            opens = gd[gd["trans_code"].isin(["BTO", "STO"])]
            closes = gd[gd["trans_code"].isin(["STC", "BTC"])]
            expd = gd[gd["trans_code"] == "OEXP"]

            open_q = opens["quantity"].sum()
            open_c = -opens["amount"].sum()           # buys are negative -> positive cost
            close_q = closes["quantity"].sum()
            close_proceeds = closes["amount"].sum()    # sells are positive

            avail_q = carry_q + open_q
            avail_c = carry_c + open_c
            avg = avail_c / avail_q if avail_q > 0 else 0.0

            day_pnl = 0.0
            had_close = False

            if close_q > 0:
                had_close = True
                eff_q = min(close_q, avail_q)
                # scale proceeds if (rarely) more closed than we can account for
                proceeds = close_proceeds * (eff_q / close_q) if close_q else 0.0
                day_pnl += proceeds - avg * eff_q
                avail_q -= eff_q
                avail_c -= avg * eff_q

            if len(expd) > 0:
                had_close = True
                day_pnl += -avail_c       # remaining basis expires worthless
                avail_q = 0.0
                avail_c = 0.0

            if had_close:
                rows.append((dt, day_pnl))

            carry_q, carry_c = avail_q, avail_c

    if not rows:
        return pd.DataFrame(columns=["date", "pnl", "trades", "wins", "win_rate"])

    rt = pd.DataFrame(rows, columns=["date", "pnl"])
    daily = (
        rt.groupby("date")
        .agg(
            pnl=("pnl", "sum"),
            trades=("pnl", "size"),
            wins=("pnl", lambda s: int((s > 0).sum())),
        )
        .reset_index()
    )
    daily["win_rate"] = (daily["wins"] / daily["trades"] * 100).round(1)
    return daily.sort_values("date").reset_index(drop=True)


# --------------------------------------------------------------------------- #
#  Formatting helpers
# --------------------------------------------------------------------------- #
def fmt_money(v: float, k: bool = True) -> str:
    sign = "-" if v < 0 else ""
    a = abs(v)
    if k and a >= 1000:
        return f"{sign}${a/1000:.2f}K"
    return f"{sign}${a:,.0f}" if a >= 100 else f"{sign}${a:,.2f}"


def day_color(pnl: float, max_abs: float, P: dict) -> tuple[str, str, str]:
    """Return (background, border, text_color) scaled by magnitude for theme P."""
    if pnl == 0:
        return P["cell_empty_bg"], P["cell_empty_border"], P["amt_text"]
    intensity = 0.10 + 0.28 * min(abs(pnl) / max_abs, 1.0) if max_abs else 0.18
    if pnl > 0:
        txt = P["green"] if P["amt_colored"] else P["amt_text"]
        return f"rgba({P['green_rgb']},{intensity:.2f})", f"rgba({P['green_rgb']},0.40)", txt
    txt = P["red"] if P["amt_colored"] else P["amt_text"]
    return f"rgba({P['red_rgb']},{intensity:.2f})", f"rgba({P['red_rgb']},0.40)", txt


# --------------------------------------------------------------------------- #
#  Calendar rendering
# --------------------------------------------------------------------------- #
def render_calendar(year: int, month: int, daily: pd.DataFrame, P: dict) -> str:
    """Build an HTML calendar grid styled like a trading-journal calendar."""
    stats = {
        r["date"].day: r
        for _, r in daily.iterrows()
        if r["date"].year == year and r["date"].month == month
    }
    max_abs = max([abs(s["pnl"]) for s in stats.values()], default=1) or 1

    calendar.setfirstweekday(calendar.SUNDAY)
    weeks = calendar.monthcalendar(year, month)
    dow = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

    css = f"""
    <style>
    .cal {{ width:100%; border-collapse:separate; border-spacing:6px; font-family:-apple-system,Segoe UI,Roboto,sans-serif; }}
    .cal th {{ color:{P['muted']}; font-weight:600; font-size:12px; padding:8px 0;
              background:{P['th_bg']}; border:1px solid {P['th_border']}; border-radius:8px; }}
    .cell {{ border-radius:10px; padding:8px 10px; height:80px; vertical-align:top;
            border:1px solid {P['cell_empty_border']}; background:{P['cell_empty_bg']}; position:relative; }}
    .cell .dnum {{ position:absolute; top:6px; right:9px; font-size:11px; color:{P['day_num']}; }}
    .cell .pnl  {{ font-size:17px; font-weight:700; margin-top:16px; color:{P['amt_text']};
                  font-variant-numeric:tabular-nums; }}
    .cell .sub  {{ font-size:11px; color:{P['muted']}; line-height:1.35; }}
    .empty {{ background:transparent; border:none; }}
    </style>
    """

    html = css + "<table class='cal'><tr>" + "".join(f"<th>{d}</th>" for d in dow) + "</tr>"
    for week in weeks:
        html += "<tr>"
        for day in week:
            if day == 0:
                html += "<td class='empty'></td>"
                continue
            if day in stats:
                s = stats[day]
                bg, border, txt = day_color(s["pnl"], max_abs, P)
                tip = (
                    f"Realized P&L: {fmt_money(s['pnl'], k=False)} · "
                    f"{int(s['trades'])} closed trade{'s' if s['trades']!=1 else ''} · "
                    f"{s['win_rate']:.0f}% win — booked on the day each trade was closed "
                    f"(matches Robinhood's Realized P&L page)."
                )
                html += (
                    f"<td class='cell' style='background:{bg};border-color:{border}' title=\"{tip}\">"
                    f"<div class='dnum'>{day}</div>"
                    f"<div class='pnl' style='color:{txt}'>{fmt_money(s['pnl'])}</div>"
                    f"<div class='sub'>{int(s['trades'])} trade{'s' if s['trades']!=1 else ''}<br>"
                    f"{s['win_rate']:.1f}%</div>"
                    f"</td>"
                )
            else:
                html += f"<td class='cell'><div class='dnum'>{day}</div></td>"
        html += "</tr>"
    html += "</table>"
    return html


def weekly_summary(year: int, month: int, daily: pd.DataFrame) -> list[dict]:
    calendar.setfirstweekday(calendar.SUNDAY)
    weeks = calendar.monthcalendar(year, month)
    stats = {
        r["date"].day: r
        for _, r in daily.iterrows()
        if r["date"].year == year and r["date"].month == month
    }
    out = []
    for i, week in enumerate(weeks, 1):
        days = [d for d in week if d in stats]
        if not days:
            continue
        pnl = sum(stats[d]["pnl"] for d in days)
        out.append({"week": i, "pnl": pnl, "days": len(days)})
    return out


# --------------------------------------------------------------------------- #
#  Main app
# --------------------------------------------------------------------------- #
def main():
    P = get_palette()
    st.markdown(global_css(P), unsafe_allow_html=True)
    st.title("📈 Trade Journal")

    with st.sidebar:
        st.radio(
            "Theme",
            ["Light", "Dark"],
            key="theme",
            horizontal=True,
        )
        st.divider()
        st.header("Upload activity")
        st.caption(
            "Drop in your Robinhood **Account → Statements & history → "
            "Export** CSV. New uploads are **saved and merged** with what's "
            "already there — upload just the new day, or a full export; either "
            "works. You can also re-upload a backup file here to restore."
        )
        files = st.file_uploader(
            "CSV export(s)",
            type=["csv"],
            accept_multiple_files=True,
        )
        if st.button("🚪 Log out"):
            keep = {"theme": st.session_state.get("theme")}
            st.session_state.clear()
            st.session_state.update(keep)
            st.rerun()

    # ---- Load saved data, merge any new uploads, persist -------------------
    master = load_master()
    if files:
        new = load_trades([f.getvalue() for f in files])
        if new.empty:
            st.warning("No option trades found in the uploaded file(s); showing saved data.")
            trades = master
        else:
            trades = merge_by_date(master, new)
            save_master(trades)
    else:
        trades = master

    if trades.empty:
        st.info("👈 Upload a Robinhood CSV export to build your journal.")
        st.markdown(
            "**How P&L is calculated:** realized profit/loss per closed trade. "
            "Each option contract is tracked at average cost — buying opens or "
            "adds to a position, selling closes it, and the gain or loss is "
            "booked on the day you *close* (so a trade held overnight counts on "
            "the day it's sold, not split across days). A *win* is a closed "
            "contract with positive realized P&L. Cash transfers, fees, and "
            "subscriptions are ignored, and still-open positions don't count "
            "until you close them."
        )
        return

    # ---- Saved-data status + backup/reset (sidebar) -----------------------
    with st.sidebar:
        st.divider()
        dmin, dmax = trades["date"].min(), trades["date"].max()
        ndays = trades["date"].dt.normalize().nunique()
        st.caption(
            f"💾 **Saved:** {dmin.strftime('%b %-d')} → {dmax.strftime('%b %-d, %Y')} "
            f"· {ndays} day{'s' if ndays != 1 else ''}"
        )
        st.download_button(
            "⬇️ Download backup",
            backup_csv(trades),
            file_name="trade_journal_backup.csv",
            mime="text/csv",
            help="Save a copy you can re-upload later to restore your journal.",
        )
        if st.session_state.get("confirm_reset"):
            st.warning("Delete all saved data?")
            c_yes, c_no = st.columns(2)
            if c_yes.button("Yes, delete"):
                if os.path.exists(MASTER_FILE):
                    os.remove(MASTER_FILE)
                st.session_state.pop("confirm_reset", None)
                st.rerun()
            if c_no.button("Cancel"):
                st.session_state.pop("confirm_reset", None)
                st.rerun()
        elif st.button("🗑️ Reset saved data"):
            st.session_state["confirm_reset"] = True
            st.rerun()

    daily = build_journal(trades)

    # Month picker — default to most recent month in the data
    months = sorted({(d.year, d.month) for d in daily["date"]}, reverse=True)
    labels = [f"{calendar.month_name[m]} {y}" for (y, m) in months]
    pick = st.selectbox("Month", labels, index=0)
    year, month = months[labels.index(pick)]

    mdaily = daily[(daily["date"].dt.year == year) & (daily["date"].dt.month == month)]

    # ---- Monthly stat header (GEX-Metrix-style data strip) ----------------
    total = mdaily["pnl"].sum()
    n_days = len(mdaily)
    n_trades = int(mdaily["trades"].sum())
    n_wins = int(mdaily["wins"].sum())
    win_rate = (n_wins / n_trades * 100) if n_trades else 0
    green_days = int((mdaily["pnl"] > 0).sum())
    avg_day = total / n_days if n_days else 0
    best = mdaily.loc[mdaily["pnl"].idxmax()] if n_days else None
    worst = mdaily.loc[mdaily["pnl"].idxmin()] if n_days else None
    pnl_color = P["green"] if total >= 0 else P["red"]

    st.markdown(
        gex_strip(
            [
                ("Net P&L", fmt_money(total, k=False), pnl_color),
                ("Win Rate", f"{win_rate:.1f}%", ""),
                ("Trading Days", str(n_days), ""),
                ("Total Trades", str(n_trades), ""),
                ("Green Days", f"{green_days}/{n_days}", ""),
                ("Avg / Day", fmt_money(avg_day, k=False), P["green"] if avg_day >= 0 else P["red"]),
                (
                    "Best Day",
                    f"{fmt_money(best['pnl'])} · {best['date'].strftime('%-m/%-d')}" if best is not None else "—",
                    (P["green"] if best["pnl"] >= 0 else P["red"]) if best is not None else "",
                ),
                (
                    "Worst Day",
                    f"{fmt_money(worst['pnl'])} · {worst['date'].strftime('%-m/%-d')}" if worst is not None else "—",
                    (P["green"] if worst["pnl"] >= 0 else P["red"]) if worst is not None else "",
                ),
            ]
        ),
        unsafe_allow_html=True,
    )

    # ---- Calendar + weekly rail -------------------------------------------
    left, right = st.columns([4, 1])
    with left:
        st.markdown(f"#### {calendar.month_name[month]} {year}")
        st.caption(
            "Figures are **realized P&L**, booked on the day a trade is *closed* "
            "(matches Robinhood's **Realized profit & loss** page). This won't equal "
            "the home-screen **\"Today\"** number, which marks open positions to "
            "market — they differ only when a position is held overnight."
        )
        st.markdown(render_calendar(year, month, daily, P), unsafe_allow_html=True)
    with right:
        st.markdown("#### Weekly")
        for w in weekly_summary(year, month, daily):
            color = P["green"] if w["pnl"] >= 0 else P["red"]
            st.markdown(
                f"<div style='border:1px solid {P['border']};border-radius:12px;"
                f"background:{P['panel']};padding:11px 14px;margin-bottom:9px;"
                f"box-shadow:{P['shadow']};'>"
                f"<div style='font-size:12px;color:{P['muted']};font-weight:600;'>Week {w['week']}</div>"
                f"<div style='font-size:21px;font-weight:700;color:{color};"
                f"font-variant-numeric:tabular-nums;margin:2px 0 6px;'>{fmt_money(w['pnl'])}</div>"
                f"<span style='font-size:11px;color:{P['muted']};background:{P['pill_bg']};"
                f"border-radius:20px;padding:2px 10px;'>{w['days']} day"
                f"{'s' if w['days']!=1 else ''}</span></div>",
                unsafe_allow_html=True,
            )

    st.divider()

    # ---- Equity curve ------------------------------------------------------
    st.markdown("#### Cumulative P&L (selected month)")
    curve = mdaily.copy()
    curve["cumulative"] = curve["pnl"].cumsum()
    st.line_chart(curve.set_index("date")["cumulative"], height=260, color=P["accent"])

    # ---- Detail table ------------------------------------------------------
    with st.expander("📋 Daily detail"):
        show = mdaily.copy()
        show["date"] = show["date"].dt.strftime("%a %m/%d")
        show = show.rename(
            columns={
                "date": "Date",
                "pnl": "P&L ($)",
                "trades": "Trades",
                "wins": "Wins",
                "win_rate": "Win %",
            }
        )[["Date", "P&L ($)", "Trades", "Wins", "Win %"]]
        st.dataframe(show, use_container_width=True, hide_index=True)

        csv = mdaily.assign(date=mdaily["date"].dt.strftime("%Y-%m-%d")).to_csv(index=False)
        st.download_button(
            "⬇️ Download this month's journal (CSV)",
            csv,
            file_name=f"journal_{year}_{month:02d}.csv",
            mime="text/csv",
        )


# --------------------------------------------------------------------------- #
if not check_password():
    st.stop()
main()
