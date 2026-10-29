"""
Tests for the analysis queries, using a tiny hand-made database where we know
the right answers in advance. Run all tests with:   python -m pytest
"""

import numpy as np
import pandas as pd
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


# ---------- sessions ----------
# `play()` makes 4-minute listens stamped with when they END, so plays ending
# 4 minutes apart follow each other with no gap at all.

def test_sessions_split_on_gaps_longer_than_30_minutes():
    conn = analysed([
        play("2026-01-05T18:00:00Z", "A"), play("2026-01-05T18:04:00Z", "B"), play("2026-01-05T18:08:00Z", "C"),
        play("2026-01-05T19:00:00Z", "D"),                      # starts 48 min after C ended -> new session
    ])
    sessions = run_query(conn, "sessions")
    assert list(sessions["tracks"]) == [3, 1]
    assert sessions.iloc[0]["minutes"] == 12.0                   # 17:56 start to 18:08 end


def test_a_gap_of_exactly_30_minutes_does_not_split_a_session():
    conn = analysed([play("2026-01-05T18:00:00Z", "A"), play("2026-01-05T18:34:00Z", "B")])   # B starts 18:30
    assert list(run_query(conn, "sessions")["tracks"]) == [2]


def test_session_date_range_uses_the_start_date_and_never_cuts_a_session():
    # Chicago is UTC-6 in January: this session starts Jan 5 23:50 local and ends after midnight.
    conn = analysed([play("2026-01-06T05:54:00Z", "A"), play("2026-01-06T05:58:00Z", "B"),
                     play("2026-01-06T06:02:00Z", "C"),
                     play("2026-01-10T18:00:00Z", "D")])
    jan5 = run_query(conn, "sessions", start="2026-01-05", end="2026-01-05")
    assert list(jan5["tracks"]) == [3]
    assert run_query(conn, "sessions", start="2026-01-06", end="2026-01-06").empty


def test_sessions_count_skipped_previews_but_report_real_plays_separately():
    conn = analysed([play("2026-01-05T18:00:00Z", "A", ms=240000),
                     play("2026-01-05T18:00:04Z", "B", ms=4000, reason_end="fwdbtn")])
    session = run_query(conn, "sessions").iloc[0]
    assert (session["tracks"], session["plays"], session["skips"]) == (2, 1, 1)


def test_session_summary_and_length_buckets():
    from analysis.metrics import session_length_buckets, session_summary
    conn = analysed([play("2026-01-05T18:00:00Z", "A"), play("2026-01-05T18:04:00Z", "B"),   # 8 min
                     play("2026-01-06T18:00:00Z", "C"), play("2026-01-06T18:04:00Z", "D"),
                     play("2026-01-06T18:08:00Z", "E"), play("2026-01-06T18:12:00Z", "F"),   # 16 min
                     play("2026-01-07T18:00:00Z", "G")])                                      # 4 min
    sessions = run_query(conn, "sessions")
    summary = session_summary(sessions)
    assert summary["sessions"] == 3
    assert summary["median_minutes"] == 8.0
    assert summary["longest_minutes"] == 16.0
    buckets = session_length_buckets(sessions).set_index("length")
    assert list(buckets["sessions"]) == [2, 1, 0, 0, 0, 0]
    assert buckets.loc["10-30m", "pct_of_sessions"] == 33.3
    assert session_summary(sessions.iloc[0:0])["sessions"] == 0


def test_skip_fatigue_groups_skip_rate_by_position_in_session():
    reasons = ["trackdone", "trackdone", "fwdbtn", "fwdbtn", "fwdbtn"]
    conn = analysed([play(f"2026-01-05T18:{4 * i:02d}:00Z", f"T{i}", reason_end=r) for i, r in enumerate(reasons)])
    fatigue = run_query(conn, "skip_fatigue")
    assert set(fatigue["scope"]) == {"All sessions"}              # nobody reached 20 tracks
    rates = dict(zip(fatigue["position_bucket"], fatigue["skip_rate_pct"]))
    assert rates == {"1. 1": 0.0, "2. 2-3": 50.0, "3. 4-6": 100.0}


def test_skip_fatigue_has_a_same_sessions_comparison_for_long_sessions():
    # One session of 22 tracks (all skipped) and one of 2 (none skipped).
    long_session = [play(f"2026-01-05T{18 + i * 4 // 60:02d}:{i * 4 % 60:02d}:00Z", f"L{i}", reason_end="fwdbtn")
                    for i in range(22)]
    short_session = [play("2026-01-06T18:00:00Z", "S1"), play("2026-01-06T18:04:00Z", "S2")]
    fatigue = run_query(analysed(long_session + short_session), "skip_fatigue")
    long_only = fatigue[fatigue["scope"] == "Sessions of 20+ tracks"]
    assert long_only["plays"].sum() == 22
    assert set(long_only["skip_rate_pct"]) == {100.0}
    first_slot = fatigue[(fatigue["scope"] == "All sessions") & (fatigue["position_bucket"] == "1. 1")]
    assert first_slot.iloc[0]["plays"] == 2                      # both sessions have a first track


# ---------- artist deep-dive ----------

