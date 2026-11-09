"""Mesa de aprovação, ciclo de resultado e página do dia: a pessoa decide, e o script só conta o que aconteceu depois."""

import csv
import datetime as dt
import shutil
import sys
import unittest
from pathlib import Path

from apoio import REF, Empresa, rodar, textos_para_ia
from gerar_bases import REF as DATA_REF

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import guarda_privacidade  # noqa: E402
from cslib import ciclo as ciclo_mod  # noqa: E402

NOME = "Clínica Fictícia Saudável 01"


def dias(n: int) -> str:
    return (DATA_REF + dt.timedelta(days=n)).isoformat()


def ajustar(e: Empresa, nome: str, **valores) -> None:
    caminho = e.entrada / "contas.csv"
    with caminho.open(encoding="utf-8", newline="") as f:
        linhas = list(csv.reader(f))
    cab = linhas[0]
    for linha in linhas[1:]:
        if linha[cab.index("Cliente")] == nome:
            for coluna, valor in valores.items():
                linha[cab.index(coluna.replace("_", " "))] = valor
    with caminho.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(linhas)


def itens_da_mesa(pasta: Path) -> list:
    from cslib.mesa import ler_itens

    return ler_itens(pasta)


class TestMesa(unittest.TestCase):
    def setUp(self):
        self.e = Empresa("completa")
        codigo, saida = self.e.rodada()
        assert codigo == 0, saida
        self.m = self.e.mapa()
        self.conta = self.m[NOME]

    def tearDown(self):
        self.e.fechar()

    def _plano(self, conta=None, data=REF):
        codigo, saida = rodar("plano", "--pasta", self.e.pasta, "--conta", conta or self.conta, "--tipo", "risco", "--data", data)
        self.assertEqual(codigo, 0, saida)
        return self.e.pasta / "3-clientes" / (conta or self.conta) / f"plano-risco-{data}.md"

    def _mesa(self, *extras):
        codigo, saida = rodar("mesa", "--pasta", self.e.pasta, "--data", REF, *extras)
        self.assertEqual(codigo, 0, saida)
        return saida

    def test_o_que_foi_preparado_entra_uma_vez_so(self):
        self._plano()
        rodar("reuniao", "--pasta", self.e.pasta, "--conta", self.conta, "--tipo", "revisao", "--data", REF)
        saida = self._mesa()
        self.assertIn("2 em aberto", saida)
        self.assertIn("Novos agora: 2", saida)
        self.assertIn("Plano para conta em risco", saida)
        self.assertIn("Reunião de revisão", saida)
        saida = self._mesa()
        self.assertIn("2 em aberto", saida)
        self.assertIn("Novos agora: 0", saida)
        self.assertEqual([i["item"] for i in itens_da_mesa(self.e.pasta)], ["M-001", "M-002"])

    def test_arquivo_antigo_nao_lota_a_mesa(self):
        self._plano(data=dias(-31))
        self.assertIn("0 em aberto", self._mesa())

    def test_aprovar_com_campo_em_branco_pede_confirmacao(self):
        self._plano()
        self._mesa()
        codigo, saida = rodar("decidir", "--pasta", self.e.pasta, "--item", "M-001", "--decisao", "aprovado", "--data", REF)
        self.assertEqual(codigo, 2, saida)
        self.assertIn("campos em branco", saida)
        self.assertEqual(itens_da_mesa(self.e.pasta)[0]["decisao"], "")
        codigo, saida = rodar("decidir", "--pasta", self.e.pasta, "--item", "M-001", "--decisao", "aprovado", "--mesmo-assim", "--data", REF)
        self.assertEqual(codigo, 0, saida)
        self.assertIn("quem age é a pessoa", saida)
        item = itens_da_mesa(self.e.pasta)[0]
        self.assertEqual((item["decisao"], item["decidido_em"]), ("aprovado", REF))

    def test_recusar_nao_pede_o_arquivo_completo_e_nao_decide_duas_vezes(self):
        self._plano()
        self._mesa()
        self.assertEqual(rodar("decidir", "--pasta", self.e.pasta, "--item", "m-001", "--decisao", "recusado", "--data", REF)[0], 0)
        codigo, saida = rodar("decidir", "--pasta", self.e.pasta, "--item", "M-001", "--decisao", "aprovado", "--mesmo-assim", "--data", REF)
        self.assertEqual(codigo, 2, saida)
        self.assertIn("já foi decidido", saida)
        self.assertEqual(rodar("decidir", "--pasta", self.e.pasta, "--item", "M-099", "--decisao", "recusado")[0], 2)

    def test_rotina_que_nao_existe_e_recusada(self):
        self._plano()
        self._mesa()
        codigo, saida = rodar("decidir", "--pasta", self.e.pasta, "--item", "M-001", "--decisao", "recusado", "--acompanhar", "Inventada")
        self.assertEqual(codigo, 2, saida)
        self.assertIn("Acompanhamento do plano", saida)

    def test_a_pessoa_decide_na_tabela_e_o_que_ela_escreveu_fica(self):
        self._plano()
        self._mesa()
        caminho = self.e.pasta / "mesa.md"
        texto = caminho.read_text(encoding="utf-8").replace("- Nada ainda.", "- 03/11: combinei com a liderança.")
        linha = next(l for l in texto.splitlines() if l.startswith("| M-001"))
        caminho.write_text(texto.replace(linha, linha.replace("|  |  |  |", "| sim |  |  |")), encoding="utf-8")
        self._mesa()
        texto = caminho.read_text(encoding="utf-8")
        self.assertIn("combinei com a liderança", texto)
        item = itens_da_mesa(self.e.pasta)[0]
        self.assertEqual((item["decisao"], item["decidido_em"]), ("aprovado", REF))

    def test_decisao_que_nao_se_entende_continua_em_aberto(self):
        self._plano()
        self._mesa()
        caminho = self.e.pasta / "mesa.md"
        texto = caminho.read_text(encoding="utf-8")
        linha = next(l for l in texto.splitlines() if l.startswith("| M-001"))
        caminho.write_text(texto.replace(linha, linha.replace("|  |  |  |", "| talvez |  |  |")), encoding="utf-8")
        saida = self._mesa()
        self.assertIn("1 em aberto", saida)
        self.assertIn("não é aprovado, recusado nem resolvido", saida)

    def test_sugestao_de_melhoria_passa_pela_mesa_e_a_resposta_volta(self):
        caminho = self.e.pasta / "5-melhoria" / "sugestoes.md"
        with caminho.open("a", encoding="utf-8") as f:
            f.write(f"| {REF} | Reduzir o prazo do onboarding | Quem saiu demorou mais |  |\n| {REF} | Mudar o plano | Outro motivo | não |\n")
        saida = self._mesa()
        self.assertIn("1 em aberto", saida)
        self.assertIn("1 recusados", saida)
        item = next(i for i in itens_da_mesa(self.e.pasta) if "onboarding" in i["o_que_e"])
        self.assertEqual(rodar("decidir", "--pasta", self.e.pasta, "--item", item["item"], "--decisao", "aprovado", "--data", REF)[0], 0)
        self.assertIn("| Reduzir o prazo do onboarding | Quem saiu demorou mais | sim |", caminho.read_text(encoding="utf-8"))

    def test_item_avulso(self):
        saida = self._mesa("--adicionar", "Rascunho da pesquisa com clientes novos")
        self.assertIn("Rascunho da pesquisa com clientes novos", saida)
        codigo, saida = rodar("mesa", "--pasta", self.e.pasta, "--arquivo", "4-dados/entradas/x.md", "--adicionar", "x")
        self.assertEqual(codigo, 2, saida)
        codigo, saida = rodar("mesa", "--pasta", self.e.pasta, "--conta", "CONTA-001")
        self.assertEqual(codigo, 2, saida)

    def test_decidir_nunca_fica_liberado_para_o_agente(self):
        self.assertNotIn("decidir", guarda_privacidade.LIBERADOS)

    def test_modo_protegido_nao_mostra_nome_e_a_copia_tem(self):
        self._plano()
        saida = self._mesa()
        self.assertNotIn("Fictíci", saida)
        for nome, texto in textos_para_ia(self.e.pasta).items():
            if nome == "mesa.md":
                self.assertNotIn("Fictíci", texto)
        self.assertIn(NOME, (self.e.pasta / "com-nomes" / "mesa.md").read_text(encoding="utf-8"))


