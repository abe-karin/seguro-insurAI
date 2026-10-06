"""Componentes de interface reutilizados pelas telas."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from agents.extraction_agent import qualidade_ancoragem
from agents.report_agent import (
    ORDEM_CATEGORIAS,
    RELEVANCIA_ICONE,
    RELEVANCIA_ROTULO,
    generate_comparison_markdown,
    generate_comparison_pdf,
    generate_policy_markdown,
    generate_policy_pdf,
)
from models.schemas import ApoliceExtraida, CATEGORIAS, RelatorioComparativo, rotulo_topico

NA = "N/D"


def _pagina(fonte) -> str:
    return str(fonte.pagina) if fonte and fonte.pagina else "-"


def _selo(fonte) -> str:
    """Indica se o trecho citado foi confirmado no texto da página."""
    if not fonte or not fonte.pagina:
        return "—"
    return "✅" if fonte.verificada else "⚠️"


def display_policy(apolice: ApoliceExtraida, key: str = "pol") -> None:
    """Exibe uma apólice extraída: métricas, ficha técnica, coberturas, exclusões e cláusulas."""
    da, seg = apolice.dados_apolice, apolice.segurado
    st.subheader(f"📋 {apolice.nome_arquivo or 'Apólice'}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Seguradora", da.seguradora or NA)
    c2.metric("Tipo de documento", (apolice.tipo_documento or NA).replace("_", " "))
    c3.metric("Base de acionamento", da.base_acionamento or NA)
    c4.metric("Páginas", apolice.total_paginas or NA)

    ancoragem = qualidade_ancoragem(apolice)
    if ancoragem["total"]:
        pct = 100 * ancoragem["verificadas"] / ancoragem["total"]
        st.caption(
            f"🔎 Verificação das fontes: **{ancoragem['verificadas']} de {ancoragem['total']}** trechos citados "
            f"foram confirmados no texto da página indicada ({pct:.0f}%)."
        )

    tab_ficha, tab_dados, tab_cob, tab_exc, tab_cls = st.tabs(
        ["🧾 Ficha técnica", "📄 Dados gerais", "🛡️ Coberturas", "🚫 Exclusões", "📝 Cláusulas especiais"]
    )

    with tab_ficha:
        linhas = [
            {
                "Tópico": rotulo_topico(i.topico),
                "O que o documento diz": i.valor or "Não trata do assunto",
                "Pág.": _pagina(i.fonte),
                "Fonte": _selo(i.fonte),
            }
            for i in apolice.ficha_tecnica
        ]
        st.dataframe(pd.DataFrame(linhas), width="stretch", hide_index=True)
        st.caption("✅ trecho confirmado na página · ⚠️ citação não localizada no texto (conferir no documento)")

    with tab_dados:
        col_a, col_b = st.columns(2)
        col_a.markdown("**Dados da apólice**")
        col_a.json(
            {
                "Número": da.numero_apolice or NA,
                "Seguradora": da.seguradora or NA,
                "Vigência": f"{da.vigencia_inicio or NA} a {da.vigencia_fim or NA}",
                "Prêmio": da.premio or NA,
                "Limite global": da.limite_global or NA,
                "Processo SUSEP": da.processo_susep or NA,
                "Versão": da.versao_documento or NA,
            }
        )
        col_b.markdown("**Dados do segurado**")
        col_b.json({"Nome/Razão social": seg.nome_segurado or NA, "CNPJ": seg.cnpj or NA, "Setor": seg.setor or NA})
        if apolice.observacoes:
            st.markdown("**Observações**")
            st.markdown(apolice.observacoes)

    with tab_cob:
        if not apolice.coberturas:
            st.info("Nenhuma cobertura identificada.")
        for i, cob in enumerate(apolice.coberturas):
            pagina = f" · p. {cob.fonte.pagina}" if cob.fonte and cob.fonte.pagina else ""
            with st.expander(f"**{cob.nome}**{pagina}", expanded=(i == 0)):
                st.markdown(cob.descricao or "_Sem descrição no documento._")
                c1, c2, c3 = st.columns(3)
                c1.metric("Limite", cob.limite or NA)
                c2.metric("Franquia", cob.franquia or NA)
                c3.metric("Retroatividade", cob.retroatividade or NA)
                if cob.fonte and cob.fonte.trecho:
                    st.caption(f"“{cob.fonte.trecho}”")

    with tab_exc:
        if apolice.exclusoes:
            df = pd.DataFrame(
                [
                    {"Categoria": e.categoria, "Descrição": e.descricao or "—", "Pág.": _pagina(e.fonte), "Fonte": _selo(e.fonte)}
                    for e in apolice.exclusoes
                ]
            )
            st.dataframe(df, width="stretch", hide_index=True)
        else:
            st.info("Nenhuma exclusão identificada.")

    with tab_cls:
        if apolice.clausulas_especiais:
            for clausula in apolice.clausulas_especiais:
                st.markdown(f"- {clausula}")
        else:
            st.info("Nenhuma cláusula especial identificada.")


def policy_downloads(apolice: ApoliceExtraida, base_name: str, key: str) -> None:
    """Botões de download (PDF e Markdown) da apólice."""
    col_pdf, col_md = st.columns(2)
    col_pdf.download_button(
        "⬇️ Baixar relatório PDF",
        data=generate_policy_pdf(apolice),
        file_name=f"{base_name}.pdf",
        mime="application/pdf",
        width="stretch",
        key=f"{key}_pdf",
    )
    col_md.download_button(
        "⬇️ Baixar relatório Markdown",
        data=generate_policy_markdown(apolice).encode("utf-8"),
        file_name=f"{base_name}.md",
        mime="text/markdown",
        width="stretch",
        key=f"{key}_md",
    )


def display_comparison(relatorio: RelatorioComparativo, key: str = "cmp") -> None:
    """Exibe o comparativo: resumo, recomendação e uma matriz por categoria."""
    st.subheader("📊 " + "  ×  ".join(relatorio.apolices))

    modo = f"LLM · {relatorio.modelo}" if relatorio.modo == "llm" and relatorio.modelo else "determinística (sem LLM)"
    contagem = {"alta": 0, "media": 0, "baixa": 0}
    for d in relatorio.diferencas:
        contagem[d.relevancia] = contagem.get(d.relevancia, 0) + 1

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Divergências", len(relatorio.diferencas))
    c2.metric("🔴 Alta relevância", contagem["alta"])
    c3.metric("🟡 Média", contagem["media"])
    c4.metric("Sem divergência", len(relatorio.topicos_iguais))
    st.caption(f"Análise: {modo}")

    with st.expander("📝 Resumo executivo", expanded=True):
        st.markdown(relatorio.resumo_executivo)
    with st.expander("💡 Recomendação", expanded=True):
        st.markdown(relatorio.recomendacao)

    grupos = relatorio.por_categoria()
    categorias = [c for c in ORDEM_CATEGORIAS if c in grupos]
    if categorias:
        abas = st.tabs([CATEGORIAS.get(c, c) for c in categorias])
        for aba, categoria in zip(abas, categorias):
            with aba:
                linhas = []
                for d in grupos[categoria]:
                    linha = {"Tópico": d.rotulo}
                    for v in d.valores:
                        marca = " ⭐" if d.mais_favoravel == v.apolice else ""
                        linha[v.apolice] = (f"{v.valor} (p. {v.pagina})" if v.pagina else v.valor) if v.valor else "—"
                        linha[v.apolice] += marca if v.valor else ""
                    linha["Relevância"] = f"{RELEVANCIA_ICONE.get(d.relevancia, '')} {RELEVANCIA_ROTULO.get(d.relevancia, d.relevancia)}"
                    linha["Análise"] = d.comentario
                    linhas.append(linha)
                st.dataframe(pd.DataFrame(linhas), width="stretch", hide_index=True)
        st.caption("⭐ = apólice mais favorável ao segurado naquele tópico · — = o documento não trata do assunto")
    else:
        st.info("Nenhuma divergência identificada entre as apólices.")

    if relatorio.topicos_iguais:
        with st.expander("Tópicos sem divergência"):
            st.write(", ".join(relatorio.topicos_iguais))

    col_pdf, col_md = st.columns(2)
    col_pdf.download_button(
        "⬇️ Baixar comparativo PDF",
        data=generate_comparison_pdf(relatorio),
        file_name="comparativo_do.pdf",
        mime="application/pdf",
        width="stretch",
        key=f"{key}_pdf",
    )
    col_md.download_button(
        "⬇️ Baixar comparativo Markdown",
        data=generate_comparison_markdown(relatorio).encode("utf-8"),
        file_name="comparativo_do.md",
        mime="text/markdown",
        width="stretch",
        key=f"{key}_md",
    )
