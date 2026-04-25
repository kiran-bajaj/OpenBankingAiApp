"""
Database engine, session factory, and lifecycle helpers.

DATABASE_URL controls the backend:
  postgresql://postgres:postgres@localhost:5432/openbanking  (default)
  sqlite:///./openbanking.db                                 (zero-setup fallback)

The rest of the app is dialect-agnostic — switching is a single env-var change.

load_dotenv() is called here so this module is safe to import standalone
(e.g. mcp_server.py, tests) without the caller needing to load .env first.
"""
import logging
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()  # idempotent — safe to call multiple times

log = logging.getLogger(__name__)

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/openbanking",
)

# SQLite needs check_same_thread=False; PostgreSQL needs pool settings.
_is_sqlite = DATABASE_URL.startswith("sqlite")

if _is_sqlite:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=False,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Create all tables if they don't exist. Safe to call on every startup."""
    from db import models  # noqa: F401 — ensures models are registered with Base
    Base.metadata.create_all(bind=engine)
    log.info("Database tables ready (%s)", "sqlite" if _is_sqlite else "postgresql")


def check_db_connection() -> bool:
    """Return True if the database is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
