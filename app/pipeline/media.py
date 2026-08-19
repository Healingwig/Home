"""Utilidades de ffmpeg: duración, fotogramas y pista de audio."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class MediaError(RuntimeError):
    pass


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _run(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def probe(path: Path) -> dict:
    result = _run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        timeout=60,
    )
    if result.returncode != 0:
        raise MediaError(f"ffprobe falló: {result.stderr.strip()[:200]}")
    return json.loads(result.stdout or "{}")


def duration_seconds(path: Path) -> float:
    info = probe(path)
    raw = info.get("format", {}).get("duration")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def has_audio(path: Path) -> bool:
    return any(s.get("codec_type") == "audio" for s in probe(path).get("streams", []))


def frame_timestamps(duration: float, count: int) -> list[float]:
    """Reparte `count` instantes por el vídeo evitando el primer y último frame."""
    if duration <= 0 or count <= 0:
        return [0.0]
    if count == 1:
        return [duration / 2]
    usable = max(duration - 0.4, 0.1)
    step = usable / (count - 1)
    return [round(0.2 + step * i, 2) for i in range(count)]


def extract_frames(video: Path, out_dir: Path, count: int, max_dim: int) -> list[tuple[float, Path]]:
    """Devuelve [(segundo, ruta_jpg)] con fotogramas repartidos por el vídeo."""
    stamps = frame_timestamps(duration_seconds(video), count)
    frames = extract_frames_at(video, out_dir, stamps, max_dim)
    if not frames:
        raise MediaError("ffmpeg no pudo extraer ningún fotograma del vídeo.")
    return frames


def extract_frames_at(
    video: Path, out_dir: Path, timestamps: list[float], max_dim: int
) -> list[tuple[float, Path]]:
    """Extrae los fotogramas de los instantes indicados."""
    out_dir.mkdir(parents=True, exist_ok=True)
    frames: list[tuple[float, Path]] = []
    scale = f"scale='min({max_dim},iw)':-2:flags=lanczos"

    for index, timestamp in enumerate(timestamps):
        target = out_dir / f"frame_{index:02d}.jpg"
        result = _run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                "-ss", f"{timestamp:.2f}", "-i", str(video),
                "-frames:v", "1", "-vf", scale, "-q:v", "3", "-y", str(target),
            ],
            timeout=120,
        )
        if result.returncode == 0 and target.exists() and target.stat().st_size > 0:
            frames.append((timestamp, target))
        else:
            logger.warning("No se pudo extraer el fotograma en %.2fs: %s", timestamp, result.stderr.strip()[:120])

    return frames


def extract_audio(video: Path, out_path: Path) -> Path | None:
    """Pista mono a 16 kHz, que es lo que espera Whisper."""
    if not has_audio(video):
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = _run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
            "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
            "-c:a", "pcm_s16le", "-y", str(out_path),
        ],
        timeout=600,
    )
    if result.returncode != 0 or not out_path.exists():
        logger.warning("No se pudo extraer el audio: %s", result.stderr.strip()[:200])
        return None
    return out_path


def compress_for_upload(video: Path, out_path: Path, max_bytes: int) -> Path | None:
    """Recomprime el vídeo para que quepa en una petición al modelo.

    Devuelve el original si ya cabe, el recomprimido si se consigue, o None si
    ni bajando la calidad entra (entonces se usan fotogramas sueltos).
    """
    if video.stat().st_size <= max_bytes and video.suffix.lower() == ".mp4":
        return video

    duration = duration_seconds(video)
    if duration <= 0:
        return None

    out_path.parent.mkdir(parents=True, exist_ok=True)
    for height, audio_kbps in ((480, 48), (360, 32)):
        # Bitrate objetivo a partir del tamaño máximo, con margen para el
        # contenedor. El audio importa: Gemini lo transcribe.
        total_kbps = (max_bytes * 8 / 1000) / duration * 0.88
        video_kbps = max(int(total_kbps - audio_kbps), 120)
        result = _run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(video),
                "-vf", f"scale='min(iw,trunc(ih*{height}/ih))':'min({height},ih)':flags=lanczos",
                "-c:v", "libx264", "-preset", "veryfast",
                "-b:v", f"{video_kbps}k", "-maxrate", f"{int(video_kbps * 1.4)}k",
                "-bufsize", f"{video_kbps * 2}k",
                "-c:a", "aac", "-b:a", f"{audio_kbps}k", "-ac", "1",
                "-movflags", "+faststart", "-y", str(out_path),
            ],
            timeout=900,
        )
        if result.returncode == 0 and out_path.exists() and out_path.stat().st_size <= max_bytes:
            logger.info(
                "Vídeo recomprimido a %.1f MB (%dp)", out_path.stat().st_size / 1e6, height
            )
            return out_path
        logger.warning("La recompresión a %dp no bastó: %s", height, result.stderr.strip()[:150])

    return None
