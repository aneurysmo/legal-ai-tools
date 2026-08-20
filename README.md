# Lex Workspace

Suite de herramientas de IA legal con interfaz unificada en Streamlit:

- **Análisis de riesgo contractual** — sube un contrato (`.pdf`/`.docx`) y obtén cláusulas de alto, medio y bajo riesgo, con un reporte descargable.
- **Biblioteca jurídica compartida** — sube documentos a una base de conocimiento compartida entre usuarios, pídele al LLM que clasifique y resuma cada documento, pregúntale directamente a un documento (con cita de fragmento) o usa el chat flotante para investigación jurídica general.
- **Redacción de documentos** — genera cartas, contratos y escritos legales completando un formulario; el borrador se puede editar por instrucciones y descargar en `.docx`/`.txt`.
- **Autenticación propia** (usuario/contraseña + pregunta de seguridad) con historial de actividad y de chat por usuario, persistido en SQLite vía Prisma.
- **Modo oscuro** conmutable desde el sidebar.

## Requisitos

- Python 3.11+
- Un proveedor de LLM configurado (ver abajo). El proyecto soporta **Gemini, Claude (Anthropic), OpenAI, DeepSeek, GitHub Models y Groq** — estos tres últimos usan el SDK de `openai` con un `base_url` distinto, así que no requieren dependencias extra.

## Instalación

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

pip install -r requirements.txt
```

> **Nota sobre `torch` (CPU-only):** `requirements.txt` fuerza la instalación de la variante CPU-only de PyTorch (dependencia de `sentence-transformers`, usado para los embeddings del RAG — ver [legal_research.py](legal_research.py)) vía `--extra-index-url https://download.pytorch.org/whl/cpu`. Esto reduce el peso de la instalación de ~2-3 GB a ~500-800 MB sin cambiar ningún comportamiento — solo se omite el soporte CUDA/GPU, que no se usa en este proyecto ni en despliegues típicos sin GPU (Cloud Run, Render, etc.). Si en el futuro se necesita GPU, quitar esa línea e instalar `torch` normal.

### Base de datos (Prisma)

El proyecto soporta **SQLite** (desarrollo local, default) y **PostgreSQL** (demo/producción en la nube) desde el mismo `prisma/schema.prisma.template`. Como Prisma no permite que el `provider` del datasource sea dinámico vía `env()` (solo la `url` lo admite), un script genera el `schema.prisma` real a partir de la plantilla según la variable `DB_PROVIDER` de tu `.env`:

```bash
# 1. Define DB_PROVIDER=sqlite (o postgresql) y DATABASE_URL en tu .env
# 2. Genera prisma/schema.prisma a partir de la plantilla:
python scripts/prepare_prisma_schema.py

# 3. Genera el cliente y sincroniza el esquema:
prisma generate --schema=prisma/schema.prisma
prisma db push --schema=prisma/schema.prisma
```

Vuelve a correr los tres pasos cada vez que cambies `DB_PROVIDER`, `prisma/schema.prisma.template`, o tu `.env`. **`prisma/schema.prisma` es un archivo generado (ignorado por git)** — solo se versiona `schema.prisma.template`.

### Variables de entorno

Copia `.env.example` a `.env` (desarrollo local) y completa tu proveedor principal:

```
LLM_PROVIDER=gemini
GEMINI_API_KEY=tu_clave
DB_PROVIDER=sqlite
DATABASE_URL=file:./app.db
```

Proveedores adicionales soportados (opcionales, descomenta según necesites): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `GITHUB_API_KEY`, `GROQ_API_KEY`.

**Plan de proveedores actual: Gemini como principal, Groq como fallback.** Configura `LLM_FALLBACK_PROVIDER=groq` (con su propia `GROQ_API_KEY`) para que la app reintente automáticamente con Groq cuando Gemini falle (cuota agotada, error de red, etc.) — útil para no interrumpir una demo en vivo. Ver `config.get_provider_config` / `legal_research.ask_llm`.

## Uso

```bash
streamlit run app.py
```

Abre `http://localhost:8501`, crea una cuenta (usuario + contraseña + pregunta de seguridad) e inicia sesión.

### Herramientas individuales por CLI (sin la UI)

