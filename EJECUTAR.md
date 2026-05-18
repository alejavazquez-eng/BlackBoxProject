# Cómo ejecutar DocGen desde PyCharm

---

## 1. Obtener el API Key de Anthropic (Claude)

Si ya tenés cuenta en [claude.ai](https://claude.ai), el API key se consigue en la consola de desarrolladores de Anthropic, que es un sitio separado:

1. Abrí **[console.anthropic.com](https://console.anthropic.com)** en el navegador.
2. Iniciá sesión con la misma cuenta que usás en Claude (Google o email).
3. En el menú lateral izquierdo, hacé clic en **"API Keys"**.
4. Hacé clic en el botón **"Create Key"**.
5. Ponele un nombre (ej: `docgen-local`) y hacé clic en **"Create Key"**.
6. **Copiá el key ahora** — solo se muestra una vez. Tiene el formato `sk-ant-api03-...`

> **Nota sobre el plan gratuito:** Los créditos de API son independientes de la suscripción a Claude.ai.
> Si la cuenta es nueva, en [console.anthropic.com/settings/billing](https://console.anthropic.com/settings/billing)
> podés ver si tenés créditos de prueba o cargar un monto mínimo (USD 5) para empezar.

---

## 2. Abrir el proyecto en PyCharm

1. Abrí PyCharm.
2. **File → Open** → seleccioná la carpeta `BlackBoxProject`.
3. PyCharm debería detectar el `pyproject.toml` automáticamente.

---

## 3. Configurar el intérprete de Python (virtualenv)

### Opción A — PyCharm crea el entorno automáticamente

Cuando abrís el proyecto por primera vez, PyCharm suele mostrar un aviso en la parte inferior:
> *"No interpreter configured"* o *"Create virtualenv"*

Hacé clic en **"Create virtualenv"** y dejá que lo configure con Python 3.11+.

### Opción B — Configurarlo a mano

1. **File → Settings** (Win/Linux) o **PyCharm → Settings** (Mac).
2. Ir a **Project: BlackBoxProject → Python Interpreter**.
3. Clic en el ícono del engranaje → **Add Interpreter → Add Local Interpreter**.
4. Elegir **Virtualenv Environment → New**.
5. Seleccionar Python 3.11 o superior como base.
6. Confirmar con **OK**.

---

## 4. Instalar las dependencias

### Con la Terminal integrada de PyCharm

Abrí la terminal (**View → Tool Windows → Terminal**) y ejecutá:

```bash
pip install -e .
```

Esto instala todas las dependencias listadas en `pyproject.toml` y deja el paquete
`docgen` disponible como comando en el entorno.

> Si el `pip` no apunta al entorno del proyecto, verificá que la terminal use
> el intérprete correcto (el nombre del virtualenv debería aparecer al inicio del prompt,
> ej: `(venv)`). Si no, activalo manualmente:
> - **Mac/Linux:** `source .venv/bin/activate`
> - **Windows:** `.venv\Scripts\activate`

---

## 1b. Obtener el API Key de Google Gemini (alternativa)

Si preferís usar Gemini en lugar de Claude:

1. Abrí **[aistudio.google.com](https://aistudio.google.com)** en el navegador.
2. Iniciá sesión con tu cuenta de Google.
3. Hacé clic en **"Get API Key"** (arriba a la izquierda).
4. Clic en **"Create API key"** → seleccioná un proyecto de Google Cloud (o creá uno nuevo).
5. Copiá el key generado. Tiene el formato `AIzaSy...`

> El tier gratuito de Gemini API incluye cuota suficiente para pruebas. No requiere tarjeta de crédito.

---

## 5. Crear el archivo `.env`

En la raíz del proyecto hay un archivo `.env.example`. Copialo y completalo:

**Mac/Linux (terminal integrada):**
```bash
cp .env.example .env
```

**Windows (terminal integrada):**
```bash
copy .env.example .env
```

Luego abrí `.env` en PyCharm y completá los keys que vayas a usar:

```env
# Claude (Anthropic)
ANTHROPIC_API_KEY=sk-ant-api03-XXXXX...

# Gemini (Google) — opcional, solo si querés usarlo
GEMINI_API_KEY=AIzaSy...

DOCGEN_MODEL=claude-opus-4-7
DOCGEN_MODEL_GEMINI=gemini-2.5-pro-preview-05-06
DOCGEN_PORT=8000
```

No es necesario completar ambos keys — solo el del proveedor que vayas a usar.

---

## 6. Ejecutar el servidor web

### Opción A — Configuración de ejecución en PyCharm (recomendado)

1. Hacé clic en **"Edit Configurations…"** (menú desplegable arriba a la derecha, junto al botón ▶).
2. Clic en **"+"** → **Python**.
3. Completá los campos:

   | Campo | Valor |
   |---|---|
   | **Name** | `DocGen - Servidor` |
   | **Script path** | Seleccionar **Module name** en el desplegable → escribir `docgen.main` |
   | **Parameters** | `serve` |
   | **Working directory** | `/ruta/a/BlackBoxProject` |
   | **Environment variables** | (vacío, se lee del `.env` automáticamente) |

4. Hacé clic en **OK** y luego en el botón ▶ verde para iniciar.

### Opción B — Desde la Terminal integrada

```bash
python -m docgen.main serve
```

o si el paquete ya está instalado con `pip install -e .`:

```bash
docgen serve
```

El servidor arranca en **[http://localhost:8000](http://localhost:8000)**.
Abrí esa URL en el navegador para usar la interfaz gráfica.

---

## 7. Usar el CLI directamente (sin interfaz web)

Para generar documentación desde la terminal y guardarla en un archivo:

```bash
docgen generate "https://mi-app.com" "postgresql://user:pass@localhost:5432/midb" -o documentacion.md
```

Parámetros disponibles:

| Parámetro | Descripción |
|---|---|
| Primer argumento | URL de la interfaz web |
| Segundo argumento | Connection string de la base de datos |
| `-o archivo.md` | Archivo de salida (por defecto: `documentation.md`) |
| `-c "texto"` | Contexto adicional para Claude |
| `-m modelo` | Modelo de Claude (por defecto: `claude-opus-4-7`) |

---

## 8. Ejemplos de connection strings

| Motor | Connection string |
|---|---|
| **SQLite** (archivo local) | `sqlite:///ruta/al/archivo.db` |
| **PostgreSQL** | `postgresql://usuario:contraseña@localhost:5432/nombre_bd` |
| **MySQL** | `mysql+pymysql://usuario:contraseña@localhost:3306/nombre_bd` |

---

## 9. Verificar que todo funciona

Abrí [http://localhost:8000/docs](http://localhost:8000/docs) en el navegador.
Deberías ver la documentación interactiva de la API (Swagger UI) con todos los endpoints disponibles.

---

## Problemas comunes

| Problema | Solución |
|---|---|
| `ModuleNotFoundError: No module named 'docgen'` | Ejecutar `pip install -e .` en el entorno correcto |
| `ANTHROPIC_API_KEY not set` | Verificar que el archivo `.env` existe y tiene el key correcto |
| `Error 401 Unauthorized` (Claude) | El API key es inválido o expiró; generá uno nuevo en console.anthropic.com |
| `Error 429 Too Many Requests` (Claude) | Sin créditos disponibles; verificar billing en console.anthropic.com |
| `API_KEY_INVALID` (Gemini) | El key de Gemini es incorrecto; verificar en aistudio.google.com |
| `google.generativeai not found` | Ejecutar `pip install -e .` para instalar la nueva dependencia |
| Puerto 8000 ocupado | Usar `docgen serve --port 8001` |
| `psycopg2` no instala en Mac | Instalar primero `brew install postgresql` |
