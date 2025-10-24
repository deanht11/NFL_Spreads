import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
import pytz
import os

# --------------------------------------------
# CONFIGURATION
# --------------------------------------------
API_KEY_FILE = "API_Key.txt"  # file containing your API key (one line)
SPORT = "americanfootball_nfl"
REGION = "us"
MARKETS = "h2h,spreads,totals"
TIMEZONE = "America/New_York"  # local timezone for output
OUTPUT_FILE = "nfl_odds.xlsx"

# NFL 2025 season start (Thursday after Labor Day)
SEASON_START = datetime(2025, 9, 4, tzinfo=timezone.utc)
# --------------------------------------------


def load_api_key(file_path: str) -> str:
    """Loads The Odds API key from a local text file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(
            f"❌ API key file not found: {file_path}\n"
            f"Please create a file named '{file_path}' containing your API key on the first line."
        )
    with open(file_path, "r") as f:
        key = f.readline().strip()
    if not key:
        raise ValueError("❌ API key file is empty.")
    return key


def get_current_week_bounds():
    """Return start and end datetimes (UTC) for the current NFL week."""
    now = datetime.now(timezone.utc)
    weeks_since_start = int((now - SEASON_START).days // 7)
    current_week_start = SEASON_START + timedelta(weeks=weeks_since_start)
    current_week_end = current_week_start + timedelta(days=7)
    return current_week_start, current_week_end, weeks_since_start + 1


def fetch_odds(api_key):
    """Fetch odds data from The Odds API."""
    url = (
        f"https://api.the-odds-api.com/v4/sports/{SPORT}/odds/"
        f"?regions={REGION}&markets={MARKETS}&apiKey={api_key}"
    )
    r = requests.get(url)
    r.raise_for_status()
    return r.json()


def parse_odds(data, week_start, week_end):
    """Parse and filter the odds JSON into a clean list of games."""
    games = []
    for game in data:
        home_team = game.get("home_team")
        away_team = game.get("away_team")
        commence_time = game.get("commence_time")
        commence_dt = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))

        # Filter only current-week games
        if not (week_start <= commence_dt < week_end):
            continue

        bookmaker = game["bookmakers"][0] if game.get("bookmakers") else None
        if not bookmaker:
            continue

        odds = {"home_ml": None, "away_ml": None, "spread": None, "total": None}
        for market in bookmaker.get("markets", []):
            if market["key"] == "h2h":
                for o in market["outcomes"]:
                    if o["name"] == home_team:
                        odds["home_ml"] = o["price"]
                    elif o["name"] == away_team:
                        odds["away_ml"] = o["price"]
            elif market["key"] == "spreads":
                for o in market["outcomes"]:
                    if o["name"] == home_team:
                        odds["spread"] = o["point"]
            elif market["key"] == "totals":
                for o in market["outcomes"]:
                    if o["name"] == "Over":
                        odds["total"] = o["point"]

        # Convert kickoff to local time
        local_tz = pytz.timezone(TIMEZONE)
        local_time = commence_dt.astimezone(local_tz).strftime("%Y-%m-%d %I:%M %p %Z")

        games.append({
            "Kickoff (Local)": local_time,
            "Away Team": away_team,
            "Home Team": home_team,
            "Point Spread": odds["spread"],
            "Total Points": odds["total"],
            "Moneyline Away": odds["away_ml"],
            "Moneyline Home": odds["home_ml"],
            "Bookmaker": bookmaker["title"]
        })
    return games


def add_favored_team(df):
    """Add a Favored Team column based on spread or moneyline."""
    def determine_favorite(row):
        # Prefer spread if available
        if pd.notnull(row["Point Spread"]):
            if row["Point Spread"] < 0:
                return row["Home Team"]
            elif row["Point Spread"] > 0:
                return row["Away Team"]
        # Fallback to moneyline
        if pd.notnull(row["Moneyline Home"]) and pd.notnull(row["Moneyline Away"]):
            if row["Moneyline Home"] < row["Moneyline Away"]:
                return row["Home Team"]
            elif row["Moneyline Away"] < row["Moneyline Home"]:
                return row["Away Team"]
        return "Even"
    df["Favored Team"] = df.apply(determine_favorite, axis=1)
    return df


def main():
    api_key = load_api_key(API_KEY_FILE)
    week_start, week_end, week_num = get_current_week_bounds()
    print(f"📅 Pulling NFL Week {week_num} games "
          f"({week_start.date()} → {week_end.date()})")

    data = fetch_odds(api_key)
    games = parse_odds(data, week_start, week_end)

    if not games:
        print("No upcoming games found for this week.")
        return

    df = pd.DataFrame(games)
    df.sort_values("Kickoff (Local)", inplace=True)
    df = add_favored_team(df)
    df.to_excel(OUTPUT_FILE, index=False)
    print(f"✅ Saved {len(df)} Week {week_num} games to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
