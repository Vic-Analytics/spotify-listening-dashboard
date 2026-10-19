"""
report.py - run every analysis query and print the results.

    python -m analysis.report                 # your whole history
    python -m analysis.report 2025-01-01 2025-12-31   # a date range

This is how we sanity-check the numbers before building the dashboard.
"""

import sys

import pandas as pd

from analysis.metrics import heatmap_matrix, streak_summary
from analysis.queries import connect, get_timezone_name, run_query


def section(title: str) -> None:
    print(f"\n{'=' * 8} {title} {'=' * 8}")


def main() -> None:
    args = {}
    if len(sys.argv) >= 3:
        args = {"start": sys.argv[1], "end": sys.argv[2]}

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.max_colwidth", 40)

    conn = connect()
    print(f"Time zone: {get_timezone_name()}   Range: {args or 'all time'}")

    section("SUMMARY")
    print(run_query(conn, "summary", **args).T.to_string(header=False))

    section("TOP 10 ARTISTS (by minutes)")
    print(run_query(conn, "top_artists", limit=10, **args).to_string(index=False))

    section("TOP 10 TRACKS (by plays)")
    print(run_query(conn, "top_tracks", limit=10, **args).to_string(index=False))

    section("HEATMAP (minutes, weekday x hour)")
    print(heatmap_matrix(run_query(conn, "heatmap", **args)).round(0).astype(int).to_string())

    section("MONTHLY TREND (last 12 months)")
    print(run_query(conn, "trend_monthly", **args).tail(12).to_string(index=False))

    section("STREAKS")
    streaks = run_query(conn, "streaks", **args)
    print(streak_summary(streaks))
    print(streaks.head(5).to_string(index=False))

    section("ARTIST DISCOVERY (last 12 months)")
    print(run_query(conn, "discovery", **args).tail(12).to_string(index=False))

    section("SKIP RATE BY YEAR")
    skips = run_query(conn, "skips_trend", **args)
    skips["year"] = skips["month_start"].str[:4]
    yearly = skips.groupby("year")[["plays", "skips"]].sum()
    yearly["skip_rate_pct"] = (100 * yearly["skips"] / yearly["plays"]).round(1)
    print(yearly.to_string())

    section("HOW QUICKLY DO I SKIP?")
    print(run_query(conn, "skip_timing", **args).to_string(index=False))

    section("SKIPS BY DEVICE & SHUFFLE")
    print(run_query(conn, "skips_by_context", **args).to_string(index=False))

    section("MOST-SKIPPED ARTISTS (100+ plays)")
    print(run_query(conn, "skips_by_artist", **args).head(8).to_string(index=False))

    conn.close()


if __name__ == "__main__":
    main()
