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

    serverless: bool
    storage_backend: str  # "local" | "gcs"
    gcs_bucket: str
    gcs_prefix: str

    api_key: str
    app_password: str
    session_secret: str

    llm_provider: str  # "ollama" | "gemini" | "anthropic"

    ollama_host: str
    ollama_model: str
    ollama_timeout: int

    gemini_api_key: str
    gemini_model: str

    anthropic_model: str
    max_tokens: int
    effort: str
    refusal_fallback: bool

    language: str
    frame_count: int
    frame_max_dim: int

    transcriber: str  # "auto" | "whisper" | "none"
    whisper_model: str
    whisper_compute_type: str

    send_video: bool
    video_max_bytes: int

    cookies_file: str | None
    cookies_b64: str
    cookies_from_browser: str | None
    max_video_seconds: int

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
            # Cloud Run define K_SERVICE. Ahí no hay CPU asignada después de
            # responder, así que el trabajo no puede quedarse en segundo plano.
            serverless=_env_bool("SERVERLESS", bool(os.getenv("K_SERVICE"))),
            storage_backend=os.getenv("STORAGE_BACKEND", "local").strip().lower(),
            gcs_bucket=os.getenv("GCS_BUCKET", "").strip(),
            gcs_prefix=os.getenv("GCS_PREFIX", "recetario").strip(),
            api_key=api_key,
            app_password=os.getenv("APP_PASSWORD", "").strip() or api_key,
            session_secret=os.getenv("SESSION_SECRET", "").strip() or api_key,
            llm_provider=os.getenv("LLM_PROVIDER", "gemini").strip().lower(),
            ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/"),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5vl:7b"),
            ollama_timeout=_env_int("OLLAMA_TIMEOUT", 900),
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
            anthropic_model=os.getenv("CLAUDE_MODEL", "claude-opus-5"),
            max_tokens=_env_int("CLAUDE_MAX_TOKENS", 16000),
            effort=os.getenv("CLAUDE_EFFORT", "high"),
            refusal_fallback=_env_bool("CLAUDE_REFUSAL_FALLBACK", True),
            language=os.getenv("RECIPE_LANGUAGE", "español"),
            frame_count=_env_int("FRAME_COUNT", 14),
            frame_max_dim=_env_int("FRAME_MAX_DIM", 1024),
            transcriber=os.getenv("TRANSCRIBER", "auto").strip().lower(),
            whisper_model=os.getenv("WHISPER_MODEL", "small"),
            whisper_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
            send_video=_env_bool("SEND_VIDEO", True),
            # Gemini admite hasta 20 MB por petición contando la codificación
            # base64; dejamos margen para el texto del prompt.
            video_max_bytes=_env_int("VIDEO_MAX_BYTES", 13 * 1024 * 1024),
            cookies_file=os.getenv("IG_COOKIES_FILE", "").strip() or None,
            cookies_b64=os.getenv("IG_COOKIES_B64", "").strip(),
            cookies_from_browser=os.getenv("IG_COOKIES_FROM_BROWSER", "").strip() or None,
            max_video_seconds=_env_int("MAX_VIDEO_SECONDS", 900),
        )

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.work_dir):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings.from_env()
