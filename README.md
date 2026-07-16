# Legal AI Tools

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

### Base de datos (Prisma + SQLite)

```bash
prisma generate --schema=prisma/schema.prisma
prisma db push --schema=prisma/schema.prisma
```

Vuelve a correr ambos comandos cada vez que cambies `prisma/schema.prisma`.

### Variables de entorno

Copia `.env.example` a `.env` y completa tu proveedor principal:

```
LLM_PROVIDER=gemini
GEMINI_API_KEY=tu_clave
DATABASE_URL=file:./app.db
```

Proveedores adicionales soportados (opcionales, descomenta según necesites): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `GITHUB_API_KEY`, `GROQ_API_KEY`.

**Fallback automático:** si configuras `LLM_FALLBACK_PROVIDER` (ej. `groq`) con su propia API key, la app reintenta automáticamente con ese proveedor cuando el principal falla (cuota agotada, error de red, etc.) — útil para no interrumpir una demo en vivo. Ver `config.get_provider_config` / `legal_research.ask_llm`.

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
| `prisma/schema.prisma` | Esquema de la base de datos SQLite |
| `.interface-design/system.md` | Sistema de diseño de la UI (paleta, tipografía, patrones, modo oscuro) |
