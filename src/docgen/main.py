"""Punto de entrada: servidor FastAPI + CLI con Typer."""

import asyncio
import json
from pathlib import Path

import typer
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic_settings import BaseSettings

from docgen.analyzers import analyze_database, analyze_web_interface
from docgen.generators import generate_documentation, generate_documentation_stream
from docgen.models import GenerationRequest, GenerationResult


# ── Configuración ────────────────────────────────────────────────────────────

class Settings(BaseSettings):
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    docgen_model: str = "claude-opus-4-7"
    docgen_model_gemini: str = "gemini-2.5-pro-preview-05-06"
    docgen_port: int = 8000

    class Config:
        env_file = ".env"


settings = Settings()

# ── FastAPI ───────────────────────────────────────────────────────────────────

_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

app = FastAPI(
    title="DocGen",
    description="Generador de documentación de servicios a partir de interfaces web y bases de datos",
    version="0.1.0",
)

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/analyze/web")
async def analyze_web(url: str):
    """Analiza una URL y devuelve la estructura detectada."""
    result = await asyncio.to_thread(analyze_web_interface, url)
    return result.model_dump()


@app.post("/api/analyze/db")
async def analyze_db(connection: str):
    """Analiza una base de datos y devuelve su esquema."""
    try:
        result = await asyncio.to_thread(analyze_database, connection)
        return result.model_dump()
    except Exception as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})


def _resolve_model_and_configure(req: GenerationRequest) -> tuple[str, str]:
    """Devuelve (provider, model) y configura el SDK del proveedor."""
    provider = req.provider if req.provider in ("anthropic", "gemini") else "anthropic"

    if provider == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        model = req.model or settings.docgen_model_gemini
    else:
        import anthropic as _anthropic
        import os
        os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
        model = req.model or settings.docgen_model

    return provider, model


@app.post("/api/generate")
async def generate(req: GenerationRequest):
    """Genera documentación completa (sin streaming)."""
    provider, model = _resolve_model_and_configure(req)

    web = await asyncio.to_thread(analyze_web_interface, req.web_url)
    try:
        db = await asyncio.to_thread(analyze_database, req.db_connection)
    except Exception as exc:
        return JSONResponse(status_code=400, content={"error": f"DB error: {exc}"})

    doc, tokens = await asyncio.to_thread(
        generate_documentation,
        web,
        db,
        model,
        req.extra_context,
        provider,
    )

    return GenerationResult(
        documentation=doc,
        web_analysis=web,
        db_schema=db,
        model_used=model,
        tokens_used=tokens,
    ).model_dump()


@app.post("/api/generate/stream")
async def generate_stream(req: GenerationRequest):
    """Genera documentación con streaming SSE."""

    async def event_stream():
        provider, model = _resolve_model_and_configure(req)

        web = await asyncio.to_thread(analyze_web_interface, req.web_url)
        try:
            db = await asyncio.to_thread(analyze_database, req.db_connection)
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            return

        yield f"data: {json.dumps({'event': 'analysis_complete', 'tables': len(db.tables), 'forms': len(web.forms), 'model': model, 'provider': provider})}\n\n"

        loop = asyncio.get_event_loop()
        gen = generate_documentation_stream(web, db, model, req.extra_context, provider)

        def _next_chunk():
            try:
                return next(gen)
            except StopIteration:
                return None

        while True:
            chunk = await loop.run_in_executor(None, _next_chunk)
            if chunk is None:
                break
            yield f"data: {json.dumps({'event': 'chunk', 'text': chunk})}\n\n"

        yield f"data: {json.dumps({'event': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── CLI ───────────────────────────────────────────────────────────────────────

app_cli = typer.Typer(help="DocGen — Generador de documentación de servicios")


@app_cli.command("serve")
def serve(
    port: int = typer.Option(settings.docgen_port, help="Puerto del servidor"),
    host: str = typer.Option("127.0.0.1", help="Host del servidor"),
    reload: bool = typer.Option(False, help="Auto-reload en desarrollo"),
):
    """Inicia el servidor web de DocGen."""
    typer.echo(f"🚀  Iniciando DocGen en http://{host}:{port}")
    uvicorn.run("docgen.main:app", host=host, port=port, reload=reload)


@app_cli.command("generate")
def cli_generate(
    web_url: str = typer.Argument(..., help="URL de la interfaz web"),
    db_connection: str = typer.Argument(..., help="Connection string de la BD"),
    output: Path = typer.Option(Path("documentation.md"), "-o", help="Archivo de salida"),
    extra_context: str = typer.Option("", "-c", help="Contexto adicional"),
    provider: str = typer.Option("anthropic", "-p", help="Proveedor: anthropic o gemini"),
    model: str = typer.Option("", "-m", help="Modelo a usar (deja vacío para usar el default del proveedor)"),
):
    """Genera documentación desde la línea de comandos."""
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn

    console = Console()

    if provider == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        resolved_model = model or settings.docgen_model_gemini
    else:
        resolved_model = model or settings.docgen_model

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Analizando interfaz web…", total=None)
        web = analyze_web_interface(web_url)
        progress.update(task, description=f"✓ Web analizada: {web.title or web_url}")

        progress.update(task, description="Analizando base de datos…")
        try:
            db = analyze_database(db_connection)
        except Exception as exc:
            console.print(f"[red]Error en la base de datos:[/red] {exc}")
            raise typer.Exit(1)
        progress.update(task, description=f"✓ BD analizada: {len(db.tables)} tablas")

        provider_label = "Gemini" if provider == "gemini" else "Claude"
        progress.update(task, description=f"Generando documentación con {provider_label} ({resolved_model})…")

        full_doc: list[str] = []
        for chunk in generate_documentation_stream(web, db, resolved_model, extra_context, provider):
            full_doc.append(chunk)

        progress.update(task, description="✓ Documentación generada")

    doc_text = "".join(full_doc)
    output.write_text(doc_text, encoding="utf-8")
    console.print(f"\n[green]✓ Documentación guardada en:[/green] {output}")
    console.print(f"  Proveedor: {provider_label} ({resolved_model})")
    console.print(f"  Tablas analizadas: {len(db.tables)}")
    console.print(f"  Formularios detectados: {len(web.forms)}")
    console.print(f"  Caracteres generados: {len(doc_text):,}")


if __name__ == "__main__":
    app_cli()
