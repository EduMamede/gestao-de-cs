"""Contas e receita: renovação por tipo de contrato, desconto pela leitura da conta e reunião com número que veio do script."""

import json
import re
import unittest

import openpyxl

from apoio import REF, Empresa, rodar, textos_para_ia
from gerar_bases import escrever, f, md

from cslib import apresentacao as apresentacao_mod
from cslib import contas as contas_mod
from cslib.medir import tipo_de_contrato

try:
    from pptx.enum.shapes import PP_PLACEHOLDER
except ImportError:
    PP_PLACEHOLDER = None


def item_base(**extras) -> dict:
    item = {"conta": "CONTA-001", "nota": 100, "sinais": [], "rotinas": [], "chance_churn_pct": None}
    item.update(extras)
    return item


class TestLeituras(unittest.TestCase):
    def test_tipo_de_contrato(self):
        for texto in ("Anual", "ANUAL", "12 meses", "2 anos", "contrato anual"):
            self.assertEqual(tipo_de_contrato(texto), "anual", texto)
        for texto in ("Mensal", "mensal recorrente", "30 dias", "mês"):
            self.assertEqual(tipo_de_contrato(texto), "mensal", texto)
        self.assertEqual(tipo_de_contrato("Trimestral"), "outro")
        self.assertIsNone(tipo_de_contrato(""))

    def test_sem_sinal_pede_contrapartida(self):
        self.assertEqual(contas_mod.caminho_da_conversa(item_base()), ("contrapartida", []))

    def test_com_sinal_recupera(self):
        caminho, motivos = contas_mod.caminho_da_conversa(item_base(nota=40, sinais=[{"codigo": "nota_amarela", "texto": "Nota 40"}]))
        self.assertEqual(caminho, "recuperacao")
        self.assertEqual(motivos, ["Nota 40"])

    def test_muitos_chamados_conta_como_sinal(self):
        rotinas = [{"bloco": "chamados", "rotina": "Chamados", "subnota": 0.0, "agora": 9.0}]
        self.assertEqual(contas_mod.caminho_da_conversa(item_base(rotinas=rotinas))[0], "recuperacao")
        rotinas[0]["subnota"] = 100.0
        self.assertEqual(contas_mod.caminho_da_conversa(item_base(rotinas=rotinas))[0], "contrapartida")

    def test_modelo_so_conta_com_chance_alta(self):
        self.assertEqual(contas_mod.caminho_da_conversa(item_base(chance_churn_pct=49))[0], "contrapartida")
        self.assertEqual(contas_mod.caminho_da_conversa(item_base(chance_churn_pct=50))[0], "recuperacao")

    def test_renovacao_sozinha_nao_e_insatisfacao(self):
        item = item_base(sinais=[{"codigo": "renovacao_sozinha", "texto": "Renova em 60 dias"}])
        self.assertEqual(contas_mod.caminho_da_conversa(item)[0], "contrapartida")

    def test_sem_nota_e_sem_sinal_nao_da_para_saber(self):
        self.assertEqual(contas_mod.caminho_da_conversa(item_base(nota=None))[0], "sem_dados")


