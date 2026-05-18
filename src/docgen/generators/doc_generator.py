"""Genera documentación de servicio usando Claude o Gemini a partir de los análisis de web y BD."""

import json
from collections.abc import Iterator

from docgen.models import DatabaseSchema, WebInterfaceAnalysis


_SYSTEM_PROMPT = """Eres un arquitecto de software senior especializado en diseño de APIs y servicios backend.
Tu tarea es analizar una interfaz web existente y el esquema de su base de datos para generar
documentación técnica completa sobre cómo debería funcionar el servicio backend que los soporte.

La documentación que produces debe ser:
- Clara, estructurada y directamente accionable por un equipo de desarrollo
- Basada únicamente en la evidencia presente en el análisis provisto
- Organizada con secciones claras y bien definidas
- Escrita en español

NO inventes funcionalidades que no estén evidenciadas en los datos. Si algo es ambiguo, menciónalo explícitamente."""


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

Con base en toda la información anterior, genera la documentación técnica completa del servicio.
La documentación debe incluir las siguientes secciones:

1. **Resumen del Sistema** — Qué hace el sistema, su propósito y dominio de negocio
2. **Entidades y Modelos de Datos** — Descripción de cada entidad, sus atributos y validaciones
3. **Endpoints de API** — Lista completa de endpoints con método HTTP, ruta, parámetros, body, respuestas y códigos de estado
4. **Reglas de Negocio** — Lógica de validación, restricciones y flujos de trabajo inferidos
5. **Flujos de Usuario** — Casos de uso principales y flujos de interacción
6. **Relaciones entre Entidades** — Diagrama o descripción de las relaciones
7. **Consideraciones de Seguridad** — Autenticación, autorización y validaciones necesarias
8. **Dependencias y Servicios Externos** — Cualquier integración externa detectada
9. **Sugerencias de Implementación** — Tecnologías recomendadas, patrones de diseño sugeridos
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
