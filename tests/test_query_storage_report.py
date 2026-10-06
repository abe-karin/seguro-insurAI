"""Testes da consulta (BM25 + citações), da persistência, da ingestão e dos relatórios em PDF."""
import tempfile
import unittest
from unittest import mock

from agents import query_agent as qa
from agents.comparison_agent import comparar_apolices
from agents.ingestion_agent import format_pages_for_llm, ingest_pages
from agents.report_agent import (
    generate_comparison_markdown,
    generate_comparison_pdf,
    generate_policy_markdown,
    generate_policy_pdf,
)
from storage import database as db
from tests.fixtures import apolice_alfa, apolice_beta


def _texto_pdf(dados: bytes) -> str:
    import pymupdf

    with pymupdf.open(stream=dados, filetype="pdf") as doc:
        return "\n".join(p.get_text() for p in doc)


class TestConsulta(unittest.TestCase):
    def setUp(self):
        self.apolices = {"Alfa": apolice_alfa(), "Beta": apolice_beta()}

    def test_tokenizar_remove_acentos_e_palavras_vazias(self):
        self.assertEqual(qa.tokenizar("O prazo de aviso é de 30 dias"), ["prazo", "aviso", "30", "dias"])

    def test_recupera_a_pagina_certa_de_cada_apolice(self):
        indice = qa.IndicePaginas({n: a.paginas for n, a in self.apolices.items()})
        achados = indice.buscar("adiantamento de custos de defesa", por_apolice=1)
        paginas = {(n, p) for n, p, _, _ in achados}
        self.assertIn(("Alfa", 2), paginas)
        self.assertIn(("Beta", 2), paginas)

    def test_pergunta_sem_correspondencia_nao_chama_o_llm(self):
        with mock.patch.object(qa, "generate_text_ex") as chamada:
            resp = qa.responder("zzzzqqq", self.apolices)
        chamada.assert_not_called()
        self.assertIn("Não encontrei", resp.resposta)

    def test_resposta_reconhece_citacoes_validas(self):
        texto = "Alfa adianta custos [Alfa, p. 2]; Beta não [Beta, p. 2]. Citação falsa [Gama, p. 9]."
        with mock.patch.object(qa, "generate_text_ex", return_value=(texto, "m")):
            resp = qa.responder("adiantamento de custos de defesa", self.apolices)
        citadas = {(f.apolice, f.pagina) for f in resp.citadas}
        self.assertEqual(citadas, {("Alfa", 2), ("Beta", 2)})  # [Gama, p. 9] não foi recuperada

    def test_citacao_em_outros_formatos_e_reconhecida(self):
        texto = "Ver [alfa, pág. 2] e [BETA, página 2]."
        with mock.patch.object(qa, "generate_text_ex", return_value=(texto, "m")):
            resp = qa.responder("adiantamento de custos de defesa", self.apolices)
        self.assertEqual({(f.apolice, f.pagina) for f in resp.citadas}, {("Alfa", 2), ("Beta", 2)})

    def test_contexto_inclui_ficha_e_trechos(self):
        trechos = [("Alfa", 2, "texto da página dois", 1.0)]
        contexto = qa.montar_contexto(self.apolices, trechos)
        self.assertIn("Claims made", contexto)
        self.assertIn("[Alfa, p. 2]", contexto)

    def test_pergunta_vazia_e_rejeitada(self):
        with self.assertRaises(ValueError):
            qa.responder("   ", self.apolices)


