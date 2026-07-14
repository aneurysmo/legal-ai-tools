"""
Configuracion central para legal_research.py.

Controla que proveedor de LLM se usa (Gemini, OpenAI o Claude Code / API de
Anthropic) y los parametros de embeddings/chunking. Las claves de API se
leen desde variables de entorno (usa un archivo .env si lo prefieres, junto
con python-dotenv).
"""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
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

SYSTEM_PROMPT = (
    "Eres un asistente de investigacion juridica. Responde unicamente con "
    "base en los fragmentos del documento que se te entregan como contexto. "
    "Si la respuesta no esta en el contexto, dilo explicitamente en lugar de "
    "inventarla. Cuando sea util, menciona el numero de fragmento en el que "
    "encontraste la informacion."
)


def get_active_provider_config():
    """Valida y devuelve la configuracion del proveedor de LLM activo."""
    if LLM_PROVIDER == "claude":
        if not ANTHROPIC_API_KEY:
            raise RuntimeError(
                "LLM_PROVIDER='claude' pero falta ANTHROPIC_API_KEY en el entorno."
            )
        return {"provider": "claude", "model": ANTHROPIC_MODEL}

    if LLM_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            raise RuntimeError(
                "LLM_PROVIDER='openai' pero falta OPENAI_API_KEY en el entorno."
            )
        return {"provider": "openai", "model": OPENAI_MODEL}

    if LLM_PROVIDER == "gemini":
        if not GEMINI_API_KEY:
            raise RuntimeError(
                "LLM_PROVIDER='gemini' pero falta GEMINI_API_KEY en el entorno."
            )
        return {"provider": "gemini", "model": GEMINI_MODEL}

    raise ValueError(
        f"LLM_PROVIDER desconocido: '{LLM_PROVIDER}'. Usa 'claude', 'openai' o 'gemini'."
    )