class TestBaseCompleta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Empresa("completa")
        codigo, saida = cls.e.rodada()
        assert codigo == 0, saida
        cls.m = cls.e.mapa()
        cls.fatos = json.loads((cls.e.pasta / "4-dados" / "rodadas" / REF / "contas.json").read_text(encoding="utf-8"))
        cls.grande = cls.m["Hospital Fictício Grande Conta"]
        cls.saudavel = cls.m["Clínica Fictícia Renova Bem"]

    @classmethod
    def tearDownClass(cls):
        cls.e.fechar()

    def test_fatos_batem_com_a_conta_calculada_a_mao(self):
        item = self.fatos[self.grande]
        self.assertEqual(item["nota"], 10)  # gerar_bases.py: (3*25 + 2*0 + 2*25 + 3*0 + 2*0) / 12 = 10,4
        self.assertEqual(item["receita"], 48000)
        self.assertEqual(item["dias_ate_renovar"], 45)
        self.assertEqual(item["dias_sem_contato"], 90)
        self.assertTrue(item["contatos_anotados"]["patrocinador"])

    def test_nada_de_nome_nos_fatos_do_modo_protegido(self):
        texto = (self.e.pasta / "4-dados" / "rodadas" / REF / "contas.json").read_text(encoding="utf-8")
        self.assertNotIn("Fictíci", texto)
        self.assertNotIn("Pagamento\": \"atrasado", texto)
        self.assertNotIn("atrasado", re.sub(r'"texto": "[^"]*"', "", texto))

    def test_rotulo_do_export_nao_entra_nos_fatos(self):
        pagamento = next(r for r in self.fatos[self.grande]["rotinas"] if r["id"] == "pagamento")
        self.assertIsNone(pagamento["agora"])
        self.assertEqual(pagamento["subnota"], 0.0)

    def test_carteira(self):
        codigo, saida = rodar("carteira", "--pasta", self.e.pasta)
        self.assertEqual(codigo, 0, saida)
        self.assertIn(self.grande, saida)
        self.assertIn("recuperar primeiro", saida)
        self.assertIn("sem sinal de insatisfação", saida)
        self.assertNotIn("Fictíci", saida)

    def test_reuniao_de_renovacao_em_conta_com_risco(self):
        codigo, saida = rodar("reuniao", "--pasta", self.e.pasta, "--conta", self.grande, "--tipo", "renovacao", "--data", REF)
        self.assertEqual(codigo, 0, saida)
        self.assertIn("recuperar primeiro", saida)
        self.assertIn("Envolva a liderança", saida)
        self.assertIn("R$ 48.000", saida)
        self.assertIn("Renova em 45 dias", saida)
        self.assertNotIn("Fictíci", saida)
        arquivo = self.e.pasta / "3-clientes" / self.grande / "reunioes" / f"{REF}-renovacao.md"
        self.assertTrue(arquivo.exists())
        self.assertTrue((self.e.pasta / "3-clientes" / self.grande / "ficha.md").exists())

    def test_reuniao_de_renovacao_em_conta_sem_risco(self):
        codigo, saida = rodar("reuniao", "--pasta", self.e.pasta, "--conta", self.saudavel, "--tipo", "renovacao", "--data", REF)
        self.assertEqual(codigo, 0, saida)
        self.assertIn("pedir contrapartida", saida)
        self.assertIn("menos por usuário, com mais usuários", saida)
        self.assertIn("levante o valor", saida)

    def test_reuniao_nao_sobrescreve_o_que_a_pessoa_escreveu(self):
        rodar("reuniao", "--pasta", self.e.pasta, "--conta", self.saudavel, "--tipo", "revisao", "--data", REF)
        arquivo = self.e.pasta / "3-clientes" / self.saudavel / "reunioes" / f"{REF}-revisao.md"
        arquivo.write_text("escrevi aqui", encoding="utf-8")
        codigo, saida = rodar("reuniao", "--pasta", self.e.pasta, "--conta", self.saudavel, "--tipo", "revisao", "--data", REF)
        self.assertEqual(codigo, 0, saida)
        self.assertIn("não mexi nele", saida)
        self.assertEqual(arquivo.read_text(encoding="utf-8"), "escrevi aqui")

    def test_valor_vem_da_ficha(self):
        codigo = self.m["Clínica Fictícia Cresceu"]
        rodar("nova-ficha", "--pasta", self.e.pasta, "--conta", codigo)
        ficha = self.e.pasta / "3-clientes" / codigo / "ficha.md"
        texto = ficha.read_text(encoding="utf-8")
        trocado = re.sub(r"\{\{pergunte isso depois.*?\}\}", "Reduzimos a perda de estoque em 12%", texto)
        ficha.write_text(trocado, encoding="utf-8")
        saida = rodar("reuniao", "--pasta", self.e.pasta, "--conta", codigo, "--data", REF)[1]
        self.assertIn("Reduzimos a perda de estoque em 12%", saida)
        self.assertNotIn(contas_mod.MARCA_VALOR, saida)
        # número da ficha da própria conta passa na conferência
        arquivo = f"3-clientes/{codigo}/reunioes/{REF}-revisao.md"
        (self.e.pasta / arquivo).write_text("Reduzimos em 12%, e o estoque caiu 77%.", encoding="utf-8")
        codigo_saida, saida = rodar("conferir-numeros", "--pasta", self.e.pasta, "--arquivo", arquivo)
        self.assertEqual(codigo_saida, 1, saida)
        self.assertIn("77%", saida)
        self.assertNotIn("12%", saida)

    def test_conta_que_nao_existe(self):
        codigo, saida = rodar("reuniao", "--pasta", self.e.pasta, "--conta", "CONTA-999")
        self.assertEqual(codigo, 2, saida)
        self.assertIn("não achei a conta", saida)

    def test_aba_contas_chave_tem_nome_real_e_campos_para_preencher(self):
        livro = openpyxl.load_workbook(self.e.pasta / "4-dados" / "rodadas" / REF / "health-score.xlsx")
        if not self.e.resumo()["contas_chave"].get("existe"):
            self.assertNotIn("Contas-chave", livro.sheetnames)
            return
        aba = livro["Contas-chave"]
        textos = [str(c.value) for linha in aba.iter_rows() for c in linha if c.value is not None]
        self.assertIn("Hospital Fictício Grande Conta", textos)
        self.assertIn("O que mais ajudamos vocês hoje?", textos)

    def test_tudo_que_a_ia_le_continua_sem_nome(self):
        for arquivo, texto in textos_para_ia(self.e.pasta).items():
            self.assertNotIn("Hospital Fictício", texto, arquivo)


