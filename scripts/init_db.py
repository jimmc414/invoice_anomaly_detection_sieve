"""Initialize PostgreSQL schema for the Invoice Anomaly Sieve."""
from __future__ import annotations

import os
import pathlib

from sqlalchemy import create_engine, text

DSN = os.getenv("DB_DSN", "postgresql+psycopg://postgres:postgres@localhost:5432/sieve")
SQL_PATH = pathlib.Path("app/schema.sql")


def main() -> None:
    engine = create_engine(DSN, future=True)
    sql = SQL_PATH.read_text()
    with engine.begin() as connection:
        for statement in filter(None, (stmt.strip() for stmt in sql.split(";"))):
            if statement:
                connection.execute(text(statement))
    print("DB initialized.")


if __name__ == "__main__":  # pragma: no cover - script entry point
    main()
