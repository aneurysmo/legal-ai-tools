"""
Configuracion central para legal_research.py.

Controla que proveedor de LLM se usa (Gemini, OpenAI o Claude Code / API de
Anthropic) y los parametros de embeddings/chunking. Las claves de API se
leen desde variables de entorno (usa un archivo .env si lo prefieres, junto
con python-dotenv).
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

# Proveedor activo: "claude", "openai" o "gemini"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "claude").lower()

# --- Embeddings / chunking ---
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_SIZE_WORDS = 500
TOP_K_CHUNKS = 4

# --- Claude (Anthropic API / Claude Code) ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8")

# --- OpenAI ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

# --- Gemini ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# --- DeepSeek (API compatible con OpenAI) ---
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# --- GitHub Models (API compatible con OpenAI, usa un token de GitHub) ---
GITHUB_API_KEY = os.getenv("GITHUB_API_KEY")
GITHUB_MODEL = os.getenv("GITHUB_MODEL", "gpt-4o")

# --- Groq (API compatible con OpenAI, inferencia muy rapida) ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Proveedor de respaldo: si esta configurado y es distinto al proveedor
# activo, ask_llm() reintenta automaticamente con el si el proveedor activo
# falla (cuota agotada, error de red, etc.) para no interrumpir una demo.
LLM_FALLBACK_PROVIDER = os.getenv("LLM_FALLBACK_PROVIDER", "").lower()

SYSTEM_PROMPT = (
    "Eres un asistente de investigacion juridica. Responde unicamente con "
    "base en los fragmentos del documento que se te entregan como contexto. "
    "Si la respuesta no esta en el contexto, dilo explicitamente en lugar de "
    "inventarla. Cuando sea util, menciona el numero de fragmento en el que "
    "encontraste la informacion."
)

LIBRARY_CHAT_SYSTEM_PROMPT = (
    "Eres un asistente de investigacion juridica. Si la pregunta no es sobre "
    "temas legales, indica explicitamente que no puedes ayudar con eso y no "
    "respondas la pregunta. Si en el contexto se incluyen fragmentos de "
    "documentos de la biblioteca, basa tu respuesta en ellos y cita el "
    "nombre del documento del que proviene cada dato. Si no se incluyen "
    "fragmentos (porque no hay ninguno suficientemente relevante en la "
    "biblioteca), responde con tu conocimiento juridico general y aclara "
    "que la respuesta no esta basada en un documento especifico de la "
    "biblioteca."
)

DOCUMENT_TYPE_PROMPT = (
    "Clasifica el siguiente documento legal en una categoria breve "
    "(ej. Contrato, Sentencia, Memorando, Ley/Reglamento, Demanda, Otro). "
    "Responde unicamente con la categoria, sin explicacion adicional.\n\n"
    "Documento:\n{texto}"
)

DOCUMENT_SUMMARY_PROMPT = (
    "Resume el siguiente documento legal en un parrafo breve, y luego lista "
    "los puntos mas importantes en formato de lista con guiones. Responde "
    "en espanol.\n\nDocumento:\n{texto}"
)

# Umbral minimo de similitud coseno para incluir los fragmentos recuperados
# como contexto citable ("anclado" en la biblioteca). Por debajo de esto, el
# chat responde con conocimiento juridico general del LLM en vez de forzar
# una cita a un documento poco relevante. Calibrado empiricamente con
# all-MiniLM-L6-v2 sobre texto legal en espanol: preguntas genuinamente
# ancladas en un documento subido puntuan ~0.6+; preguntas juridicas
# genericas no cubiertas por ningun documento puntuan ~0.35-0.45 (el mismo
# vocabulario legal produce similitud "de fondo" alta); preguntas
# totalmente ajenas al derecho puntuan ~0.2 o menos.
MIN_RELEVANCE_SCORE = 0.55


def get_provider_config(provider_name: str) -> dict:
    """Valida y devuelve la configuracion de UN proveedor especifico (no
    necesariamente el activo). La usan tanto get_active_provider_config()
    como el mecanismo de fallback automatico de ask_llm()."""
    if provider_name == "claude":
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("Falta ANTHROPIC_API_KEY en el entorno.")
        return {"provider": "claude", "model": ANTHROPIC_MODEL}

    if provider_name == "openai":
        if not OPENAI_API_KEY:
            raise RuntimeError("Falta OPENAI_API_KEY en el entorno.")
        return {"provider": "openai", "model": OPENAI_MODEL}

    if provider_name == "gemini":
        if not GEMINI_API_KEY:
            raise RuntimeError("Falta GEMINI_API_KEY en el entorno.")
        return {"provider": "gemini", "model": GEMINI_MODEL}

    if provider_name == "deepseek":
        if not DEEPSEEK_API_KEY:
            raise RuntimeError("Falta DEEPSEEK_API_KEY en el entorno.")
        return {"provider": "deepseek", "model": DEEPSEEK_MODEL}

    if provider_name == "github":
        if not GITHUB_API_KEY:
            raise RuntimeError("Falta GITHUB_API_KEY en el entorno.")
        return {"provider": "github", "model": GITHUB_MODEL}

    if provider_name == "groq":
        if not GROQ_API_KEY:
            raise RuntimeError("Falta GROQ_API_KEY en el entorno.")
        return {"provider": "groq", "model": GROQ_MODEL}

    raise ValueError(
        f"Proveedor desconocido: '{provider_name}'. "
        "Usa 'claude', 'openai', 'gemini', 'deepseek', 'github' o 'groq'."
    )


def get_active_provider_config():
    """Valida y devuelve la configuracion del proveedor de LLM activo
    (LLM_PROVIDER)."""
    try:
        return get_provider_config(LLM_PROVIDER)
    except RuntimeError:
        raise RuntimeError(
            f"LLM_PROVIDER='{LLM_PROVIDER}' pero falta su API key en el entorno."
        )
    except ValueError:
        raise ValueError(
            f"LLM_PROVIDER desconocido: '{LLM_PROVIDER}'. "
            "Usa 'claude', 'openai', 'gemini', 'deepseek', 'github' o 'groq'."
        )
