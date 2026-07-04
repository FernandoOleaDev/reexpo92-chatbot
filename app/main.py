"""reexpo92-chatbot — servicio RAG "Curro" para re-Expo92.

Un solo servicio (Railway) que:
  · POST /chat    — endpoint PÚBLICO del chatbot (recuperar + Groq + acciones)
  · POST /embed   — embeddings (uso interno / futuro WebGL-Unity), protegido
  · GET  /panel   — panel de admin (login): monitor + índice + config del modelo
  · POST /panel/* — acciones del panel
  · GET  /health  — estado para Railway
"""
from __future__ import annotations

import time

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from . import auth, chat, config, embeddings, indexer, panel, scheduler, settings

app = FastAPI(title="reexpo92-chatbot", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins(),
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

_boot: dict = {}
_rate: dict[str, list[float]] = {}


@app.on_event("startup")
def _startup():
    try:
        embeddings.warmup()
    except Exception as e:  # noqa: BLE001
        _boot["embed_error"] = str(e)
    _boot["cron"] = scheduler.start()


# ── público: el chat ────────────────────────────────────────────────────────────
class ChatIn(BaseModel):
    question: str
    session_id: str | None = None


def _rate_ok(key: str) -> bool:
    now = time.time()
    hits = [t for t in _rate.get(key, []) if now - t < 60]
    if len(hits) >= config.CHAT_RATE_PER_MIN:
        _rate[key] = hits
        return False
    hits.append(now)
    _rate[key] = hits
    return True


@app.post("/chat")
def post_chat(body: ChatIn, request: Request):
    q = (body.question or "").strip()
    if not q:
        raise HTTPException(400, "Pregunta vacía")
    if len(q) > config.CHAT_MAX_CHARS:
        q = q[: config.CHAT_MAX_CHARS]
    key = body.session_id or (request.client.host if request.client else "anon")
    if not _rate_ok(key):
        raise HTTPException(429, "Demasiadas preguntas seguidas, espera un momento 🙂")
    return chat.answer(q, body.session_id)


# ── embeddings (interno / futuro) ────────────────────────────────────────────────
class EmbedIn(BaseModel):
    text: str


@app.post("/embed")
def post_embed(body: EmbedIn, x_embed_secret: str | None = Header(default=None)):
    if not config.EMBED_SECRET or x_embed_secret != config.EMBED_SECRET:
        raise HTTPException(401, "No autorizado")
    return {"vector": embeddings.embed_query(body.text)}


# ── panel de administración ──────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/panel")


@app.get("/panel", response_class=HTMLResponse)
def get_panel(_: str = Depends(auth.require_admin)):
    return HTMLResponse(panel.render())


async def _read_form(request: Request) -> dict:
    """Lee un form urlencoded sin depender de python-multipart."""
    from urllib.parse import parse_qsl
    raw = await request.body()
    return dict(parse_qsl(raw.decode("utf-8"))) if raw else {}


@app.post("/panel/reindex", response_class=HTMLResponse)
async def post_reindex(request: Request, _: str = Depends(auth.require_admin)):
    body = await _read_form(request)
    full = body.get("mode") == "all"
    started = indexer.start_async(full=full)
    msg = (f"Indexado {'completo' if full else 'incremental'} en marcha…"
           if started else "Ya había un indexado en curso.")
    return HTMLResponse(panel.render(msg))


@app.get("/panel/progress")
def get_progress(_: str = Depends(auth.require_admin)):
    """Estado del indexado en curso (para la barra de progreso en vivo)."""
    return JSONResponse({
        "running": indexer.status["running"],
        "progress": indexer.status["progress"],
        "last_error": indexer.status.get("last_error"),
    })


@app.get("/panel/conversaciones", response_class=HTMLResponse)
def get_conversaciones(_: str = Depends(auth.require_admin)):
    return HTMLResponse(panel.render_conversations())


@app.post("/panel/settings", response_class=HTMLResponse)
async def post_settings(request: Request, _: str = Depends(auth.require_admin)):
    body = await _read_form(request)
    settings.update({
        "groq_model": body.get("groq_model") or None,
        "llm_enabled": "llm_enabled" in body,
        "temperature": float(body.get("temperature") or 0.3),
        "sources": {k: (f"src_{k}" in body) for k in ("re_memory", "photo", "knowledge", "ayuda", "video")},
    })
    return HTMLResponse(panel.render("Configuración guardada."))


# ── salud ─────────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return JSONResponse({
        "ok": not config.missing_required(),
        "missing_env": config.missing_required(),
        "groq_key": bool(config.GROQ_API_KEY),
        "model": settings.get("groq_model"),
        "cron": _boot.get("cron"),
        "index": {k: indexer.status.get(k) for k in ("running", "last_run", "last_mode")},
    })