class TestApresentacao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Empresa("completa")
        cls.e.rodada()
        cls.codigo = cls.e.mapa()["Hospital Fictício Grande Conta"]
        rodar("reuniao", "--pasta", cls.e.pasta, "--conta", cls.codigo, "--data", REF)
        cls.relativo = f"3-clientes/{cls.codigo}/reunioes/{REF}-revisao.md"
        cls.arquivo = cls.e.pasta / cls.relativo
        cls.modelo = cls.arquivo.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.e.fechar()

    def preenchido(self) -> str:
        return (
            self.modelo.replace("- {{o número do cliente}}", f"- A equipe da {self.codigo} ganhou 3 horas por semana\n- Menos retrabalho no plano")
            .replace("Print: {{o que este print mostra}}", "Print: A tela da agenda")
            .replace("- {{o que vende, o que caiu, o que não usa}}", "- A agenda ainda não é usada")
            .replace("- {{uma ação só}}", "- Treinar a equipe na agenda")
            .replace("- {{o resultado e quando voltamos para mostrar}}", "- Agenda em uso em 60 dias, e voltamos para mostrar")
        )

    def gerar(self, texto: str) -> tuple:
        self.arquivo.write_text(texto, encoding="utf-8")
        return rodar("apresentacao", "--pasta", self.e.pasta, "--arquivo", self.relativo)

    def abrir(self):
        from pptx import Presentation

        return Presentation(str(self.e.pasta / "com-nomes" / f"{self.codigo}-{REF}-revisao.pptx"))

    def com_slide(self, conteudo: str) -> str:
        """Troca o primeiro passo do modelo pelo conteúdo do teste. O slide dele é o terceiro, depois da capa e do resumo."""
        return re.sub(r"(### O que vocês já ganharam\n\n).*?(?=### Onde ainda)", lambda m: m.group(1) + conteudo + "\n\n", self.preenchido(), flags=re.S)

    def test_nao_gera_com_campo_em_branco(self):
        self.arquivo.write_text(self.modelo, encoding="utf-8")
        codigo, saida = rodar("apresentacao", "--pasta", self.e.pasta, "--arquivo", self.relativo)
        self.assertEqual(codigo, 2, saida)
        self.assertIn("campo sem preencher", saida)

    def test_recusa_slide_com_texto_demais(self):
        for linhas in ("- " + "a" * 141, "- primeira\n- " + "b" * 201):
            codigo, saida = self.gerar(self.preenchido().replace("- A agenda ainda não é usada", linhas))
            self.assertEqual(codigo, 2, saida)
            self.assertIn("texto demais", saida)

    def test_gera_o_powerpoint_com_o_nome_real(self):
        from pptx import Presentation

        self.arquivo.write_text(self.preenchido(), encoding="utf-8")
        codigo, saida = rodar("apresentacao", "--pasta", self.e.pasta, "--arquivo", self.relativo)
        self.assertEqual(codigo, 0, saida)
        self.assertNotIn("Hospital", saida)
        destino = self.e.pasta / "com-nomes" / f"{self.codigo}-{REF}-revisao.pptx"
        self.assertTrue(destino.exists())
        deck = Presentation(str(destino))
        self.assertEqual(len(deck.slides), 7)  # capa, resumo, os 4 passos e mais um no primeiro: gráfico e print ficam separados
        self.assertIn("colar o print (A tela da agenda)", saida)
        self.assertEqual(deck.core_properties.last_modified_by, "")  # sem o nome do modelo da biblioteca
        self.assertEqual(deck.core_properties.author, "")
        textos = [forma.text_frame.text for slide in deck.slides for forma in slide.shapes if forma.has_text_frame]
        junto = "\n".join(textos)
        self.assertIn("Hospital Fictício Grande Conta", junto)
        self.assertNotIn(self.codigo, junto)
        self.assertIn("Treinar a equipe na agenda", junto)
        self.assertNotIn("{{", junto)

    def test_so_aceita_arquivo_da_pasta(self):
        codigo, saida = rodar("apresentacao", "--pasta", self.e.pasta, "--arquivo", "4-dados/.privado/rotulos.csv")
        self.assertEqual(codigo, 2, saida)

    def test_grafico_traz_o_numero_do_export_e_e_de_barras(self):
        # gerar_bases.py: esta conta tem agenda=(5, 5): 5 agora e 5 no período anterior
        codigo, saida = self.gerar(self.com_slide("Gráfico: Agenda"))
        self.assertEqual(codigo, 0, saida)
        formas = [f for f in self.abrir().slides[2].shapes if f.has_chart]
        self.assertEqual(len(formas), 1)
        grafico = formas[0].chart
        self.assertEqual(grafico.chart_type.name, "COLUMN_CLUSTERED")
        self.assertEqual(list(grafico.plots[0].series[0].values), [5, 5])
        self.assertEqual(list(grafico.plots[0].categories), ["Período anterior", "03/11"])
        self.assertIn("de 5 para 5", [f.text_frame.text for f in self.abrir().slides[2].shapes if f.has_text_frame])

    def test_nota_e_chance_nao_viram_grafico(self):
        for nome in ("Nota", "Chance de cancelar", "Receita"):
            codigo, saida = self.gerar(self.com_slide(f"Gráfico: {nome}"))
            self.assertEqual(codigo, 2, saida)
            self.assertIn("não há rotina com esse nome", saida)

    def test_rotina_com_uma_medicao_deixa_o_espaco_sem_inventar(self):
        rotinas = json.loads((self.e.pasta / "4-dados" / "rodadas" / REF / "contas.json").read_text(encoding="utf-8"))[self.codigo]["rotinas"]
        sem_antes = [r["rotina"] for r in rotinas if r["agora"] is None or r["antes"] is None]
        self.assertTrue(sem_antes, "a base precisa de uma rotina sem as duas medições")
        codigo, saida = self.gerar(self.com_slide(f"Gráfico: {sem_antes[0]}"))
        self.assertEqual(codigo, 0, saida)
        self.assertIn("ainda não tem duas medições", saida)
        slide = self.abrir().slides[2]
        self.assertFalse(any(f.has_chart for f in slide.shapes))
        self.assertEqual(len(list(slide.placeholders)), 1)

    def test_grafico_e_print_em_branco_so_deixam_o_espaco(self):
        codigo, saida = self.gerar(self.com_slide("Gráfico:"))
        self.assertEqual(codigo, 0, saida)
        self.assertIn("colar o gráfico", saida)
        codigo, saida = self.gerar(self.com_slide("Print:\nPrint:"))
        self.assertEqual(codigo, 0, saida)
        self.assertIn("colar o print", saida)
        deck = self.abrir()
        espacos = list(deck.slides[2].placeholders)
        self.assertEqual(len(espacos), 2)
        for espaco in espacos:
            self.assertEqual(espaco.placeholder_format.type, PP_PLACEHOLDER.PICTURE)
            self.assertLessEqual(espaco.left + espaco.width, deck.slide_width)
        self.assertEqual(espacos[0].height, espacos[1].height)
        modelo = deck.slides[2].slide_layout
        self.assertEqual(len(list(modelo.placeholders)), len({m.placeholder_format.idx for m in modelo.placeholders}))
        for espaco in modelo.placeholders:
            self.assertLessEqual(espaco.left + espaco.width, deck.slide_width)

    def test_mais_numeros_abrem_mais_slides(self):
        codigo, saida = self.gerar(self.com_slide("Gráfico: Agenda\nGráfico: Estoque\nGráfico: Acompanhamento do plano\nPrint: Tela"))
        self.assertEqual(codigo, 0, saida)
        deck = self.abrir()
        self.assertEqual(len(deck.slides), 8)  # capa, resumo, 3 no primeiro passo e os outros 3 passos
        self.assertEqual([sum(f.has_chart for f in deck.slides[i].shapes) for i in (2, 3, 4)], [2, 1, 0])
        self.assertEqual(len(list(deck.slides[4].placeholders)), 1)
        rotulos = [f.text_frame.text for f in deck.slides[3].shapes if f.has_text_frame]
        self.assertIn("PASSO 1 · O QUE VOCÊS JÁ GANHARAM · CONTINUAÇÃO", rotulos)
        # texto também abre outro slide, em vez de ser recusado
        linhas = "\n".join(f"- linha {i}" for i in range(8))
        codigo, saida = self.gerar(self.preenchido().replace("- A agenda ainda não é usada", linhas))
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(len(self.abrir().slides), 8)

    def test_resumo_sai_da_primeira_linha_de_cada_passo(self):
        codigo, saida = self.gerar(self.preenchido())
        self.assertEqual(codigo, 0, saida)
        textos = [f.text_frame.text for f in self.abrir().slides[1].shapes if f.has_text_frame]
        self.assertIn("Nossa conversa em 4 passos", textos)
        self.assertIn("Próximos passos. Treinar a equipe na agenda", textos)
        self.assertIn("A equipe da Hospital Fictício Grande Conta ganhou 3 horas por semana", " ".join(textos))
        self.assertEqual([t for t in textos if t in ("1", "2", "3", "4")], ["2", "1", "2", "3", "4"])  # o primeiro é o número da página

    def test_capa_e_fechamento_em_destaque_e_um_slide_em_detalhe(self):
        from pptx.dml.color import RGBColor

        codigo, saida = self.gerar(self.preenchido())
        self.assertEqual(codigo, 0, saida)
        slides = list(self.abrir().slides)
        cor = lambda slide: str(slide.background.fill.fore_color.rgb)
        self.assertEqual(cor(slides[0]), "D7FF00")
        self.assertEqual(cor(slides[-1]), "D7FF00")
        self.assertEqual(cor(slides[-2]), "FF4FD8")
        for slide in slides[1:-2]:
            self.assertNotIn("<p:bg>", slide._element.xml)
        for slide in slides:
            self.assertIn('type="slidenum"', slide._element.xml)

    def test_recusa_texto_demais_ao_lado_do_grafico(self):
        codigo, saida = self.gerar(self.com_slide("Print: um\n\n- a\n- b\n- c\n- d"))
        self.assertEqual(codigo, 2, saida)
        self.assertIn("texto demais", saida)

    def test_campo_em_branco_no_print_tambem_barra(self):
        codigo, saida = self.gerar(self.preenchido().replace("Print: A tela da agenda", "Print: {{o que este print mostra}}"))
        self.assertEqual(codigo, 2, saida)
        self.assertIn("campo sem preencher", saida)

    def test_reuniao_de_antes_dos_graficos_continua_gerando(self):
        antigo = re.sub(r"(?m)^(Gráfico|Print):.*$", "", self.preenchido())
        codigo, saida = self.gerar(antigo)
        self.assertEqual(codigo, 0, saida)
        self.assertEqual(len(self.abrir().slides), 6)  # capa, resumo e os 4 passos
        self.assertNotIn("precisa fazer", saida)

    def test_modelo_nao_sugere_o_que_nao_subiu(self):
        # gerar_bases.py: nesta conta plano, estoque e agenda ficaram iguais, e os chamados não entram
        trecho = re.search(r"### O que vocês já ganharam(.*?)### Onde ainda", self.modelo, re.S).group(1)
        self.assertRegex(trecho, r"(?m)^Gráfico:$")
        self.assertNotIn("Gráfico: ", trecho)
        self.assertIn("Print:", trecho)
        self.assertNotIn("Gráfico", re.search(r"### Onde ainda(.*?)### Próximos passos", self.modelo, re.S).group(1))


