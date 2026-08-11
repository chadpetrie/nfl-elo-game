import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


@pytest.fixture(scope="session", autouse=True)
def temp_db(tmp_path_factory):
    """ Point the app at a throwaway database before anything imports it.

    app.main runs init_db() at import time, so the redirect has to happen first or the tests
    would read and write the picks the user actually saved in the real app.
    """
    from app import db, paths

    test_db = tmp_path_factory.mktemp("data") / "test.db"
    db.DB_PATH = test_db
    paths.DB_PATH = test_db
    db.init_db()
    yield test_db


@pytest.fixture(scope="session")
def client(temp_db):
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_state(temp_db):
    """ Every test starts from default parameters and no saved picks """
    from app import db, engine, main

    conn = db.get_conn()
    try:
        conn.execute("DELETE FROM user_picks")
        conn.commit()
    finally:
        conn.close()
    db.save_params(dict(db.DEFAULT_PARAMS))
    engine.invalidate_cache()
    main._invalidate_scoreboard()
    yield


@pytest.fixture(scope="session")
def model():
    from app import db, engine

    return engine.get_model(dict(db.DEFAULT_PARAMS))
