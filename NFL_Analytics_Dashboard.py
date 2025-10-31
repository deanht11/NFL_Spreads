# nfl_epa_dashboard_week_selector.py

import pandas as pd
from dash import Dash, dcc, html, Input, Output
import plotly.graph_objects as go
import nfl_data_py as nfl
import asyncio

# === 1. Load Team Metrics ===
df = pd.read_csv("nfl_team_metrics_2025_with_rolling.csv")
df = df.dropna(subset=["week", "team"]).sort_values(["team", "week"])

# === 2. Load Schedule Safely ===
try:
    games = nfl.import_schedules([2025])
    if games.empty:
        print("⚠️ Warning: games dataset is empty — Vegas/matchup tabs will be limited.")
except Exception as e:
    print("⚠️ Could not load games data:", e)
    games = pd.DataFrame(columns=["week", "home_team", "away_team", "spread_line", "total_line", "result"])

# Clean column names if needed
cols = games.columns
spread_col = "spread_line" if "spread_line" in cols else next((c for c in cols if "spread" in c.lower()), None)
total_col = "total_line" if "total_line" in cols else next((c for c in cols if "total" in c.lower()), None)
result_col = "result" if "result" in cols else next((c for c in cols if "result" in c.lower()), None)

schedule_cols = ["week", "home_team", "away_team"]
rename_map = {}
if spread_col:
    schedule_cols.append(spread_col)
    rename_map[spread_col] = "spread_line"
else:
    games["spread_line"] = None
if total_col:
    schedule_cols.append(total_col)
    rename_map[total_col] = "total_line"
else:
    games["total_line"] = None
if result_col:
    schedule_cols.append(result_col)
    rename_map[result_col] = "result"
else:
    games["result"] = None

games = games[schedule_cols].rename(columns=rename_map)

# === 3. Build Available Weeks & Matchups ===
available_weeks = sorted(games["week"].dropna().astype(int).unique())
current_week = max(available_weeks) if available_weeks else 1

# Precompute week->matchup dict
matchup_dict = {
    int(w): [
        {"label": f"{row['away_team']} @ {row['home_team']}", "value": f"{row['away_team']}@{row['home_team']}"}
        for _, row in games[games["week"] == w].iterrows()
    ]
    for w in available_weeks
}

default_game = matchup_dict.get(current_week, [])[0]["value"] if matchup_dict.get(current_week) else None

# === 4. Metric Options ===
metric_options = {
    "Offensive EPA/play": "rolling_epa_per_play_3wk",
    "Defensive EPA/play": "rolling_def_epa_per_play_3wk",
    "Offensive EPA/pass": "rolling_epa_per_pass_3wk",
    "Offensive EPA/rush": "rolling_epa_per_rush_3wk",
    "Defensive EPA/pass": "rolling_def_epa_per_pass_3wk",
    "Defensive EPA/rush": "rolling_def_epa_per_rush_3wk",
}

# === 5. Dash Layout ===
app = Dash(__name__)
app.title = "NFL EPA Matchup Dashboard"

app.layout = html.Div([
    html.H1("🏈 NFL Advanced EPA & Matchup Dashboard (2025 Season)", style={"textAlign": "center"}),

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
        dcc.Tab(label="💰 Vegas Lines & Win Probabilities", value="vegas"),
        dcc.Tab(label="⚔️ Matchup Comparison", value="matchup")
    ]),

    html.Div(id="week-matchup-selectors", style={"margin": "15px"}),

    html.Div(id="tab-content")
])

# === 6. Week + Matchup Dropdowns ===
@app.callback(
    Output("week-matchup-selectors", "children"),
    Input("tabs", "value")
)
def show_week_matchup_dropdown(tab):
    if tab != "matchup":
        return ""
    return html.Div([
        html.Label("Select Week:"),
        dcc.Dropdown(
            id="week-dropdown",
            options=[{"label": f"Week {w}", "value": w} for w in available_weeks],
            value=current_week,
            clearable=False,
            style={"width": "20%", "display": "inline-block", "marginRight": "15px"}
        ),
        html.Label("Select Game:"),
        dcc.Dropdown(
            id="matchup-dropdown",
            options=matchup_dict.get(current_week, []),
            value=default_game,
            clearable=False,
            style={"width": "40%", "display": "inline-block"}
        )
    ])