class TestGraficoComRodadas(unittest.TestCase):
    """A evolução vem das rodadas guardadas, e rodada sem o dado fica de fora."""

    def setUp(self):
        self.e = Empresa("completa")

    def tearDown(self):
        self.e.fechar()

    def test_modelo_sugere_o_que_subiu(self):
        # gerar_bases.py: esta conta tem plano=(25, 10), e o resto ficou igual
        self.assertEqual(self.e.rodada()[0], 0)
        codigo = self.e.mapa()["Clínica Fictícia Cresceu"]
        saida = rodar("reuniao", "--pasta", self.e.pasta, "--conta", codigo, "--data", REF)[1]
        trecho = re.search(r"### O que vocês já ganharam(.*?)### Onde ainda", saida, re.S).group(1)
        self.assertEqual(re.findall(r"(?m)^Gráfico: (.+)$", trecho), ["Acompanhamento do plano"])

    def test_capa_da_expansao_nao_diz_que_e_expansao(self):
        self.assertEqual(self.e.rodada()[0], 0)
        codigo = self.e.mapa()["Clínica Fictícia Cresceu"]
        saida = rodar("reuniao", "--pasta", self.e.pasta, "--conta", codigo, "--tipo", "expansao", "--data", REF)[1]
        self.assertIn("Capa: Revisão de resultados\n", saida)

    def test_o_que_subiu_e_o_que_caiu_vao_para_passos_diferentes(self):
        rotinas = [
            {"id": "a", "rotina": "Sobe", "bloco": "rotina", "agora": 10, "antes": 2},
            {"id": "b", "rotina": "Cai", "bloco": "rotina", "agora": 2, "antes": 10},
            {"id": "c", "rotina": "Chamados", "bloco": "chamados", "agora": 9, "antes": 1},
            {"id": "d", "rotina": "Igual", "bloco": "rotina", "agora": 5, "antes": 5},
            {"id": "e", "rotina": "Sem dado", "bloco": "rotina", "agora": None, "antes": 5},
        ]
        data = __import__("datetime").date.fromisoformat(REF)
        self.assertEqual(contas_mod.rotinas_para_grafico(self.e.pasta, data, {"conta": "CONTA-001", "rotinas": rotinas}), (["Sobe"], ["Cai"]))

    def test_grafico_com_tres_rodadas_marca_so_a_primeira_e_a_ultima(self):
        from pptx import Presentation

        for data in ("2026-09-03", "2026-10-03", REF):
            self.assertEqual(self.e.rodada(data)[0], 0)
        codigo = self.e.mapa()["Clínica Fictícia Cresceu"]
        rodar("reuniao", "--pasta", self.e.pasta, "--conta", codigo, "--data", REF)
        relativo = f"3-clientes/{codigo}/reunioes/{REF}-revisao.md"
        arquivo = self.e.pasta / relativo
        texto = re.sub(r"(?s)^### O que vocês já ganharam.*", "### Como evoluiu\n\nGráfico: Acompanhamento do plano\n", arquivo.read_text(encoding="utf-8"), flags=re.M)
        arquivo.write_text(texto, encoding="utf-8")
        retorno, saida = rodar("apresentacao", "--pasta", self.e.pasta, "--arquivo", relativo)
        self.assertEqual(retorno, 0, saida)
        deck = Presentation(str(self.e.pasta / "com-nomes" / f"{codigo}-{REF}-revisao.pptx"))
        grafico = next(f.chart for f in deck.slides[1].shapes if f.has_chart)
        # gerar_bases.py: plano=(25, 10). As três rodadas leram o mesmo export
        self.assertEqual(list(grafico.plots[0].series[0].values), [25, 25, 25])
        self.assertEqual(list(grafico.plots[0].categories), ["03/09", "03/10", "03/11"])
        self.assertEqual(grafico.value_axis.minimum_scale, 0)
        xml = grafico._chartSpace.xml
        self.assertEqual(xml.count("<c:dLbl>"), 2)
        self.assertEqual(re.findall(r'<c:showVal val="(\d)"/>', re.search(r"<c:dLbls>.*</c:dLbls>", xml, re.S).group(0)), ["1", "1", "0"])

    def test_serie_usa_as_rodadas_e_nao_preenche_buraco(self):
        for data in ("2026-09-03", "2026-10-03", REF):
            self.assertEqual(self.e.rodada(data)[0], 0)
        codigo = self.e.mapa()["Clínica Fictícia Saudável 01"]
        fatos = json.loads((self.e.pasta / "4-dados" / "rodadas" / REF / "contas.json").read_text(encoding="utf-8"))
        rotina = next(r for r in fatos[codigo]["rotinas"] if r["rotina"] == "Acompanhamento do plano")
        pasta_outubro = self.e.pasta / "4-dados" / "rodadas" / "2026-10-03" / "valores.csv"
        texto = pasta_outubro.read_text(encoding="utf-8-sig")
        linhas = texto.splitlines()
        cabecalho = linhas[0].split(";")
        coluna = cabecalho.index(f"ind:{rotina['id']}")
        for i, linha in enumerate(linhas):
            partes = linha.split(";")
            if partes[0] == codigo:
                partes[coluna] = ""
                linhas[i] = ";".join(partes)
        pasta_outubro.write_text("\n".join(linhas), encoding="utf-8-sig")
        serie = contas_mod.serie_da_rotina(self.e.pasta, __import__("datetime").date.fromisoformat(REF), codigo, rotina)
        self.assertEqual([rotulo for rotulo, _ in serie], ["03/09", "03/11"])
        self.assertEqual(serie[-1][1], rotina["agora"])


