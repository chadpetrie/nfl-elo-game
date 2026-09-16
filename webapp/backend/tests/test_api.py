""" The HTTP surface: contract, validation, and the things a user can do to it by accident. """

import pytest

SEASON, WEEK = 2025, 1


@pytest.fixture
def week_games(client):
    return client.get(f"/api/games?season={SEASON}&week={WEEK}").json()["games"]


class TestSeasonsAndWeeks:
    def test_seasons_are_listed_newest_first(self, client):
        seasons = client.get("/api/seasons").json()
        assert seasons == sorted(seasons, reverse=True)
        assert 2025 in seasons

    def test_a_full_season_has_eighteen_weeks_plus_four_playoff_rounds(self, client):
        weeks = client.get(f"/api/weeks?season={SEASON}").json()
        assert [w["week"] for w in weeks] == list(range(1, 23))

    def test_playoff_rounds_are_labelled_by_name(self, client):
        labels = {w["week"]: w["label"] for w in client.get(f"/api/weeks?season={SEASON}").json()}
        assert labels[1] == "Week 1"
        assert labels[19] == "Wild Card"
        assert labels[22] == "Super Bowl"

    def test_an_unknown_season_is_a_404_not_an_empty_list(self, client):
        assert client.get("/api/weeks?season=1873").status_code == 404

    def test_a_non_numeric_season_is_rejected(self, client):
        assert client.get("/api/weeks?season=nonsense").status_code == 422

    def test_exactly_one_week_is_flagged_current(self, client):
        weeks = client.get(f"/api/weeks?season={SEASON}").json()
        assert sum(1 for w in weeks if w["current"]) == 1

    def test_a_fully_played_season_treats_its_last_week_as_current(self, client):
        # SEASON (2025) is complete, so there's no "week you still need to pick" - the last one
        # played is the sane fallback rather than always snapping back to Week 1.
        weeks = client.get(f"/api/weeks?season={SEASON}").json()
        assert next(w for w in weeks if w["current"])["week"] == weeks[-1]["week"]

    def test_current_week_is_the_first_one_with_an_unplayed_game(self, client):
        # Uses whatever the newest season actually is instead of a hardcoded year, so this stays
        # correct as more of that season gets played and the data file is refreshed.
        newest = max(client.get("/api/seasons").json())
        weeks = client.get(f"/api/weeks?season={newest}").json()

        def has_unplayed(week):
            games = client.get(f"/api/games?season={newest}&week={week}").json()["games"]
            return any(g["result1"] is None for g in games)

        expected = next((w["week"] for w in weeks if has_unplayed(w["week"])), weeks[-1]["week"])
        assert next(w for w in weeks if w["current"])["week"] == expected


class TestGames:
    def test_a_regular_season_week_has_the_expected_shape(self, week_games):
        assert len(week_games) == 16
        g = week_games[0]
        for field in ("game_id", "team1", "team2", "elo_prob", "vegas_prob", "combined_prob",
                      "elo_rank", "vegas_rank", "combined_rank", "elo1", "elo2"):
            assert field in g

    def test_games_come_back_in_kickoff_order(self, week_games):
        keys = [(g["date"], g["gametime"] or "") for g in week_games]
        assert keys == sorted(keys)

    def test_every_game_is_ranked_exactly_once(self, week_games):
        for source in ("elo", "vegas", "combined"):
            ranks = sorted(g[f"{source}_rank"] for g in week_games if g[f"{source}_rank"] is not None)
            assert ranks == list(range(1, len(ranks) + 1))

    def test_the_pick_always_agrees_with_the_probability(self, week_games):
        for g in week_games:
            for source in ("elo", "vegas", "combined"):
                prob, pick = g[f"{source}_prob"], g[f"{source}_pick"]
                if prob is None:
                    continue
                assert pick == (g["team1"] if prob >= 0.5 else g["team2"])

    def test_the_week_summary_counts_a_finished_week_correctly(self, client):
        summary = client.get(f"/api/games?season={SEASON}&week={WEEK}").json()["summary"]
        assert summary["played"] == summary["total"] == 16
        for source in ("elo", "vegas", "combined"):
            assert 0 <= summary[source]["correct"] <= 16
            assert summary[source]["possible"] == 16 * 17 // 2

    def test_an_unplayed_season_reports_no_results(self, client):
        # The newest season's last week (e.g. the Super Bowl) rather than a hardcoded season/week:
        # week 1 goes stale the moment that week is actually played and the data gets refreshed.
        newest = max(client.get("/api/seasons").json())
        last_week = client.get(f"/api/weeks?season={newest}").json()[-1]["week"]
        summary = client.get(f"/api/games?season={newest}&week={last_week}").json()["summary"]
        assert summary["played"] == 0

    def test_an_unknown_week_is_a_404(self, client):
        assert client.get(f"/api/games?season={SEASON}&week=99").status_code == 404

    def test_a_missing_parameter_is_rejected(self, client):
        assert client.get("/api/games?season=2025").status_code == 422


