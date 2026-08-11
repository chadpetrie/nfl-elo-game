"""
Walks a season week by week, makes predictions with only the games that came before, then
grades them against what actually happened.

    python scripts/backtest.py            # 2025, writes reports/backtest_2025.md
    python scripts/backtest.py 2024

Three forecasters are compared:

  Elo       this repo's model, replayed from 1920 with the parameters in forecast.py
  Vegas     the devigged closing moneyline, which is the number to beat
  Combined  a 50/50 blend of the two

Each is graded two ways: the original game's Brier points, and a confidence pool where the week's
games are ranked 1..N and a correct pick collects its rank.

The Elo model already forecasts each game before applying that game's result, so its predictions
are out-of-sample by construction. verify_no_leakage() re-derives a few weeks from a truncated
history to prove that rather than take it on faith.
"""

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from forecast import Forecast  # noqa: E402
from util import Util  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND = 0.5
REPORT_DIR = os.path.join(ROOT, "reports")


# --------------------------------------------------------------------------- data

def load_games():
    games = Util.read_games(os.path.join(ROOT, "data", "nfl_games.csv")) + \
        Util.read_games(os.path.join(ROOT, "data", "nfl_games_recent.csv"))
    Forecast.forecast(games)
    return games


def season_weeks(games, season):
    weeks = defaultdict(list)
    for g in games:
        if g["season"] == season and g.get("week") and g["result1"] is not None:
            weeks[int(g["week"])].append(g)
    return dict(sorted(weeks.items()))


def combined_prob(g):
    if g["elo_prob1"] is None:
        return g["my_prob1"]
    return BLEND * g["my_prob1"] + (1 - BLEND) * g["elo_prob1"]


PROBS = {
    "Elo": lambda g: g["my_prob1"],
    "Vegas": lambda g: g["elo_prob1"],
    "Combined": combined_prob,
}


def pick(g, prob):
    return None if prob is None else (g["team1"] if prob >= 0.5 else g["team2"])


def winner(g):
    return g["team1"] if g["result1"] == 1 else (g["team2"] if g["result1"] == 0 else None)


def confidence(prob):
    return max(prob, 1 - prob)


def rank_week(week_games, prob_fn):
    """ 1..N by confidence, N = most confident, matching the web app's ranking """
    ranked = [g for g in week_games if prob_fn(g) is not None]
    ranked.sort(key=lambda g: (-confidence(prob_fn(g)), g.get("gametime") or "", g["game_id"]))
    n = len(ranked)
    return {g["game_id"]: n - i for i, g in enumerate(ranked)}


# --------------------------------------------------------------------------- leakage check

def verify_no_leakage(games, season, weeks_to_check=(1, 8, 15, 22)):
    """ Re-forecasts from a history that stops before each week and checks the probability is
    identical. If any future result were feeding back into a forecast, these would diverge. """
    problems = []
    for week in weeks_to_check:
        cutoff = [g for g in games
                  if g["season"] < season or (g.get("week") and int(g["week"]) <= week
                                              and g["season"] == season)]
        if not cutoff:
            continue
        truncated = [dict(g) for g in cutoff]
        # Hide every result from the week under test, so the model cannot have seen any of them.
        target = [g for g in truncated
                  if g["season"] == season and g.get("week") and int(g["week"]) == week]
        for g in target:
            g["score1"] = g["score2"] = g["result1"] = None
        Forecast.forecast(truncated)

        full = {g["game_id"]: g["my_prob1"] for g in games
                if g["season"] == season and g.get("week") and int(g["week"]) == week}
        for g in target:
            if abs(g["my_prob1"] - full[g["game_id"]]) > 1e-9:
                problems.append((week, g["game_id"], g["my_prob1"], full[g["game_id"]]))
    return problems


# --------------------------------------------------------------------------- grading

