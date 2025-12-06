
import pandas as pd
from dash import Dash, dcc, html, Input, Output
import plotly.graph_objects as go
import nfl_data_py as nfl
import asyncio

# =====================================================
# 1. LOAD / PREP DATA
# =====================================================

# Load rolling EPA/team strength data
df = pd.read_csv("nfl_team_metrics_2025_with_rolling.csv")
df = df.dropna(subset=["week", "team"]).sort_values(["team", "week"])

# Load NFL schedule / betting lines
try:
    games = nfl.import_schedules([2025])
    if games.empty:
        print("⚠️ Warning: schedule data empty.")
except Exception as e:
    print("⚠️ Could not load games data:", e)
    games = pd.DataFrame(
        columns=["week", "home_team", "away_team", "spread_line", "total_line", "result"]
    )

# Normalize column names from games so we always have:
# week, home_team, away_team, spread_line, total_line, result
cols = games.columns

spread_col = "spread_line" if "spread_line" in cols else next(
    (c for c in cols if "spread" in c.lower()), None
)
total_col = "total_line" if "total_line" in cols else next(
    (c for c in cols if "total" in c.lower()), None
)
result_col = "result" if "result" in cols else next(
    (c for c in cols if "result" in c.lower()), None
)

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

# Available weeks and a "current week" guess
available_weeks = sorted(games["week"].dropna().astype(int).unique())
current_week = max(available_weeks) if available_weeks else 1

# Build per-week matchup choices like "CIN@CHI"
matchup_dict = {
    int(w): [
        {
            "label": f"{row['away_team']} @ {row['home_team']}",
            "value": f"{row['away_team']}@{row['home_team']}",
        }
        for _, row in games[games["week"] == w].iterrows()
    ]
    for w in available_weeks
}

default_game = matchup_dict.get(current_week, [])[0]["value"] if matchup_dict.get(current_week) else None

# Dropdown metric options used in Rolling EPA tab
metric_options = {
    "Offensive EPA/play": "rolling_epa_per_play_3wk",
    "Defensive EPA/play": "rolling_def_epa_per_play_3wk",
    "Offensive EPA/pass": "rolling_epa_per_pass_3wk",
    "Offensive EPA/rush": "rolling_epa_per_rush_3wk",
    "Defensive EPA/pass": "rolling_def_epa_per_pass_3wk",
    "Defensive EPA/rush": "rolling_def_epa_per_rush_3wk",
}


# =====================================================
# 2. DASH APP LAYOUT (WITH PERSISTENCE)
# =====================================================

app = Dash(__name__)
app.title = "NFL EPA & Upset Dashboard"

app.layout = html.Div([
    html.H1("🏈 NFL EPA & Upset Analytics Dashboard", style={"textAlign": "center"}),

    # Global metric + team selectors (persisted across tabs and reloads)
    html.Div([
        html.Label("Select Metric:"),
        dcc.Dropdown(
            id="metric-dropdown",
            options=[{"label": k, "value": v} for k, v in metric_options.items()],
            value="rolling_epa_per_play_3wk",
            clearable=False,
            persistence=True,
            persistence_type="local",
            style={"width": "40%", "display": "inline-block", "marginRight": "20px"}
        ),

        html.Label("Select Team(s):"),
        dcc.Dropdown(
            id="team-dropdown",
            options=[{"label": t, "value": t} for t in sorted(df["team"].unique())],
            value=["KC", "BUF", "DAL"],
            multi=True,
            persistence=True,
            persistence_type="local",
            style={"width": "40%", "display": "inline-block"}
        ),
    ], style={"margin": "20px"}),

    # Tabs, also persisted
    dcc.Tabs(
        id="tabs",
        value="about",
        persistence=True,
        persistence_type="local",
        children=[
            dcc.Tab(label="📘 About / How to Interpret", value="about"),
            dcc.Tab(label="📈 Rolling EPA Trends", value="time_series"),
            dcc.Tab(label="🏈 Offense vs Defense Scatter", value="scatter"),
            dcc.Tab(label="💰 Vegas Lines & Totals", value="vegas"),
            dcc.Tab(label="⚔️ Matchup & Upset Analysis", value="matchup"),
            dcc.Tab(label="🔮 League-Wide Upset Watch", value="upset_watch"),
        ],
    ),

    # Dynamic (Week / Matchup) controls appear here only for certain tabs
    html.Div(id="week-matchup-selectors", style={"margin": "15px"}),

    # Body content for whichever tab is active
    html.Div(id="tab-content")
])


