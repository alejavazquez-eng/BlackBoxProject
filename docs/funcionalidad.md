# DocGen — Especificación de Funcionalidad

## Propósito

DocGen analiza un sistema existente (interfaz web + base de datos) o un request HTTP concreto y produce **especificaciones técnicas orientadas a la generación de código fuente**. El output está diseñado para que otra IA o un desarrollador pueda escribir el código completo del sistema sin tomar decisiones de diseño adicionales.

El sistema soporta generar specs para:
- **Backend**: Python (FastAPI + SQLAlchemy) o Node.js (Express/NestJS + TypeORM/Prisma)
- **Frontend**: React (TypeScript), Vue, Angular o vanilla JS
- **Base de datos**: PostgreSQL, MySQL, SQLite

---

## Modo 1: Documentar Sistema

### Objetivo

Analizar una interfaz web completa y su base de datos para producir una especificación técnica que permita reimplementar el sistema desde cero en el stack elegido.

### Inputs

| Campo | Descripción | Ejemplo |
|---|---|---|
| URL de la interfaz web | Página principal del sistema | `https://miapp.com/admin` |
| Connection string de BD | Cadena SQLAlchemy | `postgresql://user:pass@localhost:5432/midb` |
| Proveedor de IA | Claude (Anthropic) o Gemini (Google) | `anthropic` |
| Modelo | Versión del modelo | `claude-opus-4-7` |
| Contexto adicional | Stack preferido, restricciones, aclaraciones | `"usar FastAPI + React, JWT con RS256"` |

### Qué se analiza como input

**De la interfaz web** (scraping con BeautifulSoup):
- Formularios: campos, tipos, labels, validaciones visibles, opciones de selects
- Tablas de datos: columnas visibles y datos de muestra
- Navegación: rutas y jerarquía de secciones
- Botones y acciones: href, método, atributos data
- Hints de endpoints API en código JS (fetch, axios, action attributes)

**Del schema de base de datos** (inspección via SQLAlchemy):
- Tablas: nombre, columnas (tipo, nullable, PK, FK, default), filas de muestra
- Relaciones: foreign keys y su dirección

### Output generado por la IA

Una especificación Markdown con estas secciones, todas con **código real y tipos exactos**:

#### 1. Stack tecnológico recomendado
Stack exacto para backend, frontend y BD con versiones. Justificación de cada elección basada en el sistema analizado.

#### 2. Estructura de carpetas
Árbol de directorios completo del backend y frontend con los archivos principales.

```
backend/
├── app/
│   ├── models/         # SQLAlchemy models
│   ├── schemas/        # Pydantic schemas (request/response)
│   ├── routers/        # FastAPI routers por dominio
│   ├── services/       # Lógica de negocio
│   └── main.py
frontend/
├── src/
│   ├── components/
│   ├── pages/
│   ├── api/            # Llamadas a la API tipadas
│   └── types/          # TypeScript interfaces
```

#### 3. Modelos de datos
Para cada entidad, con **tipos exactos en ambos lenguajes**:

```python
# Python — Pydantic
class Usuario(BaseModel):
    id: int
    nombre: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    rol_id: int
    activo: bool = True
    creado_en: datetime
```

```typescript
// TypeScript
interface Usuario {
  id: number;
  nombre: string;        // min:2, max:100
  email: string;
  rolId: number;
  activo: boolean;
  creadoEn: string;      // ISO 8601
}
```

#### 4. Schema de base de datos
DDL SQL ejecutable + ORM equivalente:

```sql
CREATE TABLE usuarios (
  id          SERIAL PRIMARY KEY,
  nombre      VARCHAR(100) NOT NULL,
  email       VARCHAR(255) NOT NULL UNIQUE,
  rol_id      INTEGER NOT NULL REFERENCES roles(id),
  activo      BOOLEAN NOT NULL DEFAULT TRUE,
  creado_en   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_usuarios_email ON usuarios(email);
```

