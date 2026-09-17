import math
import threading
from datetime import date

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import db, engine, ranking, scoring, totals
from .models import ParamsIn, PickIn, TotalIn
from .paths import FRONTEND_DIST

db.init_db()

app = FastAPI(title="NFL Predictions")


def _json_safe(value):
    """ Replaces the values json.dumps refuses to emit with something it will """
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


@app.exception_handler(RequestValidationError)
def validation_error(request: Request, exc: RequestValidationError):
    """ FastAPI's default handler echoes the rejected input back in the error body. When that
    input is Infinity or NaN - which json.loads accepts but json.dumps refuses - rendering the
    422 raises, and the client sees a 500 instead of the validation message it earned. """
    return JSONResponse(status_code=422, content={"detail": _json_safe(exc.errors())})

SOURCES = ("elo", "vegas", "combined")
PROB_FIELD = {"elo": "elo_prob", "vegas": "vegas_prob", "combined": "combined_prob"}

_scoreboard_lock = threading.Lock()
_scoreboard_cache = {}


def _game_out(g, ranks, pick):
    out = {
        "game_id": g["game_id"],
        "date": g["date"],
        "gametime": g.get("gametime"),
        "game_type": g.get("game_type"),
        "team1": g["team1"],
        "team2": g["team2"],
        "score1": g["score1"],
        "score2": g["score2"],
        "result1": g["result1"],
        "elo1": round(g["my_elo1"], 1) if g.get("my_elo1") is not None else None,
        "elo2": round(g["my_elo2"], 1) if g.get("my_elo2") is not None else None,
        "user_pick": pick,
    }
    for source in SOURCES:
        field = PROB_FIELD[source]
        out["%s_prob" % source] = g[field]
        out["%s_pick" % source] = ranking.winner(g, field)
        out["%s_rank" % source] = ranks[source].get(g["game_id"])
    return out


def _week_summary(annotated, picks):
    """ Per-source record and confidence-pool haul for the games in this week that have finished.

    Ranked over the final games only, matching how the scoreboard totals the season, so a week's
    numbers here always add up to what the Scoreboard tab shows.
    """
    final = [g for g in annotated if scoring.is_final(g)]
    scorable = [g for g in final if scoring.is_scorable(g)]
    summary = {"played": len(final), "total": len(annotated), "pot": scoring.week_pot(final)}

    for source in SOURCES:
        field = PROB_FIELD[source]
        earned, pot = scoring.pool_points_for_week(final, field) if final else (0, 0)
        summary[source] = {
            "correct": sum(1 for g in scorable if ranking.winner(g, field) == scoring.actual_winner(g)),
            "graded": sum(1 for g in scorable if g.get(field) is not None),
            "earned": earned,
            "possible": pot,
        }

    earned, pot, graded = scoring.pool_points_for_user(final, picks)
    summary["user"] = {
        "correct": sum(1 for g in scorable
                       if picks.get(g["game_id"], {}).get("team") == scoring.actual_winner(g)),
        "graded": graded,
        "earned": earned,
        "possible": pot,
    }
    return summary


@app.get("/api/seasons")
def list_seasons():
    return engine.get_model(db.get_params()).seasons


@app.get("/api/weeks")
def list_weeks(season: int):
    model = engine.get_model(db.get_params())
    weeks = model.weeks_for(season)
    if not weeks:
        raise HTTPException(status_code=404, detail="No weekly schedule for season %d" % season)
    # The first week with a game still unplayed is the one you'd actually open the app to work
    # on; once a season is fully final (games all graded) there's no such week, so fall back to
    # the last one played rather than always defaulting back to Week 1. A cancelled game (e.g.
    # 2022's Bills-Bengals) would break this if it ever sat in the data with a permanent null
    # result, but update_recent_games.py's source drops cancelled games entirely rather than
    # keeping them unresolved - see test_completed_seasons_have_a_full_schedule.
    current = next(
        (w for w in weeks if any(g["result1"] is None for g in model.week_games(season, w))),
        weeks[-1],
    )
    return [{"week": w, "game_type": model.week_types[(season, w)],
             "label": ranking.week_label(w, model.week_types[(season, w)]),
             "current": w == current} for w in weeks]


