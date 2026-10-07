"""
Agente de Comparação — compara duas ou mais apólices D&O.

Duas etapas, de propósito:
  1. Alinhamento determinístico: os valores de cada tópico vêm direto da ficha técnica
     extraída. O LLM nunca "recita" valores, então não pode inventá-los.
  2. Análise pelo LLM: recebe só os tópicos em que há divergência e julga a relevância,
     indica qual apólice é mais favorável ao segurado e redige resumo e recomendação.

Se o LLM falhar, a comparação continua disponível em modo determinístico.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Optional, Sequence

from agents.llm_client import LLMError, generate_json_ex
from app.config import DEFAULT_MODELS
from models.schemas import (
    AnaliseLLM,
    ApoliceExtraida,
    DiferencaTopico,
    RelatorioComparativo,
    TOPICOS_AGREGADOS,
    TOPICOS_FICHA,
    ValorApolice,
    categoria_topico,
    rotulo_topico,
    valor_ou_none,
)

logger = logging.getLogger(__name__)

# Tópicos cadastrais comparados além da ficha técnica (campo da apólice → rótulo).
CAMPOS_CADASTRAIS = {
    "seguradora": "Seguradora",
    "limite_global": "Limite global",
    "premio": "Prêmio",
    "vigencia": "Vigência",
    "versao_documento": "Versão do documento",
}

COMPARISON_SYSTEM_PROMPT = """Você é um corretor e analista sênior de seguros D&O, especialista em comparar condições de apólices para apoiar a decisão de quem contrata.

Você receberá, para cada tópico, o que cada apólice diz. Os valores já foram extraídos dos documentos — NÃO os repita nem os corrija; avalie-os.

