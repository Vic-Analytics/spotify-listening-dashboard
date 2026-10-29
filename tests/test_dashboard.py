"""
Tests for the dashboard. They run the real app against the FAKE sample database
using Streamlit's headless test runner, so no browser is needed.

They are skipped automatically if Streamlit/Plotly aren't installed (for example
in the lightweight GitHub Actions job that only runs the collector).
"""

import pytest

pytest.importorskip("streamlit")
pytest.importorskip("plotly")

from streamlit.testing.v1 import AppTest  # noqa: E402

from analysis.metrics import (add_cumulative_artists, calendar_grid, heatmap_matrix,  # noqa: E402
                              session_length_buckets)
from analysis.queries import connect, run_query  # noqa: E402
from dashboard import charts  # noqa: E402
from database.db import PROJECT_ROOT  # noqa: E402

SAMPLE_DB = PROJECT_ROOT / "data" / "sample" / "sample.db"
APP = str(PROJECT_ROOT / "dashboard" / "app.py")

pytestmark = pytest.mark.skipif(not SAMPLE_DB.exists(), reason="sample database not generated")


@pytest.fixture(scope="module")
def sample_conn():
    return connect(SAMPLE_DB, "UTC")


def run_app(monkeypatch, **widget_changes):
    """Start the app in demo mode (sample data only) and return the finished AppTest."""
    monkeypatch.setenv("DASHBOARD_DEMO", "1")
    at = AppTest.from_file(APP, default_timeout=60).run()
    return at


def test_app_starts_without_errors_and_shows_the_headline_numbers(monkeypatch):
    at = run_app(monkeypatch)
    assert not at.exception, [e.value for e in at.exception]
    labels = [m.label for m in at.metric]
    assert {"Time listened", "Plays", "Unique artists", "Unique tracks", "Top artist"} <= set(labels)
    assert at.title[0].value == "My Spotify Listening Stats"


def test_demo_mode_offers_only_the_fake_data(monkeypatch):
    at = run_app(monkeypatch)
    # With a single source there is no radio button, and no GitHub sync button.
    assert len(at.sidebar.radio) == 0
    assert not any("Sync" in b.label for b in at.sidebar.button)
    assert any("synthetic" in c.value for c in at.sidebar.caption)


def test_changing_the_date_range_filters_the_numbers(monkeypatch):
    at = run_app(monkeypatch)
    all_time_plays = next(m for m in at.metric if m.label == "Plays").value

    at.sidebar.selectbox[0].select("Last 30 days").run()
    assert not at.exception, [e.value for e in at.exception]
    recent_plays = next(m for m in at.metric if m.label == "Plays").value

    to_int = lambda text: int(text.replace(",", ""))  # noqa: E731
    assert to_int(recent_plays) < to_int(all_time_plays)


def test_every_tab_renders_with_each_toggle(monkeypatch):
    at = run_app(monkeypatch)
    for radio in at.radio:
        # Flip every radio to its last option and make sure nothing crashes.
        radio.set_value(radio.options[-1])
    at.run()
    assert not at.exception, [e.value for e in at.exception]


def test_the_new_tabs_exist_and_the_artist_and_year_pickers_work(monkeypatch):
    at = run_app(monkeypatch)
    assert [t.label for t in at.tabs] == ["Top lists", "Artist deep dive", "Trends", "Habits & streaks",
                                         "Sessions", "Discovery", "Skips"]
    artist_picker = next(s for s in at.selectbox if s.label == "Artist")
    year_picker = next(s for s in at.selectbox if s.label == "Year")
    assert year_picker.options == ["2026", "2025"]               # newest first, from the sample's date range

    # Pick the least-listened artist and the oldest year; the page must still render.
    artist_picker.select(artist_picker.options[-1])
    year_picker.select("2025")
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert any(m.label == "Longest session" for m in at.metric)
    assert any(m.label == "Skip rate" for m in at.metric)


