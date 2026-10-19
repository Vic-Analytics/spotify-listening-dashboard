"""
Tests for the analysis queries, using a tiny hand-made database where we know
the right answers in advance. Run all tests with:   python -m pytest
"""

import pytest

from analysis.metrics import fill_missing_periods, heatmap_matrix, streak_summary
from analysis.queries import prepare, run_query
from database.db import get_connection, save_plays

CHICAGO = "America/Chicago"


def play(played_at, artist="A", uri=None, ms=240000, reason_end="trackdone", **extra):
    """One export-style play. Defaults to a full 4-minute listen."""
    return {
        "played_at": played_at,
        "track_uri": uri or f"spotify:track:{artist}",
        "track_name": f"{artist} song",
        "artist_name": artist,
        "ms_played": ms,
        "reason_end": reason_end,
        "shuffle": 0,
        "platform": "iOS",
        **extra,
    }


def analysed(plays, source="export", tz=CHICAGO):
    """Build an in-memory database from `plays` and prepare it for queries."""
    conn = get_connection(":memory:")
    save_plays(conn, plays, source)
    return prepare(conn, tz)


# ---------- the 30-second rule ----------

def test_plays_under_30_seconds_are_not_counted_as_listens():
    conn = analysed([
        play("2026-01-05T18:00:00Z", "A", ms=240000),
        play("2026-01-05T18:05:00Z", "B", ms=4000, reason_end="fwdbtn"),   # skipped fast
        play("2026-01-05T18:10:00Z", "C", ms=30000),                       # exactly 30s counts
    ])
    summary = run_query(conn, "summary").iloc[0]
    assert summary["plays"] == 2
    assert summary["unique_artists"] == 2


def test_api_only_rows_count_and_use_track_length_as_listening_time():
    conn = analysed([{"played_at": "2026-01-05T18:00:00Z", "track_uri": "spotify:track:x",
                      "artist_name": "A", "duration_ms": 180000}], source="api")
    summary = run_query(conn, "summary").iloc[0]
    assert summary["plays"] == 1
    assert summary["minutes_listened"] == 3


# ---------- time zones ----------

def test_utc_times_are_converted_to_the_local_day_and_hour():
    # 03:30 UTC on Oct 17 is 22:30 on Oct 16 in Chicago (daylight time, UTC-5).
    conn = analysed([play("2026-10-17T03:30:00Z")])
    row = conn.execute("SELECT local_date, hour, dow FROM play_facts").fetchone()
    assert row == ("2026-10-16", 22, 5)   # 5 = Friday


def test_daylight_saving_changes_the_offset():
    # Same UTC clock time, but winter (UTC-6) vs summer (UTC-5).
    conn = analysed([play("2026-01-15T03:30:00Z"), play("2026-07-15T03:30:00Z", "B")])
    hours = [r[0] for r in conn.execute("SELECT hour FROM play_facts ORDER BY local_at")]
    assert hours == [21, 22]   # January (UTC-6) then July (UTC-5)


# ---------- rankings and filters ----------

def test_top_artists_are_ranked_by_minutes_and_respect_the_date_range():
    conn = analysed([
        play("2026-01-05T18:00:00Z", "Old", ms=600000),       # 10 minutes in one play
        play("2026-03-05T18:00:00Z", "Recent", ms=240000),    # 4 + 4 = 8 minutes in two plays
        play("2026-03-06T18:00:00Z", "Recent", ms=240000),
    ])
    everything = run_query(conn, "top_artists")
    assert list(everything["artist_name"]) == ["Old", "Recent"]   # ranked by minutes, not plays

    march_only = run_query(conn, "top_artists", start="2026-03-01", end="2026-03-31")
    assert list(march_only["artist_name"]) == ["Recent"]


def test_top_tracks_group_by_track_not_by_artist():
    conn = analysed([
        play("2026-01-05T18:00:00Z", "A", uri="spotify:track:1"),
        play("2026-01-05T19:00:00Z", "A", uri="spotify:track:1"),
        play("2026-01-05T20:00:00Z", "A", uri="spotify:track:2"),
    ])
    top = run_query(conn, "top_tracks")
    assert list(top["plays"]) == [2, 1]


# ---------- trends ----------

