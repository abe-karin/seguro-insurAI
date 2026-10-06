"""Tela de envio: recebe um ou mais documentos e executa ingestão + extração."""
from __future__ import annotations

import streamlit as st

from agents.extraction_agent import extract_policy
from agents.ingestion_agent import ingest_pages
from agents.llm_client import LLMError
from app.views.components import display_policy, policy_downloads
from storage.database import save_policy


def render_upload(provider: str, model: str, ocr_engine: str) -> None:
    st.subheader("📤 Enviar apólices D&O")
    st.markdown(
        "Envie apólices ou condições gerais em **PDF** ou **imagem** (PNG, JPG, TIFF). "
        "O sistema extrai o texto, estrutura a ficha técnica D&O e cita a página de cada informação."
    )

    arquivos = st.file_uploader(
        "Selecione um ou mais arquivos",
        type=["pdf", "png", "jpg", "jpeg", "tiff", "tif"],
        accept_multiple_files=True,
        help="Formatos aceitos: PDF, PNG, JPG, TIFF",
    )

    col1, col2 = st.columns(2)
    salvar = col1.checkbox("Salvar no histórico", value=True)
    mostrar_texto = col2.checkbox("Mostrar texto extraído", value=False)

    if arquivos and st.button("🔍 Processar", type="primary", width="stretch"):
        for indice, arquivo in enumerate(arquivos):
            st.markdown("---")
            _processar(arquivo, indice, provider, model, ocr_engine, salvar, mostrar_texto)


def _processar(arquivo, indice: int, provider: str, model: str, ocr_engine: str, salvar: bool, mostrar_texto: bool) -> None:
    nome = arquivo.name
    conteudo = arquivo.read()

    with st.status(f"📄 {nome} — lendo o documento...", expanded=True) as status:
        try:
            paginas = ingest_pages(conteudo, nome, ocr_engine=ocr_engine)
        except Exception as exc:  # noqa: BLE001 — mostramos o erro ao usuário
            status.update(label=f"❌ {nome} — falha na leitura", state="error")
            st.error(f"Não foi possível ler o documento: {exc}")
            return

        caracteres = sum(len(p) for p in paginas)
        st.write(f"✅ {len(paginas)} página(s), **{caracteres:,}** caracteres extraídos")
        if caracteres < 200:
            st.warning("Pouco texto extraído: o arquivo pode ser digitalizado. Tente o engine `tesseract`.")
        status.update(label=f"✅ {nome} — texto extraído", state="complete")

    if mostrar_texto:
        with st.expander("📄 Texto extraído (primeiras páginas)"):
            st.text_area("Conteúdo", "\n\n".join(paginas[:3])[:6000], height=260, key=f"raw_{indice}_{nome}")

    with st.status(f"🤖 {nome} — analisando com {provider}/{model}...", expanded=True) as status:
        try:
            apolice = extract_policy(paginas, filename=nome, provider=provider, model=model, progress=st.write)
        except LLMError as exc:
            status.update(label=f"❌ {nome} — falha na análise", state="error")
            st.error(f"O modelo não conseguiu analisar o documento: {exc}")
            return
        st.write(
            f"✅ {len(apolice.coberturas)} coberturas · {len(apolice.exclusoes)} exclusões · "
            f"{len(apolice.clausulas_especiais)} cláusulas especiais"
        )
        status.update(label=f"✅ {nome} — análise concluída", state="complete")

    if salvar:
        st.success(f"Apólice salva no histórico com o ID **#{save_policy(apolice)}**")

    display_policy(apolice, key=f"up_{indice}")
    policy_downloads(apolice, f"relatorio_{nome.rsplit('.', 1)[0]}", key=f"up_{indice}")
