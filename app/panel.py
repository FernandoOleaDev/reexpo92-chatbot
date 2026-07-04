"""Render del panel web (HTML server-side, estética Win95/Expo, sin dependencias)."""
from __future__ import annotations

import html

from . import config, indexer, monitor, scheduler, settings

# modelos de Groq recomendados por defecto (el dropdown se completa en vivo si hay clave)
FALLBACK_MODELS = [
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.6-27b",
    "qwen/qwen3-32b",
    "llama-3.3-70b-versatile",
    "gemma2-9b-it",
]

_CSS = """
:root{--blue:#1B2A6B;--orange:#FF6B35;--paper:#f4ead6;--ink:#1a1714;--line:#7a6a4d;--green:#2e7d4f;--red:#c0392b}
*{box-sizing:border-box}body{margin:0;background:#008080;font-family:"Segoe UI",system-ui,sans-serif;color:var(--ink)}
.wrap{max-width:960px;margin:0 auto;padding:18px}
h1{background:var(--blue);color:#fff;margin:0 -18px 18px;padding:14px 18px;font-size:18px;text-transform:uppercase}
.win{background:var(--paper);border:2px solid var(--line);box-shadow:4px 4px 0 rgba(0,0,0,.25);margin:0 0 16px}
.tb{background:linear-gradient(#2f44a0,var(--blue));color:#fff;padding:7px 12px;font-weight:800;text-transform:uppercase;font-size:13px}
.bd{padding:14px 16px}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.stat{background:#fffdf7;border:1px solid var(--line);padding:10px}
.stat b{display:block;font-size:22px;color:var(--orange);font-family:ui-monospace,monospace}
.stat span{font-size:11px;text-transform:uppercase;color:#5a5142}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{border:1px solid #c9b48f;padding:6px 8px;text-align:left}
th{background:var(--blue);color:#fff;font-size:11px;text-transform:uppercase}
button,input,select{font:inherit}
.btn{background:var(--orange);color:#fff;border:0;padding:9px 16px;font-weight:800;cursor:pointer;text-transform:uppercase;font-size:12px}
.btn.blue{background:var(--blue)} .btn.ghost{background:#8a7f6a}
label{display:block;font-size:12px;font-weight:700;margin:10px 0 4px;text-transform:uppercase}
select,input[type=number]{padding:7px;border:1px solid var(--line);background:#fff;width:100%;max-width:340px}
.row{display:flex;gap:20px;flex-wrap:wrap;align-items:flex-end}
.ok{color:var(--green);font-weight:800}.err{color:var(--red);font-weight:800}
.gap{color:var(--red)}
form{margin:0}.muted{color:#6a614e;font-size:12px}
"""


