"""Histórico de apólices e comparações realizadas."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.views.components import display_comparison
from storage.database import list_comparisons, list_policies, load_comparison


def render_history() -> None:
    st.subheader("📁 Histórico de análises")
    aba_apolices, aba_comparacoes = st.tabs(["🗂️ Apólices salvas", "📊 Comparações salvas"])

    with aba_apolices:
        policies = list_policies()
        if policies:
            df = pd.DataFrame(policies)[["id", "filename", "seguradora", "segurado", "total_paginas", "created_at"]]
            df.columns = ["ID", "Arquivo", "Seguradora", "Segurado", "Páginas", "Processado em"]
            st.dataframe(df, width="stretch", hide_index=True)
            st.caption(f"Total: {len(policies)} apólice(s)")
        else:
            st.info("Nenhuma apólice processada.")

    with aba_comparacoes:
        comparacoes = list_comparisons()
        if not comparacoes:
            st.info("Nenhuma comparação realizada.")
            return

        df = pd.DataFrame(comparacoes)[["id", "titulo", "created_at"]]
        df.columns = ["ID", "Apólices comparadas", "Realizado em"]
        st.dataframe(df, width="stretch", hide_index=True)
        st.caption(f"Total: {len(comparacoes)} comparação(ões)")

        escolhida = st.selectbox(
            "Visualizar comparação:",
            options=[c["id"] for c in comparacoes],
            format_func=lambda cid: next((f"#{c['id']} — {c['titulo']}" for c in comparacoes if c["id"] == cid), str(cid)),
        )
        relatorio = load_comparison(escolhida)
        if relatorio:
            st.markdown("---")
            display_comparison(relatorio, key=f"hist_{escolhida}")
