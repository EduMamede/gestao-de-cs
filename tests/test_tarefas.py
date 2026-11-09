"""A lista de tarefas e o arquivo de agenda: sai do que já existe, e a pessoa marca o que fez."""

import datetime as dt
import re
import sys
import unittest
from pathlib import Path

from apoio import REF, Empresa, rodar, textos_para_ia
from gerar_bases import REF as DATA_REF
from test_mesa import NOME, dias, itens_da_mesa

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import guarda_privacidade  # noqa: E402
from cslib import tarefas as tarefas_mod  # noqa: E402


def ler(e: Empresa) -> list:
    return tarefas_mod.ler_tarefas(e.pasta)


class TestTarefas(unittest.TestCase):
    def setUp(self):
        self.e = Empresa("completa")
        self.assertEqual(self.e.rodada()[0], 0)
        self.conta = self.e.mapa()[NOME]

    def tearDown(self):
        self.e.fechar()

    def _tarefas(self, *extras, data=REF):
        codigo, saida = rodar("tarefas", "--pasta", self.e.pasta, "--data", data, *extras)
        self.assertEqual(codigo, 0, saida)
        return saida

    def _plano_aprovado(self, acoes: str):
        rodar("plano", "--pasta", self.e.pasta, "--conta", self.conta, "--tipo", "risco", "--data", REF)
        arquivo = self.e.pasta / "3-clientes" / self.conta / f"plano-risco-{REF}.md"
        arquivo.write_text(arquivo.read_text(encoding="utf-8").replace("| {{ }} | {{ }} | {{ }} | {{ }} |", acoes), encoding="utf-8")
        rodar("mesa", "--pasta", self.e.pasta, "--data", REF)
        item = next(i for i in itens_da_mesa(self.e.pasta) if i["conta"] == self.conta)
        self.assertEqual(rodar("decidir", "--pasta", self.e.pasta, "--item", item["item"], "--decisao", "aprovado", "--mesmo-assim", "--data", REF)[0], 0)
        return arquivo

    def test_sem_nada_ainda_nao_inventa_tarefa(self):
        self.assertIn("Nenhuma tarefa em aberto", self._tarefas())

    def test_a_semana_vira_lista_dia_a_dia(self):
        self.assertEqual(rodar("semana", "--pasta", self.e.pasta, "--data", REF)[0], 0)
        saida = self._tarefas()
        self.assertIn("Hoje:", saida)
        self.assertIn("Olhar o que andou e atualizar a situação das metas", saida)
        lista = ler(self.e)
        crucial = [t for t in lista if t["de_onde"].endswith(":crucial")]
        self.assertTrue(crucial)
        self.assertLessEqual(len(crucial), tarefas_mod.MAX_POR_DIA)
        self.assertEqual({t["ate"] for t in crucial}, {REF})  # terça
        self.assertEqual({t["ate"] for t in lista if t["de_onde"].endswith(":metas")}, {dias(3)})  # sexta

    def test_a_tarefa_diz_o_que_fazer_e_nao_repete_a_conta_crucial(self):
        rodar("semana", "--pasta", self.e.pasta, "--data", REF)
        self._tarefas()
        lista = ler(self.e)
        crucial = [t for t in lista if t["de_onde"].endswith(":crucial")]
        self.assertTrue(all(t["texto"].startswith("Agir na conta: ") for t in crucial))
        self.assertTrue(all(len(t["texto"]) < 90 for t in crucial), [t["texto"] for t in crucial])
        contas = {t["conta"] for t in crucial}
        self.assertFalse([t for t in lista if t["de_onde"].endswith((":destravar", ":cliente")) and t["conta"] in contas])

    def test_o_que_era_de_um_dia_que_passou_entra_hoje(self):
        self.assertEqual(rodar("semana", "--pasta", self.e.pasta, "--data", dias(1))[0], 0)  # quarta
        self._tarefas(data=dias(1))
        self.assertEqual({t["ate"] for t in ler(self.e) if t["de_onde"].endswith(":crucial")}, {dias(1)})

    def test_rodar_de_novo_nao_duplica(self):
        rodar("semana", "--pasta", self.e.pasta, "--data", REF)
        self._tarefas()
        total = len(ler(self.e))
        self._tarefas()
        self.assertEqual(len(ler(self.e)), total)

    def test_acao_de_plano_aprovado_vira_tarefa_com_data_e_quem(self):
        self._plano_aprovado(f"| Ligar para a liderança | Ana do CS | {dias(1)} | voltar a lançar |")
        self._tarefas()
        tarefa = next(t for t in ler(self.e) if t["texto"] == "Ligar para a liderança")
        self.assertEqual((tarefa["ate"], tarefa["conta"], tarefa["quem"]), (dias(1), self.conta, "Ana do CS"))

    def test_acao_sem_data_tambem_entra(self):
        self._plano_aprovado("| Ligar para a liderança | CS | quando der | voltar |")
        self._tarefas()
        self.assertEqual(next(t for t in ler(self.e) if t["texto"] == "Ligar para a liderança")["ate"], "")

    def test_plano_sem_aprovacao_nao_vira_tarefa(self):
        rodar("plano", "--pasta", self.e.pasta, "--conta", self.conta, "--tipo", "risco", "--data", REF)
        arquivo = self.e.pasta / "3-clientes" / self.conta / f"plano-risco-{REF}.md"
        arquivo.write_text(arquivo.read_text(encoding="utf-8").replace("| {{ }} | {{ }} | {{ }} | {{ }} |", f"| Ligar | CS | {dias(1)} | x |"), encoding="utf-8")
        self.assertNotIn("Ligar", self._tarefas())

    def test_prazo_mudou_no_plano_e_a_tarefa_acompanha(self):
        arquivo = self._plano_aprovado(f"| Ligar | CS | {dias(1)} | x |")
        self._tarefas()
        arquivo.write_text(arquivo.read_text(encoding="utf-8").replace(dias(1), dias(5)), encoding="utf-8")
        self._tarefas()
        self.assertEqual(next(t for t in ler(self.e) if t["texto"] == "Ligar")["ate"], dias(5))

    def test_reuniao_vira_tarefa(self):
        rodar("reuniao", "--pasta", self.e.pasta, "--conta", self.conta, "--tipo", "revisao", "--data", dias(2))
        self._tarefas()
        tarefa = next(t for t in ler(self.e) if "Reunião de revisão" in t["texto"])
        self.assertEqual((tarefa["ate"], tarefa["conta"]), (dias(2), self.conta))

    def test_a_pessoa_acrescenta_e_marca(self):
        saida = self._tarefas("--adicionar", "Pedir o export ao financeiro", "--ate", "07/11", "--quem", "Eu")
        self.assertIn("Tarefa T-001 na lista", saida)
        self.assertEqual(ler(self.e)[0]["ate"], "2026-11-07")
        saida = self._tarefas("--feita", "t-001")
        self.assertIn("marcada como feita", saida)
        self.assertEqual(ler(self.e)[0]["feita_em"], REF)
        self.assertIn("Nenhuma tarefa em aberto", saida)
        self.assertEqual(rodar("tarefas", "--pasta", self.e.pasta, "--feita", "T-001")[0], 2)
        self.assertEqual(rodar("tarefas", "--pasta", self.e.pasta, "--feita", "T-999")[0], 2)

    def test_data_invalida_e_opcao_solta(self):
        self.assertEqual(rodar("tarefas", "--pasta", self.e.pasta, "--adicionar", "x", "--ate", "amanhã")[0], 2)
        self.assertEqual(rodar("tarefas", "--pasta", self.e.pasta, "--ate", "07/11")[0], 2)

    def test_a_pessoa_escreve_na_tabela_e_o_que_ela_escreveu_fica(self):
        self._tarefas("--adicionar", "Primeira")
        caminho = self.e.pasta / "tarefas.md"
        texto = caminho.read_text(encoding="utf-8").replace("- Nada ainda.", "- Combinei com a liderança.")
        texto = texto.rstrip() + "\n|  | 07/11 |  | Escrita à mão | Eu |  |  |\n"
        linha = next(l for l in texto.splitlines() if l.startswith("| T-001"))
        texto = texto.replace(linha, linha.rstrip().rstrip("|").rstrip() + " x |")
        caminho.write_text(texto, encoding="utf-8")
        self._tarefas()
        texto = caminho.read_text(encoding="utf-8")
        self.assertIn("Combinei com a liderança", texto)
        lista = ler(self.e)
        self.assertEqual(lista[0]["feita_em"], REF)
        self.assertEqual((lista[1]["tarefa"], lista[1]["ate"], lista[1]["de_onde"]), ("T-002", "2026-11-07", "você"))

    def test_marcar_tarefa_resolve_o_aviso_de_prazo_e_o_contrario(self):
        self._plano_aprovado(f"| Ligar para a liderança | CS | {dias(1)} | x |\n| Rever o estoque | CS | {dias(1)} | x |")
        self.assertEqual(rodar("hoje", "--pasta", self.e.pasta, "--data", dias(3))[0], 0)
        avisos = {i["o_que_e"]: i for i in itens_da_mesa(self.e.pasta) if i["o_que_e"].startswith("Passou do prazo")}
        self.assertEqual(len(avisos), 2)
        por_texto = {t["texto"]: t["tarefa"] for t in ler(self.e)}

        self._tarefas("--feita", por_texto["Ligar para a liderança"], data=dias(3))
        aviso_ligar = next(i for o, i in avisos.items() if "Ligar" in o)
        self.assertEqual(rodar("decidir", "--pasta", self.e.pasta, "--item", next(i for o, i in avisos.items() if "estoque" in o)["item"], "--decisao", "resolvido", "--data", dias(3))[0], 0)
        saida = rodar("hoje", "--pasta", self.e.pasta, "--data", dias(4))[1]
        self.assertEqual(next(i for i in itens_da_mesa(self.e.pasta) if i["item"] == aviso_ligar["item"])["decisao"], "resolvido")
        self.assertTrue(next(t for t in ler(self.e) if t["texto"] == "Rever o estoque")["feita_em"])
        self.assertNotIn("Passou do prazo", saida)

    def test_tarefa_ja_feita_nao_vira_aviso_de_prazo(self):
        self._plano_aprovado(f"| Ligar | CS | {dias(1)} | x |")
        self._tarefas()
        self._tarefas("--feita", next(t["tarefa"] for t in ler(self.e) if t["texto"] == "Ligar"))
        rodar("hoje", "--pasta", self.e.pasta, "--data", dias(3))
        self.assertFalse([i for i in itens_da_mesa(self.e.pasta) if i["o_que_e"].startswith("Passou do prazo")])

    def test_nao_fica_liberado_para_o_agente(self):
        self.assertNotIn("tarefas", guarda_privacidade.LIBERADOS)

    def test_modo_protegido_so_codigos_e_a_copia_tem_nomes(self):
        rodar("semana", "--pasta", self.e.pasta, "--data", REF)
        saida = self._tarefas()
        self.assertNotIn("Fictíci", saida)
        for nome, texto in textos_para_ia(self.e.pasta).items():
            self.assertNotIn("Fictíci", texto, nome)
        self.assertIn("Fictíci", (self.e.pasta / "com-nomes" / "tarefas.md").read_text(encoding="utf-8"))
        self.assertIn("Fictíci", (self.e.pasta / "com-nomes" / "agenda.ics").read_text(encoding="utf-8"))


