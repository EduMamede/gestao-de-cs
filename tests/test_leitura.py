"""Números, datas e arquivos do jeito que vêm na vida real."""

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from apoio import RAIZ  # noqa: F401
from cslib.config import Config, _direcao, ler_como_medir, tabela_md
from cslib.leitura import (
    inferir_formato_numero,
    inferir_ordem_data,
    ler_tabela,
    normalizar_nome_conta,
    parse_data,
    parse_numero,
    perfil_coluna,
    perfil_tabela,
)


class TestNumeros(unittest.TestCase):
    def test_formatos_brasileiros(self):
        for texto, esperado in [("R$ 1.234,56", 1234.56), ("1.234,56", 1234.56), ("R$1.500,00", 1500.0), ("3.500,50", 3500.5), ("750", 750.0), ("12,5", 12.5), ("1.000.000", 1000000.0), ("(1.234,56)", -1234.56), ("-10", -10.0), ("R$ 750", 750.0), ("45%", 45.0)]:
            self.assertEqual(parse_numero(texto, "br"), esperado, texto)

    def test_ponto_de_milhar_sem_decimal(self):
        self.assertEqual(parse_numero("1.200", "br"), 1200.0)
        self.assertEqual(parse_numero("1.5", "br"), 1.5)

    def test_formato_americano(self):
        self.assertEqual(parse_numero("1,234.56", "en"), 1234.56)
        self.assertEqual(parse_numero("1,234", "en"), 1234.0)
        self.assertEqual(inferir_formato_numero(["1,234.56", "12.50"]), "en")
        self.assertEqual(inferir_formato_numero(["1.234,56", "12,50"]), "br")

    def test_vazios_e_lixo(self):
        for texto in ["", "-", "n/a", "N/D", None, "#REF!", "abc", "R$"]:
            self.assertIsNone(parse_numero(texto), texto)


class TestDatas(unittest.TestCase):
    def test_formatos(self):
        alvo = dt.date(2026, 11, 3)
        for valor in ["03/11/2026", "3/11/26", "2026-11-03", "03.11.2026", "03-11-2026", "2026-11-03 14:30:00", dt.datetime(2026, 11, 3, 9), alvo, "3 de novembro de 2026", "03 nov 2026"]:
            self.assertEqual(parse_data(valor), alvo, valor)

    def test_serial_do_excel(self):
        self.assertEqual(parse_data(46329), dt.date(2026, 11, 3))
        self.assertEqual(parse_data("46329"), dt.date(2026, 11, 3))

    def test_ordem_mes_dia(self):
        self.assertEqual(inferir_ordem_data(["12/25/2026", "01/31/2026"]), "mdy")
        self.assertEqual(parse_data("11/03/2026", "mdy"), dt.date(2026, 11, 3))
        self.assertEqual(inferir_ordem_data(["25/12/2026", "03/11/2026"]), "dmy")

    def test_invalidas(self):
        for valor in ["sem data", "32/13/2026", "", None, "ontem"]:
            self.assertIsNone(parse_data(valor), valor)


class TestArquivos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_latin1_com_ponto_e_virgula_e_titulo(self):
        caminho = self.dir / "a.csv"
        caminho.write_bytes("Relatório de contas;;\n;;\nRazão Social;Valor;Observação\nClínica São José;\"R$ 1,00\";ç\n".encode("latin-1"))
        t = ler_tabela(caminho)
        self.assertEqual(t.separador, ";")
        self.assertEqual(t.colunas, ["Razão Social", "Valor", "Observação"])
        self.assertEqual(t.linhas[0][0], "Clínica São José")
        self.assertEqual(t.linhas_ignoradas, 2)

    def test_utf8_com_bom_e_virgula(self):
        caminho = self.dir / "b.csv"
        caminho.write_text("Conta,Receita\nÁgua,10\n", encoding="utf-8-sig")
        t = ler_tabela(caminho)
        self.assertEqual(t.colunas, ["Conta", "Receita"])
        self.assertEqual(t.codificacao, "utf-8-sig")

    def test_formato_nao_suportado(self):
        caminho = self.dir / "c.pdf"
        caminho.write_text("x")
        with self.assertRaises(ValueError):
            ler_tabela(caminho)

    def test_nome_da_conta_normalizado(self):
        self.assertEqual(normalizar_nome_conta("CLÍNICA FICTÍCIA BETA LTDA"), normalizar_nome_conta("Clinica Ficticia Beta"))
        self.assertEqual(normalizar_nome_conta("CLINICA GAMA S/A"), normalizar_nome_conta("Clínica Gama"))


