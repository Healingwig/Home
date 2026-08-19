"""Guardado de recetas sobre almacenamiento de objetos.

Cada receta es un JSON y su miniatura un JPEG, así que no hace falta una base
de datos: funciona igual sobre disco (desarrollo) que sobre Google Cloud
Storage (producción sin ordenador propio, donde no hay disco persistente).

Un índice con los resúmenes evita tener que leer todas las recetas para pintar
el listado.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from app.config import settings

logger = logging.getLogger(__name__)

INDEX_NAME = "index.json"
INDEX_RETRIES = 6
INDEX_BACKOFF_SECONDS = 0.2
SUMMARY_FIELDS = ("id", "source_url", "status", "error", "title", "author", "thumbnail",
                  "created_at", "updated_at")


class ObjectStore:
    """Interfaz mínima: leer, escribir, borrar y modificar en exclusiva."""

    def get_bytes(self, name: str) -> bytes | None:
        raise NotImplementedError

    def put_bytes(self, name: str, data: bytes, content_type: str) -> None:
        raise NotImplementedError

    def delete(self, name: str) -> bool:
        raise NotImplementedError

    def update_json(self, name: str, mutate: Callable[[dict], dict]) -> dict:
        """Lee, aplica `mutate` y escribe, sin que se pisen dos escrituras."""
        raise NotImplementedError

    def get_json(self, name: str) -> dict | None:
        raw = self.get_bytes(name)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("El objeto %s no es JSON válido", name)
            return None

    def put_json(self, name: str, data: dict) -> None:
        self.put_bytes(name, json.dumps(data, ensure_ascii=False).encode(), "application/json")


class LocalObjectStore(ObjectStore):
    """Ficheros en disco. Para desarrollo y para quien lo ejecute en su equipo."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, name: str) -> Path:
        path = (self.root / name).resolve()
        if not str(path).startswith(str(self.root.resolve())):
            raise ValueError(f"Ruta fuera del almacén: {name}")
        return path

    def get_bytes(self, name: str) -> bytes | None:
        path = self._path(name)
        return path.read_bytes() if path.is_file() else None

    def put_bytes(self, name: str, data: bytes, content_type: str) -> None:
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Escritura atómica: nadie ve un fichero a medias.
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(path)

    def delete(self, name: str) -> bool:
        path = self._path(name)
        if not path.is_file():
            return False
        path.unlink()
        return True

    def update_json(self, name: str, mutate: Callable[[dict], dict]) -> dict:
        with self._lock:
            updated = mutate(self.get_json(name) or {})
            self.put_json(name, updated)
            return updated


class GcsObjectStore(ObjectStore):
    """Google Cloud Storage. Su capa gratuita cubre de sobra un recetario."""

    def __init__(self, bucket_name: str, prefix: str = "", bucket: Any = None):
        if bucket is None:
            try:
                from google.cloud import storage
            except ImportError as exc:
                raise RuntimeError(
                    "Falta google-cloud-storage. Instálalo con: pip install google-cloud-storage"
                ) from exc
            bucket = storage.Client().bucket(bucket_name)
        self._bucket = bucket
        self.prefix = prefix.strip("/")

    def _blob(self, name: str):
        return self._bucket.blob(f"{self.prefix}/{name}" if self.prefix else name)

    def get_bytes(self, name: str) -> bytes | None:
        from google.cloud.exceptions import NotFound

        try:
            return self._blob(name).download_as_bytes()
        except NotFound:
            return None

    def put_bytes(self, name: str, data: bytes, content_type: str) -> None:
        self._blob(name).upload_from_string(data, content_type=content_type)

    def delete(self, name: str) -> bool:
        from google.cloud.exceptions import NotFound

        try:
            self._blob(name).delete()
            return True
        except NotFound:
            return False

    def update_json(self, name: str, mutate: Callable[[dict], dict]) -> dict:
        """Lectura-modificación-escritura con control de versión y reintentos.

        Dos recetas procesándose a la vez tocan el mismo índice; la condición
        de generación hace que la segunda reintente en lugar de pisar a la
        primera.
        """
        from google.api_core.exceptions import PreconditionFailed
        from google.cloud.exceptions import NotFound

        blob = self._blob(name)
        for intento in range(INDEX_RETRIES):
            try:
                current = json.loads(blob.download_as_bytes())
                generation = blob.generation
            except NotFound:
                current, generation = {}, 0
            except json.JSONDecodeError:
                current, generation = {}, blob.generation or 0

            updated = mutate(current)
            try:
                blob.upload_from_string(
                    json.dumps(updated, ensure_ascii=False),
                    content_type="application/json",
                    if_generation_match=generation,
                )
                return updated
            except PreconditionFailed:
                logger.info("El índice cambió mientras se escribía; reintento %d", intento + 1)
                blob = self._blob(name)
                time.sleep(INDEX_BACKOFF_SECONDS * (intento + 1))
        raise RuntimeError("No se pudo actualizar el índice tras varios reintentos.")


# --------------------------------------------------------------------------- #
# Recetas
# --------------------------------------------------------------------------- #

