"""A rotina roda sozinha, sem IA: lê o export, atualiza a nota, monta a semana, reavalia o urgente e refaz a página."""

import datetime as dt
import json
import os
import shutil
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from apoio import REF, Empresa, rodar
from gerar_bases import REF as DATA_REF
from test_mesa import NOME, ajustar, dias, itens_da_mesa

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import guarda_privacidade  # noqa: E402
from cslib import rotina as rotina_mod  # noqa: E402

# 2026-11-03 é terça. A segunda daquela semana é 2026-11-02.
SEGUNDA = "2026-11-02"


def largar_export(e: Empresa, nome="contas.csv", antigo=True) -> Path:
    """Como se a pessoa, ou o sistema dela, tivesse deixado o arquivo na pasta."""
    novos = e.pasta / "4-dados" / "entradas" / "novos"
    novos.mkdir(parents=True, exist_ok=True)
    destino = novos / nome
    shutil.copyfile(e.entrada / "contas.csv", destino)
    if antigo:
        momento = time.time() - 600
        os.utime(destino, (momento, momento))
    return destino


class TestRotina(unittest.TestCase):
    def setUp(self):
        self.e = Empresa("completa")
        self.m = None

    def tearDown(self):
        self.e.fechar()

    def _rotina(self, data=REF):
        codigo, saida = rodar("rotina", "--pasta", self.e.pasta, "--data", data)
        self.assertEqual(codigo, 0, saida)
        return saida

    def test_primeira_vez_faz_tudo_em_sequencia(self):
        saida = self._rotina()
        self.assertIn("o health score foi atualizado", saida)
        self.assertIn(f"Semana criada em 2-metas/semana-{SEGUNDA}.md", saida)
        self.assertIn("Preparados: 3 arquivos", saida)
        self.assertIn("# Hoje, 03/11/2026", saida)
        self.assertTrue((self.e.pasta / "4-dados" / "rodadas" / REF / "health-score.xlsx").exists())
        self.assertTrue((self.e.pasta / "2-metas" / f"semana-{SEGUNDA}.md").exists())
        self.assertTrue((self.e.pasta / "hoje.md").exists())
        self.assertGreaterEqual(len(itens_da_mesa(self.e.pasta)), 3)

    def test_rodar_duas_vezes_nao_duplica(self):
        self._rotina()
        itens = len(itens_da_mesa(self.e.pasta))
        semana = (self.e.pasta / "2-metas" / f"semana-{SEGUNDA}.md").read_text(encoding="utf-8")
        saida = self._rotina()
        self.assertIn("Sem export novo: o health score não mudou", saida)
        self.assertEqual(len(itens_da_mesa(self.e.pasta)), itens)
        self.assertEqual((self.e.pasta / "2-metas" / f"semana-{SEGUNDA}.md").read_text(encoding="utf-8"), semana)

    def test_o_que_a_pessoa_escreveu_na_semana_fica(self):
        self._rotina()
        caminho = self.e.pasta / "2-metas" / f"semana-{SEGUNDA}.md"
        caminho.write_text("minha semana", encoding="utf-8")
        self._rotina(dias(1))
        self.assertEqual(caminho.read_text(encoding="utf-8"), "minha semana")

    def test_export_novo_atualiza_o_health_score_e_nao_some(self):
        self._rotina()
        largar_export(self.e)
        saida = self._rotina(dias(7))
        self.assertIn("Export novo (1 arquivo): o health score foi atualizado", saida)
        self.assertTrue((self.e.pasta / "4-dados" / "rodadas" / dias(7) / "health-score.xlsx").exists())
        self.assertTrue((self.e.pasta / "4-dados" / "entradas" / dias(7) / "contas.csv").exists())
        self.assertFalse((self.e.pasta / "4-dados" / "entradas" / "novos" / "contas.csv").exists())

    def test_segunda_seguinte_monta_a_semana_nova(self):
        self._rotina()
        saida = self._rotina(dias(6))  # 2026-11-09, segunda
        self.assertIn("Semana criada em 2-metas/semana-2026-11-09.md", saida)
        self.assertIn("Sem export novo", saida)

    def test_na_sexta_nao_monta_semana(self):
        saida = self._rotina(dias(3))  # 2026-11-06, sexta
        self.assertNotIn("Semana criada", saida)
        self.assertFalse(list((self.e.pasta / "2-metas").glob("semana-*.md")))

    def test_segunda_com_computador_desligado_monta_na_terca(self):
        self._rotina()
        saida = self._rotina(dias(7))  # 2026-11-10, terça: a rotina de segunda não rodou
        self.assertIn("Semana criada em 2-metas/semana-2026-11-09.md", saida)

    def test_arquivo_ainda_sendo_gravado_espera(self):
        self._rotina()
        largar_export(self.e, antigo=False)
        saida = self._rotina(dias(7))
        self.assertIn("1 arquivo ficou em entradas/novos", saida)
        self.assertTrue((self.e.pasta / "4-dados" / "entradas" / "novos" / "contas.csv").exists())

    def test_ja_houve_rodada_hoje_o_arquivo_espera(self):
        self._rotina()
        largar_export(self.e)
        saida = self._rotina()
        self.assertIn("1 arquivo ficou em entradas/novos", saida)
        self.assertTrue((self.e.pasta / "4-dados" / "entradas" / "novos" / "contas.csv").exists())

    def test_nome_repetido_nao_sobrescreve(self):
        self._rotina()
        destino = self.e.pasta / "4-dados" / "entradas" / dias(7)
        destino.mkdir(parents=True)
        (destino / "contas.csv").write_text("o que já estava", encoding="utf-8")
        largar_export(self.e)
        self._rotina(dias(7))
        self.assertEqual((destino / "contas.csv").read_text(encoding="utf-8"), "o que já estava")

    def test_arquivo_estranho_fica_onde_esta(self):
        self._rotina()
        estranho = self.e.pasta / "4-dados" / "entradas" / "novos" / "anotacao.docx"
        estranho.write_text("x", encoding="utf-8")
        self.assertIn("Sem export novo", self._rotina(dias(7)))
        self.assertTrue(estranho.exists())

    def test_export_que_nao_le_conta_avisa_na_pagina_e_tenta_de_novo(self):
        self._rotina()
        novos = self.e.pasta / "4-dados" / "entradas" / "novos"
        arquivo = novos / "contas.csv"
        arquivo.write_text("Outra coisa;Nada\n1;2\n", encoding="utf-8")
        momento = time.time() - 600
        os.utime(arquivo, (momento, momento))
        saida = self._rotina(dias(7))
        self.assertIn("não rodou", saida)
        self.assertIn("Os números abaixo são da rodada anterior", saida)
        self.assertIn("Dados da rodada de 03/11/2026", saida)
        self.assertIn("rodada: erro", (self.e.pasta / "4-dados" / "rotina.log").read_text(encoding="utf-8"))
        self.assertIn("não rodou", self._rotina(dias(8)))

    def test_sem_nenhuma_rodada_diz_o_que_fazer(self):
        shutil.rmtree(self.e.entrada)
        saida = self._rotina()
        self.assertIn("Ainda não há rodada", saida)
        self.assertIn("4-dados/entradas/novos", saida)

    def test_falha_inesperada_fica_registrada_sem_expor_dado(self):
        self._rotina()
        from cslib.rotina import registrar_falha

        try:
            raise ValueError("Clínica Fictícia Sigilosa")
        except ValueError as erro:
            registrar_falha(self.e.pasta, DATA_REF, erro)
        registro = (self.e.pasta / "4-dados" / "rotina.log").read_text(encoding="utf-8")
        self.assertIn("ERRO: ValueError", registro)
        self.assertNotIn("Sigilosa", registro)
        self.assertIn("não terminou", (self.e.pasta / "hoje.md").read_text(encoding="utf-8"))

    def test_modo_protegido_so_codigos_e_copias_com_nomes(self):
        saida = self._rotina()
        self.assertNotIn("Fictíci", saida)
        for arquivo in ("hoje.md", "mesa.md", "4-dados/rotina.log", f"2-metas/semana-{SEGUNDA}.md"):
            self.assertNotIn("Fictíci", (self.e.pasta / arquivo).read_text(encoding="utf-8"), arquivo)
        self.assertIn("Fictíci", (self.e.pasta / "com-nomes" / "hoje.md").read_text(encoding="utf-8"))
        self.assertIn("Fictíci", (self.e.pasta / "com-nomes" / f"semana-{SEGUNDA}.md").read_text(encoding="utf-8"))

    def test_validar_mostra_o_que_espera_e_nao_confunde_com_entrada(self):
        self._rotina()
        largar_export(self.e)
        codigo, saida = rodar("validar", "--pasta", self.e.pasta)
        self.assertEqual(codigo, 0, saida)
        self.assertIn("Esperando em entradas/novos: 1 arquivo", saida)
        self.assertNotIn("Última entrada: novos", saida)


