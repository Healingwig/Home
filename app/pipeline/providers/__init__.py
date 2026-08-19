"""Selección del backend que genera la receta."""

from __future__ import annotations

from app.config import settings
from app.pipeline.providers.base import Part, Provider, ProviderError

_BACKENDS = {"ollama", "gemini", "anthropic"}


def get_provider(name: str | None = None) -> Provider:
    backend = (name or settings.llm_provider).strip().lower()
    if backend not in _BACKENDS:
        raise ProviderError(
            f"LLM_PROVIDER='{backend}' no existe. Opciones: {', '.join(sorted(_BACKENDS))}."
        )

    if backend == "ollama":
        from app.pipeline.providers.ollama_provider import OllamaProvider

        return OllamaProvider()
    if backend == "gemini":
        from app.pipeline.providers.gemini_provider import GeminiProvider

        return GeminiProvider()

    from app.pipeline.providers.anthropic_provider import AnthropicProvider

    return AnthropicProvider()


def check_provider(name: str | None = None) -> tuple[bool, str]:
    """(¿listo?, mensaje) del backend configurado, para el arranque y /healthz."""
    backend = (name or settings.llm_provider).strip().lower()
    if backend == "ollama":
        from app.pipeline.providers.ollama_provider import check_available
    elif backend == "gemini":
        from app.pipeline.providers.gemini_provider import check_available
    elif backend == "anthropic":
        from app.pipeline.providers.anthropic_provider import check_available
    else:
        return False, f"LLM_PROVIDER='{backend}' no existe."
    return check_available()


__all__ = ["Part", "Provider", "ProviderError", "get_provider", "check_provider"]
