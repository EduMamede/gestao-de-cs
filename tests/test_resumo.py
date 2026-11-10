"""O resumo da conta antes de uma conversa: uma página dos últimos 90 dias, sem número inventado."""

import datetime as dt
import json
import unittest

from apoio import REF, Empresa, rodar
from gerar_bases import REF as DATA_REF
from test_mesa import NOME, ajustar, dias


class TestResumo(unittest.TestCase):
    def setUp(self):
        self.e = Empresa("completa")
        ajustar(self.e, NOME, Planos_lançados_30d=10)
        self.assertEqual(self.e.rodada()[0], 0)
        self.m = self.e.mapa()
        self.conta = self.m[NOME]

    def tearDown(self):
        self.e.fechar()

    def _resumo(self, conta=None, data=REF):
        codigo, saida = rodar("resumo", "--pasta", self.e.pasta, "--conta", conta or self.conta, "--data", data)
        self.assertEqual(codigo, 0, saida)
        return saida

    def test_tem_as_sete_partes_e_grava_o_arquivo(self):
        saida = self._resumo()
        for titulo in ("## Em uma linha", "## O que mudou", "## O que já ganharam", "## Em aberto", "## Quem é quem", "## A última conversa", "## O que perguntar"):
            self.assertIn(titulo, saida)
        self.assertTrue((self.e.pasta / "3-clientes" / self.conta / f"resumo-{REF}.md").exists())

    def test_primeira_rodada_diz_que_nao_tem_historico(self):
        saida = self._resumo()
        self.assertIn("primeira rodada: ainda sem histórico", saida)
        self.assertIn("Ainda sem rodada anterior na janela para comparar", saida)

    def test_rotina_que_caiu_aparece_com_os_numeros_e_vira_pergunta(self):
        ajustar(self.e, NOME, Planos_lançados_30d=4)
        self.assertEqual(self.e.rodada(dias(30))[0], 0)
        saida = self._resumo(data=dias(30))
        self.assertIn("Acompanhamento do plano: de 10 para 4 desde 03/11, piorou", saida)
        self.assertIn("O que mudou em Acompanhamento do plano desde 03/11?", saida)

    def test_rodada_fora_da_janela_nao_entra(self):
        ajustar(self.e, NOME, Planos_lançados_30d=4)
        self.assertEqual(self.e.rodada(dias(120))[0], 0)
        saida = self._resumo(data=dias(120))
        self.assertIn("primeira rodada: ainda sem histórico", saida)

    def test_formula_diferente_nao_compara_a_nota(self):
        self.assertEqual(self.e.rodada(dias(30))[0], 0)
        resumo = self.e.pasta / "4-dados" / "rodadas" / dias(30) / "resumo.json"
        dados = json.loads(resumo.read_text(encoding="utf-8"))
        dados["formula"]["versao"] = "outra"
        resumo.write_text(json.dumps(dados), encoding="utf-8")
        self.assertIn("a fórmula mudou na janela, então a nota não se compara", self._resumo(data=dias(30)))

    def test_o_que_a_pessoa_escreveu_na_ficha_aparece(self):
        rodar("nova-ficha", "--pasta", self.e.pasta, "--conta", self.conta)
        ficha = self.e.pasta / "3-clientes" / self.conta / "ficha.md"
        texto = ficha.read_text(encoding="utf-8")
        texto = texto.replace("- {{data: o que foi combinado}}", "- 01/11: combinamos treinar a recepção")
        texto = texto.replace("| Patrocinador | {{ }} | |", "| Patrocinador | Diretora clínica | decide a renovação |")
        inicio = texto.index("{{pergunte isso depois")
        texto = texto[:inicio] + "Paramos de perder plano" + texto[texto.index("}}", inicio) + 2 :]
        ficha.write_text(texto, encoding="utf-8")
        saida = self._resumo()
        self.assertIn("**O que mais ajudamos vocês hoje?** Paramos de perder plano", saida)
        self.assertIn("Patrocinador: Diretora clínica (decide a renovação)", saida)
        self.assertIn("Na ficha: 01/11: combinamos treinar a recepção", saida)
        self.assertNotIn("O que mais ajudamos vocês hoje?\n", saida.split("## O que perguntar")[1])
        self.assertNotIn("Quem decide a renovação", saida)
        self.assertNotIn("{{", saida)

    def test_sem_valor_nem_patrocinador_vira_pergunta(self):
        fatos = self.e.pasta / "4-dados" / "rodadas" / REF / "contas.json"
        dados = json.loads(fatos.read_text(encoding="utf-8"))
        dados[self.conta]["contatos_anotados"]["patrocinador"] = False
        fatos.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        perguntas = self._resumo().split("## O que perguntar")[1]
        self.assertIn("O que mais ajudamos vocês hoje?", perguntas)
        self.assertIn("Quem decide a renovação do lado de vocês?", perguntas)

    def test_mesa_tarefa_e_conversa_da_reuniao_entram(self):
        rodar("plano", "--pasta", self.e.pasta, "--conta", self.conta, "--tipo", "risco", "--data", REF)
        rodar("tarefas", "--pasta", self.e.pasta, "--adicionar", "Ligar para a diretora", "--ate", dias(2), "--conta", self.conta, "--data", REF)
        reuniao = self.e.pasta / "3-clientes" / self.conta / "reunioes"
        rodar("reuniao", "--pasta", self.e.pasta, "--conta", self.conta, "--tipo", "revisao", "--data", dias(-10))
        arquivo = reuniao / f"{dias(-10)}-revisao.md"
        arquivo.write_text(arquivo.read_text(encoding="utf-8").replace("- Nada ainda.", "- Pediram relatório mensal", 1), encoding="utf-8")
        saida = self._resumo()
        aberto = saida.split("## Em aberto")[1].split("## Quem é quem")[0]
        self.assertIn("Na mesa: M-", aberto)
        self.assertIn(f"Tarefa T-001, até {(DATA_REF + dt.timedelta(days=2)).strftime('%d/%m')}: Ligar para a diretora", aberto)
        self.assertIn(f"Na reunião de {(DATA_REF - dt.timedelta(days=10)).strftime('%d/%m')}: Pediram relatório mensal", saida)

    def test_conta_com_risco_nao_repete_chamado_e_avisa_na_oportunidade(self):
        grande = self.m["Hospital Fictício Grande Conta"]
        saida = self._resumo(grande)
        self.assertEqual(saida.count("Chamados"), 1, saida)
        self.assertIn("Resolva a insatisfação primeiro", saida)

    def test_modo_protegido_so_codigo_e_a_copia_tem_o_nome(self):
        saida = self._resumo()
        self.assertNotIn("Fictíci", saida)
        self.assertNotIn("Fictíci", (self.e.pasta / "3-clientes" / self.conta / f"resumo-{REF}.md").read_text(encoding="utf-8"))
        self.assertIn(NOME, (self.e.pasta / "com-nomes" / f"resumo-{self.conta}-{REF}.md").read_text(encoding="utf-8"))

    def test_conta_que_nao_existe(self):
        codigo, saida = rodar("resumo", "--pasta", self.e.pasta, "--conta", "CONTA-999")
        self.assertEqual(codigo, 2, saida)
        self.assertEqual(rodar("resumo", "--pasta", self.e.pasta, "--conta", "../fora")[0], 2)

    def test_reuniao_de_amanha_ja_encontra_o_resumo_pronto(self):
        rodar("reuniao", "--pasta", self.e.pasta, "--conta", self.conta, "--tipo", "revisao", "--data", dias(1))
        codigo, saida = rodar("hoje", "--pasta", self.e.pasta, "--data", REF)
        self.assertEqual(codigo, 0, saida)
        self.assertTrue((self.e.pasta / "3-clientes" / self.conta / f"resumo-{REF}.md").exists())
        self.assertIn(f"Reunião de revisão: {self.conta} (resumo pronto)", saida)

    def test_reuniao_longe_nao_gera_resumo(self):
        rodar("reuniao", "--pasta", self.e.pasta, "--conta", self.conta, "--tipo", "revisao", "--data", dias(5))
        rodar("hoje", "--pasta", self.e.pasta, "--data", REF)
        self.assertFalse((self.e.pasta / "3-clientes" / self.conta / f"resumo-{REF}.md").exists())

    def test_resumo_nao_entra_na_mesa(self):
        self._resumo()
        rodar("mesa", "--pasta", self.e.pasta, "--data", REF)
        from cslib.mesa import ler_itens

        self.assertFalse([i for i in ler_itens(self.e.pasta) if "resumo" in i["arquivo"]])


if __name__ == "__main__":
    unittest.main()
