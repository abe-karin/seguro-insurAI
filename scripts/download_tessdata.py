"""
Baixa os arquivos de idioma do Tesseract (por.traineddata, eng.traineddata)
para storage/tessdata/ do projeto.

Permite usar OCR em português sem precisar de permissão de administrador para
instalar o pacote de idioma em C:\\Program Files\\Tesseract-OCR\\tessdata\\.

Uso:
    python scripts/download_tessdata.py              # baixa por + eng
    python scripts/download_tessdata.py por eng spa  # baixa idiomas específicos
"""
from __future__ import annotations
import shutil
import sys
import urllib.request
from pathlib import Path

TESSDATA_URL = "https://github.com/tesseract-ocr/tessdata/raw/main/{lang}.traineddata"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TARGET_DIR = PROJECT_ROOT / "storage" / "tessdata"
LOCAL_TESSERACT_TESSDATA = Path(r"C:\Program Files\Tesseract-OCR\tessdata")


def download(lang: str) -> None:
    dest = TARGET_DIR / f"{lang}.traineddata"
    if dest.is_file():
        print(f"  [ok] {lang}: já existe ({dest.stat().st_size // 1024} KB)")
        return

    # Primeiro tenta copiar do Tesseract instalado localmente (mais rápido)
    local_source = LOCAL_TESSERACT_TESSDATA / f"{lang}.traineddata"
    if local_source.is_file():
        shutil.copy2(local_source, dest)
        print(f"  [copy] {lang}: copiado de {local_source} ({dest.stat().st_size // 1024} KB)")
        return

    url = TESSDATA_URL.format(lang=lang)
    print(f"  [get]  {lang}: baixando de {url} ...", end=" ", flush=True)
    try:
        urllib.request.urlretrieve(url, dest)
        print(f"OK ({dest.stat().st_size // 1024} KB)")
    except Exception as e:
        print(f"FALHOU: {e}")
        if dest.exists():
            dest.unlink()
        raise


def main() -> int:
    langs = sys.argv[1:] or ["por", "eng"]
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Destino: {TARGET_DIR}\n")
    for lang in langs:
        download(lang)
    print(f"\nPronto. Lembre-se de que o aplicativo detecta esta pasta automaticamente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
