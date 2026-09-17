""" Total-points prediction methods for a single game.

Every method here is computed only from games that happened strictly before the game being
predicted - the same walk-forward discipline scoring.py and scripts/backtest.py use elsewhere,
so a "prediction" here can never have quietly seen the answer.

Checked against 2010+ history before writing this: Elo's win-probability confidence has
essentially no correlation with how many total points get scored (r = 0.01) - a blowout doesn't
run notably higher or lower than a coin-flip game. So there's no honest "Elo-implied total"
method here; Elo tells you who wins and by roughly how much, not how many points get scored.
"""

RECENT_FORM_GAMES = 4


def team_history(games):
    """ Every team's chronological points-for/points-against record, keyed by team. """
    history = {}
    ordered = sorted(
        (g for g in games if g["score1"] is not None and g["score2"] is not None),
        key=lambda g: (g["date"], g.get("gametime") or "", g.get("game_id") or ""),
    )
    for g in ordered:
        history.setdefault(g["team1"], []).append(
            {"date": g["date"], "season": g["season"], "pf": g["score1"], "pa": g["score2"]})
        history.setdefault(g["team2"], []).append(
            {"date": g["date"], "season": g["season"], "pf": g["score2"], "pa": g["score1"]})
    return history


def _average(entries):
    if not entries:
        return None
    return sum(e["pf"] for e in entries) / len(entries), sum(e["pa"] for e in entries) / len(entries)


def _season_average(history, team, date, season):
    """ A team's scoring average this season before this date, falling back to last season's
    full average if the season hasn't produced enough games of its own yet (e.g. week 1). """
    this_season = [e for e in history.get(team, []) if e["date"] < date and e["season"] == season]
    if this_season:
        return _average(this_season)
    return _average([e for e in history.get(team, []) if e["season"] == season - 1])


def _recent_form(history, team, date, n=RECENT_FORM_GAMES):
    prior = [e for e in history.get(team, []) if e["date"] < date]
    return _average(prior[-n:])


def _league_average_total(games, date, season):
    """ Average combined score across the season so far, falling back to all of last season if
    this one hasn't been played into yet. """
    this_season = [g["score1"] + g["score2"] for g in games
                   if g["season"] == season and g["date"] < date and g["score1"] is not None]
    if this_season:
        return sum(this_season) / len(this_season)
    last_season = [g["score1"] + g["score2"] for g in games
                    if g["season"] == season - 1 and g["score1"] is not None]
    return sum(last_season) / len(last_season) if last_season else None


def _projected_total(team1_stats, team2_stats):
    """ Each team's own scoring average blended with the other's scoring-allowed average,
    the standard simple way to turn two teams' averages into a projection for this matchup. """
    if team1_stats is None or team2_stats is None:
        return None
    t1_scored, t1_allowed = team1_stats
    t2_scored, t2_allowed = team2_stats
    home_projected = (t1_scored + t2_allowed) / 2
    away_projected = (t2_scored + t1_allowed) / 2
    return home_projected + away_projected


def predict(game, history, all_games):
    """ {method: predicted total or None} for one game, plus a "consensus" average of whichever
    methods actually produced a number. """
    team1, team2, date, season = game["team1"], game["team2"], game["date"], game["season"]

    methods = {
        "vegas": game.get("total_line"),
        "season": _projected_total(
            _season_average(history, team1, date, season), _season_average(history, team2, date, season)),
        "recent": _projected_total(_recent_form(history, team1, date), _recent_form(history, team2, date)),
        "league": _league_average_total(all_games, date, season),
    }
    methods = {k: round(v, 1) if v is not None else None for k, v in methods.items()}

    known = [v for v in methods.values() if v is not None]
    methods["consensus"] = round(sum(known) / len(known), 1) if known else None
    return methods