class TestPaginaComTarefas(unittest.TestCase):
    def setUp(self):
        self.e = Empresa("completa")
        self.assertEqual(self.e.rodada()[0], 0)

    def tearDown(self):
        self.e.fechar()

    def _hoje(self, data=REF):
        codigo, saida = rodar("hoje", "--pasta", self.e.pasta, "--data", data)
        self.assertEqual(codigo, 0, saida)
        return saida

    def test_sem_lista_mostra_o_dia_da_agenda(self):
        self.assertIn("**Terça: o mais crucial.**", self._hoje().split("## Para fazer")[1])

    def test_com_lista_mostra_as_de_hoje_e_a_atrasada_primeiro(self):
        rodar("semana", "--pasta", self.e.pasta, "--data", "2026-11-02")
        self._hoje("2026-11-02")
        bloco = self._hoje().split("## Para fazer")[1].split("## O que está marcado")[0].strip()
        self.assertTrue(bloco.startswith("- **Atrasada") or bloco.startswith("- T-"), bloco)
        self.assertIn("em tarefas.md", bloco)

    def test_atrasada_aparece_com_a_data(self):
        rodar("tarefas", "--pasta", self.e.pasta, "--adicionar", "Coisa velha", "--ate", dias(-2), "--data", REF)
        self.assertIn(f"**Atrasada, era {(DATA_REF - dt.timedelta(days=2)).strftime('%d/%m')}.** T-001 · Coisa velha", self._hoje())

    def test_rotina_grava_a_agenda(self):
        self.assertEqual(rodar("rotina", "--pasta", self.e.pasta, "--data", REF)[0], 0)
        self.assertTrue((self.e.pasta / "com-nomes" / "agenda.ics").exists())
        self.assertTrue(ler(self.e))
        self.assertLess(len((self.e.pasta / "hoje.md").read_text(encoding="utf-8").splitlines()), 50)


