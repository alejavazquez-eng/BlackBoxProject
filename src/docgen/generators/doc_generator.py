"""Genera documentación de servicio usando Claude o Gemini a partir de los análisis de web y BD."""

import json
from collections.abc import Iterator

from docgen.models import DatabaseSchema, HttpRequestInput, RequestAnalysisResult, WebInterfaceAnalysis


_SYSTEM_PROMPT = """Eres un arquitecto de software senior. Tu tarea es producir una especificación técnica
completa y lista para ser usada como input de generación de código fuente.

El output que produces debe permitir a un desarrollador (o a otra IA) escribir el código completo
del sistema sin necesidad de tomar decisiones de diseño: backend en Python (FastAPI/Django) o Node.js
(Express/NestJS), frontend en React/Vue/Angular u otro framework, y las migraciones de base de datos.

Reglas estrictas:
- Todos los modelos de datos deben incluir tipos exactos en el lenguaje target (Python type hints, TypeScript interfaces)
- Todos los endpoints deben tener firma completa: ruta, método, request body tipado, response tipado, códigos de error
- Las queries a la BD deben ser SQL ejecutable o código ORM (SQLAlchemy / Prisma / TypeORM)
- El código de ejemplo debe ser real y sintácticamente correcto, no pseudocódigo
- Las validaciones deben ser expresadas como reglas concretas (min, max, regex, enum, etc.)
- Escrito en español, código en inglés
- NO inventes funcionalidades no evidenciadas. Si algo es ambiguo, marcalo como [INFERIDO] y documentá el supuesto."""