_store: ObjectStore | None = None


def get_store() -> ObjectStore:
    global _store
    if _store is None:
        if settings.storage_backend == "gcs":
            if not settings.gcs_bucket:
                raise RuntimeError("STORAGE_BACKEND=gcs requiere GCS_BUCKET.")
            _store = GcsObjectStore(settings.gcs_bucket, settings.gcs_prefix)
            logger.info("Almacenando en gs://%s/%s", settings.gcs_bucket, settings.gcs_prefix)
        else:
            _store = LocalObjectStore(settings.data_dir)
            logger.info("Almacenando en %s", settings.data_dir)
    return _store


def reset_store() -> None:
    """Fuerza a releer la configuración (lo usan las pruebas)."""
    global _store
    _store = None


def init() -> None:
    get_store()


def _recipe_name(recipe_id: str) -> str:
    return f"recetas/{recipe_id}.json"


def _thumbnail_name(recipe_id: str) -> str:
    return f"miniaturas/{recipe_id}.jpg"


def _summary(record: dict[str, Any]) -> dict[str, Any]:
    summary = {field: record.get(field) for field in SUMMARY_FIELDS}
    data = record.get("data") or {}
    summary["title"] = data.get("title") or record.get("title")
    summary["summary"] = data.get("summary") or ""
    parts = [data.get("prep_minutes"), data.get("cook_minutes")]
    total = sum(part for part in parts if isinstance(part, int))
    summary["total_minutes"] = total or None
    # Con esto el buscador del listado no necesita abrir cada receta.
    summary["haystack"] = " ".join(
        [str(summary["title"] or ""), summary["summary"], *(data.get("tags") or []),
         *[str(i.get("name", "")) for i in (data.get("ingredients") or [])]]
    ).lower()
    return summary


def _index_put(record: dict[str, Any]) -> None:
    get_store().update_json(INDEX_NAME, lambda index: {**index, record["id"]: _summary(record)})


def _index_drop(recipe_id: str) -> None:
    def mutate(index: dict) -> dict:
        index.pop(recipe_id, None)
        return index

    get_store().update_json(INDEX_NAME, mutate)


def create_recipe(source_url: str) -> str:
    recipe_id = uuid.uuid4().hex[:12]
    now = time.time()
    record = {
        "id": recipe_id, "source_url": source_url, "status": "pending", "error": None,
        "title": None, "author": None, "caption": None, "transcript": None,
        "data": None, "thumbnail": None, "created_at": now, "updated_at": now,
    }
    get_store().put_json(_recipe_name(recipe_id), record)
    _index_put(record)
    return recipe_id


def update_recipe(recipe_id: str, **fields: Any) -> dict[str, Any] | None:
    store = get_store()
    record = store.get_json(_recipe_name(recipe_id))
    if record is None:
        logger.warning("Se intentó actualizar una receta inexistente: %s", recipe_id)
        return None
    record.update(fields)
    record["updated_at"] = time.time()
    store.put_json(_recipe_name(recipe_id), record)
    _index_put(record)
    return record


def get_recipe(recipe_id: str) -> dict[str, Any] | None:
    return get_store().get_json(_recipe_name(recipe_id))


def find_by_url(source_url: str) -> dict[str, Any] | None:
    matches = [
        summary
        for summary in _index().values()
        if summary.get("source_url") == source_url
        and summary.get("status") in {"pending", "processing", "ready"}
    ]
    if not matches:
        return None
    newest = max(matches, key=lambda item: item.get("created_at") or 0)
    return get_recipe(newest["id"])


def _index() -> dict[str, dict[str, Any]]:
    return get_store().get_json(INDEX_NAME) or {}


def list_recipes(limit: int = 200, query: str | None = None) -> list[dict[str, Any]]:
    rows = sorted(_index().values(), key=lambda item: item.get("created_at") or 0, reverse=True)
    if query:
        needle = query.strip().lower()
        rows = [row for row in rows if needle in (row.get("haystack") or "")]
    return rows[:limit]


def delete_recipe(recipe_id: str) -> bool:
    store = get_store()
    store.delete(_thumbnail_name(recipe_id))
    existed = store.delete(_recipe_name(recipe_id))
    _index_drop(recipe_id)
    return existed


def save_thumbnail(recipe_id: str, source: Path) -> None:
    get_store().put_bytes(_thumbnail_name(recipe_id), Path(source).read_bytes(), "image/jpeg")
    update_recipe(recipe_id, thumbnail=f"{recipe_id}.jpg")


def read_thumbnail(recipe_id: str) -> bytes | None:
    return get_store().get_bytes(_thumbnail_name(recipe_id))


def iter_stale_processing(older_than_seconds: int) -> list[dict[str, Any]]:
    """Recetas que se quedaron a medias (el contenedor se apagó a mitad)."""
    cutoff = time.time() - older_than_seconds
    return [
        summary
        for summary in _index().values()
        if summary.get("status") in {"pending", "processing"}
        and (summary.get("updated_at") or 0) < cutoff
    ]
