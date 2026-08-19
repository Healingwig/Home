"""Convierte el material del vídeo en una receta estructurada con Claude."""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic

from app.config import settings
from app.models import RECIPE_JSON_SCHEMA, Recipe

logger = logging.getLogger(__name__)

REFUSAL_FALLBACK_BETA = "server-side-fallback-2026-07-01"

SYSTEM_PROMPT = f"""Eres un chef que transcribe recetas de vídeos cortos de redes sociales \
(reels de Instagram, TikTok) a fichas de cocina claras y ejecutables.

Recibes tres fuentes sobre el mismo vídeo, en orden de fiabilidad:
1. El texto del post (pie de foto): suele traer la lista de ingredientes con cantidades. Es la fuente más fiable para las cantidades.
2. La transcripción del audio: lo que dice la persona mientras cocina. Fiable para el orden y la técnica.
3. Fotogramas del vídeo en orden cronológico: muestran los ingredientes, las texturas y, muy a menudo, texto sobreimpreso con las cantidades. Léelo.

Reglas:
- Escribe TODO en {settings.language}, incluidos los nombres de ingredientes y utensilios.
- Usa unidades del sistema métrico (g, ml, cucharada, cucharadita, unidad). Convierte tazas y onzas si aparecen.
- Deduce las cantidades que falten a partir de lo que se ve y de proporciones habituales de cocina, y anota esa deducción en `warnings`. Nunca inventes un ingrediente que no aparece ni se menciona.
- `pantry: true` solo para básicos que casi todo el mundo tiene: sal, pimienta, aceite de oliva, agua, azúcar.
- Los pasos deben ser autocontenidos: quien los lea en una tablet mientras cocina no ve el vídeo. Incluye temperaturas, tiempos y señales sensoriales ("hasta que dore", "hasta que espese").
- Un paso por acción significativa. Entre 4 y 12 pasos.
- `timer_seconds` solo cuando el paso tenga una espera concreta (hornear 25 min, reposar 10 min); si no, null.
- `servings`: si el vídeo no lo dice, estima a partir de las cantidades y anótalo en `warnings`.
- `confidence`: 0.9+ si el pie de foto trae la receta completa; 0.5-0.7 si has tenido que reconstruirla de los fotogramas; menos de 0.4 si el vídeo apenas es una receta.

Si el material no corresponde a una receta de cocina, devuelve igualmente el JSON con \
`title` describiendo lo que hay, `confidence` cercano a 0 y una advertencia explicándolo."""


@dataclass
class ExtractionInput:
    caption: str = ""
    transcript: str = ""
    author: str = ""
    source_url: str = ""
    duration: float | None = None
    frames: list[tuple[float, Path]] = field(default_factory=list)


class ExtractionError(RuntimeError):
    pass


def _image_block(path: Path) -> dict[str, Any]:
    data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": data},
    }


def _context_text(payload: ExtractionInput) -> str:
    lines = ["<contexto>"]
    if payload.source_url:
        lines.append(f"URL: {payload.source_url}")
    if payload.author:
        lines.append(f"Cuenta: @{payload.author}")
    if payload.duration:
        lines.append(f"Duración del vídeo: {int(payload.duration)} s")
    lines.append("</contexto>")

    lines.append("\n<pie_del_post>")
    lines.append(payload.caption.strip() or "(el post no tiene texto)")
    lines.append("</pie_del_post>")

    lines.append("\n<transcripcion_audio>")
    lines.append(payload.transcript.strip() or "(sin audio o sin transcripción disponible)")
    lines.append("</transcripcion_audio>")
    return "\n".join(lines)


def build_content(payload: ExtractionInput) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [{"type": "text", "text": _context_text(payload)}]
    if payload.frames:
        content.append(
            {"type": "text", "text": f"\nFotogramas del vídeo ({len(payload.frames)}), en orden cronológico:"}
        )
        for timestamp, path in payload.frames:
            content.append({"type": "text", "text": f"Fotograma en {timestamp:.1f}s:"})
            content.append(_image_block(path))
    content.append(
        {
            "type": "text",
            "text": (
                "\nDevuelve la receta completa siguiendo el esquema. Repasa los fotogramas en busca de "
                "cantidades sobreimpresas antes de dar por perdida una cantidad."
            ),
        }
    )
    return content


def _request_kwargs(content: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "model": settings.model,
        "max_tokens": settings.max_tokens,
        "system": SYSTEM_PROMPT,
        "thinking": {"type": "adaptive"},
        "output_config": {
            "effort": settings.effort,
            "format": {"type": "json_schema", "schema": RECIPE_JSON_SCHEMA},
        },
        "messages": [{"role": "user", "content": content}],
    }


def _call_claude(client: anthropic.Anthropic, content: list[dict[str, Any]]):
    kwargs = _request_kwargs(content)
    if settings.refusal_fallback:
        try:
            # `fallbacks: "default"` enruta a otro modelo si un clasificador
            # rechaza la petición, en lugar de devolvernos un error.
            return client.beta.messages.create(
                betas=[REFUSAL_FALLBACK_BETA], fallbacks="default", **kwargs
            )
        except anthropic.BadRequestError as exc:
            logger.warning("Fallback de rechazo no disponible (%s); reintento sin él.", exc)
    return client.messages.create(**kwargs)


def _response_text(response) -> str:
    for block in response.content:
        if block.type == "text" and block.text.strip():
            return block.text
    raise ExtractionError("Claude no devolvió ningún bloque de texto con la receta.")


def extract_recipe(payload: ExtractionInput, client: anthropic.Anthropic | None = None) -> Recipe:
    if not payload.caption.strip() and not payload.transcript.strip() and not payload.frames:
        raise ExtractionError("No hay material suficiente (ni texto, ni audio, ni imágenes).")

    client = client or anthropic.Anthropic()
    response = _call_claude(client, build_content(payload))

    if getattr(response, "stop_reason", None) == "refusal":
        details = getattr(response, "stop_details", None)
        reason = getattr(details, "explanation", None) or "sin detalle"
        raise ExtractionError(f"El modelo rechazó procesar este vídeo ({reason}).")

    raw = _response_text(response)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"La respuesta del modelo no era JSON válido: {exc}") from exc

    try:
        return Recipe.model_validate(data)
    except Exception as exc:
        raise ExtractionError(f"La receta no encaja con el esquema esperado: {exc}") from exc