class TestPicks:
    def test_a_pick_round_trips(self, client, week_games):
        g = week_games[0]
        assert client.put(f"/api/games/{g['game_id']}/pick",
                          json={"team": g["team1"], "confidence": 9}).status_code == 200
        saved = client.get(f"/api/games?season={SEASON}&week={WEEK}").json()["games"][0]["user_pick"]
        assert saved == {"team": g["team1"], "confidence": 9}

    def test_a_pick_can_be_cleared(self, client, week_games):
        gid = week_games[0]["game_id"]
        client.put(f"/api/games/{gid}/pick", json={"team": week_games[0]["team1"], "confidence": 3})
        assert client.delete(f"/api/games/{gid}/pick").status_code == 200
        assert client.get(f"/api/games?season={SEASON}&week={WEEK}").json()["games"][0]["user_pick"] is None

    def test_clearing_a_pick_that_was_never_made_is_harmless(self, client, week_games):
        assert client.delete(f"/api/games/{week_games[0]['game_id']}/pick").status_code == 200

    def test_a_team_not_playing_in_the_game_is_rejected(self, client, week_games):
        g = week_games[0]
        other = next(x for x in week_games if x["team1"] not in (g["team1"], g["team2"]))
        r = client.put(f"/api/games/{g['game_id']}/pick", json={"team": other["team1"], "confidence": 1})
        assert r.status_code == 422
        assert "not playing" in r.json()["detail"]

    def test_a_pick_on_an_unknown_game_is_a_404(self, client):
        r = client.put("/api/games/not-a-real-game/pick", json={"team": "SEA", "confidence": 1})
        assert r.status_code == 404

    @pytest.mark.parametrize("team", ["", "x", "Seattle Seahawks", "sea", "S3A", "A" * 500,
                                      "'; DROP TABLE user_picks; --", "<script>alert(1)</script>"])
    def test_junk_team_values_are_rejected(self, client, week_games, team):
        r = client.put(f"/api/games/{week_games[0]['game_id']}/pick", json={"team": team, "confidence": 1})
        assert r.status_code == 422

    @pytest.mark.parametrize("confidence", [0, -1, 17, 999, 1.5, "high"])
    def test_out_of_range_confidence_is_rejected(self, client, week_games, confidence):
        g = week_games[0]
        r = client.put(f"/api/games/{g['game_id']}/pick",
                       json={"team": g["team1"], "confidence": confidence})
        assert r.status_code == 422

    def test_confidence_is_optional(self, client, week_games):
        g = week_games[0]
        assert client.put(f"/api/games/{g['game_id']}/pick", json={"team": g["team1"]}).status_code == 200

    def test_the_injection_attempt_did_not_drop_the_table(self, client, week_games):
        g = week_games[0]
        client.put(f"/api/games/{g['game_id']}/pick",
                   json={"team": "'; DROP TABLE user_picks; --", "confidence": 1})
        assert client.put(f"/api/games/{g['game_id']}/pick",
                          json={"team": g["team1"], "confidence": 1}).status_code == 200

    def test_repicking_the_same_game_overwrites_rather_than_duplicates(self, client, week_games):
        g = week_games[0]
        client.put(f"/api/games/{g['game_id']}/pick", json={"team": g["team1"], "confidence": 1})
        client.put(f"/api/games/{g['game_id']}/pick", json={"team": g["team2"], "confidence": 2})
        saved = client.get(f"/api/games?season={SEASON}&week={WEEK}").json()["games"][0]["user_pick"]
        assert saved == {"team": g["team2"], "confidence": 2}


