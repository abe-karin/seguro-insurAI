"""
View: Upload e processamento de apólice.
"""
from __future__ import annotations
import streamlit as st


def render_upload(provider: str, model: str, ocr_engine: str):
    st.subheader("📤 Enviar Apólice D&O")
    st.markdown(
        "Faça upload de uma apólice em **PDF** ou **imagem** (PNG, JPG, TIFF). "
        "O sistema irá extrair e estruturar as informações automaticamente."
    )

    uploaded_file = st.file_uploader(
        "Selecione o arquivo",
        type=["pdf", "png", "jpg", "jpeg", "tiff", "tif"],
        help="Formatos aceitos: PDF, PNG, JPG, TIFF",
    )

    col1, col2 = st.columns([2, 1])
    with col2:
        save_to_db = st.checkbox("Salvar no histórico", value=True)
        show_raw_text = st.checkbox("Mostrar texto bruto extraído", value=False)

    if uploaded_file and st.button("🔍 Processar Apólice", type="primary", use_container_width=True):
        _process_upload(uploaded_file, provider, model, ocr_engine, save_to_db, show_raw_text)


def _process_upload(uploaded_file, provider, model, ocr_engine, save_to_db, show_raw_text):
    from agents.ingestion_agent import ingest_document
    from agents.extraction_agent import extract_policy
    from storage.database import save_policy

    file_bytes = uploaded_file.read()
    filename = uploaded_file.name

    # Etapa 1: Ingestão
    with st.status("🔍 Etapa 1/2 — Extraindo texto do documento...", expanded=True) as status:
        try:
            text = ingest_document(file_bytes, filename, ocr_engine=ocr_engine)
            chars = len(text)
            st.write(f"✅ Texto extraído: **{chars:,} caracteres**")

            if chars < 50:
                st.warning("⚠️ Pouco texto extraído. O PDF pode ser digitalizado — tente o engine 'tesseract'.")

            status.update(label="✅ Texto extraído com sucesso", state="complete")
        except Exception as e:
            st.error(f"❌ Falha na extração de texto: {e}")
            status.update(label="❌ Falha na extração", state="error")
            return

    if show_raw_text:
        with st.expander("📄 Texto bruto extraído"):
            st.text_area("Conteúdo", text[:5000] + ("..." if len(text) > 5000 else ""), height=300)

    # Etapa 2: Extração LLM
    with st.status(f"🤖 Etapa 2/2 — Analisando com {provider}/{model}...", expanded=True) as status:
        try:
            apolice = extract_policy(text, filename=filename, provider=provider, model=model)
            st.write(f"✅ Coberturas identificadas: **{len(apolice.coberturas)}**")
            st.write(f"✅ Exclusões identificadas: **{len(apolice.exclusoes)}**")
            st.write(f"✅ Cláusulas especiais: **{len(apolice.clausulas_especiais)}**")
            status.update(label="✅ Extração LLM concluída", state="complete")
        except Exception as e:
            st.error(f"❌ Falha na extração LLM: {e}")
            status.update(label="❌ Falha na extração LLM", state="error")
            return

    # Salva no BD
    if save_to_db:
        policy_id = save_policy(apolice)
        st.success(f"✅ Apólice salva no histórico com ID **#{policy_id}**")

    # Exibe resultado
    st.markdown("---")
    _display_policy(apolice)

    # Botão de download
    from agents.report_agent import generate_policy_pdf, generate_policy_markdown
    col_pdf, col_md = st.columns(2)
    with col_pdf:
        pdf_bytes = generate_policy_pdf(apolice)
        st.download_button(
            "⬇️ Baixar Relatório PDF",
            data=pdf_bytes,
            file_name=f"relatorio_{filename.rsplit('.', 1)[0]}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    with col_md:
        md_text = generate_policy_markdown(apolice)
        st.download_button(
            "⬇️ Baixar Relatório Markdown",
            data=md_text.encode("utf-8"),
            file_name=f"relatorio_{filename.rsplit('.', 1)[0]}.md",
            mime="text/markdown",
            use_container_width=True,
        )


def _display_policy(apolice):
    from models.schemas import ApoliceExtraida
    da = apolice.dados_apolice
    seg = apolice.segurado

    st.subheader(f"📋 {apolice.nome_arquivo}")

    # Métricas principais
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Seguradora", da.seguradora or "N/D")
    col2.metric("Limite Global", da.limite_global or "N/D")
    col3.metric("Prêmio", da.premio or "N/D")
    col4.metric("Base de Acionamento", da.base_acionamento or "N/D")

    tab1, tab2, tab3, tab4 = st.tabs(["📄 Dados Gerais", "🛡️ Coberturas", "🚫 Exclusões", "📝 Cláusulas Especiais"])

    with tab1:
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Dados da Apólice**")
            st.json({
                "Número": da.numero_apolice or "N/D",
                "Seguradora": da.seguradora or "N/D",
                "Vigência Início": da.vigencia_inicio or "N/D",
                "Vigência Fim": da.vigencia_fim or "N/D",
                "Base de Acionamento": da.base_acionamento or "N/D",
            })
        with col_b:
            st.markdown("**Dados do Segurado**")
            st.json({
                "Nome/Razão Social": seg.nome_segurado or "N/D",
                "CNPJ": seg.cnpj or "N/D",
                "Setor": seg.setor or "N/D",
            })

    with tab2:
        if apolice.coberturas:
            for i, cob in enumerate(apolice.coberturas):
                with st.expander(f"**{cob.nome}**", expanded=(i == 0)):
                    st.markdown(cob.descricao)
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Limite", cob.limite or "N/D")
                    c2.metric("Franquia", cob.franquia or "N/D")
                    c3.metric("Retroatividade", cob.retroatividade or "N/D")
        else:
            st.info("Nenhuma cobertura identificada.")

    with tab3:
        if apolice.exclusoes:
            import pandas as pd
            df = pd.DataFrame([
                {"Categoria": e.categoria, "Descrição": e.descricao}
                for e in apolice.exclusoes
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma exclusão identificada.")

    with tab4:
        if apolice.clausulas_especiais:
            for cls in apolice.clausulas_especiais:
                st.markdown(f"- {cls}")
        else:
            st.info("Nenhuma cláusula especial identificada.")

        if apolice.observacoes:
            st.markdown("**Observações:**")
            st.markdown(apolice.observacoes)
