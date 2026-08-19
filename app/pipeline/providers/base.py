"""Interfaz común de los backends que convierten el vídeo en receta."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Literal, Protocol

# El contenido se describe de forma neutra y cada backend lo traduce a su
# formato: Claude intercala texto e imágenes, Ollama manda las imágenes aparte.
Part = tuple[Literal["text", "image"], str | Path]


class ProviderError(RuntimeError):
    """Fallo al hablar con el modelo (red, credenciales, cuota, rechazo)."""


class Provider(Protocol):
    name: str

    def generate(self, system: str, parts: list[Part]) -> str:
        """Devuelve la respuesta del modelo como texto JSON sin parsear."""


def encode_image(path: Path) -> str:
    return base64.standard_b64encode(Path(path).read_bytes()).decode("ascii")


def flatten_text(parts: list[Part]) -> str:
    """Une los fragmentos de texto para backends que no aceptan intercalado."""
    return "\n".join(str(value) for kind, value in parts if kind == "text")


def images_of(parts: list[Part]) -> list[Path]:
    return [Path(value) for kind, value in parts if kind == "image"]
