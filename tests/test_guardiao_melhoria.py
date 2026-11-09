"""Guardião da carteira e Melhoria contínua: os fatos vêm do script, a causa vem da conversa."""

import datetime as dt
import unittest

from apoio import REF, Empresa, rodar, textos_para_ia
from gerar_bases import REF as DATA_REF, escrever, md


class TestGuardiao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Empresa("completa")
        codigo, saida = cls.e.rodada()
        assert codigo == 0, saida
        cls.m = cls.e.mapa()
        cls.grande = cls.m["Hospital Fictício Grande Conta"]

    @classmethod
    def tearDownClass(cls):
        cls.e.fechar()

    def test_cuidados_separa_o_que_e_nosso(self):
        codigo, saida = rodar("cuidados", "--pasta", self.e.pasta)
        self.assertEqual(codigo, 0, saida)
        self.assertIn(f"Parado por nós, destravar primeiro: {self.m['Clínica Fictícia Parada Por Nós']}", saida)
        self.assertIn(f"Pendência do cliente: {self.m['Clínica Fictícia Verde Parada']}", saida)
        self.assertIn(f"Sem motivo, descobrir: {self.m['Clínica Fictícia Parada Sem Motivo']}", saida)
        self.assertNotIn("Fictíci", saida)

    def test_a_conta_mais_pesada_vem_primeiro(self):
        saida = rodar("cuidados", "--pasta", self.e.pasta)[1]
        trecho = saida.split("Contas com sinal de insatisfação")[1].splitlines()[1]
        self.assertIn(self.grande, trecho)
        self.assertIn("R$ 48.000", trecho)

    def test_plano_de_risco_traz_fatos_e_deixa_a_causa_em_branco(self):
        codigo, saida = rodar("plano", "--pasta", self.e.pasta, "--conta", self.grande, "--tipo", "risco", "--data", REF)
        self.assertEqual(codigo, 0, saida)
        self.assertIn("Renova em 45 dias", saida)
        self.assertIn("Sem contato há 90 dias", saida)
        self.assertIn("{{a causa específica", saida)
        self.assertIn("Revisei a sua conta e vi que {{o fato da conta}}", saida)
        self.assertIn("Ela ainda está lá?", saida)
        self.assertNotIn("Fictíci", saida)
        self.assertTrue((self.e.pasta / "3-clientes" / self.grande / f"plano-risco-{REF}.md").exists())

    def test_plano_nao_sobrescreve(self):
        conta = self.m["Clínica Fictícia Renova Bem"]
        rodar("plano", "--pasta", self.e.pasta, "--conta", conta, "--data", REF)
        arquivo = self.e.pasta / "3-clientes" / conta / f"plano-risco-{REF}.md"
        arquivo.write_text("meu plano", encoding="utf-8")
        saida = rodar("plano", "--pasta", self.e.pasta, "--conta", conta, "--data", REF)[1]
        self.assertIn("não mexi nele", saida)
        self.assertEqual(arquivo.read_text(encoding="utf-8"), "meu plano")

    def test_troca_de_contato_leva_o_valor_da_ficha(self):
        conta = self.m["Clínica Fictícia Cresceu"]
        rodar("nova-ficha", "--pasta", self.e.pasta, "--conta", conta)
        ficha = self.e.pasta / "3-clientes" / conta / "ficha.md"
        texto = ficha.read_text(encoding="utf-8")
        inicio = texto.index("{{pergunte isso depois")
        fim = texto.index("}}", inicio) + 2
        ficha.write_text(texto[:inicio] + "Paramos de perder plano" + texto[fim:], encoding="utf-8")
        codigo, saida = rodar("plano", "--pasta", self.e.pasta, "--conta", conta, "--tipo", "contato", "--data", REF)
        self.assertEqual(codigo, 0, saida)
        self.assertIn("Paramos de perder plano", saida)
        self.assertIn("Quem chegou", saida)

    def test_conta_que_nao_existe(self):
        codigo, saida = rodar("plano", "--pasta", self.e.pasta, "--conta", "CONTA-999")
        self.assertEqual(codigo, 2, saida)
        self.assertEqual(rodar("plano", "--pasta", self.e.pasta, "--conta", "../../fora")[0], 2)


