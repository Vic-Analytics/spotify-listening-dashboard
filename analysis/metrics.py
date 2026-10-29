"""
metrics.py - pandas helpers that reshape query results for charts.

SQL is great at filtering, grouping and counting. pandas is better for
reshaping tables (pivots), filling gaps and running totals. So each tool does
the part it is best at.
"""

import numpy as np
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


# ---- sessions ---------------------------------------------------------------

# (label, lower bound in minutes). A session lands in the last bucket whose bound it reaches.
SESSION_LENGTHS = [("<10m", 0), ("10-30m", 10), ("30-60m", 30),
                   ("1-2h", 60), ("2-4h", 120), ("4h+", 240)]


def session_summary(sessions_df: pd.DataFrame) -> dict:
    """Headline numbers from sessions.sql rows. Medians, not averages: a few
    all-day sessions would drag an average far above a typical session."""
    if sessions_df.empty:
        return {"sessions": 0, "median_minutes": 0.0, "median_tracks": 0.0,
                "longest_minutes": 0.0, "longest_started": None}
    longest = sessions_df.loc[sessions_df["minutes"].idxmax()]
    return {
        "sessions": len(sessions_df),
        "median_minutes": float(sessions_df["minutes"].median()),
        "median_tracks": float(sessions_df["tracks"].median()),
        "longest_minutes": float(longest["minutes"]),
        "longest_started": longest["started_at"],
    }


def session_length_buckets(sessions_df: pd.DataFrame) -> pd.DataFrame:
    """Count sessions by length: one row per bucket, empty buckets included as 0."""
    bounds = [low for _, low in SESSION_LENGTHS] + [float("inf")]
    labels = [label for label, _ in SESSION_LENGTHS]
    bucket = pd.cut(sessions_df["minutes"], bins=bounds, labels=labels, right=False)
    counts = bucket.value_counts().reindex(labels).fillna(0).astype(int)
    total = counts.sum()
    return pd.DataFrame({
        "length": labels,
        "sessions": counts.to_numpy(),
        "pct_of_sessions": (100 * counts / total).round(1).to_numpy() if total else 0.0,
    })


# ---- calendar heatmap ---------------------------------------------------------

def calendar_grid(daily_df: pd.DataFrame, year: int, within: tuple | None = None) -> dict:
    """
    Lay one year out like a wall calendar: 7 rows (Mon..Sun) by one column per week.

    `within` = (first_day, last_day) of your data. Days outside it are left blank
    instead of being shown as "no listening", because before your history starts
    (or after your latest sync) you simply have no information.

    Returns numpy-style grids of the same shape:
      minutes  listening per day. 0 = no listening, NaN = a blank square (outside the
               year, or outside `within`)
      plays    same idea
      dates    'YYYY-MM-DD' text for the hover label ('' for blank squares)
    plus month_ticks: [(week column, 'Jan'), ...] for the axis labels.
    """
    first, last = pd.Timestamp(year, 1, 1), pd.Timestamp(year, 12, 31)
    grid_start = first - pd.Timedelta(days=first.weekday())     # the Monday on or before Jan 1
    days = pd.date_range(first, last)
    shape = (7, int(((last - grid_start).days // 7) + 1))
    if within is not None:
        days = days[(days >= pd.Timestamp(within[0])) & (days <= pd.Timestamp(within[1]))]
    weeks = (days - grid_start).days // 7                       # which column each day lands in
    rows = days.weekday                                         # 0 = Monday

    daily = daily_df.assign(local_date=pd.to_datetime(daily_df["local_date"])).set_index("local_date")
    minutes, plays = np.full(shape, np.nan), np.full(shape, np.nan)
    dates = np.full(shape, "", dtype=object)
    minutes[rows, weeks] = daily["minutes"].reindex(days).fillna(0).to_numpy()
    plays[rows, weeks] = daily["plays"].reindex(days).fillna(0).to_numpy()
    dates[rows, weeks] = days.strftime("%Y-%m-%d")

    month_starts = [pd.Timestamp(year, month, 1) for month in range(1, 13)]
    month_ticks = [(int((m - grid_start).days // 7), m.strftime("%b")) for m in month_starts]
    return {"minutes": minutes, "plays": plays, "dates": dates, "month_ticks": month_ticks,
            "active_days": int((np.nan_to_num(minutes) > 0).sum()), "days_covered": len(days)}