def _esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def render(msg: str = "") -> str:
    st = indexer.status
    cfg = settings.get_all(force=True)
    ov = monitor.overview(7)
    models = _groq_models()

    cur_model = cfg.get("groq_model")
    opts = "".join(
        f'<option value="{_esc(m)}"{" selected" if m == cur_model else ""}>{_esc(m)}</option>'
        for m in models
    )
    llm_checked = "checked" if cfg.get("llm_enabled") else ""

    src = cfg.get("sources") or {}
    src_boxes = "".join(
        f'<label style="display:inline-block;margin-right:16px;text-transform:none">'
        f'<input type="checkbox" name="src_{k}" {"checked" if src.get(k, True) else ""}> {k}</label>'
        for k in ("re_memory", "photo", "knowledge", "ayuda")
    )

    top_rows = "".join(f"<tr><td>{_esc(q)}</td><td>{n}</td></tr>" for q, n in ov["top_questions"]) \
        or "<tr><td colspan=2 class=muted>Sin datos aún</td></tr>"
    gap_rows = "".join(f"<tr><td class=gap>{_esc(q)}</td><td>{n}</td></tr>" for q, n in ov["content_gaps"]) \
        or "<tr><td colspan=2 class=muted>Nada sin responder 🎉</td></tr>"

    run_state = ('<span class="err">indexando…</span>' if st["running"]
                 else (f'<span class="ok">OK</span> · {_esc(st["last_run"])}' if st["last_run"]
                       else "nunca"))
    err = f'<p class="err">⚠ Último error: {_esc(st["last_error"])}</p>' if st.get("last_error") else ""
    banner = f'<div class="win"><div class="bd ok">{_esc(msg)}</div></div>' if msg else ""

    return f"""<!doctype html><html lang=es><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Panel RAG · re-Expo92</title>
<style>{_CSS}</style></head><body><div class=wrap>
<h1>Panel RAG · Curro · re-Expo92</h1>
{banner}

<div class=win><div class=tb>Monitorización · últimos {ov['days']} días</div><div class=bd>
<div class=grid>
  <div class=stat><b>{ov['total']}</b><span>Preguntas</span></div>
  <div class=stat><b>{ov['answered_pct']}%</b><span>Respondidas</span></div>
  <div class=stat><b>{ov['llm_pct']}%</b><span>Con LLM</span></div>
  <div class=stat><b>{ov['groq_today']}</b><span>Groq hoy</span></div>
</div>
<p class=muted>Latencia media: {ov['avg_latency_ms']} ms</p>
<div class=row style="align-items:flex-start">
  <div style="flex:1;min-width:280px"><h3>Top preguntas</h3><table><tr><th>Pregunta</th><th>Nº</th></tr>{top_rows}</table></div>
  <div style="flex:1;min-width:280px"><h3>Huecos de contenido (0 fuentes)</h3><table><tr><th>Pregunta</th><th>Nº</th></tr>{gap_rows}</table></div>
</div>
</div></div>

<div class=win><div class=tb>Índice</div><div class=bd>
<p>Última indexación: {run_state} · modo: {_esc(st.get('last_mode'))} · cron: {_esc(scheduler.scheduled_at() or 'desactivado')}</p>
{err}
<form method=post action=/panel/reindex style="display:inline"><button class=btn name=mode value=new {'disabled' if st['running'] else ''}>▶ Reindexar nuevo</button></form>
<form method=post action=/panel/reindex style="display:inline"><button class="btn blue" name=mode value=all {'disabled' if st['running'] else ''}>↻ Reindexar todo</button></form>
</div></div>

<div class=win><div class=tb>Configuración del modelo (Groq)</div><div class=bd>
<form method=post action=/panel/settings>
<div class=row>
  <div><label>Modelo Groq</label><select name=groq_model>{opts}</select></div>
  <div><label>Temperatura</label><input type=number name=temperature min=0 max=1 step=0.1 value="{_esc(cfg.get('temperature'))}"></div>
  <div><label style="text-transform:none"><input type=checkbox name=llm_enabled {llm_checked}> Respuestas con LLM (si se desactiva: solo búsqueda)</label></div>
</div>
<label>Fuentes a indexar</label><div>{src_boxes}</div>
<p class=muted>{'✓ Clave Groq detectada.' if config.GROQ_API_KEY else '⚠ Sin GROQ_API_KEY: el chat funciona en modo solo búsqueda.'} La lista de modelos se actualiza en vivo desde Groq si hay clave.</p>
<button class=btn type=submit>Guardar</button>
</form>
</div></div>

<p class=muted>reexpo92-chatbot · servicio RAG. Este panel usa la service_role de Supabase; mantenlo tras login.</p>
</div></body></html>"""


def _groq_models() -> list[str]:
    """Lista de modelos: en vivo desde Groq si hay clave, si no, la de reserva."""
    if not config.GROQ_API_KEY:
        return FALLBACK_MODELS
    try:
        import requests
        r = requests.get(f"{config.GROQ_BASE_URL}/models",
                         headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"}, timeout=10)
        r.raise_for_status()
        ids = sorted(m["id"] for m in r.json().get("data", []) if "whisper" not in m["id"] and "tts" not in m["id"])
        return ids or FALLBACK_MODELS
    except Exception:
        return FALLBACK_MODELS
