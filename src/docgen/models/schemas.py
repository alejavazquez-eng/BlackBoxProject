"""Modelos Pydantic para request/response."""

from pydantic import BaseModel, Field
from typing import Any


class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool
    primary_key: bool
    foreign_key: str | None = None
    default: str | None = None


class TableInfo(BaseModel):
    name: str
    columns: list[ColumnInfo]
    row_count: int
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)


class DatabaseSchema(BaseModel):
    dialect: str
    tables: list[TableInfo]
    relationships: list[dict[str, str]] = Field(default_factory=list)


class FormField(BaseModel):
    name: str
    type: str
    label: str | None = None
    required: bool = False
    options: list[str] = Field(default_factory=list)


class WebForm(BaseModel):
    action: str | None = None
    method: str = "GET"
    fields: list[FormField]


class NavigationItem(BaseModel):
    text: str
    href: str | None = None
    children: list["NavigationItem"] = Field(default_factory=list)


class WebInterfaceAnalysis(BaseModel):
    url: str
    title: str | None = None
    description: str | None = None
    navigation: list[NavigationItem] = Field(default_factory=list)
    forms: list[WebForm] = Field(default_factory=list)
    data_tables: list[dict[str, Any]] = Field(default_factory=list)
    buttons_and_actions: list[dict[str, str]] = Field(default_factory=list)
    api_hints: list[str] = Field(default_factory=list)
    raw_text_summary: str = ""


class GenerationRequest(BaseModel):
    web_url: str = Field(..., description="URL de la interfaz web a analizar")
    db_connection: str = Field(..., description="Connection string de la base de datos")
    output_format: str = Field(default="markdown", description="Formato de salida: markdown o json")
    extra_context: str = Field(default="", description="Contexto adicional para la generación")
    provider: str = Field(default="anthropic", description="Proveedor: anthropic o gemini")
    model: str | None = Field(default=None, description="Modelo a usar (sobreescribe el default del proveedor)")


class GenerationResult(BaseModel):
    documentation: str
    web_analysis: WebInterfaceAnalysis
    db_schema: DatabaseSchema
    model_used: str
    tokens_used: int = 0


class HttpRequestInput(BaseModel):
    method: str = Field(default="POST", description="Método HTTP: GET, POST, PUT, PATCH, DELETE")
    path: str = Field(..., description="Path del endpoint, ej: /api/users o URL completa")
    headers: dict[str, str] = Field(default_factory=dict, description="Headers del request")
    query_params: dict[str, str] = Field(default_factory=dict, description="Query parameters")
    body: str = Field(default="", description="Body del request en JSON o form-encoded")
    content_type: str = Field(default="application/json", description="Content-Type del body")


class RequestAnalysisResult(BaseModel):
    method: str
    path: str
    body_fields: list[str]
    impacted_tables: list[str]
    matched_columns: list[dict[str, str]]
    suggested_operation: str


class RequestGenerationRequest(BaseModel):
    http_request: HttpRequestInput
    db_connection: str = Field(..., description="Connection string de la base de datos")
    provider: str = Field(default="anthropic", description="Proveedor: anthropic o gemini")
    model: str | None = Field(default=None)
    extra_context: str = Field(default="")