COLUNAS = md(
    "Colunas",
    "Arquivos",
    "| arquivo | tipo |\n| --- | --- |\n| contas.csv | contas |\n| chamados.csv | eventos |\n",
    "\n## Colunas\n\n| arquivo | coluna | campo |\n| --- | --- | --- |\n| contas.csv | ID | conta_id |\n| contas.csv | Cliente | conta_nome |\n| contas.csv | MRR | receita |\n"
    "| contas.csv | Início | data_inicio |\n| contas.csv | Status | status |\n| contas.csv | Cancelamento | data_cancelamento |\n| contas.csv | Motivo | motivo_cancelamento |\n"
    "| contas.csv | NPS | nps |\n| contas.csv | Uso | \n| chamados.csv | ID | conta_id |\n| chamados.csv | Data | data_evento |\n| chamados.csv | Categoria | tema_evento |\n",
)
INDICADORES = md(
    "Como medir",
    "Indicadores",
    "| id | bloco | rotina | dado que prova | onde está o dado | coluna | coluna anterior | como ler | frequência esperada | criticidade | subir é |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
    "| chamados | chamados | Chamados | Chamado aberto | chamados.csv | | | eventos | 10 em 30 dias | média | ruim |\n"
    "| uso | rotina | Uso | Uso no mês | contas.csv | Uso | Uso ant | contagem | 5 | alta | bom |\n",
)


def br(dias: int) -> str:
    return (DATA_REF - dt.timedelta(days=dias)).strftime("%d/%m/%Y")


