# app/services/db.py
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.engine import URL

from app.config import settings

# ---- Single source of truth for Base (models must import from here)
Base = declarative_base()

# Fail fast if host is blank
if not settings.DB_HOST:
    raise RuntimeError("[DB] DB_HOST is empty! Check backend/.env")

# Build URL safely (handles '@' in password)
url = URL.create(
    drivername="postgresql+psycopg",   # psycopg3
    username=settings.DB_USER,
    password=settings.DB_PASSWORD,
    host=settings.DB_HOST,
    port=settings.DB_PORT,
    database=settings.DB_NAME,
)

def _mask(u: URL) -> str:
    user = (u.username or "") + (":" if u.username else "")
    host = u.host or "<NONE>"
    port = f":{u.port}" if u.port else ""
    db = f"/{u.database}" if u.database else ""
    return f"{u.drivername}://{user}****@{host}{port}{db}"

print("[DB] Using", _mask(url))

engine = create_engine(url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

@contextmanager
def get_session():
    """Yield a SQLAlchemy session as a context manager."""
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()

def init_db():
    """Ping DB, import models to register metadata, then create tables."""
    print("[DB] init_db: starting connection test…")
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("[DB] init_db: connection OK, creating tables if missing…")

    # IMPORTANT: import models INSIDE this function to avoid circular imports
    import app.models.question  # noqa: F401

    Base.metadata.create_all(bind=engine)
    print("[DB] init_db: tables ensured.")
