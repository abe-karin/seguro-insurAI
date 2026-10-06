"""
Processa PDFs/imagens de apólices em lote, sem abrir a interface.

Executa o mesmo pipeline do app (ingestão → extração → persistência) e, com
--comparar, gera também o relatório comparativo entre todas as apólices processadas.

Uso:
    python scripts/processar_pdfs.py apolices/*.pdf
    python scripts/processar_pdfs.py a.pdf b.pdf --comparar --saida Projeto_Final_Artefatos/exemplos
    python scripts/processar_pdfs.py a.pdf --provider openai --model gpt-4o
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from agents.comparison_agent import comparar_apolices
from agents.extraction_agent import extract_policy, qualidade_ancoragem
from agents.ingestion_agent import ingest_pages
from agents.llm_client import LLMError
from agents.report_agent import (
    generate_comparison_markdown,
    generate_comparison_pdf,
    generate_policy_markdown,
    generate_policy_pdf,
)
from app.config import PROVIDERS, default_model, default_provider, get_ocr_engine
from storage.database import save_comparison, save_policy


def main() -> int:
    parser = argparse.ArgumentParser(description="Processa apólices D&O em lote.")
    parser.add_argument("arquivos", nargs="+", type=Path, help="PDFs ou imagens das apólices")
    parser.add_argument("--provider", choices=PROVIDERS, default=default_provider())
    parser.add_argument("--model", default=None, help="Modelo do provedor (padrão do .env/config)")
    parser.add_argument("--ocr", choices=("pdfplumber", "pymupdf", "tesseract"), default=get_ocr_engine())
    parser.add_argument("--comparar", action="store_true", help="Compara todas as apólices processadas")
    parser.add_argument("--sem-llm", action="store_true", help="Comparação determinística (sem LLM)")
    parser.add_argument("--saida", type=Path, default=None, help="Pasta para gravar os relatórios (PDF e Markdown)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    for ruidosa in ("httpx", "httpcore", "google_genai", "pdfminer", "pdfplumber", "PIL", "urllib3"):
        logging.getLogger(ruidosa).setLevel(logging.WARNING)

    modelo = args.model or default_model(args.provider)
    if args.saida:
        args.saida.mkdir(parents=True, exist_ok=True)

    apolices, ids = [], []
    for caminho in args.arquivos:
        if not caminho.is_file():
            print(f"[ERRO] Arquivo não encontrado: {caminho}")
            return 1
        print(f"\n▶ {caminho.name}")
        inicio = time.time()
        paginas = ingest_pages(caminho.read_bytes(), caminho.name, args.ocr)
        try:
            apolice = extract_policy(paginas, filename=caminho.name, provider=args.provider, model=modelo, progress=print)
        except LLMError as exc:
            print(f"[ERRO] {caminho.name}: {exc}")
            return 1
        ancoragem = qualidade_ancoragem(apolice)
        ids.append(save_policy(apolice))
        apolices.append(apolice)
        print(
            f"  ✔ {apolice.dados_apolice.seguradora or 'seguradora n/d'} · {len(paginas)} págs · "
            f"{len(apolice.coberturas)} coberturas · {len(apolice.exclusoes)} exclusões · "
            f"fontes verificadas {ancoragem['verificadas']}/{ancoragem['total']} · {time.time() - inicio:.0f}s"
        )
        if args.saida:
            (args.saida / f"{caminho.stem}.md").write_text(generate_policy_markdown(apolice), encoding="utf-8")
            (args.saida / f"{caminho.stem}.pdf").write_bytes(generate_policy_pdf(apolice))

    if args.comparar and len(apolices) >= 2:
        print("\n▶ Comparando apólices...")
        relatorio = comparar_apolices(apolices, provider=args.provider, model=modelo, use_llm=not args.sem_llm)
        save_comparison(relatorio, ids)
        print(f"  ✔ {len(relatorio.diferencas)} divergências · análise: {relatorio.modo}")
        print(f"\n{relatorio.resumo_executivo}\n")
        if args.saida:
            (args.saida / "comparativo.md").write_text(generate_comparison_markdown(relatorio), encoding="utf-8")
            (args.saida / "comparativo.pdf").write_bytes(generate_comparison_pdf(relatorio))
            print(f"Relatórios gravados em {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