class TestComposicaoDaApresentacao(unittest.TestCase):
    def test_numeros_se_destacam_sozinhos(self):
        self.assertEqual(apresentacao_mod.trechos("subiram de 4 para 25,5% e R$ 1.000"), [("subiram de ", False), ("4", True), (" para ", False), ("25,5%", True), (" e ", False), ("R$ 1.000", True)])
        self.assertEqual(apresentacao_mod.trechos("sem número"), [("sem número", False)])

    def test_marca_manual_vale_mais_que_o_numero(self):
        self.assertEqual(apresentacao_mod.trechos("as **duas unidades** em 60 dias"), [("as ", False), ("duas unidades", True), (" em 60 dias", False)])

    def test_grafico_fica_com_grafico_e_print_com_print(self):
        g = lambda nome: ("grafico", nome)
        p = lambda nome: ("print", nome)
        lista = apresentacao_mod.paginas([("Passo", ["frase"], [g("a"), g("b"), g("c"), p("x"), p("y"), p("z")])])
        self.assertEqual([pagina["visuais"] for pagina in lista], [[g("a"), g("b")], [g("c")], [p("x"), p("y")], [p("z")]])
        self.assertEqual([pagina["linhas"] for pagina in lista], [["frase"], [], [], []])
        self.assertEqual([pagina["continuacao"] for pagina in lista], [False, True, True, True])

    def test_texto_comprido_abre_outro_slide(self):
        lista = apresentacao_mod.paginas([("Passo", [f"linha {i}" for i in range(8)], [])])
        self.assertEqual([len(pagina["linhas"]) for pagina in lista], [6, 2])
        longas = ["x" * 200, "y" * 200, "z" * 200]
        self.assertEqual([len(p["linhas"]) for p in apresentacao_mod.paginas([("Passo", longas, [])])], [2, 1])

    def test_so_o_fim_ganha_cor_e_grafico_fica_no_escuro(self):
        self.assertEqual([apresentacao_mod.modo_do_slide(i, 4, []) for i in range(4)], ["escuro", "escuro", "detalhe", "destaque"])
        self.assertEqual(apresentacao_mod.modo_do_slide(3, 4, [("print", "")]), "escuro")
        self.assertEqual(apresentacao_mod.modo_do_slide(1, 2, []), "escuro")


