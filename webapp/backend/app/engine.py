import threading

from .paths import DATA_DIR  # noqa: F401  (imported first: puts the repo root on sys.path)

import forecast  # noqa: E402  (repo-root module, reachable via paths)
from util import Util  # noqa: E402

_lock = threading.RLock()
_raw_games = None
_cache_key = None
_cache = None


class _Model:
    """ One fully-forecast view of history, plus the indexes the API reads off it """

    def __init__(self, games, teams):
        self.games = games
        self.teams = teams
        self.by_season_week = {}
        self.week_types = {}
        self.by_id = {}
        for g in games:
            if g.get("game_id"):
                self.by_id[g["game_id"]] = g
            week = g.get("week")
            if not week:
                continue
            key = (g["season"], int(week))
            self.by_season_week.setdefault(key, []).append(g)
            self.week_types[key] = g.get("game_type", "REG")
        self.seasons = sorted({season for season, _ in self.by_season_week}, reverse=True)

    def weeks_for(self, season):
        return sorted(w for s, w in self.by_season_week if s == season)

    def week_games(self, season, week):
        return self.by_season_week.get((season, int(week)), [])


def _load_raw_games():
    global _raw_games
    if _raw_games is None:
        _raw_games = Util.read_games(str(DATA_DIR / "nfl_games.csv")) + \
            Util.read_games(str(DATA_DIR / "nfl_games_recent.csv"))
    return _raw_games


def invalidate_cache():
    global _cache_key, _cache
    with _lock:
        _cache_key = None
        _cache = None


def get_model(params):
    """ Returns a _Model with my_prob1 recomputed for the given params.

    forecast's tuning knobs are module-level globals, so the whole replay is held under the lock
    to keep a concurrent request from reading ratings built with someone else's parameters.
    """
    global _cache_key, _cache
    key = (params["hfa"], params["k"], params["revert"], params["mov_base"])
    with _lock:
        if key != _cache_key or _cache is None:
            games = _load_raw_games()
            forecast.HFA = params["hfa"]
            forecast.K = params["k"]
            forecast.REVERT = params["revert"]
            forecast.MOV_BASE = params["mov_base"]
            teams = forecast.Forecast.forecast(games)
            _cache = _Model(games, {name: t["elo"] for name, t in teams.items()})
            _cache_key = key
        return _cache


def get_games(params):
    return get_model(params).games
