"""
legal_research.py

Herramienta de investigacion juridica sobre un PDF:

1. Recibe la ruta de un PDF como argumento.
2. Extrae el texto y lo divide en fragmentos ("chunks") de ~500 palabras.
3. Genera embeddings de cada fragmento con sentence-transformers
   (all-MiniLM-L6-v2).
4. Permite hacer preguntas desde la terminal; recupera los fragmentos mas
   relevantes (busqueda semantica) y se los pasa como contexto al LLM
   configurado en config.py (Gemini, OpenAI o Claude).

Uso:
    python legal_research.py ruta/al/documento.pdf
"""

import argparse
import sys

import numpy as np
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

import config


def extract_text_from_pdf(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    pages_text = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages_text)


def chunk_text(text: str, chunk_size_words: int = config.CHUNK_SIZE_WORDS) -> list[str]:
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size_words):
        chunk = " ".join(words[i:i + chunk_size_words])
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def embed_chunks(model: SentenceTransformer, chunks: list[str]) -> np.ndarray:
    embeddings = model.encode(chunks, convert_to_numpy=True, normalize_embeddings=True)
    return embeddings


def retrieve_top_chunks(
    model: SentenceTransformer,
    question: str,
    chunks: list[str],
    chunk_embeddings: np.ndarray,
    top_k: int = config.TOP_K_CHUNKS,
) -> list[tuple[int, str, float]]:
    query_embedding = model.encode([question], convert_to_numpy=True, normalize_embeddings=True)[0]
    scores = chunk_embeddings @ query_embedding
    top_indices = np.argsort(scores)[::-1][:top_k]
    return [(int(i), chunks[i], float(scores[i])) for i in top_indices]


def build_prompt(question: str, retrieved: list[tuple[int, str, float]]) -> str:
    context_blocks = "\n\n".join(
        f"[Fragmento {i}]\n{chunk}" for i, chunk, _ in retrieved
    )
    return (
        f"Contexto extraido del documento:\n\n{context_blocks}\n\n"
        f"Pregunta: {question}\n\n"
        "Responde en espanol, basandote solo en el contexto anterior."
    )


def ask_claude(prompt: str, model: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=config.SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def ask_openai(prompt: str, model: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": config.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content


def ask_gemini(prompt: str, model: str) -> str:
    import google.generativeai as genai

    genai.configure(api_key=config.GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel(model, system_instruction=config.SYSTEM_PROMPT)
    response = gemini_model.generate_content(prompt)
    return response.text


def ask_llm(prompt: str, provider_config: dict) -> str:
    provider = provider_config["provider"]
    model = provider_config["model"]
    if provider == "claude":
        return ask_claude(prompt, model)
    if provider == "openai":
        return ask_openai(prompt, model)
    if provider == "gemini":
        return ask_gemini(prompt, model)
    raise ValueError(f"Proveedor no soportado: {provider}")


def main():
    parser = argparse.ArgumentParser(description="Investigacion juridica sobre un PDF")
    parser.add_argument("pdf_path", help="Ruta al archivo PDF a analizar")
    args = parser.parse_args()

    provider_config = config.get_active_provider_config()
    print(f"Proveedor de LLM activo: {provider_config['provider']} ({provider_config['model']})")

    print(f"Leyendo PDF: {args.pdf_path}")
    text = extract_text_from_pdf(args.pdf_path)
    if not text.strip():
        print("No se pudo extraer texto del PDF (¿esta escaneado sin OCR?).", file=sys.stderr)
        sys.exit(1)

    chunks = chunk_text(text)
    print(f"Documento dividido en {len(chunks)} fragmentos de ~{config.CHUNK_SIZE_WORDS} palabras.")

    print(f"Generando embeddings con {config.EMBEDDING_MODEL}...")
    embedding_model = SentenceTransformer(config.EMBEDDING_MODEL)
    chunk_embeddings = embed_chunks(embedding_model, chunks)

    print("\nListo. Escribe tu pregunta (o 'salir' para terminar).\n")
    while True:
        try:
            question = input("Pregunta> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not question:
            continue
        if question.lower() in {"salir", "exit", "quit"}:
            break

        retrieved = retrieve_top_chunks(embedding_model, question, chunks, chunk_embeddings)
        prompt = build_prompt(question, retrieved)

        try:
            answer = ask_llm(prompt, provider_config)
        except Exception as exc:
            print(f"Error al consultar el LLM: {exc}", file=sys.stderr)
            continue

        print(f"\n{answer}\n")


if __name__ == "__main__":
    main()