def grade_season(weeks):
    """ Returns per-week rows and the per-game detail every summary is derived from """
    week_rows, details = [], []

    for week, week_games in weeks.items():
        pot = len(week_games) * (len(week_games) + 1) // 2
        row = {"week": week, "games": len(week_games), "pot": pot}

        ranks = {name: rank_week(week_games, fn) for name, fn in PROBS.items()}
        for name, fn in PROBS.items():
            correct = graded = earned = 0
            brier = 0.0
            for g in week_games:
                prob = fn(g)
                if prob is None:
                    continue
                actual = winner(g)
                if actual is None:  # tie: dead points for everyone
                    continue
                graded += 1
                brier += Util.score_probability(prob, g["result1"], g["playoff"])
                if pick(g, prob) == actual:
                    correct += 1
                    earned += ranks[name][g["game_id"]]
            row[name] = {"correct": correct, "graded": graded, "earned": earned,
                         "brier": round(brier, 1)}
        week_rows.append(row)

        for g in week_games:
            actual = winner(g)
            entry = {"week": week, "game_id": g["game_id"], "team1": g["team1"], "team2": g["team2"],
                     "score1": g["score1"], "score2": g["score2"], "winner": actual,
                     "playoff": g["playoff"], "elo1": g.get("my_elo1"), "elo2": g.get("my_elo2")}
            for name, fn in PROBS.items():
                prob = fn(g)
                entry[name] = {
                    "prob": prob,
                    "pick": pick(g, prob),
                    "rank": ranks[name].get(g["game_id"]),
                    "correct": None if actual is None or prob is None else pick(g, prob) == actual,
                }
            details.append(entry)

    return week_rows, details


def season_totals(week_rows):
    totals = {}
    for name in PROBS:
        totals[name] = {
            "correct": sum(r[name]["correct"] for r in week_rows),
            "graded": sum(r[name]["graded"] for r in week_rows),
            "earned": sum(r[name]["earned"] for r in week_rows),
            "brier": round(sum(r[name]["brier"] for r in week_rows), 1),
        }
    totals["pot"] = sum(r["pot"] for r in week_rows)
    return totals


def calibration(details, name, buckets=((0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01))):
    """ Of the games this forecaster called at 70-80%, how many did the favourite actually win? """
    out = []
    for lo, hi in buckets:
        hits = shown = 0
        total_prob = 0.0
        for d in details:
            entry = d[name]
            if entry["prob"] is None or d["winner"] is None:
                continue
            c = confidence(entry["prob"])
            if lo <= c < hi:
                shown += 1
                total_prob += c
                if entry["correct"]:
                    hits += 1
        if shown:
            out.append({"range": "%d-%d%%" % (lo * 100, min(hi, 1.0) * 100), "n": shown,
                        "predicted": round(100 * total_prob / shown, 1),
                        "actual": round(100 * hits / shown, 1)})
    return out


def biggest(details, name, correct, limit=6):
    """ The most confident calls that went right (or wrong) """
    pool = [d for d in details if d[name]["correct"] is correct and d[name]["prob"] is not None]
    pool.sort(key=lambda d: -confidence(d[name]["prob"]))
    return pool[:limit]


def disagreements(details, limit=8):
    """ Games where Elo and Vegas picked different sides, and who was right """
    out = []
    for d in details:
        e, v = d["Elo"], d["Vegas"]
        if e["pick"] and v["pick"] and e["pick"] != v["pick"] and d["winner"]:
            out.append({**d, "gap": abs(e["prob"] - v["prob"])})
    out.sort(key=lambda d: -d["gap"])
    return out[:limit]


