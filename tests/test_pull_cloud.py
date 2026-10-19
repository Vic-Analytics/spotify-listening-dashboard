"""Tests for merging the cloud (GitHub Actions) database into the local one."""

import pytest

from database.db import count_plays, get_connection, save_plays
from database.pull_cloud import merge_from_file


def api_play(played_at, uri="spotify:track:aaa", artist="Artist"):
    return {"played_at": played_at, "track_uri": uri, "artist_name": artist,
            "track_name": "Song", "duration_ms": 200000}


def make_cloud_db(path, plays):
    """Create a small cloud-style database file containing API plays."""
    cloud = get_connection(path)
    save_plays(cloud, plays, "api")
    cloud.close()


def test_new_cloud_plays_are_added_and_known_ones_are_skipped(tmp_path):
    cloud_file = tmp_path / "cloud.db"
    make_cloud_db(cloud_file, [api_play("2026-10-20T10:00:00Z"),
                               api_play("2026-10-20T11:00:00Z", "spotify:track:bbb")])
    local = get_connection(":memory:")
    save_plays(local, [api_play("2026-10-20T10:00:00Z")], "api")   # already known

    result = merge_from_file(local, cloud_file)

    assert result == {"in cloud": 2, "added": 1, "already local": 1}
    assert count_plays(local) == 2


def test_pulling_twice_adds_nothing_the_second_time(tmp_path):
    cloud_file = tmp_path / "cloud.db"
    make_cloud_db(cloud_file, [api_play("2026-10-20T10:00:00Z")])
    local = get_connection(":memory:")

    assert merge_from_file(local, cloud_file)["added"] == 1
    assert merge_from_file(local, cloud_file)["added"] == 0
    assert count_plays(local) == 1


def test_a_local_export_row_is_never_overwritten_by_the_cloud_copy(tmp_path):
    cloud_file = tmp_path / "cloud.db"
    make_cloud_db(cloud_file, [api_play("2026-10-20T10:00:00Z")])

    local = get_connection(":memory:")
    save_plays(local, [{**api_play("2026-10-20T10:00:00Z"), "ms_played": 187000,
                        "skipped": 1, "reason_end": "fwdbtn"}], "export")

    merge_from_file(local, cloud_file)

    row = local.execute("SELECT source, ms_played, skipped, reason_end FROM plays").fetchone()
    assert tuple(row) == ("export", 187000, 1, "fwdbtn")
    assert count_plays(local) == 1


def test_a_cloud_database_from_an_older_schema_still_merges(tmp_path):
    """The cloud job may still be running old code that lacks the newer columns."""
    cloud_file = tmp_path / "cloud.db"
    make_cloud_db(cloud_file, [api_play("2026-10-20T10:00:00Z")])
    old = get_connection(cloud_file)
    for column in ("reason_start", "reason_end", "shuffle", "platform"):
        old.execute(f"ALTER TABLE plays DROP COLUMN {column}")
    old.commit()
    old.close()

    local = get_connection(":memory:")
    result = merge_from_file(local, cloud_file)

    assert result["added"] == 1
    row = local.execute("SELECT artist_name, source, platform FROM plays").fetchone()
    assert tuple(row) == ("Artist", "api", None)


def test_a_file_without_a_plays_table_gives_a_clear_error(tmp_path):
    import sqlite3
    bad_file = tmp_path / "bad.db"
    sqlite3.connect(bad_file).close()

    local = get_connection(":memory:")
    with pytest.raises(RuntimeError, match="no `plays` table"):
        merge_from_file(local, bad_file)
