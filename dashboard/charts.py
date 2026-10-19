"""
charts.py - turns query results (pandas DataFrames) into Plotly figures.

Design rules used throughout (so the charts read as one system):
  * One colour per METRIC, the same everywhere:
        blue   = listening time / plays       orange = skipping
        aqua   = artist discovery
    (These are the first three slots of a palette validated for colour-blind
    viewers. Colour follows the metric, never the rank of a bar.)
  * Single-series bar charts use ONE colour, not a rainbow or a ramp.
  * Only the heatmap uses a ramp (light -> dark blue = more listening).
  * Never two y-axes on one chart: different measures get separate charts.
  * Thin marks, hairline solid gridlines, quiet text, values in the hover tooltip.
"""

import pandas as pd
import plotly.graph_objects as go

# ---- colours -----------------------------------------------------------
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
GRAY = "#b5b3ab"           # "everything else" in emphasis charts

INK = "#0b0b0b"            # primary text
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"      # axis labels
GRID = "#e1e0d9"           # hairline gridlines
BASELINE = "#c3c2b7"

# One-hue light -> dark blue ramp for the heatmap (more listening = darker).
BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#1c5cab", "#184f95", "#0d366b"]
HEATMAP_SCALE = [[i / (len(BLUE_RAMP) - 1), c] for i, c in enumerate(BLUE_RAMP)]

FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"

# Hide Plotly's toolbar; the hover tooltips are what readers use.
PLOT_CONFIG = {"displayModeBar": False}


def _style(fig: go.Figure, height: int = 340, legend: bool = False) -> go.Figure:
    """Apply the shared look to any figure."""
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=16, t=16, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=13, color=INK_SECONDARY),
        showlegend=legend,
        hoverlabel=dict(bgcolor="#fcfcfb", bordercolor=GRID, font=dict(family=FONT, color=INK)),
        bargap=0.4,
    )
    fig.update_xaxes(showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False,
                     linecolor=BASELINE, tickfont=dict(color=INK_MUTED), automargin=True)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, gridwidth=1, zeroline=False,
                     linecolor=BASELINE, tickfont=dict(color=INK_MUTED), automargin=True)
    if hasattr(fig.layout, "barcornerradius"):
        fig.update_layout(barcornerradius=4)   # softly rounded bar ends
    return fig


def _shorten(text: str, limit: int = 30) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _empty(message: str = "No data for this selection") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(color=INK_MUTED, size=14))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _style(fig, height=200)


# ---- ranked bars ---------------------------------------------------------

