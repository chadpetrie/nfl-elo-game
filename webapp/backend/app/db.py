import sqlite3
from datetime import datetime, timezone

from .paths import DB_PATH

DEFAULT_PARAMS = {"hfa": 32.0, "k": 20.0, "revert": 1 / 3.0, "mov_base": 2.2, "blend_weight": 0.5}

# The shipped hfa default was recalibrated from 65 to 32 (see forecast.py). An install that
# already has a saved model_params row keeps whatever it has - init_db() below only inserts a
# fresh row - so without this, every existing app.db would silently stay on the old, now
# de-calibrated value forever. Only migrate a row that's still exactly on the old default; a row
# where someone deliberately set hfa to 65.0 themselves is indistinguishable from that and gets
# carried along too, but that's a narrow edge case against leaving every existing install stuck.
PREVIOUS_DEFAULT_HFA = 65.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS model_params (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    hfa REAL NOT NULL,
    k REAL NOT NULL,
    revert REAL NOT NULL,
    mov_base REAL NOT NULL,
    blend_weight REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS user_picks (
    game_id TEXT PRIMARY KEY,
    team TEXT NOT NULL,
    confidence INTEGER,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_totals (
    game_id TEXT PRIMARY KEY,
    predicted_total REAL NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        row = conn.execute("SELECT hfa FROM model_params WHERE id = 1").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO model_params (id, hfa, k, revert, mov_base, blend_weight) VALUES (1, ?, ?, ?, ?, ?)",
                (DEFAULT_PARAMS["hfa"], DEFAULT_PARAMS["k"], DEFAULT_PARAMS["revert"],
                 DEFAULT_PARAMS["mov_base"], DEFAULT_PARAMS["blend_weight"]),
            )
        elif row["hfa"] == PREVIOUS_DEFAULT_HFA:
            conn.execute("UPDATE model_params SET hfa = ? WHERE id = 1", (DEFAULT_PARAMS["hfa"],))
        conn.commit()
    finally:
        conn.close()


def get_params():
    conn = get_conn()
    try:
        row = conn.execute("SELECT hfa, k, revert, mov_base, blend_weight FROM model_params WHERE id = 1").fetchone()
        return dict(row) if row else dict(DEFAULT_PARAMS)
    finally:
        conn.close()


def save_params(params):
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE model_params SET hfa=?, k=?, revert=?, mov_base=?, blend_weight=? WHERE id = 1",
            (params["hfa"], params["k"], params["revert"], params["mov_base"], params["blend_weight"]),
        )
        conn.commit()
    finally:
        conn.close()


def get_pick(game_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT team, confidence FROM user_picks WHERE game_id = ?", (game_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all_picks():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT game_id, team, confidence FROM user_picks").fetchall()
        return {row["game_id"]: {"team": row["team"], "confidence": row["confidence"]} for row in rows}
    finally:
        conn.close()


def delete_pick(game_id):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM user_picks WHERE game_id = ?", (game_id,))
        conn.commit()
    finally:
        conn.close()


def save_pick(game_id, team, confidence):
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO user_picks (game_id, team, confidence, updated_at) VALUES (?, ?, ?, ?)
               ON CONFLICT(game_id) DO UPDATE SET team=excluded.team, confidence=excluded.confidence, updated_at=excluded.updated_at""",
            (game_id, team, confidence, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def get_total(game_id):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT predicted_total FROM user_totals WHERE game_id = ?", (game_id,)).fetchone()
        return row["predicted_total"] if row else None
    finally:
        conn.close()


def save_total(game_id, predicted_total):
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO user_totals (game_id, predicted_total, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(game_id) DO UPDATE SET
                   predicted_total=excluded.predicted_total, updated_at=excluded.updated_at""",
            (game_id, predicted_total, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def delete_total(game_id):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM user_totals WHERE game_id = ?", (game_id,))
        conn.commit()
    finally:
        conn.close()
