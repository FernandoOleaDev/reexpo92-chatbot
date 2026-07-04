"""El cerebro de Curro: recuperar contexto (pgvector) + redactar con Groq + acciones.

Flujo de una pregunta:
  1. Frases sociales (hola/gracias/…) → respuesta instantánea, sin LLM ni búsqueda.
  2. Embedding de la pregunta (e5-base) → RPC match_kb → top fragmentos.
  3. Si el LLM está activo y hay clave Groq → redacta en JSON {answer, navigate}.
     Si no (o si Groq falla) → modo "solo búsqueda": resumen + enlaces.
  4. Registra la consulta en rag_queries (monitorización) y devuelve el resultado.
"""
from __future__ import annotations

import json
import re
import time

import requests

from . import config, db, embeddings, settings

# ── Rutas a las que Curro puede llevar al usuario (lista blanca) ─────────────────
KNOWN_PAGES = {
    "/mapa": "Mapa interactivo del recinto de la Expo 92",
    "/re-memories": "Catálogo de re-memorias (pabellones, esculturas, etc.)",
    "/fotos": "Archivo fotográfico de la comunidad",
    "/zonas": "Zonas del recinto",
    "/foro": "Foro de la comunidad",
    "/investigacion": "Vídeos de archivo",
    "/recopilacion": "Recopilación multimedia (imágenes, vídeos, descargas)",
    "/bibliografia": "Bibliografía y fuentes",
    "/colabora": "Cómo colaborar en el proyecto",
    "/ayuda": "Ayuda de la web",
}
# prefijos permitidos para navegación (incluye deep-links a fichas)
_NAV_ALLOW = re.compile(r"^/(mapa|re-memories|fotos|zonas|foro|investigacion|recopilacion|bibliografia|colabora|ayuda)(/|$|\?)")

SOCIAL = [
    (re.compile(r"\b(hola|buenas|hey|eoo?|saludos)\b", re.I),
     "¡Hola! Soy Curro, la mascota de la Expo 92 🌈 Pregúntame lo que quieras: pabellones, fotos, el mapa, cómo colaborar…"),
    (re.compile(r"\b(gracias|thank)\b", re.I), "¡De nada, a mandar! 😊 ¿Algo más sobre la Expo?"),
    (re.compile(r"\b(adios|adiós|hasta luego|chao|bye)\b", re.I), "¡Hasta pronto! Aquí estaré si necesitas algo de la Expo 92."),
    (re.compile(r"(quién eres|quien eres|qué eres|que eres|cómo te llamas)", re.I),
     "Soy Curro, la mascota de la Expo 92 de Sevilla. Ahora ayudo en re-Expo92: te busco pabellones, fotos, zonas y te explico cómo usar la web."),
    (re.compile(r"(te quiero|eres tonto|idiota)", re.I), "Jeje, yo solo soy un pájaro de colores 🐦 ¿Te ayudo con algo de la Expo?"),
]

SYSTEM_PROMPT = (
    "Eres Curro, la simpática mascota de la Expo 92 de Sevilla, y ayudante de la web re-Expo92 "
    "(recreación colaborativa de la Expo). Respondes en español, con cercanía y brevedad. "
    "REGLAS: Responde ÚNICAMENTE con la información del CONTEXTO. Si el contexto no contiene la "
    "respuesta, dilo con honestidad y sugiere buscar o preguntar de otra forma; NO te inventes datos. "
    "Si el usuario pide explícitamente ir a una página o ver algo (mapa, fotos, un pabellón…), "
    "indícalo en el campo navigate.\n"
    "Devuelve SIEMPRE un JSON válido con esta forma exacta:\n"
    '{\"answer\": \"tu respuesta\", \"navigate\": \"/ruta\" o null}\n'
    "El campo navigate SOLO puede ser una de estas rutas (o una ficha /re-memories/<id> del contexto), "
    "o null si no procede: " + ", ".join(KNOWN_PAGES) + "."
)


