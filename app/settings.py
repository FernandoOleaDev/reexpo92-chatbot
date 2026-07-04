"""Ajustes EN CALIENTE editables desde el panel (persistidos en Supabase).

Se guardan en la tabla `rag_settings` (fila única id=1, columna `config` jsonb), de
modo que sobreviven a los reinicios de Railway. Los valores de entorno (config.py)
actúan como valores por defecto si el ajuste no está definido.

Claves soportadas:
  - groq_model    (str)   modelo de Groq a usar
  - llm_enabled   (bool)  si false, el chat responde en modo "solo búsqueda"
  - temperature   (float) creatividad de la respuesta
  - sources       (dict)  {re_memory:true, photo:true, knowledge:true, ayuda:true}
"""
from __future__ import annotations

import threading
import time

from . import config, db

_cache: dict | None = None
_cache_ts = 0.0
_TTL = 15  # segundos: el panel ve cambios casi al instante; el chat no martillea la BD
_lock = threading.Lock()

_DEFAULTS = {
    "groq_model": config.GROQ_MODEL,
    "llm_enabled": True,
    "temperature": 0.3,
    "sources": {"re_memory": True, "photo": True, "knowledge": True, "ayuda": True},
}


def _load() -> dict:
    try:
        rows = db.select("rag_settings", {"select": "config", "id": "eq.1", "limit": "1"})
        stored = (rows[0].get("config") if rows else None) or {}
    except Exception:
        stored = {}
    merged = dict(_DEFAULTS)
    merged.update({k: v for k, v in stored.items() if v is not None})
    # `sources` se fusiona a nivel de clave para no perder tipos nuevos
    src = dict(_DEFAULTS["sources"])
    if isinstance(stored.get("sources"), dict):
        src.update(stored["sources"])
    merged["sources"] = src
    return merged


def get_all(force: bool = False) -> dict:
    global _cache, _cache_ts
    now = time.time()
    if force or _cache is None or (now - _cache_ts) > _TTL:
        with _lock:
            _cache = _load()
            _cache_ts = now
    return dict(_cache)


def get(key: str, default=None):
    return get_all().get(key, default)


def update(patch: dict) -> dict:
    """Fusiona `patch` con lo guardado y persiste. Devuelve la config resultante."""
    current = _load()
    for k, v in patch.items():
        if k == "sources" and isinstance(v, dict):
            merged_src = dict(current.get("sources") or {})
            merged_src.update(v)
            current["sources"] = merged_src
        else:
            current[k] = v
    db.upsert("rag_settings", [{"id": 1, "config": current}], on_conflict="id")
    global _cache, _cache_ts
    _cache = current
    _cache_ts = time.time()
    return current