class TestUrgentes(unittest.TestCase):
    def setUp(self):
        self.e = Empresa("completa")
        ajustar(self.e, NOME, Planos_lançados_30d=9)
        self.assertEqual(self.e.rodada()[0], 0)
        self.conta = self.e.mapa()[NOME]

    def tearDown(self):
        self.e.fechar()

    def _hoje(self, data):
        codigo, saida = rodar("hoje", "--pasta", self.e.pasta, "--data", data)
        self.assertEqual(codigo, 0, saida)
        return saida

    def _rodada_com(self, data, **mudanca):
        """Uma rodada nova, com a foto da conta alterada à mão no contas.json: é o que o gatilho lê."""
        self.assertEqual(self.e.rodada(data)[0], 0)
        caminho = self.e.pasta / "4-dados" / "rodadas" / data / "contas.json"
        fatos = json.loads(caminho.read_text(encoding="utf-8"))
        fatos[self.conta].update(mudanca)
        caminho.write_text(json.dumps(fatos, ensure_ascii=False), encoding="utf-8")

    def _item_urgente(self):
        return [i for i in itens_da_mesa(self.e.pasta) if i["urgente"] and i["conta"] == self.conta]

    def test_rodada_sem_novidade_nao_inventa_urgencia(self):
        self.assertEqual(self.e.rodada(dias(1))[0], 0)
        self._hoje(dias(1))
        self.assertEqual(self._item_urgente(), [])

    def test_cancelamento_agendado_novo_entra_na_fila_com_plano(self):
        self._rodada_com(dias(1), sinais=[{"codigo": "cancelamento_agendado", "texto": "Cancelamento já agendado"}])
        saida = self._hoje(dias(1))
        self.assertIn(f"**Urgente: cancelamento agendado.** M-", saida)
        itens = self._item_urgente()
        self.assertEqual(len(itens), 1)
        self.assertTrue((self.e.pasta / itens[0]["arquivo"]).exists())
        self.assertIn("{{a causa específica", (self.e.pasta / itens[0]["arquivo"]).read_text(encoding="utf-8"))

    def test_o_urgente_vem_primeiro_na_pagina(self):
        rodar("plano", "--pasta", self.e.pasta, "--conta", self.e.mapa()["Clínica Fictícia Cresceu"], "--tipo", "risco", "--data", REF)
        self._rodada_com(dias(1), sinais=[{"codigo": "cancelamento_agendado", "texto": "x"}])
        bloco = self._hoje(dias(1)).split("## O que espera você")[1]
        self.assertTrue(bloco.strip().startswith("- **Urgente"))

    def test_nao_entra_duas_vezes(self):
        self._rodada_com(dias(1), sinais=[{"codigo": "cancelamento_agendado", "texto": "x"}])
        self._hoje(dias(1))
        total = len(itens_da_mesa(self.e.pasta))
        self._hoje(dias(2))
        self.assertEqual(len(itens_da_mesa(self.e.pasta)), total)

    def test_caiu_para_a_vermelha_so_quando_e_novo(self):
        anterior = self.e.pasta / "4-dados" / "rodadas" / REF / "contas.json"
        fatos = json.loads(anterior.read_text(encoding="utf-8"))
        self.assertNotEqual(fatos[self.conta]["faixa"], "possivel_churn")
        self._rodada_com(dias(1), faixa="possivel_churn")
        self._hoje(dias(1))
        self.assertIn("caiu para a faixa vermelha", self._item_urgente()[0]["urgente"])
        self._rodada_com(dias(2), faixa="possivel_churn")
        # A rodada de antes já era vermelha: não é novo. E o gatilho não duplica o item.
        self._hoje(dias(2))
        self.assertEqual(len(self._item_urgente()), 1)

    def test_formula_nova_nao_vira_urgencia_de_faixa(self):
        from cslib.hoje import gatilhos_de_urgencia

        item = {"conta": "CONTA-1", "receita": 10, "faixa": "possivel_churn", "sinais": [], "renovacao": None, "rotinas": [], "chance_churn_pct": None}
        antes = {"CONTA-1": {**item, "faixa": "saudavel"}}
        self.assertEqual(len(gatilhos_de_urgencia(DATA_REF, {"formula": {"mudou_nesta_rodada": False}}, {"CONTA-1": item}, antes)), 1)
        self.assertEqual(gatilhos_de_urgencia(DATA_REF, {"formula": {"mudou_nesta_rodada": True}}, {"CONTA-1": item}, antes), [])

    def test_financeiro_sem_rodada_anterior_nao_e_novo(self):
        from cslib.hoje import gatilhos_de_urgencia

        item = {"conta": "CONTA-1", "receita": 10, "faixa": "saudavel", "sinais": [{"codigo": "financeiro", "texto": "x"}], "renovacao": None, "rotinas": [], "chance_churn_pct": None}
        self.assertEqual(gatilhos_de_urgencia(DATA_REF, {"formula": {}}, {"CONTA-1": item}, {}), [])
        outra = {**item, "conta": "CONTA-2", "sinais": []}
        self.assertEqual(gatilhos_de_urgencia(DATA_REF, {"formula": {}}, {"CONTA-1": item}, {"CONTA-2": outra})[0][2], "problema financeiro novo")

    def test_renovacao_com_risco_entra_pela_data_sem_export_novo(self):
        """Sem rodada nova, o que muda é o calendário: a mesma conta vira urgente quando a data chega perto."""
        grande = self.e.mapa()["Hospital Fictício Grande Conta"]
        fatos = json.loads((self.e.pasta / "4-dados" / "rodadas" / REF / "contas.json").read_text(encoding="utf-8"))
        renova = dt.date.fromisoformat(fatos[grande]["renovacao"])
        longe = (renova - dt.timedelta(days=40)).isoformat()
        perto = (renova - dt.timedelta(days=20)).isoformat()
        self._hoje(longe)
        self.assertFalse([i for i in itens_da_mesa(self.e.pasta) if i["conta"] == grande and "renova em" in i["urgente"]])
        saida = self._hoje(perto)
        self.assertIn(f"renova em {renova.strftime('%d/%m')}, com sinal de insatisfação", saida)
        item = next(i for i in itens_da_mesa(self.e.pasta) if i["conta"] == grande and "renova em" in i["urgente"])
        self.assertIn("renovacao.md", item["arquivo"])

    def test_item_ja_decidido_vira_aviso_para_rever_uma_vez(self):
        rodar("plano", "--pasta", self.e.pasta, "--conta", self.conta, "--tipo", "risco", "--data", REF)
        rodar("mesa", "--pasta", self.e.pasta, "--data", REF)
        self.assertEqual(rodar("decidir", "--pasta", self.e.pasta, "--item", "M-001", "--decisao", "aprovado", "--mesmo-assim", "--data", REF)[0], 0)
        self._rodada_com(dias(1), sinais=[{"codigo": "cancelamento_agendado", "texto": "x"}])
        self._hoje(dias(1))
        self._hoje(dias(2))
        itens = self._item_urgente()
        self.assertEqual([i["o_que_e"] for i in itens], ["Rever o plano"])
        self.assertEqual(rodar("decidir", "--pasta", self.e.pasta, "--item", itens[0]["item"], "--decisao", "aprovado", "--data", dias(2))[0], 2)
        self.assertEqual(rodar("decidir", "--pasta", self.e.pasta, "--item", itens[0]["item"], "--decisao", "resolvido", "--data", dias(2))[0], 0)
        self._hoje(dias(3))
        self.assertEqual(len(self._item_urgente()), 1)

    def test_prazo_vencido_entra_uma_vez_e_resolvido_nao_volta(self):
        rodar("plano", "--pasta", self.e.pasta, "--conta", self.conta, "--tipo", "risco", "--data", REF)
        arquivo = self.e.pasta / "3-clientes" / self.conta / f"plano-risco-{REF}.md"
        arquivo.write_text(arquivo.read_text(encoding="utf-8").replace("| {{ }} | {{ }} | {{ }} | {{ }} |", f"| Ligar para a liderança | CS | {dias(1)} | voltar |"), encoding="utf-8")
        rodar("mesa", "--pasta", self.e.pasta, "--data", REF)
        self.assertEqual(rodar("decidir", "--pasta", self.e.pasta, "--item", "M-001", "--decisao", "aprovado", "--mesmo-assim", "--data", REF)[0], 0)
        self.assertNotIn("Passou do prazo", self._hoje(REF))
        saida = self._hoje(dias(3))
        self.assertIn("**Urgente: prazo vencido.**", saida)
        self.assertIn("Passou do prazo em", saida)
        self.assertIn("Ligar para a liderança", saida)
        aviso = next(i for i in itens_da_mesa(self.e.pasta) if i["o_que_e"].startswith("Passou do prazo"))
        self.assertEqual(rodar("decidir", "--pasta", self.e.pasta, "--item", aviso["item"], "--decisao", "resolvido", "--data", dias(3))[0], 0)
        self.assertNotIn("Passou do prazo", self._hoje(dias(4)))

    def test_aviso_nao_conta_como_acao_no_ciclo(self):
        from cslib.ciclo import calcular

        itens = [{"item": "M-1", "conta": self.conta, "o_que_e": "Rever o plano", "urgente": "x", "arquivo": "", "decisao": "aprovado", "decidido_em": REF, "acompanhar": ""}]
        self.assertEqual(calcular(self.e.pasta, itens, DATA_REF)["resultados"], [])

    def test_limite_por_vez_e_o_resto_entra_depois(self):
        from cslib import hoje as hoje_mod

        fatos = json.loads((self.e.pasta / "4-dados" / "rodadas" / REF / "contas.json").read_text(encoding="utf-8"))
        for conta in fatos.values():
            conta["sinais"] = [{"codigo": "cancelamento_agendado", "texto": "x"}]
        self.assertEqual(self.e.rodada(dias(1))[0], 0)
        (self.e.pasta / "4-dados" / "rodadas" / dias(1) / "contas.json").write_text(json.dumps(fatos, ensure_ascii=False), encoding="utf-8")
        anterior = self.e.pasta / "4-dados" / "rodadas" / REF / "contas.json"
        base = json.loads(anterior.read_text(encoding="utf-8"))
        for conta in base.values():
            conta["sinais"] = []
        anterior.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
        self.assertGreater(len(fatos), hoje_mod.LIMITE_DE_URGENTES)
        saida = self._hoje(dias(1))
        self.assertIn("de fora por hoje", saida)
        antes = len(itens_da_mesa(self.e.pasta))
        self.assertGreaterEqual(antes, hoje_mod.LIMITE_DE_URGENTES)
        self._hoje(dias(2))
        self.assertGreater(len(itens_da_mesa(self.e.pasta)), antes)


