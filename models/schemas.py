"""
Schemas Pydantic para representação estruturada de apólices D&O.
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class CoberturaPrincipal(BaseModel):
    nome: str = Field(description="Nome da cobertura")
    descricao: str = Field(description="Descrição da cobertura")
    limite: Optional[str] = Field(default=None, description="Limite de indenização")
    franquia: Optional[str] = Field(default=None, description="Franquia/Dedutível aplicável")
    retroatividade: Optional[str] = Field(default=None, description="Data de retroatividade")


class Exclusao(BaseModel):
    categoria: str = Field(description="Categoria da exclusão (ex: fraude, dolo, etc.)")
    descricao: str = Field(description="Descrição da exclusão")


class DadosSegurado(BaseModel):
    nome_segurado: Optional[str] = Field(default=None, description="Nome/Razão social do segurado")
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
        default=None,
        description="Base de acionamento: claims made (reclamação) ou ocorrência"
    )


class ApoliceExtraida(BaseModel):
    """Representação completa e estruturada de uma apólice D&O extraída."""
    dados_apolice: DadosApolice = Field(description="Dados cadastrais da apólice")
    segurado: DadosSegurado = Field(description="Dados do segurado")
    coberturas: list[CoberturaPrincipal] = Field(
        default_factory=list,
        description="Lista de coberturas identificadas"
    )
    exclusoes: list[Exclusao] = Field(
        default_factory=list,
        description="Lista de exclusões identificadas"
    )
    clausulas_especiais: list[str] = Field(
        default_factory=list,
        description="Cláusulas especiais ou endossos relevantes"
    )
    observacoes: Optional[str] = Field(
        default=None,
        description="Observações gerais sobre a apólice"
    )
    texto_bruto: Optional[str] = Field(
        default=None,
        description="Texto bruto extraído do documento (não enviado ao LLM)"
    )
    nome_arquivo: Optional[str] = Field(default=None)


class DiferencaCobertura(BaseModel):
    campo: str
    valor_a: Optional[str]
    valor_b: Optional[str]
    relevancia: str = Field(description="alta | media | baixa")
    comentario: str


class RelatorioComparativo(BaseModel):
    """Resultado da comparação entre duas apólices D&O."""
    apolice_a: str = Field(description="Identificador/nome da apólice A")
    apolice_b: str = Field(description="Identificador/nome da apólice B")
    diferencas_cadastrais: list[DiferencaCobertura] = Field(default_factory=list)
    diferencas_coberturas: list[DiferencaCobertura] = Field(default_factory=list)
    diferencas_exclusoes: list[DiferencaCobertura] = Field(default_factory=list)
    diferencas_limites: list[DiferencaCobertura] = Field(default_factory=list)
    resumo_executivo: str = Field(description="Resumo textual das principais diferenças")
    recomendacao: str = Field(description="Recomendação técnica baseada na comparação")