def test_sessions_tab_responds_to_the_date_range(monkeypatch):
    at = run_app(monkeypatch)
    all_time = int(next(m for m in at.metric if m.label == "Sessions").value.replace(",", ""))
    at.sidebar.selectbox[0].select("Last 30 days").run()
    assert not at.exception, [e.value for e in at.exception]
    recent = int(next(m for m in at.metric if m.label == "Sessions").value.replace(",", ""))
    assert 0 < recent < all_time


def test_all_charts_build_from_real_query_results(sample_conn):
    figures = [
        charts.top_artists_chart(run_query(sample_conn, "top_artists", limit=10)),
        charts.top_tracks_chart(run_query(sample_conn, "top_tracks", limit=10)),
        charts.heatmap_chart(heatmap_matrix(run_query(sample_conn, "heatmap"))),
        charts.streaks_chart(run_query(sample_conn, "streaks")),
        charts.skip_rate_chart(run_query(sample_conn, "skips_trend")),
        charts.skip_timing_chart(run_query(sample_conn, "skip_timing")),
        charts.skips_by_context_chart(run_query(sample_conn, "skips_by_context")),
    ]
    discovery = add_cumulative_artists(run_query(sample_conn, "discovery"))
    figures += [charts.new_artists_chart(discovery), charts.discovery_rate_chart(discovery),
                charts.cumulative_artists_chart(discovery)]

    sessions = run_query(sample_conn, "sessions")
    top_artist = run_query(sample_conn, "artist_list").iloc[0]["artist_name"]
    daily = run_query(sample_conn, "daily", start="2025-01-01", end="2025-12-31")
    figures += [
        charts.session_length_chart(session_length_buckets(sessions)),
        charts.skip_fatigue_chart(run_query(sample_conn, "skip_fatigue")),
        charts.artist_tracks_chart(run_query(sample_conn, "artist_tracks", artist=top_artist, limit=10)),
        charts.calendar_chart(calendar_grid(daily, 2025)),
    ]
    assert all(len(fig.data) >= 1 for fig in figures)


def test_calendar_and_session_charts_show_a_message_on_empty_data(sample_conn):
    empty_year = calendar_grid(run_query(sample_conn, "daily", start="1900-01-01", end="1900-12-31"), 1900)
    assert charts.calendar_chart(empty_year).layout.annotations[0].text == "No data for this selection"
    no_sessions = run_query(sample_conn, "sessions", start="1900-01-01", end="1900-12-31")
    assert charts.session_length_chart(session_length_buckets(no_sessions)).layout.annotations


def test_the_fake_data_shows_skip_fatigue_but_not_on_the_first_track(sample_conn):
    fatigue = run_query(sample_conn, "skip_fatigue")
    all_sessions = fatigue[fatigue["scope"] == "All sessions"].set_index("position_bucket")["skip_rate_pct"]
    assert all_sessions["1. 1"] < all_sessions["3. 4-6"] < all_sessions["6. 21-40"]


def test_charts_show_a_friendly_message_instead_of_crashing_on_empty_data(sample_conn):
    empty = run_query(sample_conn, "top_artists", start="1900-01-01", end="1900-01-02")
    fig = charts.top_artists_chart(empty)
    assert fig.layout.annotations[0].text == "No data for this selection"


def test_ranked_bars_keep_one_row_per_item_even_when_two_names_match():
    # Two different tracks that share a title, and two long titles that look the same once shortened.
    names = ["Intro", "Intro", "A" * 40 + " one", "A" * 40 + " two"]
    fig = charts.ranked_bars(names, [90, 50, 30, 10], names, "plays")
    bar = fig.data[0]
    assert len(set(bar.y)) == 4                                   # four separate rows, none merged
    assert list(bar.x) == [90, 50, 30, 10]                        # lengths follow the values, in order
    assert list(fig.layout.yaxis.ticktext)[:2] == ["Intro", "Intro"]


def test_no_chart_uses_a_second_y_axis(sample_conn):
    fig = charts.skips_by_context_chart(run_query(sample_conn, "skips_by_context"))
    assert not any(getattr(trace, "yaxis", "y") not in (None, "y") for trace in fig.data)