class TestParams:
    def test_defaults_are_recalibrated_from_538s_published_values(self, client):
        p = client.get("/api/params").json()
        # hfa is recalibrated from the actual 2021-2025 home win rate; 538's original was 65.
        # k and mov_base are unchanged from 538's published values.
        assert p["hfa"] == 32.0 and p["k"] == 20.0 and p["mov_base"] == 2.2

    def test_saving_parameters_changes_the_forecast(self, client):
        before = client.get(f"/api/games?season={SEASON}&week={WEEK}").json()["games"][0]["elo_prob"]
        client.put("/api/params", json={"hfa": 200.0, "k": 20.0, "revert": 1 / 3,
                                        "mov_base": 2.2, "blend_weight": 0.5})
        after = client.get(f"/api/games?season={SEASON}&week={WEEK}").json()["games"][0]["elo_prob"]
        assert after != before

    @pytest.mark.parametrize("bad", [
        {"hfa": -1}, {"hfa": 10_000}, {"k": 0}, {"k": -5}, {"k": 1e9},
        {"revert": -0.1}, {"revert": 1.5}, {"mov_base": 0}, {"mov_base": -2},
        {"blend_weight": -0.01}, {"blend_weight": 2}, {"hfa": "lots"}, {"k": None},
    ])
    def test_out_of_range_parameters_are_rejected(self, client, bad):
        payload = {"hfa": 65.0, "k": 20.0, "revert": 1 / 3, "mov_base": 2.2, "blend_weight": 0.5}
        payload.update(bad)
        assert client.put("/api/params", json=payload).status_code == 422

    def test_a_partial_payload_is_rejected(self, client):
        assert client.put("/api/params", json={"hfa": 65.0}).status_code == 422

    def test_rejected_parameters_leave_the_saved_ones_alone(self, client):
        before = client.get("/api/params").json()
        client.put("/api/params", json={"hfa": -50, "k": 20.0, "revert": 0.3,
                                        "mov_base": 2.2, "blend_weight": 0.5})
        assert client.get("/api/params").json() == before

    def test_extreme_but_legal_parameters_do_not_break_the_replay(self, client):
        client.put("/api/params", json={"hfa": 300.0, "k": 100.0, "revert": 1.0,
                                        "mov_base": 10.0, "blend_weight": 0.0})
        r = client.get(f"/api/games?season={SEASON}&week={WEEK}")
        assert r.status_code == 200
        assert all(0 < g["elo_prob"] < 1 for g in r.json()["games"])

    def test_zero_reversion_keeps_ratings_finite(self, client):
        client.put("/api/params", json={"hfa": 0.0, "k": 100.0, "revert": 0.0,
                                        "mov_base": 10.0, "blend_weight": 1.0})
        assert client.get("/api/rankings").status_code == 200


class TestScoreboard:
    def test_every_season_since_1920_is_present(self, client):
        seasons = [r["season"] for r in client.get("/api/scoreboard").json()["seasons"]]
        assert seasons[0] == 1920
        assert seasons == sorted(seasons)

    def test_the_market_benchmark_only_exists_from_2021(self, client):
        data = client.get("/api/scoreboard").json()
        for row in data["seasons"]:
            if row["season"] < data["first_vegas_season"]:
                assert row["vegas_points"] is None, "pre-2021 has no market line to compare against"
            else:
                assert row["fte_points"] is None, "538 stopped publishing forecasts after 2020"

    def test_pool_scoring_only_exists_for_seasons_with_weekly_schedules(self, client):
        data = client.get("/api/scoreboard").json()
        for row in data["seasons"]:
            if row["season"] < data["first_vegas_season"]:
                assert row["elo_pool"] is None

    def test_all_sources_play_for_the_same_pot_of_points(self, client):
        for row in client.get("/api/scoreboard").json()["seasons"]:
            pools = [row[f"{s}_pool"] for s in ("elo", "vegas", "combined", "user")]
            possible = {p["possible"] for p in pools if p}
            assert len(possible) <= 1, f"season {row['season']} gave sources different maximums"

    def test_no_source_can_score_more_than_the_maximum(self, client):
        for row in client.get("/api/scoreboard").json()["seasons"]:
            for source in ("elo", "vegas", "combined", "user"):
                pool = row[f"{source}_pool"]
                if pool:
                    assert 0 <= pool["earned"] <= pool["possible"]

    def test_a_season_with_no_saved_picks_is_flagged_rather_than_scored_zero(self, client):
        # No picks have been made anywhere yet in a fresh test db, so every season's user pool
        # should say so via graded=0 rather than looking like a real 0-point performance.
        rows = client.get("/api/scoreboard").json()["seasons"]
        graded = [r["user_pool"]["graded"] for r in rows if r["user_pool"]]
        assert graded and all(g == 0 for g in graded)

    def test_saved_picks_show_up_in_the_pool_score(self, client, week_games):
        before = _pool(client, SEASON, "user")["earned"]
        assert _pool(client, SEASON, "user")["graded"] == 0
        for g in week_games:
            client.put(f"/api/games/{g['game_id']}/pick",
                       json={"team": g["elo_pick"], "confidence": g["elo_rank"]})
        after = _pool(client, SEASON, "user")
        assert after["earned"] > before
        assert after["graded"] == len(week_games)

    def test_copying_elo_exactly_reproduces_its_score(self, client):
        """ The strongest check that user and model scoring share one rule. """
        for week in range(1, 23):
            games = client.get(f"/api/games?season={SEASON}&week={week}").json()["games"]
            for g in games:
                if g["elo_pick"] and g["elo_rank"]:
                    client.put(f"/api/games/{g['game_id']}/pick",
                               json={"team": g["elo_pick"], "confidence": g["elo_rank"]})
        assert _pool(client, SEASON, "user")["earned"] == _pool(client, SEASON, "elo")["earned"]

    def test_the_scoreboard_survives_a_parameter_change(self, client):
        first = client.get("/api/scoreboard").json()
        client.put("/api/params", json={"hfa": 120.0, "k": 30.0, "revert": 0.5,
                                        "mov_base": 3.0, "blend_weight": 0.7})
        second = client.get("/api/scoreboard").json()
        assert first["seasons"][-1]["elo_points"] != second["seasons"][-1]["elo_points"]


