"""
Agente de Consulta — responde perguntas em linguagem natural sobre as apólices salvas.

Recuperação + geração: um índice lexical (BM25, sem acentos e sem palavras vazias)
escolhe as páginas mais relevantes de cada apólice e o LLM responde apenas com base
nelas, citando apólice e página. Assim a resposta é rastreável até o documento.
"""
from __future__ import annotations

import logging
import math
import re
import unicodedata
from collections import Counter
from typing import Mapping, Optional, Sequence

from pydantic import BaseModel, Field

from agents.llm_client import LLMError, generate_text_ex
from app.config import DEFAULT_MODELS
from models.schemas import ApoliceExtraida, TOPICOS_FICHA, rotulo_topico

logger = logging.getLogger(__name__)

STOPWORDS = frozenset(
    "a o as os um uma uns umas de do da dos das em no na nos nas por para com sem sob sobre e ou que se "
    "ao aos como mais mas ja seu sua seus suas ele ela eles elas este esta isto esse essa isso qual quais "
    "quando onde ser sao foi tem ter pelo pela pelos pelas entre ate apos".split()
)

SYSTEM_PROMPT = """Você é um analista de seguros D&O que responde perguntas sobre apólices e condições gerais.

REGRAS:
1. Responda SOMENTE com base nos trechos fornecidos. Não use conhecimento externo.
2. Se os trechos não bastarem, diga claramente que não encontrou a informação nos documentos.
3. Cite a fonte de cada afirmação no formato [Nome da apólice, p. N].
4. Quando a pergunta envolver mais de uma apólice, responda separadamente para cada uma e destaque a diferença.
5. Seja objetivo e escreva em português."""

CITACAO = re.compile(r"\[([^\[\]]+?),\s*p\.?\s*(\d+)\s*\]")


class FonteConsulta(BaseModel):
    apolice: str
    pagina: int
    trecho: str = Field(description="Início do texto da página recuperada")


class RespostaConsulta(BaseModel):
    pergunta: str
    resposta: str
    fontes: list[FonteConsulta] = Field(default_factory=list, description="Páginas enviadas ao modelo")
    citadas: list[FonteConsulta] = Field(default_factory=list, description="Páginas que o modelo efetivamente citou")
    modelo: Optional[str] = None


# ─── Índice BM25 ─────────────────────────────────────────────────────────────

def tokenizar(texto: str) -> list[str]:
    base = unicodedata.normalize("NFKD", texto or "")
    base = "".join(c for c in base if not unicodedata.combining(c)).lower()
    return [t for t in re.findall(r"[a-z0-9]+", base) if len(t) > 1 and t not in STOPWORDS]


class IndicePaginas:
    """Índice BM25 sobre as páginas de uma ou mais apólices."""

    K1, B = 1.5, 0.75

    def __init__(self, documentos: Mapping[str, Sequence[str]]):
        self.entradas: list[tuple[str, int, str]] = []  # (apólice, página, texto)
        self.tokens: list[Counter] = []
        for nome, paginas in documentos.items():
            for numero, texto in enumerate(paginas, start=1):
                self.entradas.append((nome, numero, texto))
                self.tokens.append(Counter(tokenizar(texto)))

        n = len(self.entradas) or 1
        self.comprimentos = [sum(c.values()) for c in self.tokens]
        self.medio = (sum(self.comprimentos) / n) or 1.0
        frequencia: Counter = Counter()
        for contagem in self.tokens:
            frequencia.update(contagem.keys())
        self.idf = {t: math.log(1 + (n - df + 0.5) / (df + 0.5)) for t, df in frequencia.items()}

    def _pontuar(self, consulta: list[str], i: int) -> float:
        contagem, comprimento = self.tokens[i], self.comprimentos[i]
        pontos = 0.0
        for termo in consulta:
            f = contagem.get(termo, 0)
            if not f:
                continue
            denominador = f + self.K1 * (1 - self.B + self.B * comprimento / self.medio)
            pontos += self.idf.get(termo, 0.0) * f * (self.K1 + 1) / denominador
        return pontos

    def buscar(self, pergunta: str, por_apolice: int = 5) -> list[tuple[str, int, str, float]]:
        """Melhores páginas de CADA apólice (para que todas fiquem representadas)."""
        consulta = tokenizar(pergunta)
        por_nome: dict[str, list[tuple[float, int]]] = {}
        for i, (nome, _, _) in enumerate(self.entradas):
            pontos = self._pontuar(consulta, i)
            if pontos > 0:
                por_nome.setdefault(nome, []).append((pontos, i))

        resultado = []
        for nome, lista in por_nome.items():
            for pontos, i in sorted(lista, reverse=True)[:por_apolice]:
                _, pagina, texto = self.entradas[i]
                resultado.append((nome, pagina, texto, pontos))
        resultado.sort(key=lambda r: (r[0], r[1]))
        return resultado


