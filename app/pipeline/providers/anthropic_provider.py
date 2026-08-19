"""Claude (API de Anthropic). Es de pago, pero da la mejor lectura del texto
sobreimpreso en los vídeos."""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.models import RECIPE_JSON_SCHEMA
from app.pipeline.providers.base import Part, ProviderError, encode_image

logger = logging.getLogger(__name__)

REFUSAL_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    name = "anthropic"
    accepts_video = False

    def __init__(self, client: Any | None = None, model: str | None = None):
        self.model = model or settings.anthropic_model
        if client is not None:
            self.client = client
        else:
            try:
                import anthropic
            except ImportError as exc:
                raise ProviderError(
                    "Falta el paquete `anthropic`. Instálalo con: pip install anthropic"
                ) from exc
            try:
                self.client = anthropic.Anthropic()
            except Exception as exc:
                raise ProviderError(f"No se pudo crear el cliente de Anthropic: {exc}") from exc

    def _content(self, parts: list[Part]) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for kind, value in parts:
            if kind == "text":
                blocks.append({"type": "text", "text": str(value)})
            else:
                blocks.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": encode_image(value),
                        },
                    }
                )
        return blocks

    def _kwargs(self, system: str, parts: list[Part]) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": settings.max_tokens,
            "system": system,
            "thinking": {"type": "adaptive"},
            "output_config": {
                "effort": settings.effort,
                "format": {"type": "json_schema", "schema": RECIPE_JSON_SCHEMA},
            },
            "messages": [{"role": "user", "content": self._content(parts)}],
        }

    def generate(self, system: str, parts: list[Part]) -> str:
        import anthropic

        kwargs = self._kwargs(system, parts)
        response = None
        if settings.refusal_fallback:
            try:
                # `fallbacks: "default"` reencamina a otro modelo si un
                # clasificador rechaza la petición, en vez de devolver error.
                response = self.client.beta.messages.create(
                    betas=[REFUSAL_FALLBACK_BETA], fallbacks="default", **kwargs
                )
            except anthropic.BadRequestError as exc:
                logger.warning("Fallback de rechazo no disponible (%s); reintento sin él.", exc)
        if response is None:
            response = self.client.messages.create(**kwargs)

        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            reason = getattr(details, "explanation", None) or "sin detalle"
            raise ProviderError(f"El modelo rechazó procesar este vídeo ({reason}).")

        for block in response.content:
            if block.type == "text" and block.text.strip():
                return block.text
        raise ProviderError("Claude no devolvió ningún bloque de texto con la receta.")


def check_available() -> tuple[bool, str]:
    import os

    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        return False, "Falta ANTHROPIC_API_KEY"
    return True, f"Claude listo con '{settings.anthropic_model}'"
