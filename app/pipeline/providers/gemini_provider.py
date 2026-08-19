"""Google Gemini a través de su capa gratuita (AI Studio)."""

from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.models import RECIPE_JSON_SCHEMA
from app.pipeline.providers.base import Part, ProviderError, encode_image
from app.schema_utils import gemini_schema

logger = logging.getLogger(__name__)

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiProvider:
    name = "gemini"
    # Gemini procesa el vídeo entero: ve las imágenes y escucha el audio, así
    # que no hace falta ni extraer fotogramas ni transcribir por separado.
    accepts_video = True

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model = model or settings.gemini_model
        if not self.api_key:
            raise ProviderError(
                "Falta GEMINI_API_KEY. Consíguela gratis en https://aistudio.google.com/apikey"
            )

    def _payload(self, system: str, parts: list[Part]) -> dict:
        contents = []
        for kind, value in parts:
            if kind == "text":
                contents.append({"text": str(value)})
            else:
                mime = "video/mp4" if kind == "video" else "image/jpeg"
                contents.append({"inline_data": {"mime_type": mime, "data": encode_image(value)}})

        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": contents}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "responseSchema": gemini_schema(RECIPE_JSON_SCHEMA),
            },
        }

    def generate(self, system: str, parts: list[Part]) -> str:
        try:
            response = httpx.post(
                ENDPOINT.format(model=self.model),
                params={"key": self.api_key},
                json=self._payload(system, parts),
                timeout=300,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"No se pudo contactar con Gemini: {exc}") from exc

        if response.status_code == 429:
            raise ProviderError(
                "Se ha agotado la cuota gratuita de Gemini por hoy. Inténtalo más tarde "
                "o cambia a LLM_PROVIDER=ollama."
            )
        if response.status_code == 400 and "API key" in response.text:
            raise ProviderError("La GEMINI_API_KEY no es válida.")
        if response.status_code in (400, 413) and "too large" in response.text.lower():
            raise ProviderError(
                "El vídeo excede el tamaño que admite Gemini en una petición. "
                "Baja VIDEO_MAX_BYTES o pon SEND_VIDEO=false."
            )
        if response.status_code >= 400:
            raise ProviderError(f"Gemini devolvió {response.status_code}: {response.text[:300]}")

        return _extract_text(response.json())


def _extract_text(body: dict) -> str:
    blocked = body.get("promptFeedback", {}).get("blockReason")
    if blocked:
        raise ProviderError(f"Gemini bloqueó la petición ({blocked}).")

    candidates = body.get("candidates") or []
    if not candidates:
        raise ProviderError("Gemini no devolvió ninguna respuesta.")

    candidate = candidates[0]
    finish = candidate.get("finishReason")
    if finish == "MAX_TOKENS":
        raise ProviderError("La respuesta de Gemini se cortó por longitud; prueba con menos fotogramas.")
    if finish not in (None, "STOP"):
        raise ProviderError(f"Gemini terminó de forma inesperada ({finish}).")

    text = "".join(part.get("text", "") for part in candidate.get("content", {}).get("parts", []))
    if not text.strip():
        raise ProviderError("Gemini devolvió una respuesta vacía.")
    return text


def check_available() -> tuple[bool, str]:
    if not settings.gemini_api_key:
        return False, "Falta GEMINI_API_KEY (gratis en https://aistudio.google.com/apikey)"
    return True, f"Gemini listo con '{settings.gemini_model}'"
