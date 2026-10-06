"""
Agente de Relatório — gera PDFs e Markdown a partir das extrações e comparações.
"""
from __future__ import annotations
import io
import logging
from datetime import datetime
from typing import Optional

from models.schemas import ApoliceExtraida, RelatorioComparativo

logger = logging.getLogger(__name__)


# ─── Geração de Markdown ─────────────────────────────────────────────────────

def generate_policy_markdown(apolice: ApoliceExtraida) -> str:
    """Gera relatório Markdown de uma apólice extraída."""
    da = apolice.dados_apolice
    seg = apolice.segurado
    lines = [
        f"# Relatório de Apólice D&O",
        f"**Arquivo:** {apolice.nome_arquivo or 'N/D'}  ",
        f"**Gerado em:** {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        "",
        "---",
        "",
        "## 1. Dados da Apólice",
        "",
        f"| Campo | Valor |",
        f"|-------|-------|",
        f"| Número da Apólice | {da.numero_apolice or 'N/D'} |",
        f"| Seguradora | {da.seguradora or 'N/D'} |",
        f"| Vigência | {da.vigencia_inicio or 'N/D'} a {da.vigencia_fim or 'N/D'} |",
        f"| Prêmio | {da.premio or 'N/D'} |",
        f"| Limite Global | {da.limite_global or 'N/D'} |",
        f"| Base de Acionamento | {da.base_acionamento or 'N/D'} |",
        "",
        "## 2. Dados do Segurado",
        "",
        f"| Campo | Valor |",
        f"|-------|-------|",
        f"| Nome/Razão Social | {seg.nome_segurado or 'N/D'} |",
        f"| CNPJ | {seg.cnpj or 'N/D'} |",
        f"| Setor | {seg.setor or 'N/D'} |",
        "",
        "## 3. Coberturas",
        "",
    ]

    if apolice.coberturas:
        for i, cob in enumerate(apolice.coberturas, 1):
            lines += [
                f"### 3.{i} {cob.nome}",
                f"{cob.descricao}",
                "",
                f"- **Limite:** {cob.limite or 'N/D'}",
                f"- **Franquia:** {cob.franquia or 'N/D'}",
                f"- **Retroatividade:** {cob.retroatividade or 'N/D'}",
                "",
            ]
    else:
        lines.append("_Nenhuma cobertura identificada._\n")

    lines += ["## 4. Exclusões", ""]
    if apolice.exclusoes:
        for exc in apolice.exclusoes:
            lines.append(f"- **{exc.categoria}:** {exc.descricao}")
        lines.append("")
    else:
        lines.append("_Nenhuma exclusão identificada._\n")

    lines += ["## 5. Cláusulas Especiais", ""]
    if apolice.clausulas_especiais:
        for cls in apolice.clausulas_especiais:
            lines.append(f"- {cls}")
        lines.append("")
    else:
        lines.append("_Nenhuma cláusula especial identificada._\n")

    if apolice.observacoes:
        lines += ["## 6. Observações", "", apolice.observacoes, ""]

    return "\n".join(lines)


def generate_comparison_markdown(relatorio: RelatorioComparativo) -> str:
    """Gera relatório Markdown comparativo entre duas apólices."""

    def relevancia_badge(r: str) -> str:
        icons = {"alta": "🔴", "media": "🟡", "baixa": "🟢"}
        return icons.get(r, "⚪")

    def diff_table(diffs) -> list[str]:
        if not diffs:
            return ["_Nenhuma diferença identificada._", ""]
        rows = [
            "| Campo | Apólice A | Apólice B | Relevância | Comentário |",
            "|-------|-----------|-----------|------------|------------|",
        ]
        for d in diffs:
            rows.append(
                f"| {d.campo} | {d.valor_a or 'N/D'} | {d.valor_b or 'N/D'} "
                f"| {relevancia_badge(d.relevancia)} {d.relevancia.capitalize()} | {d.comentario} |"
            )
        rows.append("")
        return rows

    lines = [
        f"# Relatório Comparativo de Apólices D&O",
        f"**Gerado em:** {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        "",
        f"**Apólice A:** {relatorio.apolice_a}  ",
        f"**Apólice B:** {relatorio.apolice_b}",
        "",
        "---",
        "",
        "## Resumo Executivo",
        "",
        relatorio.resumo_executivo,
        "",
        "## Recomendação Técnica",
        "",
        relatorio.recomendacao,
        "",
        "---",
        "",
        "## 1. Diferenças Cadastrais",
        "",
    ]
    lines += diff_table(relatorio.diferencas_cadastrais)
    lines += ["## 2. Diferenças em Coberturas", ""]
    lines += diff_table(relatorio.diferencas_coberturas)
    lines += ["## 3. Diferenças em Exclusões", ""]
    lines += diff_table(relatorio.diferencas_exclusoes)
    lines += ["## 4. Diferenças em Limites", ""]
    lines += diff_table(relatorio.diferencas_limites)

    return "\n".join(lines)


