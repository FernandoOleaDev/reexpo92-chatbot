"""Configuración leída SÓLO de variables de entorno (nada de secretos en el repo).

En Railway estas variables se definen en el panel del servicio. En local, copia
`.env.example` a `.env` (el `.env` está gitignoreado).
"""
from __future__ import annotations

import os


def _clean(v: str | None) -> str:
    return (v or "").strip()


# ── Supabase (el service_role es TODOPODEROSO: solo en env de Railway) ──────────
SUPABASE_URL = _clean(os.getenv("SUPABASE_URL"))
SUPABASE_SERVICE_ROLE_KEY = _clean(os.getenv("SUPABASE_SERVICE_ROLE_KEY"))

# ── Groq (capa de generación; si falta, el chat cae a modo "solo búsqueda") ─────
GROQ_API_KEY = _clean(os.getenv("GROQ_API_KEY"))
GROQ_MODEL = _clean(os.getenv("GROQ_MODEL")) or "openai/gpt-oss-20b"
GROQ_BASE_URL = _clean(os.getenv("GROQ_BASE_URL")) or "https://api.groq.com/openai/v1"

# ── Secreto para /embed (uso interno / futuro WebGL-Unity) ──────────────────────
EMBED_SECRET = _clean(os.getenv("EMBED_SECRET"))

# ── Panel de administración (login básico) ──────────────────────────────────────
RAG_ADMIN_USER = _clean(os.getenv("RAG_ADMIN_USER")) or "admin"
RAG_ADMIN_PASS = _clean(os.getenv("RAG_ADMIN_PASS"))  # sin default: si está vacío, el panel se bloquea

# ── Embeddings ──────────────────────────────────────────────────────────────────
EMBED_MODEL = _clean(os.getenv("EMBED_MODEL")) or "intfloat/multilingual-e5-base"
EMBED_DIM = int(_clean(os.getenv("EMBED_DIM")) or "768")

# ── Indexado ────────────────────────────────────────────────────────────────────
# Cron interno (APScheduler). Formato "HH:MM" UTC, o vacío para desactivar.
# DESACTIVADO por defecto: el indexado se hace EN LOCAL (index_local.py), porque
# hacerlo en Railway agota la RAM (OOM). Servir preguntas sí cabe.
REINDEX_CRON = _clean(os.getenv("REINDEX_CRON"))
CHUNK_CHARS = int(_clean(os.getenv("CHUNK_CHARS")) or "900")
CHUNK_OVERLAP = int(_clean(os.getenv("CHUNK_OVERLAP")) or "150")

# Página pública de ayuda a rastrear (opcional). Si se define, el indexador baja
# su HTML y extrae el texto como fuente 'ayuda'.
AYUDA_URL = _clean(os.getenv("AYUDA_URL"))  # p.ej. https://reexpo92.com/ayuda

# ── CORS: dominios que pueden llamar a /chat desde el navegador ─────────────────
def cors_origins() -> list[str]:
    raw = _clean(os.getenv("CORS_ORIGINS"))
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    # Defaults razonables para desarrollo + producción.
    return [
        "http://localhost:5173",
        "http://localhost:4173",
        "https://reexpo92.com",
        "https://www.reexpo92.com",
    ]


# ── Anti-abuso del endpoint público /chat ───────────────────────────────────────
CHAT_RATE_PER_MIN = int(_clean(os.getenv("CHAT_RATE_PER_MIN")) or "20")   # por sesión/IP
CHAT_MAX_CHARS = int(_clean(os.getenv("CHAT_MAX_CHARS")) or "500")


def missing_required() -> list[str]:
    """Devuelve qué variables imprescindibles faltan (para /health y el panel)."""
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_SERVICE_ROLE_KEY:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    return missing
