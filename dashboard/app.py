"""
app.py - the Streamlit dashboard.

Run it from the project folder with:
    streamlit run dashboard/app.py

How Streamlit works (the short version): it runs this whole file top to bottom
every time you click something. Whatever st.something(...) calls it meets along
the way are drawn on the page. So the file reads like a page, top to bottom:
sidebar controls first, then the numbers and charts that depend on them.
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

# `streamlit run dashboard/app.py` puts the dashboard folder on the import path,
# not the project root, so add the root to let us import analysis/ and database/.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from analysis.metrics import (add_cumulative_artists, fill_missing_periods,  # noqa: E402
                              heatmap_matrix, streak_summary)
from analysis.queries import connect, get_timezone_name, run_query  # noqa: E402
from dashboard import charts  # noqa: E402
from database.db import get_connection, get_db_path  # noqa: E402
from database.pull_cloud import sync_from_cloud  # noqa: E402

st.set_page_config(page_title="My Spotify Listening Stats", page_icon="🎧", layout="wide")

SAMPLE_DB = PROJECT_ROOT / "data" / "sample" / "sample.db"
DATE_PRESETS = ["All time", "Last 30 days", "Last 90 days", "Last 12 months", "This year", "Custom range"]


# ---------------------------------------------------------------------------
# Data access. Streamlit re-runs this file on every click, so we CACHE the slow
# parts: opening the database (a few seconds on a big history) and the queries.
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner="Preparing your data…")
def open_database(path: str, tz_name: str, file_version: float):
    """One shared read-only connection per database file. `file_version` (the
    file's modified time) is part of the cache key, so the connection rebuilds
    itself automatically after new plays are synced."""
    return connect(path, tz_name)


@st.cache_data(show_spinner=False)
def cached_query(_conn, db_key: tuple, name: str, **params) -> pd.DataFrame:
    """Run one analysis/sql query. The leading underscore on `_conn` tells
    Streamlit not to try to hash the connection; `db_key` identifies the data."""
    return run_query(_conn, name, **params)


def available_sources() -> dict:
    """Which datasets can the viewer choose from?"""
    sources = {}
    real_db = get_db_path()
    # On the public demo site the real database doesn't exist (it is git-ignored),
    # so only the fake sample is offered. DASHBOARD_DEMO=1 forces that anywhere.
    if real_db.exists() and real_db.resolve() != SAMPLE_DB.resolve() and os.getenv("DASHBOARD_DEMO") != "1":
        sources["My listening history"] = (real_db, get_timezone_name(), True)
    sources["Demo sample (fake data)"] = (SAMPLE_DB, "UTC", False)
    return sources


def date_range_for(preset: str, first: date, last: date) -> tuple[date, date]:
    """Presets count back from your LATEST data, not from today's date."""
    if preset == "All time":
        return first, last
    if preset == "This year":
        return max(first, date(last.year, 1, 1)), last
    days = {"Last 30 days": 30, "Last 90 days": 90, "Last 12 months": 365}[preset]
    return max(first, last - timedelta(days=days - 1)), last


def fmt_time(minutes: float) -> str:
    return f"{minutes / 60:,.0f} hours" if minutes >= 600 else f"{minutes:,.0f} min"


def table_view(df: pd.DataFrame, label: str = "Table view") -> None:
    """Every chart has a table twin, for exact values and screen-reader users."""
    with st.expander(label):
        st.dataframe(df, hide_index=True, width="stretch")


def show(fig) -> None:
    st.plotly_chart(fig, width="stretch", config=charts.PLOT_CONFIG, theme=None)


# ---------------------------------------------------------------------------
# Sidebar: choose data and filters
# ---------------------------------------------------------------------------
sources = available_sources()

st.sidebar.header("Filters")
source_name = st.sidebar.radio("Data", list(sources), index=0) if len(sources) > 1 else list(sources)[0]
db_path, tz_name, is_real = sources[source_name]

if not Path(db_path).exists():
    st.error(f"Database not found: {db_path}\n\nGenerate the demo data with "
             "`python -m scripts.make_sample_data`.")
    st.stop()

file_version = Path(db_path).stat().st_mtime
conn = open_database(str(db_path), tz_name, file_version)
db_key = (str(db_path), tz_name, file_version)


def query(name: str, **params) -> pd.DataFrame:
    return cached_query(conn, db_key, name, **params)


bounds = query("summary").iloc[0]
if not bounds["plays"]:
    st.warning("This database has no plays yet.")
    st.stop()
first_day, last_day = date.fromisoformat(bounds["first_date"]), date.fromisoformat(bounds["last_date"])

preset = st.sidebar.selectbox("Date range", DATE_PRESETS)
if preset == "Custom range":
    picked = st.sidebar.date_input("Pick dates", value=(first_day, last_day),
                                   min_value=first_day, max_value=last_day)
    if len(picked) != 2:
        st.info("Pick an end date to apply the range.")
        st.stop()
    start_day, end_day = picked
else:
    start_day, end_day = date_range_for(preset, first_day, last_day)
filters = {"start": start_day.isoformat(), "end": end_day.isoformat()}

top_n = st.sidebar.slider("Items in top lists", 5, 25, 10)

if is_real:
    st.sidebar.divider()
    st.sidebar.caption(f"Latest listening day in database: **{last_day:%b %d, %Y}**")
    if st.sidebar.button("Sync new plays from GitHub"):
        try:
            write_conn = get_connection(db_path)
            with st.spinner("Downloading from the GitHub data branch…"):
                result = sync_from_cloud(write_conn)
            write_conn.close()
            st.cache_resource.clear()
            st.cache_data.clear()
            st.session_state["sync_message"] = f"Added {result['added']:,} new plays."
            st.rerun()
        except Exception as error:   # show the reason instead of a stack trace
            st.sidebar.error(f"Sync failed: {error}")
    if "sync_message" in st.session_state:
        st.sidebar.success(st.session_state.pop("sync_message"))
else:
    st.sidebar.divider()
    st.sidebar.caption("Showing a **synthetic** listening history made for this demo. "
                       "Artists, tracks and dates are invented.")

# ---------------------------------------------------------------------------
# Header + summary numbers
# ---------------------------------------------------------------------------
st.title("My Spotify Listening Stats")
st.caption(f"{source_name}  ·  {start_day:%b %d, %Y} – {end_day:%b %d, %Y}  ·  times in {tz_name}  ·  "
           "a *play* is 30+ seconds of listening")

summary = query("summary", **filters).iloc[0]
if not summary["plays"]:
    st.warning("No listening in this date range. Try a wider range.")
    st.stop()

# Smaller, wrapping numbers so the five tiles never get cut off on narrower windows.
st.markdown(
    "<style>[data-testid='stMetricValue'] {font-size: 1.6rem; line-height: 1.2;}"
    "[data-testid='stMetricValue'] > div {white-space: normal; overflow-wrap: anywhere;}</style>",
    unsafe_allow_html=True,
)
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Time listened", fmt_time(summary["minutes_listened"]))
k2.metric("Plays", f"{summary['plays']:,.0f}")
k3.metric("Unique artists", f"{summary['unique_artists']:,.0f}")
k4.metric("Unique tracks", f"{summary['unique_tracks']:,.0f}")
k5.metric("Top artist", summary["top_artist"], f"{fmt_time(summary['top_artist_minutes'])}",
          delta_color="off", delta_arrow="off")
st.caption(f"Listened on {summary['active_days']:,.0f} different days.")

tab_top, tab_trends, tab_habits, tab_discovery, tab_skips = st.tabs(
    ["Top lists", "Trends", "Habits & streaks", "Discovery", "Skips"])

# ---- Top lists --------------------------------------------------------------
with tab_top:
    left, right = st.columns(2)
    with left:
        st.subheader("Top artists")
        st.caption("Ranked by time listened")
        artists = query("top_artists", limit=top_n, **filters)
        show(charts.top_artists_chart(artists))
        table_view(artists)
    with right:
        st.subheader("Top tracks")
        st.caption("Ranked by number of plays")
        tracks = query("top_tracks", limit=top_n, **filters)
        show(charts.top_tracks_chart(tracks))
        table_view(tracks)

# ---- Trends -------------------------------------------------------------------
with tab_trends:
    st.subheader("Listening over time")
    period = st.radio("Group by", ["Weekly", "Monthly"], horizontal=True)
    if period == "Weekly":
        trend = fill_missing_periods(query("trend_weekly", **filters), "week_start", "W-MON")
    else:
        trend = fill_missing_periods(query("trend_monthly", **filters), "month_start", "MS")
    show(charts.trend_chart(trend, period))
    st.caption("Weeks start on Monday. A dip to zero means no listening that period.")
    table_view(trend)

# ---- Habits & streaks ------------------------------------------------------------
with tab_habits:
    st.subheader("When do you listen?")
    measure = st.radio("Measure", ["minutes", "plays"], horizontal=True)
    grid = heatmap_matrix(query("heatmap", **filters), value=measure)
    show(charts.heatmap_chart(grid, measure))
    st.caption("Each square is one weekday + hour of the day. Darker blue means more listening.")
    grid_table = grid.round(0).astype(int)
    grid_table.columns = [f"{hour}:00" for hour in grid_table.columns]   # text column names
    table_view(grid_table.reset_index(names="weekday"), "Table view (minutes or plays per weekday and hour)")

    st.subheader("Listening streaks")
    streaks = query("streaks", **filters)
    summary_streak = streak_summary(streaks)
    s1, s2 = st.columns(2)
    s1.metric("Longest streak", f"{summary_streak['longest_days']} days")
    s2.metric("Streak ending at latest listening day", f"{summary_streak['current_days']} days")
    st.caption("A streak is consecutive days with at least one 30+ second play.")
    show(charts.streaks_chart(streaks))
    table_view(streaks.head(25), "Table view (longest streaks)")

# ---- Discovery ----------------------------------------------------------------------
with tab_discovery:
    st.subheader("New artist discovery")
    discovery = add_cumulative_artists(query("discovery", **filters))
    if discovery.empty:
        st.info("No data for this range.")
    else:
        d1, d2 = st.columns(2)
        with d1:
            st.markdown("**New artists per month**")
            show(charts.new_artists_chart(discovery))
        with d2:
            st.markdown("**Share of each month's artists that were new**")
            show(charts.discovery_rate_chart(discovery))
        st.markdown("**Artists discovered so far (running total)**")
        show(charts.cumulative_artists_chart(discovery))
        st.caption("\"New\" means the first month you ever played that artist for 30+ seconds. "
                   "The earliest months of any history look like 100% new simply because the "
                   "data starts there.")
        table_view(discovery)

# ---- Skips ------------------------------------------------------------------------------
with tab_skips:
    st.subheader("Skip behavior")
    skip_trend = query("skips_trend", **filters)
    if skip_trend.empty:
        st.info("Skip data comes from the Extended Streaming History export. "
                "There is none in this date range.")
    else:
        st.caption("A skip means you pressed Next before the track finished. Uses every play, "
                   "including ones under 30 seconds. Only plays from the export carry skip details.")
        if first_day.year < 2022:
            st.caption("Spotify only began filling in its own “skipped” flag in 2022, so this "
                       "dashboard counts Next-button presses instead. Earlier years may still be "
                       "less consistent.")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Skip rate by month**")
            show(charts.skip_rate_chart(skip_trend))
        with c2:
            st.markdown("**How quickly you skip**")
            timing = query("skip_timing", **filters)
            show(charts.skip_timing_chart(timing))

        c3, c4 = st.columns(2)
        with c3:
            st.markdown("**Skip rate by device and shuffle**")
            context = query("skips_by_context", **filters)
            show(charts.skips_by_context_chart(context))
            st.caption("Combinations with fewer than 200 plays are hidden.")
        with c4:
            st.markdown("**Most-skipped artists**")
            min_plays = st.slider("Minimum plays per artist", 10, 500, 100, step=10)
            skipped_artists = query("skips_by_artist", min_plays=min_plays, **filters)
            st.dataframe(skipped_artists.head(15), hide_index=True, width="stretch")

        table_view(skip_trend, "Table view (skip rate by month)")
