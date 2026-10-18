"""
Tests for the database layer. Run them with:   python -m pytest

A test is a tiny program that checks the code does what we claim. These use an
in-memory database (":memory:") so they never touch your real data.
"""

from database.db import count_plays, get_connection, normalize_timestamp, save_plays


def make_play(played_at="2026-10-16T19:21:53.789Z", uri="spotify:track:aaa"):
    return {
        "played_at": played_at,
        "track_uri": uri,
        "track_name": "Song",
        "artist_name": "Artist",
    }


def test_timestamp_is_cut_to_whole_seconds_in_utc():
    assert normalize_timestamp("2026-10-16T19:21:53.789Z") == "2026-10-16T19:21:53Z"
    assert normalize_timestamp("2026-10-16T21:21:53+02:00") == "2026-10-16T19:21:53Z"


def test_saving_the_same_plays_twice_adds_nothing_the_second_time():
    conn = get_connection(":memory:")
    plays = [make_play(), make_play("2026-10-16T19:30:00.000Z", "spotify:track:bbb")]

    assert save_plays(conn, plays, "api") == (2, 0)
    assert save_plays(conn, plays, "api") == (0, 2)
    assert count_plays(conn) == 2


def test_api_and_export_versions_of_one_play_count_once():
    """The API reports milliseconds, the export doesn't, but it's the same play."""
    conn = get_connection(":memory:")
    save_plays(conn, [make_play("2026-10-16T19:21:53.789Z")], "api")
    added, skipped = save_plays(conn, [make_play("2026-10-16T19:21:53Z")], "export")

    assert (added, skipped) == (0, 1)
    assert count_plays(conn) == 1


def test_same_track_at_different_times_is_two_plays():
    conn = get_connection(":memory:")
    plays = [make_play("2026-10-16T19:00:00Z"), make_play("2026-10-16T19:05:00Z")]
    assert save_plays(conn, plays, "api") == (2, 0)
