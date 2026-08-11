""" The Elo engine, the scoring rules, and the weekly ranking. """

import math

import pytest

from app import ranking, scoring
from util import Util


def game(**kw):
    base = {"game_id": "G", "team1": "AAA", "team2": "BBB", "result1": None,
            "my_prob1": 0.5, "elo_prob1": None, "playoff": 0, "gametime": "13:00"}
    base.update(kw)
    return base


class TestBrierScoring:
    def test_perfect_confident_forecast_scores_max(self):
        assert Util.score_probability(1.0, 1, 0) == 25.0

    def test_confidently_wrong_forecast_scores_minimum(self):
        assert Util.score_probability(1.0, 0, 0) == -75.0

    def test_coin_flip_is_worth_zero(self):
        assert Util.score_probability(0.5, 1, 0) == 0.0
        assert Util.score_probability(0.5, 0, 0) == 0.0

    def test_playoff_games_count_double(self):
        assert Util.score_probability(0.75, 1, 1) == 2 * Util.score_probability(0.75, 1, 0)

    def test_probability_is_rounded_to_two_places_before_scoring(self):
        # The game's rule scores the displayed percentage, not full float precision.
        assert Util.score_probability(0.7499, 1, 0) == Util.score_probability(0.75, 1, 0)

    def test_score_is_symmetric_between_the_two_teams(self):
        for p in (0.1, 0.35, 0.5, 0.62, 0.9):
            assert Util.score_probability(p, 1, 0) == pytest.approx(Util.score_probability(1 - p, 0, 0))


class TestRanking:
    def test_most_confident_game_gets_the_highest_rank(self):
        games = [game(game_id="a", my_prob1=0.55), game(game_id="b", my_prob1=0.95),
                 game(game_id="c", my_prob1=0.05)]
        ranks = ranking.rank_week(games, "my_prob1")
        assert ranks == {"b": 3, "c": 2, "a": 1}

    def test_confidence_is_distance_from_a_coin_flip_in_either_direction(self):
        assert ranking.confidence(0.9) == pytest.approx(0.9)
        assert ranking.confidence(0.1) == pytest.approx(0.9)

    def test_ranks_are_a_permutation_of_one_through_n(self):
        games = [game(game_id=str(i), my_prob1=0.5 + i / 100) for i in range(16)]
        ranks = ranking.rank_week(games, "my_prob1")
        assert sorted(ranks.values()) == list(range(1, 17))

    def test_games_without_a_probability_are_left_unranked(self):
        games = [game(game_id="a", my_prob1=0.8), game(game_id="b", my_prob1=None)]
        assert ranking.rank_week(games, "my_prob1") == {"a": 1}

    def test_ties_break_deterministically(self):
        games = [game(game_id="b", my_prob1=0.7, gametime="13:00"),
                 game(game_id="a", my_prob1=0.7, gametime="13:00")]
        assert ranking.rank_week(games, "my_prob1") == ranking.rank_week(list(reversed(games)), "my_prob1")

    def test_a_favourite_at_exactly_even_odds_picks_the_home_team(self):
        assert ranking.winner(game(my_prob1=0.5), "my_prob1") == "AAA"


class TestAnnotate:
    def test_blend_weight_of_one_is_pure_elo(self):
        out = ranking.annotate([game(my_prob1=0.8, elo_prob1=0.2)], 1.0)
        assert out[0]["combined_prob"] == pytest.approx(0.8)

    def test_blend_weight_of_zero_is_pure_vegas(self):
        out = ranking.annotate([game(my_prob1=0.8, elo_prob1=0.2)], 0.0)
        assert out[0]["combined_prob"] == pytest.approx(0.2)

    def test_combined_falls_back_to_elo_when_no_line_was_posted(self):
        out = ranking.annotate([game(my_prob1=0.8, elo_prob1=None)], 0.5)
        assert out[0]["combined_prob"] == pytest.approx(0.8)

    def test_source_games_are_not_modified(self):
        source = game(my_prob1=0.8, elo_prob1=0.2)
        ranking.annotate([source], 0.5)
        assert "combined_prob" not in source


class TestPoolScoring:
    def test_a_correct_pick_earns_its_confidence(self):
        games = [game(game_id="a", result1=1, my_prob1=0.9)]
        picks = {"a": {"team": "AAA", "confidence": 5}}
        assert scoring.pool_points_for_user(games, picks) == (5, 1)

    def test_a_wrong_pick_earns_nothing_but_costs_no_points(self):
        games = [game(game_id="a", result1=0, my_prob1=0.9)]
        picks = {"a": {"team": "AAA", "confidence": 5}}
        earned, _ = scoring.pool_points_for_user(games, picks)
        assert earned == 0

    def test_the_maximum_is_the_sum_of_one_through_n(self):
        games = [game(game_id=str(i), result1=1) for i in range(5)]
        assert scoring.pool_points_for_user(games, {})[1] == 15

    def test_skipping_a_game_still_counts_against_the_maximum(self):
        games = [game(game_id=str(i), result1=1) for i in range(3)]
        picks = {"0": {"team": "AAA", "confidence": 3}}
        assert scoring.pool_points_for_user(games, picks) == (3, 6)

    def test_a_pick_with_no_confidence_scores_nothing(self):
        games = [game(game_id="a", result1=1)]
        assert scoring.pool_points_for_user(games, {"a": {"team": "AAA", "confidence": None}}) == (0, 1)

    def test_a_tie_pays_nobody_but_its_points_stay_in_the_pot(self):
        # A tie is part of the slate everyone had to rank, so the points put on it are simply
        # lost - the same thing that happens in a real pool.
        games = [game(game_id="a", result1=0.5), game(game_id="b", result1=1)]
        picks = {"a": {"team": "AAA", "confidence": 2}, "b": {"team": "AAA", "confidence": 1}}
        assert scoring.pool_points_for_user(games, picks) == (1, 3)

    def test_an_empty_slate_has_no_pot(self):
        assert scoring.pool_points_for_user([], {}) == (0, 0)

    def test_only_final_games_count_as_the_slate(self):
        games = [game(game_id="a", result1=1), game(game_id="b", result1=None)]
        assert [g["game_id"] for g in games if scoring.is_final(g)] == ["a"]


