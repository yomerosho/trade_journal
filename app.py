"""
0DTE Trade Journal — Streamlit app
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
    page_title="0DTE Trade Journal",
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
        st.markdown("## 📈 0DTE Trade Journal")
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


@st.cache_data(show_spinner=False)
def load_trades(file_bytes_list: list[bytes]) -> pd.DataFrame:
    """
    Parse one or more Robinhood activity CSV exports into a clean trades frame.
    Multiple files are concatenated and de-duplicated, so you can upload a fresh
    export a couple of times a week and the journal just grows.
    """
    from io import BytesIO
    import hashlib

    # De-duplicate whole identical files (so re-uploading the same export is a
    # no-op) WITHOUT collapsing genuine identical fills inside a single export.
    seen, frames = set(), []
    for raw in file_bytes_list:
        h = hashlib.md5(raw).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        frames.append(pd.read_csv(BytesIO(raw), on_bad_lines="skip"))

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)

    # Robinhood column names
    needed = ["Activity Date", "Instrument", "Description", "Trans Code", "Quantity", "Price", "Amount"]
    for col in needed:
        if col not in df.columns:
            df[col] = pd.NA

    # Drop footer / blank rows
    df = df.dropna(subset=["Activity Date", "Trans Code"])
    df = df[df["Activity Date"].astype(str).str.strip() != ""]

    df["amount"] = df["Amount"].apply(parse_money)
    df["date"] = pd.to_datetime(df["Activity Date"], errors="coerce")
    df = df.dropna(subset=["date"])

    # Keep only option trade legs
    trades = df[df["Trans Code"].isin(TRADE_CODES)].copy()
    trades = trades.rename(
        columns={
            "Instrument": "instrument",
            "Description": "description",
            "Trans Code": "trans_code",
            "Quantity": "quantity",
            "Price": "price",
        }
    )
    return trades[["date", "instrument", "description", "trans_code", "price", "amount"]].reset_index(drop=True)


@st.cache_data(show_spinner=False)
def build_journal(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate to a daily journal.

    A 'trade' is one option contract (instrument + description, i.e. strike +
    expiry + put/call) round-tripped on a given day. Its P&L is the net of all
    its legs that day (opens are negative, closes positive). A win is net > 0.
    """
    if trades.empty:
        return pd.DataFrame()

    by_contract = (
        trades.groupby(["date", "instrument", "description"])["amount"]
        .sum()
        .reset_index()
    )
    daily = (
        by_contract.groupby("date")
        .agg(
            pnl=("amount", "sum"),
            trades=("amount", "size"),
            wins=("amount", lambda s: int((s > 0).sum())),
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
                html += (
                    f"<td class='cell' style='background:{bg};border-color:{border}'>"
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
    st.title("📈 0DTE Trade Journal")

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
            "Export** CSV. Tip: each visit, export your **full month-to-date** "
            "activity and upload that one file — it always shows the complete "
            "picture. (Uploading the same file twice is harmless.)"
        )
        files = st.file_uploader(
            "Robinhood CSV export(s)",
            type=["csv"],
            accept_multiple_files=True,
        )
        if st.button("🚪 Log out"):
            keep = {"theme": st.session_state.get("theme")}
            st.session_state.clear()
            st.session_state.update(keep)
            st.rerun()

    if not files:
        st.info("👈 Upload one or more Robinhood CSV exports to build your journal.")
        st.markdown(
            "**How P&L is calculated:** each option contract (same strike, "
            "expiry, and put/call) is treated as one *trade*. Its P&L is the "
            "net of every leg that day — buys count as cost, sells as proceeds. "
            "A *win* is any contract that closed net-positive. Cash transfers, "
            "fees, and subscriptions are ignored."
        )
        return

    trades = load_trades([f.getvalue() for f in files])
    if trades.empty:
        st.warning("No option trades found in the uploaded file(s).")
        return

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