def artist_db():
    return analysed([
        play("2026-01-05T18:00:00Z", "Fav", uri="spotify:track:f1"),
        play("2026-01-05T19:00:00Z", "Fav", uri="spotify:track:f1"),
        play("2026-02-05T18:00:00Z", "Fav", uri="spotify:track:f2", ms=120000),
        play("2026-02-05T19:00:00Z", "Fav", uri="spotify:track:f2", ms=3000, reason_end="fwdbtn"),
        play("2026-02-05T20:00:00Z", "Fav", uri="spotify:track:f3", ms=3000, reason_end="fwdbtn"),   # never reached 30 s
        play("2026-02-06T18:00:00Z", "Other", ms=240000),
    ])


def test_artist_list_ranks_artists_by_minutes():
    artists = run_query(artist_db(), "artist_list")
    assert list(artists["artist_name"]) == ["Fav", "Other"]
    assert list(artists["minutes"]) == [10.0, 4.0]


def test_artist_profile_reports_the_facts_for_one_artist():
    row = run_query(artist_db(), "artist_profile", artist="Fav").iloc[0]
    assert (row["first_heard"], row["last_heard"]) == ("2026-01-05", "2026-02-05")
    assert (row["plays"], row["starts"], row["tracks"], row["active_days"]) == (3, 5, 2, 2)
    assert row["minutes"] == 10.0                                # 4 + 4 + 2
    assert row["minutes_rank"] == 1
    assert row["share_pct"] == round(100 * 10 / 14, 2)
    assert row["skip_rate_pct"] == 40.0                          # 2 of 5 starts ended with Next
    assert row["period_skip_pct"] == 40.0                        # all 5 of Fav's plays + nothing else in that span


def test_artist_profile_for_an_unknown_artist_has_zero_plays():
    row = run_query(artist_db(), "artist_profile", artist="Nobody").iloc[0]
    assert row["plays"] == 0 and row["starts"] == 0


def test_artist_tracks_rank_by_plays_and_leave_out_never_played_tracks():
    tracks = run_query(artist_db(), "artist_tracks", artist="Fav")
    assert list(tracks["plays"]) == [2, 1]                       # f1 then f2; f3 never reached 30 s
    assert tracks.iloc[1]["starts"] == 2
    assert tracks.iloc[1]["skip_rate_pct"] == 50.0
    assert len(run_query(artist_db(), "artist_tracks", artist="Fav", limit=1)) == 1


def test_artist_monthly_has_one_row_per_active_month():
    monthly = run_query(artist_db(), "artist_monthly", artist="Fav")
    assert list(monthly["month_start"]) == ["2026-01-01", "2026-02-01"]
    assert list(monthly["minutes"]) == [8.0, 2.0]


# ---------- calendar heatmap ----------

def test_daily_query_and_calendar_grid_lay_a_year_out_by_week():
    from analysis.metrics import calendar_grid
    # 2026-01-01 is a Thursday, so the first column starts on Monday Dec 29 (outside the year).
    conn = analysed([play("2026-01-01T18:00:00Z"), play("2026-01-01T19:00:00Z", "B"), play("2026-01-12T18:00:00Z")])
    daily = run_query(conn, "daily", start="2026-01-01", end="2026-12-31")
    assert list(daily["local_date"]) == ["2026-01-01", "2026-01-12"]
    assert list(daily["minutes"]) == [8.0, 4.0]

    grid = calendar_grid(daily, 2026)
    assert grid["minutes"].shape == (7, 53)
    assert grid["dates"][3, 0] == "2026-01-01"                   # Thursday, first column
    assert grid["minutes"][3, 0] == 8.0
    assert np.isnan(grid["minutes"][0, 0])                       # Mon Dec 29 belongs to last year
    assert grid["dates"][0, 2] == "2026-01-12" and grid["minutes"][0, 2] == 4.0
    assert grid["minutes"][1, 1] == 0.0                          # a quiet day inside the year is 0, not blank
    assert grid["active_days"] == 2 and grid["days_covered"] == 365
    assert grid["month_ticks"][0] == (0, "Jan") and len(grid["month_ticks"]) == 12


def test_calendar_grid_leaves_days_outside_your_data_blank():
    from analysis.metrics import calendar_grid
    conn = analysed([play("2026-03-10T18:00:00Z")])
    daily = run_query(conn, "daily", start="2026-01-01", end="2026-12-31")
    grid = calendar_grid(daily, 2026, within=(pd.Timestamp("2026-03-01"), pd.Timestamp("2026-03-31")))
    assert grid["days_covered"] == 31
    assert np.isnan(grid["minutes"]).sum() == grid["minutes"].size - 31       # everything but March is blank
    assert grid["dates"][0, 0] == ""                                           # the very first square: not in range
    # Without `within`, a quiet day is a real 0.
    assert calendar_grid(daily, 2026)["minutes"][3, 0] == 0.0


def test_calendar_grid_handles_an_empty_year():
    from analysis.metrics import calendar_grid
    grid = calendar_grid(run_query(analysed([play("2026-01-05T18:00:00Z")]), "daily", start="2030-01-01", end="2030-12-31"), 2030)
    assert grid["active_days"] == 0


def test_unknown_query_name_fails_loudly():
    conn = analysed([play("2026-01-05T18:00:00Z")])
    with pytest.raises(FileNotFoundError):
        run_query(conn, "does_not_exist")