def _pool(client, season, source):
    rows = client.get("/api/scoreboard").json()["seasons"]
    return next(r for r in rows if r["season"] == season)[f"{source}_pool"]


class TestRankings:
    def test_a_full_league_is_rated_and_ordered(self, client):
        rows = client.get("/api/rankings?season=2025").json()
        assert len(rows) == 32
        assert [r["rank"] for r in rows] == list(range(1, 33))
        assert [r["elo"] for r in rows] == sorted((r["elo"] for r in rows), reverse=True)

    def test_ratings_are_plausible(self, client):
        assert all(1100 < r["elo"] < 1900 for r in client.get("/api/rankings?season=2025").json())

    def test_an_unknown_season_returns_nothing_rather_than_failing(self, client):
        assert client.get("/api/rankings?season=1873").json() == []


class TestNonFiniteNumbers:
    """ json.loads accepts Infinity and NaN; json.dumps refuses to emit them. Echoing a rejected
    value straight back into the 422 body therefore turns a validation error into a 500. """

    @pytest.mark.parametrize("literal", ["Infinity", "-Infinity", "NaN"])
    def test_a_non_finite_parameter_is_a_422_not_a_500(self, client, literal):
        body = ('{"hfa": %s, "k": 20.0, "revert": 0.33, "mov_base": 2.2, "blend_weight": 0.5}'
                % literal)
        r = client.put("/api/params", content=body, headers={"Content-Type": "application/json"})
        assert r.status_code == 422
        r.json()  # the error body itself has to be serialisable

    def test_a_non_finite_confidence_is_a_422_not_a_500(self, client, week_games):
        r = client.put(f"/api/games/{week_games[0]['game_id']}/pick",
                       content='{"team": "SEA", "confidence": NaN}',
                       headers={"Content-Type": "application/json"})
        assert r.status_code == 422
        r.json()

    def test_non_finite_values_never_reach_a_success_response(self, client):
        import math

        client.put("/api/params", json={"hfa": 300.0, "k": 100.0, "revert": 1.0,
                                        "mov_base": 10.0, "blend_weight": 1.0})
        for g in client.get(f"/api/games?season={SEASON}&week={WEEK}").json()["games"]:
            for field in ("elo_prob", "combined_prob", "elo1", "elo2"):
                assert g[field] is None or math.isfinite(g[field])


class TestStaticAndMisc:
    def test_the_favicon_is_served(self, client):
        assert client.get("/favicon.ico").status_code == 200

    def test_an_unknown_api_route_is_a_404(self, client):
        assert client.get("/api/nope").status_code == 404

    def test_a_traversal_attempt_in_a_game_id_serves_no_file(self, client):
        r = client.get("/api/games/..%2F..%2F..%2Fetc%2Fpasswd/pick")
        assert r.status_code in (404, 405)
        assert "root:" not in r.text
