"""API + web app de recetas a partir de vídeos de Instagram."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app import security, storage
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
    storage.init()
    if not os.getenv("API_KEY"):
        logger.warning("API_KEY no configurada. Clave temporal de esta ejecución: %s", settings.api_key)
    if not ffmpeg_available():
        logger.warning("ffmpeg/ffprobe no están en el PATH: sin fotogramas ni transcripción.")
    ready, detail = check_provider()
    logger.log(logging.INFO if ready else logging.WARNING, "Modelo (%s): %s", settings.llm_provider, detail)
    logger.info("Almacenamiento: %s · serverless: %s", settings.storage_backend, settings.serverless)
    # Recetas que se quedaron a medias en un reinicio anterior.
    for stale in storage.iter_stale_processing(older_than_seconds=1800):
        storage.update_recipe(stale["id"], status="error", error="El proceso se interrumpió. Vuelve a intentarlo.")
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


def _enqueue(recipe_id: str, url: str, inline: bool = False) -> None:
    """Lanza el procesado.

    `inline` es para las rutas web en plataformas serverless: allí el
    contenedor se congela en cuanto se responde, así que un hilo de fondo no
    llegaría a terminar. Las rutas de la API no lo necesitan porque mantienen
    la petición abierta con `wait`.
    """
    if inline:
        process_recipe(recipe_id, url)
    else:
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


POLL_SECONDS = 3


def _streamed_wait(recipe_id: str, url: str, request: Request, seconds: int) -> StreamingResponse:
    """Una sola petición que no responde hasta que la receta está lista.

    Mientras espera va soltando espacios en blanco: iOS corta una conexión que
    pasa 60 s sin recibir nada, y el espacio delante de un objeto JSON es
    válido, así que el Atajo puede leer el cuerpo tal cual. Además mantiene la
    petición viva, que es lo que hace que el servidor siga teniendo CPU
    asignada en plataformas que escalan a cero.
    """

    async def body():
        loop = asyncio.get_running_loop()
        deadline = loop.time() + seconds
        row = await asyncio.to_thread(storage.get_recipe, recipe_id)
        while row and row["status"] in {"pending", "processing"} and loop.time() < deadline:
            yield b" "
            await asyncio.sleep(POLL_SECONDS)
            row = await asyncio.to_thread(storage.get_recipe, recipe_id)

        payload = _public_row(row or {"id": recipe_id, "status": "pending", "source_url": url}, request)
        yield json.dumps(payload, ensure_ascii=False).encode()

    return StreamingResponse(body(), media_type="application/json")


def _load_ready_recipe(recipe_id: str) -> tuple[dict[str, Any], Recipe]:
    row = storage.get_recipe(recipe_id)
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

    existing = None if payload.force else storage.find_by_url(url)
    if existing:
        recipe_id = existing["id"]
    else:
        recipe_id = storage.create_recipe(url)
        _enqueue(recipe_id, url)

    if payload.wait:
        return _streamed_wait(recipe_id, url, request, payload.wait)

    row = storage.get_recipe(recipe_id)
    body = _public_row(row or {"id": recipe_id, "status": "pending", "source_url": url}, request)
    body["reused"] = bool(existing)
    return JSONResponse(body, status_code=200 if existing else 202)


@app.get("/api/recipes", dependencies=[Depends(security.require_api_key)])
def api_list_recipes(request: Request, q: str | None = None, limit: int = 50) -> dict[str, Any]:
    rows = storage.list_recipes(limit=min(limit, 200), query=q)
    recipes = [
        {**{key: value for key, value in row.items() if key != "haystack"},
         "web_url": str(request.url_for("recipe_page", recipe_id=row["id"]))}
        for row in rows
    ]
    return {"count": len(recipes), "recipes": recipes}


@app.get("/api/recipes/{recipe_id}", dependencies=[Depends(security.require_api_key)])
def api_get_recipe(recipe_id: str, request: Request) -> dict[str, Any]:
    row = storage.get_recipe(recipe_id)
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
    row = storage.get_recipe(recipe_id)
    if not row:
        raise HTTPException(status_code=404, detail="No existe esa receta.")
    storage.update_recipe(recipe_id, status="pending", error=None)
    _enqueue(recipe_id, row["source_url"])
    return _public_row(storage.get_recipe(recipe_id) or row, request)


@app.delete("/api/recipes/{recipe_id}", dependencies=[Depends(security.require_api_key)])
def api_delete(recipe_id: str) -> dict[str, Any]:
    if not storage.delete_recipe(recipe_id):
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
    cards = [
        {**row, "display_title": row.get("title") or "Sin título"}
        for row in storage.list_recipes(query=q)
    ]
    return templates.TemplateResponse(request, "index.html", {"recipes": cards, "q": q or ""})


@app.post("/nueva")
def web_create(request: Request, url: str = Form(...)):
    if not security.web_session_ok(request):
        return _redirect_to_login(request)
    clean = download.normalize_url(url)
    if not download.is_supported_url(clean):
        return RedirectResponse(url="/?error=url", status_code=303)
    existing = storage.find_by_url(clean)
    if existing:
        return RedirectResponse(url=f"/receta/{existing['id']}", status_code=303)
    recipe_id = storage.create_recipe(clean)
    _enqueue(recipe_id, clean, inline=settings.serverless)
    return RedirectResponse(url=f"/receta/{recipe_id}", status_code=303)


@app.post("/ejemplo")
def web_demo(request: Request):
    """Guarda una receta de muestra: sirve para ver la web sin gastar un reel."""
    if not security.web_session_ok(request):
        return _redirect_to_login(request)
    from app.demo import DEMO_RECIPE

    recipe_id = storage.create_recipe("ejemplo://receta-de-muestra")
    storage.update_recipe(recipe_id, status="ready", title=DEMO_RECIPE["title"], data=DEMO_RECIPE)
    return RedirectResponse(url=f"/receta/{recipe_id}", status_code=303)


@app.get("/receta/{recipe_id}", response_class=HTMLResponse, name="recipe_page")
def recipe_page(request: Request, recipe_id: str, servings: int | None = None):
    if not security.web_session_ok(request):
        return _redirect_to_login(request)
    row = storage.get_recipe(recipe_id)
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
    row = storage.get_recipe(recipe_id)
    if not row:
        raise HTTPException(status_code=404, detail="No existe esa receta.")
    storage.update_recipe(recipe_id, status="pending", error=None)
    _enqueue(recipe_id, row["source_url"], inline=settings.serverless)
    return RedirectResponse(url=f"/receta/{recipe_id}", status_code=303)


@app.post("/receta/{recipe_id}/borrar")
def web_delete(request: Request, recipe_id: str):
    if not security.web_session_ok(request):
        return _redirect_to_login(request)
    storage.delete_recipe(recipe_id)
    return RedirectResponse(url="/", status_code=303)


@app.get("/media/{filename}")
def media_file(request: Request, filename: str):
    if not security.web_session_ok(request):
        raise HTTPException(status_code=401, detail="Sesión no iniciada")
    image = storage.read_thumbnail(Path(filename).stem)
    if image is None:
        raise HTTPException(status_code=404, detail="No encontrado")
    return Response(
        image, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"}
    )
