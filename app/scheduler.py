"""Cron interno para el reindexado incremental automático (APScheduler)."""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from . import config, indexer

_scheduler: BackgroundScheduler | None = None


def _job():
    try:
        indexer.run_index(full=False)
    except Exception:
        pass  # el error queda registrado en indexer.status["last_error"]


def start() -> str | None:
    """Arranca el cron si REINDEX_CRON es "HH:MM". Devuelve la hora programada o None."""
    global _scheduler
    cron = config.REINDEX_CRON
    if not cron or ":" not in cron:
        return None
    try:
        hh, mm = (int(x) for x in cron.split(":", 1))
    except ValueError:
        return None
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(_job, "cron", hour=hh, minute=mm, id="reindex", replace_existing=True)
    _scheduler.start()
    return f"{hh:02d}:{mm:02d} UTC"


def scheduled_at() -> str | None:
    if _scheduler and _scheduler.get_job("reindex"):
        return config.REINDEX_CRON + " UTC"
    return None
