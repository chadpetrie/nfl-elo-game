# Can You Beat the Market's NFL Predictions?

This repository contains code and data to replay [FiveThirtyEight's NFL Elo model](https://fivethirtyeight.com/features/how-our-nfl-predictions-work/) and evaluate alternative forecasts against it. Specifically, it has:

* Historical NFL scores back to 1920 in `data/nfl_games.csv`, with FiveThirtyEight's own Elo win probabilities for each game through the 2020 season.
* Game schedule and results from the 2021 season onward in `data/nfl_games_recent.csv`, refreshed via `scripts/update_recent_games.py`.
* Code to generate Elo win probabilities from that data (`forecast.py`).
* Code to evaluate alternative forecasts against a benchmark using the historical data and the rules of the original 538 forecasting game (`util.py`, `eval.py`).

**A note on the benchmark:** FiveThirtyEight stopped updating its sports forecasts in June 2023, and its data API (`projects.fivethirtyeight.com/nfl-api`) is no longer online. So the `elo_prob1` field means two different things depending on the game:

* **1920–2020** (`data/nfl_games.csv`): FiveThirtyEight's own official Elo forecast, exactly as before.
* **2021–present** (`data/nfl_games_recent.csv`): since there's no more official Elo forecast to fetch, `elo_prob1` is instead a devigged win probability implied by the closing Vegas moneyline for that game, pulled from [nflverse/nfldata](https://github.com/nflverse/nfldata). Beating the Vegas market is a considerably higher bar than beating a public Elo model, so don't be surprised if `my_prob1` does worse against it than it used to against 538's Elo.

Our goal in providing this repository is for people to be able to figure out how an NFL Elo model works and to provide a loose framework for evaluating forecasts against historical data. This repository does not include assistance in building a predictive model.

## Evaluating historical forecasts

`eval.py` is the only runnable script, and does the following:

1. Reads in the CSVs of historical and recent games. Each row includes an `elo_prob1` field, which is the probability that `team1` (the home team) wins — see the note above on what that means pre- and post-2021.
2. Fills in a `my_prob1` field for every game using code in `forecast.py`. By default, these are filled in using the same Elo model FiveThirtyEight used.
3. Evaluates the probabilities stored in `my_prob1` against the ones in `elo_prob1`, and shows how those forecasts would have done in our game for every season since 1920, plus forecasts for any upcoming games.

Jump in by running `python eval.py`. You should see output ending with something like:

```

On average, your forecasts would have gotten 636.11 points per season. Elo got 671.93 points per season.

```

Each individual season through 2020 is graded against FiveThirtyEight's own Elo forecast, and from 2021 on against the closing Vegas line instead — a much tougher benchmark, so expect the built-in model to lose ground there. Try to close that gap.

**A word of caution about this all-time average.** `forecast.py`'s default `HFA` (home-field advantage) is `32`, recalibrated from actual 2021-2025 results rather than FiveThirtyEight's originally published `65` (still the default for `K` and `MOV_BASE`, which weren't part of this recalibration). If you set `HFA` back to `65` and rerun `eval.py`, the all-time average actually *improves* to 652.67 — but that's because `forecast.py` becomes a byte-for-byte replica of FiveThirtyEight's own model for 1920-2020, and those seasons are graded against FiveThirtyEight's own Elo output, so matching their exact constant trivially wins that comparison. It says nothing about which constant predicts *real* outcomes better. For that, see `reports/backtest_2025.md` (or rerun `scripts/backtest.py`): walked forward week by week against real Vegas closing lines for 2021-2025, `HFA = 32` outscores `HFA = 65` in every one of those seasons, closing about a third of Elo's gap to the market. `OVERNIGHT_REPORT.md` has the full writeup.

## Making 2026 forecasts

Run `python scripts/update_recent_games.py` any time to refresh `data/nfl_games_recent.csv` with the latest results and closing lines from [nflverse/nfldata](https://github.com/nflverse/nfldata) (a community-maintained source, since FiveThirtyEight's own API is defunct). Rerun `python eval.py` afterward and you'll see something like:

```

Forecasts for upcoming games:
2026-09-09	SEA vs. NE		63% (Elo)		65% (You)
2026-09-10	LAR vs. SF		63% (Elo)		57% (You)
2026-09-13	CAR vs. CHI		43% (Elo)		40% (You)

```

The scripts are now maintaining Elo ratings through the 2026 season, and printing forecasts (both from `elo_prob1` and from `my_prob1`) for upcoming games. Games far enough in the future that Vegas hasn't posted a line yet won't show up here — they're skipped until a line exists to forecast against.

## More

Have at it! Some ideas for further exploration:

* Tweak the Elo parameters and margin of victory multiplier and see what happens.
* Augment these Elo ratings with data from other sources to improve forecasts.
* Use this code as an example to build your own model using whatever language, framework or approach you'd like.
