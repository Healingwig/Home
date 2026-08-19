"""Configuración leída del entorno."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

# Categorías de supermercado que usamos tanto en el prompt como en la lista de
# la compra. El orden es el del recorrido típico por el super.
GROCERY_CATEGORIES = [
    "frutas y verduras",
    "carnicería",
    "pescadería",
    "lácteos y huevos",
    "panadería",
    "despensa",
    "especias y condimentos",
    "congelados",
    "bebidas",
    "otros",
]


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on", "si", "sí"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    api_key: str
    app_password: str
    session_secret: str

    model: str
    max_tokens: int
    effort: str
    refusal_fallback: bool

    language: str
    frame_count: int
    frame_max_dim: int

    transcriber: str  # "auto" | "whisper" | "none"
    whisper_model: str
    whisper_compute_type: str

    cookies_file: str | None
    cookies_from_browser: str | None
    keep_video: bool
    max_video_seconds: int

    @property
    def db_path(self) -> Path:
        return self.data_dir / "recetas.sqlite3"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def work_dir(self) -> Path:
        return self.data_dir / "work"

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("DATA_DIR", "./data")).expanduser().resolve()
        api_key = os.getenv("API_KEY", "").strip()
        if not api_key:
            # Sin clave la app quedaría abierta a Internet; generamos una
            # efímera y la registramos al arrancar para que no pase inadvertido.
            api_key = secrets.token_urlsafe(24)
        return cls(
            data_dir=data_dir,
            api_key=api_key,
            app_password=os.getenv("APP_PASSWORD", "").strip() or api_key,
            session_secret=os.getenv("SESSION_SECRET", "").strip() or api_key,
            model=os.getenv("CLAUDE_MODEL", "claude-opus-5"),
            max_tokens=_env_int("CLAUDE_MAX_TOKENS", 16000),
            effort=os.getenv("CLAUDE_EFFORT", "high"),
            refusal_fallback=_env_bool("CLAUDE_REFUSAL_FALLBACK", True),
            language=os.getenv("RECIPE_LANGUAGE", "español"),
            frame_count=_env_int("FRAME_COUNT", 14),
            frame_max_dim=_env_int("FRAME_MAX_DIM", 1024),
            transcriber=os.getenv("TRANSCRIBER", "auto").strip().lower(),
            whisper_model=os.getenv("WHISPER_MODEL", "small"),
            whisper_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
            cookies_file=os.getenv("IG_COOKIES_FILE", "").strip() or None,
            cookies_from_browser=os.getenv("IG_COOKIES_FROM_BROWSER", "").strip() or None,
            keep_video=_env_bool("KEEP_VIDEO", False),
            max_video_seconds=_env_int("MAX_VIDEO_SECONDS", 900),
        )

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.media_dir, self.work_dir):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings.from_env()
