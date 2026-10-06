"""Apólices fictícias usadas nos testes (sem rede e sem chave de API)."""
from __future__ import annotations

from models.schemas import (
    ApoliceExtraida,
    CoberturaPrincipal,
    DadosApolice,
    DadosSegurado,
    Exclusao,
    Fonte,
    ItemFicha,
)

PAGINAS_ALFA = [
    "CONDICOES GERAIS ALFA SEGUROS\nA cobertura opera na base de reclamacoes feitas (claims made) durante a vigencia.",
    "Prazo de aviso: o segurado deve avisar a seguradora em ate 30 dias da reclamacao.\n"
    "Os custos de defesa sao adiantados pela seguradora.",
    "Exclusoes: nao ha cobertura para atos dolosos apos decisao judicial transitada em julgado.",
]

PAGINAS_BETA = [
    "CONDICOES GERAIS BETA SEGUROS\nBase de acionamento: ocorrencia do ato danoso.",
    "O segurado deve comunicar a reclamacao em ate 10 dias.\nNao ha adiantamento de custos de defesa.",
    "Exclusoes: atos dolosos, poluicao e reclamacoes entre segurados.",
]


def _ficha(valores: dict[str, tuple[str, int, str]]) -> list[ItemFicha]:
    return [
        ItemFicha(topico=topico, valor=valor, fonte=Fonte(pagina=pagina, trecho=trecho))
        for topico, (valor, pagina, trecho) in valores.items()
    ]


def apolice_alfa() -> ApoliceExtraida:
    return ApoliceExtraida(
        nome_arquivo="alfa.pdf",
        tipo_documento="condicoes_gerais",
        total_paginas=3,
        paginas=list(PAGINAS_ALFA),
        dados_apolice=DadosApolice(seguradora="Alfa Seguros", limite_global="R$ 10.000.000,00"),
        segurado=DadosSegurado(),
        coberturas=[
            CoberturaPrincipal(nome="Side A", descricao="Protecao dos administradores", fonte=Fonte(pagina=1, trecho="claims made")),
            CoberturaPrincipal(nome="Custos de defesa", descricao="Adiantamento de custos"),
        ],
        exclusoes=[Exclusao(categoria="Dolo", descricao="Atos dolosos com decisao transitada")],
        clausulas_especiais=["Periodo complementar de 90 dias"],
        ficha_tecnica=_ficha(
            {
                "base_acionamento": ("Claims made", 1, "base de reclamacoes feitas (claims made)"),
                "prazo_aviso": ("30 dias", 2, "avisar a seguradora em ate 30 dias"),
                "custos_defesa": ("Adiantados pela seguradora", 2, "custos de defesa sao adiantados"),
                "exclusao_dolo": ("Apos decisao judicial transitada em julgado", 3, "atos dolosos apos decisao judicial"),
            }
        ),
    )


def apolice_beta() -> ApoliceExtraida:
    return ApoliceExtraida(
        nome_arquivo="beta.pdf",
        tipo_documento="condicoes_gerais",
        total_paginas=3,
        paginas=list(PAGINAS_BETA),
        dados_apolice=DadosApolice(seguradora="Beta Seguros", limite_global="R$ 10.000.000,00"),
        segurado=DadosSegurado(),
        coberturas=[CoberturaPrincipal(nome="Side A", descricao="Protecao dos administradores")],
        exclusoes=[
            Exclusao(categoria="Dolo", descricao="Atos dolosos"),
            Exclusao(categoria="Poluicao", descricao="Danos ambientais"),
        ],
        clausulas_especiais=[],
        ficha_tecnica=_ficha(
            {
                "base_acionamento": ("Ocorrencia", 1, "Base de acionamento: ocorrencia"),
                "prazo_aviso": ("10 dias", 2, "comunicar a reclamacao em ate 10 dias"),
                "exclusao_dolo": ("Atos dolosos, sem exigir decisao judicial", 3, "atos dolosos"),
                "exclusao_poluicao": ("Excluida", 3, "poluicao"),
            }
        ),
    )