def _build_analysis_prompt(
    web: WebInterfaceAnalysis,
    db: DatabaseSchema,
    extra_context: str,
) -> str:
    parts: list[str] = []

    parts.append("## ANÁLISIS DE LA INTERFAZ WEB\n")
    parts.append(f"**URL analizada:** {web.url}")
    if web.title:
        parts.append(f"**Título:** {web.title}")
    if web.description:
        parts.append(f"**Descripción:** {web.description}")

    if web.navigation:
        parts.append("\n### Navegación detectada")
        for item in web.navigation[:15]:
            parts.append(f"- {item.text}: {item.href}")

    if web.forms:
        parts.append("\n### Formularios detectados")
        for i, form in enumerate(web.forms, 1):
            parts.append(f"\n**Formulario {i}** — {form.method} {form.action or '(sin action)'}")
            for field in form.fields:
                opts = f" [opciones: {', '.join(field.options[:5])}]" if field.options else ""
                req = " *requerido*" if field.required else ""
                parts.append(f"  - `{field.name}` ({field.type}){req}{opts}")

    if web.data_tables:
        parts.append("\n### Tablas de datos en la UI")
        for tbl in web.data_tables:
            if tbl.get("headers"):
                parts.append(f"  Columnas: {', '.join(tbl['headers'])}")

    if web.buttons_and_actions:
        parts.append("\n### Acciones / Botones")
        for btn in web.buttons_and_actions[:15]:
            parts.append(f"  - [{btn.get('text')}] ({btn.get('tag')}){' → ' + btn.get('href','') if btn.get('href') else ''}")

    if web.api_hints:
        parts.append("\n### Hints de endpoints API encontrados en el código")
        for hint in web.api_hints:
            parts.append(f"  - `{hint}`")

    if web.raw_text_summary:
        parts.append(f"\n### Resumen de texto visible en la página\n```\n{web.raw_text_summary[:1500]}\n```")

    parts.append("\n\n## ESQUEMA DE BASE DE DATOS\n")
    parts.append(f"**Motor:** {db.dialect}")
    parts.append(f"**Tablas:** {len(db.tables)}\n")

    for table in db.tables:
        parts.append(f"\n### Tabla: `{table.name}` ({table.row_count} filas)")
        for col in table.columns:
            markers: list[str] = []
            if col.primary_key:
                markers.append("PK")
            if col.foreign_key:
                markers.append(f"FK→{col.foreign_key}")
            if not col.nullable:
                markers.append("NOT NULL")
            marker_str = f" [{', '.join(markers)}]" if markers else ""
            default_str = f" default={col.default}" if col.default else ""
            parts.append(f"  - `{col.name}`: {col.type}{marker_str}{default_str}")

        if table.sample_rows:
            parts.append("  *Muestra de datos:*")
            for row in table.sample_rows[:2]:
                parts.append(f"  ```json\n  {json.dumps(row, ensure_ascii=False, default=str)}\n  ```")

    if db.relationships:
        parts.append("\n### Relaciones entre tablas")
        for rel in db.relationships:
            parts.append(
                f"  - `{rel['from_table']}.{rel['from_columns']}` → "
                f"`{rel['to_table']}.{rel['to_columns']}`"
            )

    if extra_context.strip():
        parts.append(f"\n\n## CONTEXTO ADICIONAL PROVISTO POR EL USUARIO\n{extra_context}")

    parts.append("""

---

Con base en toda la información anterior, generá la especificación técnica completa del sistema,
orientada a la generación de código fuente. Cada sección debe contener código real, tipos exactos
y contratos claros que permitan implementar el sistema sin ambigüedad.

## 1. Stack tecnológico recomendado
Indicá el stack exacto para backend, frontend y BD, con versiones. Justificá brevemente cada elección.

## 2. Estructura de carpetas del proyecto
Mostrá el árbol de directorios completo del backend y del frontend, con los archivos principales.

## 3. Modelos de datos
Para cada entidad del sistema:
- Clase Python con type hints (Pydantic BaseModel) Y equivalente TypeScript interface
- Validaciones exactas: tipo, min/max, regex, nullable, unique
- Ejemplo de instancia JSON válida

## 4. Schema de base de datos
- DDL SQL completo (CREATE TABLE con constraints, FK, índices)
- Equivalente en ORM (SQLAlchemy models Python o Prisma schema)

## 5. Contrato de API (estilo OpenAPI)
Para cada endpoint detectado:
- Método HTTP + ruta exacta
- Path params / query params con tipos y si son requeridos
- Request body: schema JSON tipado (Pydantic o Zod)
- Response body exitosa: schema JSON tipado con ejemplo
- Códigos de error con mensaje y condición que los dispara

## 6. Implementación del backend
Para cada endpoint, código real del handler:
- Función/controlador completo en Python (FastAPI) o Node.js (Express/NestJS)
- Llamada a la capa de servicio
- Query SQL o ORM ejecutable
- Manejo de errores

## 7. Implementación del frontend
- Componentes principales con sus props (React/Vue/Angular según corresponda)
- Llamadas a la API (fetch/axios con tipos)
- Manejo de estado (loading, error, data)
- Ejemplo de formulario vinculado al endpoint principal

## 8. Autenticación y autorización
- Mecanismo exacto (JWT, session, OAuth)
- Código del middleware/guard de autenticación
- Reglas de autorización por endpoint (quién puede hacer qué)

## 9. Variables de entorno y configuración
- Archivo `.env.example` completo con todas las variables necesarias
- Archivo de configuración del servidor (settings/config)

## 10. Casos de test
- Al menos 3 casos de test por endpoint crítico (happy path, validación fallida, error de BD)
- En pytest (backend) y Jest/Vitest (frontend)
""")

    return "\n".join(parts)


# ── Anthropic ────────────────────────────────────────────────────────────────

