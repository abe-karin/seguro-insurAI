"""Testes do agente de comparação: alinhamento, modo determinístico e análise por LLM simulado."""
import unittest
from unittest import mock

from agents import comparison_agent as ca
from agents.llm_client import LLMError
from models.schemas import AnaliseLLM, AnaliseTopico
from tests.fixtures import apolice_alfa, apolice_beta


class TestAlinhamento(unittest.TestCase):
    def test_nomes_sao_unicos(self):
        nomes = ca.nomes_unicos([apolice_alfa(), apolice_alfa()])
        self.assertEqual(nomes, ["Alfa Seguros", "Alfa Seguros (2)"])

    def test_valor_vem_da_ficha_com_a_pagina(self):
        ap = apolice_alfa()
        valor = ca._valores_do_topico("prazo_aviso", ap, "Alfa")
        self.assertEqual((valor.valor, valor.pagina), ("30 dias", 2))

    def test_topico_nao_tratado_fica_vazio(self):
        valor = ca._valores_do_topico("franquia", apolice_alfa(), "Alfa")
        self.assertIsNone(valor.valor)

    def test_todos_os_topicos_alinhados_para_cada_apolice(self):
        alinhados = ca.alinhar_topicos([apolice_alfa(), apolice_beta()], ["A", "B"])
        self.assertTrue(all(len(v) == 2 for v in alinhados.values()))
        self.assertIn("lista_exclusoes", alinhados)


class TestDeterministico(unittest.TestCase):
    def setUp(self):
        self.rel = ca.comparar_apolices([apolice_alfa(), apolice_beta()], use_llm=False)

    def test_aponta_topicos_divergentes(self):
        topicos = {d.topico for d in self.rel.diferencas}
        self.assertTrue({"base_acionamento", "prazo_aviso", "custos_defesa", "exclusao_poluicao"} <= topicos)
        self.assertEqual(self.rel.modo, "deterministico")

    def test_topico_igual_nao_vira_diferenca(self):
        topicos = {d.topico for d in self.rel.diferencas}
        self.assertNotIn("limite_global", topicos)
        self.assertIn("Limite global", self.rel.topicos_iguais)

    def test_topico_ausente_em_uma_apolice_e_sinalizado(self):
        diff = next(d for d in self.rel.diferencas if d.topico == "custos_defesa")
        self.assertIn("Beta Seguros", diff.comentario)

    def test_listas_apontam_itens_exclusivos(self):
        diff = next(d for d in self.rel.diferencas if d.topico == "lista_exclusoes")
        self.assertIn("Poluicao", diff.comentario)

    def test_exige_pelo_menos_duas_apolices(self):
        with self.assertRaises(ValueError):
            ca.comparar_apolices([apolice_alfa()])

    def test_funciona_com_tres_apolices(self):
        rel = ca.comparar_apolices([apolice_alfa(), apolice_beta(), apolice_alfa()], use_llm=False)
        self.assertEqual(len(rel.apolices), 3)
        self.assertTrue(all(len(d.valores) == 3 for d in rel.diferencas))


class TestComLLMSimulado(unittest.TestCase):
    def _analise(self, topicos):
        return AnaliseLLM(topicos=topicos, resumo_executivo="Resumo X", recomendacao="Recomendação Y")

    def test_llm_define_relevancia_e_apolice_favoravel_sem_alterar_valores(self):
        analise = self._analise([
            AnaliseTopico(topico="prazo_aviso", relevancia="alta", comentario="Prazo muito menor na Beta.", mais_favoravel="Alfa Seguros"),
            AnaliseTopico(topico="base_acionamento", relevancia="alta", comentario="Gatilho diferente."),
        ])
        with mock.patch.object(ca, "generate_json_ex", return_value=(analise, "modelo-x")):
            rel = ca.comparar_apolices([apolice_alfa(), apolice_beta()], provider="google", model="m")

        self.assertEqual(rel.modo, "llm")
        self.assertEqual(rel.modelo, "modelo-x")
        self.assertEqual(rel.resumo_executivo, "Resumo X")
        diff = next(d for d in rel.diferencas if d.topico == "prazo_aviso")
        self.assertEqual(diff.mais_favoravel, "Alfa Seguros")
        self.assertEqual({v.valor for v in diff.valores}, {"30 dias", "10 dias"})  # valores seguem os extraídos
        self.assertEqual(rel.diferencas[0].relevancia, "alta")  # ordenado por relevância

    def test_apolice_favoravel_inexistente_e_descartada(self):
        analise = self._analise([AnaliseTopico(topico="prazo_aviso", relevancia="alta", comentario="x", mais_favoravel="Seguradora Inventada")])
        with mock.patch.object(ca, "generate_json_ex", return_value=(analise, "m")):
            rel = ca.comparar_apolices([apolice_alfa(), apolice_beta()])
        self.assertIsNone(next(d for d in rel.diferencas if d.topico == "prazo_aviso").mais_favoravel)

    def test_relevancia_invalida_vira_media(self):
        analise = self._analise([AnaliseTopico(topico="prazo_aviso", relevancia="critica", comentario="x")])
        with mock.patch.object(ca, "generate_json_ex", return_value=(analise, "m")):
            rel = ca.comparar_apolices([apolice_alfa(), apolice_beta()])
        self.assertEqual(next(d for d in rel.diferencas if d.topico == "prazo_aviso").relevancia, "media")

    def test_falha_do_llm_cai_no_modo_deterministico(self):
        with mock.patch.object(ca, "generate_json_ex", side_effect=LLMError("fora do ar")):
            rel = ca.comparar_apolices([apolice_alfa(), apolice_beta()])
        self.assertEqual(rel.modo, "deterministico")
        self.assertTrue(rel.diferencas)
        self.assertIn("fora do ar", rel.recomendacao)

    def test_prompt_traz_apenas_topicos_divergentes(self):
        analise = self._analise([])
        with mock.patch.object(ca, "generate_json_ex", return_value=(analise, "m")) as chamada:
            ca.comparar_apolices([apolice_alfa(), apolice_beta()])
        pedido = chamada.call_args.args[1]
        self.assertIn("prazo_aviso", pedido)
        self.assertNotIn("limite_global", pedido)


if __name__ == "__main__":
    unittest.main()