@app.get("/api/games")
def list_games(season: int, week: int):
    params = db.get_params()
    model = engine.get_model(params)
    week_games = model.week_games(season, week)
    if not week_games:
        raise HTTPException(status_code=404, detail="No games for season %d week %d" % (season, week))

    picks = db.get_all_picks()
    annotated = ranking.annotate(week_games, params["blend_weight"])
    ranks = {source: ranking.rank_week(annotated, PROB_FIELD[source]) for source in SOURCES}

    games = [_game_out(g, ranks, picks.get(g["game_id"])) for g in annotated]
    games.sort(key=lambda r: (r["date"], r["gametime"] or "", r["game_id"]))
    return {"games": games, "summary": _week_summary(annotated, picks)}


@app.put("/api/games/{game_id}/pick")
def save_pick(game_id: str, pick: PickIn):
    game = _find_game(game_id)
    if pick.team not in (game["team1"], game["team2"]):
        raise HTTPException(
            status_code=422,
            detail="%s is not playing in %s (%s vs %s)" % (pick.team, game_id, game["team1"], game["team2"]),
        )
    db.save_pick(game_id, pick.team, pick.confidence)
    _invalidate_scoreboard()
    return {"ok": True, "game_id": game_id, "team": pick.team, "confidence": pick.confidence}


@app.delete("/api/games/{game_id}/pick")
def clear_pick(game_id: str):
    db.delete_pick(game_id)
    _invalidate_scoreboard()
    return {"ok": True}


def _find_game(game_id):
    game = engine.get_model(db.get_params()).by_id.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Unknown game %s" % game_id)
    return game


def _is_monday(date_str):
    return date.fromisoformat(date_str).weekday() == 0


@app.get("/api/totals")
def list_totals(season: int, week: int):
    """ Predicted final combined-score totals for this week's Monday game(s) - usually one, a
    Monday doubleheader gives two, and most weeks give none. """
    model = engine.get_model(db.get_params())
    monday_games = [g for g in model.week_games(season, week) if _is_monday(g["date"])]
    if not monday_games:
        return {"games": []}

    history = totals.team_history(model.games)
    out = []
    for g in monday_games:
        actual_total = g["score1"] + g["score2"] if g["score1"] is not None else None
        out.append({
            "game_id": g["game_id"],
            "team1": g["team1"],
            "team2": g["team2"],
            "date": g["date"],
            "gametime": g.get("gametime"),
            "score1": g["score1"],
            "score2": g["score2"],
            "actual_total": actual_total,
            "methods": totals.predict(g, history, model.games),
            "user_total": db.get_total(g["game_id"]),
        })
    out.sort(key=lambda r: (r["date"], r["gametime"] or "", r["game_id"]))
    return {"games": out}


@app.put("/api/totals/{game_id}")
def save_total(game_id: str, body: TotalIn):
    _find_game(game_id)
    db.save_total(game_id, body.predicted_total)
    return {"ok": True, "game_id": game_id, "predicted_total": body.predicted_total}


@app.delete("/api/totals/{game_id}")
def clear_total(game_id: str):
    db.delete_total(game_id)
    return {"ok": True}


@app.get("/api/params")
def get_params():
    return db.get_params()


@app.put("/api/params")
def update_params(params: ParamsIn):
    db.save_params(params.model_dump())
    engine.invalidate_cache()
    _invalidate_scoreboard()
    return db.get_params()


@app.get("/api/rankings")
def rankings(season: int | None = None):
    """ Current Elo ratings, limited to teams that actually played in the given season """
    model = engine.get_model(db.get_params())
    if not model.seasons:
        return []
    season = season or model.seasons[0]
    active = set()
    for week in model.weeks_for(season):
        for g in model.week_games(season, week):
            active.add(g["team1"])
            active.add(g["team2"])
    rated = [{"team": t, "elo": round(model.teams[t], 1)} for t in active if t in model.teams]
    rated.sort(key=lambda r: -r["elo"])
    for i, row in enumerate(rated):
        row["rank"] = i + 1
    return rated