def test_weekly_buckets_start_on_monday():
    # Sunday 2026-10-18 belongs to the week that began Monday 2026-10-12.
    conn = analysed([play("2026-10-18T18:00:00Z"), play("2026-10-12T18:00:00Z", "B")])
    weekly = run_query(conn, "trend_weekly")
    assert list(weekly["week_start"]) == ["2026-10-12"]
    assert weekly.iloc[0]["plays"] == 2


def test_empty_weeks_are_filled_with_zero_for_charts():
    conn = analysed([play("2026-10-05T18:00:00Z"), play("2026-10-19T18:00:00Z", "B")])
    filled = fill_missing_periods(run_query(conn, "trend_weekly"), "week_start", "W-MON")
    assert list(filled["minutes"]) == [4.0, 0.0, 4.0]


# ---------- heatmap ----------

def test_heatmap_grid_is_7_by_24_starting_on_monday():
    conn = analysed([play("2026-10-19T23:00:00Z")])     # Monday 18:00 Chicago
    grid = heatmap_matrix(run_query(conn, "heatmap"))
    assert grid.shape == (7, 24)
    assert list(grid.index)[0] == "Mon"
    assert grid.loc["Mon", 18] == 4.0
    assert grid.to_numpy().sum() == 4.0


# ---------- streaks ----------

def test_streaks_find_runs_of_consecutive_days_and_ignore_repeat_plays():
    days = ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-05"]
    plays = [play(f"{d}T18:00:00Z", f"A{i}") for i, d in enumerate(days)]
    plays.append(play("2026-10-02T19:00:00Z", "extra"))   # second play, same day
    conn = analysed(plays)

    streaks = run_query(conn, "streaks")
    assert list(streaks["days"]) == [3, 1]
    summary = streak_summary(streaks)
    assert summary["longest_days"] == 3
    assert summary["longest_start"] == "2026-10-01"
    assert summary["current_days"] == 1      # the streak ending on the latest day, Oct 5


# ---------- discovery ----------

def test_discovery_counts_an_artist_as_new_only_in_their_first_month():
    conn = analysed([
        play("2026-01-10T18:00:00Z", "A"),
        play("2026-02-10T18:00:00Z", "A"),
        play("2026-02-11T18:00:00Z", "B"),
    ])
    d = run_query(conn, "discovery").set_index("month_start")
    assert d.loc["2026-01-01", "new_artists"] == 1
    assert d.loc["2026-02-01", "new_artists"] == 1          # only B
    assert d.loc["2026-02-01", "active_artists"] == 2
    assert d.loc["2026-02-01", "discovery_rate_pct"] == 50.0


def test_filtering_to_a_later_range_does_not_make_old_artists_look_new():
    conn = analysed([
        play("2026-01-10T18:00:00Z", "A"),
        play("2026-02-10T18:00:00Z", "A"),
    ])
    feb = run_query(conn, "discovery", start="2026-02-01", end="2026-02-28")
    assert feb.iloc[0]["new_artists"] == 0


# ---------- skips ----------

def test_skip_rate_counts_next_button_presses_and_ignores_api_only_rows():
    conn = get_connection(":memory:")
    save_plays(conn, [
        play("2026-01-05T18:00:00Z", "A", ms=3000, reason_end="fwdbtn"),
        play("2026-01-05T18:01:00Z", "B", ms=240000, reason_end="trackdone"),
    ], "export")
    save_plays(conn, [{"played_at": "2026-01-05T19:00:00Z", "track_uri": "spotify:track:z",
                       "artist_name": "C", "duration_ms": 200000}], "api")
    prepare(conn, CHICAGO)

    trend = run_query(conn, "skips_trend").iloc[0]
    assert (trend["plays"], trend["skips"], trend["skip_rate_pct"]) == (2, 1, 50.0)

    timing = run_query(conn, "skip_timing")
    assert list(timing["skipped_after"]) == ["1. under 5 sec"]


def test_most_skipped_artists_hides_artists_below_the_minimum():
    conn = analysed([play("2026-01-05T18:00:00Z", "Rare", ms=2000, reason_end="fwdbtn")])
    assert run_query(conn, "skips_by_artist", min_plays=5).empty
    assert len(run_query(conn, "skips_by_artist", min_plays=1)) == 1


def test_unknown_query_name_fails_loudly():
    conn = analysed([play("2026-01-05T18:00:00Z")])
    with pytest.raises(FileNotFoundError):
        run_query(conn, "does_not_exist")
