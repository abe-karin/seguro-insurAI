"""
Schemas Pydantic do domínio: apólice extraída, ficha técnica D&O e comparação.

Todo dado extraído carrega a `Fonte` (página e trecho literal) de onde saiu, o que
permite ao usuário conferir cada informação no documento original.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

# ─── Ficha técnica D&O ───────────────────────────────────────────────────────
# Tópicos fixos que sustentam a comparação: como todos os documentos são lidos
# contra a mesma lista, as respostas ficam alinhadas e comparáveis.
# chave → (rótulo, categoria, descrição usada no prompt de extração)
TOPICOS_FICHA: dict[str, tuple[str, str, str]] = {
    "base_acionamento": (
        "Base de acionamento", "acionamento",
        "Gatilho da cobertura: claims made (reclamações), com notificação, ocorrência etc.",
    ),
    "retroatividade": (
        "Retroatividade", "acionamento",
        "Data ou período de retroatividade: a partir de quando fatos geradores são cobertos.",
    ),
    "prazo_aviso": (
        "Prazo de aviso do sinistro", "acionamento",
        "Prazo para o segurado avisar a seguradora de reclamações ou circunstâncias.",
    ),
    "prazo_complementar": (
        "Prazo complementar de notificação", "acionamento",
        "Período adicional/complementar/estendido de notificação após o fim da vigência.",
    ),
    "pessoas_seguradas": (
        "Pessoas seguradas", "cobertura",
        "Quem é segurado: administradores, ex-administradores, herdeiros, controladas, empregados.",
    ),
    "cobertura_side_a": (
        "Side A (administradores)", "cobertura",
        "Proteção direta dos administradores quando a empresa não indeniza.",
    ),
    "cobertura_side_b": (
        "Side B (reembolso à empresa)", "cobertura",
        "Reembolso à empresa por valores pagos em favor dos administradores.",
    ),
    "cobertura_side_c": (
        "Side C (pessoa jurídica)", "cobertura",
        "Cobertura da própria pessoa jurídica (entity coverage), se existir.",
    ),
    "custos_defesa": (
        "Custos de defesa", "cobertura",
        "Cobertura de custas e honorários de defesa, inclusive adiantamento.",
    ),
    "escolha_defesa": (
        "Escolha e anuência da defesa", "processo",
        "Quem escolhe os advogados e se a seguradora deve consentir nas despesas e acordos.",
    ),
    "multas_penalidades": (
        "Multas e penalidades", "cobertura",
        "Tratamento de multas, penalidades administrativas e valores não indenizáveis.",
    ),
    "limite_sublimites": (
        "Limite e sublimites", "limite",
        "Limite máximo de garantia, limites agregados e sublimites por cobertura.",
    ),
    "franquia": (
        "Franquia / retenção", "limite",
        "Franquia, participação obrigatória ou retenção aplicável.",
    ),
    "exclusao_dolo": (
        "Exclusão: dolo e fraude", "exclusao",
        "Exclusão de atos dolosos, fraudulentos ou criminosos e quando se torna aplicável.",
    ),
    "exclusao_vantagem": (
        "Exclusão: vantagem indevida", "exclusao",
        "Exclusão de vantagem pessoal ou remuneração ilegítima.",
    ),
    "exclusao_poluicao": (
        "Exclusão: poluição / ambiental", "exclusao",
        "Exclusão de danos ambientais ou poluição.",
    ),
    "exclusao_anteriores": (
        "Exclusão: fatos anteriores", "exclusao",
        "Exclusão de reclamações, circunstâncias ou processos anteriores/pendentes.",
    ),
    "exclusao_entre_segurados": (
        "Exclusão: reclamações entre segurados", "exclusao",
        "Exclusão de reclamações movidas por um segurado contra outro (insured vs insured).",
    ),
    "mudanca_controle": (
        "Mudança de controle", "processo",
        "Efeito de aquisição, fusão ou mudança de controle sobre a cobertura (run-off).",
    ),
    "rateio": (
        "Rateio e alocação", "processo",
        "Regras de rateio de perdas entre segurados e entre coberturas.",
    ),
    "cancelamento": (
        "Cancelamento e rescisão", "processo",
        "Condições para cancelamento ou rescisão pelo segurado e pela seguradora.",
    ),
    "arbitragem_foro": (
        "Arbitragem e foro", "processo",
        "Cláusula de arbitragem, foro de eleição e lei aplicável.",
    ),
    "territorialidade": (
        "Território", "processo",
        "Abrangência territorial da cobertura.",
    ),
}

# Tópicos agregados, calculados a partir das listas extraídas.
TOPICOS_AGREGADOS: dict[str, tuple[str, str]] = {
    "lista_coberturas": ("Coberturas listadas", "cobertura"),
    "lista_exclusoes": ("Exclusões listadas", "exclusao"),
    "lista_clausulas": ("Cláusulas especiais", "processo"),
}

CATEGORIAS = {
    "acionamento": "Acionamento",
    "cobertura": "Coberturas",
    "limite": "Limites e franquias",
    "exclusao": "Exclusões",
    "processo": "Processo e condições",
    "cadastral": "Dados cadastrais",
}


def rotulo_topico(chave: str) -> str:
    if chave in TOPICOS_FICHA:
        return TOPICOS_FICHA[chave][0]
    if chave in TOPICOS_AGREGADOS:
        return TOPICOS_AGREGADOS[chave][0]
    return chave.replace("_", " ").capitalize()


def categoria_topico(chave: str) -> str:
    if chave in TOPICOS_FICHA:
        return TOPICOS_FICHA[chave][1]
    if chave in TOPICOS_AGREGADOS:
        return TOPICOS_AGREGADOS[chave][1]
    return "cadastral"


# ─── Extração ────────────────────────────────────────────────────────────────

class Fonte(BaseModel):
    pagina: Optional[int] = Field(default=None, description="Número da página de onde a informação foi extraída")
    trecho: Optional[str] = Field(default=None, description="Citação literal curta (até 200 caracteres) que sustenta a informação")
    verificada: Optional[bool] = Field(
        default=None, description="Preenchido pelo sistema (não pelo modelo): o trecho foi encontrado na página citada"
    )


class CoberturaPrincipal(BaseModel):
    nome: str = Field(description="Nome da cobertura")
    descricao: Optional[str] = Field(default=None, description="Descrição da cobertura")
    limite: Optional[str] = Field(default=None, description="Limite de indenização")
    franquia: Optional[str] = Field(default=None, description="Franquia/dedutível aplicável")
    retroatividade: Optional[str] = Field(default=None, description="Data de retroatividade")
    fonte: Optional[Fonte] = None


class Exclusao(BaseModel):
    categoria: str = Field(description="Categoria da exclusão (ex.: dolo, poluição)")
    descricao: Optional[str] = Field(default=None, description="Descrição da exclusão")
    fonte: Optional[Fonte] = None


class DadosSegurado(BaseModel):
    nome_segurado: Optional[str] = Field(default=None, description="Nome/razão social do segurado")
    cnpj: Optional[str] = Field(default=None, description="CNPJ do segurado")
    setor: Optional[str] = Field(default=None, description="Setor de atividade")


class DadosApolice(BaseModel):
    numero_apolice: Optional[str] = Field(default=None, description="Número da apólice")
    seguradora: Optional[str] = Field(default=None, description="Nome da seguradora")
    vigencia_inicio: Optional[str] = Field(default=None, description="Início de vigência")
    vigencia_fim: Optional[str] = Field(default=None, description="Fim de vigência")
    premio: Optional[str] = Field(default=None, description="Prêmio total")
    limite_global: Optional[str] = Field(default=None, description="Limite máximo de garantia global")
    base_acionamento: Optional[str] = Field(
        default=None, description="Base de acionamento: claims made (reclamação) ou ocorrência"
    )
    processo_susep: Optional[str] = Field(default=None, description="Número do processo SUSEP, se citado")
    versao_documento: Optional[str] = Field(default=None, description="Versão ou data de vigência do documento")


class ItemFicha(BaseModel):
    topico: str = Field(description="Chave do tópico da ficha técnica, exatamente como listada")
    valor: Optional[str] = Field(
        default=None,
        description="Resumo objetivo do que o documento diz sobre o tópico; null se não tratar do assunto",
    )
    fonte: Optional[Fonte] = None


class ExtracaoLLM(BaseModel):
    """Parte da apólice produzida pelo modelo (é o schema pedido ao LLM)."""

    tipo_documento: Optional[str] = Field(
        default=None, description="'apolice' (com dados do segurado), 'condicoes_gerais' ou 'outro'"
    )
    dados_apolice: DadosApolice = Field(default_factory=DadosApolice)
    segurado: DadosSegurado = Field(default_factory=DadosSegurado)
    coberturas: list[CoberturaPrincipal] = Field(default_factory=list)
    exclusoes: list[Exclusao] = Field(default_factory=list)
    clausulas_especiais: list[str] = Field(default_factory=list, description="Cláusulas especiais ou endossos relevantes")
    ficha_tecnica: list[ItemFicha] = Field(default_factory=list)
    observacoes: Optional[str] = Field(default=None, description="Observações gerais sobre o documento")


class ApoliceExtraida(ExtracaoLLM):
    """Apólice completa: extração do LLM + dados do documento de origem."""

    nome_arquivo: Optional[str] = None
    total_paginas: Optional[int] = None
    texto_bruto: Optional[str] = Field(default=None, description="Texto bruto (não persistido no JSON)")
    paginas: list[str] = Field(default_factory=list, description="Texto por página (persistido à parte)")

    def ficha_por_topico(self) -> dict[str, ItemFicha]:
        return {item.topico: item for item in self.ficha_tecnica}


# ─── Comparação ──────────────────────────────────────────────────────────────

class ValorApolice(BaseModel):
    apolice: str
    valor: Optional[str] = None
    pagina: Optional[int] = None


class DiferencaTopico(BaseModel):
    topico: str
    rotulo: str
    categoria: str
    valores: list[ValorApolice]
    relevancia: str = Field(description="alta | media | baixa")
    comentario: str
    mais_favoravel: Optional[str] = Field(
        default=None, description="Apólice mais favorável ao segurado neste tópico, se houver"
    )


class AnaliseTopico(BaseModel):
    """Julgamento do LLM sobre um tópico cujos valores já foram extraídos."""

    topico: str
    relevancia: str = Field(description="alta | media | baixa")
    comentario: str
    mais_favoravel: Optional[str] = None


class AnaliseLLM(BaseModel):
    topicos: list[AnaliseTopico] = Field(default_factory=list)
    resumo_executivo: str = ""
    recomendacao: str = ""


class RelatorioComparativo(BaseModel):
    """Resultado da comparação entre duas ou mais apólices D&O."""

    apolices: list[str]
    diferencas: list[DiferencaTopico] = Field(default_factory=list)
    topicos_iguais: list[str] = Field(default_factory=list, description="Tópicos sem divergência relevante")
    resumo_executivo: str
    recomendacao: str
    modo: str = Field(default="llm", description="'llm' ou 'deterministico'")
    modelo: Optional[str] = None

    def por_categoria(self) -> dict[str, list[DiferencaTopico]]:
        grupos: dict[str, list[DiferencaTopico]] = {}
        for diff in self.diferencas:
            grupos.setdefault(diff.categoria, []).append(diff)
        return grupos