class TestScorableGames:
    def test_a_tie_is_not_scorable(self):
        assert not scoring.is_scorable(game(result1=0.5))

    def test_an_unplayed_game_is_not_scorable(self):
        assert not scoring.is_scorable(game(result1=None))

    def test_a_decided_game_is_scorable(self):
        assert scoring.is_scorable(game(result1=1))
        assert scoring.is_scorable(game(result1=0))

    def test_the_winner_is_read_off_the_result(self):
        assert scoring.actual_winner(game(result1=1)) == "AAA"
        assert scoring.actual_winner(game(result1=0)) == "BBB"
        assert scoring.actual_winner(game(result1=0.5)) is None


class TestEloEngine:
    def test_every_game_gets_a_probability(self, model):
        assert all(g.get("my_prob1") is not None for g in model.games)

    def test_probabilities_are_valid(self, model):
        assert all(0.0 < g["my_prob1"] < 1.0 for g in model.games)

    def test_every_game_records_the_ratings_it_forecast_from(self, model):
        assert all(g.get("my_elo1") is not None and g.get("my_elo2") is not None for g in model.games)

    def test_games_are_processed_in_chronological_order(self, model):
        dates = [g["date"] for g in model.games]
        assert dates == sorted(dates)

    def test_ratings_stay_in_a_plausible_range(self, model):
        assert all(800 < elo < 2200 for elo in model.teams.values())

    def test_elo_is_roughly_zero_sum_around_the_league_average(self, model):
        recent = [g for g in model.games if g["season"] == 2025]
        teams = {g["team1"] for g in recent} | {g["team2"] for g in recent}
        mean = sum(model.teams[t] for t in teams) / len(teams)
        assert 1450 < mean < 1560

    def test_the_home_team_is_favoured_between_evenly_rated_teams(self, model):
        even = [g for g in model.games
                if abs(g["my_elo1"] - g["my_elo2"]) < 1 and g["neutral"] == 0]
        assert even, "expected at least one evenly matched home game in 100 years of football"
        assert all(g["my_prob1"] > 0.5 for g in even)

    def test_a_neutral_site_game_between_equals_is_a_coin_flip(self, model):
        neutral = [g for g in model.games
                   if g["neutral"] == 1 and abs(g["my_elo1"] - g["my_elo2"]) < 0.5]
        for g in neutral:
            assert g["my_prob1"] == pytest.approx(0.5, abs=0.01)

    def test_the_model_beats_a_coin_flip_over_the_modern_era(self, model):
        scored = [g for g in model.games if g["season"] >= 2021 and scoring.is_scorable(g)]
        correct = sum(1 for g in scored
                      if ranking.winner(g, "my_prob1") == scoring.actual_winner(g))
        assert correct / len(scored) > 0.6

    def test_replaying_with_the_same_parameters_is_deterministic(self):
        from app import db, engine

        params = dict(db.DEFAULT_PARAMS)
        first = [g["my_prob1"] for g in engine.get_model(params).games]
        engine.invalidate_cache()
        second = [g["my_prob1"] for g in engine.get_model(params).games]
        assert first == second

    def test_raising_home_field_advantage_raises_the_home_probability(self):
        # A single unplayed game isolates the effect: no result means no rating update, so the
        # only thing that differs between runs is the home-field term.
        assert _forecast_one(hfa=0.0) < _forecast_one(hfa=65.0) < _forecast_one(hfa=200.0)

    def test_home_field_advantage_does_not_apply_at_a_neutral_site(self):
        assert _forecast_one(hfa=0.0, neutral=1) == _forecast_one(hfa=200.0, neutral=1)

    def test_changing_a_parameter_invalidates_the_cached_replay(self):
        from app import db, engine

        base = dict(db.DEFAULT_PARAMS)
        first = engine.get_model({**base, "k": 20.0}).teams["SEA"]
        second = engine.get_model({**base, "k": 45.0}).teams["SEA"]
        assert first != second


def _forecast_one(hfa, neutral=0):
    """ Runs the model over one hypothetical unplayed game and returns the home win probability """
    import forecast

    previous = forecast.HFA
    try:
        forecast.HFA = hfa
        game = {"season": 2020, "neutral": neutral, "playoff": 0, "team1": "SEA", "team2": "NE",
                "score1": None, "score2": None, "result1": None}
        forecast.Forecast.forecast([game])
        return game["my_prob1"]
    finally:
        forecast.HFA = previous


class TestProbabilityMath:
    def test_the_elo_formula_matches_the_published_curve(self):
        # 538's documented anchor: a 100-point edge is about a 64% favourite.
        p = 1.0 / (math.pow(10.0, (-100 / 400.0)) + 1.0)
        assert p == pytest.approx(0.64, abs=0.01)