class TestCiclo(unittest.TestCase):
    """A decisão é em REF. A rodada de antes é em REF, e as de depois vêm com a data de cada teste."""

    def setUp(self):
        self.e = Empresa("completa")
        ajustar(self.e, NOME, Planos_lançados_30d=4)
        assert self.e.rodada()[0] == 0
        self.conta = self.e.mapa()[NOME]
        assert rodar("plano", "--pasta", self.e.pasta, "--conta", self.conta, "--tipo", "risco", "--data", REF)[0] == 0
        assert rodar("mesa", "--pasta", self.e.pasta, "--data", REF)[0] == 0

    def tearDown(self):
        self.e.fechar()

    def _aprovar(self, *extras):
        codigo, saida = rodar("decidir", "--pasta", self.e.pasta, "--item", "M-001", "--decisao", "aprovado", "--mesmo-assim", "--data", REF, *extras)
        self.assertEqual(codigo, 0, saida)

    def _resultado(self, data):
        codigo, saida = rodar("resultado", "--pasta", self.e.pasta, "--data", data)
        self.assertEqual(codigo, 0, saida)
        return saida

    def test_sem_acao_aprovada_nao_ha_o_que_acompanhar(self):
        self.assertIn("Ainda não há ação aprovada", self._resultado(REF))

    def test_sem_rodada_depois_nao_inventa_resultado(self):
        self._aprovar("--acompanhar", "Acompanhamento do plano")
        saida = self._resultado(dias(5))
        self.assertIn("falta uma rodada depois da decisão", saida)
        self.assertNotIn("Melhorou depois", saida)

    def test_rotina_subiu_depois_de_uma_janela_inteira(self):
        self._aprovar("--acompanhar", "Acompanhamento do plano")
        ajustar(self.e, NOME, Planos_lançados_30d=9)
        self.assertEqual(self.e.rodada(dias(35))[0], 0)
        saida = self._resultado(dias(35))
        self.assertIn("Melhorou depois da ação", saida)
        self.assertIn("Acompanhamento do plano de 4 para 9", saida)
        self.assertIn("não prova que foi por causa dela", saida)

    def test_antes_da_janela_inteira_ainda_e_cedo(self):
        self._aprovar("--acompanhar", "Acompanhamento do plano")
        ajustar(self.e, NOME, Planos_lançados_30d=9)
        self.assertEqual(self.e.rodada(dias(7))[0], 0)
        saida = self._resultado(dias(7))
        self.assertIn("ainda é cedo", saida)
        self.assertNotIn("Melhorou depois da ação", saida)

    def test_rotina_que_caiu_pede_para_rever_e_vai_para_a_semana(self):
        self._aprovar("--acompanhar", "Acompanhamento do plano")
        ajustar(self.e, NOME, Planos_lançados_30d=2)
        self.assertEqual(self.e.rodada(dias(35))[0], 0)
        self.assertIn("Não melhorou: rever a causa", self._resultado(dias(35)))
        codigo, saida = rodar("semana", "--pasta", self.e.pasta, "--data", dias(35))
        self.assertEqual(codigo, 0, saida)
        fazer = saida.split("## O que fazer")[1].split("## O que foi conversado")[0]
        self.assertIn("Acompanhamento do plano de 4 para 2. Rever a causa", fazer)
        self.assertIn("## O que aconteceu depois das ações", saida)

    def test_chamado_subir_e_ruim(self):
        self.assertEqual(ciclo_mod._direcao_do_movimento(2, 5, "ruim"), "piorou")
        self.assertEqual(ciclo_mod._direcao_do_movimento(5, 2, "ruim"), "melhorou")
        self.assertEqual(ciclo_mod._direcao_do_movimento(5, 5, "ruim"), "igual")

    def test_conta_que_saiu_nao_vira_numero(self):
        self._aprovar()
        pasta_rodada = self.e.pasta / "4-dados" / "rodadas" / dias(35)
        pasta_rodada.mkdir(parents=True)
        origem = self.e.pasta / "4-dados" / "rodadas" / REF
        shutil.copy2(origem / "resumo.json", pasta_rodada / "resumo.json")
        with (origem / "valores.csv").open(encoding="utf-8-sig", newline="") as f:
            linhas = list(csv.DictReader(f, delimiter=";"))
        for linha in linhas:
            if linha["codigo"] == self.conta:
                linha["status"] = "cancelada"
        with (pasta_rodada / "valores.csv").open("w", encoding="utf-8-sig", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=list(linhas[0]), delimiter=";")
            escritor.writeheader()
            escritor.writerows(linhas)
        saida = self._resultado(dias(35))
        self.assertIn("Saiu mesmo com a ação", saida)
        self.assertIn("a conta saiu", saida)

    def test_nota_de_formulas_diferentes_nao_se_compara(self):
        self._aprovar()
        ajustar(self.e, NOME, Planos_lançados_30d=9)
        self.assertEqual(self.e.rodada(dias(35))[0], 0)
        resumo = self.e.pasta / "4-dados" / "rodadas" / dias(35) / "resumo.json"
        import json

        dados = json.loads(resumo.read_text(encoding="utf-8"))
        dados["formula"]["versao"] = "outra"
        resumo.write_text(json.dumps(dados), encoding="utf-8")
        saida = self._resultado(dias(35))
        self.assertIn("sem número para comparar", saida)
        self.assertNotIn("Nota de", saida)

    def test_com_poucos_casos_nao_compara_com_quem_nao_teve_acao(self):
        self._aprovar()
        ajustar(self.e, NOME, Planos_lançados_30d=9)
        self.assertEqual(self.e.rodada(dias(35))[0], 0)
        self.assertIn("poucos casos", self._resultado(dias(35)))


