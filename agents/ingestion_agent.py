"""
Agente de Ingestão — extrai o texto de PDFs e imagens, página por página.

Motores suportados: pdfplumber (padrão), PyMuPDF e Tesseract (OCR, para imagens e
PDFs digitalizados). O texto sai separado por página porque as etapas seguintes
precisam citar a página de origem de cada informação.
"""
from __future__ import annotations

import io
import logging
import os
import shutil
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

PageSource = Union[str, Path, bytes]

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp")

# Abaixo disso o documento é tratado como digitalizado (sem texto embutido).
MIN_TEXT_CHARS = 100

# Caminhos comuns do Tesseract no Windows (ordem de prioridade)
_TESSERACT_WINDOWS_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    os.path.expandvars(r"%USERPROFILE%\AppData\Local\Tesseract-OCR\tesseract.exe"),
    os.path.expandvars(r"%ProgramW6432%\Tesseract-OCR\tesseract.exe"),
]


# ─── Localização do Tesseract ────────────────────────────────────────────────

def _find_tesseract_binary() -> Optional[str]:
    """Procura o binário: TESSERACT_CMD, depois o PATH, depois os caminhos do Windows."""
    env_override = os.getenv("TESSERACT_CMD")
    if env_override and Path(env_override).is_file():
        return env_override

    in_path = shutil.which("tesseract")
    if in_path:
        return in_path

    for candidate in _TESSERACT_WINDOWS_PATHS:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def _configure_tessdata_prefix() -> None:
    """
    Aponta TESSDATA_PREFIX para `storage/tessdata/` quando ela existir, permitindo
    usar o pacote de idioma português sem gravar na instalação do Tesseract.
    """
    if os.getenv("TESSDATA_PREFIX"):
        return

    project_tessdata = Path(__file__).resolve().parent.parent / "storage" / "tessdata"
    if project_tessdata.is_dir() and any(project_tessdata.glob("*.traineddata")):
        os.environ["TESSDATA_PREFIX"] = str(project_tessdata)
        logger.info("TESSDATA_PREFIX configurado: %s", project_tessdata)


def _ensure_tesseract_available() -> None:
    """Configura o pytesseract ou falha com orientação clara de instalação."""
    import pytesseract

    _configure_tessdata_prefix()

    current = getattr(pytesseract.pytesseract, "tesseract_cmd", None)
    if current and current != "tesseract" and Path(current).is_file():
        return

    binary = _find_tesseract_binary()
    if binary:
        pytesseract.pytesseract.tesseract_cmd = binary
        logger.info("Tesseract localizado em: %s", binary)
        return

    raise RuntimeError(
        "Tesseract OCR não está instalado neste sistema (ou não foi encontrado "
        "no PATH nem nos caminhos padrão do Windows).\n\n"
        "Soluções:\n"
        "  1. Troque o Engine OCR na barra lateral para 'pdfplumber' ou 'pymupdf' "
        "(funciona se o PDF tiver texto embutido, não digitalizado).\n"
        "  2. Instale o Tesseract: winget install UB-Mannheim.TesseractOCR\n"
        "     (ou baixe em https://github.com/UB-Mannheim/tesseract/wiki e marque "
        "o idioma 'Portuguese' durante a instalação).\n"
        "  3. Se instalou em local não padrão, defina TESSERACT_CMD com o caminho "
        "completo do tesseract.exe."
    )


# ─── Extração por página ─────────────────────────────────────────────────────

def _open_fitz(source: PageSource):
    import pymupdf as fitz

    if isinstance(source, bytes):
        return fitz.open(stream=source, filetype="pdf")
    return fitz.open(str(source))


def pages_from_pdf_pdfplumber(source: PageSource) -> list[str]:
    """Texto de cada página via pdfplumber."""
    import pdfplumber

    handle = io.BytesIO(source) if isinstance(source, bytes) else source
    with pdfplumber.open(handle) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


def pages_from_pdf_pymupdf(source: PageSource) -> list[str]:
    """Texto de cada página via PyMuPDF — mais tolerante a layouts complexos."""
    doc = _open_fitz(source)
    try:
        return [page.get_text("text") for page in doc]
    finally:
        doc.close()


