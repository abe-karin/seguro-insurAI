"""Tela com as apólices já extraídas, detalhes e conferência das fontes."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.views.components import display_policy, policy_downloads
from models.schemas import rotulo_topico
from storage.database import delete_policy, list_policies, load_pages, load_policy


def render_policies() -> None:
    st.subheader("📋 Apólices extraídas")

    policies = list_policies()
    if not policies:
        st.info("Nenhuma apólice processada ainda. Use a aba **Enviar apólices** para começar.")
        return

    st.markdown(f"**{len(policies)} apólice(s) no histórico**")
    df = pd.DataFrame(policies)[["id", "filename", "seguradora", "tipo_documento", "total_paginas", "created_at"]]
    df.columns = ["ID", "Arquivo", "Seguradora", "Tipo", "Páginas", "Processado em"]
    st.dataframe(df, width="stretch", hide_index=True)

    st.markdown("---")
    selecionado = st.selectbox(
        "Selecione uma apólice para ver os detalhes:",
        options=[p["id"] for p in policies],
        format_func=lambda pid: next(
            (f"#{p['id']} — {p['seguradora']} · {p['filename']}" for p in policies if p["id"] == pid), str(pid)
        ),
    )
    apolice = load_policy(selecionado)
    if not apolice:
        return

    display_policy(apolice, key=f"pol_{selecionado}")
    _conferir_fonte(selecionado, apolice)

    colunas = st.columns([2, 1])
    with colunas[0]:
        policy_downloads(apolice, f"apolice_{selecionado}", key=f"pol_{selecionado}")
    with colunas[1]:
        if st.button("🗑️ Excluir apólice", type="secondary", width="stretch"):
            delete_policy(selecionado)
            st.success("Apólice excluída.")
            st.rerun()


def _conferir_fonte(policy_id: int, apolice) -> None:
    """Mostra o texto da página citada por um tópico da ficha, para conferência manual."""
    citados = [i for i in apolice.ficha_tecnica if i.valor and i.fonte and i.fonte.pagina]
    if not citados:
        return
    with st.expander("🔍 Conferir a fonte de um item no documento original"):
        item = st.selectbox(
            "Tópico",
            options=citados,
            format_func=lambda i: f"{rotulo_topico(i.topico)} — p. {i.fonte.pagina}",
            key=f"fonte_{policy_id}",
        )
        paginas = load_pages(policy_id)
        if item.fonte.trecho:
            st.markdown(f"**Trecho citado:** “{item.fonte.trecho}”")
        if 0 < item.fonte.pagina <= len(paginas):
            st.text_area(f"Texto da página {item.fonte.pagina}", paginas[item.fonte.pagina - 1], height=300, key=f"pg_{policy_id}_{item.topico}")
