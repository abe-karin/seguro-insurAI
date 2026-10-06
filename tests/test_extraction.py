"""Testes do agente de extração: divisão em lotes, fusão, ancoragem das fontes e fluxo com LLM simulado."""
import unittest
from unittest import mock

from agents import extraction_agent as ea
from models.schemas import ExtracaoLLM, Fonte, ItemFicha, TOPICOS_FICHA, CoberturaPrincipal, Exclusao
from tests.fixtures import PAGINAS_ALFA


class TestDivisaoEmLotes(unittest.TestCase):
    def test_nunca_corta_uma_pagina(self):
        paginas = ["a" * 100, "b" * 100, "c" * 100, "d" * 100]
        lotes = ea.split_pages(paginas, max_chars=250)
        self.assertEqual([len(l) for _, l in lotes], [2, 2])
        self.assertEqual("".join("".join(l) for _, l in lotes), "".join(paginas))

    def test_numeracao_da_primeira_pagina_de_cada_lote(self):
        lotes = ea.split_pages(["x" * 100] * 5, max_chars=250)
        self.assertEqual([primeira for primeira, _ in lotes], [1, 3, 5])

    def test_documento_pequeno_gera_um_unico_lote(self):
        self.assertEqual(len(ea.split_pages(PAGINAS_ALFA, max_chars=100_000)), 1)


class TestFusao(unittest.TestCase):
    def test_remove_duplicatas_ignorando_acentos_e_caixa(self):
        a = ExtracaoLLM(coberturas=[CoberturaPrincipal(nome="Custos de Defesa", descricao="x")])
        b = ExtracaoLLM(coberturas=[
            CoberturaPrincipal(nome="custos de defesa", descricao="y"),
            CoberturaPrincipal(nome="Side A", descricao="z"),
        ])
        fundida = ea.merge_extractions([a, b])
        self.assertEqual([c.nome for c in fundida.coberturas], ["Custos de Defesa", "Side A"])

    def test_preenche_campos_vazios_com_os_do_lote_seguinte(self):
        a = ExtracaoLLM()
        b = ExtracaoLLM()
        b.dados_apolice.seguradora = "Alfa"
        self.assertEqual(ea.merge_extractions([a, b]).dados_apolice.seguradora, "Alfa")

    def test_ficha_prefere_valor_preenchido(self):
        a = ExtracaoLLM(ficha_tecnica=[ItemFicha(topico="franquia", valor=None)])
        b = ExtracaoLLM(ficha_tecnica=[ItemFicha(topico="franquia", valor="R$ 50 mil")])
        fundida = ea.merge_extractions([a, b])
        self.assertEqual(fundida.ficha_tecnica[0].valor, "R$ 50 mil")

    def test_exclusoes_repetidas_sao_unificadas(self):
        e = Exclusao(categoria="Dolo", descricao="Atos dolosos")
        fundida = ea.merge_extractions([ExtracaoLLM(exclusoes=[e]), ExtracaoLLM(exclusoes=[e])])
        self.assertEqual(len(fundida.exclusoes), 1)


class TestDeduplicarCoberturas(unittest.TestCase):
    def _cob(self, nome, descricao="x"):
        return CoberturaPrincipal(nome=nome, descricao=descricao)

    def test_resumo_e_clausula_da_mesma_extensao_viram_uma_so(self):
        saida = ea.deduplicar_coberturas([
            self._cob("Extensão de Cobertura para Multas e Penalidades", "curta"),
            self._cob("Extensão para Multas e Penalidades", "descrição bem mais completa da cláusula"),
        ])
        self.assertEqual(len(saida), 1)
        self.assertEqual(saida[0].descricao, "descrição bem mais completa da cláusula")  # fica a mais completa

    def test_coberturas_diferentes_nao_sao_unidas(self):
        saida = ea.deduplicar_coberturas([
            self._cob("Extensão para Custos de Defesa"),
            self._cob("Danos Ambientais — Custos de Defesa"),
            self._cob("Extensão para Multas e Penalidades"),
        ])
        self.assertEqual(len(saida), 3)

    def test_preserva_a_ordem_da_primeira_ocorrencia(self):
        saida = ea.deduplicar_coberturas([self._cob("Side A"), self._cob("Side B"), self._cob("Side A")])
        self.assertEqual([c.nome for c in saida], ["Side A", "Side B"])


