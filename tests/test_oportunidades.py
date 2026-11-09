"""Oportunidades: área sem uso, usuário sobrecarregado, regras da empresa e o mapa que é da pessoa."""

import datetime as dt
import json
import unittest

import openpyxl

from apoio import REF, Empresa, rodar, textos_para_ia
from gerar_bases import REF as DATA_REF, escrever, md

COLUNAS = md(
    "Colunas",
    "Arquivos",
    "| arquivo | tipo |\n| --- | --- |\n| contas.csv | contas |\n| plano.csv | eventos |\n",
    "\n## Colunas\n\n| arquivo | coluna | campo |\n| --- | --- | --- |\n| contas.csv | ID | conta_id |\n| contas.csv | Cliente | conta_nome |\n"
    "| contas.csv | MRR | receita |\n| contas.csv | Status | status |\n| contas.csv | Usuários | usuarios |\n"
    "| plano.csv | ID | conta_id |\n| plano.csv | Data | data_evento |\n| plano.csv | Quem | usuario_evento |\n",
)
INDICADORES = (
    "| id | bloco | rotina | dado que prova | onde está o dado | coluna | coluna anterior | como ler | frequência esperada | criticidade | subir é |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
    "| plano | rotina | Planos | Plano lançado | plano.csv | | | eventos | 1 em 30 dias | alta | bom |\n"
    "| agenda | rotina | Agenda | Agenda no mês | contas.csv | Agenda | | contagem | 1 | média | bom |\n"
)
REGRAS = (
    "\n## Oportunidades\n\n| oportunidade | rotina | como ler | limite | o que oferecer |\n| --- | --- | --- | --- | --- |\n"
    "| Usuário sobrecarregado | plano | um usuário concentra | | Mais acessos |\n"
    "| Muito volume por usuário | plano | volume por usuário | 15 | Mais acessos |\n"
    "| Perto do limite do plano | agenda | acima de | 90 | Plano maior |\n"
    "| Agenda parada | agenda | sem uso | | Módulo de agenda |\n"
)


def data_br(dias: int) -> str:
    return (DATA_REF - dt.timedelta(days=dias)).strftime("%d/%m/%Y")


def montar(e: Empresa, regras: str = REGRAS) -> None:
    for outro in e.entrada.iterdir():
        outro.unlink()
    # (id, MRR, usuários, agenda, registros de plano por usuário)
    contas = [
        ("A1", 1000, 5, 20, {"Usuária Secreta A": 5, "Usuário Secreto B": 5}),  # divide bem
        ("A2", 2000, 5, 20, {"Usuária Secreta C": 5, "Usuário Secreto D": 5}),
        ("B1", 3000, 5, 0, {"Usuária Secreta E": 5, "Usuário Secreto F": 5}),  # não usa a agenda
        ("C1", 4000, 5, 20, {"Usuária Secreta G": 18, "Usuário Secreto H": 2}),  # 18 de 20: 90%
        ("D1", 5000, 1, 20, {"Usuária Secreta I": 30}),  # um usuário só: 100%, e 30 por usuário
        ("E1", 6000, 5, 95, {"Usuária Secreta J": 5, "Usuário Secreto K": 5}),  # agenda acima de 90
    ]
    linhas = [["ID", "Cliente", "MRR", "Status", "Usuários", "Agenda"]]
    plano = [["ID", "Data", "Quem"]]
    for id_, mrr, usuarios, agenda, registros in contas:
        linhas.append([id_, f"Cliente Fictício {id_}", mrr, "Ativo", usuarios, agenda])
        for pessoa, quantos in registros.items():
            plano += [[id_, data_br(1 + i % 20), pessoa] for i in range(quantos)]
    escrever(e.entrada / "contas.csv", linhas)
    escrever(e.entrada / "plano.csv", plano)
    (e.pasta / "4-dados" / "colunas.md").write_text(COLUNAS, encoding="utf-8")
    (e.pasta / "4-dados" / "como-medir.md").write_text(md("Como medir", "Indicadores", INDICADORES, regras), encoding="utf-8")


