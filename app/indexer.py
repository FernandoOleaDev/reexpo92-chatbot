"""Indexador incremental: reúne documentos de las fuentes, los trocea, calcula
embeddings (e5-base) y hace upsert en `kb_chunks`.

- Tipos incrementales (re_memory, photo): solo procesa lo cambiado desde la marca
  de agua (`rag_index_state.watermark` = mayor updated_at ya procesado).
- Tipos completos (knowledge, ayuda): se recorren siempre, pero un hash de documento
  evita recalcular embeddings si el texto no cambió.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import threading

from . import db, embeddings, settings, sources
from .config import CHUNK_CHARS, CHUNK_OVERLAP

_run_lock = threading.Lock()

status: dict = {
    "running": False,
    "last_run": None,
    "last_mode": None,
    "last_report": None,
    "last_error": None,
}


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_text(text: str) -> list[str]:
    """Trocea por párrafos acumulando hasta ~CHUNK_CHARS, con solape."""
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paras:
        paras = [text.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 2 <= CHUNK_CHARS:
            buf = f"{buf}\n\n{p}" if buf else p
        else:
            if buf:
                chunks.append(buf)
            if len(p) <= CHUNK_CHARS:
                buf = p
            else:
                # párrafo enorme: cortar duro con solape
                for i in range(0, len(p), CHUNK_CHARS - CHUNK_OVERLAP):
                    chunks.append(p[i:i + CHUNK_CHARS])
                buf = ""
    if buf:
        chunks.append(buf)
    # solape entre chunks contiguos para no perder contexto en los bordes
    if CHUNK_OVERLAP and len(chunks) > 1:
        out = [chunks[0]]
        for i in range(1, len(chunks)):
            tail = chunks[i - 1][-CHUNK_OVERLAP:]
            out.append((tail + "\n" + chunks[i]).strip())
        chunks = out
    return chunks


def _read_watermarks() -> dict[str, str | None]:
    try:
        rows = db.select("rag_index_state", {"select": "source_type,watermark"})
    except Exception:
        rows = []
    return {r["source_type"]: r.get("watermark") for r in rows}


def _existing_doc_hash(source_type: str, source_id: str) -> str | None:
    try:
        rows = db.select("kb_chunks", {
            "select": "doc_hash", "source_type": f"eq.{source_type}",
            "source_id": f"eq.{source_id}", "limit": "1",
        })
    except Exception:
        return None
    return rows[0]["doc_hash"] if rows else None


def _replace_doc_chunks(doc: dict) -> int:
    """Borra los chunks previos del documento e inserta los nuevos. Devuelve nº chunks."""
    st, sid = doc["source_type"], doc["source_id"]
    doc_hash = _hash(doc["text"])
    if _existing_doc_hash(st, sid) == doc_hash:
        return 0  # sin cambios: no recalculamos embeddings

    pieces = chunk_text(doc["text"])
    vecs = embeddings.embed_passages(pieces)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    rows = []
    for i, (piece, vec) in enumerate(zip(pieces, vecs)):
        rows.append({
            "source_type": st, "source_id": sid, "chunk_index": i,
            "title": doc.get("title"), "content": piece, "url": doc.get("url"),
            "content_hash": _hash(piece), "doc_hash": doc_hash,
            "embedding": vec, "updated_at": now,
        })
    # borrar previos y subir nuevos (upsert por unique(source_type,source_id,chunk_index))
    db.delete("kb_chunks", {"source_type": f"eq.{st}", "source_id": f"eq.{sid}"})
    db.upsert("kb_chunks", rows, on_conflict="source_type,source_id,chunk_index")
    return len(rows)


def run_index(full: bool = False, only: list[str] | None = None) -> dict:
    """Ejecuta una pasada de indexado. `full`=True ignora las marcas de agua."""
    if not _run_lock.acquire(blocking=False):
        return {"skipped": "ya hay un indexado en curso"}
    status["running"] = True
    status["last_error"] = None
    report: dict = {"processed": {}, "chunks": 0, "skipped_unchanged": 0}
    try:
        embeddings.warmup()
        enabled = settings.get("sources") or {}
        watermarks = {} if full else _read_watermarks()
        since_map = {t: watermarks.get(t) for t in sources.INCREMENTAL_TYPES}

        max_seen: dict[str, str] = {}
        for doc in sources.all_sources(since_map):
            st = doc["source_type"]
            if only and st not in only:
                continue
            if not enabled.get(st, True):
                continue
            n = _replace_doc_chunks(doc)
            if n == 0:
                report["skipped_unchanged"] += 1
            report["processed"][st] = report["processed"].get(st, 0) + 1
            report["chunks"] += n
            ua = doc.get("updated_at")
            if st in sources.INCREMENTAL_TYPES and ua:
                if st not in max_seen or ua > max_seen[st]:
                    max_seen[st] = ua

        # actualizar estado por fuente
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        state_rows = []
        for st in list(sources.INCREMENTAL_TYPES) + list(sources.FULL_TYPES):
            total = db.count("kb_chunks", {"source_type": f"eq.{st}"})
            row = {"source_type": st, "last_indexed_at": now, "chunk_count": total}
            wm = max_seen.get(st) or (None if full else watermarks.get(st))
            if wm:
                row["watermark"] = wm
            state_rows.append(row)
        db.upsert("rag_index_state", state_rows, on_conflict="source_type")

        status["last_report"] = report
        status["last_run"] = now
        status["last_mode"] = "completo" if full else "incremental"
        return report
    except Exception as e:  # noqa: BLE001
        status["last_error"] = str(e)
        raise
    finally:
        status["running"] = False
        _run_lock.release()
