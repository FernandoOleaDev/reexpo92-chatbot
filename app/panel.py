"""Render del panel web (HTML server-side, estética Win95/Expo, sin dependencias)."""
from __future__ import annotations

import html
import re

from . import config, monitor, ratelimit, settings

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
nav.menu{display:flex;gap:6px;margin:-8px -18px 16px;padding:0 18px 10px;border-bottom:2px solid var(--line)}
nav.menu a{background:#fffdf7;border:1px solid var(--line);border-bottom:0;padding:7px 14px;font-weight:800;font-size:12px;text-transform:uppercase;text-decoration:none;color:var(--blue)}
nav.menu a.active{background:var(--orange);color:#fff}
.bar{height:22px;background:#e9e0cd;border:1px solid var(--line);position:relative;overflow:hidden}
.bar>i{display:block;height:100%;background:linear-gradient(90deg,#F7A81B,var(--orange));width:0;transition:width .4s}
.bar>span{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:800;color:#1a1714}
.logbox{background:#1a1714;color:#e9e0cd;font-family:ui-monospace,monospace;font-size:12px;padding:10px;height:180px;overflow:auto;white-space:pre-wrap;margin-top:8px}
.conv{border:1px solid var(--line);background:#fffdf7;margin:0 0 12px}
.conv .h{background:#efe4cd;padding:6px 10px;font-size:11px;color:#6a614e;font-family:ui-monospace,monospace}
.bub{max-width:80%;padding:7px 11px;border-radius:10px;margin:8px 10px;font-size:13.5px;line-height:1.4}
.bub.u{background:#2f44a0;color:#fff;margin-left:auto;border-bottom-right-radius:2px}
.bub.c{background:#fff;border:1px solid var(--line);border-bottom-left-radius:2px}
.bub .m{display:block;font-size:10px;color:#8a7f6a;margin-top:3px;text-transform:uppercase}
.bub.c p{margin:0 0 5px}.bub.c p:last-child{margin-bottom:0}
.bub.c ul,.bub.c ol{margin:4px 0;padding-left:18px}.bub.c ul{list-style:disc}.bub.c ol{list-style:decimal}
.bub.c li{margin:1px 0}.bub.c strong{font-weight:800}.bub.c em{font-style:italic}
.bub.c code{background:#efe4cd;border:1px solid #c9b48f;border-radius:3px;padding:0 3px;font-size:.9em}
.bub.c a{color:#2f44a0;font-weight:700}
.rl{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.rl .c{background:#fffdf7;border:1px solid var(--line);padding:10px}
.rl .c b{display:block;font-size:20px;font-family:ui-monospace,monospace}
.rl .c.ok b{color:var(--green)}.rl .c.warn b{color:#E8852A}.rl .c.crit b{color:var(--red)}
.rl .c span{font-size:11px;text-transform:uppercase;color:#5a5142}
"""


def _esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


# Renderiza el markdown+colores de Curro (igual que curroMarkdown.ts) para el panel.
_MD_COLORS = {
    "azul": "color:#1B2A6B;font-weight:700", "naranja": "color:#FF6B35;font-weight:700",
    "rojo": "color:#E8412B;font-weight:700", "turquesa": "color:#00A8A8;font-weight:700",
    "verde": "color:#2e7d4f;font-weight:700",
    "amarillo": "background:#FFC72C;color:#1a1714;padding:0 3px;border-radius:2px;font-weight:600",
}


def _md_inline(s: str) -> str:
    s = _esc(s)
    s = re.sub(r"\*\*([^*]+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"__([^_]+?)__", r"<strong>\1</strong>", s)
    s = re.sub(r"\*([^*\n]+?)\*", r"<em>\1</em>", s)
    s = re.sub(r"`([^`]+?)`", r"<code>\1</code>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
               r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    s = re.sub(r"\[(azul|naranja|amarillo|rojo|turquesa|verde)\]([\s\S]+?)\[/\1\]",
               lambda m: f'<span style="{_MD_COLORS[m.group(1)]}">{m.group(2)}</span>', s)
    return s


def _md(text: str) -> str:
    out, lst = [], None
    for raw in (text or "").split("\n"):
        line = raw.rstrip()
        ol = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
        ul = re.match(r"^\s*[-*•]\s+(.*)$", line)
        if ol:
            if lst != "ol":
                if lst:
                    out.append(f"</{lst}>")
                out.append("<ol>"); lst = "ol"
            out.append(f"<li>{_md_inline(ol.group(1))}</li>")
        elif ul:
            if lst != "ul":
                if lst:
                    out.append(f"</{lst}>")
                out.append("<ul>"); lst = "ul"
            out.append(f"<li>{_md_inline(ul.group(1))}</li>")
        elif not line.strip():
            if lst:
                out.append(f"</{lst}>"); lst = None
        else:
            if lst:
                out.append(f"</{lst}>"); lst = None
            out.append(f"<p>{_md_inline(line)}</p>")
    if lst:
        out.append(f"</{lst}>")
    return "".join(out)


def _shell(active: str, body: str, extra_head: str = "") -> str:
    nav = "".join(
        f'<a href="{href}"{" class=active" if key == active else ""}>{label}</a>'
        for key, href, label in (
            ("resumen", "/panel", "Resumen"),
            ("conversaciones", "/panel/conversaciones", "Conversaciones"),
        )
    )
    return f"""<!doctype html><html lang=es><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Panel RAG · re-Expo92</title>
<style>{_CSS}</style>{extra_head}</head><body><div class=wrap>
<h1>Panel RAG · Curro · re-Expo92</h1>
<nav class=menu>{nav}</nav>
{body}
<p class=muted>reexpo92-chatbot · servicio RAG. Este panel usa la service_role de Supabase; mantenlo tras login.</p>
</div></body></html>"""


def _rl_cell(label: str, remaining, limit, reset=None, lvl="") -> str:
    val = f"{_esc(remaining)}/{_esc(limit)}" if remaining is not None else _esc(limit if limit is not None else "—")
    sub = label + (f" · reinicio {_esc(reset)}" if reset else "")
    return f'<div class="c {lvl}"><b>{val}</b><span>{sub}</span></div>'


def _ratelimit_card(model: str) -> str:
    v = ratelimit.monitor_view(model)
    lvl = ratelimit.status_level()
    warn = ("<p class=err>⚠ Te acercas al límite DIARIO de peticiones (RPD).</p>" if lvl == "crit"
            else ("<p style='color:#E8852A;font-weight:800'>Atención: consumo diario alto.</p>" if lvl == "warn" else ""))
    live_note = ("actualizado: " + _esc(v.get("at")) if v.get("has_live")
                 else "restantes en vivo tras la 1ª respuesta con LLM; límites del catálogo Groq")
    return f"""<div class=win><div class=tb>Rate limit de Groq · modelo {_esc(model)}</div><div class=bd>
<div class=rl style="grid-template-columns:repeat(4,1fr)">
  {_rl_cell('RPM · peticiones/min', None, v['rpm'])}
  {_rl_cell('RPD · peticiones/día', v['rpd']['remaining'], v['rpd']['limit'], v['rpd']['reset'], lvl)}
  {_rl_cell('TPM · tokens/min', v['tpm']['remaining'], v['tpm']['limit'], v['tpm']['reset'])}
  {_rl_cell('TPD · tokens/día', None, v['tpd'])}
</div>
<p class=muted>Restantes en vivo cuando aparecen (RPD/TPM); RPM y TPD son el tope del plan gratis. {live_note}.</p>
{warn}
<p class=muted>💡 ¿Pocas al día? <b>llama-3.1-8b-instant</b> da <b>14.400 RPD</b> (14×) y 500K TPD. Cámbialo abajo.</p>
</div></div>"""


def render_conversations() -> str:
    sesiones = monitor.conversations(300)
    if not sesiones:
        body = '<div class=win><div class=tb>Conversaciones</div><div class=bd><p class=muted>Aún no hay preguntas registradas.</p></div></div>'
        return _shell("conversaciones", body)
    # Estadísticas (sobre las sesiones recientes cargadas)
    n_ses = len(sesiones)
    n_msgs = sum(len(s["items"]) for s in sesiones)
    n_pre = sum(1 for s in sesiones for it in s["items"] if it.get("mode") != "social")
    media = round(n_msgs / n_ses, 1) if n_ses else 0
    stats = f"""<div class=win><div class=tb>Resumen de conversaciones</div><div class=bd>
<div class=grid>
  <div class=stat><b>{n_ses}</b><span>Sesiones (anónimas)</span></div>
  <div class=stat><b>{n_msgs}</b><span>Mensajes</span></div>
  <div class=stat><b>{n_pre}</b><span>Preguntas reales</span></div>
  <div class=stat><b>{media}</b><span>Media msgs/sesión</span></div>
</div>
<p class=muted>Cada "sesión" es un visitante anónimo (una pestaña/navegador); no hay cuentas, así que es la mejor aproximación a "usuarios distintos".</p>
</div></div>"""

    blocks = []
    for s in sesiones:
        items = s["items"]
        rows = []
        for it in items:
            q = _esc(it.get("question"))
            a = _md(it.get("answer") or "(sin respuesta registrada)")
            meta = f"{_esc(it.get('mode'))}" + (f" · {_esc(it.get('model'))}" if it.get("model") else "") \
                + f" · {_esc((it.get('created_at') or '')[11:19])}"
            rows.append(f'<div class="bub u">{q}</div>'
                        f'<div class="bub c">{a}<span class=m>{meta}</span></div>')
        blocks.append(f'<div class=conv><div class=h>Sesión {_esc(s["session_id"])} · {len(items)} mensaje(s)</div>'
                      f'{"".join(rows)}</div>')
    body = (stats + f'<div class=win><div class=tb>Conversaciones · últimas {len(sesiones)} sesiones</div>'
            f'<div class=bd>{"".join(blocks)}</div></div>')
    return _shell("conversaciones", body)


def render(msg: str = "") -> str:
    cfg = settings.get_all(force=True)
    ov = monitor.overview(7)
    ix = monitor.index_state()
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
        for k in ("re_memory", "photo", "knowledge", "ayuda", "video")
    )

    top_rows = "".join(f"<tr><td>{_esc(q)}</td><td>{n}</td></tr>" for q, n in ov["top_questions"]) \
        or "<tr><td colspan=2 class=muted>Sin datos aún</td></tr>"
    gap_rows = "".join(f"<tr><td class=gap>{_esc(q)}</td><td>{n}</td></tr>" for q, n in ov["content_gaps"]) \
        or "<tr><td colspan=2 class=muted>Nada sin responder 🎉</td></tr>"

    banner = f'<div class="win"><div class="bd ok">{_esc(msg)}</div></div>' if msg else ""
    ix_rows = "".join(
        f"<tr><td>{_esc(r.get('source_type'))}</td><td>{_esc(r.get('chunk_count'))}</td>"
        f"<td>{_esc((r.get('last_indexed_at') or '')[:19])}</td></tr>"
        for r in ix["sources"]
    ) or "<tr><td colspan=3 class=muted>Sin indexar aún: ejecuta index_local.py</td></tr>"

    body = f"""{banner}
<div class=win><div class=tb>Monitorización · últimos {ov['days']} días</div><div class=bd>
<div class=grid>
  <div class=stat><b>{ov['total']}</b><span>Preguntas</span></div>
  <div class=stat><b>{ov['answered_pct']}%</b><span>Respondidas</span></div>
  <div class=stat><b>{ov['llm_pct']}%</b><span>Con LLM</span></div>
  <div class=stat><b>{ov['groq_today']}</b><span>Groq hoy</span></div>
</div>
<p class=muted>Latencia media: {ov['avg_latency_ms']} ms · <a href="/panel/conversaciones">ver todas las conversaciones →</a></p>
<div class=row style="align-items:flex-start">
  <div style="flex:1;min-width:280px"><h3>Top preguntas</h3><table><tr><th>Pregunta</th><th>Nº</th></tr>{top_rows}</table></div>
  <div style="flex:1;min-width:280px"><h3>Huecos de contenido (0 fuentes)</h3><table><tr><th>Pregunta</th><th>Nº</th></tr>{gap_rows}</table></div>
</div>
</div></div>

{_ratelimit_card(cfg.get('groq_model'))}

<div class=win><div class=tb>Índice · se genera en LOCAL</div><div class=bd>
<p>Fragmentos indexados: <b>{ix['total']}</b> · última indexación: {_esc((ix['last_indexed_at'] or 'nunca')[:19])}</p>
<table><tr><th>Fuente</th><th>Fragmentos</th><th>Última</th></tr>{ix_rows}</table>
<p class=muted style="margin-top:12px">⚠ El indexado NO se hace en el servidor (en Railway agota la memoria). Ejecútalo en tu ordenador — verás el progreso por consola:</p>
<div class=logbox style="height:auto">cd reexpo92-chatbot
source .venv/bin/activate
python3 index_local.py --all   # completo · sin --all = solo lo nuevo</div>
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
</div></div>"""
    return _shell("resumen", body)


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
