"""Analiza el esquema de base de datos y extrae estructura, relaciones y datos de muestra."""

from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Inspector

from docgen.models import ColumnInfo, DatabaseSchema, TableInfo


_MAX_SAMPLE_ROWS = 3
_MAX_TABLES = 50


def analyze_database(connection_string: str) -> DatabaseSchema:
    engine = create_engine(connection_string, echo=False)

    with engine.connect() as conn:
        insp: Inspector = inspect(engine)
        dialect = engine.dialect.name

        tables: list[TableInfo] = []
        relationships: list[dict[str, str]] = []

        table_names = insp.get_table_names()[:_MAX_TABLES]

        for table_name in table_names:
            columns = _get_columns(insp, table_name)
            row_count = _get_row_count(conn, table_name)
            sample_rows = _get_sample_rows(conn, table_name, _MAX_SAMPLE_ROWS)

            tables.append(
                TableInfo(
                    name=table_name,
                    columns=columns,
                    row_count=row_count,
                    sample_rows=sample_rows,
                )
            )

            # Recolectar relaciones FK
            for fk in insp.get_foreign_keys(table_name):
                relationships.append(
                    {
                        "from_table": table_name,
                        "from_columns": ", ".join(fk["constrained_columns"]),
                        "to_table": fk["referred_table"],
                        "to_columns": ", ".join(fk["referred_columns"]),
                    }
                )

    return DatabaseSchema(
        dialect=dialect,
        tables=tables,
        relationships=relationships,
    )


def _get_columns(insp: Inspector, table_name: str) -> list[ColumnInfo]:
    columns: list[ColumnInfo] = []

    pk_cols = {col for col in insp.get_pk_constraint(table_name).get("constrained_columns", [])}
    fk_map: dict[str, str] = {}
    for fk in insp.get_foreign_keys(table_name):
        for col in fk["constrained_columns"]:
            fk_map[col] = f"{fk['referred_table']}.{', '.join(fk['referred_columns'])}"

    for col in insp.get_columns(table_name):
        columns.append(
            ColumnInfo(
                name=col["name"],
                type=str(col["type"]),
                nullable=col.get("nullable", True),
                primary_key=col["name"] in pk_cols,
                foreign_key=fk_map.get(col["name"]),
                default=str(col["default"]) if col.get("default") is not None else None,
            )
        )

    return columns


def _get_row_count(conn, table_name: str) -> int:
    try:
        result = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
        return result.scalar() or 0
    except Exception:
        try:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            return result.scalar() or 0
        except Exception:
            return -1


def _get_sample_rows(conn, table_name: str, limit: int) -> list[dict[str, Any]]:
    try:
        result = conn.execute(text(f'SELECT * FROM "{table_name}" LIMIT {limit}'))
    except Exception:
        try:
            result = conn.execute(text(f"SELECT * FROM {table_name} LIMIT {limit}"))
        except Exception:
            return []

    keys = list(result.keys())
    rows: list[dict[str, Any]] = []
    for row in result.fetchall():
        rows.append({k: _safe_value(v) for k, v in zip(keys, row)})
    return rows


def _safe_value(value: Any) -> Any:
    """Convierte valores no serializables a strings."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
