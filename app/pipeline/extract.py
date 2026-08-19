"""Convierte el material del vídeo en una receta estructurada.

El modelo que hace el trabajo se elige con `LLM_PROVIDER`; aquí solo se prepara
el material y se valida lo que devuelve.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings
from app.models import Recipe
from app.pipeline.providers import Part, Provider, ProviderError, get_provider

logger = logging.getLogger(__name__)

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

Responde únicamente con el objeto JSON de la receta, sin texto alrededor ni bloques de código.

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


def build_parts(payload: ExtractionInput) -> list[Part]:
    """Material del vídeo en fragmentos que cada backend traduce a su formato."""
    parts: list[Part] = [("text", _context_text(payload))]
    if payload.frames:
        parts.append(
            ("text", f"\nFotogramas del vídeo ({len(payload.frames)}), en orden cronológico:")
        )
        for index, (timestamp, path) in enumerate(payload.frames, start=1):
            parts.append(("text", f"Fotograma {index} de {len(payload.frames)}, en {timestamp:.1f}s:"))
            parts.append(("image", path))
    parts.append(
        (
            "text",
            "\nDevuelve la receta completa siguiendo el esquema. Repasa los fotogramas en busca de "
            "cantidades sobreimpresas antes de dar por perdida una cantidad.",
        )
    )
    return parts


def parse_recipe(raw: str) -> Recipe:
    """Valida la respuesta del modelo, tolerando envoltorios de los modelos locales."""
    try:
        data = json.loads(_strip_wrapper(raw))
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"La respuesta del modelo no era JSON válido: {exc}") from exc

    if not isinstance(data, dict):
        raise ExtractionError("El modelo devolvió un JSON que no es un objeto de receta.")

    try:
        return Recipe.model_validate(data)
    except Exception as exc:
        raise ExtractionError(f"La receta no encaja con el esquema esperado: {exc}") from exc


def _strip_wrapper(raw: str) -> str:
    """Los modelos locales suelen envolver el JSON en ```json … ```."""
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fenced:
        return fenced.group(1).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return text[start : end + 1]
    return text


def extract_recipe(payload: ExtractionInput, provider: Provider | None = None) -> Recipe:
    if not payload.caption.strip() and not payload.transcript.strip() and not payload.frames:
        raise ExtractionError("No hay material suficiente (ni texto, ni audio, ni imágenes).")

    try:
        backend = provider or get_provider()
        raw = backend.generate(SYSTEM_PROMPT, build_parts(payload))
    except ProviderError as exc:
        raise ExtractionError(str(exc)) from exc

    return parse_recipe(raw)
