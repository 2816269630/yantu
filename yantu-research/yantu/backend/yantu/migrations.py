"""Additive, idempotent extension migration; never alter Plane core tables."""
from sqlalchemy import inspect, text
from .models import Base


def relax_resource_team(engine):
    """Preserve IDs and foreign keys while allowing team-independent personal files."""
    with engine.connect() as connection:
        inspector = inspect(connection)
        if "yt_resources" not in inspector.get_table_names():
            return
        columns = inspector.get_columns("yt_resources")
        if next(c for c in columns if c["name"] == "team_id")["nullable"]:
            return
        connection.commit()
        if engine.dialect.name == "postgresql":
            with connection.begin():
                connection.execute(text('ALTER TABLE yt_resources ALTER COLUMN team_id DROP NOT NULL'))
        elif engine.dialect.name == "sqlite":
            # Do not rename the old table: SQLite would rewrite dependent foreign keys.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
            try:
                with connection.begin():
                    ddl = connection.exec_driver_sql("SELECT sql FROM sqlite_master WHERE type='table' AND name='yt_resources'").scalar_one()
                    import re
                    ddl = re.sub(r'CREATE TABLE\s+"?yt_resources"?', 'CREATE TABLE yt_resources_upgrade', ddl, count=1)
                    ddl = re.sub(r'(\bteam_id\s+[^,\n]+?)\s+NOT NULL', r'\1', ddl, count=1)
                    indexes = connection.exec_driver_sql("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='yt_resources' AND sql IS NOT NULL").scalars().all()
                    connection.exec_driver_sql(ddl)
                    names = ','.join('"'+c['name']+'"' for c in columns)
                    connection.exec_driver_sql(f'INSERT INTO yt_resources_upgrade ({names}) SELECT {names} FROM yt_resources')
                    connection.exec_driver_sql('DROP TABLE yt_resources')
                    connection.exec_driver_sql('ALTER TABLE yt_resources_upgrade RENAME TO yt_resources')
                    for index in indexes:
                        connection.exec_driver_sql(index)
                    if connection.exec_driver_sql("PRAGMA foreign_key_check").first():
                        raise RuntimeError("Resource migration foreign-key validation failed")
            finally:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.commit()
        else:
            raise RuntimeError("Personal drive migration requires PostgreSQL or SQLite")


def migrate(engine):
    relax_resource_team(engine)
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
