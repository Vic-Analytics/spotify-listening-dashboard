"""
metrics.py - pandas helpers that reshape query results for charts.

SQL is great at filtering, grouping and counting. pandas is better for
reshaping tables (pivots), filling gaps and running totals. So each tool does
the part it is best at.
"""

import pandas as pd

# SQLite numbers weekdays 0 = Sunday. Charts read better starting on Monday.
WEEKDAY_ORDER = [1, 2, 3, 4, 5, 6, 0]
WEEKDAY_NAMES = {0: "Sun", 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat"}


def heatmap_matrix(heatmap_df: pd.DataFrame, value: str = "minutes") -> pd.DataFrame:
    """
    Turn heatmap.sql rows into a 7 x 24 grid: rows = weekdays (Mon..Sun),
    columns = hours 0..23, cells = minutes (or plays). Missing cells become 0.
    """
    grid = heatmap_df.pivot_table(index="dow", columns="hour", values=value, aggfunc="sum")
    grid = grid.reindex(index=WEEKDAY_ORDER, columns=range(24)).fillna(0)
    grid.index = [WEEKDAY_NAMES[d] for d in grid.index]
    return grid


def fill_missing_periods(df: pd.DataFrame, column: str, freq: str) -> pd.DataFrame:
    """
    Add rows of zeros for weeks/months with no listening, so line charts show a
    drop to zero instead of drawing a straight line across the gap.
    freq: "W-MON" for weekly (Monday starts) or "MS" for months.
    """
    if df.empty:
        return df
    dated = df.assign(**{column: pd.to_datetime(df[column])}).set_index(column)
    full_range = pd.date_range(dated.index.min(), dated.index.max(), freq=freq)
    return dated.reindex(full_range, fill_value=0).rename_axis(column).reset_index()


def streak_summary(streaks_df: pd.DataFrame) -> dict:
    """
    From streaks.sql rows (longest first), report the longest streak and the
    "current" streak = the one that ends on your most recent listening day.
    """
    if streaks_df.empty:
        return {"longest_days": 0, "longest_start": None, "longest_end": None, "current_days": 0}

    longest = streaks_df.iloc[0]
    latest_day = streaks_df["streak_end"].max()
    current = streaks_df[streaks_df["streak_end"] == latest_day].iloc[0]
    return {
        "longest_days": int(longest["days"]),
        "longest_start": longest["streak_start"],
        "longest_end": longest["streak_end"],
        "current_days": int(current["days"]),
    }


def add_cumulative_artists(discovery_df: pd.DataFrame) -> pd.DataFrame:
    """Add a running total of artists discovered, for a 'growing library' chart."""
    return discovery_df.assign(total_artists_discovered=discovery_df["new_artists"].cumsum())
