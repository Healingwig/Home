"""Descarga del vídeo y los metadatos del post con yt-dlp."""

from __future__ import annotations

import base64
import binascii
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com", "m.instagram.com", "instagr.am"}
URL_RE = re.compile(r"https?://\S+")


class DownloadError(RuntimeError):
    pass


@dataclass
class SourceMedia:
    video_path: Path | None
    caption: str
    title: str
    author: str
    duration: float | None
    webpage_url: str
    thumbnail_url: str | None


def normalize_url(raw: str) -> str:
    """El menú de compartir de iOS manda a veces texto suelto con la URL dentro."""
    raw = (raw or "").strip()
    match = URL_RE.search(raw)
    url = match.group(0) if match else raw
    url = url.rstrip(").,\"'>")
    # Quitamos parámetros de seguimiento (igshid, utm_*) que rompen la deduplicación.
    if "?" in url:
        base, _, query = url.partition("?")
        kept = [
            part
            for part in query.split("&")
            if part and not part.split("=")[0].lower().startswith(("igsh", "utm_", "img_index"))
        ]
        url = base + ("?" + "&".join(kept) if kept else "")
    return url


def is_supported_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def _ydl_options(dest_dir: Path) -> dict:
    options = {
        "outtmpl": str(dest_dir / "source.%(ext)s"),
        "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 3,
        "socket_timeout": 30,
        "restrictfilenames": True,
    }
    cookies = cookie_file()
    if cookies:
        options["cookiefile"] = cookies
    if settings.cookies_from_browser:
        options["cookiesfrombrowser"] = (settings.cookies_from_browser,)
    return options


def _first_entry(info: dict) -> dict:
    """Un carrusel devuelve una playlist: nos quedamos con el primer vídeo."""
    entries = info.get("entries")
    if not entries:
        return info
    for entry in entries:
        if entry and entry.get("duration"):
            return entry
    return entries[0] or info


def fetch(url: str, dest_dir: Path) -> SourceMedia:
    import yt_dlp

    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        with yt_dlp.YoutubeDL(_ydl_options(dest_dir)) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as exc:  # yt_dlp.utils.DownloadError y derivados
        raise DownloadError(_explain(exc)) from exc

    if info is None:
        raise DownloadError("Instagram no devolvió ningún contenido para esa URL.")

    entry = _first_entry(info)
    video_path = _locate_downloaded_file(entry, dest_dir)

    caption = (entry.get("description") or info.get("description") or "").strip()
    if not caption and not video_path:
        raise DownloadError("No se pudo obtener ni el vídeo ni el texto del post.")

    duration = entry.get("duration") or info.get("duration")
    if duration and duration > settings.max_video_seconds:
        raise DownloadError(
            f"El vídeo dura {int(duration)}s y el límite está en {settings.max_video_seconds}s."
        )

    return SourceMedia(
        video_path=video_path,
        caption=caption,
        title=(entry.get("title") or info.get("title") or "").strip(),
        author=(entry.get("uploader") or entry.get("channel") or info.get("uploader") or "").strip(),
        duration=duration,
        webpage_url=entry.get("webpage_url") or info.get("webpage_url") or url,
        thumbnail_url=entry.get("thumbnail") or info.get("thumbnail"),
    )


def _locate_downloaded_file(entry: dict, dest_dir: Path) -> Path | None:
    candidate = entry.get("requested_downloads", [{}])[0].get("filepath") if entry.get("requested_downloads") else None
    if candidate and Path(candidate).exists():
        return Path(candidate)
    if entry.get("filepath") and Path(entry["filepath"]).exists():
        return Path(entry["filepath"])
    media = sorted(
        (p for p in dest_dir.glob("source.*") if p.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov", ".m4v"}),
        key=lambda p: p.stat().st_size,
        reverse=True,
    )
    return media[0] if media else None


def _explain(exc: Exception) -> str:
    message = str(exc)
    lowered = message.lower()
    if "login required" in lowered or "rate-limit" in lowered or "empty media response" in lowered:
        return (
            "Instagram pide iniciar sesión para este post. Configura IG_COOKIES_FILE con "
            "las cookies de una sesión válida (ver docs/despliegue.md)."
        )
    if "unsupported url" in lowered:
        return "Esa URL no la reconoce yt-dlp. Comprueba que sea el enlace de un reel o post."
    if "private" in lowered:
        return "El post es privado y la cuenta configurada no tiene acceso."
    return f"No se pudo descargar el vídeo: {message.splitlines()[0][:300]}"


@lru_cache(maxsize=1)
def cookie_file() -> str | None:
    """Ruta al fichero de cookies, venga de disco o de una variable de entorno.

    En un contenedor sin disco propio no hay dónde dejar el fichero, así que
    IG_COOKIES_B64 permite pasarlo como variable (base64 del fichero Netscape).
    """
    if settings.cookies_file and Path(settings.cookies_file).is_file():
        return settings.cookies_file
    if settings.cookies_b64:
        target = settings.work_dir / "cookies_instagram.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_bytes(base64.b64decode(settings.cookies_b64))
        except (ValueError, binascii.Error) as exc:
            logger.error("IG_COOKIES_B64 no es base64 válido: %s", exc)
            return None
        return str(target)
    if settings.cookies_file:
        logger.warning("IG_COOKIES_FILE apunta a %s, que no existe.", settings.cookies_file)
    return None
