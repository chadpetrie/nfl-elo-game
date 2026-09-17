"""
Refreshes data/nfl_games_recent.csv (2021-present) from nflverse's community-maintained
game data. Replaces FiveThirtyEight's own nfl-api, which stopped being updated in mid-2023.

FiveThirtyEight's Elo forecasts don't exist for these games, so elo_prob1 here is instead
a devigged win probability implied by the closing Vegas moneylines - the "expert" forecast
the game is meant to be judged against for 2021 onward. Pre-2021 games in data/nfl_games.csv
are untouched and keep 538's original elo_prob1.

Run this periodically during the season to pull the latest results and lines:
    python scripts/update_recent_games.py
"""

import csv
import sys
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

SOURCE_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
OUTPUT_PATH = "data/nfl_games_recent.csv"
FIRST_SEASON = 2021  # last season already present in data/nfl_games.csv is 2020

FIELDNAMES = ["date", "season", "neutral", "playoff", "team1", "team2",
              "elo1", "elo2", "elo_prob1", "score1", "score2", "result1",
              "week", "game_type", "gametime", "game_id", "total_line"]

# nflverse uses each team's current city; the legacy file keeps one fixed code per
# franchise across relocations (Rams stayed LAR through St. Louis, Chargers stayed LAC
# through San Diego, and per the existing 2020 rows, the Raiders are still coded OAK
# even for their move to Las Vegas). Only these three need remapping.
TEAM_CODE_MAP = {"LA": "LAR", "WAS": "WSH", "LV": "OAK"}


def american_to_implied_prob(moneyline):
    ml = float(moneyline)
    if ml > 0:
        return 100.0 / (ml + 100.0)
    return -ml / (-ml + 100.0)


def devig_home_prob(home_moneyline, away_moneyline):
    home_raw = american_to_implied_prob(home_moneyline)
    away_raw = american_to_implied_prob(away_moneyline)
    return home_raw / (home_raw + away_raw)


def fetch_source_rows():
    try:
        with urlopen(SOURCE_URL) as response:
            text = response.read().decode("utf-8")
    except (URLError, HTTPError) as e:
        sys.exit(
            "Failed to download nflverse game data from %s (%s). "
            "Check your network connection or whether the source has moved." % (SOURCE_URL, e)
        )
    return list(csv.DictReader(text.splitlines()))


def transform(row):
    home = TEAM_CODE_MAP.get(row["home_team"], row["home_team"])
    away = TEAM_CODE_MAP.get(row["away_team"], row["away_team"])

    result1 = ""
    if row["home_score"] != "" and row["away_score"] != "":
        home_score, away_score = int(row["home_score"]), int(row["away_score"])
        result1 = 1 if home_score > away_score else (0 if away_score > home_score else 0.5)

    elo_prob1 = ""
    if row["home_moneyline"] != "" and row["away_moneyline"] != "":
        elo_prob1 = round(devig_home_prob(row["home_moneyline"], row["away_moneyline"]), 6)

    return {
        "date": row["gameday"],
        "season": row["season"],
        "neutral": 1 if row["location"] == "Neutral" else 0,
        "playoff": 0 if row["game_type"] == "REG" else 1,
        "team1": home,
        "team2": away,
        "elo1": "",
        "elo2": "",
        "elo_prob1": elo_prob1,
        "score1": row["home_score"],
        "score2": row["away_score"],
        "result1": result1,
        "week": row["week"],
        "game_type": row["game_type"],
        "gametime": row["gametime"],
        "game_id": row["game_id"],
        "total_line": row.get("total_line", ""),
    }


def main():
    source_rows = fetch_source_rows()
    recent_rows = [transform(r) for r in source_rows if int(r["season"]) >= FIRST_SEASON]

    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(recent_rows)

    seasons = sorted(set(r["season"] for r in recent_rows), key=int)
    print("Wrote %d games (seasons %s-%s) to %s" % (
        len(recent_rows), seasons[0], seasons[-1], OUTPUT_PATH))


if __name__ == "__main__":
    main()