# Update matchups dynamically when week changes
@app.callback(
    Output("matchup-dropdown", "options"),
    Output("matchup-dropdown", "value"),
    Input("week-dropdown", "value")
)
def update_matchups_for_week(selected_week):
    opts = matchup_dict.get(selected_week, [])
    val = opts[0]["value"] if opts else None
    return opts, val

# === 7. Main Callback for All Tabs ===
@app.callback(
    Output("tab-content", "children"),
    Input("tabs", "value"),
    Input("metric-dropdown", "value"),
    Input("team-dropdown", "value"),
    Input("week-dropdown", "value"),
    Input("matchup-dropdown", "value")
)
def render_content(tab, metric_col, selected_teams, selected_week, selected_matchup):

    if df.empty:
        return html.Div("❌ No team metrics available.")

    # --- Rolling EPA Trends ---
    if tab == "time_series":
        fig = go.Figure()
        for team in selected_teams:
            team_df = df[df["team"] == team]
            if len(team_df) < 3:
                continue
            fig.add_trace(go.Scatter(
                x=team_df["week"], y=team_df[metric_col],
                mode="lines+markers", name=team,
                hovertemplate=team + "<br>Week: %{x}<br>EPA: %{y:.3f}<extra></extra>"
            ))
        metric_name = [k for k, v in metric_options.items() if v == metric_col][0]
        fig.update_layout(
            title=f"{metric_name} – Rolling 3-Week Average",
            xaxis_title="Week", yaxis_title="EPA per Play (3-Week Avg)",
            template="plotly_white", hovermode="x unified"
        )
        return dcc.Graph(figure=fig)

    # --- Scatter Tab ---
    elif tab == "scatter":
        scatter_df = df.groupby("team").agg({
            "rolling_epa_per_play_3wk": "mean",
            "rolling_def_epa_per_play_3wk": "mean"
        }).dropna()

        fig = go.Figure()
        for team in scatter_df.index:
            fig.add_trace(go.Scatter(
                x=[scatter_df.loc[team, "rolling_epa_per_play_3wk"]],
                y=[-scatter_df.loc[team, "rolling_def_epa_per_play_3wk"]],
                mode="markers+text", text=team, textposition="top center"
            ))
        fig.update_layout(
            title="Offensive vs Defensive EPA (3-Week Rolling Avg)",
            xaxis_title="Offensive EPA/play (higher = better)",
            yaxis_title="Defensive EPA/play (lower = better)",
            template="plotly_white", hovermode="closest"
        )
        return dcc.Graph(figure=fig)

    # --- Vegas Tab ---
    elif tab == "vegas":
        if games.empty:
            return html.Div("⚠️ Vegas data not available.")
        fig = go.Figure()
        for team in selected_teams:
            tg = games[(games["home_team"] == team) | (games["away_team"] == team)]
            if tg.empty: continue
            fig.add_trace(go.Scatter(
                x=tg["week"], y=tg["spread_line"], mode="lines+markers",
                name=f"{team} Spread",
                hovertemplate=team + "<br>Week %{x}<br>Spread: %{y:.1f}<extra></extra>"
            ))
            fig.add_trace(go.Scatter(
                x=tg["week"], y=tg["total_line"], mode="lines+markers",
                name=f"{team} Total",
                hovertemplate=team + "<br>Week %{x}<br>Total: %{y:.1f}<extra></extra>",
                line=dict(dash="dot")
            ))
        fig.update_layout(
            title="Vegas Spreads & Totals by Week",
            xaxis_title="Week", yaxis_title="Line Value (Points)",
            template="plotly_white", hovermode="x unified"
        )
        return dcc.Graph(figure=fig)

    # --- Matchup Tab ---
    elif tab == "matchup":
        if not selected_matchup or not selected_week:
            return html.Div("⚠️ Select a week and matchup.")
        away, home = selected_matchup.split("@")

        off = df.groupby("team")[["rolling_epa_per_pass_3wk", "rolling_epa_per_rush_3wk"]].mean().reset_index()
        deff = df.groupby("team")[["rolling_def_epa_per_pass_3wk", "rolling_def_epa_per_rush_3wk"]].mean().reset_index()

        def val(team, frame, col):
            if team in frame["team"].values:
                return frame.loc[frame["team"] == team, col].values[0]
            return 0

        matchup_rows = [
            {"type": "Pass", "matchup": f"{away} Off vs {home} Def",
             "delta": val(away, off, "rolling_epa_per_pass_3wk") - val(home, deff, "rolling_def_epa_per_pass_3wk")},
            {"type": "Rush", "matchup": f"{away} Off vs {home} Def",
             "delta": val(away, off, "rolling_epa_per_rush_3wk") - val(home, deff, "rolling_def_epa_per_rush_3wk")},
            {"type": "Pass", "matchup": f"{home} Off vs {away} Def",
             "delta": val(home, off, "rolling_epa_per_pass_3wk") - val(away, deff, "rolling_def_epa_per_pass_3wk")},
            {"type": "Rush", "matchup": f"{home} Off vs {away} Def",
             "delta": val(home, off, "rolling_epa_per_rush_3wk") - val(away, deff, "rolling_def_epa_per_rush_3wk")}
        ]
        matchup_df = pd.DataFrame(matchup_rows)
        matchup_df["color"] = matchup_df["delta"].apply(lambda x: "#2ECC71" if x > 0 else "#E74C3C")

        fig = go.Figure(go.Bar(
            x=matchup_df["matchup"] + " – " + matchup_df["type"],
            y=matchup_df["delta"], marker_color=matchup_df["color"],
            hovertemplate="%{x}<br>EPA Advantage: %{y:.3f}<extra></extra>"
        ))
        fig.update_layout(
            title=f"Week {selected_week}: {away} @ {home} – Offense vs Defense EPA Advantage",
            xaxis_title="Matchup & Play Type", yaxis_title="EPA Advantage (Offense – Defense)",
            template="plotly_white", xaxis_tickangle=-25
        )
        # === Team Rankings Summary ===
        def rank_teams(col):
            ranked = df.groupby("team")[col].mean().rank(ascending=False, method="min")
            return ranked.to_dict()

        ranks = {
            "off_pass": rank_teams("rolling_epa_per_pass_3wk"),
            "off_rush": rank_teams("rolling_epa_per_rush_3wk"),
            "def_pass": rank_teams("rolling_def_epa_per_pass_3wk"),
            "def_rush": rank_teams("rolling_def_epa_per_rush_3wk"),
        }

        def style_rank(rank):
            if rank <= 10:
                return {"color": "#2ECC71", "fontWeight": "bold"}  # top 10 = green
            elif rank >= 23:
                return {"color": "#E74C3C", "fontWeight": "bold"}  # bottom 10 = red
            else:
                return {}

        summary_table = html.Table([
            html.Thead(html.Tr([
                html.Th("Team"),
                html.Th("Off Pass Rank"),
                html.Th("Off Rush Rank"),
                html.Th("Def Pass Rank"),
                html.Th("Def Rush Rank")
            ])),
            html.Tbody([
                html.Tr([
                    html.Td(team),
                    html.Td(int(ranks["off_pass"].get(team, 0)), style=style_rank(ranks["off_pass"].get(team, 0))),
                    html.Td(int(ranks["off_rush"].get(team, 0)), style=style_rank(ranks["off_rush"].get(team, 0))),
                    html.Td(int(ranks["def_pass"].get(team, 0)), style=style_rank(ranks["def_pass"].get(team, 0))),
                    html.Td(int(ranks["def_rush"].get(team, 0)), style=style_rank(ranks["def_rush"].get(team, 0))),
                ]) for team in [away, home]
            ])
        ], style={
            "width": "60%",
            "margin": "20px auto",
            "borderCollapse": "collapse",
            "textAlign": "center",
            "fontSize": "16px",
            "border": "1px solid #ccc"
        })

        # === Expected EPA Advantage ===
        league_avg_off = df["rolling_epa_per_play_3wk"].mean()
        league_avg_def = df["rolling_def_epa_per_play_3wk"].mean()

        team_off_e = df.groupby("team")["rolling_epa_per_play_3wk"].mean()
        team_def_e = df.groupby("team")["rolling_def_epa_per_play_3wk"].mean()

        away_edge = (team_off_e.get(away, 0) - team_def_e.get(home, 0)) - (league_avg_off - league_avg_def)
        home_edge = (team_off_e.get(home, 0) - team_def_e.get(away, 0)) - (league_avg_off - league_avg_def)

        # === Expected EPA Advantage ===
        league_avg_off = df["rolling_epa_per_play_3wk"].mean()
        league_avg_def = df["rolling_def_epa_per_play_3wk"].mean()

        team_off_e = df.groupby("team")["rolling_epa_per_play_3wk"].mean()
        team_def_e = df.groupby("team")["rolling_def_epa_per_play_3wk"].mean()

        away_edge = (team_off_e.get(away, 0) - team_def_e.get(home, 0)) - (league_avg_off - league_avg_def)
        home_edge = (team_off_e.get(home, 0) - team_def_e.get(away, 0)) - (league_avg_off - league_avg_def)

        # Determine projected winner
        if away_edge > home_edge:
            winner = away
            color = "#2ECC71"
        elif home_edge > away_edge:
            winner = home
            color = "#2ECC71"
        else:
            winner = "Even"
            color = "#95A5A6"

        diff = abs(away_edge - home_edge)
        if diff >= 0.15:
            confidence = "High confidence"
        elif diff >= 0.07:
            confidence = "Moderate confidence"
        else:
            confidence = "Low confidence"

        edge_text = html.Div([
            html.H4("⚖️ Predicted Efficiency Edge (EPA Differential)", style={"textAlign": "center"}),
            html.Table([
                html.Tr([
                    html.Td(f"{away} Expected Edge:", style={"fontWeight": "bold", "textAlign": "right", "paddingRight": "10px"}),
                    html.Td(f"{away_edge:+.3f} EPA", style={"color": "#2ECC71" if away_edge > 0 else "#E74C3C", "fontWeight": "bold"})
                ]),
                html.Tr([
                    html.Td(f"{home} Expected Edge:", style={"fontWeight": "bold", "textAlign": "right", "paddingRight": "10px"}),
                    html.Td(f"{home_edge:+.3f} EPA", style={"color": "#2ECC71" if home_edge > 0 else "#E74C3C", "fontWeight": "bold"})
                ])
            ], style={
                "margin": "auto",
                "borderCollapse": "collapse",
                "textAlign": "center",
                "fontSize": "16px",
            }),
            html.Br(),
            html.H4(f"🏆 Projected Advantage: {winner}", style={
                "textAlign": "center",
                "color": color,
                "fontWeight": "bold",
                "fontSize": "20px"
            }),
            html.P(f"Confidence level: {confidence}", style={"textAlign": "center", "fontStyle": "italic", "marginTop": "-10px"})
        ])

        # Return graph + ranks + projected edge
        return html.Div([
            dcc.Graph(figure=fig),
            html.H4("📊 Team Efficiency Ranks (Season-to-Date)", style={"textAlign": "center", "marginTop": "10px"}),
            summary_table,
            html.Br(),
            edge_text
        ])





        return dcc.Graph(figure=fig)

    return html.Div("⚙️ Select a valid tab above to view data.")

# === 8. Run App (async-safe) ===
if __name__ == "__main__":
    try:
        asyncio.run(app.run(debug=True))
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.create_task(app.run(debug=True))
