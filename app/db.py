"""Acceso a Supabase con la clave service_role (bypassa RLS).

Usamos la REST API de PostgREST y las RPC directamente con `requests` para no atar
el servicio a la versión del SDK. Todo pasa por el service_role, que vive solo en
las env vars de Railway.
"""
from __future__ import annotations

from typing import Any

import requests

from . import config

_TIMEOUT = 30


def _headers(extra: dict | None = None) -> dict:
    h = {
        "apikey": config.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _rest(path: str) -> str:
    return f"{config.SUPABASE_URL}/rest/v1/{path}"


def select(table: str, params: dict[str, Any]) -> list[dict]:
    """SELECT vía PostgREST. `params` en sintaxis PostgREST (p.ej. {'select': '*', 'updated_at': 'gt.<iso>'})."""
    r = requests.get(_rest(table), headers=_headers(), params=params, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def upsert(table: str, rows: list[dict], on_conflict: str | None = None) -> None:
    if not rows:
        return
    params = {}
    prefer = "resolution=merge-duplicates,return=minimal"
    if on_conflict:
        params["on_conflict"] = on_conflict
    r = requests.post(
        _rest(table), headers=_headers({"Prefer": prefer}), params=params,
        json=rows, timeout=_TIMEOUT,
    )
    r.raise_for_status()


def insert(table: str, row: dict) -> None:
    r = requests.post(
        _rest(table), headers=_headers({"Prefer": "return=minimal"}), json=row, timeout=_TIMEOUT,
    )
    r.raise_for_status()


def delete(table: str, params: dict[str, Any]) -> None:
    r = requests.delete(_rest(table), headers=_headers({"Prefer": "return=minimal"}),
                        params=params, timeout=_TIMEOUT)
    r.raise_for_status()


def rpc(fn: str, payload: dict) -> Any:
    r = requests.post(f"{config.SUPABASE_URL}/rest/v1/rpc/{fn}", headers=_headers(),
                      json=payload, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def count(table: str, params: dict[str, Any] | None = None) -> int:
    p = dict(params or {})
    p["select"] = "id"
    r = requests.get(_rest(table), headers=_headers({"Prefer": "count=exact", "Range": "0-0"}),
                     params=p, timeout=_TIMEOUT)
    r.raise_for_status()
    cr = r.headers.get("content-range", "")  # "0-0/1234"
    if "/" in cr:
        try:
            return int(cr.split("/")[-1])
        except ValueError:
            return 0
    return 0