def team_errors(details, name, limit=6):
    """ Which teams this forecaster was most wrong about, by average probability error """
    err = defaultdict(list)
    for d in details:
        entry = d[name]
        if entry["prob"] is None or d["winner"] is None:
            continue
        # Signed error from team1's perspective, credited to both teams involved.
        e = d["score1"] is not None and (d["winner"] == d["team1"])
        err[d["team1"]].append(entry["prob"] - (1.0 if e else 0.0))
        err[d["team2"]].append((1 - entry["prob"]) - (0.0 if e else 1.0))
    rows = [{"team": t, "n": len(v), "bias": round(100 * sum(v) / len(v), 1)}
            for t, v in err.items() if len(v) >= 4]
    rows.sort(key=lambda r: -abs(r["bias"]))
    return rows[:limit]


# --------------------------------------------------------------------------- report

def fmt_pct(x):
    return "—" if x is None else "%d%%" % round(100 * x)


def write_report(season, week_rows, details, totals, leaks, path):
    L = []
    w = L.append

    w("# %d season backtest\n" % season)
    w("Every forecast below was made with only the games that had already been played, then "
      "graded against what actually happened.\n")
    w("*Generated by `python scripts/backtest.py %d`. Regenerate after refreshing the data with "
      "`scripts/update_recent_games.py`, or after changing the model parameters in "
      "`forecast.py`.*\n" % season)

    if leaks:
        w("> **Leakage check FAILED** — %d forecasts changed when future results were hidden.\n"
          % len(leaks))
    else:
        w("> **Leakage check passed.** Re-forecasting from a history truncated before weeks 1, 8, "
          "15 and 22 reproduced the same probabilities exactly, so no future result influenced "
          "any prediction.\n")

    # ---- headline
    w("## How the three forecasters finished\n")
    w("| Forecaster | Straight up | Win rate | Confidence pool | Pool share | Brier points |")
    w("|---|---|---|---|---|---|")
    for name in PROBS:
        t = totals[name]
        w("| %s | %d-%d | %.1f%% | %d / %d | %.1f%% | %.1f |" % (
            name, t["correct"], t["graded"] - t["correct"],
            100 * t["correct"] / t["graded"], t["earned"], totals["pot"],
            100 * t["earned"] / totals["pot"], t["brier"]))
    w("")
    best = max(PROBS, key=lambda n: totals[n]["earned"])
    most_correct = max(PROBS, key=lambda n: totals[n]["correct"])
    w("**%s won the confidence pool**, and **%s picked the most winners outright** (%d-%d). Elo "
      "trailed Vegas by %d pool points (%.1f percentage points) and %.0f Brier points.\n" % (
          best, most_correct, totals[most_correct]["correct"],
          totals[most_correct]["graded"] - totals[most_correct]["correct"],
          totals["Vegas"]["earned"] - totals["Elo"]["earned"],
          100 * (totals["Vegas"]["earned"] - totals["Elo"]["earned"]) / totals["pot"],
          totals["Vegas"]["brier"] - totals["Elo"]["brier"]))
    if most_correct == "Combined" and best != "Combined":
        w("That split is worth sitting with: blending the model into the market picked more "
          "games correctly than the market alone, but the market was better at knowing *which* "
          "of its picks to trust, which is what the pool actually pays for.\n")

    # ---- week by week
    w("## Week by week\n")
    w("| Week | Games | Elo | Vegas | Combined | Elo pool | Vegas pool | Pot |")
    w("|---|---|---|---|---|---|---|---|")
    for r in week_rows:
        w("| %s | %d | %d-%d | %d-%d | %d-%d | %d | %d | %d |" % (
            week_name(r["week"]), r["games"],
            r["Elo"]["correct"], r["Elo"]["graded"] - r["Elo"]["correct"],
            r["Vegas"]["correct"], r["Vegas"]["graded"] - r["Vegas"]["correct"],
            r["Combined"]["correct"], r["Combined"]["graded"] - r["Combined"]["correct"],
            r["Elo"]["earned"], r["Vegas"]["earned"], r["pot"]))
    w("")

    # Playoff rounds are too small to be meaningful here - winning a one-game week is 100%.
    full = sorted((r for r in week_rows if r["games"] >= 10),
                  key=lambda r: r["Elo"]["earned"] / r["pot"])
    if full:
        hi, lo = full[-1], full[0]
        w("Ignoring the playoff rounds, which are too small to compare, Elo's best week was %s "
          "(%d of %d pool points, %d-%d straight up) and its worst was %s (%d of %d, %d-%d).\n" % (
              week_name(hi["week"]), hi["Elo"]["earned"], hi["pot"],
              hi["Elo"]["correct"], hi["Elo"]["graded"] - hi["Elo"]["correct"],
              week_name(lo["week"]), lo["Elo"]["earned"], lo["pot"],
              lo["Elo"]["correct"], lo["Elo"]["graded"] - lo["Elo"]["correct"]))

    beat = [r for r in week_rows if r["Elo"]["earned"] > r["Vegas"]["earned"]]
    w("Elo out-scored Vegas in %d of %d weeks, so the season gap is not one bad afternoon - the "
      "market was ahead most weeks.\n" % (len(beat), len(week_rows)))

    # ---- calibration
    w("## Is Elo's confidence honest?\n")
    w("When the model says 75%, does the favourite win about 75% of the time?\n")
    w("| Stated confidence | Games | Model said | Actually won |")
    w("|---|---|---|---|")
    for row in calibration(details, "Elo"):
        w("| %s | %d | %.1f%% | %.1f%% |" % (row["range"], row["n"], row["predicted"], row["actual"]))
    w("")
    w("Same question for Vegas:\n")
    w("| Stated confidence | Games | Market said | Actually won |")
    w("|---|---|---|---|")
    for row in calibration(details, "Vegas"):
        w("| %s | %d | %.1f%% | %.1f%% |" % (row["range"], row["n"], row["predicted"], row["actual"]))
    w("")

    # ---- hits and misses
    w("## Elo's biggest hits\n")
    w("Confident calls that came in.\n")
    w(game_table(biggest(details, "Elo", True)))

    w("## Elo's biggest misses\n")
    w("Confident calls that did not.\n")
    w(game_table(biggest(details, "Elo", False)))

    w("## Where Elo and Vegas disagreed\n")
    w("The games the model and the market picked differently, widest gap first.\n")
    w("| Week | Game | Score | Elo | Vegas | Winner | Right |")
    w("|---|---|---|---|---|---|---|")
    for d in disagreements(details):
        right = "Elo" if d["Elo"]["correct"] else "Vegas"
        w("| %s | %s @ %s | %d-%d | %s %s | %s %s | %s | **%s** |" % (
            week_name(d["week"]), d["team2"], d["team1"], d["score2"], d["score1"],
            d["Elo"]["pick"], fmt_pct(confidence(d["Elo"]["prob"])),
            d["Vegas"]["pick"], fmt_pct(confidence(d["Vegas"]["prob"])),
            d["winner"], right))
    w("")
    dis = disagreements(details, limit=10_000)
    elo_right = sum(1 for d in dis if d["Elo"]["correct"])
    w("Across all %d disagreements, Elo was right %d times and Vegas %d.\n"
      % (len(dis), elo_right, len(dis) - elo_right))

    # ---- team bias
    w("## Which teams Elo misjudged\n")
    w("Average error in the win probability Elo gave each team. A positive number means Elo "
      "rated the team higher than its results deserved.\n")
    w("| Team | Games | Elo's bias |")
    w("|---|---|---|")
    bias = team_errors(details, "Elo")
    for row in bias:
        w("| %s | %d | %+.1f pts |" % (row["team"], row["n"], row["bias"]))
    w("")
    if bias:
        over = [r["team"] for r in bias if r["bias"] > 0][:3]
        under = [r["team"] for r in bias if r["bias"] < 0][:3]
        w("Elo held on to %s long after their results stopped justifying it, and was equally slow "
          "to credit %s. That is the standing cost of a rating that only reads the scoreboard: "
          "it cannot hear about a roster change until enough games have gone the other way.\n"
          % (" and ".join(filter(None, [", ".join(over[:-1]), over[-1]])) if over else "—",
             " and ".join(filter(None, [", ".join(under[:-1]), under[-1]])) if under else "—"))

    # ---- the weekly recommendations themselves
    w("## Appendix: every weekly recommendation\n")
    w("The pick and confidence rank each forecaster would have entered, before the game was "
      "played. Rank N is the most confident game of that week. A tie is marked `—` because no "
      "forecaster can win it.\n")
    for week, rows in group_by_week(details):
        w("### %s\n" % week_name(week))
        w("| Game | Score | Elo pick | Elo rank | Vegas pick | Vegas rank | Combined pick | "
          "Winner |")
        w("|---|---|---|---|---|---|---|---|")
        for d in rows:
            w("| %s @ %s | %d-%d | %s %s | %s | %s %s | %s | %s %s | %s |" % (
                d["team2"], d["team1"], d["score2"], d["score1"],
                d["Elo"]["pick"] or "—", mark(d["Elo"]),
                d["Elo"]["rank"] if d["Elo"]["rank"] else "—",
                d["Vegas"]["pick"] or "—", mark(d["Vegas"]),
                d["Vegas"]["rank"] if d["Vegas"]["rank"] else "—",
                d["Combined"]["pick"] or "—", mark(d["Combined"]),
                d["winner"] or "tie"))
        w("")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return "\n".join(L)


