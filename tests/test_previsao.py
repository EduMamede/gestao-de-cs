"""As previsões: achar o padrão que existe, admitir quando não existe e nunca olhar o futuro."""

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import openpyxl

from apoio import REF, Empresa, rodar, textos_para_ia
import gerar_historico
from gerar_bases import REF as DATA_REF

from cslib import config as config_mod, prever as prever_mod
from cslib import pasta as pasta_mod
from cslib.config import Config, Indicador
from cslib.medir import Conta, rodar as medir_rodar

precisa_da_biblioteca = unittest.skipUnless(prever_mod._tem_biblioteca(), "instale o scikit-learn para testar o modelo")
if prever_mod._tem_biblioteca():
    import numpy as np


class EmpresaComHistorico:
    def __init__(self, cenario: str, modo: str = "protegido", **opcoes):
        self.tmp = tempfile.TemporaryDirectory(prefix="csprev-")
        self.pasta = Path(self.tmp.name) / "empresa"
        codigo, saida = rodar("criar-pasta", "--destino", self.pasta, "--empresa", "Empresa inventada", "--modo", modo)
        assert codigo == 0, saida
        self.dados = gerar_historico.montar(self.pasta, cenario, **opcoes)
        self.rodada_dir = self.pasta / "4-dados" / "rodadas" / REF

    def rodada(self):
        return rodar("rodada", "--pasta", self.pasta, "--data", REF, "--entrada", REF)

    def resumo(self) -> dict:
        return json.loads((self.rodada_dir / "resumo.json").read_text(encoding="utf-8"))

    def fechar(self):
        self.tmp.cleanup()


@precisa_da_biblioteca
class TestContas(unittest.TestCase):
    """Conferidas à mão."""

    def test_auc(self):
        self.assertEqual(prever_mod._auc(np.array([1, 0]), np.array([0.9, 0.1])), 1.0)
        self.assertEqual(prever_mod._auc(np.array([1, 0]), np.array([0.1, 0.9])), 0.0)
        self.assertEqual(prever_mod._auc(np.array([1, 0]), np.array([0.5, 0.5])), 0.5)
        # 2 positivos e 2 negativos: 3 dos 4 pares na ordem certa
        self.assertEqual(prever_mod._auc(np.array([1, 0, 1, 0]), np.array([0.9, 0.8, 0.7, 0.1])), 0.75)
        self.assertIsNone(prever_mod._auc(np.array([1, 1]), np.array([0.5, 0.2])))

    def test_pegou_no_topo(self):
        y = np.array([1, 1, 0, 0, 0, 0, 0, 0, 0, 0])
        self.assertEqual(prever_mod._pegou_no_topo(y, np.array([9, 8, 7, 6, 5, 4, 3, 2, 1, 0.0])), 2)  # 20% de 10: 2 vagas
        self.assertEqual(prever_mod._pegou_no_topo(y, np.array([0, 1, 9, 8, 7, 6, 5, 4, 3, 2.0])), 0)
        # todas empatadas: 2 vagas para 10 contas, cada caso vale 2/10
        self.assertAlmostEqual(prever_mod._pegou_no_topo(y, np.full(10, 5.0)), 0.4)
        # 5 contas: 20% dá 1 vaga, e empate não favorece quem vem primeiro no arquivo
        self.assertAlmostEqual(prever_mod._pegou_no_topo(np.array([1, 0, 0, 0, 0]), np.full(5, 1.0)), 0.2)

    def test_mais_comparacoes_deixam_o_corte_mais_duro(self):
        y = np.array([1, 0] * 30)
        modelo = np.array([0.6, 0.4] * 30) + np.linspace(-0.3, 0.3, 60)
        base = np.linspace(0, 1, 60)
        contas = [f"C{i}" for i in range(60)]
        self.assertLess(prever_mod._ganho_garantido(y, modelo, base, contas, 6), prever_mod._ganho_garantido(y, modelo, base, contas, 1))

    def test_mudanca_usa_a_regua_da_mudanca_de_padrao(self):
        regras = {"minimo absoluto": 2, "variacao para alerta": 30}
        self.assertEqual(prever_mod._mudanca(7, 10, regras), -1)  # caiu 30%
        self.assertEqual(prever_mod._mudanca(8, 10, regras), 0)  # caiu 20%
        self.assertEqual(prever_mod._mudanca(13, 10, regras), 1)
        self.assertEqual(prever_mod._mudanca(2, 3, regras), 0)  # caiu 33%, mas só 1 de diferença
        self.assertEqual(prever_mod._mudanca(3, 0, regras), 1)


