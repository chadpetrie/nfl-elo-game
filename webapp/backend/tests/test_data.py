""" Integrity of the CSVs the whole app is built on. A bad refresh should fail here first. """

import csv

import pytest

from app.paths import DATA_DIR

FIRST_RECENT_SEASON = 2021


@pytest.fixture(scope="module")
def recent():
    with open(DATA_DIR / "nfl_games_recent.csv") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def historical():
    with open(DATA_DIR / "nfl_games.csv") as f:
        return list(csv.DictReader(f))


class TestRecentGames:
    def test_rows_are_in_chronological_order(self, recent):
        dates = [r["date"] for r in recent]
        assert dates == sorted(dates)

    def test_game_ids_are_unique(self, recent):
        ids = [r["game_id"] for r in recent]
        assert len(ids) == len(set(ids))

    def test_every_row_has_the_fields_the_app_indexes_on(self, recent):
        for r in recent:
            assert r["game_id"] and r["week"] and r["game_type"] and r["date"]

    def test_the_two_files_do_not_overlap(self, recent, historical):
        assert max(int(r["season"]) for r in historical) < min(int(r["season"]) for r in recent)

    def test_no_team_plays_itself(self, recent):
        assert not [r for r in recent if r["team1"] == r["team2"]]

    def test_a_result_always_agrees_with_the_score(self, recent):
        for r in recent:
            if r["score1"] == "" or r["score2"] == "":
                continue
            s1, s2 = int(r["score1"]), int(r["score2"])
            expected = 1.0 if s1 > s2 else (0.0 if s2 > s1 else 0.5)
            assert float(r["result1"]) == expected, r["game_id"]

    def test_a_game_either_has_both_scores_or_neither(self, recent):
        for r in recent:
            assert (r["score1"] == "") == (r["score2"] == ""), r["game_id"]

    def test_market_probabilities_are_valid(self, recent):
        for r in recent:
            if r["elo_prob1"]:
                assert 0.0 < float(r["elo_prob1"]) < 1.0, r["game_id"]

    def test_playoff_flag_agrees_with_game_type(self, recent):
        for r in recent:
            assert int(r["playoff"]) == (0 if r["game_type"] == "REG" else 1), r["game_id"]

    def test_week_numbers_are_unique_per_round_within_a_season(self, recent):
        seen = {}
        for r in recent:
            key = (r["season"], r["week"])
            seen.setdefault(key, set()).add(r["game_type"])
        assert all(len(types) == 1 for types in seen.values())

    def test_completed_seasons_have_a_full_schedule(self, recent):
        # 272 regular season + 13 playoff. 2022 is one short: Bills-Bengals was abandoned after
        # Damar Hamlin's cardiac arrest and never replayed.
        expected = {"2022": 284}
        counts = {}
        for r in recent:
            counts[r["season"]] = counts.get(r["season"], 0) + 1
        for season, n in counts.items():
            if season == "2026":  # still being played
                continue
            assert n == expected.get(season, 285), f"{season} has {n} games"

    def test_team_codes_are_consistent_with_the_historical_file(self, recent, historical):
        legacy = {r["team1"] for r in historical} | {r["team2"] for r in historical}
        current = {r["team1"] for r in recent} | {r["team2"] for r in recent}
        assert current <= legacy, f"unmapped relocation codes: {sorted(current - legacy)}"


class TestInitialElos:
    def test_every_team_in_the_data_has_a_starting_rating(self, recent, historical):
        with open(DATA_DIR / "initial_elos.csv") as f:
            rated = {r["team"] for r in csv.DictReader(f)}
        playing = {r["team1"] for r in recent + historical} | {r["team2"] for r in recent + historical}
        assert playing <= rated, f"missing initial Elo for: {sorted(playing - rated)}"