class TestComparacaoSemAcao(unittest.TestCase):
    """Conta em baixa costuma subir de qualquer jeito. Contas à mão: 5 com plano (4 subiram) e 5 sem plano (3 subiram)."""

    def test_mostra_as_contas_da_mesma_faixa_sem_a_acao(self):
        e = Empresa("completa")
        self.addCleanup(e.fechar)
        self.assertEqual(e.rodada()[0], 0)
        cab = ["codigo", "status", "nota", "faixa"]

        def gravar(data, notas):
            pasta = e.pasta / "4-dados" / "rodadas" / data
            pasta.mkdir(parents=True, exist_ok=True)
            with (pasta / "valores.csv").open("w", encoding="utf-8-sig", newline="") as f:
                escritor = csv.writer(f, delimiter=";")
                escritor.writerow(cab)
                for codigo, nota, faixa in notas:
                    escritor.writerow([codigo, "ativa", nota, faixa])
            shutil.copy2(e.pasta / "4-dados" / "rodadas" / REF / "resumo.json", pasta / "resumo.json")

        antes = [(f"CONTA-{i:03d}", 40, "possivel_churn") for i in range(901, 911)] + [("CONTA-950", 90, "saudavel")]
        depois = [(f"CONTA-{i:03d}", n, "pode_melhorar") for i, n in zip(range(901, 911), (50, 50, 50, 50, 40, 50, 50, 50, 40, 30))] + [("CONTA-950", 99, "saudavel")]
        gravar(dias(1), antes)
        gravar(dias(40), depois)
        itens = [{"item": f"M-{i}", "conta": f"CONTA-{i}", "o_que_e": "Plano para conta em risco", "arquivo": "", "decisao": "aprovado", "decidido_em": dias(2), "acompanhar": ""} for i in range(901, 906)]
        ciclo = ciclo_mod.calcular(e.pasta, itens, dt.date.fromisoformat(dias(40)))
        linha = ciclo["por_tipo"][0]
        self.assertEqual((linha["melhorou"], linha["igual"], linha["total"]), (4, 1, 5))
        self.assertEqual(linha["comparacao"], {"com_acao_contas": 5, "com_acao_subiram": 4, "contas": 5, "subiram": 3})
        self.assertIn("em 4 de 5 com a ação, e em 3 de 5 da mesma faixa sem ela", ciclo_mod.frase_por_tipo(linha))