class TestNaoOlhaOFuturo(unittest.TestCase):
    REF = dt.date(2026, 11, 3)

    def historia(self, eventos, cancelou=None, tmp=None):
        ind = Indicador(id="plano", rotina="Planos", arquivo="plano.csv", medida="eventos", esperado=2.0, janela=30)
        cfg = Config(indicadores=[ind], arquivos={"plano.csv": "eventos"})
        campos = {"data_inicio": self.REF - dt.timedelta(days=700)}
        if cancelou:
            campos["data_cancelamento"] = cancelou
        conta = Conta(codigo="CONTA-001", campos=campos, eventos={"plano.csv": eventos}, status="cancelada" if cancelou else "ativa")
        r = SimpleNamespace(data=self.REF, cfg=cfg, contas=[conta], ativas=[] if cancelou else [conta], canceladas=[conta] if cancelou else [])
        return prever_mod.Historia(Path(tmp), r), conta, ind

    def test_evento_futuro_nao_muda_os_sinais(self):
        data = self.REF - dt.timedelta(days=200)
        passado = [data - dt.timedelta(days=d) for d in (1, 5, 40, 70, 100)]
        with tempfile.TemporaryDirectory() as tmp:
            sem, conta_sem, _ = self.historia(list(passado), tmp=tmp)
            com, conta_com, _ = self.historia(passado + [data + dt.timedelta(days=d) for d in (1, 10, 90)], tmp=tmp)
            self.assertEqual(sem.sinais(conta_sem, data), com.sinais(conta_com, data))

    def test_contagem_por_periodo(self):
        data = self.REF - dt.timedelta(days=200)
        eventos = [data, data - dt.timedelta(days=29), data - dt.timedelta(days=30), data - dt.timedelta(days=59), data - dt.timedelta(days=60), data + dt.timedelta(days=1)]
        with tempfile.TemporaryDirectory() as tmp:
            h, conta, ind = self.historia(eventos, tmp=tmp)
            self.assertEqual(h.medida_em(conta, ind, data), (2.0, 2.0))  # últimos 30 dias: 2. Os 30 antes: 2. O de depois não conta.

    def test_treino_so_usa_o_que_ja_se_sabia(self):
        cancelou = self.REF - dt.timedelta(days=200)
        eventos = [self.REF - dt.timedelta(days=d) for d in range(201, 700, 7)]
        with tempfile.TemporaryDirectory() as tmp:
            h, _, _ = self.historia(eventos, cancelou=cancelou, tmp=tmp)
            linhas = prever_mod._linhas_churn(h)
        self.assertTrue(linhas)
        for linha in linhas:
            self.assertLessEqual(linha.conhecido_em, self.REF)
            self.assertLess(linha.data, cancelou)  # depois de sair, a conta não entra
            self.assertEqual(linha.y, int(cancelou <= linha.data + dt.timedelta(days=prever_mod.HORIZONTE)))
        self.assertEqual(sorted({l.y for l in linhas}), [1])  # só existem as fotos dentro de 90 dias da saída


class TestPoucosDados(unittest.TestCase):
    def test_nas_5_bases_diz_que_ainda_nao_da(self):
        for nome in ("completa", "baguncada", "minima", "canceladas", "recompra"):
            with self.subTest(base=nome):
                e = Empresa(nome)
                try:
                    codigo, saida = e.rodada()
                    self.assertEqual(codigo, 0, saida)
                    prev = e.resumo()["previsoes"]
                    self.assertIn("Previsões:", saida)
                    for bloco in ("churn", "engajamento", "incremento"):
                        self.assertEqual(prev[bloco]["status"], "sem_dados", bloco)
                        self.assertNotIn("teste", prev[bloco])
                        self.assertFalse(prev[bloco].get("contas"))
                    self.assertTrue((e.pasta / "4-dados" / "rodadas" / REF / "previsoes.md").exists())
                    self.assertNotIn("O que o modelo prevê", rodar("semana", "--pasta", e.pasta, "--data", REF)[1])
                finally:
                    e.fechar()

    def test_o_que_falta_conta_quantos_casos_ja_tem(self):
        e = Empresa("canceladas")
        try:
            e.rodada()
            faltas = {f["o_que_falta"]: f for f in e.resumo()["falta_medir"]}
            nome = next(n for n in faltas if n.startswith("Histórico para prever churn"))
            self.assertIn("de 30 casos", nome)
            self.assertEqual(faltas[nome]["prioridade"], "baixa")
        finally:
            e.fechar()

    def test_recompra_nao_pede_cancelamento(self):
        e = Empresa("recompra")
        try:
            e.rodada()
            self.assertFalse([f for f in e.resumo()["falta_medir"] if f["o_que_falta"].startswith("Histórico para prever churn")])
        finally:
            e.fechar()

    def test_carteira_pequena_nao_preve_nem_com_historico_longo(self):
        # Foi a semente 7 com 12 contas que mostrou o falso positivo: com poucas contas, o sorteio dá uma segurança que não existe.
        e = EmpresaComHistorico("ruido", contas=12, meses=28)
        try:
            codigo, saida = e.rodada()
            self.assertEqual(codigo, 0, saida)
            resumo = e.resumo()
            prev = resumo["previsoes"]
            self.assertEqual(prev["churn"]["status"], "sem_dados")
            self.assertEqual(prev["incremento"]["status"], "sem_dados")
            self.assertEqual(prev["engajamento"]["status"], "sem_dados")
            self.assertEqual(prev["engajamento"]["unidade"], "contas")
            self.assertFalse(prev["engajamento"]["contas"])
            self.assertTrue(any(f["o_que_falta"].endswith(f"de {prever_mod.MIN_CONTAS} contas") for f in resumo["falta_medir"]), resumo["falta_medir"])
        finally:
            e.fechar()