class TestPerfil(unittest.TestCase):
    def test_texto_livre_fica_bloqueado(self):
        p = perfil_coluna("Observações", ["falei com ele", "ligar amanhã", "tudo certo"])
        self.assertEqual(p["tipo"], "texto-livre")
        self.assertTrue(p["bloqueada"])
        p = perfil_coluna("Qualquer", ["um texto bem comprido que passa de quarenta caracteres fácil, fácil"] * 3)
        self.assertTrue(p["bloqueada"])

    def test_dado_pessoal(self):
        self.assertEqual(perfil_coluna("Contato", ["a@b.com", "c@d.com"])["dado_pessoal"], "e-mail")
        self.assertIn("documento", perfil_coluna("Doc", ["12.345.678/0001-90", "98.765.432/0001-10"])["dado_pessoal"])

    def test_tipos(self):
        self.assertEqual(perfil_coluna("Valor", ["R$ 1,00", "R$ 2,00"])["tipo"], "numero")
        self.assertEqual(perfil_coluna("Início", ["01/01/2026", "02/02/2026"])["tipo"], "data")
        self.assertEqual(perfil_coluna("Plano", ["Ouro", "Prata", "Ouro", "Ouro"])["tipo"], "categoria")
        self.assertEqual(perfil_coluna("Nada", ["", None])["tipo"], "vazia")

    def test_perfil_nao_traz_valores(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "x.csv"
            caminho.write_text("Cliente,Valor\nSEGREDO-UM,10\nSEGREDO-DOIS,20\n", encoding="utf-8")
            self.assertNotIn("SEGREDO", repr(perfil_tabela(ler_tabela(caminho))))


class TestConfig(unittest.TestCase):
    def test_tabela_md_ignora_campo_em_branco_do_modelo(self):
        texto = "# X\n\n## Metas\n\n| meta | alvo |\n| --- | --- |\n| {{meta}} | {{alvo}} |\n| Churn | 2 |\n"
        self.assertEqual(tabela_md(texto, "Metas"), [{"meta": "Churn", "alvo": "2"}])

    def test_direcao_por_etapa(self):
        base, etapas = _direcao("Implantação: bom; demais: ruim")
        self.assertEqual(base, "ruim")
        self.assertEqual(etapas, {"implantacao": "bom"})

    def test_erros_do_checklist(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "m.md"
            caminho.write_text(
                "## Indicadores\n\n| id | rotina | onde está o dado | coluna | como ler | frequência esperada | criticidade |\n| --- | --- | --- | --- | --- | --- | --- |\n"
                "| a | A | x.csv | C | | 3 | alta |\n| b | B | x.csv | D | contagem | | urgente |\n",
                encoding="utf-8",
            )
            cfg = Config()
            ler_como_medir(caminho, cfg)
            # só o que está escrito errado trava a rodada
            self.assertEqual(len(cfg.erros), 1)
            self.assertIn("criticidade", cfg.erros[0])
            # o que ainda não foi respondido fica em aberto
            aberto = " ".join(cfg.pendencias)
            self.assertIn("como ler", aberto)
            self.assertIn("frequência esperada", aberto)


if __name__ == "__main__":
    unittest.main()
