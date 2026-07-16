"""
knowledge_base.py

Persistencia de la biblioteca juridica compartida: documentos, fragmentos
("chunks") con sus embeddings, historial de chat por usuario y registro de
actividad. Sigue el mismo patron que auth.py: cada operacion abre y cierra
su propia conexion de corta duracion, sin cache compartido entre sesiones o
threads de Streamlit.
"""

import json
from contextlib import contextmanager

import numpy as np
from prisma import Prisma
from prisma.errors import UniqueViolationError

import config


@contextmanager
def get_db():
    db = Prisma()
    db.connect()
    try:
        yield db
    finally:
        db.disconnect()


def find_existing_document(filename: str, size_bytes: int) -> int | None:
    """Chequeo barato de duplicados: una sola consulta indexada por
    (filename, sizeBytes), sin leer ni procesar el archivo."""
    with get_db() as db:
        doc = db.document.find_first(
            where={"filename": filename, "sizeBytes": size_bytes}
        )
    return doc.id if doc is not None else None


def add_document(
    filename: str,
    size_bytes: int,
    username: str,
    chunks: list[str],
    embeddings: np.ndarray,
) -> tuple[int, bool]:
    """Crea Document + Chunks. Si (filename, sizeBytes) ya existe, devuelve
    el id existente sin duplicar filas. Retorna (document_id, fue_creado)."""
    with get_db() as db:
        existing = db.document.find_first(
            where={"filename": filename, "sizeBytes": size_bytes}
        )
        if existing is not None:
            return existing.id, False

        user = db.user.find_unique(where={"username": username})
        try:
            doc = db.document.create(
                data={
                    "filename": filename,
                    "sizeBytes": size_bytes,
                    "uploadedById": user.id,
                }
            )
        except UniqueViolationError:
            doc = db.document.find_first(
                where={"filename": filename, "sizeBytes": size_bytes}
            )
            return doc.id, False

        db.chunk.create_many(
            data=[
                {
                    "documentId": doc.id,
                    "ordinal": i,
                    "text": chunk,
                    "embedding": json.dumps(embedding.tolist()),
                }
                for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
            ]
        )
        return doc.id, True


def list_documents() -> list[dict]:
    with get_db() as db:
        docs = db.document.find_many(
            include={"uploadedBy": True, "chunks": True},
            order={"uploadedAt": "desc"},
        )
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "uploaded_by": d.uploadedBy.username,
            "uploaded_at": d.uploadedAt,
            "chunk_count": len(d.chunks),
            "document_type": d.documentType,
            "summary": d.summary,
        }
        for d in docs
    ]


def get_document(document_id: int) -> dict | None:
    with get_db() as db:
        doc = db.document.find_unique(
            where={"id": document_id}, include={"chunks": True}
        )
    if doc is None:
        return None
    chunks = sorted(doc.chunks, key=lambda c: c.ordinal)
    return {
        "id": doc.id,
        "filename": doc.filename,
        "document_type": doc.documentType,
        "summary": doc.summary,
        "chunks": [c.text for c in chunks],
    }


def set_document_analysis(document_id: int, document_type: str, summary: str) -> None:
    with get_db() as db:
        db.document.update(
            where={"id": document_id},
            data={"documentType": document_type, "summary": summary},
        )


def retrieve_top_chunks_for_document(
    document_id: int, query_embedding: np.ndarray, top_k: int = config.TOP_K_CHUNKS
) -> list[tuple[int, str, float]]:
    """Recuperacion acotada a UN documento (no a toda la biblioteca).
    Devuelve (ordinal, texto, score), mejor primero — mismo shape que
    legal_research.retrieve_top_chunks para reusar build_prompt tal cual."""
    with get_db() as db:
        chunks = db.chunk.find_many(where={"documentId": document_id})

    if not chunks:
        return []

    matrix = np.array([json.loads(c.embedding) for c in chunks], dtype=np.float32)
    scores = matrix @ query_embedding
    top_indices = np.argsort(scores)[::-1][:top_k]
    return [(chunks[i].ordinal, chunks[i].text, float(scores[i])) for i in top_indices]


def retrieve_top_chunks_global(
    query_embedding: np.ndarray, top_k: int = config.TOP_K_CHUNKS
) -> list[tuple[str, str, float]]:
    """Recuperacion cruzada entre TODOS los documentos de la biblioteca
    compartida. Devuelve (filename, texto, score), mejor primero."""
    with get_db() as db:
        chunks = db.chunk.find_many(include={"document": True})

    if not chunks:
        return []

    matrix = np.array([json.loads(c.embedding) for c in chunks], dtype=np.float32)
    scores = matrix @ query_embedding
    top_indices = np.argsort(scores)[::-1][:top_k]
    return [
        (chunks[i].document.filename, chunks[i].text, float(scores[i]))
        for i in top_indices
    ]


def log_chat_message(username: str, role: str, content: str) -> None:
    with get_db() as db:
        user = db.user.find_unique(where={"username": username})
        db.chatmessage.create(data={"userId": user.id, "role": role, "content": content})


def get_chat_history(username: str) -> list[dict]:
    with get_db() as db:
        user = db.user.find_unique(where={"username": username})
        messages = db.chatmessage.find_many(
            where={"userId": user.id}, order={"createdAt": "asc"}
        )
    return [{"role": m.role, "content": m.content} for m in messages]


def log_activity(username: str, tool: str, filename: str) -> None:
    with get_db() as db:
        user = db.user.find_unique(where={"username": username})
        db.activitylog.create(data={"userId": user.id, "tool": tool, "filename": filename})


def get_activity_log(limit: int = 50) -> list[dict]:
    with get_db() as db:
        logs = db.activitylog.find_many(
            include={"user": True}, order={"createdAt": "desc"}, take=limit
        )
    return [
        {
            "username": l.user.username,
            "tool": l.tool,
            "filename": l.filename,
            "created_at": l.createdAt,
        }
        for l in logs
    ]
