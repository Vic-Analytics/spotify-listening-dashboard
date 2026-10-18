"""
db.py - everything the project needs to talk to the SQLite database.

The collector (Phase 3), the importer (Phase 5) and the dashboard (Phase 7)
all use these functions, so the rules about how data is stored live in one place.

SQLite stores the whole database in a single file. Python includes it
(the `sqlite3` module), so there is nothing to install or run.
"""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Your real data lives here. "*.db" is in .gitignore, so it is never uploaded.
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "spotify.db"


def get_db_path() -> Path:
    """Use SPOTIFY_DB_PATH from the environment if set, otherwise the default.
    (Later the demo dashboard will point this at the fake sample database.)"""
    override = os.getenv("SPOTIFY_DB_PATH")
    return Path(override) if override else DEFAULT_DB_PATH


def get_connection(db_path=None) -> sqlite3.Connection:
    """Open the database (creating the file if needed) and make sure the
    `plays` table exists. Pass ":memory:" for a throwaway database in tests."""
    db_path = str(db_path or get_db_path())
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # lets us read columns by name: row["artist_name"]
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def normalize_timestamp(value: str) -> str:
    """
    Convert any ISO timestamp into our one standard format: UTC, whole seconds.
        '2026-10-16T19:21:53.789Z'  ->  '2026-10-16T19:21:53Z'

    The API gives milliseconds; the export doesn't. Cutting both down to whole
    seconds means the same play looks identical in both sources, which is what
    lets the UNIQUE rule catch duplicates.
    """
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# The columns we write, in order. ":name" placeholders are filled from a dict.
_INSERT_SQL = """
    INSERT OR IGNORE INTO plays (
        played_at, track_uri, track_id, track_name, artist_name, artist_id,
        all_artists, album_name, duration_ms, ms_played, skipped,
        context_type, source, collected_at
    ) VALUES (
        :played_at, :track_uri, :track_id, :track_name, :artist_name, :artist_id,
        :all_artists, :album_name, :duration_ms, :ms_played, :skipped,
        :context_type, :source, :collected_at
    )
"""
# "INSERT OR IGNORE" = if the UNIQUE rule says this play already exists, skip
# it silently instead of crashing. That is the whole de-duplication mechanism.

_OPTIONAL_COLUMNS = (
    "track_id", "track_name", "artist_name", "artist_id", "all_artists",
    "album_name", "duration_ms", "ms_played", "skipped", "context_type",
)


def save_plays(conn: sqlite3.Connection, plays: list[dict], source: str) -> tuple[int, int]:
    """
    Save flat play rows. Returns (new_rows_added, duplicates_skipped).
    `source` is 'api' or 'export'.
    """
    collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    rows = []
    for play in plays:
        row = {col: play.get(col) for col in _OPTIONAL_COLUMNS}  # missing -> None
        row["played_at"] = normalize_timestamp(play["played_at"])
        row["track_uri"] = play["track_uri"]
        row["source"] = source
        row["collected_at"] = collected_at
        rows.append(row)

    changes_before = conn.total_changes
    conn.executemany(_INSERT_SQL, rows)
    conn.commit()  # without commit(), the changes would be thrown away

    added = conn.total_changes - changes_before  # only rows that really went in
    return added, len(rows) - added


def count_plays(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM plays").fetchone()[0]
