"""Monitor del rate limit de Groq.

Groq devuelve en CADA respuesta las cabeceras `x-ratelimit-*` (peticiones y tokens
restantes, límite y tiempo de reinicio). Guardamos el último snapshot en memoria y en
la tabla `rag_ratelimit` (persistente) para que el panel avise cuando nos acercamos al
límite, incluso tras un reinicio del servicio.
"""
from __future__ import annotations

import datetime as dt

from . import db

_latest: dict = {}


def _num(v):
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        try:
            return float(v)
        except (ValueError, TypeError):
            return None


def save_from_headers(headers) -> None:
    """Extrae las cabeceras x-ratelimit-* y persiste el snapshot."""
    snap = {
        "limit_requests": _num(headers.get("x-ratelimit-limit-requests")),
        "remaining_requests": _num(headers.get("x-ratelimit-remaining-requests")),
        "reset_requests": headers.get("x-ratelimit-reset-requests"),
        "limit_tokens": _num(headers.get("x-ratelimit-limit-tokens")),
        "remaining_tokens": _num(headers.get("x-ratelimit-remaining-tokens")),
        "reset_tokens": headers.get("x-ratelimit-reset-tokens"),
        "at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    if snap["limit_requests"] is None and snap["remaining_requests"] is None:
        return  # la respuesta no traía cabeceras de rate limit
    global _latest
    _latest = snap
    try:
        db.upsert("rag_ratelimit", [{"id": 1, "data": snap, "updated_at": snap["at"]}], on_conflict="id")
    except Exception:
        pass


def latest() -> dict:
    """Último snapshot (memoria; si no hay, lo lee de la BD)."""
    global _latest
    if _latest:
        return _latest
    try:
        rows = db.select("rag_ratelimit", {"select": "data", "id": "eq.1", "limit": "1"})
        _latest = (rows[0]["data"] if rows else {}) or {}
    except Exception:
        _latest = {}
    return _latest


def status_level() -> str:
    """'ok' | 'warn' | 'crit' según cuántas peticiones quedan (para colorear el panel)."""
    d = latest()
    lim, rem = d.get("limit_requests"), d.get("remaining_requests")
    if not lim or rem is None:
        return "unknown"
    frac = rem / lim if lim else 1
    if frac <= 0.1:
        return "crit"
    if frac <= 0.25:
        return "warn"
    return "ok"