class TestContratoMensal(unittest.TestCase):
    """Base pequena e própria: uma conta anual e uma mensal, as duas com data no campo de renovação."""

    @classmethod
    def setUpClass(cls):
        cls.e = Empresa("minima")
        base = cls.e.pasta / "4-dados"
        escrever(
            cls.e.entrada / "contas.csv",
            [
                ["ID", "Cliente", "MRR", "Renovação", "Contrato", "Status", "Uso", "Uso ant"],
                ["A1", "Cliente Fictício Anual", 1000, f(30), "Anual", "Ativo", 2, 20],
                ["M1", "Cliente Fictício Mensal", 1000, f(30), "Mensal", "Ativo", 2, 20],
                ["S1", "Cliente Fictício Sem Tipo", 1000, f(30), "", "Ativo", 20, 20],
            ],
        )
        (base / "colunas.md").write_text(
            md(
                "Colunas",
                "Arquivos",
                "| arquivo | tipo |\n| --- | --- |\n| contas.csv | contas |\n",
                "\n## Colunas\n\n| arquivo | coluna | campo |\n| --- | --- | --- |\n| contas.csv | ID | conta_id |\n| contas.csv | Cliente | conta_nome |\n"
                "| contas.csv | MRR | receita |\n| contas.csv | Renovação | renovacao |\n| contas.csv | Contrato | contrato |\n| contas.csv | Status | status |\n",
            ),
            encoding="utf-8",
        )
        (base / "como-medir.md").write_text(
            md(
                "Como medir",
                "Indicadores",
                "| id | bloco | rotina | dado que prova | onde está o dado | coluna | coluna anterior | como ler | frequência esperada | criticidade | subir é |\n"
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
                "| uso | rotina | Uso | Uso no mês | contas.csv | Uso | Uso ant | contagem | 10 | alta | bom |\n",
            ),
            encoding="utf-8",
        )
        for outro in cls.e.entrada.iterdir():
            if outro.name != "contas.csv":
                outro.unlink()
        codigo, saida = cls.e.rodada()
        assert codigo == 0, saida
        cls.m = cls.e.mapa()
        cls.fatos = json.loads((cls.e.pasta / "4-dados" / "rodadas" / REF / "contas.json").read_text(encoding="utf-8"))
        cls.resumo = cls.e.resumo()

    @classmethod
    def tearDownClass(cls):
        cls.e.fechar()

    def test_mensal_nao_tem_data_de_decisao(self):
        mensal = self.fatos[self.m["Cliente Fictício Mensal"]]
        self.assertEqual(mensal["contrato"], "mensal")
        self.assertIsNone(mensal["dias_ate_renovar"])
        codigos = [s["codigo"] for s in mensal["sinais"]]
        self.assertFalse([c for c in codigos if c.startswith("renovacao")])
        self.assertNotIn(self.m["Cliente Fictício Mensal"], [x["conta"] for x in self.resumo["renovacoes"]])

    def test_anual_e_sem_tipo_seguem_com_renovacao(self):
        for nome in ("Cliente Fictício Anual", "Cliente Fictício Sem Tipo"):
            self.assertEqual(self.fatos[self.m[nome]]["dias_ate_renovar"], 30, nome)
            self.assertIn(self.m[nome], [x["conta"] for x in self.resumo["renovacoes"]])

    def test_carteira_separa_o_mensal(self):
        saida = rodar("carteira", "--pasta", self.e.pasta)[1]
        self.assertIn("Contrato mensal com sinal de insatisfação", saida)
        self.assertIn("sinal em 1 de 1 rodada", saida)

    def test_reuniao_explica_o_mensal(self):
        saida = rodar("reuniao", "--pasta", self.e.pasta, "--conta", self.m["Cliente Fictício Mensal"], "--tipo", "renovacao", "--data", REF)[1]
        self.assertIn("Contrato mensal", saida)
        self.assertIn("acumula por meses", saida)

    def test_nao_cobra_data_de_renovacao_de_quem_e_so_mensal(self):
        e = Empresa("minima")
        try:
            base = e.pasta / "4-dados"
            for outro in e.entrada.iterdir():
                outro.unlink()
            escrever(e.entrada / "contas.csv", [["ID", "Cliente", "MRR", "Status", "Uso", "Uso ant"], ["M2", "Cliente Fictício Dois", 500, "Ativo", 10, 10]])
            colunas = (self.e.pasta / "4-dados" / "colunas.md").read_text(encoding="utf-8")
            (base / "colunas.md").write_text(colunas.replace("| contas.csv | Renovação | renovacao |\n", "").replace("| contas.csv | Contrato | contrato |\n", ""), encoding="utf-8")
            como_medir = (self.e.pasta / "4-dados" / "como-medir.md").read_text(encoding="utf-8")
            (base / "como-medir.md").write_text(como_medir + "\n## Regras\n\n| regra | valor |\n| --- | --- |\n| contrato padrão | mensal |\n", encoding="utf-8")
            codigo, saida = e.rodada()
            self.assertEqual(codigo, 0, saida)
            faltas = [x["o_que_falta"] for x in e.resumo()["falta_medir"]]
            self.assertNotIn("Data de renovação", faltas)
            self.assertNotIn("Tipo de contrato", faltas)
        finally:
            e.fechar()


if __name__ == "__main__":
    unittest.main()
