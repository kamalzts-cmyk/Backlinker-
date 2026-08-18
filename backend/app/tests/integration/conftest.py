
import pytest

from app.core.config import settings
from app.db.base import Base, make_engine


@pytest.fixture
def test_db_url() -> str:
    return (
        f"postgresql+psycopg://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}_test"
    )


@pytest.fixture(autouse=True)
def _use_test_database(monkeypatch, test_db_url):
    """Point app.db.base at the dedicated Postgres test database (not the
    dev database) and reset schema+engine for each test so crawl runs are
    isolated and inspectable.
    """
    import app.crawler.repository  # noqa: F401 ensures models are imported
    import app.db.base as db_base

    engine = make_engine(test_db_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    from sqlalchemy.orm import sessionmaker

    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr(db_base, "engine", engine)
    monkeypatch.setattr(db_base, "SessionLocal", session_factory)

    yield engine

    engine.dispose()