```bash
python contract_risk_analyzer.py ruta/al/contrato.pdf
python legal_research.py ruta/al/documento.pdf
python document_drafting.py
```

## Estructura del proyecto

| Archivo | Rol |
|---|---|
| `app.py` | Interfaz Streamlit unificada (router, tema visual, autenticación) |
| `auth.py` | Registro/login, hashing de contraseñas, recuperación por pregunta de seguridad |
| `config.py` | Configuración de proveedores de LLM, prompts y umbrales |
| `contract_risk_analyzer.py` | Lógica de análisis de riesgo contractual |
| `legal_research.py` | Extracción de texto, embeddings, RAG y despacho a los proveedores de LLM |
| `knowledge_base.py` | Persistencia de la biblioteca compartida (documentos, chunks, chat, actividad) |
| `document_drafting.py` | Generación y exportación (.docx/.txt) de documentos redactados |
| `prisma/schema.prisma.template` | Plantilla versionada del esquema de base de datos (provider dinámico) |
| `scripts/prepare_prisma_schema.py` | Genera `prisma/schema.prisma` (gitignored) desde la plantilla según `DB_PROVIDER` |
| `Dockerfile` | Imagen base para despliegue (demo y producción), instala Tesseract OCR + dependencias |
| `.interface-design/system.md` | Sistema de diseño de la UI (paleta, tipografía, patrones, modo oscuro) |

## Ambientes (demo / producción)

La app está pensada para correr como **dos ambientes separados desde la misma imagen Docker**: código y `Dockerfile` idénticos, solo cambian las variables de entorno.

| | Demo | Producción (PRD) |
|---|---|---|
| Propósito | Mostrar la app a prospectos, pruebas | Cliente que ya contrató, datos reales |
| Hosting | Plan gratis/barato, scale-to-zero (ej. Cloud Run free tier) | Plan pagado, siempre encendido |
| Base de datos | Postgres gestionado, tier gratuito (ej. Neon free) | Postgres gestionado, plan pagado, **instancia separada de demo** |
| Plantilla de env | [.env.demo.example](.env.demo.example) | [.env.prod.example](.env.prod.example) |

Ambos ambientes usan `DB_PROVIDER=postgresql` — SQLite queda reservado solo para desarrollo local (ver sección de Base de datos arriba), porque el filesystem de un contenedor en la nube es efímero y no persiste entre reinicios/redeploys.

Copia la plantilla correspondiente (`.env.demo.example` → `.env.demo`, `.env.prod.example` → `.env.prod`), completa las credenciales reales, y pásalas al servicio de despliegue como variables de entorno (o un secret manager) — **nunca subir esos archivos al repo ni hornearlos en la imagen**.

### Despliegue con Docker

```bash
docker build -t legal-ai-tools .
docker run -p 8501:8501 --env-file .env.demo legal-ai-tools
```

El [Dockerfile](Dockerfile) instala Tesseract OCR (`apt-get`, liviano ~30-50 MB, no requiere Windows), instala las dependencias de Python (incluyendo `torch` CPU-only, ver nota arriba), descarga el modelo de spaCy en español, genera el cliente de Prisma con `DB_PROVIDER=postgresql` por defecto, y sirve la app en el puerto de la variable `PORT` (o `8501` si no está definida).

## Notas de despliegue en la nube

- **SQLite (`file:./app.db`) es solo para desarrollo local.** En un contenedor efímero (Cloud Run, Render, etc.) el filesystem no persiste entre reinicios/redeploys — para demo y producción, usar `DB_PROVIDER=postgresql` apuntando a un Postgres gestionado (ej. Neon, Supabase).
- **OCR (Tesseract):** el binario debe instalarse a nivel de sistema operativo (`apt-get install tesseract-ocr` en la imagen Docker basada en Linux) — no basta con las dependencias de `requirements.txt`. Ya incluido en el `Dockerfile`.
- **Peso de la imagen:** ver la nota sobre `torch` CPU-only arriba — es la dependencia más pesada del proyecto y ya está optimizada para despliegue.
- **Secretos:** nunca commitear `.env`, `.env.demo` ni `.env.prod` (ya están en `.gitignore`); en despliegue real usar variables de entorno del proveedor cloud o un secret manager en vez de un archivo `.env` dentro del contenedor.