def _retrieve(question: str, k: int = 5) -> list[dict]:
    qv = embeddings.embed_query(question)
    try:
        rows = db.rpc("match_kb", {"query_embedding": qv, "match_count": k})
    except Exception:
        return []
    return rows or []


def _sources_from(chunks: list[dict]) -> list[dict]:
    seen, out = set(), []
    for c in chunks:
        key = (c.get("source_type"), c.get("url"), c.get("title"))
        if key in seen or not c.get("url"):
            continue
        seen.add(key)
        out.append({"title": c.get("title") or "Ver", "url": c["url"], "type": c.get("source_type")})
        if len(out) >= 4:
            break
    return out


def _valid_nav(path, chunks) -> str | None:
    if not path or not isinstance(path, str):
        return None
    path = path.strip()
    if not _NAV_ALLOW.match(path):
        return None
    return path


def _groq_answer(question: str, chunks: list[dict]) -> tuple[str, str | None, dict]:
    context = "\n\n---\n\n".join(
        f"[{c.get('title','')}] ({c.get('url','')})\n{c.get('content','')}" for c in chunks
    ) or "(sin contexto relevante)"
    model = settings.get("groq_model", config.GROQ_MODEL)
    temperature = float(settings.get("temperature", 0.3))
    body = {
        "model": model,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"CONTEXTO:\n{context}\n\nPREGUNTA: {question}"},
        ],
    }
    r = requests.post(
        f"{config.GROQ_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
        json=body, timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    usage = data.get("usage", {})
    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    answer = (parsed.get("answer") or "").strip()
    navigate = _valid_nav(parsed.get("navigate"), chunks)
    meta = {
        "model": model,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
    }
    return answer, navigate, meta


def _retrieval_answer(chunks: list[dict]) -> str:
    if not chunks:
        return ("No he encontrado nada sobre eso en la web todavía. Prueba a preguntar de otra forma, "
                "o explora el catálogo y el mapa desde el menú.")
    top = chunks[0]
    return (f"Esto es lo más relevante que tengo: «{top.get('title','')}». "
            "Te dejo los enlaces para verlo en la web 👇")


def _log(row: dict) -> None:
    try:
        db.insert("rag_queries", row)
    except Exception:
        pass


def answer(question: str, session_id: str | None) -> dict:
    t0 = time.time()
    q = (question or "").strip()

    # 1) frases sociales
    for pat, resp in SOCIAL:
        if pat.search(q):
            _log({"session_id": session_id, "question": q, "mode": "social",
                  "answered": True, "matched_count": 0, "used_llm": False,
                  "latency_ms": int((time.time() - t0) * 1000)})
            return {"answer": resp, "sources": [], "navigate": None, "mode": "social"}

    # 2) recuperar contexto
    chunks = _retrieve(q, k=5)
    srcs = _sources_from(chunks)
    top_sim = chunks[0].get("similarity") if chunks else None
    top_src = chunks[0].get("source_type") if chunks else None

    llm_on = bool(settings.get("llm_enabled", True)) and bool(config.GROQ_API_KEY)
    mode, used_llm, navigate, meta = "retrieval", False, None, {}
    if llm_on:
        try:
            ans, navigate, meta = _groq_answer(q, chunks)
            mode, used_llm = "llm", True
            if not ans:
                ans = _retrieval_answer(chunks)
        except Exception as e:  # noqa: BLE001 — caída elegante a solo búsqueda
            ans = _retrieval_answer(chunks)
            meta = {"error": str(e)[:200]}
    else:
        ans = _retrieval_answer(chunks)

    answered = bool(chunks) or used_llm
    _log({
        "session_id": session_id, "question": q, "mode": mode, "answered": answered,
        "matched_count": len(chunks), "top_similarity": top_sim, "top_source": top_src,
        "used_llm": used_llm, "model": meta.get("model"),
        "prompt_tokens": meta.get("prompt_tokens"), "completion_tokens": meta.get("completion_tokens"),
        "latency_ms": int((time.time() - t0) * 1000),
    })
    return {"answer": ans, "sources": srcs, "navigate": navigate, "mode": mode}
