"""Transcripción del audio con faster-whisper (opcional)."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_model():
    from faster_whisper import WhisperModel

    logger.info("Cargando modelo Whisper '%s'…", settings.whisper_model)
    return WhisperModel(
        settings.whisper_model,
        device="auto",
        compute_type=settings.whisper_compute_type,
    )


def available() -> bool:
    if settings.transcriber == "none":
        return False
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        if settings.transcriber == "whisper":
            logger.warning("TRANSCRIBER=whisper pero faster-whisper no está instalado.")
        return False
    return True


def transcribe(audio_path: Path) -> str:
    """Texto plano de la locución. Cadena vacía si no se puede transcribir."""
    if not available():
        return ""
    try:
        model = _load_model()
        segments, _info = model.transcribe(
            str(audio_path),
            vad_filter=True,
            beam_size=5,
            condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
    except Exception:  # una transcripción fallida no debe tumbar el pipeline
        logger.exception("Falló la transcripción del audio")
        return ""
