# nfl_epa_dashboard_advanced_fixed.py

import pandas as pd
from dash import Dash, dcc, html, Input, Output
import plotly.graph_objects as go
import nfl_data_py as nfl

# === 1. Load team metrics ===
df = pd.read_csv("nfl_team_metrics_2025_with_rolling.csv")
df = df.dropna(subset=["week", "team"]).sort_values(["team", "week"])

# === 2. Load Vegas spreads & outcomes safely ===
try:
    games = nfl.import_schedules([2025])
    if games.empty:
        print("⚠️ Warning: games dataset is empty — Vegas tab will show no data.")
except Exception as e:
    print("⚠️ Could not load games data:", e)
    games = pd.DataFrame(columns=["week", "home_team", "away_team", "spread_line", "total_line", "result"])

# Handle schema differences
cols = games.columns
spread_col = "spread_line" if "spread_line" in cols else cols[cols.str.contains("spread", case=False)].tolist()[0] if any(cols.str.contains("spread", case=False)) else None
total_col = "total_line" if "total_line" in cols else cols[cols.str.contains("total", case=False)].tolist()[0] if any(cols.str.contains("total", case=False)) else None
result_col = "result" if "result" in cols else cols[cols.str.contains("result", case=False)].tolist()[0] if any(cols.str.contains("result", case=False)) else None

games = games[["week", "home_team", "away_team", spread_col, total_col, result_col]].rename(
    columns={spread_col: "spread_line", total_col: "total_line", result_col: "result"}
)

# === 3. Define Metric Options ===
metric_options = {
    "Offensive EPA/play": "rolling_epa_per_play_3wk",
    "Defensive EPA/play": "rolling_def_epa_per_play_3wk",
    "Offensive EPA/pass": "rolling_epa_per_pass_3wk",
    "Offensive EPA/rush": "rolling_epa_per_rush_3wk",
    "Defensive EPA/pass": "rolling_def_epa_per_pass_3wk",
    "Defensive EPA/rush": "rolling_def_epa_per_rush_3wk",
}

# === 4. Build Dash App ===
app = Dash(__name__)
app.title = "NFL EPA Dashboard (Advanced)"

app.layout = html.Div([
    html.H1("NFL Advanced EPA & Betting Dashboard (2025 Season)", style={"textAlign": "center"}),

    html.Div([
        html.Label("Select Metric:"),
        dcc.Dropdown(
            id="metric-dropdown",
            options=[{"label": k, "value": v} for k, v in metric_options.items()],
            value="rolling_epa_per_play_3wk",
            clearable=False,
            style={"width": "40%", "display": "inline-block", "marginRight": "20px"}
        ),
        html.Label("Select Team(s):"),
        dcc.Dropdown(
            id="team-dropdown",
            options=[{"label": t, "value": t} for t in sorted(df["team"].unique())],
            value=["KC", "BUF", "DAL"],
            multi=True,
            style={"width": "40%", "display": "inline-block"}
        ),
    ], style={"margin": "20px"}),

    dcc.Tabs(id="tabs", value="time_series", children=[
        dcc.Tab(label="📈 Rolling EPA Trends", value="time_series"),
        dcc.Tab(label="🏈 Offense vs Defense Scatter", value="scatter"),
        dcc.Tab(label="💰 Vegas Lines & Win Probabilities", value="vegas")
    ]),

    html.Div(id="tab-content")
])

# === 5. Callbacks ===

@app.callback(
    Output("tab-content", "children"),
    Input("tabs", "value"),
    Input("metric-dropdown", "value"),
    Input("team-dropdown", "value")
)
def render_content(tab, metric_col, selected_teams):

    # Ensure valid data
    if df.empty:
        return html.Div("❌ No team metrics available. Please check your CSV file.")

    # ----- TAB 1: Rolling EPA Trends -----
    if tab == "time_series":
        fig = go.Figure()
        for team in selected_teams:
            team_df = df[df["team"] == team]
            if len(team_df) < 3:
                continue
            fig.add_trace(go.Scatter(
                x=team_df["week"],
                y=team_df[metric_col],
                mode="lines+markers",
                name=team,
                hovertemplate=team + "<br>Week: %{x}<br>EPA: %{y:.3f}<extra></extra>",
            ))

        metric_name = [k for k, v in metric_options.items() if v == metric_col][0]
        fig.update_layout(
            title=f"{metric_name} – Rolling 3-Week Average",
            xaxis_title="Week",
            yaxis_title="EPA per Play (3-Week Avg)",
            template="plotly_white",
            hovermode="x unified",
            legend_title="Team",
        )
        return dcc.Graph(figure=fig)

    # ----- TAB 2: Offense vs Defense Scatter -----
    elif tab == "scatter":
        scatter_df = df.groupby("team").agg({
            "rolling_epa_per_play_3wk": "mean",
            "rolling_def_epa_per_play_3wk": "mean"
        }).dropna()

        if scatter_df.empty:
            return html.Div("⚠️ Not enough data for scatter plot yet.")

        fig = go.Figure()

        for team in scatter_df.index:
            fig.add_trace(go.Scatter(
                x=[scatter_df.loc[team, "rolling_epa_per_play_3wk"]],
                y=[-scatter_df.loc[team, "rolling_def_epa_per_play_3wk"]],  # invert defense axis
                mode="markers+text",
                text=team,
                textposition="top center",
                name=team
            ))

        fig.update_layout(
            title="Offensive vs Defensive EPA (3-Week Rolling Avg)",
            xaxis_title="Offensive EPA/play (higher = better)",
            yaxis_title="Defensive EPA/play (lower = better)",
            template="plotly_white",
            hovermode="closest",
            showlegend=False
        )
        return dcc.Graph(figure=fig)

    # ----- TAB 3: Vegas & Win Probabilities -----
    elif tab == "vegas":
        if games.empty:
            return html.Div("⚠️ Vegas data not available yet for 2025.")

        fig = go.Figure()

        for team in selected_teams:
            team_games = games[(games["home_team"] == team) | (games["away_team"] == team)]
            if team_games.empty:
                continue
            fig.add_trace(go.Scatter(
                x=team_games["week"],
                y=team_games["spread_line"],
                mode="lines+markers",
                name=f"{team} Spread",
                hovertemplate=team + "<br>Week %{x}<br>Spread: %{y:.1f}<extra></extra>"
            ))
            fig.add_trace(go.Scatter(
                x=team_games["week"],
                y=team_games["total_line"],
                mode="lines+markers",
                name=f"{team} Total",
                hovertemplate=team + "<br>Week %{x}<br>Total: %{y:.1f}<extra></extra>",
                line=dict(dash="dot")
            ))

        fig.update_layout(
            title="Vegas Spreads & Totals by Week",
            xaxis_title="Week",
            yaxis_title="Line Value (Points)",
            template="plotly_white",
            hovermode="x unified"
        )
        return dcc.Graph(figure=fig)

    # ----- Default fallback -----
    return html.Div("⚙️ Select a valid tab above to view data.")


# === 6. Run App ===
if __name__ == "__main__":
    import asyncio

    # If an event loop is already running (e.g., in Jupyter), reuse it safely
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(app.run(debug=True))
    except RuntimeError:
        # No running loop (normal Python run) → just start it
        app.run(debug=True)

