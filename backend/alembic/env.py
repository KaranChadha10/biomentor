# backend/alembic/env.py
from __future__ import annotations
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import URL

# --- Make sure "app" is importable (points to backend/) ---
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

# --- Load .env so env vars are available ---
from dotenv import load_dotenv
import os
load_dotenv(BASE_DIR / ".env")

# --- Single source of truth for Base ---
from app.services.db import Base
import app.models.question  # noqa: F401  (register tables)

# Build DB URL from env (handles '@' safely)
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "biomentor")
DB_USER = os.getenv("DB_USER", "biomentor")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

APP_URL = URL.create(
    drivername="postgresql+psycopg",
    username=DB_USER,
    password=DB_PASSWORD,  # raw password; URL.create handles escaping
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME,
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    # IMPORTANT: pass URL directly here; do NOT set_main_option (avoids % interpolation)
    context.configure(
        url=APP_URL.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        APP_URL.render_as_string(hide_password=False),
        poolclass=pool.NullPool,
        future=True,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
