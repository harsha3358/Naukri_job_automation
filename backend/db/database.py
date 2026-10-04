import logging
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

from sqlalchemy import Column, create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from backend.config import config
from backend.core.clock import utcnow
from backend.db.models import AppSettings, Base, CandidateProfile

log = logging.getLogger(__name__)

engine = create_engine(f"sqlite:///{config.db_path}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    # WAL lets the dashboard read while a worker writes.
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def init_db() -> None:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    config.resumes_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    added = add_missing_columns()
    if added:
        log.info("Database upgraded, columns added: %s", ", ".join(added))
    with SessionLocal() as db:
        if db.get(CandidateProfile, 1) is None:
            db.add(CandidateProfile(id=1))
        if db.get(AppSettings, 1) is None:
            db.add(AppSettings(id=1))
        db.commit()


def add_missing_columns() -> list[str]:
    """Bring a database made by an older version up to date, keeping everything in it.

    `create_all` makes missing tables but never changes an existing one, so a column added to a
    model would be missing from a user's database. This adds such columns. It only ever adds:
    a new column must allow empty values or have a simple default (text, number, yes/no).
    Renaming or removing a column needs a hand-written migration.
    """
    inspector = inspect(engine)
    missing = [
        column
        for table in Base.metadata.sorted_tables
        for column in table.columns
        if column.name not in {existing["name"] for existing in inspector.get_columns(table.name)}
    ]
    if not missing:
        return []

    backup = _backup_database()
    log.info("Database copied to %s before upgrading", backup)
    with engine.begin() as connection:
        for column in missing:
            definition = f'"{column.name}" {column.type.compile(engine.dialect)}'
            if not column.nullable:
                definition += f" NOT NULL DEFAULT {_default_literal(column)}"
            connection.execute(text(f'ALTER TABLE "{column.table.name}" ADD COLUMN {definition}'))
    return [f"{column.table.name}.{column.name}" for column in missing]


def _backup_database() -> Path:
    """A full copy of the database, taken with SQLite's own backup so it is consistent."""
    target = config.data_dir / f"data-before-upgrade-{utcnow():%Y%m%d-%H%M%S}.db"
    with closing(sqlite3.connect(config.db_path)) as source, closing(sqlite3.connect(target)) as copy:
        source.backup(copy)
    return target


def _default_literal(column: Column) -> str:
    default = column.default.arg if column.default is not None and column.default.is_scalar else None
    if isinstance(default, bool):
        return "1" if default else "0"
    if isinstance(default, (int, float)):
        return str(default)
    if isinstance(default, str):
        return "'" + str(default).replace("'", "''") + "'"
    raise RuntimeError(
        f"{column.table.name}.{column.name} is a new required column without a simple default, "
        "so an existing database cannot be upgraded. Give it a default or allow it to be empty."
    )


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db
