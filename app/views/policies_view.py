"""
View: Lista de apólices extraídas.
"""
from __future__ import annotations
import streamlit as st


def render_policies():
    st.subheader("📋 Apólices Extraídas")

    from storage.database import list_policies, load_policy, delete_policy

    policies = list_policies()

    if not policies:
        st.info("Nenhuma apólice processada ainda. Vá até a aba **Enviar Apólice** para começar.")
        return

    st.markdown(f"**{len(policies)} apólice(s) no histórico**")

    # Tabela resumida
    import pandas as pd
    df = pd.DataFrame(policies)
    df_display = df[["id", "filename", "seguradora", "numero_apolice", "segurado", "vigencia", "limite_global", "created_at"]]
    df_display.columns = ["ID", "Arquivo", "Seguradora", "Nº Apólice", "Segurado", "Vigência", "Limite Global", "Processado em"]
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("🔎 Detalhes de uma Apólice")

    selected_id = st.selectbox(
        "Selecione uma apólice para visualizar:",
        options=[p["id"] for p in policies],
        format_func=lambda pid: next(
            (f"#{p['id']} — {p['filename']} ({p['seguradora']})" for p in policies if p["id"] == pid),
            str(pid)
        ),
    )

    if selected_id:
        apolice = load_policy(selected_id)
        if apolice:
            from app.views.upload_view import _display_policy
            _display_policy(apolice)

            col_del, col_pdf, col_md = st.columns(3)
            with col_pdf:
                from agents.report_agent import generate_policy_pdf
                pdf_bytes = generate_policy_pdf(apolice)
                st.download_button(
                    "⬇️ PDF",
                    data=pdf_bytes,
                    file_name=f"apolice_{selected_id}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            with col_md:
                from agents.report_agent import generate_policy_markdown
                md_text = generate_policy_markdown(apolice)
                st.download_button(
                    "⬇️ Markdown",
                    data=md_text.encode("utf-8"),
                    file_name=f"apolice_{selected_id}.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
            with col_del:
                if st.button("🗑️ Excluir", type="secondary", use_container_width=True):
                    delete_policy(selected_id)
                    st.success("Apólice excluída.")
                    st.rerun()