class TestAgendaIcs(unittest.TestCase):
    def _texto(self, tarefas, fatos=None, hoje=DATA_REF):
        return tarefas_mod.texto_da_agenda(tarefas, fatos or {}, hoje, lambda c: f"{c} Nome")

    def test_arquivo_segue_o_formato(self):
        t = {**tarefas_mod.nova("Ligar, com calma; sem pressa", DATA_REF + dt.timedelta(days=1), "CONTA-001", "CS", "x"), "tarefa": "T-001"}
        texto = self._texto([t])
        self.assertTrue(texto.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertTrue(texto.endswith("END:VCALENDAR\r\n"))
        self.assertNotIn("\n", texto.replace("\r\n", ""))
        self.assertIn("DTSTART;VALUE=DATE:20261104\r\n", texto)
        self.assertIn("DTEND;VALUE=DATE:20261105\r\n", texto)  # o fim do dia inteiro é o dia seguinte
        desdobrado = texto.replace("\r\n ", "")
        self.assertIn("SUMMARY:CS T-001 · CONTA-001 Nome: Ligar\\, com calma\\; sem pressa", desdobrado)
        for campo in ("UID:", "DTSTAMP:", "TRANSP:TRANSPARENT"):
            self.assertIn(campo, texto)

    def test_linha_longa_e_dobrada_sem_cortar_acento(self):
        t = {**tarefas_mod.nova("ação " * 60, DATA_REF, None, None, "x"), "tarefa": "T-001"}
        texto = self._texto([t])
        for linha in texto.encode("utf-8").split(b"\r\n"):
            self.assertLessEqual(len(linha), 75)
            linha.decode("utf-8")  # um acento cortado no meio quebraria aqui
        self.assertIn("ação ação", texto.replace("\r\n ", ""))

    def test_o_identificador_nao_muda_de_um_dia_para_o_outro(self):
        t = {**tarefas_mod.nova("Ligar", DATA_REF + dt.timedelta(days=3), "CONTA-001", None, "x"), "tarefa": "T-001"}
        uid = re.search(r"UID:(.+?)\r\n", self._texto([t])).group(1)
        self.assertEqual(uid, re.search(r"UID:(.+?)\r\n", self._texto([t], hoje=DATA_REF + dt.timedelta(days=1))).group(1))
        outra = {**tarefas_mod.nova("Outra", DATA_REF + dt.timedelta(days=3), "CONTA-001", None, "x"), "tarefa": "T-002"}
        self.assertNotEqual(uid, re.search(r"UID:(.+?)\r\n", self._texto([outra])).group(1))

    def test_so_o_que_vem_pela_frente_e_nao_o_que_foi_feito(self):
        passada = {**tarefas_mod.nova("Passada", DATA_REF - dt.timedelta(days=1), None, None, "x"), "tarefa": "T-001"}
        feita = {**tarefas_mod.nova("Feita", DATA_REF + dt.timedelta(days=1), None, None, "x"), "tarefa": "T-002", "feita_em": REF}
        sem_data = {**tarefas_mod.nova("Sem data", None, None, None, "x"), "tarefa": "T-003"}
        self.assertNotIn("BEGIN:VEVENT", self._texto([passada, feita, sem_data]))

    def test_renovacao_e_contato_do_export_entram(self):
        fatos = {"CONTA-009": {"conta": "CONTA-009", "renovacao": dias(10), "proximo_contato": dias(2)}}
        texto = self._texto([], fatos).replace("\r\n ", "")
        self.assertIn("Renovação: CONTA-009 Nome", texto)
        self.assertIn("Contato marcado: CONTA-009 Nome", texto)
        self.assertEqual(texto.count("BEGIN:VEVENT"), 2)


if __name__ == "__main__":
    unittest.main()
