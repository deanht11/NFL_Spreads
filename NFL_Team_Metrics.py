# nfl_team_metrics_2025_with_interactive_charts.py

import pandas as pd
import nfl_data_py as nfl
import plotly.graph_objects as go
import os

# === 1. Load play-by-play data ===
pbp = nfl.import_pbp_data([2025], downcast=True)
pbp = pbp[pbp["week"].notna()]

# === 2. Weekly offensive metrics ===
weekly_offense = (
    pbp.groupby(["posteam", "week"])
    .apply(lambda df: pd.Series({
        "plays": len(df),
        "epa_per_play": df["epa"].mean(),
        "epa_per_pass": df.loc[df["play_type"] == "pass", "epa"].mean(),
        "epa_per_rush": df.loc[df["play_type"] == "run", "epa"].mean(),
    }))
    .reset_index()
    .rename(columns={"posteam": "team"})
)

# === 3. Weekly defensive metrics ===
weekly_defense = (
    pbp.groupby(["defteam", "week"])
    .apply(lambda df: pd.Series({
        "def_plays": len(df),
        "def_epa_per_play": df["epa"].mean(),
        "def_epa_per_pass": df.loc[df["play_type"] == "pass", "epa"].mean(),
        "def_epa_per_rush": df.loc[df["play_type"] == "run", "epa"].mean(),
    }))
    .reset_index()
    .rename(columns={"defteam": "team"})
)

# === 4. Merge offense + defense ===
weekly = pd.merge(weekly_offense, weekly_defense, on=["team", "week"], how="outer").sort_values(["team", "week"])

# === 5. Rolling 3-week averages ===
rolling_metrics = (
    weekly.groupby("team")
    .rolling(3, on="week")[[
        "epa_per_play", "epa_per_pass", "epa_per_rush",
        "def_epa_per_play", "def_epa_per_pass", "def_epa_per_rush"
    ]]
    .mean()
    .reset_index()
)

rolling_metrics = rolling_metrics.rename(columns={
    "epa_per_play": "rolling_epa_per_play_3wk",
    "epa_per_pass": "rolling_epa_per_pass_3wk",
    "epa_per_rush": "rolling_epa_per_rush_3wk",
    "def_epa_per_play": "rolling_def_epa_per_play_3wk",
    "def_epa_per_pass": "rolling_def_epa_per_pass_3wk",
    "def_epa_per_rush": "rolling_def_epa_per_rush_3wk"
})

# === 6. Merge back ===
weekly_full = pd.merge(weekly, rolling_metrics, on=["team", "week"], how="left")

# === 7. Add team metadata ===
standings = nfl.import_team_desc()
standings = standings.rename(columns={"team_abbr": "team"})
weekly_full = pd.merge(weekly_full, standings, on="team", how="left")

# === 8. Save metrics to CSV ===
weekly_full.to_csv("nfl_team_metrics_2025_with_rolling.csv", index=False)
print("✅ Saved weekly and 3-week rolling EPA metrics to nfl_team_metrics_2025_with_rolling.csv")

# === 9. Create interactive charts folder ===
os.makedirs("charts", exist_ok=True)

# === 10. Interactive team charts ===
for team, df in weekly_full.groupby("team"):
    if len(df) < 3:
        continue

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["week"], y=df["rolling_epa_per_play_3wk"],
        mode='lines+markers', name="Off EPA/play", line=dict(width=3)
    ))

    fig.add_trace(go.Scatter(
        x=df["week"], y=df["rolling_def_epa_per_play_3wk"],
        mode='lines+markers', name="Def EPA/play", line=dict(width=2, dash="dot")
    ))

    fig.add_trace(go.Scatter(
        x=df["week"], y=df["rolling_epa_per_pass_3wk"],
        mode='lines', name="Off EPA/pass", line=dict(width=1.5)
    ))

    fig.add_trace(go.Scatter(
        x=df["week"], y=df["rolling_epa_per_rush_3wk"],
        mode='lines', name="Off EPA/rush", line=dict(width=1.5)
    ))

    fig.update_layout(
        title=f"{team} – Rolling 3-Week EPA Trends (2025 Season)",
        xaxis_title="Week",
        yaxis_title="EPA per Play (3-Week Rolling Avg)",
        template="plotly_white",
        hovermode="x unified"
    )

    fig.write_html(f"charts/{team}_rolling_epa_interactive.html")

print("🌐 Saved interactive team charts in the 'charts/' folder.")

# === 11. Interactive league-wide chart ===
fig_all = go.Figure()

for team, df in weekly_full.groupby("team"):
    fig_all.add_trace(go.Scatter(
        x=df["week"],
        y=df["rolling_epa_per_play_3wk"],
        mode="lines",
        name=team,
        hovertemplate=team + "<br>Week: %{x}<br>EPA/play: %{y:.3f}<extra></extra>",
        line=dict(width=2)
    ))

fig_all.update_layout(
    title="NFL Offensive Rolling 3-Week EPA per Play – All Teams (2025 Season)",
    xaxis_title="Week",
    yaxis_title="EPA per Play (3-Week Rolling Avg)",
    template="plotly_white",
    hovermode="x unified",
    legend_title="Team"
)

fig_all.write_html("charts/ALL_TEAMS_rolling_epa_interactive.html")
print("📈 Saved interactive league-wide EPA chart in 'charts/'.")
