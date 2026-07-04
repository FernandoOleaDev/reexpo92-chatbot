"""Motor de embeddings local con el MISMO modelo que el RAG de vídeos del proyecto
(`intfloat/multilingual-e5-base`, 768 dim). Sin claves, sin coste por token.

El modelo se carga una vez (perezoso) y se reutiliza. e5 exige prefijos:
  - documentos (corpus):  "passage: <texto>"
  - consultas (usuario):  "query: <texto>"
"""
from __future__ import annotations

import threading

from . import config

_model = None
_lock = threading.Lock()


def _get():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer
                _model = SentenceTransformer(config.EMBED_MODEL)
    return _model


def warmup() -> None:
    """Carga el modelo por adelantado (llamar al arrancar)."""
    _get()


def embed_passages(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    m = _get()
    vecs = m.encode([f"passage: {t}" for t in texts], normalize_embeddings=True,
                    batch_size=32, show_progress_bar=False)
    return [v.tolist() for v in vecs]


def embed_query(text: str) -> list[float]:
    m = _get()
    v = m.encode(f"query: {text}", normalize_embeddings=True)
    return v.tolist()
