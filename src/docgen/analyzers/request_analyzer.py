"""Analiza un request HTTP y lo cruza con el schema de BD para detectar impacto."""

import json
import re

from docgen.models import DatabaseSchema, HttpRequestInput, RequestAnalysisResult


def analyze_request(http_request: HttpRequestInput, db_schema: DatabaseSchema) -> RequestAnalysisResult:
    body_fields = _extract_body_fields(http_request)
    all_fields = list(dict.fromkeys(body_fields + list(http_request.query_params.keys())))

    matched_columns: list[dict[str, str]] = []
    impacted_tables: list[str] = []

    for table in db_schema.tables:
        table_matched = False
        for col in table.columns:
            for field in all_fields:
                if _fields_match(field, col.name):
                    matched_columns.append({
                        "table": table.name,
                        "column": col.name,
                        "matched_field": field,
                        "column_type": col.type,
                        "is_pk": str(col.primary_key),
                        "is_fk": str(col.foreign_key or ""),
                        "nullable": str(col.nullable),
                    })
                    table_matched = True
            # Also match table name against path segments
            if not table_matched and _table_matches_path(table.name, http_request.path):
                table_matched = True

        if table_matched and table.name not in impacted_tables:
            impacted_tables.append(table.name)

    # Try to infer more tables from path even if no field match
    for table in db_schema.tables:
        if table.name not in impacted_tables and _table_matches_path(table.name, http_request.path):
            impacted_tables.append(table.name)

    return RequestAnalysisResult(
        method=http_request.method.upper(),
        path=http_request.path,
        body_fields=all_fields,
        impacted_tables=impacted_tables,
        matched_columns=matched_columns,
        suggested_operation=_infer_operation(http_request.method, http_request.path),
    )


def _extract_body_fields(req: HttpRequestInput) -> list[str]:
    if not req.body.strip():
        return []
    try:
        parsed = json.loads(req.body)
        return _flatten_keys(parsed) if isinstance(parsed, dict) else []
    except (json.JSONDecodeError, ValueError):
        # Try form-encoded
        fields = []
        for part in req.body.split("&"):
            key = part.split("=")[0].strip()
            if key:
                fields.append(key)
        return fields


def _flatten_keys(obj: dict, prefix: str = "") -> list[str]:
    """Extrae claves de un JSON anidado con notación plana."""
    keys: list[str] = []
    for k, v in obj.items():
        full_key = f"{prefix}.{k}" if prefix else k
        keys.append(full_key)
        if isinstance(v, dict):
            keys.extend(_flatten_keys(v, full_key))
    return keys


def _normalize(s: str) -> str:
    return re.sub(r"[_\-\s\.]", "", s.lower())


def _fields_match(field: str, col: str) -> bool:
    # Exact match after normalization
    field_leaf = field.split(".")[-1]  # handle nested keys like "user.name" → "name"
    return _normalize(field_leaf) == _normalize(col) or _normalize(field) == _normalize(col)


def _table_matches_path(table_name: str, path: str) -> bool:
    """Detecta si el nombre de una tabla aparece en los segmentos del path."""
    segments = [s for s in re.split(r"[/\-_]", path.lower()) if s and not s.isdigit()]
    norm_table = _normalize(table_name)
    return any(_normalize(seg) == norm_table or norm_table.startswith(_normalize(seg)) for seg in segments)


def _infer_operation(method: str, path: str) -> str:
    m = method.upper()
    if m == "GET":
        return "SELECT"
    if m == "POST":
        return "INSERT"
    if m in ("PUT", "PATCH"):
        return "UPDATE"
    if m == "DELETE":
        return "DELETE"
    return "UNKNOWN"
