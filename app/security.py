"""Autenticación: cabecera para la API, cookie firmada para la web."""

from __future__ import annotations

import hmac

from fastapi import Cookie, Header, HTTPException, Query, Request, status
from itsdangerous import BadSignature, URLSafeSerializer

from app.config import settings

COOKIE_NAME = "recetas_session"
_serializer = URLSafeSerializer(settings.session_secret, salt="recetas-session")


def _matches(candidate: str | None, expected: str) -> bool:
    return bool(candidate) and hmac.compare_digest(candidate, expected)


def password_ok(candidate: str) -> bool:
    """Contraseña de acceso a la web (por defecto, la propia clave de API)."""
    return _matches((candidate or "").strip(), settings.app_password)


def issue_session_cookie() -> str:
    return _serializer.dumps({"ok": True})


def valid_session_cookie(value: str | None) -> bool:
    if not value:
        return False
    try:
        return bool(_serializer.loads(value).get("ok"))
    except BadSignature:
        return False


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
    key: str | None = Query(default=None),
) -> None:
    """Acepta X-API-Key, `Authorization: Bearer …` o `?key=` (para el Atajo)."""
    bearer = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
    if any(_matches(candidate, settings.api_key) for candidate in (x_api_key, bearer, key)):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Falta la clave de API o no es correcta.",
    )


def web_session_ok(request: Request) -> bool:
    if valid_session_cookie(request.cookies.get(COOKIE_NAME)):
        return True
    # Enlace directo con clave: útil para abrir la app desde el Atajo.
    return _matches(request.query_params.get("key"), settings.api_key)


async def require_web_session(
    request: Request,
    recetas_session: str | None = Cookie(default=None),
) -> None:
    if not web_session_ok(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión no iniciada")