@precisa_da_biblioteca
class TestPadraoPlantado(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = EmpresaComHistorico("padrao")
        codigo, cls.saida = cls.e.rodada()
        assert codigo == 0, cls.saida
        cls.resumo = cls.e.resumo()
        cls.prev = cls.resumo["previsoes"]
        cls.por_codigo = {cls.e.dados["codigos"][k]: v for k, v in cls.e.dados["simuladas"].items()}

    @classmethod
    def tearDownClass(cls):
        cls.e.fechar()

    def test_churn_passa_no_teste_e_ganha_da_nota(self):
        churn = self.prev["churn"]
        self.assertEqual(churn["status"], "ok")
        teste = churn["teste"]
        self.assertTrue(teste["passou"])
        self.assertGreaterEqual(teste["casos"], 10)
        self.assertGreater(teste["pegou_modelo"], 2 * teste["pegou_base"])  # a nota não enxerga, porque o uso segue acima do esperado
        self.assertGreater(teste["auc_modelo"], teste["auc_base"])

    def test_quem_o_modelo_aponta_e_quem_esta_em_queda(self):
        topo = self.prev["churn"]["contas"][:10]
        em_queda = sum(1 for c in topo if self.por_codigo[c["conta"]]["queda"])
        self.assertGreaterEqual(em_queda, 8, topo)
        for c in topo:
            self.assertFalse(self.por_codigo[c["conta"]]["cancelou"])  # só conta ativa
        self.assertEqual([c["chance_pct"] for c in topo], sorted((c["chance_pct"] for c in topo), reverse=True))

    def test_motivos_apontam_a_rotina_certa(self):
        topo = self.prev["churn"]["contas"][:10]
        com_estoque = sum(1 for c in topo if any(m.startswith("Movimentos de estoque") for m in c["motivos"]))
        self.assertGreaterEqual(com_estoque, 8, topo)

    def test_engajamento_ve_a_queda_antes(self):
        uso = self.prev["engajamento"]
        self.assertEqual(uso["status"], "ok")
        plano = next(r for r in uso["rotinas"] if r["id"] == "plano")
        self.assertEqual(plano["cai"]["status"], "ok")
        self.assertGreater(plano["cai"]["teste"]["auc_modelo"], plano["cai"]["teste"]["auc_base"])
        for c in uso["contas"]:
            self.assertIn(c["tendencia"], ("cai", "sobe"))
            self.assertGreaterEqual(c["chance_pct"], self.prev["chance_para_tendencia_pct"])

    def test_aumento_de_receita_passa_no_teste(self):
        aumento = self.prev["incremento"]
        self.assertEqual(aumento["status"], "ok")
        self.assertGreater(aumento["teste"]["pegou_modelo"], aumento["teste"]["pegou_base"])
        self.assertEqual(aumento["aumento_tipico_pct"], 25)
        topo = aumento["contas"][:5]
        self.assertGreaterEqual(sum(1 for c in topo if self.por_codigo[c["conta"]]["alta"]), 4, topo)

    def test_tudo_que_a_ia_le_so_tem_codigo(self):
        for arquivo, texto in textos_para_ia(self.e.pasta).items():
            self.assertNotIn("Cliente Fictício", texto, arquivo)
        self.assertNotIn("Cliente Fictício", self.saida)
        self.assertNotIn("Cliente Fictício", rodar("prever", "--pasta", self.e.pasta)[1])

    def test_nomes_voltam_so_para_a_pessoa(self):
        copia = (self.e.pasta / "com-nomes" / f"previsoes-{REF}.md").read_text(encoding="utf-8")
        self.assertIn("Cliente Fictício", copia)
        livro = openpyxl.load_workbook(self.e.rodada_dir / "health-score.xlsx", data_only=True)
        self.assertIn("Previsões", livro.sheetnames)
        textos = [str(c.value) for linha in livro["Previsões"].iter_rows() for c in linha if c.value is not None]
        self.assertTrue(any("Cliente Fictício" in t for t in textos))
        self.assertTrue(any("pronta." in t for t in textos))

    def test_sem_estimativa_nao_pede_para_a_pessoa_preencher(self):
        # Nesta empresa, o tamanho previsto do aumento não confere com o que aconteceu. O valor é do modelo, não da pessoa.
        self.assertFalse(self.prev["incremento"]["teste"]["tamanho_confere"])
        self.assertTrue(all(c["valor_estimado"] is None for c in self.prev["incremento"]["contas"]))
        self.assertNotIn("a preencher", (self.e.rodada_dir / "previsoes.md").read_text(encoding="utf-8"))
        livro = openpyxl.load_workbook(self.e.rodada_dir / "health-score.xlsx", data_only=True)
        textos = [str(c.value) for linha in livro["Previsões"].iter_rows() for c in linha if c.value is not None]
        self.assertNotIn("a preencher", textos)
        self.assertIn("não estimado", textos)

    def test_planilha_traz_toda_a_carteira_e_o_resumo_so_o_topo(self):
        livro = openpyxl.load_workbook(self.e.rodada_dir / "health-score.xlsx", data_only=True)
        ids = [l[0].value for l in livro["Previsões"].iter_rows() if str(l[0].value).startswith("CONTA-")]
        self.assertEqual(len(ids), self.resumo["contas"]["ativas"])
        self.assertLessEqual(len(self.prev["churn"]["contas"]), 20)
        self.assertEqual(self.prev["churn"]["contas_no_total"], self.resumo["contas"]["ativas"])

    def test_semana_mostra_e_o_numero_confere(self):
        codigo, saida = rodar("semana", "--pasta", self.e.pasta, "--data", REF)
        self.assertEqual(codigo, 0, saida)
        self.assertIn("## O que o modelo prevê", saida)
        semana = next((self.e.pasta / "2-metas").glob("semana-*.md"))
        codigo, saida = rodar("conferir-numeros", "--pasta", self.e.pasta, "--arquivo", f"2-metas/{semana.name}")
        self.assertEqual(codigo, 0, saida)

    def test_previsao_nao_muda_a_ordem_do_mais_crucial(self):
        sem = dict(self.resumo)
        sem.pop("previsoes")
        from cslib.semana import texto_semana

        com_previsao = texto_semana(DATA_REF, self.resumo).split("## O mais crucial da semana")[1].split("## O que está atrás")[0]
        sem_previsao = texto_semana(DATA_REF, sem).split("## O mais crucial da semana")[1].split("## O que está atrás")[0]
        self.assertEqual(com_previsao, sem_previsao)

    def test_comando_prever(self):
        codigo, saida = rodar("prever", "--pasta", self.e.pasta)
        self.assertEqual(codigo, 0, saida)
        self.assertIn("Mais chance de cancelar", saida)
        self.assertIn(self.prev["churn"]["contas"][0]["conta"], saida)


@precisa_da_biblioteca
class TestModoAberto(unittest.TestCase):
    def test_nome_aparece_no_modo_aberto(self):
        e = EmpresaComHistorico("padrao", modo="aberto")
        try:
            codigo, saida = e.rodada()
            self.assertEqual(codigo, 0, saida)
            c = e.resumo()["previsoes"]["churn"]["contas"][0]
            self.assertIn("Cliente Fictício", c["nome"])
            self.assertIn("Cliente Fictício", (e.rodada_dir / "previsoes.md").read_text(encoding="utf-8"))
            self.assertIn("Cliente Fictício", rodar("prever", "--pasta", e.pasta)[1])
        finally:
            e.fechar()


@precisa_da_biblioteca
class TestRuido(unittest.TestCase):
    """Cancelamento e aumento sorteados: não há o que achar, e o modelo tem que admitir."""

    def test_admite_que_nao_ganhou(self):
        for semente in (7, 11):
            with self.subTest(semente=semente):
                e = EmpresaComHistorico("ruido", semente=semente)
                try:
                    codigo, saida = e.rodada()
                    self.assertEqual(codigo, 0, saida)
                    prev = e.resumo()["previsoes"]
                    for bloco in ("churn", "engajamento", "incremento"):
                        self.assertEqual(prev[bloco]["status"], "sem_ganho", bloco)
                        self.assertFalse(prev[bloco].get("contas"), bloco)
                    self.assertFalse(prev["churn"]["teste"]["passou"])
                    self.assertNotIn("O que o modelo prevê", rodar("semana", "--pasta", e.pasta, "--data", REF)[1])
                    texto = (e.rodada_dir / "previsoes.md").read_text(encoding="utf-8")
                    self.assertIn("testado, sem ganho", texto)
                    self.assertNotIn("Quem pode cancelar", texto)
                finally:
                    e.fechar()


@precisa_da_biblioteca
class TestSemBibliotecaEComErro(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="csprev-")
        cls.pasta = Path(cls.tmp.name) / "empresa"
        pasta_mod.criar_pasta(cls.pasta, "Empresa inventada", "protegido")
        gerar_historico.montar(cls.pasta, "padrao")
        cls.cfg = config_mod.carregar(cls.pasta)
        cls.entrada = cls.pasta / "4-dados" / "entradas" / REF

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def rodada(self):
        return medir_rodar(self.pasta, DATA_REF, self.entrada, self.cfg, "protegido")

    def test_sem_biblioteca_o_resto_funciona_e_diz_o_que_instalar(self):
        with mock.patch.object(prever_mod, "_tem_biblioteca", return_value=False):
            r = self.rodada()
        for bloco in ("churn", "engajamento", "incremento"):
            self.assertEqual(r.previsoes[bloco]["status"], "sem_biblioteca", bloco)
            self.assertIn("pip install scikit-learn", r.previsoes[bloco]["motivo"])
        self.assertTrue(r.ativas)
        item = next(f for f in r.faltas if f["o_que_falta"] == "Biblioteca de previsão não instalada")
        self.assertIn("pip install scikit-learn", item["primeiro_passo"])

    def test_erro_na_previsao_nao_derruba_a_rodada_nem_vaza_dado(self):
        with mock.patch.object(prever_mod, "prever_churn", side_effect=ValueError("SEGREDO do cliente")):
            r = self.rodada()
        self.assertEqual(r.previsoes["churn"]["status"], "erro")
        self.assertNotIn("SEGREDO", r.previsoes["churn"]["motivo"])
        self.assertIn(r.previsoes["incremento"]["status"], ("ok", "sem_ganho"))
        self.assertTrue(r.ativas)

    def test_minimo_de_casos_vem_do_checklist(self):
        como_medir = self.pasta / "4-dados" / "como-medir.md"
        original = como_medir.read_text(encoding="utf-8")
        try:
            como_medir.write_text(original + "\n## Regras\n\n| regra | valor |\n| --- | --- |\n| mínimo de casos para prever | 1000 |\n| aumento mínimo de receita | 40 |\n", encoding="utf-8")
            cfg = config_mod.carregar(self.pasta)
            self.assertEqual(cfg.regras["minimo de casos para prever"], 1000)
            self.assertEqual(cfg.regras["aumento minimo de receita"], 40)
            r = medir_rodar(self.pasta, DATA_REF, self.entrada, cfg, "protegido")
            self.assertEqual(r.previsoes["churn"]["status"], "sem_dados")
            self.assertEqual(r.previsoes["churn"]["minimo"], 1000)
        finally:
            como_medir.write_text(original, encoding="utf-8")


class TestRodadaAntiga(unittest.TestCase):
    def test_rodada_sem_previsoes_nao_quebra_a_semana_nem_o_comando(self):
        e = Empresa("completa")
        try:
            e.rodada()
            caminho = e.pasta / "4-dados" / "rodadas" / REF / "resumo.json"
            resumo = json.loads(caminho.read_text(encoding="utf-8"))
            resumo.pop("previsoes")
            caminho.write_text(json.dumps(resumo), encoding="utf-8")
            codigo, saida = rodar("prever", "--pasta", e.pasta)
            self.assertEqual(codigo, 0, saida)
            self.assertIn("--refazer", saida)
            codigo, saida = rodar("semana", "--pasta", e.pasta, "--data", REF)
            self.assertEqual(codigo, 0, saida)
        finally:
            e.fechar()


if __name__ == "__main__":
    unittest.main()