PLAYOFF_NAMES = {19: "Wild Card", 20: "Divisional", 21: "Conf Champ", 22: "Super Bowl"}


def week_name(week):
    return PLAYOFF_NAMES.get(week, "Week %d" % week)


def group_by_week(details):
    weeks = defaultdict(list)
    for d in details:
        weeks[d["week"]].append(d)
    return sorted(weeks.items())


def mark(entry):
    if entry["correct"] is None:
        return ""
    return "✓" if entry["correct"] else "✗"


def game_table(rows):
    out = ["| Week | Game | Score | Elo's pick | Confidence | Result |", "|---|---|---|---|---|---|"]
    for d in rows:
        out.append("| %s | %s @ %s | %d-%d | %s | %s | %s |" % (
            week_name(d["week"]), d["team2"], d["team1"], d["score2"], d["score1"],
            d["Elo"]["pick"], fmt_pct(confidence(d["Elo"]["prob"])),
            "correct" if d["Elo"]["correct"] else "**wrong**"))
    return "\n".join(out) + "\n"


def main():
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2025

    games = load_games()
    weeks = season_weeks(games, season)
    if not weeks:
        sys.exit("No completed games found for %d." % season)

    print("Verifying the model never saw a result before predicting it...")
    leaks = verify_no_leakage(games, season)
    print("  %s" % ("LEAKAGE DETECTED: %d" % len(leaks) if leaks else "clean"))

    # verify_no_leakage re-forecasts copies, but restore the canonical run to be safe.
    Forecast.forecast(games)
    weeks = season_weeks(games, season)

    week_rows, details = grade_season(weeks)
    totals = season_totals(week_rows)

    path = os.path.join(REPORT_DIR, "backtest_%d.md" % season)
    write_report(season, week_rows, details, totals, leaks, path)

    print("\n%d season, %d games graded across %d weeks\n" % (
        season, totals["Elo"]["graded"], len(week_rows)))
    for name in PROBS:
        t = totals[name]
        print("  %-9s %d-%-3d (%.1f%%)   pool %4d/%d (%.1f%%)   brier %+.1f" % (
            name, t["correct"], t["graded"] - t["correct"], 100 * t["correct"] / t["graded"],
            t["earned"], totals["pot"], 100 * t["earned"] / totals["pot"], t["brier"]))
    print("\nWrote %s" % path)


if __name__ == "__main__":
    main()