def _generate_anthropic(
    web: WebInterfaceAnalysis,
    db: DatabaseSchema,
    model: str,
    extra_context: str,
) -> tuple[str, int]:
    import anthropic

    client = anthropic.Anthropic()
    prompt = _build_analysis_prompt(web, db, extra_context)

    response = client.messages.create(
        model=model,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    doc_text = next(
        (block.text for block in response.content if block.type == "text"),
        "",
    )
    tokens = response.usage.input_tokens + response.usage.output_tokens
    return doc_text, tokens


def _stream_anthropic(
    web: WebInterfaceAnalysis,
    db: DatabaseSchema,
    model: str,
    extra_context: str,
) -> Iterator[str]:
    import anthropic

    client = anthropic.Anthropic()
    prompt = _build_analysis_prompt(web, db, extra_context)

    with client.messages.stream(
        model=model,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text


# ── Gemini ───────────────────────────────────────────────────────────────────

def _generate_gemini(
    web: WebInterfaceAnalysis,
    db: DatabaseSchema,
    model: str,
    extra_context: str,
) -> tuple[str, int]:
    import google.generativeai as genai

    prompt = _build_analysis_prompt(web, db, extra_context)
    full_prompt = f"{_SYSTEM_PROMPT}\n\n{prompt}"

    gemini_model = genai.GenerativeModel(model)
    response = gemini_model.generate_content(full_prompt)

    doc_text = response.text or ""
    usage = response.usage_metadata
    tokens = (usage.prompt_token_count or 0) + (usage.candidates_token_count or 0)
    return doc_text, tokens


def _stream_gemini(
    web: WebInterfaceAnalysis,
    db: DatabaseSchema,
    model: str,
    extra_context: str,
) -> Iterator[str]:
    import google.generativeai as genai

    prompt = _build_analysis_prompt(web, db, extra_context)
    full_prompt = f"{_SYSTEM_PROMPT}\n\n{prompt}"

    gemini_model = genai.GenerativeModel(model)
    for chunk in gemini_model.generate_content(full_prompt, stream=True):
        text = chunk.text
        if text:
            yield text


# ── Prompt para análisis de request específico ───────────────────────────────

_REQUEST_SYSTEM_PROMPT = """Eres un arquitecto de software senior. Tu tarea es producir el código fuente completo
del endpoint backend que satisface el request HTTP recibido, y el componente frontend que lo consume.

El output debe ser código real, listo para copiar y pegar en el proyecto:
- Backend: Python (FastAPI + SQLAlchemy) y/o Node.js (Express/NestJS + TypeORM/Prisma), según contexto
- Frontend: React (TypeScript) o vanilla JS con fetch, según contexto
- SQL: queries ejecutables contra el schema real de la BD provisto
- Validaciones: código real (Pydantic validators, Zod schemas, class-validator decorators)

Reglas estrictas:
- Usá los nombres de tablas y columnas exactos del schema provisto, sin inventar nada
- Todos los tipos deben ser explícitos (Python type hints, TypeScript types)
- El código debe manejar errores de forma explícita (try/except, try/catch)
- Si hay ambigüedad, marcala como [SUPUESTO] y tomá la decisión más conservadora
- Escrito en español, código en inglés"""


def _build_request_prompt(
    http_request: HttpRequestInput,
    analysis: RequestAnalysisResult,
    db: DatabaseSchema,
    extra_context: str,
) -> str:
    parts: list[str] = []

    parts.append("## REQUEST HTTP A IMPLEMENTAR\n")
    parts.append(f"**Método:** `{http_request.method.upper()}`")
    parts.append(f"**Path:** `{http_request.path}`")
    parts.append(f"**Content-Type:** `{http_request.content_type}`")

    if http_request.headers:
        relevant = {k: v for k, v in http_request.headers.items()
                    if k.lower() not in ("host", "connection", "accept-encoding")}
        if relevant:
            parts.append("\n**Headers relevantes:**")
            for k, v in relevant.items():
                parts.append(f"  - `{k}: {v}`")

    if http_request.query_params:
        parts.append("\n**Query params:**")
        for k, v in http_request.query_params.items():
            parts.append(f"  - `{k}` = `{v}`")

    if http_request.body.strip():
        parts.append(f"\n**Body:**\n```json\n{http_request.body.strip()}\n```")

    parts.append("\n\n## ANÁLISIS DE IMPACTO EN LA BASE DE DATOS\n")
    parts.append(f"**Operación inferida:** `{analysis.suggested_operation}`")

    if analysis.body_fields:
        parts.append(f"**Campos en el request:** {', '.join(f'`{f}`' for f in analysis.body_fields)}")

    if analysis.impacted_tables:
        parts.append(f"**Tablas impactadas:** {', '.join(f'`{t}`' for t in analysis.impacted_tables)}")

    if analysis.matched_columns:
        parts.append("\n**Mapeo campo → columna DB:**")
        for match in analysis.matched_columns:
            pk_flag = " [PK]" if match.get("is_pk") == "True" else ""
            fk_flag = f" [FK→{match['is_fk']}]" if match.get("is_fk") else ""
            parts.append(
                f"  - `{match['matched_field']}` → `{match['table']}.{match['column']}` "
                f"({match['column_type']}){pk_flag}{fk_flag}"
            )

    parts.append("\n\n## SCHEMA COMPLETO DE LAS TABLAS IMPACTADAS\n")
    parts.append(f"**Motor:** {db.dialect}")

    impacted_set = set(analysis.impacted_tables)
    tables_to_show = [t for t in db.tables if t.name in impacted_set] or db.tables[:5]

    for table in tables_to_show:
        parts.append(f"\n### Tabla: `{table.name}` ({table.row_count} filas)")
        for col in table.columns:
            markers: list[str] = []
            if col.primary_key:
                markers.append("PK")
            if col.foreign_key:
                markers.append(f"FK→{col.foreign_key}")
            if not col.nullable:
                markers.append("NOT NULL")
            marker_str = f" [{', '.join(markers)}]" if markers else ""
            default_str = f" default={col.default}" if col.default else ""
            parts.append(f"  - `{col.name}`: {col.type}{marker_str}{default_str}")

        if table.sample_rows:
            parts.append("  *Muestra de datos existentes:*")
            for row in table.sample_rows[:2]:
                parts.append(f"  ```json\n  {json.dumps(row, ensure_ascii=False, default=str)}\n  ```")

    if db.relationships:
        relevant_rels = [
            r for r in db.relationships
            if r["from_table"] in impacted_set or r["to_table"] in impacted_set
        ]
        if relevant_rels:
            parts.append("\n### Relaciones relevantes")
            for rel in relevant_rels:
                parts.append(
                    f"  - `{rel['from_table']}.{rel['from_columns']}` → "
                    f"`{rel['to_table']}.{rel['to_columns']}`"
                )

    if extra_context.strip():
        parts.append(f"\n\n## CONTEXTO ADICIONAL\n{extra_context}")

    parts.append("""

---

Con base en el request HTTP y el schema de BD anterior, generá el código fuente completo para
implementar este endpoint. El output debe poder copiarse directamente al proyecto.

## 1. Contrato del endpoint
- Método, ruta, descripción de una línea
- Tabla de parámetros (path/query/header): nombre | tipo | requerido | descripción

## 2. Schema de validación del request body
```python
# Pydantic (Python)
class NombreRequest(BaseModel):
    campo: tipo = Field(..., description="...", min_length=N)
    # ... todos los campos con sus validaciones exactas
```
```typescript
// Zod (TypeScript/Node)
const NombreSchema = z.object({
  campo: z.string().min(N),
})
```

## 3. Handler del endpoint — Python (FastAPI)
Código completo del router/endpoint, incluyendo inyección de dependencias, llamada al servicio y manejo de errores HTTP.

## 4. Handler del endpoint — Node.js (Express o NestJS)
Código equivalente en TypeScript para el mismo endpoint.

## 5. Capa de servicio
Función de servicio que contiene la lógica de negocio, separada del handler. En Python y en TypeScript.

## 6. Queries a la base de datos
- SQL ejecutable para la operación principal (INSERT/SELECT/UPDATE/DELETE)
- Equivalente con SQLAlchemy ORM (Python)
- Equivalente con Prisma o TypeORM (Node.js)
- Si hay operaciones secundarias (verificar existencia, actualizar estado, etc.), incluirlas también

## 7. Response model
```python
# Python
class NombreResponse(BaseModel):
    id: int
    # ... campos de respuesta con tipos
```
```typescript
// TypeScript
interface NombreResponse {
  id: number;
  // ...
}
```
Ejemplo de JSON de respuesta exitosa con código HTTP.

## 8. Errores y códigos HTTP
Tabla: condición de error | código HTTP | mensaje JSON de respuesta

## 9. Componente frontend que consume este endpoint
Código React (TypeScript) o Vue del componente que hace el request: formulario, llamada fetch/axios tipada, manejo de loading/error/success.

## 10. Middleware y seguridad
- Código del middleware de autenticación (JWT decode, verificación de rol)
- Qué claims del token se usan en este endpoint
- Sanitización de inputs si aplica

## 11. Tests
```python
# pytest
def test_nombre_endpoint_success(): ...
def test_nombre_endpoint_validation_error(): ...
def test_nombre_endpoint_not_found(): ...
```
```typescript
// Jest/Vitest
test('nombre endpoint success', async () => { ... })
```
""")

    return "\n".join(parts)


def _generate_request_anthropic(
    http_request: HttpRequestInput,
    analysis: RequestAnalysisResult,
    db: DatabaseSchema,
    model: str,
    extra_context: str,
) -> tuple[str, int]:
    import anthropic

    client = anthropic.Anthropic()
    prompt = _build_request_prompt(http_request, analysis, db, extra_context)

    response = client.messages.create(
        model=model,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=_REQUEST_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    doc_text = next(
        (block.text for block in response.content if block.type == "text"),
        "",
    )
    tokens = response.usage.input_tokens + response.usage.output_tokens
    return doc_text, tokens


def _stream_request_anthropic(
    http_request: HttpRequestInput,
    analysis: RequestAnalysisResult,
    db: DatabaseSchema,
    model: str,
    extra_context: str,
) -> Iterator[str]:
    import anthropic

    client = anthropic.Anthropic()
    prompt = _build_request_prompt(http_request, analysis, db, extra_context)

    with client.messages.stream(
        model=model,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=_REQUEST_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text


def _generate_request_gemini(
    http_request: HttpRequestInput,
    analysis: RequestAnalysisResult,
    db: DatabaseSchema,
    model: str,
    extra_context: str,
) -> tuple[str, int]:
    import google.generativeai as genai

    prompt = _build_request_prompt(http_request, analysis, db, extra_context)
    full_prompt = f"{_REQUEST_SYSTEM_PROMPT}\n\n{prompt}"

    gemini_model = genai.GenerativeModel(model)
    response = gemini_model.generate_content(full_prompt)

    doc_text = response.text or ""
    usage = response.usage_metadata
    tokens = (usage.prompt_token_count or 0) + (usage.candidates_token_count or 0)
    return doc_text, tokens


def _stream_request_gemini(
    http_request: HttpRequestInput,
    analysis: RequestAnalysisResult,
    db: DatabaseSchema,
    model: str,
    extra_context: str,
) -> Iterator[str]:
    import google.generativeai as genai

    prompt = _build_request_prompt(http_request, analysis, db, extra_context)
    full_prompt = f"{_REQUEST_SYSTEM_PROMPT}\n\n{prompt}"

    gemini_model = genai.GenerativeModel(model)
    for chunk in gemini_model.generate_content(full_prompt, stream=True):
        text = chunk.text
        if text:
            yield text


def generate_request_documentation(
    http_request: HttpRequestInput,
    analysis: RequestAnalysisResult,
    db: DatabaseSchema,
    model: str = "claude-opus-4-7",
    extra_context: str = "",
    provider: str = "anthropic",
) -> tuple[str, int]:
    if provider == "gemini":
        return _generate_request_gemini(http_request, analysis, db, model, extra_context)
    return _generate_request_anthropic(http_request, analysis, db, model, extra_context)


def generate_request_documentation_stream(
    http_request: HttpRequestInput,
    analysis: RequestAnalysisResult,
    db: DatabaseSchema,
    model: str = "claude-opus-4-7",
    extra_context: str = "",
    provider: str = "anthropic",
) -> Iterator[str]:
    if provider == "gemini":
        yield from _stream_request_gemini(http_request, analysis, db, model, extra_context)
    else:
        yield from _stream_request_anthropic(http_request, analysis, db, model, extra_context)


# ── Punto de entrada público ─────────────────────────────────────────────────

def generate_documentation(
    web: WebInterfaceAnalysis,
    db: DatabaseSchema,
    model: str = "claude-opus-4-7",
    extra_context: str = "",
    provider: str = "anthropic",
) -> tuple[str, int]:
    """Genera documentación completa. Retorna (documentación, tokens_usados)."""
    if provider == "gemini":
        return _generate_gemini(web, db, model, extra_context)
    return _generate_anthropic(web, db, model, extra_context)


def generate_documentation_stream(
    web: WebInterfaceAnalysis,
    db: DatabaseSchema,
    model: str = "claude-opus-4-7",
    extra_context: str = "",
    provider: str = "anthropic",
) -> Iterator[str]:
    """Genera documentación en streaming. Yield de fragmentos de texto."""
    if provider == "gemini":
        yield from _stream_gemini(web, db, model, extra_context)
    else:
        yield from _stream_anthropic(web, db, model, extra_context)
