"""Tests for the export importer. Run all tests with:   python -m pytest"""

from database.db import count_plays, get_connection, save_plays
from importer.import_export import clean_record, merge_into_db, normalize_platform


def export_record(**overrides):
    """A realistic export record; tests override only the fields they care about."""
    record = {
        "ts": "2026-10-16T19:21:53Z",
        "platform": "ios 17.0 (iPhone14,5)",
        "ms_played": 187000,
        "conn_country": "US",
        "ip_addr": "203.0.113.7",
        "master_metadata_track_name": "Song",
        "master_metadata_album_artist_name": "Artist",
        "master_metadata_album_album_name": "Album",
        "spotify_track_uri": "spotify:track:aaa",
        "episode_name": None,
        "episode_show_name": None,
        "spotify_episode_uri": None,
        "audiobook_uri": None,
        "audiobook_chapter_uri": None,
        "reason_start": "trackdone",
        "reason_end": "fwdbtn",
        "shuffle": True,
        "skipped": True,
        "offline": False,
        "incognito_mode": False,
    }
    record.update(overrides)
    return record


# ---------- cleaning ----------

def test_a_normal_track_is_converted_to_our_format():
    row, reason = clean_record(export_record())
    assert reason is None
    assert row["played_at"] == "2026-10-16T19:21:53Z"
    assert row["track_id"] == "aaa"
    assert row["ms_played"] == 187000
    assert row["skipped"] == 1 and row["shuffle"] == 1  # True -> 1
    assert row["platform"] == "iOS"


def test_the_ip_address_is_never_copied():
    row, _ = clean_record(export_record())
    assert "ip_addr" not in row
    assert "203.0.113.7" not in row.values()


def test_podcasts_and_audiobooks_are_dropped_with_a_reason():
    podcast = export_record(spotify_track_uri=None, spotify_episode_uri="spotify:episode:x")
    book = export_record(spotify_track_uri=None, audiobook_uri="spotify:show:y")
    assert clean_record(podcast) == (None, "podcast episode")
    assert clean_record(book) == (None, "audiobook")


def test_records_with_bad_numbers_or_dates_are_dropped():
    assert clean_record(export_record(ms_played=-5))[1] == "invalid ms_played"
    assert clean_record(export_record(ts="not a date"))[1] == "invalid timestamp"
    assert clean_record(export_record(spotify_track_uri=None))[1] == "no track URI"


def test_platform_names_are_tidied():
    assert normalize_platform("ios 17.0 (iPhone14,5)") == "iOS"
    assert normalize_platform("iOS 16.1 (iPhone)") == "iOS"
    assert normalize_platform("Windows 10 (10.0.19044; x64)") == "Windows"
    assert normalize_platform("") == "Unknown"
    assert normalize_platform(None) == "Unknown"


# ---------- merging ----------

def staged_row(**overrides):
    row, _ = clean_record(export_record(**overrides))
    return row


def test_export_play_that_the_api_already_saved_is_enriched_not_duplicated():
    conn = get_connection(":memory:")
    # The API saw this play, but knows nothing about listening time or skips.
    save_plays(conn, [{"played_at": "2026-10-16T19:21:53.789Z", "track_uri": "spotify:track:aaa",
                       "track_name": "Song", "artist_name": "Artist", "duration_ms": 200000}], "api")

    result = merge_into_db(conn, [staged_row()])

    assert result == {"added": 0, "enriched": 1, "already present": 0}
    assert count_plays(conn) == 1
    saved = conn.execute("SELECT * FROM plays").fetchone()
    assert saved["source"] == "api"            # the original row is kept...
    assert saved["duration_ms"] == 200000      # ...with its API-only data intact...
    assert saved["ms_played"] == 187000        # ...plus the export's extra facts
    assert saved["skipped"] == 1


def test_export_play_the_api_never_saw_is_added():
    conn = get_connection(":memory:")
    result = merge_into_db(conn, [staged_row()])
    assert result == {"added": 1, "enriched": 0, "already present": 0}
    assert conn.execute("SELECT source FROM plays").fetchone()["source"] == "export"


def test_running_the_same_import_twice_changes_nothing_the_second_time():
    conn = get_connection(":memory:")
    save_plays(conn, [{"played_at": "2026-10-16T19:21:53.789Z", "track_uri": "spotify:track:aaa"}], "api")
    rows = [staged_row(), staged_row(ts="2020-01-01T10:00:00Z", spotify_track_uri="spotify:track:bbb")]

    first = merge_into_db(conn, [dict(r) for r in rows])
    second = merge_into_db(conn, [dict(r) for r in rows])

    assert first == {"added": 1, "enriched": 1, "already present": 0}
    assert second == {"added": 0, "enriched": 0, "already present": 2}
    assert count_plays(conn) == 2


def test_an_old_database_without_the_new_columns_is_upgraded(tmp_path):
    import sqlite3
    db_file = tmp_path / "old.db"
    old = sqlite3.connect(db_file)
    old.execute("CREATE TABLE plays (id INTEGER PRIMARY KEY, played_at TEXT NOT NULL, "
                "track_uri TEXT NOT NULL, artist_name TEXT, source TEXT NOT NULL, "
                "collected_at TEXT NOT NULL, "
                "UNIQUE (played_at, track_uri))")
    old.commit()
    old.close()

    conn = get_connection(db_file)  # opening it should add the missing columns
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(plays)")}
    assert {"reason_start", "reason_end", "shuffle", "platform"} <= columns
