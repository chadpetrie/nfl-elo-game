# Overnight work — 2026-08-10

Everything below is in the working tree on branch `update-2026-season`. **Nothing has been
committed or pushed** — see [Follow-ups](#follow-ups-for-the-morning) first.

Quick status: **128 unit tests pass, 27/27 adversarial probes pass, the UI was driven end to end
in a real browser, and the 2025 backtest is written up in
[reports/backtest_2025.md](reports/backtest_2025.md).**

---

## 1. Code review findings

I reviewed the whole webapp and the engine it sits on. Four things were actually wrong, as
opposed to merely improvable.

### The serious ones

**Your picks were being scored under a rule the UI never told you about.** The scoreboard turned
each pick into a 100%-confident probability and ran it through the Brier rule. Under that rule a
correct pick is worth +25 and a wrong one is worth **−75**, so any human entry would sink deep
into the negative and look absurd next to the models. Worse, the confidence rank the UI carefully
collected for every game was never read at all. This was the single biggest correctness problem
in the app and it drove most of the redesign below.

**The "Vegas" column was not Vegas for 80% of the seasons shown.** `elo_prob1` holds a devigged
closing moneyline from 2021 on, but for 1920–2020 it holds FiveThirtyEight's own published Elo
forecast. The scoreboard labelled all of it "Vegas", which is why the Elo and Vegas columns were
identical for every pre-2021 row — the app was quietly comparing 538's model against itself and
calling it a betting market.

**Any API failure left the app on a spinner forever.** Every view did `api.x().then(setState)`
with no `.catch`. Stop the server, click a tab, and you got "Loading…" with no error, no
explanation, and no way to recover short of a page reload.

**Picks were never validated.** `team` was an unbounded free string and nothing checked that the
game existed or that the team was playing in it. A typo silently became a pick for the *away*
team, because the scorer treated "not team1" as "team2".

### The rest

Race conditions from fast season/week switching applying stale responses; shared mutable state
where `ranking.annotate` wrote derived fields back into the process-wide game cache; an
`os.chdir()` at import time; no caching on a scoreboard that rescored 18,506 games per request;
no way to clear a pick; no uniqueness enforcement on confidence values; a missing favicon; the
scoreboard opening on 1920 when you care about 2025; and no tests anywhere in the project.

---

## 2. What I built

### Scoring, rebuilt around what the UI actually promises

The app now scores two genuinely different games and keeps them apart, in
[webapp/backend/app/scoring.py](webapp/backend/app/scoring.py):

- **Confidence pool** — the office-pool game the "Your pick" column implies. Each week's games are
  ranked 1..N, and a correct pick collects its rank. Every model plays the *same* game by ranking
  the week by its own confidence, which makes model and human directly comparable for the first
  time. This is now the headline table.
- **Brier points** — the original game's rule, which only a probability can play, so it covers the
  models only. The benchmark column is now labelled honestly: "Vegas" from 2021, "538 Elo" before.

Ties are handled the way a real pool handles them: the tie is part of the slate everyone had to
rank, nobody can win it, and the points anyone put on it are simply lost. That detail matters more
than it sounds — see the bug it exposed in §3.

### Backend

- Pick validation: unknown game → 404, team not in that matchup → 422 with a readable message,
  team constrained to `^[A-Z]{2,4}$`, confidence bounded 1–16.
- `DELETE /api/games/{id}/pick` so a pick can be cleared.
- `GET /api/rankings` — current Elo power ratings for the league.
- `/api/games` now also returns a week summary: each source's record and pool haul.
- Scoreboard is cached and invalidated on any pick or parameter change (0.12s cold, 0.02s warm).
- Model replay is indexed by season/week/game id and held under one lock, so a concurrent request
  can't read ratings built from someone else's parameters.
- Removed the `os.chdir()`; `forecast.py` now resolves its own data files, so it imports cleanly
  from anywhere. This is what let the tests run at all.
- `forecast.Forecast.forecast()` now records the pre-game ratings it forecast from (`my_elo1` /
  `my_elo2`) and returns final team ratings. Backward compatible — `eval.py` still works unchanged.

### Frontend

- Real error handling everywhere: a dismissible banner with a retry button, an error boundary per
  tab, and a specific message when the server is unreachable rather than a dead spinner.
- Stale-response guards on season and week changes.
- Confidence is a bounded dropdown instead of a free number field; duplicates are highlighted in
  red on both offending rows with a banner explaining why a pool wants each number used once.
- **Autofill** — one click fills your whole week from Elo, Vegas, or Combined, plus a Clear button.
  This is the workflow the app was missing: seed from a model, then override the ones you disagree
  with.
- A week results bar showing each source's record and points once games are final.
- New **Power Ratings** tab with a diverging bar chart of every team against the 1505 average.
- Scoreboard now opens on 2021+ with a toggle for the full history back to 1920.
- Optimistic pick saving that rolls back and surfaces the error if the server rejects it.

---

## 3. Validation — including what it caught

**128 pytest tests** in [webapp/backend/tests/](webapp/backend/tests/): Elo math and determinism,
both scoring rules, ranking, the full API contract, adversarial input, and CSV integrity.

**27 adversarial probes** against a live server: negative and absurd week numbers, path traversal
in the game id, SQL injection in the team field, non-object bodies, out-of-range and non-finite
parameters, 60 concurrent reads, concurrent parameter writes, mixed read/write under load, cache
behaviour, and latency budgets.

**A real browser session** driving every tab: autofill, duplicate detection, clear, tab switching,
power ratings, both scoreboards, and error recovery with the server killed mid-session.

### Bugs the validation actually found and I then fixed

1. **Confidence ranks in the UI disagreed with the ranks the scoreboard scored against.** Caught by
   a test that copies Elo's own picks into the user slot and asserts the two scores come out equal.
   They didn't. The cause was 2025 week 4 (GB–DAL, 40–40): the week screen ranked all 16 games
   while the scoreboard renumbered over the 15 non-tie games, so an autofilled entry scored
   differently from the model it copied. If you had ever autofilled from Elo and compared, the
   numbers would not have matched and there'd be no obvious reason why. Fixed by ranking over all
   *final* games in both places.
2. **A non-finite number in a request body returned 500 instead of 422.** `json.loads` accepts
   `Infinity` and `NaN`; `json.dumps` refuses to emit them. FastAPI's default validation handler
   echoes the rejected value back in the error body, so rendering the 422 threw and the client got
   an unhandled 500. Fixed with a handler that sanitises non-finite floats out of the error
   payload, plus regression tests for `Infinity`, `-Infinity`, and `NaN`.
3. **Two of my own test assumptions were wrong, and the data was right.** 2022 has 284 games, not
   285 — Bills–Bengals was abandoned after Damar Hamlin's cardiac arrest and never replayed. And
   "higher home-field advantage raises every home win probability" is false across a full replay,
   because the ratings themselves diverge; it's only true holding ratings fixed. Both are now
   tested correctly, with the reason written down.

Everything is green as of this writing.

---

## 4. The 2025 backtest

[scripts/backtest.py](scripts/backtest.py) walks a season week by week and grades the predictions.
Full write-up with every weekly recommendation is in
[reports/backtest_2025.md](reports/backtest_2025.md); 2021–2024 are in the same folder.

**On out-of-sample honesty:** the Elo model forecasts each game before applying that game's result,
so predictions are already walk-forward. I didn't take that on faith — the script re-forecasts
weeks 1, 8, 15 and 22 from a history truncated before each, with those weeks' results blanked out,
and confirms the probabilities come out identical. It reports "leakage check passed" and does so
for all five seasons. The season totals also match the webapp's scoreboard exactly, which is a
useful cross-check since they're independent code paths.

### 2025 results

| Forecaster | Straight up | Win rate | Confidence pool | Brier |
|---|---|---|---|---|
| Elo | 181-103 | 63.7% | 1507 / 2235 (67.4%) | 778.4 |
| Vegas | 187-97 | 65.8% | **1603 / 2235 (71.7%)** | 1189.0 |
| Combined | **190-94 (66.9%)** | | 1572 / 2235 (70.3%) | 1055.2 |

**Big hits.** Elo's best week was week 7 (11-4, 103 of 120 points). Its most confident calls were
largely sound: it had BUF over NYJ at 92% (35-8), JAX over TEN at 90% (41-7), PHI over OAK at 90%
(31-0). At the very top of its confidence range it was actually *under*-confident — the four games
it called at 90%+ all won.

**Big misses.** Week 5 was a disaster: 4-10, just 26 of 105 points. The individual stingers were
NE beating BUF when Elo had BUF at 86%, WSH over PHI at 86%, and CAR over GB at 85%.

**The real story is miscalibration in the middle.** Games Elo called at 70–80% (it said 74.2%) won
only **62.3%** of the time — a 12-point gap, across 69 games, in exactly the band that gets high
confidence ranks. Vegas's equivalent band was nearly perfect (74.9% predicted, 73.8% actual). Elo
isn't mostly losing on which team to pick; it's losing on knowing when to trust itself, which is
precisely what a confidence pool pays for.

**Which teams it misjudged.** Elo held KC (+26.7 points of win probability), ARI (+22.6) and WSH
(+18.5) far too high, and was equally slow to credit NE (−26.6), JAX (−22.2) and SEA (−21.6). This
is the standing cost of a rating that only reads the scoreboard — it can't hear about a roster
change until enough games have gone the other way. Two of the three overrated teams are the ones
whose confident losses produced the biggest misses above.

**Head to head with the market.** Elo and Vegas disagreed on 40 games; Vegas was right on 23 of
them. Elo out-scored Vegas in only 4 of 22 weeks, so the season gap isn't one bad Sunday.

### A concrete finding about your blend setting

I swept the Elo/Vegas blend weight across all five seasons. Pool points as a share of the pot:

| Blend (Elo weight) | 2021 | 2022 | 2023 | 2024 | 2025 | All |
|---|---|---|---|---|---|---|
| 0.00 (pure Vegas) | 70.2 | 71.6 | 69.8 | 76.0 | 71.7 | **71.9%** |
| 0.50 (current default) | 67.9 | 70.4 | 68.4 | 75.5 | 70.3 | 70.5% |
| 1.00 (pure Elo) | 63.9 | 67.3 | 64.9 | 71.0 | 67.4 | 66.9% |

It degrades monotonically — every increment of Elo weight makes pool performance worse, in every
season, without exception. For pool play the blend slider wants to be near 0.

One honest caveat against that: Combined picked *more winners outright* than Vegas in 2025 (190 vs
187) and 2022. So Elo does add a little signal about **which team wins**, while actively damaging
the **ordering of confidence**. If you play a straight pick'em with no confidence weighting, a
small Elo weight is defensible. For a confidence pool, it isn't. I left the default at 0.50 rather
than change a setting you'd chosen — it's a one-slider change on the Settings tab.

---

## Follow-ups for the morning

### Needs your decision

1. **Nothing is committed.** All of this is uncommitted in the working tree, including the entire
   `webapp/` directory which was already untracked before I started. I didn't commit because you
   hadn't asked and it's a lot of surface to land in one go without your eyes on it. Suggested
   split: (a) engine refactor + `forecast.py`/`util.py`, (b) the webapp, (c) tests, (d) backtest
   and reports.
2. ~~**`.mcp.json` is untracked** and configures the Playwright MCP server.~~ **Mostly closed
   2026-08-11.** Playwright is now registered at **user scope** in `~/.claude.json`, so it is
   available in every project rather than only this repo. Backup of the previous config is at
   `~/.claude.json.bak-20260811-080059`.
   *Remaining step:* fully restart Claude Code, confirm Playwright still works, then delete the
   repo's `.mcp.json`. Do not delete it before confirming — a running session can rewrite
   `~/.claude.json` on exit, and you don't want to lose both copies at once.
3. **`reports/*.md` are generated output** — five files, ~500 lines each. Commit them as artifacts
   or gitignore them and regenerate on demand. I left them tracked-able but made no call.
4. **The blend weight recommendation above** is a settings change I deliberately did not make for
   you.

### Things I did not do

5. **I did not try to improve the Elo model itself.** The backtest says where it's weakest
   (70–80% confidence band, slow reaction to roster turnover) but tuning K, reversion, or adding a
   QB adjustment is a real modelling project, not an overnight change. The parameter sweep
   infrastructure now exists to evaluate any such change properly.
6. **No dark mode.** The CSS is explicitly light-only (`color-scheme: light`). Straightforward to
   add now that the palette is all CSS custom properties.
7. **No mobile/responsive testing.** Tables have `min-width: 880px` and scroll horizontally; I only
   verified desktop.
8. **No authentication**, which is correct for a localhost single-user app but means don't expose
   the port beyond `127.0.0.1` as-is.
9. **Only 52 of 272 games in 2026 have a Vegas line so far.** The app degrades correctly (shows
   "odds not posted", leaves those games unranked for Vegas), but the Vegas and Combined columns
   will stay sparse until books post the full slate. Re-run
   `python scripts/update_recent_games.py` periodically.
10. **A `StarletteDeprecationWarning`** about `httpx` vs `httpx2` appears in the test output. Cosmetic,
    from FastAPI's TestClient, not from your code.

### Housekeeping I did

- Removed a stray test pick I'd created on `2026_01_NE_SEA` during an earlier verification run —
  your picks database is empty and parameters are back at the 538 defaults.
- Added `.playwright-mcp/` and `.pytest_cache/` to `.gitignore`.
- `pytest` and `httpx` were installed into `webapp/backend/venv` to run the tests. They are **not**
  in `requirements.txt` — worth splitting into a `requirements-dev.txt` if you want the suite
  reproducible from a fresh setup.

## Running things

```powershell
cd webapp\backend; .\venv\Scripts\python.exe -m pytest tests -q   # 128 tests
python scripts\backtest.py 2025                                   # writes reports\backtest_2025.md
webapp\start_app.bat                                              # the app itself
```

The frontend has been rebuilt, so `start_app.bat` will serve all of the above without any extra
step.
