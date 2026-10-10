"""Additive, idempotent extension migration; never alter Plane core tables."""
from sqlalchemy import inspect, text
from .models import Base


def migrate(engine):
    # Serialize extension DDL on PostgreSQL. SQLite has one writer per database.
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(872346112)"))
        inspector = inspect(connection)
        existing = set(inspector.get_table_names())
        for table in Base.metadata.sorted_tables:
            if not table.name.startswith("yt_"):
                raise RuntimeError("Extension schema must use the yt_ prefix")
            if table.name not in existing:
                continue
            columns = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in columns:
                    continue
                sql_type = column.type.compile(dialect=engine.dialect)
                default = ""
                if column.server_default is not None:
                    value = str(column.server_default.arg).replace("'", "''")
                    default = f" DEFAULT '{value}'"
                if not column.nullable and not default:
                    raise RuntimeError(f"No safe additive default for {table.name}.{column.name}")
                nullability = "" if column.nullable else " NOT NULL"
                connection.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {sql_type}{default}{nullability}'))
        Base.metadata.create_all(connection)
