from util import *
from forecast import *

# Read historical games (1920-2020, from FiveThirtyEight) plus recent games (2021-present,
# from nflverse - run scripts/update_recent_games.py to refresh)
games = Util.read_games("data/nfl_games.csv") + Util.read_games("data/nfl_games_recent.csv")

# Forecast every game
Forecast.forecast(games)

# Evaluate our forecasts against Elo
Util.evaluate_forecasts(games)
