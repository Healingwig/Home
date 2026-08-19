"""API + web app de recetas a partir de vídeos de Instagram."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app import db, security
from app.config import settings
from app.models import Recipe
from app.pipeline import download, process_recipe
from app.pipeline.media import ffmpeg_available
from app.pipeline.providers import check_provider
from app.shopping import shopping_payload

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("recetas")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

_workers = ThreadPoolExecutor(
    max_workers=int(os.getenv("WORKER_THREADS", "2")), thread_name_prefix="receta"
)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.ensure_dirs()
    db.init_db()
    if not os.getenv("API_KEY"):
        logger.warning("API_KEY no configurada. Clave temporal de esta ejecución: %s", settings.api_key)
    if not ffmpeg_available():
        logger.warning("ffmpeg/ffprobe no están en el PATH: sin fotogramas ni transcripción.")
    ready, detail = check_provider()
    logger.log(logging.INFO if ready else logging.WARNING, "Modelo (%s): %s", settings.llm_provider, detail)
    # Recetas que se quedaron a medias en un reinicio anterior.
    for stale in db.iter_stale_processing(older_than_seconds=1800):
        db.update_recipe(stale["id"], status="error", error="El proceso se interrumpió. Vuelve a intentarlo.")
    yield
    _workers.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="Recetas desde Instagram", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

class RecipeRequest(BaseModel):
    url: str = Field(description="Enlace del reel o post de Instagram")
    force: bool = Field(default=False, description="Reprocesar aunque ya exista")
    wait: int = Field(default=0, ge=0, le=240, description="Segundos a esperar a que esté lista")


def _enqueue(recipe_id: str, url: str) -> None:
    _workers.submit(process_recipe, recipe_id, url)


def _recipe_object(row: dict[str, Any]) -> Recipe | None:
    if not row.get("data"):
        return None
    try:
        return Recipe.model_validate(row["data"])
    except Exception:
        logger.exception("Receta %s guardada con formato inválido", row.get("id"))
        return None


def _public_row(row: dict[str, Any], request: Request | None = None) -> dict[str, Any]:
    payload = {
        "id": row["id"],
        "status": row["status"],
        "source_url": row["source_url"],
        "title": (row.get("data") or {}).get("title") or row.get("title"),
        "author": row.get("author"),
        "error": row.get("error"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "recipe": row.get("data"),
    }
    if request is not None:
        payload["web_url"] = str(request.url_for("recipe_page", recipe_id=row["id"]))
    return payload


async def _await_ready(recipe_id: str, seconds: int) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + seconds
    row = db.get_recipe(recipe_id)
    while row and row["status"] in {"pending", "processing"} and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(2)
        row = db.get_recipe(recipe_id)
    return row or {}


def _load_ready_recipe(recipe_id: str) -> tuple[dict[str, Any], Recipe]:
    row = db.get_recipe(recipe_id)
    if not row:
        raise HTTPException(status_code=404, detail="No existe esa receta.")
    if row["status"] != "ready":
        raise HTTPException(status_code=409, detail=f"La receta todavía no está lista (estado: {row['status']}).")
    recipe = _recipe_object(row)
    if recipe is None:
        raise HTTPException(status_code=500, detail="La receta guardada está corrupta.")
    return row, recipe


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #

@app.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, Any]:
    ready, detail = check_provider()
    return {
        "ok": True,
        "ffmpeg": ffmpeg_available(),
        "provider": settings.llm_provider,
        "provider_ready": ready,
        "provider_detail": detail,
    }


@app.post("/api/recipes", dependencies=[Depends(security.require_api_key)])
async def api_create_recipe(payload: RecipeRequest, request: Request) -> JSONResponse:
    url = download.normalize_url(payload.url)
    if not download.is_supported_url(url):
        raise HTTPException(status_code=400, detail="Eso no parece un enlace válido.")

    existing = None if payload.force else db.find_by_url(url)
    if existing:
        recipe_id = existing["id"]
    else:
        recipe_id = db.create_recipe(url)
        _enqueue(recipe_id, url)

    row = await _await_ready(recipe_id, payload.wait) if payload.wait else db.get_recipe(recipe_id)
    body = _public_row(row or {"id": recipe_id, "status": "pending", "source_url": url}, request)
    body["reused"] = bool(existing)
    return JSONResponse(body, status_code=200 if existing else 202)


@app.get("/api/recipes", dependencies=[Depends(security.require_api_key)])
def api_list_recipes(request: Request, q: str | None = None, limit: int = 50) -> dict[str, Any]:
    rows = db.list_recipes(limit=min(limit, 200), query=q)
    return {"count": len(rows), "recipes": [_public_row(row, request) for row in rows]}


@app.get("/api/recipes/{recipe_id}", dependencies=[Depends(security.require_api_key)])
def api_get_recipe(recipe_id: str, request: Request) -> dict[str, Any]:
    row = db.get_recipe(recipe_id)
    if not row:
        raise HTTPException(status_code=404, detail="No existe esa receta.")
    return _public_row(row, request)


@app.get("/api/recipes/{recipe_id}/shopping-list", dependencies=[Depends(security.require_api_key)])
def api_shopping_list(
    recipe_id: str,
    servings: int | None = Query(default=None, ge=1, le=50),
    include_pantry: bool = Query(default=False, description="Incluir sal, aceite y demás básicos"),
    include_optional: bool = True,
    prefix_title: bool = Query(default=False, description="Añadir el nombre del plato a cada línea"),
    format: str = Query(default="json", pattern="^(json|text)$"),
):
    _row, recipe = _load_ready_recipe(recipe_id)
    payload = shopping_payload(
        recipe,
        servings=servings,
        include_pantry=include_pantry,
        include_optional=include_optional,
        prefix_title=prefix_title,
    )
    if format == "text":
        return PlainTextResponse(payload["text"])
    return payload


@app.post("/api/recipes/{recipe_id}/retry", dependencies=[Depends(security.require_api_key)])
def api_retry(recipe_id: str, request: Request) -> dict[str, Any]:
    row = db.get_recipe(recipe_id)
    if not row:
        raise HTTPException(status_code=404, detail="No existe esa receta.")
    db.update_recipe(recipe_id, status="pending", error=None)
    _enqueue(recipe_id, row["source_url"])
    return _public_row(db.get_recipe(recipe_id) or row, request)


@app.delete("/api/recipes/{recipe_id}", dependencies=[Depends(security.require_api_key)])
def api_delete(recipe_id: str) -> dict[str, Any]:
    thumbnail = settings.media_dir / f"{recipe_id}.jpg"
    thumbnail.unlink(missing_ok=True)
    if not db.delete_recipe(recipe_id):
        raise HTTPException(status_code=404, detail="No existe esa receta.")
    return {"deleted": recipe_id}


# --------------------------------------------------------------------------- #
# Web (tablet)
# --------------------------------------------------------------------------- #

def _redirect_to_login(request: Request) -> RedirectResponse:
    return RedirectResponse(url=f"/login?next={request.url.path}", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/", error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"next": next, "error": error})


@app.post("/login")
def login_submit(request: Request, password: str = Form(...), next: str = Form(default="/")):
    if not security.password_ok(password):
        return templates.TemplateResponse(
            request, "login.html", {"next": next, "error": "Contraseña incorrecta."}, status_code=401
        )
    response = RedirectResponse(url=next or "/", status_code=303)
    response.set_cookie(
        security.COOKIE_NAME,
        security.issue_session_cookie(),
        max_age=60 * 60 * 24 * 365,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return response


@app.get("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(security.COOKIE_NAME)
    return response


@app.get("/", response_class=HTMLResponse)
def index(request: Request, q: str | None = None):
    if not security.web_session_ok(request):
        return _redirect_to_login(request)
    rows = db.list_recipes(query=q)
    cards = [
        {
            **row,
            "display_title": (row.get("data") or {}).get("title") or row.get("title") or "Sin título",
            "summary": (row.get("data") or {}).get("summary") or "",
            "total_minutes": _total_minutes(row.get("data")),
        }
        for row in rows
    ]
    return templates.TemplateResponse(request, "index.html", {"recipes": cards, "q": q or ""})


@app.post("/nueva")
def web_create(request: Request, url: str = Form(...)):
    if not security.web_session_ok(request):
        return _redirect_to_login(request)
    clean = download.normalize_url(url)
    if not download.is_supported_url(clean):
        return RedirectResponse(url="/?error=url", status_code=303)
    existing = db.find_by_url(clean)
    if existing:
        return RedirectResponse(url=f"/receta/{existing['id']}", status_code=303)
    recipe_id = db.create_recipe(clean)
    _enqueue(recipe_id, clean)
    return RedirectResponse(url=f"/receta/{recipe_id}", status_code=303)


@app.get("/receta/{recipe_id}", response_class=HTMLResponse, name="recipe_page")
def recipe_page(request: Request, recipe_id: str, servings: int | None = None):
    if not security.web_session_ok(request):
        return _redirect_to_login(request)
    row = db.get_recipe(recipe_id)
    if not row:
        raise HTTPException(status_code=404, detail="No existe esa receta.")

    recipe = _recipe_object(row)
    if recipe and servings:
        recipe = recipe.scaled(servings)

    return templates.TemplateResponse(
        request,
        "recipe.html",
        {
            "row": row,
            "recipe": recipe,
            "servings": servings or (recipe.servings if recipe else None),
            "shopping": shopping_payload(recipe, servings=servings) if recipe else None,
            "steps_json": [step.model_dump(mode="json") for step in recipe.steps] if recipe else [],
        },
    )


@app.post("/receta/{recipe_id}/reintentar")
def web_retry(request: Request, recipe_id: str):
    if not security.web_session_ok(request):
        return _redirect_to_login(request)
    row = db.get_recipe(recipe_id)
    if not row:
        raise HTTPException(status_code=404, detail="No existe esa receta.")
    db.update_recipe(recipe_id, status="pending", error=None)
    _enqueue(recipe_id, row["source_url"])
    return RedirectResponse(url=f"/receta/{recipe_id}", status_code=303)


@app.post("/receta/{recipe_id}/borrar")
def web_delete(request: Request, recipe_id: str):
    if not security.web_session_ok(request):
        return _redirect_to_login(request)
    (settings.media_dir / f"{recipe_id}.jpg").unlink(missing_ok=True)
    db.delete_recipe(recipe_id)
    return RedirectResponse(url="/", status_code=303)


@app.get("/media/{filename}")
def media_file(request: Request, filename: str):
    if not security.web_session_ok(request):
        raise HTTPException(status_code=401, detail="Sesión no iniciada")
    # `filename` viene de la BD, pero lo anclamos igualmente al directorio de medios.
    path = (settings.media_dir / Path(filename).name).resolve()
    if not str(path).startswith(str(settings.media_dir.resolve())) or not path.is_file():
        raise HTTPException(status_code=404, detail="No encontrado")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


def _total_minutes(data: dict[str, Any] | None) -> int | None:
    if not data:
        return None
    parts = [data.get("prep_minutes"), data.get("cook_minutes")]
    total = sum(p for p in parts if isinstance(p, int))
    return total or None
