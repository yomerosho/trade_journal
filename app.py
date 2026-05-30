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

# GEX-Metrix-inspired dark palette
GREEN = "#16c784"   # calls / profit
RED = "#f6465d"     # puts / loss
ACCENT = "#22d3ee"  # cyan accent
PANEL = "#131722"
PANEL_2 = "#1c2230"
BORDER = "rgba(255,255,255,0.07)"
MUTED = "#8b93a7"
TEXT = "#e6e9ef"

GLOBAL_CSS = f"""
<style>
  .stApp {{ background:#0b0e14; }}
  /* Metric tiles */
  div[data-testid="stMetric"] {{
      background:{PANEL}; border:1px solid {BORDER}; border-radius:12px;
      padding:14px 16px;
  }}
  div[data-testid="stMetricLabel"] p {{
      color:{MUTED}; font-size:12px; text-transform:uppercase; letter-spacing:.06em;
  }}
  div[data-testid="stMetricValue"] {{
      font-variant-numeric:tabular-nums; font-weight:700;
  }}
  /* GEX-Metrix style top data strip */
  .gex-strip {{
      display:flex; flex-wrap:wrap; gap:0; background:{PANEL};
      border:1px solid {BORDER}; border-radius:12px; overflow:hidden;
      margin-bottom:18px; font-family:-apple-system,Segoe UI,Roboto,sans-serif;
  }}
  .gex-cell {{
      flex:1 1 14%; min-width:120px; padding:10px 16px;
      border-right:1px solid {BORDER};
  }}
  .gex-cell:last-child {{ border-right:none; }}
  .gex-cell .lbl {{ color:{MUTED}; font-size:10.5px; text-transform:uppercase;
      letter-spacing:.07em; margin-bottom:3px; }}
  .gex-cell .val {{ font-size:18px; font-weight:700; font-variant-numeric:tabular-nums;
      color:{TEXT}; }}
  h1,h2,h3,h4 {{ letter-spacing:-.01em; }}
</style>
"""


def gex_strip(items: list[tuple[str, str, str]]) -> str:
    """Render a GEX-Metrix-style horizontal label/value strip.
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


def day_color(pnl: float, max_abs: float) -> tuple[str, str, str]:
    """Return (background, border, text_color) scaled by magnitude, dark-theme."""
    if pnl == 0:
        return "#131722", "rgba(255,255,255,0.06)", "#8b93a7"
    intensity = 0.10 + 0.30 * min(abs(pnl) / max_abs, 1.0) if max_abs else 0.2
    if pnl > 0:
        return f"rgba(22,199,132,{intensity:.2f})", "rgba(22,199,132,0.45)", GREEN
    return f"rgba(246,70,93,{intensity:.2f})", "rgba(246,70,93,0.45)", RED


# --------------------------------------------------------------------------- #
#  Calendar rendering
# --------------------------------------------------------------------------- #
def render_calendar(year: int, month: int, daily: pd.DataFrame) -> str:
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

    css = """
    <style>
    .cal { width:100%; border-collapse:separate; border-spacing:6px; font-family:-apple-system,Segoe UI,Roboto,sans-serif; }
    .cal th { color:#8b93a7; font-weight:600; font-size:12px; text-transform:uppercase;
              letter-spacing:.06em; padding:6px 0; }
    .cell { border-radius:10px; padding:8px 10px; height:80px; vertical-align:top;
            border:1px solid rgba(255,255,255,0.06); background:#131722; position:relative; }
    .cell .dnum { position:absolute; top:6px; right:9px; font-size:11px; color:#6b7280; }
    .cell .pnl  { font-size:17px; font-weight:700; margin-top:16px;
                  font-variant-numeric:tabular-nums; }
    .cell .sub  { font-size:11px; color:#8b93a7; line-height:1.35; }
    .empty { background:transparent; border:none; }
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
                bg, border, txt = day_color(s["pnl"], max_abs)
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
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
    st.title("📈 0DTE Trade Journal")

    with st.sidebar:
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
            st.session_state.clear()
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
    pnl_color = GREEN if total >= 0 else RED

    st.markdown(
        gex_strip(
            [
                ("Net P&L", fmt_money(total, k=False), pnl_color),
                ("Win Rate", f"{win_rate:.1f}%", ""),
                ("Trading Days", str(n_days), ""),
                ("Total Trades", str(n_trades), ""),
                ("Green Days", f"{green_days}/{n_days}", ""),
                ("Avg / Day", fmt_money(avg_day, k=False), GREEN if avg_day >= 0 else RED),
                (
                    "Best Day",
                    f"{fmt_money(best['pnl'])} · {best['date'].strftime('%-m/%-d')}" if best is not None else "—",
                    GREEN,
                ),
                (
                    "Worst Day",
                    f"{fmt_money(worst['pnl'])} · {worst['date'].strftime('%-m/%-d')}" if worst is not None else "—",
                    RED,
                ),
            ]
        ),
        unsafe_allow_html=True,
    )

    # ---- Calendar + weekly rail -------------------------------------------
    left, right = st.columns([4, 1])
    with left:
        st.markdown(f"#### {calendar.month_name[month]} {year}")
        st.markdown(render_calendar(year, month, daily), unsafe_allow_html=True)
    with right:
        st.markdown("#### Weekly")
        for w in weekly_summary(year, month, daily):
            color = GREEN if w["pnl"] >= 0 else RED
            st.markdown(
                f"<div style='border:1px solid {BORDER};border-radius:10px;"
                f"background:{PANEL};padding:10px 12px;margin-bottom:8px;'>"
                f"<div style='font-size:11px;color:{MUTED};text-transform:uppercase;"
                f"letter-spacing:.06em;'>Week {w['week']}</div>"
                f"<div style='font-size:20px;font-weight:700;color:{color};"
                f"font-variant-numeric:tabular-nums;'>{fmt_money(w['pnl'])}</div>"
                f"<div style='font-size:11px;color:{MUTED};'>{w['days']} day"
                f"{'s' if w['days']!=1 else ''}</div></div>",
                unsafe_allow_html=True,
            )

    st.divider()

    # ---- Equity curve ------------------------------------------------------
    st.markdown("#### Cumulative P&L (selected month)")
    curve = mdaily.copy()
    curve["cumulative"] = curve["pnl"].cumsum()
    st.line_chart(curve.set_index("date")["cumulative"], height=260, color=ACCENT)

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
