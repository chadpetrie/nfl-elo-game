""" Two different ways to score a season, kept deliberately separate.

Brier points are the scoring rule from the original FiveThirtyEight game: a forecast is a
probability, and it is rewarded for being both correct and confident. Only a probability can
be scored this way, so it applies to the models, not to a user's pick.

Confidence-pool points are the office-pool rule the "Your pick" column implies: each game in a
week gets a distinct rank from 1..N, and you collect that rank as points when you pick the
winner. A model plays this game by ranking the week by how confident it is, which makes model
and human directly comparable - the question the app is really trying to answer.
"""

from .paths import ROOT  # noqa: F401  (imported first: puts the repo root on sys.path)

from util import Util  # noqa: E402

from . import ranking  # noqa: E402

FIRST_VEGAS_SEASON = 2021  # before this, elo_prob1 holds 538's own Elo forecast, not a market line


def brier_points(prob, result, playoff):
    return Util.score_probability(prob, result, playoff)


def is_scorable(game):
    """ A game can be scored only if it was played and did not end in a tie """
    return game["result1"] is not None and game["result1"] != 0.5


def is_final(game):
    """ A game that has been played, including one that ended in a tie.

    The pool ranks over final games rather than scorable ones so that a tie behaves the way it
    does in a real pool: it is part of the slate everyone had to rank, and the points anyone put
    on it are simply lost. Excluding it instead would renumber the ranks and quietly disagree
    with the confidence values shown on the week screen.
    """
    return game["result1"] is not None


def actual_winner(game):
    if game["result1"] == 1:
        return game["team1"]
    if game["result1"] == 0:
        return game["team2"]
    return None


def week_pot(final_games):
    """ Every source ranks the same slate, so they all play for N + (N-1) + ... + 1 """
    n = len(final_games)
    return n * (n + 1) // 2


def pool_points_for_week(final_games, prob_field):
    """ Points a model scores in a confidence pool for one week, plus the pot it played for.

    Expects games already run through ranking.annotate.
    """
    ranks = ranking.rank_week(final_games, prob_field)

    earned = 0
    for g in final_games:
        rank = ranks.get(g["game_id"])
        if rank is not None and winner_matches(g, prob_field):
            earned += rank
    return earned, week_pot(final_games)


def winner_matches(game, prob_field):
    return ranking.winner(game, prob_field) == actual_winner(game)


def pool_points_for_user(final_games, picks):
    """ Points a user's saved picks score in a confidence pool for one week.

    The user's own confidence numbers are used as entered. Unpicked games score nothing but
    still count toward the pot, so skipping games is not free.
    """
    if not final_games:
        return 0, 0

    earned = 0
    for g in final_games:
        pick = picks.get(g["game_id"])
        if not pick or pick.get("confidence") is None:
            continue
        if pick["team"] == actual_winner(g):
            earned += pick["confidence"]
    return earned, week_pot(final_games)
