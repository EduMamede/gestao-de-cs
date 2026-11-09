"""As 5 bases fictícias, de ponta a ponta, com respostas calculadas à mão em gerar_bases.py."""

import datetime as dt
import json
import shutil
import unittest
from pathlib import Path

import openpyxl

from apoio import REF, Empresa, rodar
from mini_excel import Avaliador


def por_conta(lista, codigo):
    return next((x for x in lista if x["conta"] == codigo), None)


class TestCompleta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Empresa("completa")
        cls.codigo, cls.saida = cls.e.rodada()
        cls.r = cls.e.resumo()
        cls.m = cls.e.mapa()

    @classmethod
    def tearDownClass(cls):
        cls.e.fechar()

    def test_rodou(self):
        self.assertEqual(self.codigo, 0, self.saida)

    def test_contas_e_faixas(self):
        self.assertEqual(self.r["contas"]["ativas"], 40)
        f = self.r["faixas"]
        self.assertEqual((f["saudavel"]["contas"], f["pode_melhorar"]["contas"], f["possivel_churn"]["contas"], f["sem_nota"]["contas"]), (32, 3, 3, 2))

    def test_receita(self):
        m = {x["id"]: x["valor"] for x in self.r["painel"]["metricas"]}
        self.assertEqual(m["receita_ativa"], 94100)
        self.assertEqual(m["receita_em_risco"], 48000 + 800 + 800)

    def test_nota_conferida_a_mao(self):
        grande = por_conta(self.r["prioridades"], self.m["Hospital Fictício Grande Conta"])
        self.assertEqual(grande["nota"], 10)
        morna = por_conta(self.r["prioridades"], self.m["Clínica Fictícia Morna 1"])
        self.assertEqual(morna["nota"], 46)
        critica = por_conta(self.r["prioridades"], self.m["Clínica Fictícia Crítica 1"])
        self.assertEqual(critica["nota"], 8)

    def test_grande_conta_perto_de_renovar_vem_primeiro(self):
        primeiro = self.r["prioridades"][0]
        self.assertEqual(primeiro["conta"], self.m["Hospital Fictício Grande Conta"])
        self.assertIn("Renova em 45 dias", primeiro["por_que"])
        self.assertEqual(primeiro["matriz"], "salvar")

    def test_conta_verde_parada_aparece_mesmo_com_nota_boa(self):
        parada = por_conta(self.r["empacadas"], self.m["Clínica Fictícia Verde Parada"])
        self.assertEqual(parada["nota"], 100)
        self.assertEqual(parada["dias_na_etapa"], 45)
        self.assertEqual(parada["prazo"], 20)
        self.assertEqual(parada["motivo"], "do cliente")
        self.assertIn("cliente", parada["quem_age"])
        tres = [p["conta"] for p in self.r["prioridades"][:3]]
        self.assertIn(self.m["Clínica Fictícia Verde Parada"], tres)

    def test_motivo_separa_cliente_de_nos(self):
        motivos = {e["conta"]: e["motivo"] for e in self.r["empacadas"]}
        self.assertEqual(len(motivos), 3)
        self.assertEqual(motivos[self.m["Clínica Fictícia Parada Por Nós"]], "nosso")
        self.assertEqual(motivos[self.m["Clínica Fictícia Parada Sem Motivo"]], "não informado")

    def test_queda_de_padrao_com_nota_boa(self):
        alertas = self.r["alertas_de_padrao"]
        self.assertEqual(len(alertas), 1)
        a = alertas[0]
        self.assertEqual(a["conta"], self.m["Clínica Fictícia Queda de Padrão"])
        self.assertEqual((a["antes"], a["agora"], a["variacao_pct"], a["nota"]), (40, 12, -70, 100))
        tres = [p["conta"] for p in self.r["prioridades"][:3]]
        self.assertIn(a["conta"], tres)

    def test_sinal_bom_nao_entra_como_risco(self):
        bons = self.r["sinais_bons"]
        self.assertEqual([b["conta"] for b in bons], [self.m["Clínica Fictícia Cresceu"]])
        self.assertIsNone(por_conta(self.r["prioridades"], self.m["Clínica Fictícia Cresceu"]))

    def test_confianca(self):
        c = self.r["contas"]["confianca"]
        self.assertEqual(c["média"], 2)
        self.assertEqual(c["alta"], 36)
        self.assertEqual(c["baixa"], 0)
        self.assertEqual(self.r["contas"]["sem_nota"], 2)

    def test_renovacoes(self):
        self.assertEqual(sorted(x["dias"] for x in self.r["renovacoes"]), [45, 60])
        comb = {x["conta"]: x["com_risco"] for x in self.r["renovacoes"]}
        self.assertTrue(comb[self.m["Hospital Fictício Grande Conta"]])
        self.assertFalse(comb[self.m["Clínica Fictícia Renova Bem"]])

    def test_metas(self):
        metas = {m["indicador"]: m for m in self.r["metas"]}
        self.assertEqual(metas["pct_saudaveis"]["atual"], 84.2)
        self.assertEqual(metas["pct_saudaveis"]["situacao"], "atrás")
        self.assertEqual(metas["contas_empacadas"]["atual"], 3)
        self.assertEqual(metas["contas_empacadas"]["situacao"], "atrás")
        self.assertEqual(metas["nps"]["atual"], 67)  # (27 - 3) / 36
        self.assertEqual(metas["nps"]["situacao"], "no alvo")
        # o export não traz canceladas: dizer "churn 0%, no alvo" seria inventar
        self.assertIsNone(metas["churn_contas_30d"]["atual"])
        self.assertEqual(metas["churn_contas_30d"]["situacao"], "sem dado")
        self.assertIn("O export não traz nenhuma conta cancelada", [f["o_que_falta"] for f in self.r["falta_medir"]])

    def test_responsavel_vem_em_codigo(self):
        grande = por_conta(self.r["prioridades"], self.m["Hospital Fictício Grande Conta"])
        self.assertRegex(grande["responsavel"], r"^CSM-\d{2}$")
        parada = por_conta(self.r["empacadas"], self.m["Clínica Fictícia Verde Parada"])
        self.assertRegex(parada["responsavel"], r"^CSM-\d{2}$")

    def test_painel_por_time(self):
        grupos = self.r["painel"]["por_responsavel"]
        self.assertEqual({g["grupo"] for g in grupos}, {"CSM-01", "CSM-02"})
        self.assertEqual(sum(g["contas"] for g in grupos), 40)

    def test_contas_chave(self):
        chave = self.r["contas_chave"]
        # 48.000 + 5.000 + 3.000 + 2.000 + 1.500 + 16 contas de 1.000 = 75.500, passa dos 80% de 94.100
        self.assertFalse(chave["existe"])
        self.assertEqual(chave["quantas"], 21)
        self.assertEqual(chave["pct_receita"], 80)
        self.assertNotIn("contas", chave)  # sem grupo pequeno, não há lista de contas-chave
        self.assertEqual(self.r["maiores_contas"][0]["conta"], self.m["Hospital Fictício Grande Conta"])

    def test_painel_nao_diz_nada_urgente_com_conta_em_risco(self):
        painel = (self.e.pasta / "4-dados" / "rodadas" / REF / "painel-geral.md").read_text(encoding="utf-8")
        self.assertNotIn("Nada urgente", painel)
        self.assertIn("contas para olhar", painel)

    def test_todo_md_abre_com_as_duas_partes(self):
        for caminho in self.e.pasta.rglob("*.md"):
            texto = caminho.read_text(encoding="utf-8")
            fazer, conversado = texto.find("## O que fazer"), texto.find("## O que foi conversado")
            self.assertGreaterEqual(fazer, 0, caminho)
            self.assertGreater(conversado, fazer, caminho)
            # as duas partes vêm antes de qualquer outra seção
            outras = [l for l in texto[: fazer].splitlines() if l.startswith("## ")]
            self.assertEqual(outras, [], caminho)

    def test_semana(self):
        codigo, saida = rodar("semana", "--pasta", self.e.pasta, "--data", REF)
        self.assertEqual(codigo, 0, saida)
        # 03/11/2026 é terça: a semana é a da segunda 02/11
        arquivo = self.e.pasta / "2-metas" / "semana-2026-11-02.md"
        self.assertTrue(arquivo.exists())
        texto = arquivo.read_text(encoding="utf-8")
        self.assertIn(self.m["Hospital Fictício Grande Conta"], texto.split("## O que foi conversado")[0])
        self.assertIn("85% das contas saudáveis", texto)
        self.assertIn("Parado por nós", texto)
        self.assertIn("Pendência do cliente", texto)
        self.assertNotIn("Clínica Fictícia", texto)
        self.assertIn("Hoje é terça", texto)
        self.assertIn("Renova em 45 dias", texto.split("## O que foi conversado")[0])  # o motivo inteiro, não só o primeiro
        self.assertIn("responsável", texto.split("## O que está atrás")[0])
        self.assertIn("No alvo: NPS 50", texto)
        # não sobrescreve o que já foi escrito
        arquivo.write_text(texto + "\nANOTADO PELA PESSOA\n", encoding="utf-8")
        rodar("semana", "--pasta", self.e.pasta, "--data", REF)
        self.assertIn("ANOTADO PELA PESSOA", arquivo.read_text(encoding="utf-8"))
        # a versão com nomes
        codigo, saida = rodar("restaurar-nomes", "--pasta", self.e.pasta, "--arquivo", "2-metas/semana-2026-11-02.md")
        self.assertEqual(codigo, 0, saida)
        com_nomes = (self.e.pasta / "com-nomes" / "semana-2026-11-02.md").read_text(encoding="utf-8")
        self.assertIn("Hospital Fictício Grande Conta", com_nomes)

    def test_conferir_numeros(self):
        rodar("semana", "--pasta", self.e.pasta, "--data", REF)
        arquivo = self.e.pasta / "2-metas" / "semana-2026-11-02.md"
        copia = self.e.pasta / "2-metas" / "conferir.md"
        copia.write_text(arquivo.read_text(encoding="utf-8"), encoding="utf-8")
        codigo, saida = rodar("conferir-numeros", "--pasta", self.e.pasta, "--arquivo", "2-metas/conferir.md")
        self.assertEqual(codigo, 0, saida)
        copia.write_text(copia.read_text(encoding="utf-8") + "\nA receita em risco é R$ 77.777, o churn é de 13,7%, parada há 777 dias, 7777 contas e nota 777.\n", encoding="utf-8")
        codigo, saida = rodar("conferir-numeros", "--pasta", self.e.pasta, "--arquivo", "2-metas/conferir.md")
        self.assertEqual(codigo, 1)
        for inventado in ("R$ 77.777", "13,7%", "777 dias", "7777 contas", "nota 777"):
            self.assertIn(inventado, saida)
        copia.unlink()