# =====================================================
# 3. CALLBACK: BUILD WEEK / MATCHUP CONTROLS PER TAB
# =====================================================

@app.callback(
    Output("week-matchup-selectors", "children"),
    Input("tabs", "value")
)
def render_week_matchup_selectors(active_tab):
    """
    Shows:
      - Week dropdown for 'matchup' and 'upset_watch' tabs
      - Matchup dropdown ONLY for 'matchup' tab.
    The dropdowns themselves are persisted so the last chosen values stick.
    """
    if active_tab not in ["matchup", "upset_watch"]:
        return ""

    children = [
        html.Label("Select Week:"),
        dcc.Dropdown(
            id="week-dropdown",
            options=[{"label": f"Week {w}", "value": w} for w in available_weeks],
            value=current_week,
            clearable=False,
            persistence=True,
            persistence_type="local",
            style={"width": "20%", "display": "inline-block", "marginRight": "15px"},
        ),
    ]

    if active_tab == "matchup":
        children.extend([
            html.Label("Select Game:", style={"marginRight": "10px"}),
            dcc.Dropdown(
                id="matchup-dropdown",
                options=matchup_dict.get(current_week, []),
                value=default_game,
                clearable=False,
                persistence=True,
                persistence_type="local",
                style={"width": "40%", "display": "inline-block"},
            ),
        ])
    else:
        # still return a matchup-dropdown id so downstream callback signatures are stable
        children.extend([
            dcc.Dropdown(
                id="matchup-dropdown",
                options=[],
                value=None,
                style={"display": "none"},
            )
        ])

    return html.Div(children)


@app.callback(
    Output("matchup-dropdown", "options"),
    Output("matchup-dropdown", "value"),
    Input("week-dropdown", "value")
)
def update_matchup_dropdown(selected_week):
    """
    Whenever week changes, refresh the available matchups and default matchup.
    """
    opts = matchup_dict.get(selected_week, [])
    val = opts[0]["value"] if opts else None
    return opts, val


# =====================================================
# 4. MAIN TAB RENDER CALLBACK
# =====================================================

