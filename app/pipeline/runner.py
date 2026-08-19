"""Orquesta el proceso completo: URL -> receta guardada."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app import db
from app.config import settings
from app.models import Recipe
from app.pipeline import download, media, transcribe
from app.pipeline.extract import ExtractionInput, extract_recipe

logger = logging.getLogger(__name__)


def process_recipe(recipe_id: str, url: str) -> None:
    """Punto de entrada del trabajo en segundo plano. Nunca lanza excepciones."""
    work_dir = settings.work_dir / recipe_id
    try:
        db.update_recipe(recipe_id, status="processing", error=None)
        recipe = _run(recipe_id, url, work_dir)
        db.update_recipe(
            recipe_id,
            status="ready",
            title=recipe.title,
            data=recipe.model_dump(mode="json"),
            error=None,
        )
        logger.info("Receta %s lista: %s", recipe_id, recipe.title)
    except Exception as exc:
        logger.exception("Falló el procesado de %s", recipe_id)
        db.update_recipe(recipe_id, status="error", error=str(exc)[:1000])
    finally:
        if not settings.keep_video:
            shutil.rmtree(work_dir, ignore_errors=True)


def _run(recipe_id: str, url: str, work_dir: Path) -> Recipe:
    source = download.fetch(url, work_dir)
    db.update_recipe(
        recipe_id,
        caption=source.caption,
        author=source.author,
        title=source.title or None,
    )

    frames: list[tuple[float, Path]] = []
    transcript = ""

    if source.video_path and media.ffmpeg_available():
        if settings.frame_count > 0:
            frames = media.extract_frames(
                source.video_path, work_dir / "frames", settings.frame_count, settings.frame_max_dim
            )
        # Con FRAME_COUNT=0 (modelos locales solo de texto) seguimos sacando un
        # fotograma: no va al modelo, pero da portada a la receta.
        _save_thumbnail(recipe_id, frames or media.extract_frames(
            source.video_path, work_dir / "portada", 1, 640
        ))

        audio = media.extract_audio(source.video_path, work_dir / "audio.wav")
        if audio:
            transcript = transcribe.transcribe(audio)
            if transcript:
                db.update_recipe(recipe_id, transcript=transcript)
    elif source.video_path:
        logger.warning("ffmpeg no está disponible: se usará solo el texto del post.")

    recipe = extract_recipe(
        ExtractionInput(
            caption=source.caption,
            transcript=transcript,
            author=source.author,
            source_url=source.webpage_url,
            duration=source.duration,
            frames=frames,
        )
    )
    return recipe


def _save_thumbnail(recipe_id: str, frames: list[tuple[float, Path]]) -> None:
    """Guarda un fotograma del último tercio: suele ser el plato terminado."""
    if not frames:
        return
    _, chosen = frames[min(len(frames) - 1, int(len(frames) * 0.75))]
    settings.ensure_dirs()
    target = settings.media_dir / f"{recipe_id}.jpg"
    shutil.copyfile(chosen, target)
    db.update_recipe(recipe_id, thumbnail=target.name)
