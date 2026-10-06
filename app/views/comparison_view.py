"""Tela de comparação entre duas ou três apólices já processadas."""
from __future__ import annotations

import streamlit as st

from agents.comparison_agent import comparar_apolices
from app.views.components import display_comparison
from storage.database import list_policies, load_policy, save_comparison

MAX_APOLICES = 3


def render_comparison(provider: str, model: str) -> None:
    st.subheader("⚖️ Comparar apólices D&O")
    st.markdown(
        "Selecione de **2 a 3** apólices já processadas. As divergências são alinhadas tópico a tópico "
        "(acionamento, coberturas, limites, exclusões e condições) e analisadas pelo modelo."
    )

    policies = list_policies()
    if len(policies) < 2:
        st.warning("⚠️ É necessário ter **pelo menos 2 apólices** processadas. Use a aba **Enviar apólices**.")
        return

    opcoes = {f"#{p['id']} — {p['seguradora']} · {p['filename']}": p["id"] for p in policies}
    escolhidas = st.multiselect(
        "Apólices a comparar",
        options=list(opcoes),
        default=list(opcoes)[:2],
        max_selections=MAX_APOLICES,
    )

    usar_llm = st.checkbox(
        "Usar análise por LLM (relevância, apólice mais favorável, resumo e recomendação)",
        value=True,
        help="Desmarcado: mostra apenas onde os valores divergem, sem custo de API.",
    )

    if st.button("⚖️ Comparar", type="primary", width="stretch", disabled=len(escolhidas) < 2):
        ids = [opcoes[rotulo] for rotulo in escolhidas]
        apolices = [load_policy(i) for i in ids]
        if any(a is None for a in apolices):
            st.error("Não foi possível carregar alguma das apólices selecionadas.")
            return

        with st.spinner(f"Comparando {len(apolices)} apólices via {provider}/{model}..."):
            relatorio = comparar_apolices(apolices, provider=provider, model=model, use_llm=usar_llm)
        st.session_state["ultimo_comparativo"] = (relatorio, save_comparison(relatorio, ids))

    if "ultimo_comparativo" in st.session_state:
        relatorio, cmp_id = st.session_state["ultimo_comparativo"]
        st.success(f"✅ Comparação concluída (salva como #{cmp_id})")
        display_comparison(relatorio, key="cmp_atual")