class TestAncoragem(unittest.TestCase):
    def test_trecho_literal_e_verificado(self):
        fonte = ea._ancorar(Fonte(pagina=2, trecho="avisar a seguradora em ate 30 dias"), PAGINAS_ALFA)
        self.assertTrue(fonte.verificada)
        self.assertEqual(fonte.pagina, 2)

    def test_trecho_inventado_nao_e_verificado(self):
        fonte = ea._ancorar(Fonte(pagina=2, trecho="a cobertura abrange ataques ciberneticos globais"), PAGINAS_ALFA)
        self.assertFalse(fonte.verificada)

    def test_corrige_pagina_errada_por_uma_unidade(self):
        fonte = ea._ancorar(Fonte(pagina=1, trecho="avisar a seguradora em ate 30 dias"), PAGINAS_ALFA)
        self.assertTrue(fonte.verificada)
        self.assertEqual(fonte.pagina, 2)

    def test_pagina_fora_do_documento_e_descartada(self):
        fonte = ea._ancorar(Fonte(pagina=99, trecho="claims made"), PAGINAS_ALFA)
        self.assertIsNone(fonte.pagina)
        self.assertFalse(fonte.verificada)

    def test_acentos_nao_atrapalham(self):
        fonte = ea._ancorar(Fonte(pagina=1, trecho="base de reclamações feitas (claims made)"), PAGINAS_ALFA)
        self.assertTrue(fonte.verificada)


class TestNormalizacao(unittest.TestCase):
    def test_ficha_sempre_completa_e_sem_topicos_desconhecidos(self):
        extracao = ExtracaoLLM(ficha_tecnica=[
            ItemFicha(topico="base_acionamento", valor="Claims made", fonte=Fonte(pagina=1, trecho="claims made")),
            ItemFicha(topico="topico_inventado", valor="x"),
        ])
        saida = ea.normalizar_extracao(extracao, PAGINAS_ALFA)
        self.assertEqual([i.topico for i in saida.ficha_tecnica], list(TOPICOS_FICHA))
        por_topico = {i.topico: i for i in saida.ficha_tecnica}
        self.assertEqual(por_topico["base_acionamento"].valor, "Claims made")
        self.assertIsNone(por_topico["franquia"].valor)


class TestFluxoComLLMSimulado(unittest.TestCase):
    def test_extract_policy_monta_apolice_completa(self):
        resposta = ExtracaoLLM(
            tipo_documento="condicoes_gerais",
            coberturas=[CoberturaPrincipal(nome="Side A", descricao="Administradores")],
            ficha_tecnica=[ItemFicha(topico="prazo_aviso", valor="30 dias", fonte=Fonte(pagina=2, trecho="em ate 30 dias"))],
        )
        resposta.dados_apolice.seguradora = "Alfa Seguros"
        with mock.patch.object(ea, "generate_json", return_value=resposta) as chamada:
            apolice = ea.extract_policy(PAGINAS_ALFA, filename="alfa.pdf", provider="google", model="m")

        self.assertEqual(chamada.call_count, 1)  # documento pequeno: uma única chamada
        self.assertEqual(apolice.nome_arquivo, "alfa.pdf")
        self.assertEqual(apolice.total_paginas, 3)
        self.assertEqual(apolice.paginas, PAGINAS_ALFA)
        self.assertIn("[[PÁGINA 2]]", chamada.call_args.args[1])
        self.assertEqual(ea.qualidade_ancoragem(apolice), {"total": 1, "verificadas": 1})

    def test_documento_grande_e_dividido_em_varias_chamadas(self):
        paginas = ["texto " * 100] * 6
        with mock.patch.dict(ea.MAX_CHARS_POR_CHAMADA, {"google": 1500}), \
                mock.patch.object(ea, "generate_json", return_value=ExtracaoLLM()) as chamada:
            ea.extract_policy(paginas, provider="google", model="m")
        self.assertGreater(chamada.call_count, 1)

    def test_falha_do_llm_nao_e_silenciada(self):
        from agents.llm_client import LLMError

        with mock.patch.object(ea, "generate_json", side_effect=LLMError("indisponível")):
            with self.assertRaises(LLMError):
                ea.extract_policy(PAGINAS_ALFA, provider="google", model="m")


if __name__ == "__main__":
    unittest.main()
