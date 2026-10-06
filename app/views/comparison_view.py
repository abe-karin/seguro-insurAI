"""
View: Comparação entre duas apólices.
"""
from __future__ import annotations
import streamlit as st


def render_comparison(provider: str, model: str):
    st.subheader("⚖️ Comparar Apólices D&O")
    st.markdown(
        "Selecione duas apólices já processadas para comparar suas coberturas, "
        "exclusões, limites e condições gerais."
    )

    from storage.database import list_policies, load_policy, save_comparison
    from agents.comparison_agent import compare_policies

    policies = list_policies()

    if len(policies) < 2:
        st.warning("⚠️ É necessário ter **pelo menos 2 apólices** processadas para comparar. "
                   "Vá até a aba **Enviar Apólice**.")
        return

    options = {
        f"#{p['id']} — {p['filename']} ({p['seguradora']})": p["id"]
        for p in policies
    }

    col1, col2 = st.columns(2)
    with col1:
        label_a = st.selectbox("📄 Apólice A", options=list(options.keys()), key="cmp_a")
    with col2:
        remaining = [k for k in options.keys() if k != label_a]
        label_b = st.selectbox("📄 Apólice B", options=remaining, key="cmp_b")

    id_a = options[label_a]
    id_b = options[label_b]

    use_llm = st.checkbox(
        "Usar análise LLM (requer chave de API configurada)",
        value=True,
        help="Desmarcado: usa comparação determinística sem custo de API"
    )

    if st.button("⚖️ Comparar Apólices", type="primary", use_container_width=True):
        apolice_a = load_policy(id_a)
        apolice_b = load_policy(id_b)

        if not apolice_a or not apolice_b:
            st.error("Não foi possível carregar as apólices selecionadas.")
            return

        with st.spinner(f"Comparando via {provider}/{model}..."):
            try:
                relatorio = compare_policies(
                    apolice_a, apolice_b,
                    provider=provider,
                    model=model,
                    use_llm=use_llm,
                )
                cmp_id = save_comparison(relatorio, policy_a_id=id_a, policy_b_id=id_b)
                st.success(f"✅ Comparação concluída (salva como #{cmp_id})")
                _display_comparison(relatorio)
            except Exception as e:
                st.error(f"❌ Falha na comparação: {e}")


def _display_comparison(relatorio):
    from models.schemas import RelatorioComparativo

    st.markdown("---")
    st.subheader(f"📊 Resultado: {relatorio.apolice_a}  ×  {relatorio.apolice_b}")

    # Métricas de diferenças
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Diffs Cadastrais", len(relatorio.diferencas_cadastrais))
    c2.metric("Diffs Coberturas", len(relatorio.diferencas_coberturas))
    c3.metric("Diffs Exclusões", len(relatorio.diferencas_exclusoes))
    c4.metric("Diffs Limites", len(relatorio.diferencas_limites))

    # Resumo executivo
    with st.expander("📝 Resumo Executivo", expanded=True):
        st.markdown(relatorio.resumo_executivo)

    with st.expander("💡 Recomendação Técnica", expanded=True):
        st.markdown(relatorio.recomendacao)

    # Tabs de diferenças
    tab1, tab2, tab3, tab4 = st.tabs([
        "📑 Cadastrais",
        "🛡️ Coberturas",
        "🚫 Exclusões",
        "💰 Limites",
    ])

    def render_diff_table(diffs, tab):
        with tab:
            if not diffs:
                st.info("Nenhuma diferença identificada nesta categoria.")
                return
            import pandas as pd
            rows = []
            for d in diffs:
                badge = {"alta": "🔴 Alta", "media": "🟡 Média", "baixa": "🟢 Baixa"}.get(d.relevancia, d.relevancia)
                rows.append({
                    "Campo": d.campo,
                    "Apólice A": d.valor_a or "N/D",
                    "Apólice B": d.valor_b or "N/D",
                    "Relevância": badge,
                    "Comentário": d.comentario,
                })
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

    render_diff_table(relatorio.diferencas_cadastrais, tab1)
    render_diff_table(relatorio.diferencas_coberturas, tab2)
    render_diff_table(relatorio.diferencas_exclusoes, tab3)
    render_diff_table(relatorio.diferencas_limites, tab4)

    # Downloads
    st.markdown("---")
    col_pdf, col_md = st.columns(2)
    from agents.report_agent import generate_comparison_pdf, generate_comparison_markdown
    with col_pdf:
        pdf_bytes = generate_comparison_pdf(relatorio)
        st.download_button(
            "⬇️ Baixar Comparativo PDF",
            data=pdf_bytes,
            file_name="comparativo_do.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    with col_md:
        md_text = generate_comparison_markdown(relatorio)
        st.download_button(
            "⬇️ Baixar Comparativo Markdown",
            data=md_text.encode("utf-8"),
            file_name="comparativo_do.md",
            mime="text/markdown",
            use_container_width=True,
        )