class TestOportunidades(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Empresa("minima")
        montar(cls.e)
        codigo, saida = cls.e.rodada()
        assert codigo == 0, saida
        cls.saida = saida
        cls.m = cls.e.mapa()
        cls.fatos = json.loads((cls.e.pasta / "4-dados" / "rodadas" / REF / "contas.json").read_text(encoding="utf-8"))
        cls.resumo = cls.e.resumo()

    @classmethod
    def tearDownClass(cls):
        cls.e.fechar()

    def de(self, nome: str) -> list:
        return self.fatos[self.m[f"Cliente Fictício {nome}"]]["oportunidades"]

    def test_quem_divide_bem_nao_aparece(self):
        self.assertEqual(self.de("A1"), [])
        self.assertEqual(self.de("A2"), [])

    def test_area_sem_uso_usa_o_nome_e_a_oferta_da_empresa(self):
        achadas = self.de("B1")
        self.assertEqual([o["oportunidade"] for o in achadas], ["Agenda parada"])
        self.assertEqual(achadas[0]["oferta"], "Módulo de agenda")

    def test_usuario_sobrecarregado(self):
        achada = next(o for o in self.de("C1") if o["tipo"] == "um_usuario")
        self.assertEqual(achada["detalhe"], "Planos: um dos 2 usuários fez 90% dos 20 registros")

    def test_um_usuario_so_e_volume_por_usuario(self):
        achadas = {o["tipo"]: o for o in self.de("D1")}
        self.assertEqual(achadas["um_usuario"]["detalhe"], "Planos: um usuário só fez 100% dos 30 registros")
        self.assertEqual(achadas["por_usuario"]["detalhe"], "Planos: 30 por usuário, com 1 usuário. O limite é 15")

    def test_acima_do_limite(self):
        self.assertEqual([o["detalhe"] for o in self.de("E1")], ["Agenda: 95, acima de 90"])

    def test_nome_de_usuario_nunca_sai_do_script(self):
        for arquivo, texto in textos_para_ia(self.e.pasta).items():
            self.assertNotIn("Secret", texto, arquivo)
        self.assertNotIn("Secret", self.saida)
        self.assertNotIn("Secret", rodar("oportunidades", "--pasta", self.e.pasta)[1])
        self.assertNotIn("Secret", rodar("carteira", "--pasta", self.e.pasta)[1])
        livro = openpyxl.load_workbook(self.e.pasta / "4-dados" / "rodadas" / REF / "health-score.xlsx", data_only=True)
        textos = " ".join(str(c.value) for aba in livro.worksheets for linha in aba.iter_rows() for c in linha if c.value is not None)
        self.assertNotIn("Secret", textos)

    def test_planilha_e_painel(self):
        livro = openpyxl.load_workbook(self.e.pasta / "4-dados" / "rodadas" / REF / "health-score.xlsx", data_only=True)
        textos = [str(c.value) for linha in livro["Oportunidades"].iter_rows() for c in linha if c.value is not None]
        self.assertIn("Usuário sobrecarregado", textos)
        self.assertIn("Cliente Fictício C1", textos)
        painel = (self.e.pasta / "4-dados" / "rodadas" / REF / "painel-geral.md").read_text(encoding="utf-8")
        self.assertIn("## Oportunidades de upgrade", painel)
        self.assertEqual(self.resumo["oportunidades"]["total"], 5)
        self.assertEqual(self.resumo["oportunidades"]["contas"], 4)
        self.assertEqual(self.resumo["oportunidades"]["receita_das_contas"], 18000)  # 3.000 + 4.000 + 5.000 + 6.000

    def test_reuniao_lembra_que_pode_ser_adocao(self):
        saida = rodar("reuniao", "--pasta", self.e.pasta, "--conta", self.m["Cliente Fictício B1"], "--data", REF)[1]
        self.assertIn("## Oportunidades mapeadas", saida)
        self.assertIn("é adoção, não upgrade", saida)
        self.assertIn("O que oferecer: Módulo de agenda", saida)

    def test_nao_pede_a_regra_de_quem_ja_definiu(self):
        self.assertNotIn("O que configura oportunidade de upgrade nesta empresa", [f["o_que_falta"] for f in self.resumo["falta_medir"]])


class TestMapa(unittest.TestCase):
    def test_nao_mexe_no_que_a_pessoa_escreveu_nem_duplica(self):
        e = Empresa("minima")
        try:
            montar(e)
            e.rodada()
            codigo, saida = rodar("oportunidades", "--pasta", e.pasta)
            self.assertEqual(codigo, 0, saida)
            self.assertIn("5 novas", saida)
            mapa = e.pasta / "3-clientes" / "oportunidades.md"
            texto = mapa.read_text(encoding="utf-8")
            self.assertEqual(texto.count("| mapeada |"), 5)
            self.assertNotIn("Fictício", texto)
            editado = texto.replace("| mapeada | {{ }} | {{ }} |", "| proposta | R$ 900 | Ligar na terça |", 1) + "\nMinha anotação solta.\n"
            mapa.write_text(editado, encoding="utf-8")
            codigo, saida = rodar("oportunidades", "--pasta", e.pasta)
            self.assertEqual(codigo, 0, saida)
            self.assertIn("0 novas", saida)
            self.assertIn("proposta 1", saida)
            self.assertIn("mapeada 4", saida)
            self.assertEqual(mapa.read_text(encoding="utf-8"), editado)
        finally:
            e.fechar()


class TestSemRegra(unittest.TestCase):
    def test_sem_regra_ainda_aponta_a_rotina_sem_uso_e_pergunta_o_resto(self):
        e = Empresa("minima")
        try:
            montar(e, regras="")
            codigo, saida = e.rodada()
            self.assertEqual(codigo, 0, saida)
            resumo = e.resumo()
            achadas = resumo["oportunidades"]["lista"]
            self.assertEqual([o["oportunidade"] for o in achadas], ["Agenda sem uso"])
            self.assertEqual(achadas[0]["detalhe"], "Agenda: sem uso, e 5 de 6 contas usam")
            self.assertIn("O que configura oportunidade de upgrade nesta empresa", [f["o_que_falta"] for f in resumo["falta_medir"]])
        finally:
            e.fechar()

    def test_rotina_que_quase_ninguem_usa_nao_vira_oportunidade_sozinha(self):
        e = Empresa("minima")
        try:
            montar(e, regras="")
            linhas = (e.entrada / "contas.csv").read_text(encoding="utf-8").splitlines()
            corpo = [l.split(",") for l in linhas]
            for linha in corpo[1:]:
                linha[5] = "0"
            escrever(e.entrada / "contas.csv", corpo)
            codigo, saida = e.rodada()
            self.assertEqual(codigo, 0, saida)
            self.assertEqual(e.resumo()["oportunidades"]["total"], 0)
        finally:
            e.fechar()

    def test_regra_errada_trava_e_explica(self):
        e = Empresa("minima")
        try:
            montar(e, regras=REGRAS + "| Regra ruim | plano | quando der | | |\n")
            codigo, saida = e.rodada()
            self.assertEqual(codigo, 1, saida)
            self.assertIn("oportunidade 'Regra ruim'", saida)
        finally:
            e.fechar()


if __name__ == "__main__":
    unittest.main()
