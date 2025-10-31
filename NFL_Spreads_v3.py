import requests
import pandas as pd
from datetime import datetime, timezone

# === Load API key ===
with open("api_key.txt", "r") as f:
    API_KEY = f.read().strip()

# === Define endpoint ===
url = f"https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds/?apiKey={API_KEY}&regions=us&markets=h2h,spreads,totals&oddsFormat=american"

# === Get data ===
response = requests.get(url)
data = response.json()

# === Extract current week games (within next 7 days) ===
current_week_games = []
today = datetime.now(timezone.utc)

for game in data:
    commence_time = datetime.fromisoformat(game["commence_time"].replace("Z", "+00:00"))
    # Filter for games happening within ~7 days
    if 0 <= (commence_time - today).days <= 7:
        current_week_games.append(game)

# === Build DataFrame ===
rows = []
for game in current_week_games:
    home_team = game["home_team"]
    away_team = game["away_team"]
    commence_time = game["commence_time"]

    # Default odds
    home_ml, away_ml, spread, total_points = None, None, None, None

    for bookmaker in game.get("bookmakers", []):
        if bookmaker["key"] in ["fanduel", "draftkings", "betmgm", "caesars"]:
            for market in bookmaker.get("markets", []):
                if market["key"] == "h2h":
                    for outcome in market["outcomes"]:
                        if outcome["name"] == home_team:
                            home_ml = outcome["price"]
                        elif outcome["name"] == away_team:
                            away_ml = outcome["price"]
                elif market["key"] == "spreads":
                    for outcome in market["outcomes"]:
                        if outcome["name"] == home_team:
                            spread = outcome["point"]
                elif market["key"] == "totals":
                    total_points = market["outcomes"][0]["point"]

    rows.append({
        "Game Time (UTC)": commence_time,
        "Home Team": home_team,
        "Away Team": away_team,
        "Moneyline (Home)": home_ml,
        "Moneyline (Away)": away_ml,
        "Point Spread": spread,
        "Total Points": total_points
    })

df = pd.DataFrame(rows)

# === Normalize column names ===
df.columns = [c.lower().strip() for c in df.columns]

# === Determine columns dynamically ===
home_ml_col = next((c for c in df.columns if "home" in c and "money" in c), None)
away_ml_col = next((c for c in df.columns if "away" in c and "money" in c), None)

# === Correct implied probability calculation ===
def implied_probability(odds):
    if pd.isna(odds):
        return None
    elif odds < 0:
        return abs(odds) / (abs(odds) + 100)
    else:
        return 100 / (odds + 100)

df["implied_prob_home"] = df[home_ml_col].apply(implied_probability)
df["implied_prob_away"] = df[away_ml_col].apply(implied_probability)

# === Calculate total and no-vig probabilities ===
df["total_implied_prob"] = df["implied_prob_home"] + df["implied_prob_away"]
df["no_vig_home"] = df["implied_prob_home"] / df["total_implied_prob"]
df["no_vig_away"] = df["implied_prob_away"] / df["total_implied_prob"]

# === Determine favored team ===
def determine_favorite(row):
    if pd.notnull(row["point spread"]):
        if row["point spread"] < 0:
            return row["home team"]
        elif row["point spread"] > 0:
            return row["away team"]
    elif pd.notnull(row[home_ml_col]) and pd.notnull(row[away_ml_col]):
        if row[home_ml_col] < row[away_ml_col]:
            return row["home team"]
        elif row[away_ml_col] < row[home_ml_col]:
            return row["away team"]
    return "Even"

df["Favored Team"] = df.apply(determine_favorite, axis=1)

# === Add ranking based on spread ===
df["Spread Rank"] = df["point spread"].abs().rank(method="dense", ascending=False).astype(int)

# === Sort by highest spread (largest rank) ===
df = df.sort_values(by="Spread Rank", ascending=True)

# === Save to Excel ===
output_file = "nfl_odds_current_week.xlsx"
df.to_excel(output_file, index=False)

print(f"✅ Excel file '{output_file}' created successfully.")
print("✅ Columns included:", df.columns.tolist())
print(df[["home team", "away team", "implied_prob_home", "implied_prob_away", "total_implied_prob"]])