class TestAgendar(unittest.TestCase):
    def setUp(self):
        self.pasta = Path("C:/empresas/Clínica & Filhos") if os.name == "nt" else Path("/empresas/Clinica & Filhos")

    def test_nada_de_agendar_ou_decidir_no_agente_sem_a_pessoa(self):
        for comando in ("agendar", "decidir", "rotina"):
            self.assertNotIn(comando, guarda_privacidade.LIBERADOS)

    def test_a_pasta_de_chegada_esta_coberta_pela_trava(self):
        e = Empresa("completa")
        self.addCleanup(e.fechar)
        arquivo = e.pasta / "4-dados" / "entradas" / "novos" / "contas.csv"
        self.assertTrue(arquivo.parent.is_dir())
        self.assertTrue(guarda_privacidade.decidir({"tool_name": "Read", "tool_input": {"file_path": str(arquivo)}, "cwd": str(e.pasta)}))

    def test_xml_roda_quando_o_computador_ligar_e_sem_uso_de_ia(self):
        xml = rotina_mod.xml_da_tarefa(self.pasta, "08:00", "C:/py/pythonw.exe", Path("C:/skill/cs.py"), "PC\\pessoa", dt.date(2026, 11, 5))
        self.assertIn("<StartWhenAvailable>true</StartWhenAvailable>", xml)
        self.assertIn("<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>", xml)
        self.assertIn("<Monday />", xml)
        self.assertNotIn("<Saturday", xml)
        self.assertIn("2026-11-05T08:00:00", xml)
        self.assertIn(" rotina --pasta ", xml)
        self.assertIn("Clínica &amp; Filhos", xml)
        self.assertNotIn("claude", xml.split("<Actions")[1].casefold())

    def test_nome_da_tarefa_e_estavel_e_sem_acento(self):
        nome = rotina_mod.nome_da_tarefa(self.pasta)
        self.assertEqual(nome, rotina_mod.nome_da_tarefa(self.pasta))
        self.assertTrue(nome.isascii())
        self.assertNotIn(" ", nome)
        self.assertNotEqual(nome, rotina_mod.nome_da_tarefa(self.pasta.parent / "Outra"))

    def test_hora_invalida(self):
        for hora in ("8", "25:00", "08:60", "oito"):
            with self.assertRaises(Exception):
                rotina_mod.agendar(self.pasta, hora, Path("cs.py"), dt.date(2026, 11, 5))

    @unittest.skipUnless(os.name == "nt", "só no Windows")
    def test_agendar_chama_o_windows_e_mostra_o_erro(self):
        with mock.patch.object(rotina_mod, "_schtasks", return_value=(1, "sem permissão")) as chamada:
            with self.assertRaises(Exception) as erro:
                rotina_mod.agendar(self.pasta, "08:00", Path("cs.py"), dt.date(2026, 11, 5))
        self.assertIn("sem permissão", str(erro.exception))
        self.assertEqual(chamada.call_args[0][0], "/Create")

    def test_ver_sem_nada_agendado(self):
        e = Empresa("completa")
        self.addCleanup(e.fechar)
        with mock.patch.object(rotina_mod, "_schtasks", return_value=(1, "")):
            texto = rotina_mod.ver_agendamento(e.pasta)
        self.assertIn("ainda não rodou", texto)


if __name__ == "__main__":
    unittest.main()
