"""
Agente de Extração — estrutura uma apólice D&O com um LLM.

Fluxo:
  1. O texto do documento (com marcadores `[[PÁGINA n]]`) vai ao modelo em UMA chamada
     sempre que cabe na janela de contexto; só documentos maiores são divididos, e
     sempre em fronteiras de página.
  2. O modelo devolve JSON validado pelo schema `ExtracaoLLM`, incluindo uma ficha
     técnica com os tópicos fixos de D&O e a fonte (página + trecho) de cada item.
  3. O resultado é pós-processado: tópicos normalizados, páginas validadas e cada
     trecho citado conferido contra o texto da página (verificação de ancoragem).
"""
from __future__ import annotations

import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional, Sequence

from agents.ingestion_agent import format_pages_for_llm
from agents.llm_client import generate_json
from app.config import DEFAULT_MODELS
from models.schemas import (
    ApoliceExtraida,
    ExtracaoLLM,
    Fonte,
    ItemFicha,
    TOPICOS_FICHA,
    valor_ou_none,
)

logger = logging.getLogger(__name__)

# Tamanho máximo (caracteres) de texto por chamada. Mesmo com janelas de contexto enormes,
# lotes menores respondem mais rápido, falham menos por tempo limite e rodam em paralelo.
MAX_CHARS_POR_CHAMADA = {"google": 90_000, "openai": 90_000, "anthropic": 90_000}
MAX_PARALELO = 3

# Fração mínima dos tokens de um trecho que precisa aparecer na página para considerá-lo verificado.
LIMIAR_TRECHO = 0.8

EXTRACTION_SYSTEM_PROMPT = """Você é um especialista sênior em seguros D&O (Directors & Officers), com profundo conhecimento de apólices, condições gerais, regulamentação SUSEP e práticas do mercado brasileiro.

Sua tarefa é extrair e estruturar as informações do documento fornecido.

REGRAS:
1. Use SOMENTE o que está no texto. Não invente, não complete com conhecimento externo.
2. Campo ou tópico que o documento não trata deve ser null.
3. O texto traz marcadores [[PÁGINA n]]. Em todo item com `fonte`, informe `pagina` = n (inteiro) e `trecho` = citação LITERAL e curta (até 150 caracteres), copiada exatamente do texto daquela página.
4. `tipo_documento`: 'condicoes_gerais' quando for modelo/condições gerais sem os dados de um segurado específico; 'apolice' quando houver segurado, vigência e valores concretos.
5. `ficha_tecnica`: exatamente UM item para CADA tópico da lista abaixo, com a chave exata. `valor` = resumo objetivo (no máximo 30 palavras), preservando números, prazos e condições. Se o documento não tratar do tópico, `valor` = null.
6. `coberturas`: as coberturas e extensões garantidas (incluindo adicionais), com `descricao` de até 25 palavras.
7. `exclusoes`: as exclusões relevantes (até 20), cada uma com categoria curta e `descricao` de até 25 palavras.
8. `clausulas_especiais`: cláusulas que mudam materialmente a proteção (ex.: período de descoberta, run-off, adiantamento de despesas, severabilidade), em frases curtas.
9. Valores monetários, datas e prazos devem ser reproduzidos como aparecem no documento.
10. Escreva em português.

TÓPICOS DA FICHA TÉCNICA (chave: descrição):
{topicos}
"""

EXTRACTION_USER_TEMPLATE = """Extraia as informações do documento abaixo.

DOCUMENTO ({nome}):
{texto}
"""


def _topicos_para_prompt() -> str:
    return "\n".join(f"- {chave}: {desc}" for chave, (_, _, desc) in TOPICOS_FICHA.items())


# ─── Divisão e fusão ─────────────────────────────────────────────────────────

def split_pages(pages: Sequence[str], max_chars: int) -> list[tuple[int, list[str]]]:
    """
    Agrupa páginas consecutivas em lotes de até `max_chars`, sem nunca cortar uma página.
    Retorna [(número da primeira página do lote, páginas do lote), ...].
    """
    lotes: list[tuple[int, list[str]]] = []
    atual: list[str] = []
    inicio = 1
    tamanho = 0
    for numero, texto in enumerate(pages, start=1):
        custo = len(texto) + 20
        if atual and tamanho + custo > max_chars:
            lotes.append((inicio, atual))
            atual, inicio, tamanho = [], numero, 0
        atual.append(texto)
        tamanho += custo
    if atual:
        lotes.append((inicio, atual))
    return lotes


