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
