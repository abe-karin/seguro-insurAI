"""
Script de demonstração — popula o banco com duas apólices D&O sintéticas
para que a interface possa ser explorada sem um arquivo PDF real.

Uso:
    python scripts/seed_demo_data.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from models.schemas import (
    ApoliceExtraida, DadosApolice, DadosSegurado,
    CoberturaPrincipal, Exclusao
)
from storage.database import save_policy


def make_apolice_zurich() -> ApoliceExtraida:
    return ApoliceExtraida(
        nome_arquivo="apolice_zurich_demo.pdf",
        dados_apolice=DadosApolice(
            numero_apolice="ZU-DO-2024-00123",
            seguradora="Zurich Seguros S.A.",
            vigencia_inicio="01/01/2024",
            vigencia_fim="31/12/2024",
            premio="R$ 185.000,00",
            limite_global="R$ 10.000.000,00",
            base_acionamento="Claims Made (Reclamação Feita)",
        ),
        segurado=DadosSegurado(
            nome_segurado="TechCorp Brasil S.A.",
            cnpj="12.345.678/0001-99",
            setor="Tecnologia da Informação",
        ),
        coberturas=[
            CoberturaPrincipal(
                nome="Side A — Proteção Individual de Administradores",
                descricao=(
                    "Cobre perdas sofridas pelos administradores segurados quando a empresa "
                    "não puder ou não quiser indenizá-los. Inclui honorários advocatícios, "
                    "multas administrativas e despesas de defesa."
                ),
                limite="R$ 5.000.000,00",
                franquia="R$ 50.000,00",
                retroatividade="01/01/2020",
            ),
            CoberturaPrincipal(
                nome="Side B — Reembolso à Empresa",
                descricao=(
                    "Reembolsa a empresa pelos valores pagos em defesa dos administradores "
                    "quando a empresa exerce o direito de indenização (indemnification)."
                ),
                limite="R$ 5.000.000,00",
                franquia="R$ 100.000,00",
                retroatividade="01/01/2020",
            ),
            CoberturaPrincipal(
                nome="Side C — Proteção da Entidade (Securities Claims)",
                descricao=(
                    "Cobre a própria entidade em ações relacionadas a valores mobiliários "
                    "movidas em conjunto contra administradores e a companhia."
                ),
                limite="R$ 2.000.000,00",
                franquia="R$ 200.000,00",
                retroatividade=None,
            ),
        ],
        exclusoes=[
            Exclusao(
                categoria="Atos Desonestos / Fraude",
                descricao="Danos resultantes de atos desonestos, fraudulentos ou criminosos comprovados judicialmente.",
            ),
            Exclusao(
                categoria="Proveito Ilícito",
                descricao="Benefícios pessoais obtidos de forma ilícita por administradores segurados.",
            ),
            Exclusao(
                categoria="Danos Corporais / Materiais",
                descricao="Danos corporais, materiais ou morais diretos causados a terceiros.",
            ),
            Exclusao(
                categoria="Poluição",
                descricao="Reclamações relacionadas a danos ambientais ou poluição, salvo cobertura específica.",
            ),
            Exclusao(
                categoria="Insolvência / Falência",
                descricao="Reclamações decorrentes de insolvência ou falência da empresa segurada.",
            ),
        ],
        clausulas_especiais=[
            "Advance Payment: adiantamento de custos de defesa antes do julgamento definitivo",
            "Run-off automático de 12 meses em caso de mudança de controle",
            "Severabilidade: o conhecimento de um segurado não é imputado aos demais",
            "Período de descoberta estendido opcional (ERP) de até 36 meses",
        ],
        observacoes=(
            "Apólice adequada para companhias de tecnologia com exposição a reclamações de "
            "acionistas e reguladores. Limite global compartilhado entre Sides A, B e C."
        ),
    )


def make_apolice_aig() -> ApoliceExtraida:
    return ApoliceExtraida(
        nome_arquivo="apolice_aig_demo.pdf",
        dados_apolice=DadosApolice(
            numero_apolice="AIG-DO-2024-00456",
            seguradora="AIG Seguros Brasil S.A.",
            vigencia_inicio="01/01/2024",
            vigencia_fim="31/12/2024",
            premio="R$ 210.000,00",
            limite_global="R$ 15.000.000,00",
            base_acionamento="Claims Made (Reclamação Feita)",
        ),
        segurado=DadosSegurado(
            nome_segurado="TechCorp Brasil S.A.",
            cnpj="12.345.678/0001-99",
            setor="Tecnologia da Informação",
        ),
        coberturas=[
            CoberturaPrincipal(
                nome="Side A — Proteção Individual de Administradores",
                descricao=(
                    "Cobertura individual para diretores e conselheiros, sem sublimite "
                    "específico — compartilha o limite global. Inclui criptoativos e NFTs "
                    "como ativos sob gestão."
                ),
                limite="Limite global compartilhado",
                franquia="R$ 25.000,00",
                retroatividade="01/01/2019",
            ),
            CoberturaPrincipal(
                nome="Side B — Reembolso à Empresa",
                descricao=(
                    "Reembolso à empresa pelos gastos incorridos na defesa de administradores, "
                    "incluindo honorários periciais e custos de investigação regulatória."
                ),
                limite="Limite global compartilhado",
                franquia="R$ 150.000,00",
                retroatividade="01/01/2019",
            ),
            CoberturaPrincipal(
                nome="Cobertura de Investigação Regulatória",
                descricao=(
                    "Cobre custos de defesa em investigações conduzidas por órgãos reguladores "
                    "(CVM, BACEN, CADE, TCU) antes mesmo de uma reclamação formal."
                ),
                limite="R$ 1.500.000,00",
                franquia="R$ 50.000,00",
                retroatividade=None,
            ),
            CoberturaPrincipal(
                nome="Cobertura de Crise / Relações Públicas",
                descricao=(
                    "Cobre honorários de consultores de relações públicas em caso de crise "
                    "reputacional relacionada a reclamações cobertas."
                ),
                limite="R$ 500.000,00",
                franquia="Sem franquia",
                retroatividade=None,
            ),
        ],
        exclusoes=[
            Exclusao(
                categoria="Atos Desonestos / Fraude",
                descricao="Danos resultantes de atos fraudulentos ou criminosos após sentença transitada em julgado.",
            ),
            Exclusao(
                categoria="Proveito Ilícito",
                descricao="Benefícios pessoais ilícitos confirmados em processo judicial.",
            ),
            Exclusao(
                categoria="Reclamações Entre Segurados",
                descricao="Ações movidas por um segurado contra outro segurado da mesma apólice.",
            ),
            Exclusao(
                categoria="Propriedade Intelectual",
                descricao=(
                    "Reclamações por violação de patentes, marcas ou direitos autorais não "
                    "relacionadas a responsabilidade de administradores."
                ),
            ),
        ],
        clausulas_especiais=[
            "Side A DIC (Difference-in-Conditions): cobertura independente mesmo com restrições do Side B",
            "Advance Payment sem dedutível para custos de defesa de diretores individuais",
            "Severabilidade plena — dolo de um não contamina cobertura dos demais",
            "Período de descoberta estendido opcional: 12, 24 ou 36 meses",
            "Cobertura para subsidiárias adquiridas automaticamente por 90 dias",
            "Cláusula de arbitragem prevista para disputas acima de R$ 500.000",
        ],
        observacoes=(
            "Apólice com limite superior (R$ 15M vs R$ 10M) e cobertura adicional de crise "
            "e investigação regulatória. Prêmio 13,5% superior. Franquia do Side A menor "
            "(R$ 25k vs R$ 50k), o que favorece proteção individual de administradores."
        ),
    )


def seed():
    a1 = make_apolice_zurich()
    a2 = make_apolice_aig()
    id1 = save_policy(a1)
    id2 = save_policy(a2)
    print(f"[OK] Apolice Zurich salva com ID #{id1}")
    print(f"[OK] Apolice AIG salva com ID #{id2}")
    print("Abra a interface e compare as apolices na aba 'Comparar Apolices'.")


if __name__ == "__main__":
    seed()
