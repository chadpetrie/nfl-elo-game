""" db.py's own logic: schema creation, defaults, and the one-time hfa migration.

Uses its own throwaway sqlite file per test rather than the shared session-scoped test database
every other test in this suite reads and writes, since these tests need to control exactly what
a database looked like *before* init_db() runs.
"""

import sqlite3

import pytest

from app import db


@pytest.fixture
def isolated_db_path(tmp_path):
    previous = db.DB_PATH
    db.DB_PATH = tmp_path / "isolated.db"
    yield db.DB_PATH
    db.DB_PATH = previous


def _hfa(path):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute("SELECT hfa FROM model_params WHERE id = 1").fetchone()[0]
    finally:
        conn.close()


class TestInitDbMigration:
    def test_a_fresh_database_gets_the_current_default(self, isolated_db_path):
        db.init_db()
        assert _hfa(isolated_db_path) == db.DEFAULT_PARAMS["hfa"]

    def test_a_database_still_on_the_previous_default_is_migrated_forward(self, isolated_db_path):
        db.init_db()  # first run: seeds the row
        conn = sqlite3.connect(str(isolated_db_path))
        conn.execute("UPDATE model_params SET hfa = ? WHERE id = 1", (db.PREVIOUS_DEFAULT_HFA,))
        conn.commit()
        conn.close()

        db.init_db()  # simulates restarting the app after DEFAULT_PARAMS["hfa"] changed
        assert _hfa(isolated_db_path) == db.DEFAULT_PARAMS["hfa"]

    def test_a_deliberately_customized_value_is_left_alone(self, isolated_db_path):
        db.init_db()
        conn = sqlite3.connect(str(isolated_db_path))
        conn.execute("UPDATE model_params SET hfa = ? WHERE id = 1", (100.0,))
        conn.commit()
        conn.close()

        db.init_db()
        assert _hfa(isolated_db_path) == 100.0
