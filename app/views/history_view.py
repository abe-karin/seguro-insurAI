"""
View: Histórico de apólices e comparações.
"""
from __future__ import annotations
import streamlit as st


def render_history():
    st.subheader("📁 Histórico de Análises")

    from storage.database import list_policies, list_comparisons, load_comparison
    from agents.report_agent import generate_comparison_pdf, generate_comparison_markdown

    tab_policies, tab_comparisons = st.tabs(["🗂️ Apólices Salvas", "📊 Comparações Salvas"])

    with tab_policies:
        policies = list_policies()
        if policies:
            import pandas as pd
            df = pd.DataFrame(policies)[["id", "filename", "seguradora", "segurado", "vigencia", "created_at"]]
            df.columns = ["ID", "Arquivo", "Seguradora", "Segurado", "Vigência", "Processado em"]
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption(f"Total: {len(policies)} apólice(s)")
        else:
            st.info("Nenhuma apólice processada.")

    with tab_comparisons:
        comparisons = list_comparisons()
        if comparisons:
            import pandas as pd
            df = pd.DataFrame(comparisons)
            df.columns = ["ID", "Apólice A", "Apólice B", "Realizado em"]
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption(f"Total: {len(comparisons)} comparação(ões)")

            st.markdown("---")
            selected_cmp_id = st.selectbox(
                "Visualizar comparação:",
                options=[c["id"] for c in comparisons],
                format_func=lambda cid: next(
                    (f"#{c['id']} — {c['apolice_a']} × {c['apolice_b']}" for c in comparisons if c["id"] == cid),
                    str(cid)
                ),
            )
            if selected_cmp_id and st.button("📊 Abrir Comparação", use_container_width=True):
                rel = load_comparison(selected_cmp_id)
                if rel:
                    from app.views.comparison_view import _display_comparison
                    _display_comparison(rel)
        else:
            st.info("Nenhuma comparação realizada.")
