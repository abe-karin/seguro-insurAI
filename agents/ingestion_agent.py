"""
Agente de Ingestão — responsável por extrair texto de PDFs e imagens.
Suporta: pdfplumber (padrão), PyMuPDF, pytesseract (OCR para imagens).
"""
from __future__ import annotations
import io
import os
import shutil
import logging
from pathlib import Path
from typing import Union, Optional

logger = logging.getLogger(__name__)


# Caminhos comuns do Tesseract no Windows (ordem de prioridade)
_TESSERACT_WINDOWS_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    os.path.expandvars(r"%USERPROFILE%\AppData\Local\Tesseract-OCR\tesseract.exe"),
    os.path.expandvars(r"%ProgramW6432%\Tesseract-OCR\tesseract.exe"),
]


def _find_tesseract_binary() -> Optional[str]:
    """
    Localiza o binário do Tesseract — primeiro no PATH, depois em caminhos
    comuns do Windows, por fim na variável de ambiente TESSERACT_CMD.
    Retorna o caminho encontrado ou None.
    """
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
    Se existir uma pasta `storage/tessdata/` na raiz do projeto com arquivos
    .traineddata, aponta o TESSDATA_PREFIX pra lá — permite empacotar o pacote
    de idioma português (por.traineddata) junto com o projeto, sem exigir
    admin para gravar em C:\\Program Files\\Tesseract-OCR\\tessdata\\.
    """
    if os.getenv("TESSDATA_PREFIX"):
        return  # usuário já configurou manualmente, respeita

    project_tessdata = Path(__file__).resolve().parent.parent / "storage" / "tessdata"
    if project_tessdata.is_dir() and any(project_tessdata.glob("*.traineddata")):
        os.environ["TESSDATA_PREFIX"] = str(project_tessdata)
        logger.info(f"TESSDATA_PREFIX configurado: {project_tessdata}")


def _ensure_tesseract_available() -> None:
    """
    Configura `pytesseract.tesseract_cmd` se o binário for localizado,
    e aponta TESSDATA_PREFIX pra pasta local do projeto quando aplicável.
    Lança RuntimeError com mensagem amigável se o binário não existir.
    """
    import pytesseract

    _configure_tessdata_prefix()

    # Se já foi configurado anteriormente e o arquivo existe, nada a fazer
    current = getattr(pytesseract.pytesseract, "tesseract_cmd", None)
    if current and current != "tesseract" and Path(current).is_file():
        return

    binary = _find_tesseract_binary()
    if binary:
        pytesseract.pytesseract.tesseract_cmd = binary
        logger.info(f"Tesseract localizado em: {binary}")
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
        "  3. Se instalou em local não padrão, defina a variável de ambiente "
        "TESSERACT_CMD com o caminho completo do tesseract.exe."
    )


def extract_text_from_pdf_pdfplumber(path: Union[str, Path, bytes]) -> str:
    """Extrai texto de PDF usando pdfplumber."""
    import pdfplumber

    if isinstance(path, (str, Path)):
        with pdfplumber.open(path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
    else:
        with pdfplumber.open(io.BytesIO(path)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]

    return "\n\n".join(pages)


def extract_text_from_pdf_pymupdf(path: Union[str, Path, bytes]) -> str:
    """Extrai texto de PDF usando PyMuPDF (fitz) — melhor para PDFs complexos."""
    import fitz  # PyMuPDF

    if isinstance(path, bytes):
        doc = fitz.open(stream=path, filetype="pdf")
    else:
        doc = fitz.open(str(path))

    pages = []
    for page in doc:
        pages.append(page.get_text("text"))
    doc.close()
    return "\n\n".join(pages)


def extract_text_from_image_tesseract(path: Union[str, Path, bytes]) -> str:
    """Extrai texto de imagem via Tesseract OCR (PT-BR + EN)."""
    _ensure_tesseract_available()
    import pytesseract
    from PIL import Image

    if isinstance(path, bytes):
        img = Image.open(io.BytesIO(path))
    else:
        img = Image.open(path)

    try:
        return pytesseract.image_to_string(img, lang="por+eng")
    except pytesseract.TesseractError as e:
        # Mensagem típica quando falta o pacote de idioma português
        if "por" in str(e).lower() or "language" in str(e).lower():
            logger.warning(f"Idioma 'por' indisponível, tentando apenas inglês: {e}")
            return pytesseract.image_to_string(img, lang="eng")
        raise


def extract_text_from_pdf_as_images(path: Union[str, Path, bytes]) -> str:
    """
    Converte páginas de PDF em imagens e aplica OCR.
    Útil para PDFs digitalizados (sem texto embutido).
    """
    _ensure_tesseract_available()
    import fitz
    import pytesseract
    from PIL import Image

    if isinstance(path, bytes):
        doc = fitz.open(stream=path, filetype="pdf")
    else:
        doc = fitz.open(str(path))

    # Tenta por+eng; se o pacote 'por' não estiver instalado, cai para 'eng'
    lang = "por+eng"
    texts = []
    for page in doc:
        mat = fitz.Matrix(2.0, 2.0)  # 2x zoom para melhor OCR
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_bytes))
        try:
            texts.append(pytesseract.image_to_string(img, lang=lang))
        except pytesseract.TesseractError as e:
            if lang != "eng" and ("por" in str(e).lower() or "language" in str(e).lower()):
                logger.warning(f"Idioma 'por' indisponível, usando apenas inglês nas demais páginas: {e}")
                lang = "eng"
                texts.append(pytesseract.image_to_string(img, lang=lang))
            else:
                raise
    doc.close()
    return "\n\n".join(texts)


def ingest_document(file_bytes: bytes, filename: str, ocr_engine: str = "pdfplumber") -> str:
    """
    Ponto de entrada principal do agente de ingestão.
    
    Args:
        file_bytes: Conteúdo binário do arquivo
        filename: Nome do arquivo (usado para detectar tipo)
        ocr_engine: 'pdfplumber' | 'pymupdf' | 'tesseract'
    
    Returns:
        Texto extraído do documento.
    """
    ext = Path(filename).suffix.lower()
    text = ""

    try:
        if ext == ".pdf":
            if ocr_engine == "pymupdf":
                text = extract_text_from_pdf_pymupdf(file_bytes)
            elif ocr_engine == "tesseract":
                text = extract_text_from_pdf_as_images(file_bytes)
            else:
                # pdfplumber como padrão; se retornar vazio, tenta PyMuPDF
                text = extract_text_from_pdf_pdfplumber(file_bytes)
                if len(text.strip()) < 100:
                    logger.warning("pdfplumber retornou texto curto, tentando PyMuPDF...")
                    text = extract_text_from_pdf_pymupdf(file_bytes)
                if len(text.strip()) < 100:
                    # Fallback para OCR só se o Tesseract estiver disponível
                    if _find_tesseract_binary():
                        logger.warning("PDF parece ser imagem, aplicando OCR via Tesseract...")
                        text = extract_text_from_pdf_as_images(file_bytes)
                    else:
                        logger.warning(
                            "PDF parece ser digitalizado (sem texto embutido) e o Tesseract "
                            "não está instalado — não foi possível aplicar OCR."
                        )

        elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"):
            text = extract_text_from_image_tesseract(file_bytes)

        else:
            raise ValueError(f"Formato não suportado: {ext}")

    except Exception as e:
        logger.error(f"Erro na ingestão de '{filename}': {e}")
        raise

    logger.info(f"Ingestão concluída: '{filename}' → {len(text)} caracteres extraídos")
    return text
