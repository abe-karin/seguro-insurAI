"""Testes do cliente de LLM: limites por provedor, retentativas e compatibilidade com os SDKs (sem rede)."""
import os
import sys
import types
import unittest
from unittest import mock

from agents import llm_client as lc
from models.schemas import AnaliseLLM


class TestLimitesPorProvedor(unittest.TestCase):
    def _capturar(self, provider):
        chamadas = []

        def falso(system, user, model, max_tokens, schema):
            chamadas.append(max_tokens)
            return '{"topicos": [], "resumo_executivo": "", "recomendacao": ""}'

        with mock.patch.dict(lc._PROVIDERS, {provider: falso}):
            lc.generate_json("s", "u", AnaliseLLM, provider, "modelo", max_tokens=24000)
        return chamadas[0]

    def test_openai_nao_passa_do_limite_do_gpt4o(self):
        self.assertLessEqual(self._capturar("openai"), 16384)

    def test_anthropic_fica_abaixo_do_limite_sem_streaming(self):
        self.assertLessEqual(self._capturar("anthropic"), 21000)

    def test_google_mantem_o_limite_pedido(self):
        self.assertEqual(self._capturar("google"), 24000)


class TestAnthropicSDK(unittest.TestCase):
    def test_chamada_nao_envia_temperature(self):
        """As versões atuais do SDK anthropic recusam o parâmetro `temperature`."""
        recebidos = {}

        class Mensagens:
            def create(self, **kwargs):
                recebidos.update(kwargs)
                bloco = types.SimpleNamespace(type="text", text="ok")
                return types.SimpleNamespace(stop_reason="end_turn", content=[bloco])

        falso = types.ModuleType("anthropic")
        falso.Anthropic = lambda api_key: types.SimpleNamespace(messages=Mensagens())
        with mock.patch.dict(sys.modules, {"anthropic": falso}), mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "x"}):
            self.assertEqual(lc._anthropic("s", "u", "m", 1000, None), "ok")
        self.assertNotIn("temperature", recebidos)


class TestRetentativas(unittest.TestCase):
    def test_erro_de_modelo_inexistente_nao_e_transitorio(self):
        erro = RuntimeError("404 NOT_FOUND models/x is not found for API version v1beta, or is not supported for generateContent")
        self.assertFalse(lc._is_transient(erro))

    def test_sobrecarga_e_limite_de_taxa_sao_transitorios(self):
        for msg in ("503 UNAVAILABLE", "429 RESOURCE_EXHAUSTED", "Rate limit reached", "overloaded_error"):
            self.assertTrue(lc._is_transient(RuntimeError(msg)), msg)

    def test_troca_de_modelo_quando_o_primeiro_falha(self):
        def falso(system, user, model, max_tokens, schema):
            if model == "ruim":
                raise RuntimeError("503 UNAVAILABLE")
            return "resposta"

        with mock.patch.dict(lc._PROVIDERS, {"google": falso}), \
                mock.patch.dict(lc.FALLBACK_MODELS, {"google": ("bom",)}), \
                mock.patch.object(lc, "RETRY_DELAYS", ()):
            texto, usado = lc.generate_text_ex("s", "u", "google", "ruim")
        self.assertEqual((texto, usado), ("resposta", "bom"))

    def test_tempo_maximo_interrompe_as_tentativas(self):
        def falso(system, user, model, max_tokens, schema):
            raise RuntimeError("503 UNAVAILABLE")

        with mock.patch.dict(lc._PROVIDERS, {"google": falso}), \
                mock.patch.object(lc, "RETRY_DELAYS", ()), \
                mock.patch.object(lc, "PAUSA_ENTRE_RODADAS", 0), \
                mock.patch.object(lc, "TEMPO_MAXIMO_S", -1):
            with self.assertRaises(lc.LLMError):
                lc.generate_text_ex("s", "u", "google", "m")


if __name__ == "__main__":
    unittest.main()
