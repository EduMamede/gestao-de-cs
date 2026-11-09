"""A apresentação em PowerPoint: sai da seção Slides da reunião e leva os nomes reais, só em com-nomes/.

A composição: capa e fechamento na cor de destaque, miolo escuro, frase grande em cada slide,
um único slide na cor de detalhe. Os gráficos são nativos, para a pessoa editar no PowerPoint.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re
from copy import deepcopy
from pathlib import Path

from . import ErroDeUso
from .contas import carregar_fatos, serie_da_rotina
from .pasta import ler_marcador
from .planilha import carregar_tema
from .privacidade import Cofre
from .relatorios import numero

MAX_LINHAS_POR_SLIDE = 6
MAX_LETRAS_POR_SLIDE = 420
MAX_LINHAS_COM_VISUAL = 3
MAX_LETRAS_COM_VISUAL = 180
MAX_VISUAIS_POR_SLIDE = 2
MAX_LETRAS_DA_FRASE = 140
MAX_LETRAS_POR_LINHA = 200

# em polegadas, num slide de 13,333 por 7,5
LARGURA_SLIDE, ALTURA_SLIDE = 13.333, 7.5
MARGEM = 0.8
LARGURA = LARGURA_SLIDE - 2 * MARGEM
TOPO = 1.15
ALTURA = 5.3
VAO = 0.3
COLUNA_DE_TEXTO = 3.8
FAIXA_DE_TEXTO = 1.2
ALTURA_DA_LEGENDA = 0.5
ALTURA_DO_NUMERO_GRANDE = 1.05

NUMERO_NO_TEXTO = re.compile(r"(?:R\$\s?)?\d+(?:[.,]\d+)*(?:\s?%)?")


def _ler_slides(texto: str) -> tuple:
    achado = re.search(r"^##\s*Slides\s*$(.*?)(?=^##\s|\Z)", texto, re.M | re.S)
    if not achado:
        raise ErroDeUso("este arquivo não tem a seção '## Slides'.")
    corpo = achado.group(1)
    capa = re.search(r"^Capa:\s*(.+)$", corpo, re.M)
    cliente = re.search(r"^Cliente:\s*(.+)$", corpo, re.M)
    slides = []
    for titulo, conteudo in re.findall(r"^###\s*(.+?)\s*$(.*?)(?=^###\s|\Z)", corpo, re.M | re.S):
        linhas = [m.strip() for m in re.findall(r"^\s*-\s+(.+)$", conteudo, re.M)]
        visuais = [("print" if tipo.lower() == "print" else "grafico", texto_visual.strip()) for tipo, texto_visual in re.findall(r"^(Gr[aá]fico|Print):[ \t]*(.*)$", conteudo, re.M | re.I)]
        slides.append((titulo, linhas, visuais))
    if not slides:
        raise ErroDeUso("a seção '## Slides' não tem nenhum slide.")
    return (capa.group(1).strip() if capa else "Revisão de resultados"), (cliente.group(1).strip() if cliente else ""), slides


def _conferir_slides(slides: list) -> None:
    for titulo, linhas, visuais in slides:
        if any("{{" in l for l in linhas + [texto for _, texto in visuais]) or not (linhas or visuais):
            raise ErroDeUso(f"o slide '{titulo}' ainda tem campo sem preencher. Sem número, a apresentação não sai.")
        if visuais and (len(linhas) > MAX_LINHAS_COM_VISUAL or sum(len(l) for l in linhas) > MAX_LETRAS_COM_VISUAL):
            raise ErroDeUso(f"o slide '{titulo}' tem texto demais ao lado do gráfico ou print. Use até {MAX_LINHAS_COM_VISUAL} linhas curtas.")
        if linhas and len(linhas[0]) > MAX_LETRAS_DA_FRASE:
            raise ErroDeUso(f"o slide '{titulo}' tem texto demais na primeira linha, que vira a frase grande. Use até {MAX_LETRAS_DA_FRASE} letras.")
        if any(len(l) > MAX_LETRAS_POR_LINHA for l in linhas):
            raise ErroDeUso(f"o slide '{titulo}' tem texto demais numa linha. Use até {MAX_LETRAS_POR_LINHA} letras por linha.")


def _blocos_de_texto(linhas: list) -> list:
    blocos, atual, letras = [], [], 0
    for linha in linhas:
        if atual and (len(atual) >= MAX_LINHAS_POR_SLIDE or letras + len(linha) > MAX_LETRAS_POR_SLIDE):
            blocos.append(atual)
            atual, letras = [], 0
        atual.append(linha)
        letras += len(linha)
    return blocos + [atual] if atual else blocos


def paginas(slides: list) -> list:
    """Cada passo vira um ou mais slides: mais números, mais slides. Gráfico fica com gráfico e print com print, de 2 em 2."""
    saida = []
    for passo, (titulo, linhas, visuais) in enumerate(slides, 1):
        grupos = []
        for visual in visuais:
            if grupos and grupos[-1][0][0] == visual[0] and len(grupos[-1]) < MAX_VISUAIS_POR_SLIDE:
                grupos[-1].append(visual)
            else:
                grupos.append([visual])
        blocos = [(linhas, grupos[0])] + [([], grupo) for grupo in grupos[1:]] if grupos else [(bloco, []) for bloco in _blocos_de_texto(linhas)]
        for i, (texto, grupo) in enumerate(blocos):
            saida.append({"passo": passo, "titulo": titulo, "continuacao": i > 0, "linhas": texto, "visuais": grupo})
    return saida


def _dados_dos_graficos(pasta: Path, texto: str, codigo: str, slides: list) -> dict:
    """A série de cada gráfico pedido, da rodada em que a reunião foi preparada. Só rotina vira gráfico: nota e chance não passam."""
    pedidos = [(titulo, nome) for titulo, _, visuais in slides for tipo, nome in visuais if tipo == "grafico" and nome]
    if not pedidos:
        return {}
    achado = re.search(r"^Dados da rodada de (\d{4}-\d{2}-\d{2})\.", texto, re.M)
    caminho = pasta / "4-dados" / "rodadas" / achado.group(1) / "contas.json" if achado else None
    if caminho and caminho.exists():
        data, fatos = dt.date.fromisoformat(achado.group(1)), json.loads(caminho.read_text(encoding="utf-8"))
    else:
        data, _, fatos = carregar_fatos(pasta)
    item = fatos.get(codigo)
    if item is None:
        raise ErroDeUso(f"não achei a conta {codigo} na rodada de {data.isoformat()} para montar os gráficos.")
    rotinas = {r["rotina"].casefold(): r for r in item["rotinas"]}
    series = {}
    for titulo, nome in pedidos:
        rotina = rotinas.get(nome.casefold())
        if rotina is None:
            raise ErroDeUso(f"o slide '{titulo}' pede o gráfico '{nome}', mas não há rotina com esse nome. Use um nome da tabela 'As rotinas'.")
        series[nome] = serie_da_rotina(pasta, data, codigo, rotina)
    return series


def trechos(texto: str) -> list:
    """Os pedaços do texto e se cada um vai em destaque. **Assim** marca à mão; sem marca, os números se destacam sozinhos."""
    if "**" in texto:
        return [(pedaco, i % 2 == 1) for i, pedaco in enumerate(texto.split("**")) if pedaco]
    saida, posicao = [], 0
    for achado in NUMERO_NO_TEXTO.finditer(texto):
        if achado.start() > posicao:
            saida.append((texto[posicao : achado.start()], False))
        saida.append((achado.group(0), True))
        posicao = achado.end()
    if posicao < len(texto):
        saida.append((texto[posicao:], False))
    return saida


def modo_do_slide(indice: int, total: int, visuais: list) -> str:
    """O último fecha na cor de destaque e o penúltimo é o único na cor de detalhe. Gráfico e print pedem o fundo escuro."""
    if visuais or total < 3:
        return "escuro"
    if indice == total - 1:
        return "destaque"
    if indice == total - 2:
        return "detalhe"
    return "escuro"


def caixas(visuais: int, tem_texto: bool) -> tuple:
    """Onde ficam o texto e cada gráfico ou print: x, y, largura, altura."""
    if not visuais:
        return (MARGEM, TOPO, LARGURA, ALTURA), []
    if visuais == 1:
        if tem_texto:
            return (MARGEM, TOPO, COLUNA_DE_TEXTO, ALTURA), [(MARGEM + COLUNA_DE_TEXTO + VAO, TOPO, LARGURA - COLUNA_DE_TEXTO - VAO, ALTURA)]
        return None, [(MARGEM, TOPO, LARGURA, ALTURA)]
    metade = (LARGURA - VAO) / 2
    inicio = TOPO + FAIXA_DE_TEXTO if tem_texto else TOPO
    resto = TOPO + ALTURA - inicio
    return ((MARGEM, TOPO, LARGURA, FAIXA_DE_TEXTO - 0.1) if tem_texto else None), [(MARGEM, inicio, metade, resto), (MARGEM + metade + VAO, inicio, metade, resto)]


def _tamanhos(visuais: int, linhas: list) -> tuple:
    """Tamanho da frase grande e das outras linhas. Frase longa fica menor, para caber."""
    letras = len(linhas[0])
    if not visuais:
        return (44 if letras <= 60 else 36), 22
    if visuais == 1:
        return (28 if letras <= 50 else 22 if letras <= 100 else 20), 18
    return (26 if letras <= 60 else 20), 16


class Montagem:
    def __init__(self, pasta: Path):
        from pptx import Presentation
        from pptx.dml.color import RGBColor
        from pptx.util import Inches

        self.tema = carregar_tema(pasta)
        self.cofre = Cofre(pasta)
        self.cor = {nome: RGBColor.from_string(self.tema[nome].lstrip("#")) for nome in ("fundo_cabecalho", "texto_cabecalho", "destaque", "detalhe", "subtitulo", "texto_suave", "borda")}
        self.deck = Presentation()
        # o modelo da biblioteca traz o nome de quem o fez, e esse arquivo vai para o cliente
        self.deck.core_properties.author = self.deck.core_properties.last_modified_by = ""
        self.deck.slide_width, self.deck.slide_height = Inches(LARGURA_SLIDE), Inches(ALTURA_SLIDE)
        self.branco = self.deck.slide_layouts[6]
        self.modelo_imagem = self._preparar_modelo()

    def paleta(self, modo: str) -> dict:
        cor = self.cor
        if modo == "escuro":
            return {"fundo": None, "texto": cor["texto_cabecalho"], "apoio": cor["borda"], "realce": cor["destaque"], "rotulo": cor["destaque"], "selo": cor["detalhe"], "selo_texto": cor["fundo_cabecalho"], "linha": cor["texto_suave"]}
        fundo = cor[modo]
        preto = cor["fundo_cabecalho"]
        return {"fundo": fundo, "texto": preto, "apoio": preto, "realce": preto, "rotulo": preto, "selo": preto, "selo_texto": fundo, "linha": preto}

    def _preparar_modelo(self):
        """Fundo escuro em todo o arquivo, para o destaque aparecer, e o modelo de slide com o espaço para imagem."""
        from pptx.dml.color import RGBColor
        from pptx.enum.shapes import PP_PLACEHOLDER
        from pptx.oxml import parse_xml
        from pptx.oxml.ns import nsdecls, qn
        from pptx.util import Inches

        mestre = self.deck.slide_master
        mestre.background.fill.solid()
        mestre.background.fill.fore_color.rgb = self.cor["fundo_cabecalho"]
        # o texto novo que a pessoa escrever nasce claro, não preto no preto
        mapa = mestre.element.find(qn("p:clrMap"))
        for par in ("1", "2"):
            mapa.set(f"bg{par}", f"dk{par}")
            mapa.set(f"tx{par}", f"lt{par}")

        modelo = next(m for m in self.deck.slide_layouts if any(p.placeholder_format.type == PP_PLACEHOLDER.PICTURE for p in m.placeholders))
        modelo.name = "Print ou gráfico"
        primeiro = None
        for marcador in list(modelo.placeholders):
            tipo = marcador.placeholder_format.type
            if tipo == PP_PLACEHOLDER.PICTURE:
                primeiro = marcador
            elif tipo in (PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.BODY):
                marcador._element.getparent().remove(marcador._element)
        # só preenchimento, sem contorno: o contorno passaria para a imagem colada, e o preenchimento fica atrás dela
        primeiro.fill.solid()
        primeiro.fill.fore_color.rgb = RGBColor.from_string(self.tema["subtitulo"].lstrip("#"))
        elemento = primeiro._element
        elemento.find(".//" + qn("p:ph")).set("hasCustomPrompt", "1")
        novo = parse_xml(
            f'<p:txBody {nsdecls("p", "a")}><a:bodyPr anchor="ctr"/><a:lstStyle><a:lvl1pPr marL="0" indent="0" algn="ctr"><a:buNone/><a:defRPr sz="1800">'
            f'<a:solidFill><a:srgbClr val="{self.tema["borda"].lstrip("#")}"/></a:solidFill></a:defRPr></a:lvl1pPr></a:lstStyle>'
            '<a:p><a:r><a:rPr lang="pt-BR"/><a:t>Clique no ícone para colocar o print ou o gráfico</a:t></a:r></a:p></p:txBody>'
        )
        elemento.replace(elemento.find(qn("p:txBody")), novo)
        segundo = deepcopy(elemento)
        segundo.find(".//" + qn("p:ph")).set("idx", "13")
        identificacao = segundo.find(".//" + qn("p:cNvPr"))
        identificacao.set("id", str(max(int(e.get("id")) for e in modelo.shapes._spTree.iter(qn("p:cNvPr"))) + 1))
        identificacao.set("name", "Segundo print ou gráfico")
        elemento.addnext(segundo)
        # no modelo original, a posição é a de um slide mais estreito. Cada slide ajusta a sua depois
        espacos = [m for m in modelo.placeholders if m.placeholder_format.type == PP_PLACEHOLDER.PICTURE]
        for marcador, (x, y, largura, altura) in zip(espacos, caixas(2, False)[1]):
            marcador.left, marcador.top, marcador.width, marcador.height = Inches(x), Inches(y), Inches(largura), Inches(altura)
        return modelo

    def retangulo(self, slide, x, y, largura, altura, preenchimento):
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.util import Inches

        forma = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(largura), Inches(altura))
        forma.fill.solid()
        forma.fill.fore_color.rgb = preenchimento
        forma.line.fill.background()
        forma.shadow.inherit = False
        return forma

    def caixa_de_texto(self, slide, x, y, largura, altura, ancora=None):
        from pptx.util import Inches

        quadro = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(largura), Inches(altura)).text_frame
        quadro.word_wrap = True
        quadro.margin_left = quadro.margin_right = quadro.margin_top = quadro.margin_bottom = 0
        if ancora is not None:
            quadro.vertical_anchor = ancora
        return quadro

    def trecho(self, paragrafo, texto, tamanho, cor_texto, negrito=False):
        from pptx.util import Pt

        pedaco = paragrafo.add_run()
        pedaco.text = texto
        pedaco.font.name, pedaco.font.size, pedaco.font.bold = self.tema["fonte"], Pt(tamanho), negrito
        pedaco.font.color.rgb = cor_texto
        return pedaco

    def escrever(self, slide, x, y, largura, altura, texto, tamanho, cor_texto, negrito=False, ancora=None):
        quadro = self.caixa_de_texto(slide, x, y, largura, altura, ancora)
        self.trecho(quadro.paragraphs[0], texto, tamanho, cor_texto, negrito)
        return quadro

    def novo_slide(self, modelo, paleta: dict):
        slide = self.deck.slides.add_slide(modelo)
        if paleta["fundo"] is not None:
            slide.background.fill.solid()
            slide.background.fill.fore_color.rgb = paleta["fundo"]
        return slide

    def moldura(self, slide, paleta: dict, rotulo: str, empresa: str, data: str) -> None:
        """O que se repete em todo slide: o rótulo no alto, o número da página e o rodapé."""
        from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
        from pptx.oxml import parse_xml
        from pptx.oxml.ns import nsdecls

        if rotulo:
            pedaco = self.trecho(self.caixa_de_texto(slide, MARGEM, 0.5, LARGURA - 1, 0.35, MSO_ANCHOR.MIDDLE).paragraphs[0], rotulo.upper(), 13, paleta["rotulo"], negrito=True)
            pedaco.font._element.set("spc", "150")

        # campo de número de página: se a pessoa apagar um slide, os outros se ajustam sozinhos
        selo = self.retangulo(slide, LARGURA_SLIDE - MARGEM - 0.55, 0.5, 0.55, 0.35, paleta["selo"])
        quadro = selo.text_frame
        quadro.margin_left = quadro.margin_right = quadro.margin_top = quadro.margin_bottom = 0
        quadro.vertical_anchor = MSO_ANCHOR.MIDDLE
        paragrafo = quadro.paragraphs[0]
        paragrafo.alignment = PP_ALIGN.CENTER
        pagina = len(self.deck.slides)
        paragrafo._p.append(
            parse_xml(
                f'<a:fld {nsdecls("a")} id="{{B6F15528-21DE-4FAA-801E-634DDDAF4B2B}}" type="slidenum"><a:rPr lang="pt-BR" sz="1300" b="1">'
                f'<a:solidFill><a:srgbClr val="{paleta["selo_texto"]}"/></a:solidFill><a:latin typeface="{self.tema["fonte"]}"/></a:rPr><a:t>{pagina}</a:t></a:fld>'
            )
        )

        self.retangulo(slide, MARGEM, 6.62, LARGURA, 0.01, paleta["linha"])
        rodape = self.caixa_de_texto(slide, MARGEM, 6.72, LARGURA, 0.3)
        if empresa:
            self.trecho(rodape.paragraphs[0], empresa, 12, paleta["texto"], negrito=True)
        if data:
            self.trecho(rodape.paragraphs[0], f"   {data}" if empresa else data, 12, paleta["apoio"])

    def capa(self, titulo: str, cliente: str, empresa: str, data: str) -> None:
        from pptx.enum.text import MSO_ANCHOR
        from pptx.util import Pt

        paleta = self.paleta("destaque")
        slide = self.novo_slide(self.branco, paleta)
        self.moldura(slide, paleta, data, empresa, "")
        quadro = self.escrever(slide, MARGEM, 1.3, LARGURA, 2.75, titulo, 66 if len(titulo) <= 30 else 54, paleta["texto"], negrito=True, ancora=MSO_ANCHOR.BOTTOM)
        quadro.paragraphs[0].line_spacing = 0.95
        if not cliente:
            return
        # o nome do cliente num bloco escuro. A largura é uma estimativa, porque aqui não há como medir o texto
        tamanho, folga = 28, 0.55
        estimada = sum(0.66 if letra.isupper() else 0.47 for letra in cliente) * tamanho / 72 + folga
        linhas = math.ceil(estimada / LARGURA)
        caixa = self.caixa_de_texto(slide, MARGEM, 4.3, min(estimada, LARGURA), 0.72 * linhas, MSO_ANCHOR.MIDDLE)
        forma = slide.shapes[-1]
        forma.fill.solid()
        forma.fill.fore_color.rgb = self.cor["fundo_cabecalho"]
        caixa.margin_left = caixa.margin_right = Pt(16)
        self.trecho(caixa.paragraphs[0], cliente, tamanho, self.cor["destaque"], negrito=True)

    def linha_em_trechos(self, paragrafo, linha: str, tamanho: int, paleta: dict, base, negrito=False, marcado=None) -> None:
        """Escreve a linha com seus destaques. `marcado` é a cor do que veio em **assim**; os números automáticos ficam sempre no realce."""
        cor_do_destaque = marcado if marcado is not None and "**" in linha else paleta["realce"]
        for pedaco, destaque in trechos(self.cofre.restaurar(linha)):
            self.trecho(paragrafo, pedaco, tamanho, cor_do_destaque if destaque else base, negrito or destaque)

    def fileira(self, slide, y, altura, paleta: dict, ordem=None, com_fio=True):
        """Uma linha da lista, com o número em destaque se tiver ordem e um fio embaixo. Devolve o parágrafo para escrever."""
        from pptx.enum.text import MSO_ANCHOR

        coluna = 0.85 if ordem else 0
        if ordem:
            self.escrever(slide, MARGEM, y, coluna, altura, str(ordem), 34 if altura >= 0.8 else 24, paleta["realce"], negrito=True, ancora=MSO_ANCHOR.MIDDLE)
        quadro = self.caixa_de_texto(slide, MARGEM + coluna, y, LARGURA - coluna, altura, MSO_ANCHOR.MIDDLE)
        if com_fio:
            self.retangulo(slide, MARGEM, y + altura, LARGURA, 0.01, paleta["linha"])
        return quadro.paragraphs[0]

    def roteiro(self, slides: list, empresa: str, data: str) -> None:
        """O resumo da conversa, com a primeira linha de cada passo. Sai sozinho do que foi escrito nos passos."""
        paleta = self.paleta("escuro")
        slide = self.novo_slide(self.branco, paleta)
        self.moldura(slide, paleta, "Resumo", empresa, data)
        quadro = self.caixa_de_texto(slide, MARGEM, TOPO, LARGURA, 0.85)
        self.trecho(quadro.paragraphs[0], "Nossa conversa em ", 40, paleta["texto"], negrito=True)
        self.trecho(quadro.paragraphs[0], f"{len(slides)} passos", 40, paleta["realce"], negrito=True)
        inicio = 2.2
        altura = min(1.05, (TOPO + ALTURA - inicio) / len(slides))
        maior = max(len(titulo) + (len(linhas[0]) if linhas else 0) for titulo, linhas, _ in slides)
        tamanho = 22 if len(slides) <= 4 and maior <= 130 else 18 if len(slides) <= 5 else 16
        for i, (titulo, linhas, _) in enumerate(slides):
            paragrafo = self.fileira(slide, inicio + i * altura, altura, paleta, ordem=i + 1, com_fio=i < len(slides) - 1)
            nome = self.cofre.restaurar(titulo)
            self.trecho(paragrafo, (nome if nome[-1] in ".?!" else f"{nome}.") + " ", tamanho, paleta["texto"], negrito=True)
            if linhas:
                self.linha_em_trechos(paragrafo, linhas[0], tamanho, paleta, paleta["apoio"])

    def frase_e_fileiras(self, slide, linhas: list, paleta: dict) -> None:
        """Slide só de texto com várias linhas: a frase grande e as outras em lista, no meio do slide."""
        frase, resto = linhas[0], linhas[1:]
        tamanho, vao = (40 if len(frase) <= 60 else 30), 0.3
        alto_da_frase = math.ceil(len(frase) * tamanho * 0.52 / 72 / LARGURA) * tamanho * 1.2 / 72
        altura = min(0.95, (ALTURA - alto_da_frase - vao) / len(resto))
        y = TOPO + (ALTURA - alto_da_frase - vao - altura * len(resto)) / 2
        quadro = self.caixa_de_texto(slide, MARGEM, y, LARGURA, alto_da_frase)
        quadro.paragraphs[0].line_spacing = 0.95
        self.linha_em_trechos(quadro.paragraphs[0], frase, tamanho, paleta, paleta["texto"], negrito=True)
        for i, linha in enumerate(resto):
            paragrafo = self.fileira(slide, y + alto_da_frase + vao + i * altura, altura, paleta, com_fio=i < len(resto) - 1)
            self.linha_em_trechos(paragrafo, linha, 22 if len(resto) <= 3 else 20, paleta, paleta["apoio"], marcado=paleta["texto"])

    def texto(self, slide, caixa: tuple, linhas: list, visuais: int, paleta: dict) -> None:
        """A primeira linha é a frase grande. As outras ficam menores, abaixo dela."""
        from pptx.enum.text import MSO_ANCHOR
        from pptx.util import Pt

        if not visuais and len(linhas) > 1:
            self.frase_e_fileiras(slide, linhas, paleta)
            return
        x, y, largura, altura = caixa
        quadro = self.caixa_de_texto(slide, x, y, largura, altura, MSO_ANCHOR.MIDDLE if not visuais else MSO_ANCHOR.TOP)
        grande, menor = _tamanhos(visuais, linhas)
        for i, linha in enumerate(linhas):
            paragrafo = quadro.paragraphs[0] if i == 0 else quadro.add_paragraph()
            if i == 0:
                paragrafo.line_spacing = 0.95
            paragrafo.space_after = Pt((18 if i == 0 else 8) if visuais < 2 else 4)
            if i == 0:
                self.linha_em_trechos(paragrafo, linha, grande, paleta, paleta["texto"], negrito=True)
            else:
                self.linha_em_trechos(paragrafo, linha, menor, paleta, paleta["apoio"], marcado=paleta["texto"])

    def grafico(self, slide, caixa: tuple, nome: str, pontos: list) -> None:
        """O nome da rotina, a evolução em número grande e as barras: a última em destaque e as anteriores em cinza."""
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_TICK_LABEL_POSITION, XL_TICK_MARK
        from pptx.oxml import parse_xml
        from pptx.oxml.ns import nsdecls, qn
        from pptx.util import Inches, Pt

        cor = self.cor
        x, y, largura, altura = caixa
        self.escrever(slide, x, y, largura, 0.35, nome, 16, cor["texto_cabecalho"], negrito=True)
        self.escrever(slide, x, y + 0.33, largura, 0.7, f"de {numero(pontos[0][1])} para {numero(pontos[-1][1])}", 36, cor["destaque"], negrito=True)
        dados = CategoryChartData()
        dados.categories = [rotulo for rotulo, _ in pontos]
        dados.add_series(nome, [valor for _, valor in pontos])
        quadro = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(x), Inches(y + ALTURA_DO_NUMERO_GRANDE), Inches(largura), Inches(altura - ALTURA_DO_NUMERO_GRANDE), dados)
        leitura = "; ".join(f"{rotulo}: {numero(valor)}" for rotulo, valor in pontos)
        quadro._element._nvXxPr.cNvPr.set("descr", f"Gráfico de barras de {nome}. {leitura}")
        grafico = quadro.chart
        espaco = grafico._chartSpace
        sem_fundo = f'<c:spPr {nsdecls("c", "a")}><a:noFill/><a:ln><a:noFill/></a:ln></c:spPr>'
        espaco.find(qn("c:chart")).addnext(parse_xml(sem_fundo))
        espaco.find(".//" + qn("c:plotArea")).append(parse_xml(sem_fundo))
        grafico.has_legend = False
        grafico.has_title = False
        grafico.font.name, grafico.font.size = self.tema["fonte"], Pt(14)
        grafico.font.color.rgb = cor["borda"]

        plot = grafico.plots[0]
        plot.vary_by_categories = False
        plot.gap_width = 300 if len(pontos) <= 3 else 90
        serie = plot.series[0]
        serie.invert_if_negative = False
        serie.format.fill.solid()
        serie.format.fill.fore_color.rgb = cor["texto_suave"]
        ultimo = len(pontos) - 1
        serie.points[ultimo].format.fill.solid()
        serie.points[ultimo].format.fill.fore_color.rgb = cor["destaque"]
        serie.data_labels.show_value = False
        # valor só na primeira e na última barra, que contam a evolução. O eixo mostra o resto
        for indice in {0, ultimo}:
            rotulo_valor = serie.points[indice].data_label
            rotulo_valor.position = XL_LABEL_POSITION.OUTSIDE_END
            rotulo_valor.font.name, rotulo_valor.font.size, rotulo_valor.font.bold = self.tema["fonte"], Pt(16), True
            rotulo_valor.font.color.rgb = cor["texto_cabecalho"]

        eixo_x, eixo_y = grafico.category_axis, grafico.value_axis
        eixo_x.has_major_gridlines = False
        eixo_x.major_tick_mark = XL_TICK_MARK.NONE
        eixo_x.format.line.color.rgb = cor["texto_suave"]
        if min(valor for _, valor in pontos) >= 0:
            eixo_y.minimum_scale = 0  # barra que não começa no zero engana
        eixo_y.major_tick_mark = XL_TICK_MARK.NONE
        eixo_y.format.line.fill.background()
        if len(pontos) <= 2:  # as duas barras já têm o valor escrito
            eixo_y.has_major_gridlines = False
            eixo_y.tick_label_position = XL_TICK_LABEL_POSITION.NONE
        else:
            eixo_y.has_major_gridlines = True
            eixo_y.major_gridlines.format.line.color.rgb = cor["subtitulo"]
            eixo_y.major_gridlines.format.line.width = Pt(0.75)

    def slide(self, pagina: dict, series: dict, modo: str, empresa: str, data: str, com_passos: bool) -> list:
        """Monta um slide e devolve o que a pessoa ainda precisa colar nele."""
        from pptx.util import Inches

        titulo, linhas, visuais = pagina["titulo"], pagina["linhas"], pagina["visuais"]
        rotulo = self.cofre.restaurar(titulo)
        if com_passos:
            rotulo = f"Passo {pagina['passo']} · {rotulo}"
        if pagina["continuacao"]:
            rotulo += " · continuação"
        com_grafico = [(tipo, nome) for tipo, nome in visuais if tipo == "grafico" and len(series.get(nome, [])) >= 2]
        vazios = len(visuais) - len(com_grafico)
        paleta = self.paleta(modo)
        slide = self.novo_slide(self.modelo_imagem if vazios else self.branco, paleta)
        marcadores = list(slide.placeholders)
        for sobra in marcadores[vazios:]:
            sobra._element.getparent().remove(sobra._element)
        marcadores = marcadores[:vazios]
        self.moldura(slide, paleta, rotulo, empresa, data)

        caixa_do_texto, caixas_visuais = caixas(len(visuais), bool(linhas))
        if linhas:
            self.texto(slide, caixa_do_texto, linhas, len(visuais), paleta)

        pendencias = []
        # se um espaço tem legenda, os dois do slide ficam da mesma altura
        com_legenda = any(nome for tipo, nome in visuais if (tipo, nome) not in com_grafico)
        for (tipo, nome), caixa_visual in zip(visuais, caixas_visuais):
            if (tipo, nome) in com_grafico:
                self.grafico(slide, caixa_visual, self.cofre.restaurar(nome), series[nome])
                continue
            x, y, largura, altura = caixa_visual
            marcador = marcadores.pop(0)
            if com_legenda:
                altura -= ALTURA_DA_LEGENDA
            if nome:
                self.escrever(slide, x, y + altura + 0.1, largura, ALTURA_DA_LEGENDA - 0.1, self.cofre.restaurar(nome), 14, paleta["apoio"])
            marcador.left, marcador.top, marcador.width, marcador.height = Inches(x), Inches(y), Inches(largura), Inches(altura)
            if tipo == "print":
                pendencias.append(f"slide '{titulo}': colar o print" + (f" ({nome})" if nome else ""))
            elif nome:
                pendencias.append(f"slide '{titulo}': '{nome}' ainda não tem duas medições. Cole o gráfico do sistema ou gere de novo depois da próxima rodada")
            else:
                pendencias.append(f"slide '{titulo}': colar o gráfico")
        return pendencias


def gerar_apresentacao(pasta: Path, origem: Path) -> tuple:
    """Grava o PowerPoint. Devolve onde ficou e o que falta colar, sem nome real, porque a IA lê essa lista."""
    texto = origem.read_text(encoding="utf-8")
    capa, cliente, slides = _ler_slides(texto)
    _conferir_slides(slides)
    try:
        import pptx  # noqa: F401
    except ImportError as erro:
        raise ErroDeUso("falta a biblioteca de PowerPoint. Rode: python -m pip install python-pptx. O roteiro em texto continua valendo.") from erro

    series = _dados_dos_graficos(pasta, texto, origem.parent.parent.name, slides)
    montagem = Montagem(pasta)
    titulo = montagem.cofre.restaurar(capa)
    montagem.deck.core_properties.title = titulo
    empresa = ler_marcador(pasta).get("empresa", "")
    achada = re.match(r"\d{4}-\d{2}-\d{2}", origem.name)
    data = dt.date.fromisoformat(achada.group(0)).strftime("%d/%m/%Y") if achada else ""
    montagem.capa(titulo, montagem.cofre.restaurar(cliente), empresa, data)
    com_passos = len(slides) >= 2
    if com_passos:
        montagem.roteiro(slides, empresa, data)
    pendencias = []
    lista = paginas(slides)
    for indice, pagina in enumerate(lista):
        pendencias += montagem.slide(pagina, series, modo_do_slide(indice, len(lista), pagina["visuais"]), empresa, data, com_passos)
    destino = pasta / "com-nomes" / f"{origem.parent.parent.name}-{origem.stem}.pptx"
    destino.parent.mkdir(exist_ok=True)
    montagem.deck.save(str(destino))
    return destino, pendencias
