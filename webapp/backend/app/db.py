import sqlite3
from datetime import datetime, timezone

from .paths import DB_PATH

DEFAULT_PARAMS = {"hfa": 65.0, "k": 20.0, "revert": 1 / 3.0, "mov_base": 2.2, "blend_weight": 0.5}

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
        row = conn.execute("SELECT id FROM model_params WHERE id = 1").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO model_params (id, hfa, k, revert, mov_base, blend_weight) VALUES (1, ?, ?, ?, ?, ?)",
                (DEFAULT_PARAMS["hfa"], DEFAULT_PARAMS["k"], DEFAULT_PARAMS["revert"],
                 DEFAULT_PARAMS["mov_base"], DEFAULT_PARAMS["blend_weight"]),
            )
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
