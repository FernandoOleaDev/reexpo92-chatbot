"""Fuentes de conocimiento del chatbot. Cada fuente produce "documentos" con la forma:

    {source_type, source_id, title, url, text, updated_at}

El indexador los trocea, embebe y guarda en `kb_chunks`. Fuentes:
  - re_memory : catálogo de re-memorias (fichas)            [incremental por updated_at]
  - photo     : fotos aprobadas de la comunidad             [incremental por updated_at]
  - knowledge : artículos how-to del repo (knowledge/*.md)  [siempre; pocos y baratos]
  - ayuda     : página /ayuda del sitio (si AYUDA_URL)      [siempre]
"""
from __future__ import annotations

import glob
import os
import re
from typing import Iterable

import requests

from . import config, db

KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge")


# ── utilidades ──────────────────────────────────────────────────────────────────
def _flatten_attributes(attrs: dict | None) -> str:
    if not isinstance(attrs, dict):
        return ""
    parts = []
    for k, v in attrs.items():
        if v in (None, "", [], {}):
            continue
        if isinstance(v, (list, tuple)):
            v = ", ".join(str(x) for x in v if x not in (None, ""))
        elif isinstance(v, dict):
            continue  # estados de reconstrucción, etc.: no aportan como texto
        label = str(k).replace("_", " ").strip()
        parts.append(f"{label}: {v}")
    return "\n".join(parts)


def _iso(v) -> str | None:
    return v if isinstance(v, str) else None


# ── re-memorias (fichas) ─────────────────────────────────────────────────────────
def fetch_re_memories(since: str | None) -> list[dict]:
    params = {
        "select": "id,name,description,attributes,updated_at",
        "order": "updated_at.asc",
        "limit": "2000",
    }
    if since:
        params["updated_at"] = f"gt.{since}"
    docs = []
    for r in db.select("re_memories", params):
        name = (r.get("name") or "").strip()
        desc = (r.get("description") or "").strip()
        attrs = _flatten_attributes(r.get("attributes"))
        text = "\n\n".join(p for p in [name, desc, attrs] if p).strip()
        if not text:
            continue
        docs.append({
            "source_type": "re_memory",
            "source_id": str(r["id"]),
            "title": name or "Re-memoria",
            "url": f"/re-memories/{r['id']}",
            "text": text,
            "updated_at": _iso(r.get("updated_at")),
        })
    return docs


# ── fotos de la comunidad (aprobadas) ────────────────────────────────────────────
def fetch_photos(since: str | None) -> list[dict]:
    params = {
        "select": "id,title,description,tags,updated_at",
        "status": "eq.aprobada",
        "order": "updated_at.asc",
        "limit": "5000",
    }
    if since:
        params["updated_at"] = f"gt.{since}"
    docs = []
    for r in db.select("community_photos", params):
        title = (r.get("title") or "").strip()
        desc = (r.get("description") or "").strip()
        tags = r.get("tags") or []
        tagtxt = ", ".join(t for t in tags if t) if isinstance(tags, list) else ""
        text = "\n".join(p for p in [title, desc, (f"Etiquetas: {tagtxt}" if tagtxt else "")] if p).strip()
        if not text:
            continue
        url = "/fotos" + (f"?tag={tags[0]}" if isinstance(tags, list) and tags else "")
        docs.append({
            "source_type": "photo",
            "source_id": str(r["id"]),
            "title": title or "Foto de la comunidad",
            "url": url,
            "text": text,
            "updated_at": _iso(r.get("updated_at")),
        })
    return docs


# ── artículos how-to del repo (knowledge/*.md) ───────────────────────────────────
_FRONT_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _parse_front(raw: str) -> tuple[dict, str]:
    m = _FRONT_RE.match(raw)
    meta: dict[str, str] = {}
    body = raw
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
        body = raw[m.end():]
    return meta, body.strip()


def fetch_knowledge() -> list[dict]:
    docs = []
    for path in sorted(glob.glob(os.path.join(KNOWLEDGE_DIR, "*.md"))):
        raw = open(path, encoding="utf-8").read()
        meta, body = _parse_front(raw)
        slug = os.path.splitext(os.path.basename(path))[0]
        title = meta.get("title") or (body.splitlines()[0].lstrip("# ").strip() if body else slug)
        url = meta.get("url") or "/ayuda"
        docs.append({
            "source_type": "knowledge",
            "source_id": slug,
            "title": title,
            "url": url,
            "text": body,
            "updated_at": None,  # siempre se reindexa (hash decide si cambió)
        })
    return docs


# ── página /ayuda del sitio (opcional) ───────────────────────────────────────────
def fetch_ayuda() -> list[dict]:
    if not config.AYUDA_URL:
        return []
    try:
        html = requests.get(config.AYUDA_URL, timeout=20).text
    except Exception:
        return []
    # Extracción de texto muy simple (sin dependencias): quitar scripts/estilos y tags.
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < 80:
        return []
    from urllib.parse import urlparse
    path = urlparse(config.AYUDA_URL).path or "/ayuda"
    return [{
        "source_type": "ayuda",
        "source_id": "ayuda",
        "title": "Ayuda de la web",
        "url": path,
        "text": text,
        "updated_at": None,
    }]


# Registro de fuentes: (nombre, incremental?, función)
def all_sources(since_map: dict[str, str | None]) -> Iterable[dict]:
    yield from fetch_re_memories(since_map.get("re_memory"))
    yield from fetch_photos(since_map.get("photo"))
    yield from fetch_knowledge()
    yield from fetch_ayuda()


INCREMENTAL_TYPES = {"re_memory", "photo"}      # usan watermark updated_at
FULL_TYPES = {"knowledge", "ayuda"}             # se reprocesan siempre (hash filtra)