def _invalidate_scoreboard():
    with _scoreboard_lock:
        _scoreboard_cache.clear()


@app.get("/api/scoreboard")
def scoreboard():
    params = db.get_params()
    model = engine.get_model(params)
    picks = db.get_all_picks()

    key = (tuple(sorted(params.items())),
           tuple(sorted((gid, p["team"], p["confidence"]) for gid, p in picks.items())))
    with _scoreboard_lock:
        if key in _scoreboard_cache:
            return _scoreboard_cache[key]

    result = _build_scoreboard(model, params, picks)
    with _scoreboard_lock:
        _scoreboard_cache.clear()  # only the current params/picks combination is ever asked for
        _scoreboard_cache[key] = result
    return result


def _build_scoreboard(model, params, picks):
    blend = params["blend_weight"]

    # Brier scoring runs over the whole 1920-present file; only the model probabilities can be
    # scored this way, and only 2021+ has a genuine market line to compare against.
    brier = {}
    for g in model.games:
        if not scoring.is_scorable(g):
            continue
        season = g["season"]
        row = brier.setdefault(season, {"elo": 0.0, "vegas": None, "fte": None})
        row["elo"] += scoring.brier_points(g["my_prob1"], g["result1"], g["playoff"])
        if g["elo_prob1"] is not None:
            benchmark = "vegas" if season >= scoring.FIRST_VEGAS_SEASON else "fte"
            if row[benchmark] is None:
                row[benchmark] = 0.0
            row[benchmark] += scoring.brier_points(g["elo_prob1"], g["result1"], g["playoff"])

    # Confidence-pool scoring needs games grouped into weeks, which only exists for 2021+.
    pool = {}
    user_picks_made = {}
    for (season, week) in sorted(model.by_season_week):
        week_games = model.week_games(season, week)
        final = [g for g in ranking.annotate(week_games, blend) if scoring.is_final(g)]
        if not final:
            continue

        row = pool.setdefault(season, {s: [0, 0] for s in SOURCES + ("user",)})
        pot = scoring.week_pot(final)
        for source in SOURCES:
            row[source][0] += scoring.pool_points_for_week(final, PROB_FIELD[source])[0]
            row[source][1] += pot

        user_earned, user_pot, user_graded = scoring.pool_points_for_user(final, picks)
        row["user"][0] += user_earned
        row["user"][1] += user_pot
        user_picks_made[season] = user_picks_made.get(season, 0) + user_graded

    seasons = []
    for season in sorted(brier):
        b = brier[season]
        p = pool.get(season)
        row = {
            "season": season,
            "elo_points": round(b["elo"], 1),
            "vegas_points": round(b["vegas"], 1) if b["vegas"] is not None else None,
            "fte_points": round(b["fte"], 1) if b["fte"] is not None else None,
        }
        for source in SOURCES + ("user",):
            if p and p[source][1]:
                row["%s_pool" % source] = {"earned": p[source][0], "possible": p[source][1]}
                if source == "user":
                    row["user_pool"]["graded"] = user_picks_made.get(season, 0)
            else:
                row["%s_pool" % source] = None
        seasons.append(row)
    return {"seasons": seasons, "first_vegas_season": scoring.FIRST_VEGAS_SEASON}


FAVICON = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    b'<rect width="64" height="64" rx="12" fill="#0b1220"/>'
    b'<ellipse cx="32" cy="32" rx="20" ry="12" fill="#8b4a2b" stroke="#f4f4f5" stroke-width="3"/>'
    b'<path d="M22 32h20M28 27v10M36 27v10" stroke="#f4f4f5" stroke-width="3" stroke-linecap="round"/>'
    b'</svg>'
)


@app.get("/favicon.ico")
def favicon():
    return Response(content=FAVICON, media_type="image/svg+xml")


if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
