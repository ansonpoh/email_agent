from app.config import settings

DB_SCHEMA = settings.database_schema


def schema_fk(table_name: str, column_name: str = "id") -> str:
    return f"{DB_SCHEMA}.{table_name}.{column_name}"