```python
# SQLAlchemy
class UsuarioModel(Base):
    __tablename__ = "usuarios"
    id        = Column(Integer, primary_key=True)
    nombre    = Column(String(100), nullable=False)
    email     = Column(String(255), nullable=False, unique=True)
    rol_id    = Column(Integer, ForeignKey("roles.id"), nullable=False)
    activo    = Column(Boolean, nullable=False, default=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
```

#### 5. Contrato de API (estilo OpenAPI)
Para cada endpoint detectado:

```
POST /api/usuarios
Authorization: Bearer <token>

Request body:
{
  "nombre": "string (2-100 chars, requerido)",
  "email":  "string (email válido, requerido)",
  "rol_id": "integer (requerido, debe existir en roles)"
}

Response 201:
{
  "id": 42,
  "nombre": "Juan Pérez",
  "email": "juan@ejemplo.com",
  "rolId": 2,
  "activo": true,
  "creadoEn": "2026-05-18T10:30:00Z"
}

Errores:
  400 — { "detail": "Email ya registrado" }
  422 — { "detail": [{ "loc": ["body", "email"], "msg": "value is not a valid email" }] }
  401 — { "detail": "Token inválido o expirado" }
  403 — { "detail": "Sin permisos para esta acción" }
```

#### 6. Implementación del backend
Handler completo en Python (FastAPI) y Node.js (Express/NestJS) con lógica de servicio y queries ORM.

#### 7. Implementación del frontend
Componente React (TypeScript) con formulario, llamada a la API tipada y manejo de estados.

#### 8. Autenticación y autorización
Código del middleware JWT, decodificación del token y reglas de acceso por endpoint.

#### 9. Variables de entorno
Archivo `.env.example` completo con todas las variables necesarias.

#### 10. Tests
Casos de test en pytest (backend) y Jest/Vitest (frontend): happy path, validación fallida, error de BD.

---

## Modo 2: Analizar Request

### Objetivo

Dado un request HTTP concreto que el frontend envía al backend, producir el **código fuente completo** del endpoint que lo implementa: handler, servicio, queries SQL, response model, componente frontend y tests.

### Inputs

| Campo | Descripción | Ejemplo |
|---|---|---|
| Método HTTP | Verbo del request | `POST` |
| Path | Ruta del endpoint | `/api/pedidos` |
| Body (JSON) | Payload que envía el frontend | `{"cliente_id": 5, "items": [...]}` |
| Query params | Parámetros de URL | `incluir_inactivos=false` |
| Headers | Cabeceras del request | `Authorization: Bearer token123` |
| Connection string de BD | Para cruzar con el schema real | `postgresql://...` |
| Contexto adicional | Stack preferido, reglas de negocio extra | `"validar stock antes de confirmar"` |

### Cómo funciona el análisis de impacto

Antes de llamar a la IA, el sistema hace un análisis estático del request:

**Extracción de campos**
- Body JSON → claves de primer nivel y anidadas (notación `padre.hijo`)
- Body form-encoded → keys antes del `=`
- Query params → nombres de parámetros

**Cruce con el schema de BD**
Para cada campo del request y cada columna de cada tabla, normaliza ambos nombres (minúsculas, sin guiones ni underscores) y compara. Si hay match, registra: tabla, columna, tipo, si es PK/FK, si es nullable.

**Inferencia de tablas por path**
Los segmentos del path (ej: `/api/pedidos/items`) se comparan contra los nombres de tablas de la BD para detectar tablas impactadas aunque no aparezcan en el body.

**Inferencia de la operación SQL**

| Método HTTP | Operación |
|---|---|
| GET | SELECT |
| POST | INSERT |
| PUT / PATCH | UPDATE |
| DELETE | DELETE |

Este análisis previo se incluye en el contexto del prompt para que la IA tenga el mapeo campo→columna ya resuelto.

### Output generado por la IA

Código fuente completo en las siguientes secciones:

#### 1. Contrato del endpoint
Tabla de parámetros con tipos y si son requeridos.

