GAME_TYPE_LABELS = {"WC": "Wild Card", "DIV": "Divisional", "CON": "Conference Championship", "SB": "Super Bowl"}


def week_label(week, game_type):
    if game_type == "REG":
        return "Week %d" % week
    return GAME_TYPE_LABELS.get(game_type, game_type)


def confidence(prob):
    return max(prob, 1 - prob)


def winner(game, prob_field):
    prob = game.get(prob_field)
    if prob is None:
        return None
    return game["team1"] if prob >= 0.5 else game["team2"]


def annotate(games, blend_weight):
    """ Returns copies of each game carrying elo_prob/vegas_prob/combined_prob.

    Copies rather than in-place edits because the caller's games come from a process-wide cache
    that concurrent requests share; blend_weight differs per request only in principle, but
    writing derived fields back into the cache makes that a real race.
    """
    out = []
    for g in games:
        elo_prob = g["my_prob1"]
        vegas_prob = g["elo_prob1"]
        combined = elo_prob if vegas_prob is None else blend_weight * elo_prob + (1 - blend_weight) * vegas_prob
        out.append({**g, "elo_prob": elo_prob, "vegas_prob": vegas_prob, "combined_prob": combined})
    return out


def rank_week(games, prob_field):
    """ Ranks games 1..N by confidence in prob_field, N = most confident. Returns {game_id: rank}. """
    ranked = [g for g in games if g.get(prob_field) is not None]
    ranked.sort(key=lambda g: (-confidence(g[prob_field]), g.get("gametime") or "", g.get("game_id") or ""))
    n = len(ranked)
    return {g["game_id"]: n - i for i, g in enumerate(ranked)}
