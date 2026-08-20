"""FastAPI dependencies. Route handlers use plain sync SQLAlchemy
sessions (FastAPI runs sync `def` route functions in a threadpool
automatically) -- consistent with the rest of the codebase, which never
introduced an async DB engine (see app/db/base.py).
"""

from collections.abc import Iterator

from sqlalchemy.orm import Session

import app.db.base as db_base


def get_db() -> Iterator[Session]:
    # Resolved at call time (not `from ... import SessionLocal`) so tests
    # can monkeypatch app.db.base.SessionLocal to point at a test
    # database -- same reasoning as session_scope() in app/db/base.py.
    session = db_base.SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
