""" Total-points prediction methods: each one must be computed only from games strictly before
the one being predicted, the same walk-forward discipline as scoring.py and the backtest. """

from app import totals


def game(game_id, team1, team2, date, season, score1=None, score2=None, total_line=None, gametime="13:00"):
    return {"game_id": game_id, "team1": team1, "team2": team2, "date": date, "season": season,
            "score1": score1, "score2": score2, "total_line": total_line, "gametime": gametime}


class TestTeamHistory:
    def test_only_played_games_are_recorded(self):
        games = [game("a", "AAA", "BBB", "2024-09-01", 2024, 20, 10),
                 game("b", "AAA", "CCC", "2024-09-08", 2024)]  # not yet played
        history = totals.team_history(games)
        assert len(history["AAA"]) == 1

    def test_both_sides_of_a_game_are_recorded(self):
        history = totals.team_history([game("a", "AAA", "BBB", "2024-09-01", 2024, 20, 10)])
        assert history["AAA"][0] == {"date": "2024-09-01", "season": 2024, "pf": 20, "pa": 10}
        assert history["BBB"][0] == {"date": "2024-09-01", "season": 2024, "pf": 10, "pa": 20}

    def test_history_is_chronological_regardless_of_input_order(self):
        games = [game("b", "AAA", "CCC", "2024-09-08", 2024, 14, 14),
                 game("a", "AAA", "BBB", "2024-09-01", 2024, 20, 10)]
        history = totals.team_history(games)
        assert [e["date"] for e in history["AAA"]] == ["2024-09-01", "2024-09-08"]


class TestPredict:
    def test_the_vegas_line_passes_through_untouched(self):
        g = game("a", "AAA", "BBB", "2024-09-08", 2024, total_line=45.5)
        assert totals.predict(g, {}, [g])["vegas"] == 45.5

    def test_no_vegas_line_is_reported_as_unknown(self):
        g = game("a", "AAA", "BBB", "2024-09-08", 2024)
        assert totals.predict(g, {}, [g])["vegas"] is None

    def test_season_average_blends_each_teams_scoring_with_the_others_defense(self):
        history_games = [
            game("1", "AAA", "XXX", "2024-09-01", 2024, 30, 10),  # AAA so far: pf 30, pa 10
            game("2", "BBB", "YYY", "2024-09-01", 2024, 20, 20),  # BBB so far: pf 20, pa 20
        ]
        target = game("3", "AAA", "BBB", "2024-09-08", 2024)
        history = totals.team_history(history_games)
        # AAA projected = (30 + 20) / 2 = 25; BBB projected = (20 + 10) / 2 = 15; total = 40
        assert totals.predict(target, history, history_games + [target])["season"] == 40.0

    def test_a_game_on_the_same_date_is_not_leaked_into_its_own_average(self):
        already_final = game("1", "AAA", "XXX", "2024-09-08", 2024, 50, 0)
        target = game("2", "AAA", "BBB", "2024-09-08", 2024)
        history = totals.team_history([already_final])
        assert totals.predict(target, history, [already_final, target])["season"] is None

    def test_recent_form_only_looks_at_the_last_n_games(self):
        history_games = [game(str(i), "AAA", "XXX", "2024-09-0%d" % i, 2024, 10 * i, 0)
                          for i in range(1, 6)]  # AAA scores 10,20,30,40,50 across 5 games
        history = totals.team_history(history_games)
        assert totals._recent_form(history, "AAA", "2024-10-01") == (35.0, 0.0)  # last 4: 20-50

    def test_season_average_falls_back_to_last_season_before_this_one_has_games(self):
        history = totals.team_history([game("1", "AAA", "XXX", "2023-12-01", 2023, 24, 17)])
        assert totals._season_average(history, "AAA", "2024-09-08", 2024) == (24.0, 17.0)

    def test_league_average_falls_back_to_last_season_before_this_one_has_games(self):
        last_season = [game("1", "AAA", "BBB", "2023-09-01", 2023, 20, 20)]
        assert totals._league_average_total(last_season, "2024-09-08", 2024) == 40.0

    def test_consensus_averages_whatever_methods_produced_a_number(self):
        g = game("a", "AAA", "BBB", "2024-09-08", 2024, total_line=40.0)
        # season/recent/league are all None here (no history at all) - only vegas is known.
        assert totals.predict(g, {}, [g])["consensus"] == 40.0

    def test_consensus_is_none_when_nothing_is_known(self):
        g = game("a", "AAA", "BBB", "2024-09-08", 2024)
        assert totals.predict(g, {}, [g])["consensus"] is None
