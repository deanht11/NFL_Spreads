import os
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import nfl_data_py as nfl

# ---------------------------------------
# 1. Load play-by-play data for 2025 season
# ---------------------------------------
season = 2025
print("Loading play-by-play data...")
pbp = nfl.import_pbp_data([season])

# ---------------------------------------
# 2. Aggregate QB-level weekly stats
# ---------------------------------------
# We'll keep only pass plays
pbp_pass = pbp[pbp["play_type"] == "pass"].copy()

qb_stats = (
    pbp_pass.groupby(["passer_player_name", "week"], as_index=False)
    .agg(
        attempts=("pass_attempt", "sum"),
        completions=("complete_pass", "sum"),
        passing_yards=("passing_yards", "sum"),
        passing_tds=("pass_touchdown", "sum"),
        interceptions=("interception", "sum"),
        epa=("epa", "mean"),              # per-play efficiency
        cpoe=("cpoe", "mean"),            # accuracy over expectation
        success_rate=("success", "mean"), # % of plays w/ positive EPA
    )
)

# Remove rows without a valid QB name
qb_stats = qb_stats.dropna(subset=["passer_player_name"])

# Add completion %
qb_stats["completion_pct"] = qb_stats["completions"] / qb_stats["attempts"]

# ---------------------------------------
# 3. Filter to true starting quarterbacks
# ---------------------------------------
# Define a "start" as any week where QB has >= 20 attempts.
starts = (
    qb_stats[qb_stats["attempts"] >= 20]
    .groupby("passer_player_name")["week"]
    .count()
    .reset_index()
)
starts.columns = ["passer_player_name", "starts"]

# Average attempts per QB across the season
avg_atts = qb_stats.groupby("passer_player_name", as_index=False)["attempts"].mean()

# Merge and decide who is a starter:
# - At least 3 such "starts"
# - Avg >= 20 attempts per game
starters = pd.merge(starts, avg_atts, on="passer_player_name")
starters = starters[
    (starters["starts"] >= 3) &
    (starters["attempts"] >= 20)
]["passer_player_name"]

# Keep only those starting QBs
qb_stats = qb_stats[qb_stats["passer_player_name"].isin(starters)].copy()
print(f"✅ Filtered to {len(starters)} starting quarterbacks.")

# ---------------------------------------
# 4. Compute rolling 3-week averages
# ---------------------------------------
qb_stats = qb_stats.sort_values(["passer_player_name", "week"])

metrics = [
    "passing_yards",
    "passing_tds",
    "interceptions",
    "epa",
    "cpoe",
    "success_rate",
    "completion_pct",
]

for m in metrics:
    qb_stats[f"{m}_rolling"] = qb_stats.groupby("passer_player_name")[m].transform(
        lambda x: x.rolling(3, min_periods=1).mean()
    )

# ---------------------------------------
# 5. Determine top QBs by season average EPA
# ---------------------------------------
top_qbs = (
    qb_stats.groupby("passer_player_name")["epa"]
    .mean()
    .nlargest(10)
    .index
    .tolist()
)
print("Top 10 QBs by average EPA:", ", ".join(top_qbs))

# ---------------------------------------
# 6. Build interactive dashboard
# ---------------------------------------
fig = go.Figure()
buttons = []
traces_per_metric = []

unique_qbs = qb_stats["passer_player_name"].unique().tolist()

for m in metrics:
    metric_col = f"{m}_rolling"
    pretty_title = m.replace("_", " ").title()

    # Compute league average line for this metric per week
    league_avg = (
        qb_stats.groupby("week")[metric_col]
        .mean()
        .reset_index()
        .rename(columns={metric_col: "league_val"})
    )

    metric_traces = []

    # Add one trace per QB for this metric
    for qb in unique_qbs:
        qb_data = qb_stats[qb_stats["passer_player_name"] == qb]

        # Only show top 10 EPA QBs by default on first metric ("epa")
        visible_initial = (m == "epa") and (qb in top_qbs)

        # We can't use f-strings with %{x} / %{y} in them directly,
        # because Python will try to interpret {x} as a Python variable.
        # So we build the string in pieces.
        hover_text = (
            qb
            + "<br>Week: %{x}"
            + "<br>"
            + pretty_title
            + ": %{y:.3f}"
            + "<extra></extra>"
        )

        fig.add_trace(
            go.Scatter(
                x=qb_data["week"],
                y=qb_data[metric_col],
                mode="lines",
                name=qb,
                line=dict(width=1.5),
                hovertemplate=hover_text,
                visible=visible_initial,
                # dim non-top guys on the default metric
                opacity=1.0 if (qb in top_qbs) else 0.2,
            )
        )

        metric_traces.append(len(fig.data) - 1)

    # Add league average line for this metric
    league_hover = (
        "League Avg<br>"
        "Week: %{x}"
        "<br>"
        + pretty_title
        + ": %{y:.3f}"
        + "<extra></extra>"
    )

    fig.add_trace(
        go.Scatter(
            x=league_avg["week"],
            y=league_avg["league_val"],
            mode="lines",
            name=f"League Avg ({pretty_title})",
            line=dict(width=3, dash="dash"),
            hovertemplate=league_hover,
            visible=(m == "epa"),  # league average visible for default metric
            opacity=1.0,
        )
    )

    metric_traces.append(len(fig.data) - 1)

    # record which traces correspond to this metric
    traces_per_metric.append(metric_traces)

# ---------------------------------------
# 7. Build dropdown to switch metrics
# ---------------------------------------
total_traces = len(fig.data)
for i, m in enumerate(metrics):
    pretty_title = m.replace("_", " ").title()

    # default all traces off
    vis_mask = [False] * total_traces

    # turn on the traces for this metric
    for idx in traces_per_metric[i]:
        vis_mask[idx] = True

    buttons.append(
        dict(
            label=pretty_title,
            method="update",
            args=[
                {"visible": vis_mask},
                {
                    "title": f"QB Rolling {pretty_title} (3-Week Average)",
                    "yaxis": {"title": pretty_title},
                },
            ],
        )
    )

# ---------------------------------------
# 8. Layout / menu styling
# ---------------------------------------
fig.update_layout(
    title="QB Rolling EPA (3-Week Average)",
    template="plotly_dark",
    xaxis_title="Week",
    yaxis_title="EPA",
    hovermode="x unified",
    updatemenus=[
        dict(
            active=metrics.index("epa"),
            buttons=buttons,
            x=1.05,
            y=1.15,
            xanchor="left",
            yanchor="top",
            direction="down",
            bgcolor="#1f2c56",
            font=dict(color="white"),
        )
    ],
    legend=dict(
        tracegroupgap=4,
        title="Quarterback",
    ),
)

# ---------------------------------------
# 9. Save interactive dashboard
# ---------------------------------------
output_dir = "qb_metric_charts_interactive"
os.makedirs(output_dir, exist_ok=True)

output_path = os.path.join(output_dir, "qb_dashboard.html")
fig.write_html(output_path, auto_open=True)

print(f"✅ Interactive QB dashboard saved to {output_path}")
