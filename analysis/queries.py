"""
queries.py - connects to the database and runs the .sql files in analysis/sql.

Why keep SQL in separate .sql files instead of inside Python strings?
  * Each query is easy to read, review, and show off on GitHub.
  * An editor can highlight and check it as real SQL.
  * Python only has to say WHICH query to run and with what settings.

Typical use:
    conn = connect()
    df = run_query(conn, "top_artists", start="2025-01-01", end="2025-12-31", limit=10)
"""

import os
import sqlite3
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import load_dotenv

from database.db import PROJECT_ROOT, get_db_path

load_dotenv(PROJECT_ROOT / ".env")

SQL_DIR = Path(__file__).resolve().parent / "sql"

# Values used when the caller doesn't supply one. The wide default date range
# means "everything".
DEFAULT_PARAMS = {
    "start": "0000-01-01",
    "end": "9999-12-31",
    "limit": 20,
    "min_plays": 100,
}


def get_timezone_name() -> str:
    """The time zone for hour-of-day charts. Set TIMEZONE in .env; UTC if unset."""
    return os.getenv("TIMEZONE") or "UTC"


def _make_utc_offset_seconds(zone: ZoneInfo):
    """
    Build the utc_offset_seconds() function that 00_setup.sql calls from inside SQL.

    It answers: "how many seconds is this time zone ahead of UTC at this moment?"
    (Chicago: -18000 in summer, -21600 in winter, which is how daylight saving
    is handled.) SQLite's own datetime() then shifts the timestamp by that many seconds.

    Time zone math is slow in Python, and we have ~290,000 plays. But the offset
    only changes at daylight-saving switches, so we work it out once per
    15-minute window and remember the answer (lru_cache) instead of once per play.
    """

    @lru_cache(maxsize=None)
    def offset_for_window(window: str) -> int:
        # window looks like '2026-10-17T03:30' (UTC)
        moment = datetime.fromisoformat(window + ":00+00:00")
        return int(moment.astimezone(zone).utcoffset().total_seconds())

    def utc_offset_seconds(utc_text: str) -> int:
        # utc_text looks like '2026-10-17T03:37:12Z'; round minutes down to :00/:15/:30/:45
        quarter_hour = int(utc_text[14:16]) // 15 * 15
        return offset_for_window(f"{utc_text[:14]}{quarter_hour:02d}")

    return utc_offset_seconds


def prepare(conn: sqlite3.Connection, tz_name: str | None = None) -> sqlite3.Connection:
    """Teach an open connection the utc_offset_seconds() function and build the
    helper tables/views from 00_setup.sql. Returns the same connection."""
    zone = ZoneInfo(tz_name or get_timezone_name())
    conn.row_factory = None  # pandas wants plain tuples, not sqlite3.Row objects
    conn.create_function("utc_offset_seconds", 1, _make_utc_offset_seconds(zone), deterministic=True)
    conn.executescript((SQL_DIR / "00_setup.sql").read_text(encoding="utf-8"))
    return conn


def connect(db_path=None, tz_name: str | None = None) -> sqlite3.Connection:
    """Open the database read-only and prepare it for analysis."""
    path = Path(db_path or get_db_path())
    if not path.exists():
        raise FileNotFoundError(f"Database not found: {path}")
    # mode=ro: this connection physically cannot change your data.
    # check_same_thread=False: the Streamlit dashboard shares one connection
    # between its worker threads (reads only, so this is safe).
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, check_same_thread=False)
    # Temp tables still work on a read-only connection: they live in memory/temp.
    return prepare(conn, tz_name)


def run_query(conn: sqlite3.Connection, name: str, **params) -> pd.DataFrame:
    """
    Run analysis/sql/<name>.sql and return the result as a pandas DataFrame.
    Any parameter you leave out (start, end, limit, min_plays) gets its default.

    The :start / :end placeholders in the SQL are filled in by SQLite itself
    ("parameter binding"), never pasted into the text. That keeps the queries
    safe from SQL injection and avoids quoting mistakes.
    """
    sql = (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")
    return pd.read_sql_query(sql, conn, params={**DEFAULT_PARAMS, **params})