# ─── Contexto e resposta ─────────────────────────────────────────────────────

def _resumo_ficha(apolice: ApoliceExtraida) -> str:
    linhas = [
        f"- {rotulo_topico(i.topico)}: {i.valor}"
        for i in apolice.ficha_tecnica
        if i.valor and i.topico in TOPICOS_FICHA
    ]
    return "\n".join(linhas)


def montar_contexto(
    apolices: Mapping[str, ApoliceExtraida], trechos: Sequence[tuple[str, int, str, float]], max_chars_pagina: int = 3500
) -> str:
    partes = ["## FICHA TÉCNICA JÁ EXTRAÍDA (resumo de apoio)"]
    for nome, ap in apolices.items():
        partes.append(f"### {nome}\n{_resumo_ficha(ap) or '(sem ficha extraída)'}")
    partes.append("## TRECHOS RECUPERADOS DOS DOCUMENTOS")
    for nome, pagina, texto, _ in trechos:
        partes.append(f"### [{nome}, p. {pagina}]\n{texto.strip()[:max_chars_pagina]}")
    return "\n\n".join(partes)


def responder(
    pergunta: str,
    apolices: Mapping[str, ApoliceExtraida],
    provider: str = "google",
    model: str = DEFAULT_MODELS["google"],
    por_apolice: int = 5,
) -> RespostaConsulta:
    """
    Responde a uma pergunta sobre uma ou mais apólices.

    Args:
        pergunta: pergunta em linguagem natural.
        apolices: nome de exibição → apólice (com `paginas` carregadas).
        por_apolice: quantas páginas recuperar de cada apólice.
    """
    pergunta = pergunta.strip()
    if not pergunta:
        raise ValueError("A pergunta está vazia.")

    indice = IndicePaginas({nome: ap.paginas for nome, ap in apolices.items()})
    trechos = indice.buscar(pergunta, por_apolice)
    if not trechos:
        return RespostaConsulta(
            pergunta=pergunta,
            resposta="Não encontrei nos documentos selecionados nenhum trecho relacionado à pergunta.",
        )

    usuario = f"{montar_contexto(apolices, trechos)}\n\n## PERGUNTA\n{pergunta}"
    try:
        texto, usado = generate_text_ex(SYSTEM_PROMPT, usuario, provider, model, max_tokens=3000)
    except LLMError as exc:
        logger.error("Falha ao responder a consulta: %s", exc)
        raise

    fontes = [FonteConsulta(apolice=n, pagina=p, trecho=" ".join(t.split())[:160]) for n, p, t, _ in trechos]
    recuperadas = {(f.apolice, f.pagina): f for f in fontes}
    citadas: list[FonteConsulta] = []
    for nome, pagina in CITACAO.findall(texto):
        fonte = recuperadas.get((nome.strip(), int(pagina)))
        if fonte and fonte not in citadas:
            citadas.append(fonte)

    return RespostaConsulta(pergunta=pergunta, resposta=texto, fontes=fontes, citadas=citadas, modelo=usado)
