"""Additive upgrades for existing NOIR databases. Safe to run again."""
from pathlib import Path
from .db import execute, query


def migrate():
    for table, column in (("stations", "deleted_at"), ("cafe_sessions", "planned_end_at")):
        exists = query("SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                       "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s",
                       (table, column), one=True)
        if not exists:
            execute(f"ALTER TABLE {table} ADD COLUMN {column} DATETIME(6) NULL")

    script = (Path(__file__).resolve().parent.parent / "database" / "platform.sql").read_text()
    for statement in script.split(";"):
        if statement.strip():
            execute(statement)
