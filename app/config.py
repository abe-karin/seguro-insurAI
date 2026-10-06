"""Configurações centralizadas, lidas de variáveis de ambiente."""
from __future__ import annotations

import os

PROVIDERS = ("google", "openai", "anthropic")

# Modelo padrão de cada provedor. Podem ser sobrescritos por LLM_MODEL no .env
# ou pelo campo "Modelo" da barra lateral.
DEFAULT_MODELS = {
    "google": "gemini-flash-lite-latest",
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-5",
}

API_KEY_VARS = {
    "google": "GOOGLE_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}

OCR_ENGINES = ("pdfplumber", "pymupdf", "tesseract")


def default_provider() -> str:
    """Provedor padrão: o definido em LLM_PROVIDER ou o primeiro que tiver chave."""
    configured = os.getenv("LLM_PROVIDER", "").lower()
    if configured in PROVIDERS:
        return configured
    for provider in PROVIDERS:
        if os.getenv(API_KEY_VARS[provider]):
            return provider
    return "google"


def default_model(provider: str) -> str:
    return os.getenv("LLM_MODEL") or DEFAULT_MODELS.get(provider, DEFAULT_MODELS["google"])


def get_llm_config() -> tuple[str, str]:
    provider = default_provider()
    return provider, default_model(provider)


def get_ocr_engine() -> str:
    engine = os.getenv("OCR_ENGINE", "pdfplumber")
    return engine if engine in OCR_ENGINES else "pdfplumber"


def api_key_var(provider: str) -> str:
    return API_KEY_VARS.get(provider, "GOOGLE_API_KEY")