def _ocr_image(img, lang: str) -> tuple[str, str]:
    """Aplica OCR e cai para inglês se o pacote de português não estiver instalado."""
    import pytesseract

    try:
        return pytesseract.image_to_string(img, lang=lang), lang
    except pytesseract.TesseractError as exc:
        if lang != "eng" and ("por" in str(exc).lower() or "language" in str(exc).lower()):
            logger.warning("Idioma 'por' indisponível, usando apenas inglês: %s", exc)
            return pytesseract.image_to_string(img, lang="eng"), "eng"
        raise


def pages_from_image_tesseract(source: PageSource) -> list[str]:
    """OCR de uma imagem avulsa (uma única página)."""
    _ensure_tesseract_available()
    from PIL import Image

    img = Image.open(io.BytesIO(source)) if isinstance(source, bytes) else Image.open(source)
    text, _ = _ocr_image(img, "por+eng")
    return [text]


def pages_from_pdf_as_images(source: PageSource) -> list[str]:
    """Converte cada página em imagem (zoom 2x) e aplica OCR — para PDFs digitalizados."""
    _ensure_tesseract_available()
    import pymupdf as fitz
    from PIL import Image

    doc = _open_fitz(source)
    lang = "por+eng"
    texts: list[str] = []
    try:
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text, lang = _ocr_image(img, lang)
            texts.append(text)
    finally:
        doc.close()
    return texts


def _total_chars(pages: list[str]) -> int:
    return sum(len(p.strip()) for p in pages)


def _pdf_pages(file_bytes: bytes, ocr_engine: str) -> list[str]:
    if ocr_engine == "pymupdf":
        return pages_from_pdf_pymupdf(file_bytes)
    if ocr_engine == "tesseract":
        return pages_from_pdf_as_images(file_bytes)

    # pdfplumber é o padrão; se vier pouco texto, tenta PyMuPDF e por fim OCR.
    pages = pages_from_pdf_pdfplumber(file_bytes)
    if _total_chars(pages) < MIN_TEXT_CHARS:
        logger.warning("pdfplumber retornou pouco texto; tentando PyMuPDF...")
        pages = pages_from_pdf_pymupdf(file_bytes)
    if _total_chars(pages) < MIN_TEXT_CHARS:
        if _find_tesseract_binary():
            logger.warning("PDF parece digitalizado; aplicando OCR via Tesseract...")
            pages = pages_from_pdf_as_images(file_bytes)
        else:
            logger.warning(
                "PDF parece digitalizado (sem texto embutido) e o Tesseract não está "
                "instalado — não foi possível aplicar OCR."
            )
    return pages


def ingest_pages(file_bytes: bytes, filename: str, ocr_engine: str = "pdfplumber") -> list[str]:
    """
    Ponto de entrada do agente: devolve o texto do documento, uma string por página.

    Args:
        file_bytes: conteúdo binário do arquivo.
        filename: nome do arquivo (define o tipo pela extensão).
        ocr_engine: 'pdfplumber' | 'pymupdf' | 'tesseract'.
    """
    ext = Path(filename).suffix.lower()
    try:
        if ext == ".pdf":
            pages = _pdf_pages(file_bytes, ocr_engine)
        elif ext in IMAGE_EXTENSIONS:
            pages = pages_from_image_tesseract(file_bytes)
        else:
            raise ValueError(f"Formato não suportado: {ext or 'sem extensão'}")
    except Exception as exc:
        logger.error("Erro na ingestão de '%s': %s", filename, exc)
        raise

    logger.info("Ingestão concluída: '%s' → %d página(s), %d caracteres", filename, len(pages), _total_chars(pages))
    return pages


def ingest_document(file_bytes: bytes, filename: str, ocr_engine: str = "pdfplumber") -> str:
    """Versão em texto corrido de `ingest_pages` (páginas separadas por linha em branco)."""
    return "\n\n".join(ingest_pages(file_bytes, filename, ocr_engine))


def format_pages_for_llm(pages: list[str]) -> str:
    """Junta as páginas com marcadores `[[PÁGINA n]]`, que o LLM usa para citar a fonte."""
    return "\n\n".join(f"[[PÁGINA {n}]]\n{text.strip()}" for n, text in enumerate(pages, start=1))