@app.callback(
    Output("tab-content", "children"),
    Input("tabs", "value"),
    Input("metric-dropdown", "value"),
    Input("team-dropdown", "value"),
    Input("week-dropdown", "value"),
    Input("matchup-dropdown", "value"),
)
def render_tab_content(
    active_tab,
    metric_col,
    selected_teams,
    selected_week,
    selected_matchup
):
    """
    Renders the visible body for each tab.

    Tabs:
    - about
    - time_series
    - scatter
    - vegas
    - matchup
    - upset_watch
    """

    # Helper to avoid repeating code
    if df.empty:
        return html.Div("❌ No data loaded. Check your CSV file path / columns.")

    # Build offense/defense summary DataFrames
    off = df.groupby("team")[[
        "rolling_epa_per_pass_3wk",
        "rolling_epa_per_rush_3wk",
    ]].mean().reset_index()

    deff = df.groupby("team")[[
        "rolling_def_epa_per_pass_3wk",
        "rolling_def_epa_per_rush_3wk",
    ]].mean().reset_index()

    def val(team, frame, col):
        if team in frame["team"].values:
            return frame.loc[frame["team"] == team, col].values[0]
        return 0

    # =================================================
    # TAB: ABOUT
    # =================================================
    if active_tab == "about":
        return html.Div([
            html.H2("📘 How to Interpret This Dashboard", style={"textAlign": "center"}),

            html.H4("1️⃣ Rolling EPA Trends", style={"marginTop": "20px"}),
            html.P(
                "For any team(s) you pick, we plot their efficiency (EPA per play) "
                "as a rolling 3-week average. You can switch the metric to focus on "
                "offense, defense, pass, or rush. Higher offensive EPA is better. "
                "Lower defensive EPA is better."
            ),

            html.H4("2️⃣ Offense vs Defense Scatter"),
            html.P(
                "Each point is a team. X-axis is offensive EPA/play (higher = better offense). "
                "Y-axis is negative defensive EPA/play (so higher on the chart = better defense). "
                "Teams in the top-right quadrant are balanced: efficient offense and stingy defense."
            ),

            html.H4("3️⃣ Vegas Lines & Totals"),
            html.P(
                "We chart betting market expectations (spread and total) for each selected team "
                "across the season. Large negative spreads = heavily favored. Totals tell you if "
                "the market expects a shootout or a slog."
            ),

            html.H4("4️⃣ Matchup & Upset Analysis"),
            html.P(
                "Pick a single matchup. We compare BOTH directions for each game: "
                "Underdog Offense vs Favorite Defense, and Favorite Offense vs Underdog Defense. "
                "We quantify those mismatches in both pass and rush."
            ),
            html.P(
                "We then build a Composite Mismatch = (Underdog advantage - Favorite advantage). "
                "Positive composite means the underdog's strengths outweigh the favorite's strengths."
            ),
            html.P(
                "Finally we add spread context to get Upset Score and categorize it as High / Medium / Low."
            ),

            html.H4("5️⃣ League-Wide Upset Watch"),
            html.P(
                "Pick a week. We rank every game by Upset Score. "
                "If a game is High, the underdog isn't just decent — they're specifically built "
                "to attack the favorite, AND the favorite might not have a dominant counterpunch."
            ),

            html.H4("Key Ideas Behind the Model"),
            html.Ul([
                html.Li("EPA (Expected Points Added): how much each play changes expected points. "
                        "Higher EPA/play on offense = more efficient offense. "
                        "Lower EPA/play allowed on defense = stronger defense."),
                html.Li("Rolling 3-week averages: captures recent form / momentum, smooths noise."),
                html.Li("Two-way Mismatch: we check underdog's best path to score AND whether "
                        "the favorite can score freely in return."),
                html.Li("Composite Mismatch: (Under O vs Fav D) − (Fav O vs Under D). "
                        "If this is positive, the dog can trade punches or win style-on-style."),
                html.Li("Upset Potential Score: Composite Mismatch + scaled spread (0.02 * spread)."),
                html.Li("Home Field: we credit the home team ~+0.03 EPA in projected advantage (~2 pts)."),
            ]),

            html.H4("How To Use It"),
            html.P(
                "1. Go to Upset Watch → look for High/Medium.\n"
                "2. Jump to Matchup → confirm the dog has a real path (big passing mismatch, etc.).\n"
                "3. Check Composite Mismatch and Upset Score.\n"
                "4. Check confidence: lower confidence = more chaos = more upset juice."
            ),
        ], style={"width": "80%", "margin": "auto", "fontSize": "16px"})

    # =================================================
    # TAB: ROLLING EPA TRENDS
    # =================================================
    if active_tab == "time_series":
        fig = go.Figure()

        for team in selected_teams:
            tdf = df[df["team"] == team]
            if len(tdf) < 1:
                continue
            fig.add_trace(go.Scatter(
                x=tdf["week"],
                y=tdf[metric_col],
                mode="lines+markers",
                name=team,
                hovertemplate=(
                    f"{team}<br>"
                    "Week %{x}<br>"
                    "EPA: %{y:.3f}<extra></extra>"
                ),
            ))

        metric_label = [lab for lab, col in metric_options.items() if col == metric_col]
        metric_label = metric_label[0] if metric_label else metric_col

        fig.update_layout(
            title=f"{metric_label} – Rolling 3-Week Average",
            xaxis_title="Week",
            yaxis_title="EPA per Play (3-Week Avg)",
            template="plotly_white",
            hovermode="x unified",
            legend_title="Team",
        )

        return dcc.Graph(figure=fig)

    # =================================================
    # TAB: OFFENSE VS DEFENSE SCATTER
    # =================================================
    if active_tab == "scatter":
        scatter_df = df.groupby("team").agg({
            "rolling_epa_per_play_3wk": "mean",
            "rolling_def_epa_per_play_3wk": "mean"
        }).dropna()

        fig = go.Figure()
        for team in scatter_df.index:
            off_e = scatter_df.loc[team, "rolling_epa_per_play_3wk"]
            def_e = scatter_df.loc[team, "rolling_def_epa_per_play_3wk"]

            fig.add_trace(go.Scatter(
                x=[off_e],
                y=[-def_e],  # invert so "better D" plots higher
                mode="markers+text",
                text=team,
                textposition="top center",
                name=team,
                hovertemplate=(
                    f"{team}<br>"
                    "Off EPA/play: %{x:.3f}<br>"
                    "Def EPA/play allowed: %{customdata[0]:.3f}<extra></extra>"
                ),
                customdata=[[def_e]],
            ))

        fig.update_layout(
            title="Team Strength: Offense vs Defense (3-Week Rolling Averages)",
            xaxis_title="Offensive EPA/play (higher = better offense)",
            yaxis_title="Defensive EPA/play (lower allowed = better defense)",
            template="plotly_white",
            hovermode="closest",
            showlegend=False,
        )

        return dcc.Graph(figure=fig)

    # =================================================
    # TAB: VEGAS LINES & TOTALS
    # =================================================
    if active_tab == "vegas":
        if games.empty:
            return html.Div("⚠️ Vegas data not available.")

        fig = go.Figure()

        for team in selected_teams:
            tg = games[(games["home_team"] == team) | (games["away_team"] == team)]
            if tg.empty:
                continue

            # Spread trace
            fig.add_trace(go.Scatter(
                x=tg["week"],
                y=tg["spread_line"],
                mode="lines+markers",
                name=f"{team} Spread",
                hovertemplate=(
                    f"{team}<br>"
                    "Week %{x}<br>"
                    "Spread: %{y:.1f}<extra></extra>"
                ),
            ))

            # Total trace
            fig.add_trace(go.Scatter(
                x=tg["week"],
                y=tg["total_line"],
                mode="lines+markers",
                name=f"{team} Total",
                line=dict(dash="dot"),
                hovertemplate=(
                    f"{team}<br>"
                    "Week %{x}<br>"
                    "Total: %{y:.1f}<extra></extra>"
                ),
            ))

        fig.update_layout(
            title="Vegas Spreads & Totals by Week (Market Expectation)",
            xaxis_title="Week",
            yaxis_title="Line Value (Points)",
            template="plotly_white",
            hovermode="x unified",
        )

        return dcc.Graph(figure=fig)

    # =================================================
    # TAB: MATCHUP & UPSET ANALYSIS (SINGLE GAME, TWO-WAY)
    # =================================================
    if active_tab == "matchup":
        if not selected_week or not selected_matchup:
            return html.Div("⚠️ Pick a week and a game above.")

        away_team, home_team = selected_matchup.split("@")

        # ------------------------------
        # EPA Advantage bars (same as before)
        # ------------------------------
        matchup_rows = [
            {
                "type": "Pass",
                "matchup": f"{away_team} Off vs {home_team} Def",
                "delta": (
                    val(away_team, off, "rolling_epa_per_pass_3wk")
                    - val(home_team, deff, "rolling_def_epa_per_pass_3wk")
                ),
            },
            {
                "type": "Rush",
                "matchup": f"{away_team} Off vs {home_team} Def",
                "delta": (
                    val(away_team, off, "rolling_epa_per_rush_3wk")
                    - val(home_team, deff, "rolling_def_epa_per_rush_3wk")
                ),
            },
            {
                "type": "Pass",
                "matchup": f"{home_team} Off vs {away_team} Def",
                "delta": (
                    val(home_team, off, "rolling_epa_per_pass_3wk")
                    - val(away_team, deff, "rolling_def_epa_per_pass_3wk")
                ),
            },
            {
                "type": "Rush",
                "matchup": f"{home_team} Off vs {away_team} Def",
                "delta": (
                    val(home_team, off, "rolling_epa_per_rush_3wk")
                    - val(away_team, deff, "rolling_def_epa_per_rush_3wk")
                ),
            },
        ]
        matchup_df = pd.DataFrame(matchup_rows)
        matchup_df["color"] = matchup_df["delta"].apply(
            lambda x: "#2ECC71" if x > 0 else "#E74C3C"
        )

        fig_matchup = go.Figure(go.Bar(
            x=matchup_df["matchup"] + " – " + matchup_df["type"],
            y=matchup_df["delta"],
            marker_color=matchup_df["color"],
            hovertemplate="%{x}<br>EPA Advantage: %{y:.3f}<extra></extra>",
        ))
        fig_matchup.update_layout(
            title=f"Week {selected_week}: {away_team} @ {home_team} – Offense vs Defense EPA Advantage",
            xaxis_title="Matchup & Play Type",
            yaxis_title="EPA Advantage (Offense − Defense)",
            template="plotly_white",
            xaxis_tickangle=-25,
        )

        # ------------------------------
        # Projected edge / winner logic (same as before)
        # ------------------------------
        league_avg_off = df["rolling_epa_per_play_3wk"].mean()
        league_avg_def = df["rolling_def_epa_per_play_3wk"].mean()

        team_off_e = df.groupby("team")["rolling_epa_per_play_3wk"].mean()
        team_def_e = df.groupby("team")["rolling_def_epa_per_play_3wk"].mean()

        away_edge = (
            (team_off_e.get(away_team, 0) - team_def_e.get(home_team, 0))
            - (league_avg_off - league_avg_def)
        )
        home_edge = (
            (team_off_e.get(home_team, 0) - team_def_e.get(away_team, 0))
            - (league_avg_off - league_avg_def)
        )

        # Home field bump
        home_edge += 0.03

        if away_edge > home_edge:
            winner = away_team
            winner_color = "#2ECC71"
        elif home_edge > away_edge:
            winner = home_team
            winner_color = "#2ECC71"
        else:
            winner = "Even"
            winner_color = "#95A5A6"

        diff = abs(away_edge - home_edge)
        if diff >= 0.15:
            confidence = "High"
        elif diff >= 0.07:
            confidence = "Moderate"
        else:
            confidence = "Low"

        # ------------------------------
        # Get spread and figure out favorite / underdog
        # ------------------------------
        game_row = games[
            (games["week"] == selected_week)
            & (games["away_team"] == away_team)
            & (games["home_team"] == home_team)
        ]
        spread_val = game_row.iloc[0]["spread_line"] if not game_row.empty else None

        if spread_val is not None:
            # convention: positive spread for away means AWAY is underdog, negative means AWAY is favored
            underdog = away_team if spread_val > 0 else home_team
            favorite = home_team if underdog == away_team else away_team
        else:
            # fallback: projected edges
            underdog = home_team if home_edge < away_edge else away_team
            favorite = away_team if underdog == home_team else home_team

        # ------------------------------
        # TWO-WAY mismatch math
        # ------------------------------
        # Direction 1: underdog offense vs favorite defense
        und_off_pass = val(underdog, off, "rolling_epa_per_pass_3wk")
        fav_def_pass = val(favorite, deff, "rolling_def_epa_per_pass_3wk")
        und_off_rush = val(underdog, off, "rolling_epa_per_rush_3wk")
        fav_def_rush = val(favorite, deff, "rolling_def_epa_per_rush_3wk")

        off_pass_diff = und_off_pass - fav_def_pass
        off_rush_diff = und_off_rush - fav_def_rush

        # Direction 2: favorite offense vs underdog defense
        fav_off_pass = val(favorite, off, "rolling_epa_per_pass_3wk")
        und_def_pass = val(underdog, deff, "rolling_def_epa_per_pass_3wk")
        fav_off_rush = val(favorite, off, "rolling_epa_per_rush_3wk")
        und_def_rush = val(underdog, deff, "rolling_def_epa_per_rush_3wk")

        rev_pass_diff = fav_off_pass - und_def_pass
        rev_rush_diff = fav_off_rush - und_def_rush

        # Composite mismatch:
        # (underdog advantage) - (favorite advantage)
        composite_mismatch = (off_pass_diff + off_rush_diff) - (rev_pass_diff + rev_rush_diff)

        # Spread factor: turn points into "EPA-ish" weight
        spread_factor = (spread_val or 0) * 0.02

        upset_score = composite_mismatch + spread_factor

        if upset_score >= 0.15:
            upset_level = "High"
            upset_color = "#2ECC71"
        elif upset_score >= 0.07:
            upset_level = "Medium"
            upset_color = "#F1C40F"
        else:
            upset_level = "Low"
            upset_color = "#E74C3C"

        # readable blurbs
        underdog_blurb = (
            f"{underdog} Off vs {favorite} Def "
            f"(Pass {off_pass_diff:+.2f}, Rush {off_rush_diff:+.2f})"
        )
        favorite_blurb = (
            f"{favorite} Off vs {underdog} Def "
            f"(Pass {rev_pass_diff:+.2f}, Rush {rev_rush_diff:+.2f})"
        )

        # ------------------------------
        # Team ranks table
        # ------------------------------
        def rank_teams(col):
            return (
                df.groupby("team")[col]
                .mean()
                .rank(ascending=False, method="min")
                .to_dict()
            )

        ranks = {
            "off_pass": rank_teams("rolling_epa_per_pass_3wk"),
            "off_rush": rank_teams("rolling_epa_per_rush_3wk"),
            "def_pass": rank_teams("rolling_def_epa_per_pass_3wk"),
            "def_rush": rank_teams("rolling_def_epa_per_rush_3wk"),
        }

        def style_rank(r):
            if r <= 10:
                return {"color": "#2ECC71", "fontWeight": "bold"}  # top 10 unit
            elif r >= 23:
                return {"color": "#E74C3C", "fontWeight": "bold"}  # bottom 10 unit
            return {}

        ranks_table = html.Table([
            html.Thead(html.Tr([
                html.Th("Team"),
                html.Th("Off Pass Rank"),
                html.Th("Off Rush Rank"),
                html.Th("Def Pass Rank"),
                html.Th("Def Rush Rank"),
            ])),
            html.Tbody([
                html.Tr([
                    html.Td(team),
                    html.Td(int(ranks["off_pass"].get(team, 0)),
                            style=style_rank(ranks["off_pass"].get(team, 0))),
                    html.Td(int(ranks["off_rush"].get(team, 0)),
                            style=style_rank(ranks["off_rush"].get(team, 0))),
                    html.Td(int(ranks["def_pass"].get(team, 0)),
                            style=style_rank(ranks["def_pass"].get(team, 0))),
                    html.Td(int(ranks["def_rush"].get(team, 0)),
                            style=style_rank(ranks["def_rush"].get(team, 0))),
                ]) for team in [away_team, home_team]
            ])
        ], style={
            "width": "60%",
            "margin": "20px auto",
            "textAlign": "center",
            "fontSize": "16px",
        })

        # ------------------------------
        # Efficiency edge + projected advantage block
        # ------------------------------
        edge_block = html.Div([
            html.H4(
                "⚖️ Predicted Efficiency Edge (EPA Differential, Adj. for Home Field)",
                style={"textAlign": "center"}
            ),
            html.Table([
                html.Tr([
                    html.Td(
                        f"{away_team} Expected Edge:",
                        style={"fontWeight": "bold", "textAlign": "right", "paddingRight": "10px"},
                    ),
                    html.Td(
                        f"{away_edge:+.3f} EPA",
                        style={
                            "color": "#2ECC71" if away_edge > 0 else "#E74C3C",
                            "fontWeight": "bold",
                        },
                    ),
                ]),
                html.Tr([
                    html.Td(
                        f"{home_team} Expected Edge (+0.03 HFA):",
                        style={"fontWeight": "bold", "textAlign": "right", "paddingRight": "10px"},
                    ),
                    html.Td(
                        f"{home_edge:+.3f} EPA",
                        style={
                            "color": "#2ECC71" if home_edge > 0 else "#E74C3C",
                            "fontWeight": "bold",
                        },
                    ),
                ]),
            ], style={
                "margin": "auto",
                "borderCollapse": "collapse",
                "textAlign": "center",
                "fontSize": "16px",
            }),
            html.Br(),
            html.H4(
                f"🏆 Projected Advantage: {winner}",
                style={
                    "textAlign": "center",
                    "color": winner_color,
                    "fontWeight": "bold",
                    "fontSize": "20px",
                },
            ),
            html.P(
                f"Confidence level: {confidence}",
                style={
                    "textAlign": "center",
                    "fontStyle": "italic",
                    "marginTop": "-10px",
                },
            ),
        ])

        # ------------------------------
        # Upset / composite block
        # ------------------------------
        upset_block = html.Div([
            html.H4(
                f"🚨 Upset Potential: {upset_level}",
                style={
                    "textAlign": "center",
                    "color": upset_color,
                    "fontWeight": "bold",
                    "fontSize": "20px",
                },
            ),
            html.P(
                f"Composite Mismatch (Underdog minus Favorite): {composite_mismatch:+.3f}",
                style={"textAlign": "center", "fontWeight": "bold"}
            ),
            html.P(
                f"Upset Score (Composite + Spread Adj): {upset_score:+.3f}",
                style={"textAlign": "center", "fontWeight": "bold"}
            ),
            html.Br(),
            html.P(
                f"Underdog path: {underdog_blurb}",
                style={"textAlign": "center"}
            ),
            html.P(
                f"Favorite counter: {favorite_blurb}",
                style={"textAlign": "center"}
            ),
            html.P(
                "High means: underdog's offense cleanly attacks favorite's weak spots AND "
                "the favorite doesn't have an overwhelming counterpunch.",
                style={
                    "textAlign": "center",
                    "fontSize": "14px",
                    "color": "#555",
                },
            ),
        ])

        return html.Div([
            dcc.Graph(figure=fig_matchup),
            html.H3("📊 Team Efficiency Ranks (Season-to-Date)", style={
                "textAlign": "center",
                "marginTop": "10px"
            }),
            ranks_table,
            edge_block,
            html.Br(),
            upset_block,
        ])

    # =================================================
    # TAB: LEAGUE-WIDE UPSET WATCH (ALL GAMES IN A WEEK, TWO-WAY)
    # =================================================
    if active_tab == "upset_watch":
        if games.empty:
            return html.Div("⚠️ No schedule data available.")
        if not selected_week:
            return html.Div("⚠️ Pick a week above.")

        week_games = games[games["week"] == selected_week]
        if week_games.empty:
            return html.Div("⚠️ No games for that week.")

        rows = []
        for _, g in week_games.iterrows():
            away_t = g["away_team"]
            home_t = g["home_team"]
            spread_val = g.get("spread_line", None)

            # --- Figure out underdog/favorite using spread if available ---
            if spread_val is not None:
                # Common convention: positive spread for away means away is underdog
                underdog = away_t if spread_val > 0 else home_t
                favorite = home_t if underdog == away_t else away_t
            else:
                # fallback using projected edges + home field as in matchup tab
                league_avg_off = df["rolling_epa_per_play_3wk"].mean()
                league_avg_def = df["rolling_def_epa_per_play_3wk"].mean()
                team_off_e = df.groupby("team")["rolling_epa_per_play_3wk"].mean()
                team_def_e = df.groupby("team")["rolling_def_epa_per_play_3wk"].mean()

                away_edge_tmp = (
                    (team_off_e.get(away_t, 0) - team_def_e.get(home_t, 0))
                    - (league_avg_off - league_avg_def)
                )
                home_edge_tmp = (
                    (team_off_e.get(home_t, 0) - team_def_e.get(away_t, 0))
                    - (league_avg_off - league_avg_def)
                )
                home_edge_tmp += 0.03  # home field

                underdog = home_t if home_edge_tmp < away_edge_tmp else away_t
                favorite = away_t if underdog == home_t else home_t

            # --- Two-way mismatch math (same as matchup tab) ---

            # Direction 1: underdog offense vs favorite defense
            und_off_pass = val(underdog, off, "rolling_epa_per_pass_3wk")
            fav_def_pass = val(favorite, deff, "rolling_def_epa_per_pass_3wk")
            und_off_rush = val(underdog, off, "rolling_epa_per_rush_3wk")
            fav_def_rush = val(favorite, deff, "rolling_def_epa_per_rush_3wk")

            off_pass_diff = und_off_pass - fav_def_pass
            off_rush_diff = und_off_rush - fav_def_rush

            # Direction 2: favorite offense vs underdog defense
            fav_off_pass = val(favorite, off, "rolling_epa_per_pass_3wk")
            und_def_pass = val(underdog, deff, "rolling_def_epa_per_pass_3wk")
            fav_off_rush = val(favorite, off, "rolling_epa_per_rush_3wk")
            und_def_rush = val(underdog, deff, "rolling_def_epa_per_rush_3wk")

            rev_pass_diff = fav_off_pass - und_def_pass
            rev_rush_diff = fav_off_rush - und_def_rush

            # Composite mismatch:
            composite_mismatch = (off_pass_diff + off_rush_diff) - (rev_pass_diff + rev_rush_diff)

            # spread -> EPA-ish factor
            spread_factor = (spread_val or 0) * 0.02

            upset_score = composite_mismatch + spread_factor

            if upset_score >= 0.15:
                level = "High"
                level_color = "#2ECC71"
            elif upset_score >= 0.07:
                level = "Medium"
                level_color = "#F1C40F"
            else:
                level = "Low"
                level_color = "#E74C3C"

            rows.append({
                "Matchup": f"{away_t} @ {home_t}",
                "Underdog": underdog,
                "Favorite": favorite,
                "CompositeMismatch": composite_mismatch,
                "Upset Score": upset_score,
                "Level": level,
                "Color": level_color,
                "Reason": (
                    f"{underdog} Off vs {favorite} Def "
                    f"(Pass {off_pass_diff:+.2f}, Rush {off_rush_diff:+.2f}); "
                    f"{favorite} Off vs {underdog} Def "
                    f"(Pass {rev_pass_diff:+.2f}, Rush {rev_rush_diff:+.2f})"
                ),
            })

        week_df = pd.DataFrame(rows).sort_values("Upset Score", ascending=False)

        # Bar chart of upset scores by matchup
        fig_upset = go.Figure(go.Bar(
            x=week_df["Matchup"],
            y=week_df["Upset Score"],
            marker_color=week_df["Color"],
            hovertext=week_df["Reason"],
            hovertemplate=(
                "%{x}<br>"
                "Upset Score: %{y:.3f}<br>"
                "<extra></extra>"
            ),
        ))
        fig_upset.update_layout(
            title=f"Week {selected_week} – League-Wide Upset Potential (Two-Way Mismatch)",
            xaxis_title="Matchup",
            yaxis_title="Upset Potential Score",
            template="plotly_white",
            xaxis_tickangle=-25,
        )

        # Detail table
        detail_table = html.Table([
            html.Thead(html.Tr([
                html.Th("Matchup"),
                html.Th("Underdog"),
                html.Th("Favorite"),
                html.Th("Upset Score"),
                html.Th("Upset Level"),
                html.Th("Composite Mismatch"),
                html.Th("Key Mismatch Summary"),
            ])),
            html.Tbody([
                html.Tr([
                    html.Td(r["Matchup"]),
                    html.Td(r["Underdog"]),
                    html.Td(r["Favorite"]),
                    html.Td(f"{r['Upset Score']:.3f}"),
                    html.Td(
                        r["Level"],
                        style={"color": r["Color"], "fontWeight": "bold"}
                    ),
                    html.Td(f"{r['CompositeMismatch']:+.3f}"),
                    html.Td(r["Reason"]),
                ]) for _, r in week_df.iterrows()
            ])
        ], style={
            "width": "95%",
            "margin": "auto",
            "textAlign": "center",
            "fontSize": "14px",
            "border": "1px solid #ccc",
        })

        return html.Div([
            html.H3(
                f"🔮 Upset Watch – Week {selected_week}",
                style={"textAlign": "center", "marginBottom": "10px"},
            ),
            dcc.Graph(figure=fig_upset),
            html.H4(
                "Detailed Matchup Breakdown (Two-Way Mismatch, Spread-Adjusted)",
                style={"textAlign": "center", "marginTop": "20px"}
            ),
            detail_table,
        ])

    # Fallback
    return html.Div("⚙️ Unknown tab or missing inputs.")


# =====================================================
# 5. RUN IT
# =====================================================

if __name__ == "__main__":
    try:
        asyncio.run(app.run(debug=True))
    except RuntimeError:
        # for environments that already have an event loop
        loop = asyncio.get_event_loop()
        loop.create_task(app.run(debug=True))
