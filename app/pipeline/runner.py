"""Orquesta el proceso completo: URL -> receta guardada."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app import storage
from app.config import settings
from app.models import Recipe
from app.pipeline import download, media, transcribe
from app.pipeline.extract import ExtractionInput, extract_recipe
from app.pipeline.providers import Provider, get_provider

logger = logging.getLogger(__name__)


def process_recipe(recipe_id: str, url: str) -> None:
    """Punto de entrada del trabajo en segundo plano. Nunca lanza excepciones."""
    work_dir = settings.work_dir / recipe_id
    try:
        storage.update_recipe(recipe_id, status="processing", error=None)
        recipe = _run(recipe_id, url, work_dir)
        storage.update_recipe(
            recipe_id,
            status="ready",
            title=recipe.title,
            data=recipe.model_dump(mode="json"),
            error=None,
        )
        logger.info("Receta %s lista: %s", recipe_id, recipe.title)
    except Exception as exc:
        logger.exception("Falló el procesado de %s", recipe_id)
        storage.update_recipe(recipe_id, status="error", error=str(exc)[:1000])
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _run(recipe_id: str, url: str, work_dir: Path) -> Recipe:
    provider = get_provider()
    source = download.fetch(url, work_dir)
    storage.update_recipe(
        recipe_id,
        caption=source.caption,
        author=source.author,
        title=source.title or None,
    )

    payload = ExtractionInput(
        caption=source.caption,
        author=source.author,
        source_url=source.webpage_url,
        duration=source.duration,
    )

    if source.video_path:
        _attach_video_material(recipe_id, source.video_path, work_dir, provider, payload)

    return extract_recipe(payload, provider=provider)


def _attach_video_material(
    recipe_id: str,
    video: Path,
    work_dir: Path,
    provider: Provider,
    payload: ExtractionInput,
) -> None:
    """Decide qué se le manda al modelo: el vídeo entero o fotogramas y audio."""
    has_ffmpeg = media.ffmpeg_available()

    if settings.send_video and getattr(provider, "accepts_video", False):
        ready = video if not has_ffmpeg else media.compress_for_upload(
            video, work_dir / "subida.mp4", settings.video_max_bytes
        )
        if ready and ready.stat().st_size <= settings.video_max_bytes:
            payload.video = ready
            _save_thumbnail(recipe_id, video, work_dir, has_ffmpeg)
            return
        logger.info("El vídeo no cabe en una petición; se usarán fotogramas.")

    if not has_ffmpeg:
        logger.warning("Sin ffmpeg y sin envío de vídeo: solo se usará el texto del post.")
        return

    if settings.frame_count > 0:
        payload.frames = media.extract_frames(
            video, work_dir / "frames", settings.frame_count, settings.frame_max_dim
        )

    audio = media.extract_audio(video, work_dir / "audio.wav")
    if audio:
        payload.transcript = transcribe.transcribe(audio)
        if payload.transcript:
            storage.update_recipe(recipe_id, transcript=payload.transcript)

    _save_thumbnail(recipe_id, video, work_dir, has_ffmpeg, payload.frames)


def _save_thumbnail(
    recipe_id: str,
    video: Path,
    work_dir: Path,
    has_ffmpeg: bool,
    frames: list[tuple[float, Path]] | None = None,
) -> None:
    """Un fotograma del último tercio: suele ser el plato terminado."""
    if not has_ffmpeg:
        return
    try:
        if frames:
            _, chosen = frames[min(len(frames) - 1, int(len(frames) * 0.75))]
        else:
            duration = media.duration_seconds(video)
            instante = duration * 0.8 if duration > 4 else max(duration / 2, 0.1)
            _, chosen = media.extract_frames_at(video, work_dir / "portada", [instante], 640)[0]
        storage.save_thumbnail(recipe_id, chosen)
    except Exception:
        logger.warning("No se pudo guardar la miniatura de %s", recipe_id, exc_info=True)