def ranked_bars(labels, values, hover_names, value_label, color=BLUE, height=None) -> go.Figure:
    """Horizontal bars, biggest at the top, value printed at the bar end."""
    if len(values) == 0:
        return _empty()
    labels = [_shorten(str(label)) for label in labels]
    fig = go.Figure(go.Bar(
        x=list(values), y=labels, orientation="h", marker_color=color,
        customdata=list(hover_names),
        text=[f"{v:,.0f}" for v in values], textposition="outside", cliponaxis=False,
        textfont=dict(color=INK_SECONDARY),
        hovertemplate="<b>%{customdata}</b><br>%{x:,.0f} " + value_label + "<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    # Headroom past the longest bar so its printed value is never clipped.
    fig.update_xaxes(title=value_label.capitalize(), title_font=dict(color=INK_MUTED, size=12),
                     range=[0, max(values) * 1.2])
    return _style(fig, height=height or max(240, 34 * len(values) + 60))


def top_artists_chart(df: pd.DataFrame) -> go.Figure:
    return ranked_bars(df["artist_name"], df["minutes"], df["artist_name"], "minutes listened")


def top_tracks_chart(df: pd.DataFrame) -> go.Figure:
    hover = [f"{t} — {a}" for t, a in zip(df["track_name"], df["artist_name"])]
    return ranked_bars(df["track_name"], df["plays"], hover, "plays")


# ---- trends -----------------------------------------------------------------

def line_chart(df: pd.DataFrame, x: str, y: str, color: str, y_title: str,
               hover_unit: str, date_format: str, y_range=None, fill: bool = True) -> go.Figure:
    """A single-series line over time with a vertical crosshair-style tooltip."""
    if df.empty:
        return _empty()
    fig = go.Figure(go.Scatter(
        x=df[x], y=df[y], mode="lines", line=dict(color=color, width=2),
        fill="tozeroy" if fill else None,
        fillcolor=_with_alpha(color, 0.08) if fill else None,
        hovertemplate="%{y:,.1f} " + hover_unit + "<extra></extra>",
    ))
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(tickformat=date_format, showgrid=False)
    fig.update_yaxes(title=y_title, title_font=dict(color=INK_MUTED, size=12),
                     rangemode="tozero", range=y_range)
    return _style(fig, height=360)


def _with_alpha(hex_color: str, alpha: float) -> str:
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def trend_chart(df: pd.DataFrame, period: str) -> go.Figure:
    x = "week_start" if period == "Weekly" else "month_start"
    return line_chart(df, x, "minutes", BLUE, "Minutes listened", "minutes",
                      "%b %Y", fill=True)


# ---- heatmap ------------------------------------------------------------------

def heatmap_chart(grid: pd.DataFrame, value_label: str = "minutes") -> go.Figure:
    """7 x 24 grid (weekday x hour). Darker blue = more listening."""
    if grid.to_numpy().sum() == 0:
        return _empty()
    hour_names = [f"{(h % 12) or 12}{'am' if h < 12 else 'pm'}" for h in range(24)]
    fig = go.Figure(go.Heatmap(
        z=grid.to_numpy(), x=list(range(24)), y=list(grid.index),
        colorscale=HEATMAP_SCALE, xgap=2, ygap=2,   # the 2px gaps keep cells distinct
        customdata=[[hour_names[h] for h in range(24)] for _ in grid.index],
        hovertemplate="%{y} %{customdata}<br>%{z:,.0f} " + value_label + "<extra></extra>",
        colorbar=dict(title=dict(text=value_label.capitalize(), font=dict(size=12)),
                      thickness=10, len=0.9, outlinewidth=0, tickfont=dict(color=INK_MUTED)),
    ))
    fig.update_yaxes(autorange="reversed", showgrid=False, linecolor="rgba(0,0,0,0)")
    fig.update_xaxes(showgrid=False, linecolor="rgba(0,0,0,0)", tickmode="array",
                     tickvals=list(range(0, 24, 3)), ticktext=[hour_names[h] for h in range(0, 24, 3)])
    return _style(fig, height=330)


# ---- streaks ----------------------------------------------------------------------

def streaks_chart(df: pd.DataFrame, top: int = 10) -> go.Figure:
    """The longest streaks, one bar each, labelled by their dates."""
    if df.empty:
        return _empty()
    top_df = df.head(top)
    labels = [f"{_nice_date(s)} → {_nice_date(e)}" for s, e in zip(top_df["streak_start"], top_df["streak_end"])]
    fig = go.Figure(go.Bar(
        x=top_df["days"], y=labels, orientation="h", marker_color=BLUE,
        text=[f"{d} days" for d in top_df["days"]], textposition="outside", cliponaxis=False,
        textfont=dict(color=INK_SECONDARY),
        hovertemplate="%{y}<br>%{x} days in a row<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(title="Consecutive days", title_font=dict(color=INK_MUTED, size=12),
                     range=[0, top_df["days"].max() * 1.25])
    return _style(fig, height=max(240, 34 * len(top_df) + 60))


def _nice_date(iso_date: str) -> str:
    return pd.Timestamp(iso_date).strftime("%b %d, %Y").replace(" 0", " ")


# ---- discovery -----------------------------------------------------------------------

def new_artists_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty()
    fig = go.Figure(go.Bar(
        x=pd.to_datetime(df["month_start"]), y=df["new_artists"], marker_color=AQUA,
        hovertemplate="%{x|%b %Y}<br>%{y} new artists<extra></extra>",
    ))
    fig.update_xaxes(tickformat="%b %Y", showgrid=False)
    fig.update_yaxes(title="New artists", title_font=dict(color=INK_MUTED, size=12))
    return _style(fig)


def discovery_rate_chart(df: pd.DataFrame) -> go.Figure:
    plot_df = df.assign(month_start=pd.to_datetime(df["month_start"]))
    return line_chart(plot_df, "month_start", "discovery_rate_pct", AQUA,
                      "% new artists", "% new", "%b %Y", fill=False)


def cumulative_artists_chart(df: pd.DataFrame) -> go.Figure:
    plot_df = df.assign(month_start=pd.to_datetime(df["month_start"]))
    return line_chart(plot_df, "month_start", "total_artists_discovered", AQUA,
                      "Artists discovered (running total)", "artists", "%b %Y")


# ---- skips ----------------------------------------------------------------------------

def skip_rate_chart(df: pd.DataFrame) -> go.Figure:
    plot_df = df.assign(month_start=pd.to_datetime(df["month_start"]))
    return line_chart(plot_df, "month_start", "skip_rate_pct", ORANGE,
                      "% of plays skipped", "% skipped", "%b %Y", y_range=[0, 100], fill=False)


def skip_timing_chart(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty()
    # Drop the '1. ' sort prefix and shorten ' sec' to 's' so the labels stay horizontal.
    labels = [s.split(". ", 1)[1].replace(" sec", "s") for s in df["skipped_after"]]
    fig = go.Figure(go.Bar(
        x=labels, y=df["pct_of_skips"], marker_color=ORANGE,
        customdata=df["skips"],
        text=[f"{p:.0f}%" for p in df["pct_of_skips"]], textposition="outside", cliponaxis=False,
        textfont=dict(color=INK_SECONDARY),
        hovertemplate="Skipped after %{x}<br>%{y:.1f}% of skips (%{customdata:,} plays)<extra></extra>",
    ))
    fig.update_yaxes(title="% of skips", title_font=dict(color=INK_MUTED, size=12),
                     range=[0, df["pct_of_skips"].max() * 1.2])
    fig.update_xaxes(showgrid=False)
    return _style(fig)


def skips_by_context_chart(df: pd.DataFrame, min_plays: int = 200) -> go.Figure:
    """Skip rate by device, shuffle on vs off. Two series, so a legend is shown;
    shuffle-on takes the skip colour and shuffle-off is the quiet grey."""
    df = df[df["plays"] >= min_plays]
    if df.empty:
        return _empty()
    platform_order = df.groupby("platform")["plays"].sum().sort_values(ascending=False).index.tolist()
    fig = go.Figure()
    for mode, color in (("shuffle on", ORANGE), ("shuffle off", GRAY)):
        part = df[df["shuffle_mode"] == mode].set_index("platform").reindex(platform_order)
        fig.add_trace(go.Bar(
            name=mode.capitalize(), x=platform_order, y=part["skip_rate_pct"], marker_color=color,
            customdata=part["plays"].fillna(0),
            hovertemplate="%{x}, " + mode + "<br>%{y:.1f}% skipped (%{customdata:,.0f} plays)<extra></extra>",
        ))
    fig.update_layout(barmode="group", bargap=0.35, bargroupgap=0.08,
                      legend=dict(orientation="h", y=1.1, x=0, font=dict(color=INK_SECONDARY)))
    fig.update_yaxes(title="% of plays skipped", title_font=dict(color=INK_MUTED, size=12), range=[0, 100])
    fig.update_xaxes(showgrid=False)
    return _style(fig, legend=True)
