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


def _fresh_progress() -> dict:
    return {"phase": "inactivo", "current": 0, "total": 0, "percent": 0,
            "chunks": 0, "log": [], "started_at": None, "finished_at": None}


status: dict = {
    "running": False,
    "last_run": None,
    "last_mode": None,
    "last_report": None,
    "last_error": None,
    "progress": _fresh_progress(),
}


def _plog(msg: str) -> None:
    """Añade una línea al log de progreso (panel en vivo) y la imprime (consola/logs)."""
    p = status["progress"]
    ts = dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    p["log"].append(line)
    p["log"] = p["log"][-60:]  # solo las últimas líneas
    print(line, flush=True)  # visible en la consola (indexado local) y en los logs de Railway


def _set_progress(current: int, total: int, chunks: int) -> None:
    p = status["progress"]
    p["current"], p["total"], p["chunks"] = current, total, chunks
    p["percent"] = round(100 * current / total) if total else 0


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
    status["progress"] = _fresh_progress()
    prog = status["progress"]
    prog["phase"] = "recopilando"
    prog["started_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    report: dict = {"processed": {}, "chunks": 0, "skipped_unchanged": 0}
    try:
        _plog("Cargando el modelo de embeddings…")
        embeddings.warmup()
        enabled = settings.get("sources") or {}
        watermarks = {} if full else _read_watermarks()
        since_map = {t: watermarks.get(t) for t in sources.INCREMENTAL_TYPES}

        _plog(f"Recopilando documentos ({'completo' if full else 'solo nuevo'})…")
        docs = [d for d in sources.all_sources(since_map)
                if (not only or d["source_type"] in only) and enabled.get(d["source_type"], True)]
        total = len(docs)
        by_type: dict[str, int] = {}
        for d in docs:
            by_type[d["source_type"]] = by_type.get(d["source_type"], 0) + 1
        _plog("A procesar: " + (", ".join(f"{k}={v}" for k, v in by_type.items()) or "nada nuevo"))
        prog["phase"] = "indexando"

        max_seen: dict[str, str] = {}
        for i, doc in enumerate(docs, 1):
            st = doc["source_type"]
            n = _replace_doc_chunks(doc)
            if n == 0:
                report["skipped_unchanged"] += 1
            report["processed"][st] = report["processed"].get(st, 0) + 1
            report["chunks"] += n
            _set_progress(i, total, report["chunks"])
            if i % 10 == 0 or i == total:
                _plog(f"{i}/{total} · {st} · «{(doc.get('title') or '')[:40]}» (+{report['chunks']} chunks)")
            ua = doc.get("updated_at")
            if st in sources.INCREMENTAL_TYPES and ua:
                if st not in max_seen or ua > max_seen[st]:
                    max_seen[st] = ua

        prog["phase"] = "guardando estado"
        # actualizar estado por fuente (upsert POR FILA: PostgREST exige las mismas
        # claves en un upsert en lote, y aquí unas filas llevan 'watermark' y otras no)
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        for st in list(sources.INCREMENTAL_TYPES) + list(sources.FULL_TYPES):
            total = db.count("kb_chunks", {"source_type": f"eq.{st}"})
            row = {"source_type": st, "last_indexed_at": now, "chunk_count": total}
            wm = max_seen.get(st) or (None if full else watermarks.get(st))
            if wm:
                row["watermark"] = wm
            db.upsert("rag_index_state", [row], on_conflict="source_type")

        status["last_report"] = report
        status["last_run"] = now
        status["last_mode"] = "completo" if full else "incremental"
        prog["phase"] = "finalizado"
        prog["finished_at"] = now
        prog["percent"] = 100
        _plog(f"✓ Listo: +{report['chunks']} chunks · {report['skipped_unchanged']} sin cambios.")
        return report
    except Exception as e:  # noqa: BLE001
        status["last_error"] = str(e)
        prog["phase"] = "error"
        _plog(f"✗ Error: {e}")
        raise
    finally:
        status["running"] = False
        _run_lock.release()


def start_async(full: bool = False, only: list[str] | None = None) -> bool:
    """Lanza el indexado en un hilo (para no bloquear el panel). False si ya corre."""
    if status["running"]:
        return False

    def _job():
        try:
            run_index(full=full, only=only)
        except Exception:
            pass  # el error queda en status["last_error"] / progress

    threading.Thread(target=_job, daemon=True).start()
    return True