# ─── Geração de PDF ──────────────────────────────────────────────────────────

def _safe_text(text: str) -> str:
    """Converte texto para latin-1 seguro para FPDF2 com fontes built-in."""
    import unicodedata
    # Normaliza para NFD e remove diacríticos não suportados pelo latin-1
    result = []
    for ch in text:
        try:
            ch.encode("latin-1")
            result.append(ch)
        except (UnicodeEncodeError, ValueError):
            # Tenta normalizar: ç→c, ã→a, etc.
            normalized = unicodedata.normalize("NFD", ch)
            ascii_ch = normalized.encode("ascii", "ignore").decode("ascii")
            result.append(ascii_ch if ascii_ch else "?")
    return "".join(result)


def generate_pdf_from_markdown(markdown_text: str, title: str = "Relatorio D&O") -> bytes:
    """Gera PDF a partir de texto Markdown usando FPDF2."""
    try:
        from fpdf import FPDF

        safe_title = _safe_text(title)

        class PDF(FPDF):
            def header(self):
                self.set_font("Helvetica", "B", 10)
                self.set_text_color(60, 60, 60)
                self.cell(0, 8, safe_title, new_x="LMARGIN", new_y="NEXT", align="C")
                self.set_draw_color(180, 180, 180)
                self.line(10, self.get_y(), 200, self.get_y())
                self.ln(4)

            def footer(self):
                self.set_y(-15)
                self.set_font("Helvetica", "I", 8)
                self.set_text_color(150, 150, 150)
                self.cell(0, 10, f"D&O Shield - Pag. {self.page_no()}", align="C")

        pdf = PDF()
        pdf.set_margins(15, 20, 15)  # left, top, right — set BEFORE add_page
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()

        def _render_line(s: str):
            """Renderiza uma linha, adicionando nova página se necessário."""
            if pdf.get_y() > (pdf.h - pdf.b_margin - 15):
                pdf.add_page()
            if s.startswith("# "):
                pdf.set_font("Helvetica", "B", 16)
                pdf.set_text_color(30, 60, 120)
                pdf.multi_cell(0, 10, s[2:])
                pdf.ln(2)
            elif s.startswith("## "):
                pdf.set_font("Helvetica", "B", 13)
                pdf.set_text_color(50, 80, 150)
                pdf.multi_cell(0, 8, s[3:])
                pdf.ln(1)
            elif s.startswith("### "):
                pdf.set_font("Helvetica", "B", 11)
                pdf.set_text_color(70, 100, 170)
                pdf.multi_cell(0, 7, s[4:])
            elif s.startswith("---"):
                pdf.set_draw_color(200, 200, 200)
                pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
                pdf.ln(3)
            elif s.startswith("| ") and "|" in s:
                cells = [c.strip() for c in s.split("|") if c.strip()]
                if cells and not all(c.startswith("-") for c in cells):
                    pdf.set_font("Helvetica", size=7)
                    pdf.set_text_color(40, 40, 40)
                    truncated = [c[:30] for c in cells[:4]]
                    row_text = " | ".join(truncated)
                    pdf.multi_cell(0, 5, row_text)
            elif s.startswith("- "):
                pdf.set_font("Helvetica", size=9)
                pdf.set_text_color(40, 40, 40)
                pdf.multi_cell(0, 6, "  * " + s[2:])
            elif s.startswith("**") and s.endswith("**"):
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(40, 40, 40)
                pdf.multi_cell(0, 6, s.strip("*"))
            elif s:
                pdf.set_font("Helvetica", size=10)
                pdf.set_text_color(40, 40, 40)
                pdf.multi_cell(0, 6, s)
            else:
                pdf.ln(2)

        for line in markdown_text.split("\n"):
            stripped = _safe_text(line.strip())
            try:
                _render_line(stripped)
            except Exception as render_err:
                logger.debug(f"PDF render skip: {render_err}")

        return bytes(pdf.output())

    except Exception as e:
        logger.error(f"Falha ao gerar PDF: {e}")
        # Fallback: retorna markdown como bytes
        return markdown_text.encode("utf-8")


def generate_policy_pdf(apolice: ApoliceExtraida) -> bytes:
    md = generate_policy_markdown(apolice)
    return generate_pdf_from_markdown(md, title=f"Apólice D&O — {apolice.nome_arquivo or 'N/D'}")


def generate_comparison_pdf(relatorio: RelatorioComparativo) -> bytes:
    md = generate_comparison_markdown(relatorio)
    return generate_pdf_from_markdown(md, title="Relatório Comparativo D&O")