#### 2. Schema de validación del request body

```python
# Pydantic (Python)
class CrearPedidoRequest(BaseModel):
    cliente_id: int = Field(..., gt=0)
    items: list[ItemPedidoRequest] = Field(..., min_items=1)
    notas: str | None = Field(None, max_length=500)
```

```typescript
// Zod (TypeScript/Node)
const CrearPedidoSchema = z.object({
  clienteId: z.number().int().positive(),
  items: z.array(ItemPedidoSchema).min(1),
  notas: z.string().max(500).optional(),
})
```

#### 3. Handler — Python (FastAPI)
Router completo con inyección de dependencias, llamada al servicio y manejo de excepciones HTTP.

#### 4. Handler — Node.js (Express / NestJS)
Equivalente TypeScript del mismo handler.

#### 5. Capa de servicio
Función de servicio con la lógica de negocio, separada del handler, en Python y TypeScript.

#### 6. Queries a la base de datos
SQL ejecutable + ORM equivalente para la operación principal y las secundarias (verificaciones de existencia, actualizaciones de estado, etc.).

```sql
-- Insertar pedido
INSERT INTO pedidos (cliente_id, estado, notas, creado_en)
VALUES ($1, 'pendiente', $2, NOW())
RETURNING id, cliente_id, estado, creado_en;
```

```python
# SQLAlchemy
pedido = PedidoModel(
    cliente_id=data.cliente_id,
    estado="pendiente",
    notas=data.notas,
)
db.add(pedido)
await db.commit()
await db.refresh(pedido)
```

#### 7. Response model
Schema tipado de la respuesta + ejemplo JSON con código HTTP.

#### 8. Errores y códigos HTTP
Tabla: condición → código HTTP → JSON de respuesta.

#### 9. Componente frontend
React (TypeScript): formulario que construye el payload, llamada tipada a la API, manejo de loading/error/éxito.

#### 10. Middleware y seguridad
Código del guard/middleware de autenticación JWT y reglas de autorización específicas para este endpoint.

#### 11. Tests
Casos pytest (backend) y Jest/Vitest (frontend): happy path, validación fallida, error de BD.

---

## API del servidor DocGen

### Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/` | Interfaz web |
| `POST` | `/api/analyze/web?url=...` | Analiza URL → `WebInterfaceAnalysis` |
| `POST` | `/api/analyze/db?connection=...` | Analiza BD → `DatabaseSchema` |
| `POST` | `/api/analyze/request` | Analiza impacto de un request → `RequestAnalysisResult` |
| `POST` | `/api/generate` | Genera spec completa (sin streaming) |
| `POST` | `/api/generate/stream` | Genera spec del sistema con SSE streaming |
| `POST` | `/api/generate/request/stream` | Genera código del endpoint con SSE streaming |

### Formato SSE

```
data: {"event": "analysis_complete", "tables": 12, "model": "claude-opus-4-7", "provider": "anthropic"}
data: {"event": "chunk", "text": "...fragmento..."}
data: {"event": "done"}
data: {"error": "descripción del error"}
```

---

## Configuración

### Variables de entorno (`.env`)

```env
ANTHROPIC_API_KEY=sk-ant-...        # Requerido si usás Claude
GEMINI_API_KEY=AIzaSy...            # Requerido si usás Gemini
DOCGEN_MODEL=claude-opus-4-7        # Modelo default de Claude
DOCGEN_MODEL_GEMINI=gemini-2.5-pro-preview-05-06
DOCGEN_PORT=8000
```

### Bases de datos soportadas

| Motor | Connection string |
|---|---|
| PostgreSQL | `postgresql://usuario:contraseña@host:5432/nombre_bd` |
| MySQL | `mysql+pymysql://usuario:contraseña@host:3306/nombre_bd` |
| SQLite | `sqlite:///ruta/al/archivo.db` |

### Cómo correr el proyecto

```bash
pip install -r requirements.txt
python -m docgen.main serve       # Levanta en http://localhost:8000
```