class TestHoje(unittest.TestCase):
    def setUp(self):
        self.e = Empresa("completa")
        self.assertEqual(self.e.rodada()[0], 0)
        self.m = self.e.mapa()
        self.conta = self.m[NOME]

    def tearDown(self):
        self.e.fechar()

    def _hoje(self, data=REF):
        codigo, saida = rodar("hoje", "--pasta", self.e.pasta, "--data", data)
        self.assertEqual(codigo, 0, saida)
        return saida

    def test_tres_blocos_e_nao_finge_que_esta_tudo_bem(self):
        saida = self._hoje()
        for titulo in ("## O que melhorou", "## O que está marcado", "## O que espera você"):
            self.assertIn(titulo, saida)
        self.assertIn("Ainda não há ação aprovada para acompanhar", saida)
        self.assertIn("Nada espera a sua decisão", saida)
        self.assertTrue((self.e.pasta / "hoje.md").exists())

    def test_cabe_em_uma_pagina(self):
        for conta in list(self.m.values())[:9]:
            rodar("plano", "--pasta", self.e.pasta, "--conta", conta, "--tipo", "risco", "--data", REF)
        saida = self._hoje()
        self.assertIn("veja mesa.md", saida)
        pagina = (self.e.pasta / "hoje.md").read_text(encoding="utf-8")
        self.assertLess(len(pagina.splitlines()), 45)

    def test_modo_protegido_so_codigos_e_a_copia_tem_os_nomes(self):
        rodar("plano", "--pasta", self.e.pasta, "--conta", self.conta, "--tipo", "risco", "--data", REF)
        saida = self._hoje()
        self.assertNotIn("Fictíci", saida)
        self.assertNotIn("Fictíci", (self.e.pasta / "hoje.md").read_text(encoding="utf-8"))
        self.assertIn(NOME, (self.e.pasta / "com-nomes" / "hoje.md").read_text(encoding="utf-8"))

    def test_rodada_antiga_avisa(self):
        self.assertIn("Esta rodada tem 20 dias", self._hoje(dias(20)))

    def test_renovacao_aparece_marcada(self):
        self.assertIn("renova, R$", self._hoje())

    def test_sinal_bom_mostra_de_quanto_para_quanto(self):
        """Chamado caindo também é sinal bom. Dizer só que 'subiu' seria falso."""
        grande = self.m["Hospital Fictício Grande Conta"]
        self.assertEqual(self.e.rodada(dias(35))[0], 0)
        resumo = self.e.resumo(dias(35))
        chamados = next(b for b in resumo["sinais_bons"] if b["conta"] == grande and b["rotina"] == "Chamados")
        self.assertLess(chamados["agora"], chamados["antes"])
        saida = self._hoje(dias(35))
        self.assertNotIn("Subiu", saida)
        self.assertRegex(saida, r"Nesta rodada: CONTA-\d+, [^\n]+ de \d+ para \d+")

    def test_acao_de_plano_aprovado_entra_com_a_data(self):
        arquivo = self.e.pasta / "3-clientes" / self.conta / f"plano-risco-{REF}.md"
        rodar("plano", "--pasta", self.e.pasta, "--conta", self.conta, "--tipo", "risco", "--data", REF)
        texto = arquivo.read_text(encoding="utf-8").replace("| {{ }} | {{ }} | {{ }} | {{ }} |", f"| Ligar para a liderança | CS | {dias(1)} | voltar a lançar |\n| Rever o estoque | CS | {dias(-3)} | saída no sistema |")
        arquivo.write_text(texto, encoding="utf-8")
        rodar("mesa", "--pasta", self.e.pasta, "--data", REF)
        self.assertEqual(rodar("decidir", "--pasta", self.e.pasta, "--item", "M-001", "--decisao", "aprovado", "--mesmo-assim", "--data", REF)[0], 0)
        saida = self._hoje()
        self.assertIn(f"{(DATA_REF + dt.timedelta(days=1)).strftime('%d/%m')}: {self.conta}: Ligar para a liderança", saida)
        self.assertIn(f"{self.conta} · Passou do prazo em {(DATA_REF - dt.timedelta(days=3)).strftime('%d/%m')}: Rever o estoque", saida)

    def test_acao_de_plano_sem_decisao_nao_entra(self):
        arquivo = self.e.pasta / "3-clientes" / self.conta / f"plano-risco-{REF}.md"
        rodar("plano", "--pasta", self.e.pasta, "--conta", self.conta, "--tipo", "risco", "--data", REF)
        arquivo.write_text(arquivo.read_text(encoding="utf-8").replace("| {{ }} | {{ }} | {{ }} | {{ }} |", f"| Ligar para a liderança | CS | {dias(1)} | voltar |"), encoding="utf-8")
        self.assertNotIn("Ligar para a liderança", self._hoje())

    def test_sem_rodada_pede_o_analista(self):
        vazia = Empresa("completa")
        self.addCleanup(vazia.fechar)
        codigo, saida = rodar("hoje", "--pasta", vazia.pasta)
        self.assertEqual(codigo, 2, saida)
        self.assertIn("Analista", saida)

    def test_modo_aberto_mostra_os_nomes(self):
        e = Empresa("completa", modo="aberto")
        self.addCleanup(e.fechar)
        self.assertEqual(e.rodada()[0], 0)
        conta = e.mapa()[NOME]
        rodar("plano", "--pasta", e.pasta, "--conta", conta, "--tipo", "risco", "--data", REF)
        codigo, saida = rodar("hoje", "--pasta", e.pasta, "--data", REF)
        self.assertEqual(codigo, 0, saida)
        self.assertIn(f"{conta} · {NOME}", saida)