class TestPersistencia(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        db.configure_storage(self._dir.name)

    def tearDown(self):
        db._engine.dispose()
        self._dir.cleanup()

    def test_salva_e_carrega_apolice_com_paginas(self):
        pid = db.save_policy(apolice_alfa())
        sem_paginas = db.load_policy(pid)
        com_paginas = db.load_policy(pid, with_pages=True)
        self.assertEqual(sem_paginas.dados_apolice.seguradora, "Alfa Seguros")
        self.assertEqual(sem_paginas.paginas, [])
        self.assertEqual(com_paginas.paginas, apolice_alfa().paginas)
        self.assertEqual(com_paginas.ficha_por_topico()["prazo_aviso"].fonte.pagina, 2)

    def test_lista_e_exclui(self):
        pid = db.save_policy(apolice_alfa())
        self.assertEqual(db.list_policies()[0]["total_paginas"], 3)
        self.assertTrue(db.delete_policy(pid))
        self.assertEqual(db.list_policies(), [])
        self.assertEqual(db.load_pages(pid), [])

    def test_banco_da_versao_anterior_nao_derruba_o_app(self):
        """Um doshield.db criado pela primeira versão (schema antigo) não pode ser reaproveitado."""
        import sqlite3
        from pathlib import Path

        antigo = Path(self._dir.name) / "doshield.db"
        con = sqlite3.connect(antigo)
        con.execute("CREATE TABLE policies (id INTEGER PRIMARY KEY, filename TEXT, json_data TEXT)")
        con.commit()
        con.close()  # o "with" do sqlite3 não fecha a conexão, e no Windows o arquivo ficaria travado
        caminho = db.configure_storage(self._dir.name)
        self.assertNotEqual(caminho.name, "doshield.db")
        self.assertEqual(db.list_policies(), [])

    def test_salva_e_recarrega_comparacao(self):
        rel = comparar_apolices([apolice_alfa(), apolice_beta()], use_llm=False)
        cid = db.save_comparison(rel, [1, 2])
        recarregada = db.load_comparison(cid)
        self.assertEqual(recarregada.apolices, rel.apolices)
        self.assertEqual(len(recarregada.diferencas), len(rel.diferencas))
        self.assertEqual(db.list_comparisons()[0]["titulo"], "Alfa Seguros × Beta Seguros")


class TestIngestao(unittest.TestCase):
    def _pdf(self, textos):
        from fpdf import FPDF

        pdf = FPDF()
        for texto in textos:
            pdf.add_page()
            pdf.set_font("Helvetica", size=12)
            pdf.multi_cell(0, 8, texto)
        return bytes(pdf.output())

    def test_extrai_texto_por_pagina(self):
        paginas = ingest_pages(self._pdf(["Pagina um com texto suficiente " * 5, "Pagina dois tambem " * 5]), "x.pdf", "pymupdf")
        self.assertEqual(len(paginas), 2)
        self.assertIn("Pagina um", paginas[0])
        self.assertIn("Pagina dois", paginas[1])

    def test_engine_pdfplumber_tambem_separa_paginas(self):
        paginas = ingest_pages(self._pdf(["Alfa " * 40, "Beta " * 40]), "x.pdf", "pdfplumber")
        self.assertEqual(len(paginas), 2)

    def test_formato_nao_suportado(self):
        with self.assertRaises(ValueError):
            ingest_pages(b"abc", "planilha.xlsx")

    def test_marcadores_de_pagina_para_o_llm(self):
        texto = format_pages_for_llm(["um", "dois"])
        self.assertTrue(texto.startswith("[[PÁGINA 1]]\num"))
        self.assertIn("[[PÁGINA 2]]\ndois", texto)


class TestRelatorios(unittest.TestCase):
    def setUp(self):
        self.rel = comparar_apolices([apolice_alfa(), apolice_beta()], use_llm=False)

    def test_pdf_do_comparativo_contem_as_linhas_das_tabelas(self):
        """Regressão: a versão anterior exportava só os cabeçalhos das tabelas."""
        dados = generate_comparison_pdf(self.rel)
        self.assertTrue(dados.startswith(b"%PDF-"))
        texto = _texto_pdf(dados)
        for esperado in ("Prazo de aviso do sinistro", "30 dias", "10 dias", "Claims made", "Ocorrencia"):
            self.assertIn(esperado, texto)
        self.assertNotIn("**", texto)

    def test_pdf_da_apolice_contem_ficha_e_coberturas(self):
        texto = _texto_pdf(generate_policy_pdf(apolice_alfa()))
        for esperado in ("Alfa Seguros", "Base de acionamento", "Claims made", "Side A", "Dolo"):
            self.assertIn(esperado, texto)

    def test_pdf_aceita_acentos_e_simbolos(self):
        ap = apolice_alfa()
        ap.observacoes = "Cobertura “ampla” — inclui § 3º e ≥ R$ 1 mi"
        self.assertTrue(generate_policy_pdf(ap).startswith(b"%PDF-"))

    def test_cobertura_e_exclusao_sem_descricao(self):
        """O modelo às vezes omite a descrição; relatórios e telas não podem quebrar."""
        from models.schemas import CoberturaPrincipal, Exclusao

        ap = apolice_alfa()
        ap.coberturas.append(CoberturaPrincipal(nome="Cobertura sem descricao"))
        ap.exclusoes.append(Exclusao(categoria="Exclusao sem descricao"))
        self.assertIn("Cobertura sem descricao", generate_policy_markdown(ap))
        self.assertIn("Cobertura sem descricao", _texto_pdf(generate_policy_pdf(ap)))
        self.assertTrue(generate_comparison_pdf(comparar_apolices([ap, apolice_beta()], use_llm=False)).startswith(b"%PDF-"))

    def test_pdf_com_texto_muito_longo_nao_quebra(self):
        """O fpdf2 recusa linhas maiores que uma página; textos longos são encurtados."""
        from tests.fixtures import apolice_alfa as nova

        apolices = [nova(), apolice_beta(), nova()]
        apolices[0].ficha_tecnica[0].valor = "texto muito longo " * 200
        rel = comparar_apolices(apolices, use_llm=False)
        self.assertTrue(generate_comparison_pdf(rel).startswith(b"%PDF-"))

    def test_markdown_do_comparativo(self):
        md = generate_comparison_markdown(self.rel)
        self.assertIn("| Tópico | Alfa Seguros | Beta Seguros |", md)
        self.assertIn("30 dias (p. 2)", md)

    def test_markdown_da_apolice(self):
        md = generate_policy_markdown(apolice_alfa())
        self.assertIn("## 2. Ficha técnica D&O", md)
        self.assertIn("Periodo complementar de 90 dias", md)


if __name__ == "__main__":
    unittest.main()