REGRAS:
1. Responda com um item em `topicos` para CADA tópico recebido, usando a chave exata.
2. `relevancia`: 'alta' (muda a proteção efetiva ou o risco financeiro do segurado), 'media' (relevante, mas contornável) ou 'baixa' (diferença formal).
3. `comentario`: 1 a 2 frases dizendo QUAL é a diferença prática e por que importa. Não copie os valores integralmente.
4. `mais_favoravel`: nome exato da apólice mais favorável ao segurado naquele tópico, ou null se forem equivalentes ou não for possível julgar. Para exclusões, ter MENOS exclusões é mais favorável. Quando uma apólice não trata do tópico, diga isso no comentário e não presuma que seja pior.
5. `resumo_executivo`: 4 a 6 frases com as diferenças que mais pesam na decisão.
6. `recomendacao`: indique, justificando, em que perfil de contratante cada apólice se sai melhor. Seja prudente: a análise é de condições contratuais, não de preço.
7. Escreva em português."""


def _norm(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto or "")
    base = "".join(c for c in base if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", base).strip().lower()


# ─── Nomes e valores por apólice ─────────────────────────────────────────────

def nomes_unicos(apolices: Sequence[ApoliceExtraida]) -> list[str]:
    """Rótulo legível e único para cada apólice (seguradora ou nome do arquivo)."""
    nomes: list[str] = []
    for i, ap in enumerate(apolices, start=1):
        base = (ap.dados_apolice.seguradora or ap.nome_arquivo or f"Apólice {i}").strip()
        nome, n = base, 2
        while nome in nomes:
            nome, n = f"{base} ({n})", n + 1
        nomes.append(nome)
    return nomes


def _resumo_lista(itens: list[str], limite: int = 400) -> Optional[str]:
    if not itens:
        return None
    texto = "; ".join(itens)
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


def _valores_do_topico(chave: str, apolice: ApoliceExtraida, nome: str) -> ValorApolice:
    """Valor (e página de origem) de um tópico para uma apólice."""
    if chave in TOPICOS_FICHA:
        item = apolice.ficha_por_topico().get(chave)
        if item and valor_ou_none(item.valor):
            return ValorApolice(apolice=nome, valor=item.valor, pagina=item.fonte.pagina if item.fonte else None)
        return ValorApolice(apolice=nome)

    if chave == "lista_coberturas":
        return ValorApolice(apolice=nome, valor=_resumo_lista([c.nome for c in apolice.coberturas]))
    if chave == "lista_exclusoes":
        return ValorApolice(apolice=nome, valor=_resumo_lista([e.categoria for e in apolice.exclusoes]))
    if chave == "lista_clausulas":
        return ValorApolice(apolice=nome, valor=_resumo_lista(apolice.clausulas_especiais))

    da = apolice.dados_apolice
    if chave == "vigencia":
        partes = [p for p in (da.vigencia_inicio, da.vigencia_fim) if p]
        return ValorApolice(apolice=nome, valor=" a ".join(partes) or None)
    return ValorApolice(apolice=nome, valor=getattr(da, chave, None) or None)


def alinhar_topicos(apolices: Sequence[ApoliceExtraida], nomes: Sequence[str]) -> dict[str, list[ValorApolice]]:
    """Monta, para cada tópico, o valor de todas as apólices (sem usar LLM)."""
    chaves = list(CAMPOS_CADASTRAIS) + list(TOPICOS_FICHA) + list(TOPICOS_AGREGADOS)
    return {
        chave: [_valores_do_topico(chave, ap, nome) for ap, nome in zip(apolices, nomes)]
        for chave in chaves
    }


def _divergem(valores: list[ValorApolice]) -> bool:
    """Há divergência se ao menos duas apólices diferem (tratando 'não informado' como um valor)."""
    normalizados = {_norm(v.valor or "") for v in valores}
    return len(normalizados) > 1


def _todos_vazios(valores: list[ValorApolice]) -> bool:
    return not any(v.valor for v in valores)


# ─── Comparação determinística (fallback e base do alinhamento) ──────────────

def _diferencas_listas(chave: str, apolices: Sequence[ApoliceExtraida], nomes: Sequence[str]) -> Optional[str]:
    """Para listas (coberturas/exclusões), aponta o que só aparece em parte das apólices."""
    extrair = {
        "lista_coberturas": lambda a: {_norm(c.nome): c.nome for c in a.coberturas},
        "lista_exclusoes": lambda a: {_norm(e.categoria): e.categoria for e in a.exclusoes},
        "lista_clausulas": lambda a: {_norm(c): c for c in a.clausulas_especiais},
    }.get(chave)
    if not extrair:
        return None
    conjuntos = [extrair(a) for a in apolices]
    comuns = set.intersection(*(set(c) for c in conjuntos)) if conjuntos else set()
    partes = []
    for nome, itens in zip(nomes, conjuntos):
        exclusivos = [itens[k] for k in itens if k not in comuns]
        if exclusivos:
            partes.append(f"{nome}: {_resumo_lista(exclusivos, 160)}")
    return "Itens que não aparecem nas demais — " + " | ".join(partes) if partes else None


def comparar_deterministico(
    apolices: Sequence[ApoliceExtraida], nomes: Optional[Sequence[str]] = None
) -> RelatorioComparativo:
    """Comparação sem LLM: aponta onde os valores divergem, sem julgar qual é melhor."""
    nomes = list(nomes or nomes_unicos(apolices))
    alinhados = alinhar_topicos(apolices, nomes)

    diferencas: list[DiferencaTopico] = []
    iguais: list[str] = []
    for chave, valores in alinhados.items():
        if _todos_vazios(valores):
            continue
        if not _divergem(valores):
            iguais.append(rotulo_topico(chave))
            continue
        ausentes = [v.apolice for v in valores if not v.valor]
        comentario = (
            "O documento não trata do tópico em: " + ", ".join(ausentes) + "."
            if ausentes
            else "As apólices divergem neste tópico."
        )
        extra = _diferencas_listas(chave, apolices, nomes)
        diferencas.append(
            DiferencaTopico(
                topico=chave,
                rotulo=rotulo_topico(chave),
                categoria=categoria_topico(chave),
                valores=valores,
                relevancia="media",
                comentario=(extra or comentario),
            )
        )

    return RelatorioComparativo(
        apolices=nomes,
        diferencas=diferencas,
        topicos_iguais=iguais,
        resumo_executivo=(
            f"Comparação simplificada entre {', '.join(nomes)}: {len(diferencas)} tópico(s) com divergência "
            f"e {len(iguais)} sem divergência. A relevância e a recomendação exigem o modo com LLM."
        ),
        recomendacao="Análise em modo determinístico: configure uma chave de LLM para obter recomendação.",
        modo="deterministico",
    )


# ─── Comparação com LLM ──────────────────────────────────────────────────────

def _montar_pedido(alinhados: dict[str, list[ValorApolice]], divergentes: list[str], nomes: Sequence[str]) -> str:
    blocos = []
    for chave in divergentes:
        linhas = [f"- {v.apolice}: {v.valor or '(o documento não trata do tópico)'}" for v in alinhados[chave]]
        blocos.append(f"### {chave} — {rotulo_topico(chave)}\n" + "\n".join(linhas))
    return (
        f"Apólices comparadas: {', '.join(nomes)}\n\n"
        "Tópicos em que há divergência (valores extraídos dos documentos):\n\n" + "\n\n".join(blocos)
    )


def comparar_apolices(
    apolices: Sequence[ApoliceExtraida],
    provider: str = "google",
    model: str = DEFAULT_MODELS["google"],
    use_llm: bool = True,
) -> RelatorioComparativo:
    """
    Compara 2 ou mais apólices D&O.

    Args:
        apolices: apólices já extraídas (mínimo 2).
        provider: provedor do LLM.
        model: modelo do provedor.
        use_llm: com False, usa apenas a comparação determinística.
    """
    if len(apolices) < 2:
        raise ValueError("É necessário ao menos duas apólices para comparar.")

    nomes = nomes_unicos(apolices)
    base = comparar_deterministico(apolices, nomes)
    if not use_llm or not base.diferencas:
        return base

    alinhados = alinhar_topicos(apolices, nomes)
    divergentes = [d.topico for d in base.diferencas]
    pedido = _montar_pedido(alinhados, divergentes, nomes)

    try:
        analise, usado = generate_json_ex(COMPARISON_SYSTEM_PROMPT, pedido, AnaliseLLM, provider, model, max_tokens=12000)
    except LLMError as exc:
        logger.error("Falha na análise por LLM; mantendo a comparação determinística: %s", exc)
        base.recomendacao = f"Análise por LLM indisponível ({exc}). Exibindo apenas as divergências identificadas."
        return base

    julgamentos = {t.topico: t for t in analise.topicos}
    relevancias = {"alta", "media", "baixa"}
    diferencas: list[DiferencaTopico] = []
    for diff in base.diferencas:
        j = julgamentos.get(diff.topico)
        if j:
            diff.relevancia = j.relevancia if j.relevancia in relevancias else "media"
            diff.comentario = j.comentario or diff.comentario
            diff.mais_favoravel = j.mais_favoravel if j.mais_favoravel in nomes else None
        diferencas.append(diff)

    peso = {"alta": 0, "media": 1, "baixa": 2}
    diferencas.sort(key=lambda d: peso.get(d.relevancia, 1))

    return RelatorioComparativo(
        apolices=list(nomes),
        diferencas=diferencas,
        topicos_iguais=base.topicos_iguais,
        resumo_executivo=analise.resumo_executivo or base.resumo_executivo,
        recomendacao=analise.recomendacao or base.recomendacao,
        modo="llm",
        modelo=usado,
    )


def compare_policies(
    apolice_a: ApoliceExtraida,
    apolice_b: ApoliceExtraida,
    provider: str = "google",
    model: str = DEFAULT_MODELS["google"],
    use_llm: bool = True,
) -> RelatorioComparativo:
    """Atalho para comparar exatamente duas apólices (compatível com a versão anterior)."""
    return comparar_apolices([apolice_a, apolice_b], provider, model, use_llm)
