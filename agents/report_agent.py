"""
Agente de Relatório — gera Markdown e PDF da apólice extraída e do comparativo.

O PDF é montado diretamente a partir dos objetos estruturados (e não convertendo
Markdown), usando a API de tabelas do fpdf2. Isso evita perder linhas de tabela e
permite quebra automática de texto em cada célula.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Sequence

from models.schemas import (
    ApoliceExtraida,
    CATEGORIAS,
    DiferencaTopico,
    RelatorioComparativo,
    TOPICOS_FICHA,
    rotulo_topico,
)

logger = logging.getLogger(__name__)

NA = "N/D"
RELEVANCIA_ROTULO = {"alta": "ALTA", "media": "MÉDIA", "baixa": "BAIXA"}
RELEVANCIA_ICONE = {"alta": "🔴", "media": "🟡", "baixa": "🟢"}
ORDEM_CATEGORIAS = ["acionamento", "cobertura", "limite", "exclusao", "processo", "cadastral"]


def _agora() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M")


def _pagina(pagina: Optional[int]) -> str:
    return f" (p. {pagina})" if pagina else ""


def _celula_md(texto: Optional[str]) -> str:
    return (texto or NA).replace("|", "\\|").replace("\n", " ")


# ─── Markdown ────────────────────────────────────────────────────────────────

def generate_policy_markdown(apolice: ApoliceExtraida) -> str:
    """Relatório Markdown de uma apólice extraída."""
    da, seg = apolice.dados_apolice, apolice.segurado
    linhas = [
        "# Relatório de Apólice D&O",
        f"**Arquivo:** {apolice.nome_arquivo or NA}  ",
        f"**Tipo de documento:** {apolice.tipo_documento or NA}  ",
        f"**Gerado em:** {_agora()}",
        "",
        "## 1. Dados da apólice",
        "",
        "| Campo | Valor |",
        "|-------|-------|",
        f"| Número da apólice | {_celula_md(da.numero_apolice)} |",
        f"| Seguradora | {_celula_md(da.seguradora)} |",
        f"| Vigência | {_celula_md(da.vigencia_inicio)} a {_celula_md(da.vigencia_fim)} |",
        f"| Prêmio | {_celula_md(da.premio)} |",
        f"| Limite global | {_celula_md(da.limite_global)} |",
        f"| Base de acionamento | {_celula_md(da.base_acionamento)} |",
        f"| Processo SUSEP | {_celula_md(da.processo_susep)} |",
        f"| Versão do documento | {_celula_md(da.versao_documento)} |",
        f"| Segurado | {_celula_md(seg.nome_segurado)} |",
        "",
        "## 2. Ficha técnica D&O",
        "",
        "| Tópico | O que o documento diz | Página |",
        "|--------|-----------------------|--------|",
    ]
    for item in apolice.ficha_tecnica:
        pagina = item.fonte.pagina if item.fonte and item.fonte.pagina else NA
        linhas.append(f"| {rotulo_topico(item.topico)} | {_celula_md(item.valor)} | {pagina} |")

    linhas += ["", "## 3. Coberturas", ""]
    if apolice.coberturas:
        for i, cob in enumerate(apolice.coberturas, 1):
            linhas += [
                f"### 3.{i} {cob.nome}{_pagina(cob.fonte.pagina if cob.fonte else None)}",
                cob.descricao or "Sem descrição no documento.",
                "",
                f"- **Limite:** {cob.limite or NA}",
                f"- **Franquia:** {cob.franquia or NA}",
                f"- **Retroatividade:** {cob.retroatividade or NA}",
                "",
            ]
    else:
        linhas += ["_Nenhuma cobertura identificada._", ""]

    linhas += ["## 4. Exclusões", ""]
    if apolice.exclusoes:
        linhas += [f"- **{e.categoria}:** {e.descricao or NA}{_pagina(e.fonte.pagina if e.fonte else None)}" for e in apolice.exclusoes]
        linhas.append("")
    else:
        linhas += ["_Nenhuma exclusão identificada._", ""]

    linhas += ["## 5. Cláusulas especiais", ""]
    linhas += [f"- {c}" for c in apolice.clausulas_especiais] or ["_Nenhuma cláusula especial identificada._"]
    if apolice.observacoes:
        linhas += ["", "## 6. Observações", "", apolice.observacoes]
    return "\n".join(linhas) + "\n"


def generate_comparison_markdown(relatorio: RelatorioComparativo) -> str:
    """Relatório Markdown comparativo (2 ou mais apólices)."""
    nomes = relatorio.apolices
    linhas = [
        "# Relatório Comparativo de Apólices D&O",
        f"**Gerado em:** {_agora()}  ",
        f"**Apólices:** {' × '.join(nomes)}  ",
        f"**Análise:** {'LLM (' + relatorio.modelo + ')' if relatorio.modo == 'llm' and relatorio.modelo else relatorio.modo}",
        "",
        "## Resumo executivo",
        "",
        relatorio.resumo_executivo,
        "",
        "## Recomendação",
        "",
        relatorio.recomendacao,
        "",
    ]
    grupos = relatorio.por_categoria()
    for n, categoria in enumerate([c for c in ORDEM_CATEGORIAS if c in grupos], start=1):
        linhas += [f"## {n}. {CATEGORIAS.get(categoria, categoria)}", ""]
        linhas += ["| Tópico | " + " | ".join(nomes) + " | Relevância | Análise |", "|---|" + "---|" * (len(nomes) + 2)]
        for d in grupos[categoria]:
            valores = " | ".join(_celula_md(v.valor) + _pagina(v.pagina) if v.valor else NA for v in d.valores)
            favoravel = f" **Mais favorável:** {d.mais_favoravel}." if d.mais_favoravel else ""
            linhas.append(
                f"| {d.rotulo} | {valores} | {RELEVANCIA_ICONE.get(d.relevancia, '')} "
                f"{RELEVANCIA_ROTULO.get(d.relevancia, d.relevancia)} | {_celula_md(d.comentario)}{favoravel} |"
            )
        linhas.append("")
    if relatorio.topicos_iguais:
        linhas += ["## Tópicos sem divergência", "", ", ".join(relatorio.topicos_iguais), ""]
    return "\n".join(linhas) + "\n"


# ─── PDF ─────────────────────────────────────────────────────────────────────

_SUBSTITUICOES = str.maketrans(
    {
        "—": "-", "–": "-", "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...", "•": "-", "×": "x",
        "→": "->", "≥": ">=", "≤": "<=", "º": "o", "ª": "a", "\u00a0": " ", "\u2009": " ", "\u200b": "",
    }
)


def _t(texto: Optional[str]) -> str:
    """Converte para latin-1 (fonte padrão do PDF), preservando acentos do português."""
    limpo = (texto or "").translate(_SUBSTITUICOES)
    return limpo.encode("latin-1", "replace").decode("latin-1")


def _novo_pdf(titulo: str, paisagem: bool = False):
    from fpdf import FPDF

    cabecalho = _t(titulo)

    class PDF(FPDF):
        def header(self):
            self.set_font("Helvetica", "B", 9)
            self.set_text_color(90, 90, 90)
            self.cell(0, 7, cabecalho, new_x="LMARGIN", new_y="NEXT", align="C")
            self.set_draw_color(190, 190, 190)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(3)

        def footer(self):
            self.set_y(-12)
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(140, 140, 140)
            self.cell(0, 8, f"D&O Shield - Pagina {self.page_no()}", align="C")

    pdf = PDF(orientation="L" if paisagem else "P", unit="mm", format="A4")
    pdf.set_margins(12, 18, 12)
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()
    return pdf


def _titulo(pdf, texto: str, nivel: int = 1) -> None:
    tamanhos = {1: (16, 30, 60, 120), 2: (12.5, 45, 80, 150), 3: (10.5, 60, 60, 60)}
    tam, r, g, b = tamanhos[nivel]
    pdf.set_font("Helvetica", "B", tam)
    pdf.set_text_color(r, g, b)
    pdf.multi_cell(0, tam * 0.5, _t(texto), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1.5)


def _paragrafo(pdf, texto: str, tamanho: float = 9.5) -> None:
    pdf.set_font("Helvetica", "", tamanho)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, tamanho * 0.52, _t(texto), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)


def _tabela(pdf, cabecalho: Sequence[str], linhas: Sequence[Sequence[str]], larguras: Sequence[float], tamanho: float = 7.5) -> None:
    from fpdf.fonts import FontFace

    if not linhas:
        _paragrafo(pdf, "Nenhum item identificado.")
        return
    pdf.set_font("Helvetica", "", tamanho)
    pdf.set_text_color(40, 40, 40)
    pdf.set_draw_color(190, 200, 215)
    with pdf.table(
        col_widths=tuple(larguras),
        text_align="LEFT",
        line_height=tamanho * 0.5,
        headings_style=FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=(30, 58, 95)),
        cell_fill_color=(240, 244, 250),
        cell_fill_mode="ROWS",
        padding=1.2,
        repeat_headings=1,
    ) as tabela:
        cab = tabela.row()
        for texto in cabecalho:
            cab.cell(_t(texto))
        for linha in linhas:
            row = tabela.row()
            for texto in linha:
                row.cell(_t(texto))
    pdf.ln(3)


def _saida(pdf) -> bytes:
    return bytes(pdf.output())


def generate_policy_pdf(apolice: ApoliceExtraida) -> bytes:
    """PDF da apólice extraída: dados, ficha técnica, coberturas, exclusões e cláusulas."""
    da, seg = apolice.dados_apolice, apolice.segurado
    pdf = _novo_pdf(f"Apolice D&O - {apolice.nome_arquivo or NA}")
    _titulo(pdf, "Relatório de Apólice D&O")
    _paragrafo(pdf, f"Arquivo: {apolice.nome_arquivo or NA}   |   Tipo: {apolice.tipo_documento or NA}   |   Gerado em {_agora()}", 8.5)

    _titulo(pdf, "1. Dados da apólice", 2)
    _tabela(
        pdf, ["Campo", "Valor"],
        [
            ["Número da apólice", da.numero_apolice or NA],
            ["Seguradora", da.seguradora or NA],
            ["Vigência", f"{da.vigencia_inicio or NA} a {da.vigencia_fim or NA}"],
            ["Prêmio", da.premio or NA],
            ["Limite global", da.limite_global or NA],
            ["Base de acionamento", da.base_acionamento or NA],
            ["Processo SUSEP", da.processo_susep or NA],
            ["Versão do documento", da.versao_documento or NA],
            ["Segurado", seg.nome_segurado or NA],
        ],
        (45, 141), 8,
    )

    _titulo(pdf, "2. Ficha técnica D&O", 2)
    _tabela(
        pdf, ["Tópico", "O que o documento diz", "Pág."],
        [
            [rotulo_topico(i.topico), i.valor or "Não trata do assunto", str(i.fonte.pagina) if i.fonte and i.fonte.pagina else "-"]
            for i in apolice.ficha_tecnica
        ],
        (42, 130, 14),
    )

    _titulo(pdf, "3. Coberturas", 2)
    _tabela(
        pdf, ["Cobertura", "Descrição", "Limite", "Franquia", "Pág."],
        [
            [c.nome, c.descricao or NA, c.limite or NA, c.franquia or NA, str(c.fonte.pagina) if c.fonte and c.fonte.pagina else "-"]
            for c in apolice.coberturas
        ],
        (38, 90, 24, 24, 10),
    )

    _titulo(pdf, "4. Exclusões", 2)
    _tabela(
        pdf, ["Categoria", "Descrição", "Pág."],
        [[e.categoria, e.descricao or NA, str(e.fonte.pagina) if e.fonte and e.fonte.pagina else "-"] for e in apolice.exclusoes],
        (40, 132, 14),
    )

    _titulo(pdf, "5. Cláusulas especiais", 2)
    for clausula in apolice.clausulas_especiais or ["Nenhuma cláusula especial identificada."]:
        _paragrafo(pdf, f"- {clausula}", 9)
    if apolice.observacoes:
        _titulo(pdf, "6. Observações", 2)
        _paragrafo(pdf, apolice.observacoes)
    return _saida(pdf)


def _celula_valor(valor: Optional[str], pagina: Optional[int]) -> str:
    return f"{valor}{_pagina(pagina)}" if valor else "Não trata do assunto"


def generate_comparison_pdf(relatorio: RelatorioComparativo) -> bytes:
    """PDF do comparativo (paisagem): uma tabela por categoria, uma coluna por apólice."""
    nomes = relatorio.apolices
    pdf = _novo_pdf("Relatorio Comparativo D&O", paisagem=True)
    _titulo(pdf, "Relatório Comparativo de Apólices D&O")
    analise = f"LLM ({relatorio.modelo})" if relatorio.modo == "llm" and relatorio.modelo else "determinística"
    _paragrafo(pdf, f"Apólices: {' x '.join(nomes)}   |   Análise: {analise}   |   Gerado em {_agora()}", 8.5)

    _titulo(pdf, "Resumo executivo", 2)
    _paragrafo(pdf, relatorio.resumo_executivo)
    _titulo(pdf, "Recomendação", 2)
    _paragrafo(pdf, relatorio.recomendacao)

    largura = 273.0
    fixa_topico, fixa_relevancia, fixa_analise = 34.0, 16.0, 62.0
    por_apolice = (largura - fixa_topico - fixa_relevancia - fixa_analise) / len(nomes)
    larguras = (fixa_topico, *([por_apolice] * len(nomes)), fixa_relevancia, fixa_analise)

    grupos = relatorio.por_categoria()
    for n, categoria in enumerate([c for c in ORDEM_CATEGORIAS if c in grupos], start=1):
        _titulo(pdf, f"{n}. {CATEGORIAS.get(categoria, categoria)}", 2)
        linhas = []
        for d in grupos[categoria]:
            comentario = d.comentario + (f" Mais favorável: {d.mais_favoravel}." if d.mais_favoravel else "")
            linhas.append(
                [d.rotulo, *[_celula_valor(v.valor, v.pagina) for v in d.valores],
                 RELEVANCIA_ROTULO.get(d.relevancia, d.relevancia), comentario]
            )
        _tabela(pdf, ["Tópico", *nomes, "Relevância", "Análise"], linhas, larguras, 7)

    if relatorio.topicos_iguais:
        _titulo(pdf, "Tópicos sem divergência", 2)
        _paragrafo(pdf, ", ".join(relatorio.topicos_iguais), 9)
    return _saida(pdf)