class TestPreparar(unittest.TestCase):
    def setUp(self):
        self.e = Empresa("completa")
        self.assertEqual(self.e.rodada()[0], 0)

    def tearDown(self):
        self.e.fechar()

    def _preparar(self, *extras, data=REF):
        codigo, saida = rodar("preparar", "--pasta", self.e.pasta, "--data", data, *extras)
        self.assertEqual(codigo, 0, saida)
        return saida

    def test_respeita_o_limite_e_nao_repete(self):
        primeira = self._preparar("--limite", "2")
        self.assertIn("Preparei 2 arquivos", primeira)
        self.assertNotIn("Fictíci", primeira)
        planos = list((self.e.pasta / "3-clientes").glob("CONTA-*/plano-risco-*.md"))
        self.assertEqual(len(planos), 2)
        segunda = self._preparar("--limite", "2")
        for linha in primeira.splitlines()[1:]:
            self.assertNotIn(linha, segunda)
        self.assertEqual(rodar("mesa", "--pasta", self.e.pasta, "--data", REF)[0], 0)
        self.assertEqual(len(itens_da_mesa(self.e.pasta)), 4)

    def test_nao_escreve_a_causa(self):
        self._preparar("--limite", "1")
        plano = next((self.e.pasta / "3-clientes").glob("CONTA-*/plano-risco-*.md"))
        self.assertIn("{{a causa específica", plano.read_text(encoding="utf-8"))

    def test_quando_nao_ha_o_que_preparar(self):
        self._preparar("--limite", "50")
        self.assertIn("Nada novo para preparar", self._preparar("--limite", "50"))

    def test_limite_invalido(self):
        self.assertEqual(rodar("preparar", "--pasta", self.e.pasta, "--limite", "0")[0], 2)


class TestSemanaSemMesa(unittest.TestCase):
    def test_sem_mesa_a_semana_nao_muda(self):
        e = Empresa("completa")
        self.addCleanup(e.fechar)
        self.assertEqual(e.rodada()[0], 0)
        codigo, saida = rodar("semana", "--pasta", e.pasta, "--data", REF)
        self.assertEqual(codigo, 0, saida)
        self.assertNotIn("Mesa de aprovação", saida)
        self.assertNotIn("depois das ações", saida)
        self.assertFalse((e.pasta / "mesa.md").exists())


if __name__ == "__main__":
    unittest.main()
