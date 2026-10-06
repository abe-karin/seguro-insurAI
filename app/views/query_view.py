"""Tela de consulta: perguntas em linguagem natural sobre as apólices salvas."""
from __future__ import annotations

import streamlit as st

from agents.comparison_agent import nomes_unicos
from agents.llm_client import LLMError
from agents.query_agent import responder
from storage.database import list_policies, load_policy

EXEMPLOS = [
    "A apólice cobre custos de defesa? Há adiantamento?",
    "Qual o prazo para avisar a seguradora sobre uma reclamação?",
    "Existe cobertura para multas e penalidades administrativas?",
    "O que acontece com a cobertura se a empresa mudar de controle?",
    "Quais exclusões se aplicam a atos dolosos ou fraude?",
]


def render_query(provider: str, model: str) -> None:
    st.subheader("💬 Consultar apólices")
    st.markdown(
        "Faça perguntas em linguagem natural. O sistema localiza as páginas mais relevantes de cada apólice "
        "selecionada e o modelo responde **citando apólice e página**."
    )

    policies = list_policies()
    if not policies:
        st.info("Nenhuma apólice processada ainda. Use a aba **Enviar apólices** para começar.")
        return

    opcoes = {f"#{p['id']} — {p['seguradora']} · {p['filename']}": p["id"] for p in policies}
    escolhidas = st.multiselect("Apólices consultadas", options=list(opcoes), default=list(opcoes)[:3], max_selections=4)

    st.caption("Exemplos de perguntas:")
    colunas = st.columns(len(EXEMPLOS))
    for coluna, exemplo in zip(colunas, EXEMPLOS):
        if coluna.button(exemplo, width="stretch", key=f"ex_{exemplo}"):
            st.session_state["pergunta_consulta"] = exemplo

    pergunta = st.text_input("Sua pergunta", key="pergunta_consulta", placeholder="Ex.: Qual o prazo de retroatividade?")

    if st.button("🔎 Perguntar", type="primary", width="stretch", disabled=not (pergunta.strip() and escolhidas)):
        carregadas = [ap for ap in (load_policy(opcoes[r], with_pages=True) for r in escolhidas) if ap]
        # Nomes únicos: duas apólices da mesma seguradora não podem se sobrescrever.
        apolices = dict(zip(nomes_unicos(carregadas), carregadas))

        with st.spinner("Consultando os documentos..."):
            try:
                resposta = responder(pergunta, apolices, provider=provider, model=model)
            except (LLMError, ValueError) as exc:
                st.error(f"Não foi possível obter a resposta: {exc}")
                return
        st.session_state["ultima_resposta"] = resposta

    resposta = st.session_state.get("ultima_resposta")
    if resposta:
        st.markdown("### Resposta")
        st.markdown(resposta.resposta)
        if resposta.modelo:
            st.caption(f"Modelo: {resposta.modelo}")

        if resposta.citadas:
            with st.expander(f"📚 Páginas citadas ({len(resposta.citadas)})", expanded=True):
                for fonte in resposta.citadas:
                    st.markdown(f"**{fonte.apolice} — p. {fonte.pagina}**  \n> {fonte.trecho}…")
        if resposta.fontes:
            with st.expander(f"Todas as páginas recuperadas ({len(resposta.fontes)})"):
                for fonte in resposta.fontes:
                    st.markdown(f"- {fonte.apolice}, p. {fonte.pagina}")