class TestMelhoria(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Empresa("minima")
        for outro in cls.e.entrada.iterdir():
            outro.unlink()
        contas = [["ID", "Cliente", "MRR", "Início", "Status", "Cancelamento", "Motivo", "NPS", "Uso", "Uso ant"]]
        for i in range(1, 7):
            contas.append([f"A{i}", f"Cliente Fictício A{i}", 1000 * i, br(400), "Ativo", "", "", 9 if i <= 2 else (5 if i == 3 else 7), 10, 20])
        contas.append(["N1", "Cliente Fictício Novo", 500, br(30), "Ativo", "", "", "", 10, 10])
        contas.append(["X1", "Cliente Fictício Saiu Agora", 700, br(400), "Cancelado", br(10), "Motivo Secreto Preço", "", "", ""])
        contas.append(["X2", "Cliente Fictício Saiu Antes", 800, br(400), "Cancelado", br(40), "não viu valor", "", "", ""])
        escrever(cls.e.entrada / "contas.csv", contas)
        chamados = [["ID", "Data", "Categoria"]]
        chamados += [["A1", br(5 + i), "Tema Secreto Estoque"] for i in range(6)]  # 6 nos últimos 30 dias
        chamados += [["A2", br(35 + i), "Tema Secreto Estoque"] for i in range(2)]  # 2 nos 30 antes
        chamados += [["A3", br(5 + i), "Tema Secreto Agenda"] for i in range(2)]  # poucos casos: fica de fora
        chamados += [["A4", br(5 + i), "Tema Secreto Login"] for i in range(3)]
        chamados += [["A5", br(35 + i), "Tema Secreto Login"] for i in range(4)]  # caiu: não cresce
        escrever(cls.e.entrada / "chamados.csv", chamados)
        (cls.e.pasta / "4-dados" / "colunas.md").write_text(COLUNAS, encoding="utf-8")
        (cls.e.pasta / "4-dados" / "como-medir.md").write_text(INDICADORES, encoding="utf-8")
        codigo, saida = cls.e.rodada()
        assert codigo == 0, saida
        cls.saida = saida
        cls.resumo = cls.e.resumo()
        cls.dados = cls.resumo["melhoria"]
        cls.m = cls.e.mapa()

    @classmethod
    def tearDownClass(cls):
        cls.e.fechar()

    def test_o_tema_que_cresce(self):
        temas = self.dados["temas_que_crescem"]
        self.assertEqual(len(temas), 1)
        self.assertEqual((temas[0]["antes"], temas[0]["agora"], temas[0]["variacao_pct"]), (2, 6, 200))
        self.assertRegex(temas[0]["tema"], r"^TEMA-\d\d$")

    def test_a_rotina_que_caiu_preocupa(self):
        uso = next(m for m in self.dados["o_que_mudou"] if m["rotina"] == "Uso")
        # 6 contas foram de 20 para 10; a conta nova ficou em 10: 130 para 70
        self.assertEqual((uso["antes"], uso["agora"]), (130, 70))
        self.assertEqual(uso["variacao_pct"], -46)
        self.assertEqual(uso["leitura"], "preocupa")

    def test_quem_saiu(self):
        saiu = self.dados["quem_saiu"]
        self.assertEqual((saiu["ultimos_30_dias"], saiu["30_dias_antes"]), (1, 1))
        self.assertEqual(saiu["sem_motivo_especifico"], 1)  # "não viu valor" não ensina nada
        self.assertEqual(len(saiu["motivos"]), 1)
        self.assertRegex(saiu["motivos"][0]["motivo"], r"^TEMA-\d\d$")

    def test_grupos(self):
        grupos = self.dados["grupos"]
        self.assertEqual(grupos["novos"], [self.m["Cliente Fictício Novo"]])
        self.assertEqual(sorted(grupos["ex_clientes"]), sorted([self.m["Cliente Fictício Saiu Agora"], self.m["Cliente Fictício Saiu Antes"]]))
        self.assertEqual(grupos["promotores"], [self.m["Cliente Fictício A2"], self.m["Cliente Fictício A1"]])  # maior receita primeiro
        self.assertEqual(grupos["detratores"], [self.m["Cliente Fictício A3"]])

    def test_comando_e_privacidade(self):
        codigo, saida = rodar("melhoria", "--pasta", self.e.pasta)
        self.assertEqual(codigo, 0, saida)
        self.assertIn("de 2 para 6", saida)
        self.assertIn("Esse é o primeiro problema a resolver", saida)
        self.assertNotIn("Secret", saida)
        self.assertNotIn("Fictíci", saida)
        for arquivo, texto in textos_para_ia(self.e.pasta).items():
            self.assertNotIn("Tema Secreto", texto, arquivo)
            self.assertNotIn("Motivo Secreto", texto, arquivo)

    def test_tema_com_valor_demais_parece_texto_livre(self):
        e = Empresa("minima")
        try:
            for outro in e.entrada.iterdir():
                outro.unlink()
            escrever(e.entrada / "contas.csv", [["ID", "Cliente", "MRR", "Início", "Status", "Cancelamento", "Motivo", "NPS", "Uso", "Uso ant"], ["A1", "Cliente Fictício A1", 100, br(400), "Ativo", "", "", "", 1, 1]])
            escrever(e.entrada / "chamados.csv", [["ID", "Data", "Categoria"]] + [["A1", br(3), f"Texto solto {i}"] for i in range(40)])
            (e.pasta / "4-dados" / "colunas.md").write_text(COLUNAS, encoding="utf-8")
            (e.pasta / "4-dados" / "como-medir.md").write_text(INDICADORES, encoding="utf-8")
            codigo, saida = e.rodada()
            self.assertEqual(codigo, 0, saida)
            resumo = e.resumo()
            self.assertEqual(resumo["melhoria"]["temas_que_crescem"], [])
            self.assertTrue(any("parece texto livre" in a for a in resumo["avisos_sobre_os_dados"]))
        finally:
            e.fechar()


if __name__ == "__main__":
    unittest.main()
