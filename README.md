# reexpo92-chatbot

Servicio RAG del chatbot **Curro** de [re-Expo92](https://github.com/FernandoOleaDev/re-Expo92).
Un solo servicio (FastAPI, Docker, pensado para Railway) que hace de **cerebro** del chat:

- **`POST /chat`** — endpoint público del chatbot: recupera contexto de la base vectorial (Supabase pgvector), redacta la respuesta con Groq y puede devolver **acciones** (llevar al usuario a una página) y **enlaces**.
- **`POST /embed`** — embeddings del texto (uso interno / futuro WebGL-Unity), protegido por `EMBED_SECRET`.
- **`GET /panel`** — panel de administración con login: **monitorización** (qué se pregunta, cupos, huecos de contenido), **índice** (reindexar manual/programado) y **configuración del modelo Groq**.
- **`GET /health`** — estado para Railway.

El modelo de embeddings es `intfloat/multilingual-e5-base` (768 dim), el mismo que el RAG de vídeos del proyecto. Sin coste por token.

## Arquitectura

```
Web (re-Expo92)  ──POST /chat──►  reexpo92-chatbot (Railway)  ──►  Supabase pgvector (kb_chunks)
                                        │  embeddings e5-base          │  match_kb()
                                        │  Groq (redacción)            │  rag_queries (monitor)
                                        └─ panel + indexador ──lee──►  re_memories, community_photos, /ayuda, knowledge/
```

## Desarrollo local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # y rellena SUPABASE_SERVICE_ROLE_KEY, GROQ_API_KEY, RAG_ADMIN_PASS
uvicorn app.main:app --reload --port 8000
# panel: http://localhost:8000/panel
```

## Despliegue en Railway

1. Crea un proyecto en Railway desde este repo de GitHub (build por Dockerfile).
2. Define las **variables de entorno** (ver `.env.example`). Imprescindibles:
   `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `RAG_ADMIN_PASS`, `GROQ_API_KEY`.
3. La primera vez, entra en `/panel` y pulsa **Reindexar todo** para poblar la base vectorial.

> ⚠️ `SUPABASE_SERVICE_ROLE_KEY` es todopoderoso: vive **solo** en las env vars de Railway, nunca en el repo ni en el cliente.

## Variables de entorno

| Variable | Obligatoria | Descripción |
|---|---|---|
| `SUPABASE_URL` | sí | URL del proyecto Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | sí | Clave service_role (secreta) |
| `RAG_ADMIN_USER` / `RAG_ADMIN_PASS` | sí (pass) | Login del panel |
| `GROQ_API_KEY` | recomendada | Sin ella, el chat va en modo "solo búsqueda" |
| `GROQ_MODEL` | no | Modelo por defecto (editable en el panel) |
| `REINDEX_CRON` | no | Hora "HH:MM" UTC del reindexado automático |
| `AYUDA_URL` | no | URL de /ayuda a indexar |
| `CORS_ORIGINS` | no | Dominios que pueden llamar a /chat |
| `EMBED_SECRET` | no | Habilita `/embed` para uso interno |

## Base de datos

Las tablas (`kb_chunks`, `rag_index_state`, `rag_queries`, `rag_settings`) y la función
`match_kb` se crean con la migración `20260704_feat_rag_curro` en el proyecto Supabase de re-Expo92.
