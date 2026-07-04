"""Login básico del panel (HTTP Basic). Credenciales desde env vars de Railway.

Si RAG_ADMIN_PASS está vacío, el panel queda BLOQUEADO (no se sirve) por seguridad.
"""
from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from . import config

_basic = HTTPBasic(realm="reexpo92-chatbot")


def require_admin(creds: HTTPBasicCredentials = Depends(_basic)) -> str:
    if not config.RAG_ADMIN_PASS:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Panel bloqueado: define RAG_ADMIN_PASS en Railway.")
    ok_user = secrets.compare_digest(creds.username, config.RAG_ADMIN_USER)
    ok_pass = secrets.compare_digest(creds.password, config.RAG_ADMIN_PASS)
    if not (ok_user and ok_pass):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas",
                            headers={"WWW-Authenticate": "Basic"})
    return creds.username
