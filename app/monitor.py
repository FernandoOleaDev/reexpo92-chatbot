"""Analíticas para el panel: agrega `rag_queries` en el propio servicio (tráfico bajo,
así que traemos las filas recientes y agregamos en Python, sin RPC extra)."""
from __future__ import annotations

import collections
import datetime as dt

from . import db


def _since_iso(days: int) -> str:
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()


def _today_iso() -> str:
    now = dt.datetime.now(dt.timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def overview(days: int = 7) -> dict:
    try:
        rows = db.select("rag_queries", {
            "select": "question,mode,answered,matched_count,used_llm,latency_ms,created_at",
            "created_at": f"gte.{_since_iso(days)}",
            "order": "created_at.desc", "limit": "5000",
        })
    except Exception:
        rows = []

    total = len(rows)
    answered = sum(1 for r in rows if r.get("answered"))
    llm = sum(1 for r in rows if r.get("used_llm"))
    lat = [r["latency_ms"] for r in rows if r.get("latency_ms") is not None]
    avg_lat = round(sum(lat) / len(lat)) if lat else 0

    today = _today_iso()
    groq_today = sum(1 for r in rows if r.get("used_llm") and (r.get("created_at") or "") >= today)

    q_counter = collections.Counter()
    gaps = collections.Counter()
    for r in rows:
        q = (r.get("question") or "").strip().lower()
        if not q or r.get("mode") == "social":
            continue
        q_counter[q] += 1
        if not r.get("answered") or (r.get("matched_count") or 0) == 0:
            gaps[q] += 1

    return {
        "days": days,
        "total": total,
        "answered": answered,
        "answered_pct": round(100 * answered / total) if total else 0,
        "llm": llm,
        "llm_pct": round(100 * llm / total) if total else 0,
        "avg_latency_ms": avg_lat,
        "groq_today": groq_today,
        "top_questions": q_counter.most_common(10),
        "content_gaps": gaps.most_common(10),
    }