class TestPlanilha(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Empresa("completa")
        cls.e.rodada()
        caminho = cls.e.pasta / "4-dados" / "rodadas" / REF / "health-score.xlsx"
        cls.formulas = openpyxl.load_workbook(caminho)
        cls.valores = openpyxl.load_workbook(caminho, data_only=True)

    @classmethod
    def tearDownClass(cls):
        cls.formulas.close()
        cls.valores.close()
        cls.e.fechar()

    def test_abas(self):
        for aba in ("Como usar", "Painel geral", "Quem olhar primeiro", "Health score", "O que empaca", "Alertas de padrão", "O que falta medir", "Medições"):
            self.assertIn(aba, self.formulas.sheetnames)
        self.assertEqual(self.formulas.active.title, "Painel geral")

    def _celulas_com_formula(self):
        for aba in self.formulas.worksheets:
            for linha in aba.iter_rows():
                for celula in linha:
                    if isinstance(celula.value, str) and celula.value.startswith("="):
                        yield aba.title, celula.coordinate, celula.value

    def test_toda_formula_tem_o_valor_gravado_e_o_valor_bate(self):
        av = Avaliador(self.formulas)
        total = 0
        for aba, ref, _ in self._celulas_com_formula():
            total += 1
            gravado = self.valores[aba][ref].value
            calculado = av.celula(aba, ref)
            if gravado in (None, ""):
                self.assertIn(calculado, (None, ""), f"{aba}!{ref}")
            elif isinstance(gravado, (int, float)):
                self.assertAlmostEqual(float(calculado), float(gravado), places=6, msg=f"{aba}!{ref}")
            else:
                self.assertEqual(calculado, gravado, f"{aba}!{ref}")
        self.assertGreater(total, 200)

    def test_cabecalho_das_colunas_do_que_empaca(self):
        aba = self.valores["Health score"]
        cabecalho = [c.value for c in aba[5]]
        for coluna in ("Última verificação", "Aviso", "ID", "Cliente", "Nota", "Faixa", "Confiança", "Segmento", "Valor", "Renovação", "Etapa atual", "Dias na etapa", "Prazo da etapa", "Situação", "Motivo", "Próximo passo", "Data do próximo contato"):
            self.assertIn(coluna, cabecalho)

    def test_pesos_editaveis_mudam_a_nota(self):
        aba = self.formulas["Health score"]
        cabecalho = [c.value for c in aba[5]]
        col_nota = cabecalho.index("Nota") + 1
        col_plano = cabecalho.index("Acompanhamento do plano") + 1
        col_estoque = cabecalho.index("Estoque") + 1
        linha = next(l for l in range(6, 46) if aba.cell(l, cabecalho.index("Cliente") + 1).value == "Hospital Fictício Grande Conta")
        # só o plano valendo: a nota vira a subnota do plano (25)
        trocas = {}
        for c in range(col_plano, col_plano + 5):
            trocas[("Health score", f"{aba.cell(4, c).column_letter}4")] = 1.0 if c == col_plano else 0.0
        av = Avaliador(self.formulas, trocas=trocas)
        self.assertEqual(av.celula("Health score", aba.cell(linha, col_nota).coordinate), 25)
        # só o estoque: 0
        trocas = {("Health score", f"{aba.cell(4, c).column_letter}4"): (1.0 if c == col_estoque else 0.0) for c in range(col_plano, col_plano + 5)}
        av = Avaliador(self.formulas, trocas=trocas)
        self.assertEqual(av.celula("Health score", aba.cell(linha, col_nota).coordinate), 0)

    def test_nomes_reais_so_na_planilha(self):
        nomes = [c.value for c in self.valores["Health score"]["D"]]
        self.assertIn("Clínica Fictícia Verde Parada", nomes)

    def test_campo_sem_dado_fica_para_preencher(self):
        aba = self.valores["Health score"]
        cabecalho = [c.value for c in aba[5]]
        linha = next(l for l in range(6, 46) if aba.cell(l, cabecalho.index("Cliente") + 1).value == "Clínica Fictícia Sem Dados 1")
        self.assertEqual(aba.cell(linha, cabecalho.index("Faixa") + 1).value, "sem nota")
        self.assertIsNone(aba.cell(linha, cabecalho.index("Nota") + 1).value)
        self.assertIsNone(aba.cell(linha, cabecalho.index("Estoque") + 1).value)


class TestBaguncada(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Empresa("baguncada")
        cls.codigo, cls.saida = cls.e.rodada()
        cls.r = cls.e.resumo()
        cls.m = cls.e.mapa()

    @classmethod
    def tearDownClass(cls):
        cls.e.fechar()

    def test_rodou(self):
        self.assertEqual(self.codigo, 0, self.saida)

    def test_doze_contas_sem_total_nem_duplicata(self):
        self.assertEqual(self.r["contas"]["ativas"], 12)

    def test_receita_com_duplicata_resolvida(self):
        # 1234,56 + 2000 + 1000 + 1100 + 750 + 3500,50 + 10000 + 1500 + 500 + 2500,75 + 1000 + vazio
        m = {x["id"]: x["valor"] for x in self.r["painel"]["metricas"]}
        self.assertAlmostEqual(m["receita_ativa"], 25085.81, places=2)

    def test_avisos(self):
        avisos = " ".join(self.r["avisos_sobre_os_dados"])
        self.assertIn("1 linha de total", avisos)
        self.assertIn("1 linha repetida", avisos)
        self.assertIn("1 conta repetida com dados diferentes", avisos)
        self.assertIn("não deu para ler", avisos)

    def test_junta_arquivos_pelo_nome_mesmo_escrito_diferente(self):
        # Todas têm uso (peso 3) e pagamento (peso 3): cobertura de 100%
        self.assertEqual(self.r["contas"]["confianca"]["alta"], 12)
        self.assertEqual(self.r["contas"]["sem_nota"], 0)

    def test_data_de_fase_e_etapa_sem_acento(self):
        alfa = por_conta(self.r["empacadas"], self.m["Clínica Fictícia Alfa"])
        self.assertIsNotNone(alfa)
        self.assertEqual(alfa["etapa"], "Implantação")
        self.assertEqual(alfa["dias_na_etapa"], 63)  # 01/09 a 03/11

    def test_pagamento_atrasado_derruba_a_nota(self):
        # Alfa: uso 12 de 10 (100) e atrasado (0): (3*100 + 3*0) / 6 = 50
        self.assertEqual(por_conta(self.r["prioridades"], self.m["Clínica Fictícia Alfa"])["nota"], 50)

    def test_renovacao_em_serial_do_excel_e_data_de_hoje(self):
        # Gama renova em 3/11/26, a própria data de referência
        self.assertIn(0, [x["dias"] for x in self.r["renovacoes"]])
        gama = por_conta(self.r["prioridades"], self.m["Clínica Fictícia Gama"])
        self.assertIn("Renova hoje", gama["por_que"])

    def test_aviso_diz_a_conta_e_a_coluna(self):
        avisos = " ".join(self.r["avisos_sobre_os_dados"])
        self.assertIn(self.m["Clínica Fictícia Delta"], avisos)
        self.assertIn("Data da fase: 1", avisos)

    def test_renovacao_sozinha_nao_e_o_mais_crucial(self):
        rodar("semana", "--pasta", self.e.pasta, "--data", REF)
        texto = (self.e.pasta / "2-metas" / "semana-2026-11-02.md").read_text(encoding="utf-8")
        crucial = texto.split("## O mais crucial da semana")[1].split("## O que está atrás")[0]
        tabela = crucial.split("Renovam na janela")[0]
        self.assertIn(self.m["Clínica Fictícia Alfa"], tabela)
        self.assertNotIn(self.m["Clínica Fictícia Gama"], tabela)
        self.assertIn(self.m["Clínica Fictícia Gama"], crucial.split("Renovam na janela")[1])

    def test_financeiro_nao_vira_frase_confusa(self):
        alfa = por_conta(self.r["prioridades"], self.m["Clínica Fictícia Alfa"])
        self.assertIn("Financeiro com problema: Pagamento com nota 0", alfa["por_que"])

    def test_nome_com_acento_chega_certo_na_planilha(self):
        livro = openpyxl.load_workbook(self.e.pasta / "4-dados" / "rodadas" / REF / "health-score.xlsx", data_only=True)
        nomes = [c.value for c in livro["Health score"]["D"]]
        self.assertIn("Clínica Fictícia Épsilon", nomes)
        valores = {livro["Health score"].cell(l, 4).value: livro["Health score"].cell(l, 11).value for l in range(6, 18)}
        self.assertAlmostEqual(valores["Clínica Fictícia Alfa"], 1234.56)
        self.assertEqual(valores["Clínica Fictícia Delta"], 1100)
        self.assertEqual(valores["Clínica Fictícia Lambda"], 1000)
        self.assertEqual(valores["Clínica Fictícia Mi"], "a preencher")
        livro.close()

    def test_arquivo_de_duplicatas_e_privado(self):
        self.assertTrue((self.e.pasta / "4-dados" / ".privado" / "duplicatas.csv").exists())


class TestMinima(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Empresa("minima")
        cls.codigo, cls.saida = cls.e.rodada()
        cls.r = cls.e.resumo()
        cls.m = cls.e.mapa()

    @classmethod
    def tearDownClass(cls):
        cls.e.fechar()

    def test_rodou(self):
        self.assertEqual(self.codigo, 0, self.saida)

    def test_nao_finge_nota(self):
        self.assertEqual(self.r["contas"]["com_nota"], 0)
        self.assertEqual(self.r["contas"]["sem_nota"], 10)
        self.assertEqual(self.r["faixas"]["sem_nota"]["contas"], 10)
        self.assertEqual(self.r["prioridades"], [])
        valores = {x["id"]: x["valor"] for x in self.r["painel"]["metricas"]}
        for metrica in ("nota_media", "pct_saudaveis", "contas_empacadas", "churn_contas_30d", "nps", "renovacoes_90d"):
            self.assertIsNone(valores[metrica], metrica)

    def test_mostra_o_que_da_para_ver(self):
        valores = {x["id"]: x["valor"] for x in self.r["painel"]["metricas"]}
        self.assertEqual(valores["receita_ativa"], 91000)
        chave = self.r["contas_chave"]
        self.assertTrue(chave["existe"])
        self.assertEqual(chave["quantas"], 2)  # 75.000 de 91.000 = 82%
        self.assertEqual(chave["pct_receita"], 82)

    def test_aponta_o_que_falta(self):
        faltas = [f["o_que_falta"] for f in self.r["falta_medir"]]
        texto = " ".join(faltas)
        for item in ("Uso do sistema", "Data de cancelamento", "Data de renovação", "Etapa atual", "patrocinador"):
            self.assertIn(item, texto)
        self.assertEqual(self.r["falta_medir"][0]["prioridade"], "alta")
        self.assertTrue(all(f["primeiro_passo"] for f in self.r["falta_medir"]))

    def test_meta_sem_dado_nao_vira_numero(self):
        meta = self.r["metas"][0]
        self.assertIsNone(meta["atual"])
        self.assertEqual(meta["situacao"], "sem dado")

    def test_planilha_nao_tem_nota_inventada(self):
        livro = openpyxl.load_workbook(self.e.pasta / "4-dados" / "rodadas" / REF / "health-score.xlsx", data_only=True)
        aba = livro["Health score"]
        for l in range(6, 16):
            self.assertIsNone(aba.cell(l, 5).value)
            self.assertEqual(aba.cell(l, 6).value, "sem nota")
        painel = [c.value for linha in livro["Painel geral"].iter_rows() for c in linha]
        self.assertIn("a preencher", painel)
        livro.close()

    def test_semana_vira_medir_o_que_falta(self):
        codigo, saida = rodar("semana", "--pasta", self.e.pasta, "--data", REF)
        self.assertEqual(codigo, 0, saida)
        texto = (self.e.pasta / "2-metas" / "semana-2026-11-02.md").read_text(encoding="utf-8")
        self.assertIn("comece a medir", texto)
        self.assertIn("Ainda não dá para saber", texto)
        self.assertIn("maiores contas (por receita, não por risco)", texto)
        self.assertIn(self.m["Empresa Fictícia Grande Um"], texto.split("## O que está atrás")[0])
        # sem dado não é boa notícia
        self.assertNotIn("Nenhuma renovação com risco", texto)
        self.assertNotIn("Nenhuma pendência do cliente", texto)
        self.assertNotIn("Nenhuma conta com sinal", texto)

    def test_alertas_nao_confunde_sem_dado_com_boa_noticia(self):
        alertas = (self.e.pasta / "4-dados" / "rodadas" / REF / "alertas.md").read_text(encoding="utf-8")
        self.assertIn("Ainda não dá para saber", alertas)
        self.assertIn("Ainda não há com o que comparar", alertas)
        self.assertNotIn("Nenhuma conta com sinal", alertas)
        self.assertNotIn("Nenhuma conta empacada", alertas)
        painel = (self.e.pasta / "4-dados" / "rodadas" / REF / "painel-geral.md").read_text(encoding="utf-8")
        self.assertNotIn("Nada urgente", painel)
        self.assertIn("Ainda não há nota", painel)
        self.assertIn("Ainda não dá para saber", self.saida)


class TestCanceladas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Empresa("canceladas")
        cls.codigo, cls.saida = cls.e.rodada()
        cls.r = cls.e.resumo()
        cls.m = cls.e.mapa()
        cls.p = cls.r["conta_perdida"]

    @classmethod
    def tearDownClass(cls):
        cls.e.fechar()

    def test_rodou(self):
        self.assertEqual(self.codigo, 0, self.saida)

    def test_canceladas_fora_da_carteira_ativa(self):
        self.assertEqual(self.r["contas"]["ativas"], 24)
        self.assertEqual(self.r["contas"]["canceladas"], 6)
        canceladas = {self.m[n] for n in self.m if "Sumiu" in n or "Promotora" in n}
        self.assertFalse(canceladas & {p["conta"] for p in self.r["prioridades"]})

    def test_teste_da_conta_perdida(self):
        self.assertEqual((self.p["sim"], self.p["nao"], self.p["sem_dado"], self.p["total"]), (2, 2, 2, 6))
        self.assertEqual((self.p["sim_pela_nota"], self.p["sim_por_alerta"]), (1, 1))
        d = {x["conta"]: x for x in self.p["detalhes"]}
        sumiu = d[self.m["Empresa Fictícia Sumiu"]]
        self.assertEqual(sumiu["avisaria"], "sim")
        self.assertEqual(sumiu["nota"], 6)  # (3*0 + 3*12,5) / 6 = 6,25
        self.assertEqual(d[self.m["Empresa Fictícia Promotora"]]["avisaria"], "não")
        self.assertEqual(d[self.m["Empresa Fictícia Promotora"]]["nota"], 100)
        self.assertEqual(d[self.m["Empresa Fictícia Antiga Saída"]]["avisaria"], "não dá para saber")
        parada = d[self.m["Empresa Fictícia Parada"]]
        self.assertEqual(parada["avisaria"], "sim")
        self.assertIn("empacada", parada["por_que"])
        self.assertEqual(d[self.m["Empresa Fictícia Sem Histórico"]]["avisaria"], "não")
        self.assertEqual(d[self.m["Empresa Fictícia Sem Data"]]["avisaria"], "não dá para saber")

    def test_churn_conferido_a_mao(self):
        v = {x["id"]: x["valor"] for x in self.r["painel"]["metricas"]}
        self.assertEqual(v["churn_contas_30d"], 12.0)  # 3 de 25: contas novas ficam fora da base
        self.assertEqual(v["churn_receita_30d"], 21.4)  # 6.000 de 28.000
        self.assertEqual(v["churn_contas_12m"], 18.5)  # 5 de 27
        self.assertEqual(v["churn_receita_12m"], 26.7)  # 8.000 de 30.000
        d = {x["id"]: x["detalhe"] for x in self.r["painel"]["metricas"]}
        self.assertEqual(d["churn_contas_30d"], "3 de 25 contas")
        self.assertEqual(d["churn_receita_30d"], "R$ 6.000 de R$ 28.000")

    def test_rotulos_nao_contam_a_conta_duas_vezes(self):
        saida = rodar("rotulos", "--pasta", self.e.pasta)[1]
        self.assertIn("Acompanhamento (27), Implantação (1)", saida)  # 28 contas com etapa, de 30

    def test_todas_na_etapa_sem_prazo_nao_e_falta_de_dado(self):
        self.assertTrue(self.r["dados_disponiveis"]["etapa"])
        alertas = (self.e.pasta / "4-dados" / "rodadas" / REF / "alertas.md").read_text(encoding="utf-8")
        self.assertIn("Nenhuma conta empacada nesta rodada", alertas)

    def test_avisa_quando_a_regua_esta_frouxa(self):
        # 24 de 24 saudáveis, e 2 contas saíram sem a nota avisar
        self.assertTrue(any("régua pode estar frouxa" in a for a in self.r["avisos_sobre_os_dados"]))

    def test_sem_conta_com_sinal_nao_sugere_maiores_contas(self):
        rodar("semana", "--pasta", self.e.pasta, "--data", REF)
        texto = (self.e.pasta / "2-metas" / "semana-2026-11-02.md").read_text(encoding="utf-8")
        self.assertIn("Nenhuma conta com sinal de risco", texto)
        self.assertNotIn("maiores contas", texto)
        self.assertIn("1 pela nota, 1 só pelo alerta", texto)

    def test_meta_de_churn_atrasada(self):
        self.assertEqual(self.r["metas"][0]["situacao"], "atrás")

    def test_motivo_vago_vira_lacuna(self):
        texto = " ".join(f["o_que_falta"] for f in self.r["falta_medir"])
        self.assertIn("3 cancelamentos sem motivo específico", texto)

    def test_aba_na_planilha(self):
        livro = openpyxl.load_workbook(self.e.pasta / "4-dados" / "rodadas" / REF / "health-score.xlsx", data_only=True)
        self.assertIn("Conta perdida", livro.sheetnames)
        self.assertIn("teria avisado 2", livro["Conta perdida"]["A2"].value)
        livro.close()


class TestRecompra(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Empresa("recompra")
        cls.codigo, cls.saida = cls.e.rodada()
        cls.r = cls.e.resumo()
        cls.m = cls.e.mapa()
        cls.notas = {}
        livro = openpyxl.load_workbook(cls.e.pasta / "4-dados" / "rodadas" / REF / "health-score.xlsx", data_only=True)
        aba = livro["Health score"]
        for l in range(6, 12):
            cls.notas[aba.cell(l, 4).value] = (aba.cell(l, 5).value, aba.cell(l, 8).value)
        livro.close()

    @classmethod
    def tearDownClass(cls):
        cls.e.fechar()

    def test_rodou(self):
        self.assertEqual(self.codigo, 0, self.saida)

    def test_cada_conta_contra_o_proprio_padrao(self):
        self.assertEqual(self.notas["Distribuidora Fictícia Mensal"][0], 100)
        self.assertEqual(self.notas["Distribuidora Fictícia Sumiu"][0], 0)
        self.assertEqual(self.notas["Distribuidora Fictícia Trimestral"][0], 100)  # 60 dias é normal para ela
        self.assertEqual(self.notas["Distribuidora Fictícia Demorando"][0], 70)  # (3*50 + 2*100) / 5

    def test_pouco_historico_tem_confianca_baixa(self):
        self.assertEqual(self.notas["Distribuidora Fictícia Nova"], (100, "baixa"))

    def test_alerta_de_intervalo(self):
        contas = {a["conta"] for a in self.r["alertas_de_padrao"]}
        self.assertIn(self.m["Distribuidora Fictícia Sumiu"], contas)
        self.assertIn(self.m["Distribuidora Fictícia Demorando"], contas)
        self.assertNotIn(self.m["Distribuidora Fictícia Trimestral"], contas)
        self.assertNotIn(self.m["Distribuidora Fictícia Mensal"], contas)

    def test_demorando_tem_nota_boa_e_mesmo_assim_entra_na_lista(self):
        p = por_conta(self.r["prioridades"], self.m["Distribuidora Fictícia Demorando"])
        self.assertEqual(p["nota"], 70)
        self.assertTrue(any("com nota boa" in t for t in p["por_que"]))

    def test_nao_cobra_o_que_recompra_nao_tem(self):
        texto = " ".join(f["o_que_falta"] for f in self.r["falta_medir"])
        self.assertNotIn("renovação", texto)
        self.assertNotIn("Data de cancelamento", texto)
        faltas = {f["o_que_falta"]: f["prioridade"] for f in self.r["falta_medir"]}
        self.assertEqual(faltas["Etapa atual de cada conta"], "baixa")
        self.assertIn("Regra de conta perdida", faltas)

    def test_painel_sem_metricas_de_contrato(self):
        ids = {x["id"] for x in self.r["painel"]["metricas"]}
        for metrica in ("churn_contas_30d", "churn_receita_12m", "renovacoes_90d", "grr", "nrr", "contas_empacadas"):
            self.assertNotIn(metrica, ids)
        self.assertIn("receita_ativa", ids)

    def test_semana_de_recompra(self):
        codigo, saida = rodar("semana", "--pasta", self.e.pasta, "--data", REF)
        self.assertEqual(codigo, 0, saida)
        texto = (self.e.pasta / "2-metas" / "semana-2026-11-02.md").read_text(encoding="utf-8")
        self.assertIn("Quarta: contas fora do ritmo", texto)
        self.assertIn(self.m["Distribuidora Fictícia Sumiu"], texto.split("Quarta: contas fora do ritmo")[1].split("Quinta")[0])
        self.assertNotIn("renovações com risco", texto)
        self.assertIn("não usa etapas", texto)


class TestChecklistIncompleto(unittest.TestCase):
    """O que a primeira passada de ponta a ponta achou: faltar resposta não pode travar a rodada."""

    def setUp(self):
        self.e = Empresa("canceladas")
        self.caminho = self.e.pasta / "4-dados" / "como-medir.md"

    def tearDown(self):
        self.e.fechar()

    def _acrescentar(self, linha: str) -> None:
        texto = self.caminho.read_text(encoding="utf-8").rstrip() + "\n" + linha + "\n"
        self.caminho.write_text(texto, encoding="utf-8")

    def test_rotina_sem_dado_nem_frequencia_nao_trava_e_vira_lacuna(self):
        self._acrescentar("| chamados | chamados | Chamados | Chamado aberto | | | | eventos | | média | ruim |")
        codigo, saida = rodar("validar", "--pasta", self.e.pasta)
        self.assertEqual(codigo, 0, saida)
        self.assertIn("Em aberto", saida)
        self.assertIn("frequência esperada", saida)
        self.assertEqual(self.e.rodada()[0], 0)
        faltas = " ".join(f["o_que_falta"] for f in self.e.resumo()["falta_medir"])
        self.assertIn("Rotina 'Chamados' sem dado", faltas)

    def test_arquivo_ainda_nao_ligado_nao_trava(self):
        self._acrescentar("| nps | rotina | Pesquisa | Resposta | CRM | | | contagem | 1 | baixa | bom |")
        codigo, saida = rodar("validar", "--pasta", self.e.pasta)
        self.assertEqual(codigo, 0, saida)
        self.assertIn("ainda aponta para 'CRM'", saida)
        self.assertEqual(self.e.rodada()[0], 0)

    def test_rotina_com_dado_sem_frequencia_tem_lacuna_propria(self):
        self._acrescentar("| plano2 | rotina | Plano de novo | Plano | clientes.csv | Planos 30d | | contagem | | média | bom |")
        self.assertEqual(self.e.rodada()[0], 0)
        faltas = [f["o_que_falta"] for f in self.e.resumo()["falta_medir"]]
        self.assertIn("Rotina 'Plano de novo' sem frequência esperada", faltas)

    def test_criticidade_em_branco_avisa_o_que_usou(self):
        self._acrescentar("| x | rotina | Rotina X | Dado | | | | | | | |")
        self.assertEqual(self.e.rodada()[0], 0)
        self.assertTrue(any("usei média" in a for a in self.e.resumo()["avisos_sobre_os_dados"]))

    def test_o_que_esta_escrito_errado_continua_travando(self):
        self._acrescentar("| y | rotina | Rotina Y | Dado | | | | | | urgentíssima | |")
        codigo, saida = rodar("validar", "--pasta", self.e.pasta)
        self.assertEqual(codigo, 1)
        self.assertIn("Para corrigir", saida)
        self.assertEqual(self.e.rodada()[0], 1)

    def test_proximo_passo_acompanha_o_trabalho(self):
        # sem metas e sem etapas, o próximo passo não fica preso no checklist
        (self.e.pasta / "1-empresa" / "jornada.md").write_text("# Jornada\n", encoding="utf-8")
        (self.e.pasta / "2-metas" / "metas.md").write_text("# Metas\n", encoding="utf-8")
        saida = rodar("validar", "--pasta", self.e.pasta)[1]
        self.assertIn("Próximo passo: Analista: rodar a primeira rodada", saida)
        self.assertEqual(self.e.rodada()[0], 0)
        self.assertIn("Próximo passo: Líder da rotina: montar a semana", rodar("validar", "--pasta", self.e.pasta)[1])
        rodar("semana", "--pasta", self.e.pasta, "--data", REF)
        self.assertIn("receber um export novo", rodar("validar", "--pasta", self.e.pasta)[1])

    def test_cancelada_sem_data_vira_lacuna(self):
        self.assertEqual(self.e.rodada()[0], 0)
        faltas = [f["o_que_falta"] for f in self.e.resumo()["falta_medir"]]
        self.assertIn("1 conta cancelada sem data", faltas)

    def test_receber_avisa_que_o_original_fica(self):
        origem = self.e.entrada / "clientes.csv"
        codigo, saida = rodar("receber", "--pasta", self.e.pasta, "--arquivo", origem, "--data", "2026-11-04")
        self.assertEqual(codigo, 0, saida)
        self.assertIn("original continua", saida)
        self.assertNotIn("Empresa Fictícia", saida)

    def test_leia_me_mostra_o_modo(self):
        self.assertIn("**Modo de privacidade:** protegido", (self.e.pasta / "LEIA-ME.md").read_text(encoding="utf-8"))


class TestRodadas(unittest.TestCase):
    """Compara com a rodada anterior: padrão, mudança de pesos e dado real da época."""

    def setUp(self):
        self.e = Empresa("completa")
        self.primeira = "2026-10-03"
        self.segunda = REF

    def tearDown(self):
        self.e.fechar()

    def test_nao_sobrescreve_rodada_sem_confirmar(self):
        self.assertEqual(self.e.rodada()[0], 0)
        codigo, saida = self.e.rodada()
        self.assertEqual(codigo, 2)
        self.assertIn("--refazer", saida)
        self.assertEqual(self.e.rodada(REF, "--refazer")[0], 0)

    def _sem_coluna_anterior(self):
        caminho = self.e.pasta / "4-dados" / "como-medir.md"
        texto = caminho.read_text(encoding="utf-8")
        for coluna in ("Planos lançados 30d ant", "Movimentos de estoque 30d ant", "Agendas 30d ant"):
            texto = texto.replace(f" | {coluna} | ", " |  | ")
        caminho.write_text(texto, encoding="utf-8")

    def test_padrao_contra_a_rodada_anterior(self):
        self._sem_coluna_anterior()
        self.assertEqual(self.e.rodada(self.primeira)[0], 0)
        # na primeira rodada, sem coluna anterior, não há com o que comparar o plano
        self.assertEqual([a for a in self.e.resumo(self.primeira)["alertas_de_padrao"] if a["indicador"] == "plano"], [])
        # a segunda rodada traz uma conta com o plano caindo de 10 para 4
        contas = self.e.entrada / "contas.csv"
        import csv

        with contas.open(encoding="utf-8", newline="") as f:
            linhas = list(csv.reader(f))
        cab = linhas[0]
        for linha in linhas[1:]:
            if linha[cab.index("Cliente")] == "Clínica Fictícia Saudável 01":
                linha[cab.index("Planos lançados 30d")] = "4"
        with contas.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(linhas)
        self.assertEqual(self.e.rodada(self.segunda)[0], 0)
        r = self.e.resumo(self.segunda)
        codigo = self.e.mapa()["Clínica Fictícia Saudável 01"]
        alerta = por_conta(r["alertas_de_padrao"], codigo)
        self.assertEqual((alerta["antes"], alerta["agora"], alerta["variacao_pct"]), (10, 4, -60))
        self.assertEqual(r["rodada_anterior"], self.primeira)
        # o código da conta é o mesmo nas duas rodadas
        self.assertEqual(self.e.mapa()["Clínica Fictícia Saudável 01"], codigo)

    def test_mudar_peso_marca_a_data(self):
        self.assertEqual(self.e.rodada(self.primeira)[0], 0)
        self.assertFalse(self.e.resumo(self.primeira)["formula"]["mudou_nesta_rodada"])
        caminho = self.e.pasta / "4-dados" / "como-medir.md"
        caminho.write_text(caminho.read_text(encoding="utf-8").replace("| Agendas 30d ant | contagem | 20 | média |", "| Agendas 30d ant | contagem | 20 | alta |"), encoding="utf-8")
        self.assertEqual(self.e.rodada(self.segunda)[0], 0)
        r = self.e.resumo(self.segunda)
        self.assertTrue(r["formula"]["mudou_nesta_rodada"])
        self.assertEqual(r["formula"]["mudou_em"], self.segunda)
        self.assertTrue(any("não é comparável" in a for a in r["avisos_sobre_os_dados"]))
        alertas = (self.e.pasta / "4-dados" / "rodadas" / self.segunda / "alertas.md").read_text(encoding="utf-8")
        self.assertIn("não é comparável", alertas)

    def test_direcao_por_etapa(self):
        caminho = self.e.pasta / "4-dados" / "como-medir.md"
        texto = caminho.read_text(encoding="utf-8").replace("| 3 em 30 dias | média | ruim |", "| 3 em 30 dias | média | Acompanhamento: bom; demais: ruim |")
        caminho.write_text(texto, encoding="utf-8")
        self.assertEqual(self.e.rodada()[0], 0)
        r = self.e.resumo()
        grande = por_conta(r["prioridades"], self.e.mapa()["Hospital Fictício Grande Conta"])
        # chamados agora não penalizam nesta etapa: (75 + 0 + 50 + 0 + 2*100) / 12 = 27,08
        self.assertEqual(grande["nota"], 27)

    def test_conta_perdida_usa_dado_real_da_rodada(self):
        import csv

        contas = self.e.entrada / "contas.csv"
        self.assertEqual(self.e.rodada(self.primeira)[0], 0)
        with contas.open(encoding="utf-8", newline="") as f:
            linhas = list(csv.reader(f))
        cab = linhas[0]
        for linha in linhas[1:]:
            if linha[cab.index("Cliente")] == "Clínica Fictícia Morna 1":
                linha[cab.index("Status")] = "Cancelado"
                linha[cab.index("Cancelamento")] = "20/10/2026"
        with contas.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(linhas)
        self.assertEqual(self.e.rodada(self.segunda)[0], 0)
        p = self.e.resumo(self.segunda)["conta_perdida"]
        self.assertEqual(p["total"], 1)
        self.assertEqual(p["detalhes"][0]["avisaria"], "sim")
        self.assertEqual(p["detalhes"][0]["nota"], 46)
        self.assertIn(self.primeira, p["detalhes"][0]["por_que"])


if __name__ == "__main__":
    unittest.main()