def _norm(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto or "")
    base = "".join(c for c in base if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", base).strip().lower()


def merge_extractions(extracoes: Sequence[ExtracaoLLM]) -> ExtracaoLLM:
    """
    Combina extrações de lotes diferentes do mesmo documento.

    Campos escalares ficam com o primeiro valor preenchido; listas são unidas sem
    duplicatas (comparação sem acentos e sem diferença de caixa).
    """
    if len(extracoes) == 1:
        return extracoes[0]

    base = extracoes[0].model_copy(deep=True)
    vistos_cob = {_norm(c.nome) for c in base.coberturas}
    vistos_exc = {(_norm(e.categoria), _norm(e.descricao)[:60]) for e in base.exclusoes}
    vistos_cls = {_norm(c) for c in base.clausulas_especiais}
    ficha = {item.topico: item for item in base.ficha_tecnica}

    for extra in extracoes[1:]:
        for campo in ("dados_apolice", "segurado"):
            alvo, origem = getattr(base, campo), getattr(extra, campo)
            for nome in type(alvo).model_fields:
                if not getattr(alvo, nome) and getattr(origem, nome):
                    setattr(alvo, nome, getattr(origem, nome))

        if not base.tipo_documento:
            base.tipo_documento = extra.tipo_documento
        if not base.observacoes:
            base.observacoes = extra.observacoes

        for cob in extra.coberturas:
            if _norm(cob.nome) not in vistos_cob:
                vistos_cob.add(_norm(cob.nome))
                base.coberturas.append(cob)
        for exc in extra.exclusoes:
            chave = (_norm(exc.categoria), _norm(exc.descricao)[:60])
            if chave not in vistos_exc:
                vistos_exc.add(chave)
                base.exclusoes.append(exc)
        for cls in extra.clausulas_especiais:
            if _norm(cls) not in vistos_cls:
                vistos_cls.add(_norm(cls))
                base.clausulas_especiais.append(cls)
        for item in extra.ficha_tecnica:
            atual = ficha.get(item.topico)
            if item.valor and (atual is None or not atual.valor):
                ficha[item.topico] = item

    base.ficha_tecnica = list(ficha.values())
    return base


# ─── Pós-processamento e verificação de ancoragem ────────────────────────────

def _trecho_confere(trecho: Optional[str], texto_pagina: str) -> bool:
    """Verdadeiro se o trecho citado aparece (de forma substancial) no texto da página."""
    if not trecho or not texto_pagina:
        return False
    alvo, pagina = _norm(trecho), _norm(texto_pagina)
    if alvo in pagina:
        return True
    tokens = re.findall(r"\w+", alvo)
    if len(tokens) < 3:
        return False
    palavras_pagina = set(re.findall(r"\w+", pagina))
    achados = sum(1 for t in tokens if t in palavras_pagina)
    return achados / len(tokens) >= LIMIAR_TRECHO


def _ancorar(fonte: Optional[Fonte], pages: Sequence[str]) -> Optional[Fonte]:
    """Valida a página citada e marca se o trecho foi encontrado no texto dela."""
    if fonte is None:
        return None
    pagina = fonte.pagina if fonte.pagina and 1 <= fonte.pagina <= len(pages) else None
    if pagina is None:
        return Fonte(pagina=None, trecho=fonte.trecho, verificada=False)

    if _trecho_confere(fonte.trecho, pages[pagina - 1]):
        return Fonte(pagina=pagina, trecho=fonte.trecho, verificada=True)

    # O modelo às vezes erra a página por uma unidade: procura nas vizinhas.
    for vizinha in (pagina - 1, pagina + 1):
        if 1 <= vizinha <= len(pages) and _trecho_confere(fonte.trecho, pages[vizinha - 1]):
            return Fonte(pagina=vizinha, trecho=fonte.trecho, verificada=True)
    return Fonte(pagina=pagina, trecho=fonte.trecho, verificada=False)


# Palavras que só enfeitam o nome de uma cobertura ("Extensão de Cobertura para X" = "Extensão para X").
_RUIDO_NOME = frozenset("extensao cobertura coberturas adicional garantia para de da do dos das a o e em".split())
LIMIAR_NOME_SIMILAR = 0.75


def _tokens_nome(nome: str) -> frozenset[str]:
    return frozenset(t for t in re.findall(r"\w+", _norm(nome)) if t not in _RUIDO_NOME)


def _nomes_similares(a: frozenset[str], b: frozenset[str]) -> bool:
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= LIMIAR_NOME_SIMILAR


def deduplicar_coberturas(coberturas: Sequence[CoberturaPrincipal]) -> list[CoberturaPrincipal]:
    """
    Une coberturas que são a mesma com nomes ligeiramente diferentes.

    Documentos D&O costumam listar as extensões num resumo no início e depois as detalham
    nas cláusulas; sem isso a mesma extensão apareceria duas vezes. Fica a versão com a
    descrição mais completa, na posição da primeira ocorrência.
    """
    mantidas: list[CoberturaPrincipal] = []
    chaves: list[frozenset[str]] = []
    for cob in coberturas:
        chave = _tokens_nome(cob.nome)
        for i, existente in enumerate(chaves):
            if _nomes_similares(chave, existente):
                if len(cob.descricao or "") > len(mantidas[i].descricao or ""):
                    mantidas[i] = cob
                break
        else:
            mantidas.append(cob)
            chaves.append(chave)
    return mantidas


def normalizar_extracao(extracao: ExtracaoLLM, pages: Sequence[str]) -> ExtracaoLLM:
    """Garante a ficha completa, descarta tópicos desconhecidos e ancora todas as fontes."""
    extracao.coberturas = deduplicar_coberturas(extracao.coberturas)
    por_topico: dict[str, ItemFicha] = {}
    for item in extracao.ficha_tecnica:
        if item.topico in TOPICOS_FICHA and (item.topico not in por_topico or (item.valor and not por_topico[item.topico].valor)):
            por_topico[item.topico] = item

    ficha: list[ItemFicha] = []
    for chave in TOPICOS_FICHA:
        item = por_topico.get(chave) or ItemFicha(topico=chave, valor=None)
        valor = valor_ou_none(item.valor)
        ficha.append(ItemFicha(topico=chave, valor=valor, fonte=_ancorar(item.fonte, pages) if valor else None))
    extracao.ficha_tecnica = ficha

    for cob in extracao.coberturas:
        cob.fonte = _ancorar(cob.fonte, pages)
    for exc in extracao.exclusoes:
        exc.fonte = _ancorar(exc.fonte, pages)
    return extracao


def qualidade_ancoragem(apolice: ApoliceExtraida) -> dict[str, int]:
    """Quantas fontes citadas foram confirmadas no texto original (métrica de confiança)."""
    fontes = [i.fonte for i in apolice.ficha_tecnica if i.fonte]
    fontes += [c.fonte for c in apolice.coberturas if c.fonte]
    fontes += [e.fonte for e in apolice.exclusoes if e.fonte]
    return {"total": len(fontes), "verificadas": sum(1 for f in fontes if f.verificada)}


# ─── Agente principal ────────────────────────────────────────────────────────

def extract_policy(
    pages: "Sequence[str] | str",
    filename: str = "apolice.pdf",
    provider: str = "google",
    model: str = DEFAULT_MODELS["google"],
    progress: Optional[Callable[[str], None]] = None,
) -> ApoliceExtraida:
    """
    Extrai a estrutura de uma apólice D&O.

    Args:
        pages: texto do documento, uma string por página (ou um texto único).
        filename: nome do arquivo original, para rastreabilidade.
        provider: 'google' | 'openai' | 'anthropic'.
        model: modelo do provedor.
        progress: callback opcional chamado com mensagens de andamento.

    Raises:
        LLMError: se o modelo falhar após as retentativas — nunca devolve um
        resultado vazio em silêncio.
    """
    paginas = [pages] if isinstance(pages, str) else list(pages)
    avisar = progress or (lambda _msg: None)
    system = EXTRACTION_SYSTEM_PROMPT.format(topicos=_topicos_para_prompt())

    limite = MAX_CHARS_POR_CHAMADA.get(provider, 250_000)
    lotes = split_pages(paginas, limite)
    logger.info("Extraindo '%s' (%d páginas) em %d chamada(s) via %s/%s", filename, len(paginas), len(lotes), provider, model)

    def extrair_lote(primeira: int, lote: list[str]) -> ExtracaoLLM:
        # Mantém a numeração real das páginas dentro do lote.
        texto = "\n\n".join(f"[[PÁGINA {primeira + i}]]\n{t.strip()}" for i, t in enumerate(lote))
        usuario = EXTRACTION_USER_TEMPLATE.format(nome=filename, texto=texto)
        return generate_json(system, usuario, ExtracaoLLM, provider, model, max_tokens=24000)

    avisar(f"Analisando com {provider}/{model} — {len(lotes)} parte(s) em paralelo")
    resultados: dict[int, ExtracaoLLM] = {}
    # Os lotes são independentes, então vão em paralelo; o progresso é informado pela
    # thread principal (callbacks de interface não podem ser chamados de threads auxiliares).
    pool = ThreadPoolExecutor(max_workers=min(MAX_PARALELO, len(lotes)))
    try:
        futuros = {pool.submit(extrair_lote, primeira, lote): i for i, (primeira, lote) in enumerate(lotes)}
        for concluido in as_completed(futuros):
            resultados[futuros[concluido]] = concluido.result()  # propaga LLMError
            avisar(f"Parte {len(resultados)}/{len(lotes)} analisada")
    except Exception:
        # Um lote falhou: cancela os que ainda não começaram, sem esperar o restante.
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    pool.shutdown(wait=True)
    # A fusão respeita a ordem original das páginas (a primeira informação preenchida prevalece).
    extracoes = [resultados[i] for i in range(len(lotes))]

    extracao = normalizar_extracao(merge_extractions(extracoes), paginas)

    apolice = ApoliceExtraida(**extracao.model_dump())
    apolice.nome_arquivo = filename
    apolice.total_paginas = len(paginas)
    apolice.paginas = paginas
    apolice.texto_bruto = format_pages_for_llm(paginas)

    ancoragem = qualidade_ancoragem(apolice)
    logger.info(
        "Extração concluída: %d coberturas, %d exclusões, %d/%d fontes verificadas",
        len(apolice.coberturas), len(apolice.exclusoes), ancoragem["verificadas"], ancoragem["total"],
    )
    return apolice
