"""Alembic env.py – supports both sync (Alembic CLI) and async execution."""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the app importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import get_settings
from app.persistence import models as _models  # noqa: F401 – force model registration
from app.persistence.database import Base

config = context.config

# Use the exported environment variable when present, otherwise load the
# repository root .env through the same settings object used by the API.
db_url = os.environ.get("DATABASE_CONNECTION_URL") or get_settings().sync_database_url
if "+asyncpg" in db_url:
    db_url = db_url.replace("+asyncpg", "")
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode – emit SQL to stdout."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
