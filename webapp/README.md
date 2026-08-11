# NFL Predictions — local app

A local web app for browsing each week's games and predictions, built on top of the Elo
engine in the repo root (`forecast.py` / `util.py`). One process serves both the API and
the UI at `http://localhost:8000`.

* **This Week** — for any season/week, see the predicted winner and a 1..N confidence rank
  (N = most confident) from three sources: **Elo** (the repo's own model), **Vegas**
  (devigged closing moneylines, from `data/nfl_games_recent.csv`), and **Combined** (a
  blend of the two). Make your own pick and confidence per game, or fill the whole week from
  any of the three with one click and then override the ones you disagree with. Once games are
  final, a results bar shows each source's record and points for the week.
* **Scoreboard** — two ways of keeping score, kept deliberately separate:
  * *Confidence pool* — the office-pool game the "Your pick" column plays. Each week's games are
    ranked 1..N and a correct pick collects its rank. Every model plays the same game by ranking
    the week by its own confidence, so you and the models are directly comparable.
  * *Brier points* — the original game's rule, which rewards a probability for being correct and
    confident. Only models produce probabilities, so your picks don't appear here. The benchmark
    is the Vegas line from 2021 on, and FiveThirtyEight's own Elo forecast before that.
* **Power Ratings** — every team's current Elo rating against the 1505 league average.
* **Settings** — tune the Elo model (home-field advantage, K-factor, season reversion,
  margin-of-victory weighting) and the Elo/Vegas blend weight used for Combined. Saving
  replays the model over every game since 1920 and every view updates immediately.

## Install (one time)

Requires Python 3.10+ and Node.js (both already used elsewhere in this repo). From
PowerShell, in this `webapp` folder:

```powershell
.\setup.ps1
```

This creates a Python virtual environment for the backend, installs its dependencies, and
builds the frontend.

## Run

Double-click **`start_app.bat`** (or run it from a terminal). It starts the server and
opens your browser to `http://localhost:8000` automatically once it's ready. Leave the
console window open while using the app; close it to stop the server.

## Tests

```powershell
cd backend
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt   # one time
.\venv\Scripts\python.exe -m pytest tests -q
```

Covers the Elo math, both scoring rules, the weekly ranking, the whole API surface including
adversarial input, and the integrity of the CSVs everything is built on. The test dependencies
live in `requirements-dev.txt` so a plain `setup.ps1` install stays lean.

## Notes

* Your picks and tuned parameters are stored in `webapp/data/app.db` (SQLite), not in git.
* To pull the latest results and lines for the current season, run
  `python scripts/update_recent_games.py` from the repo root, then restart the app.
  Your saved picks stay attached to the right games (they're keyed by a stable game ID).
* Games with no posted line show "odds not posted" and are left out of the Vegas ranking rather
  than guessed at. Early in a season most of the slate looks like this.
* A tie is part of the slate everyone had to rank, nobody can win it, and any points placed on it
  are lost — the same way a real pool treats it.
* If you change frontend code, re-run `npm run build` inside `webapp/frontend` (or
  `.\setup.ps1` again) before restarting the app — `start_app.bat` serves the last build,
  it doesn't rebuild automatically.
