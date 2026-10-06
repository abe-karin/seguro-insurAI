"""Configurações centralizadas lidas de variáveis de ambiente."""
import os


def get_llm_config() -> tuple[str, str]:
    provider = os.getenv("LLM_PROVIDER", "openai")
    model = os.getenv("LLM_MODEL", "gpt-4o")
    return provider, model


def get_ocr_engine() -> str:
    return os.getenv("OCR_ENGINE", "pdfplumber")
