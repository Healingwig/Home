"""Modelo local con Ollama. Gratis y sin salir del ordenador."""

from __future__ import annotations

import json
import logging

import httpx

from app.config import settings
from app.models import RECIPE_JSON_SCHEMA
from app.pipeline.providers.base import Part, ProviderError, encode_image, flatten_text, images_of
from app.schema_utils import relaxed_schema

logger = logging.getLogger(__name__)


class OllamaProvider:
    name = "ollama"

    def __init__(self, host: str | None = None, model: str | None = None):
        self.host = (host or settings.ollama_host).rstrip("/")
        self.model = model or settings.ollama_model

    def _payload(self, system: str, parts: list[Part], with_schema: bool) -> dict:
        message = {"role": "user", "content": flatten_text(parts)}
        images = images_of(parts)
        if images:
            message["images"] = [encode_image(path) for path in images]

        return {
            "model": self.model,
            "stream": False,
            # `format` fuerza JSON: con esquema si el servidor lo admite, y en
            # modo JSON libre como reserva (el modelo Pydantic es tolerante).
            "format": relaxed_schema(RECIPE_JSON_SCHEMA) if with_schema else "json",
            "options": {"temperature": 0.2, "num_ctx": 16384},
            "messages": [{"role": "system", "content": system}, message],
        }

    def _post(self, payload: dict) -> str:
        try:
            response = httpx.post(
                f"{self.host}/api/chat", json=payload, timeout=settings.ollama_timeout
            )
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"No se pudo contactar con Ollama en {self.host}. ¿Está arrancado? ({exc})"
            ) from exc

        if response.status_code == 404:
            raise ProviderError(
                f"Ollama no tiene el modelo '{self.model}'. Descárgalo con: ollama pull {self.model}"
            )
        if response.status_code >= 400:
            raise ProviderError(f"Ollama devolvió {response.status_code}: {response.text[:300]}")

        content = response.json().get("message", {}).get("content", "")
        if not content.strip():
            raise ProviderError("Ollama devolvió una respuesta vacía.")
        return content

    def generate(self, system: str, parts: list[Part]) -> str:
        try:
            return self._post(self._payload(system, parts, with_schema=True))
        except ProviderError as exc:
            # Las versiones antiguas de Ollama no aceptan un esquema en `format`.
            if "400" not in str(exc):
                raise
            logger.warning("Ollama rechazó el esquema; reintento en modo JSON libre.")
            return self._post(self._payload(system, parts, with_schema=False))


def check_available() -> tuple[bool, str]:
    """Comprobación para el arranque y para /healthz."""
    try:
        response = httpx.get(f"{settings.ollama_host}/api/tags", timeout=5)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return False, f"Ollama no responde en {settings.ollama_host} ({exc})"

    installed = [model.get("name", "") for model in response.json().get("models", [])]
    base = settings.ollama_model.split(":")[0]
    if not any(name == settings.ollama_model or name.startswith(f"{base}:") for name in installed):
        return False, f"Falta el modelo '{settings.ollama_model}'. Ejecuta: ollama pull {settings.ollama_model}"
    return True, f"Ollama listo con '{settings.ollama_model}'"
