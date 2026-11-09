"""Monta a planilha da rodada. É o único arquivo com nomes reais em toda rodada.

Cada fórmula é gravada junto com o valor já calculado (xlsxwriter permite), para a planilha
fazer sentido mesmo antes de o Excel recalcular. As cores vêm de modelos/tema.json.
"""

from __future__ import annotations

import json
from pathlib import Path

from .medir import NOME_FAIXAS, FAIXA_VERDE, FAIXA_VERMELHA, arredondar, quem_age
from .pasta import raiz_plugin

ABA_NOTA = "Health score"
LINHA_PARAM, LINHA_PESOS, LINHA_CAB, PRIMEIRA = 2, 3, 4, 5
COLS_FIXAS = [
    ("Última verificação", 13), ("Aviso", 44), ("ID", 11), ("Cliente", 30), ("Nota", 7), ("Faixa", 15),
    ("Cobertura", 10), ("Confiança", 10), ("Segmento", 16), ("Responsável", 16), ("Valor", 13), ("Renovação", 12),
]
COLS_EMPACA = [("Etapa atual", 18), ("Dias na etapa", 9), ("Prazo da etapa", 9), ("Situação", 12), ("Motivo", 12), ("Próximo passo", 28), ("Data do próximo contato", 13)]


def carregar_tema(pasta: Path) -> dict:
    tema = json.loads((raiz_plugin() / "modelos" / "tema.json").read_text(encoding="utf-8"))
    proprio = pasta / "4-dados" / "tema.json"
    if proprio.exists():
        tema.update(json.loads(proprio.read_text(encoding="utf-8")))
    return tema


def _coluna(indice: int) -> str:
    nome = ""
    indice += 1
    while indice:
        indice, resto = divmod(indice - 1, 26)
        nome = chr(65 + resto) + nome
    return nome


def _formatos(livro, tema: dict) -> dict:
    fonte = {"font_name": tema["fonte"], "font_size": 10}

    def novo(**extras):
        return livro.add_format({**fonte, **extras})

    borda = {"border": 1, "border_color": tema["borda"]}
    return {
        "titulo": novo(bold=True, font_size=16, font_color=tema["texto_cabecalho"], bg_color=tema["fundo_cabecalho"]),
        "faixa_titulo": novo(bg_color=tema["fundo_cabecalho"], font_color=tema["texto_suave"]),
        "sub": novo(font_color=tema["texto_suave"], italic=True),
        "cab": novo(bold=True, font_color=tema["texto_cabecalho"], bg_color=tema["subtitulo"], text_wrap=True, valign="vcenter", **borda),
        "cab_destaque": novo(bold=True, font_color=tema["fundo_cabecalho"], bg_color=tema["destaque"], text_wrap=True, valign="vcenter", **borda),
        "secao": novo(bold=True, font_size=12, font_color=tema["subtitulo"], bottom=2, bottom_color=tema["destaque"]),
        "texto": novo(valign="top", **borda),
        "quebra": novo(text_wrap=True, valign="top", **borda),
        "centro": novo(align="center", valign="top", **borda),
        "int": novo(num_format="0", align="center", valign="top", **borda),
        "num": novo(num_format="#,##0.0", valign="top", **borda),
        "moeda": novo(num_format='"R$" #,##0.00', valign="top", **borda),
        "pct": novo(num_format='0.0"%"', valign="top", **borda),
        "pct_frac": novo(num_format="0%", align="center", valign="top", **borda),
        "pct_int": novo(num_format='0"%"', align="center", valign="top", **borda),
        "data": novo(num_format="dd/mm/yyyy", align="center", valign="top", **borda),
        "editavel": novo(bg_color=tema["campo_editavel"], valign="top", text_wrap=True, **borda),
        "editavel_num": novo(bg_color=tema["campo_editavel"], align="center", bold=True, **borda),
        "editavel_data": novo(bg_color=tema["campo_editavel"], num_format="dd/mm/yyyy", align="center", valign="top", **borda),
        "a_preencher": novo(bg_color=tema["campo_editavel"], font_color=tema["texto_suave"], italic=True, valign="top", **borda),
        "simples": novo(text_wrap=True, valign="top"),
        "negrito": novo(bold=True, valign="top"),
        "verde": livro.add_format({"bg_color": tema["verde_fundo"], "font_color": tema["verde_texto"]}),
        "amarelo": livro.add_format({"bg_color": tema["amarelo_fundo"], "font_color": tema["amarelo_texto"]}),
        "vermelho": livro.add_format({"bg_color": tema["vermelho_fundo"], "font_color": tema["vermelho_texto"]}),
        "cinza": livro.add_format({"bg_color": tema["cinza_fundo"], "font_color": tema["cinza_texto"]}),
    }


def _titulo(aba, f, texto: str, sub: str, largura: int) -> None:
    aba.set_row(0, 26)
    aba.write(0, 0, texto, f["titulo"])
    for c in range(1, largura):
        aba.write_blank(0, c, None, f["faixa_titulo"])
    aba.write(1, 0, sub, f["sub"])


def _cabecalho(aba, f, linha: int, colunas: list, inicio: int = 0, destaque_de=None) -> None:
    aba.set_row(linha, 32)
    for i, (nome, largura) in enumerate(colunas):
        formato = f["cab_destaque"] if destaque_de is not None and i >= destaque_de else f["cab"]
        aba.write(linha, inicio + i, nome, formato)
        aba.set_column(inicio + i, inicio + i, largura)


def _ou_preencher(aba, f, linha, col, valor, formato="texto") -> None:
    if valor is None or valor == "":
        aba.write(linha, col, "a preencher", f["a_preencher"])
    elif formato == "data":
        aba.write_datetime(linha, col, _dt(valor), f["data"])
    else:
        aba.write(linha, col, valor, f[formato])


def _dt(data):
    import datetime as dt

    return dt.datetime(data.year, data.month, data.day)


def _semaforo(aba, f, intervalo: str) -> None:
    for texto, formato in ((NOME_FAIXAS["saudavel"], "verde"), (NOME_FAIXAS["pode_melhorar"], "amarelo"), (NOME_FAIXAS["possivel_churn"], "vermelho"), (NOME_FAIXAS["sem_nota"], "cinza")):
        aba.conditional_format(intervalo, {"type": "cell", "criteria": "==", "value": f'"{texto}"', "format": f[formato]})


def _aba_nota(livro, f, r, contas: list) -> dict:
    aba = livro.add_worksheet(ABA_NOTA)
    inds = r.cfg.indicadores
    n_ind = len(inds)
    c_sub = len(COLS_FIXAS)
    c_empaca = c_sub + n_ind
    colunas = list(COLS_FIXAS) + [(i.rotina, 11) for i in inds] + COLS_EMPACA
    _titulo(aba, f, "Health score", f"Rodada de {r.data.strftime('%d/%m/%Y')}. Mude os pesos na linha 4 e a nota recalcula. Campos claros são para preencher.", len(colunas))
    minimo = r.cfg.regras["cobertura minima"] / 100
    aba.write(LINHA_PARAM, 3, "Cobertura mínima para dar nota", f["negrito"])
    aba.write(LINHA_PARAM, 4, minimo, f["editavel_num"])
    aba.write(LINHA_PESOS, c_sub - 1, "Peso (editável)", f["negrito"])
    for i, ind in enumerate(inds):
        aba.write(LINHA_PESOS, c_sub + i, ind.peso, f["editavel_num"])
    _cabecalho(aba, f, LINHA_CAB, colunas, destaque_de=c_empaca)

    linhas_excel = {}
    for i, conta in enumerate(contas):
        l = PRIMEIRA + i
        n_linha = l + 1
        linhas_excel[conta.codigo] = n_linha
        aba.write_datetime(l, 0, _dt(r.data), f["data"])
        aba.write(l, 1, ". ".join(s[1] for s in conta.sinais), f["quebra"])
        aba.write(l, 2, conta.codigo, f["centro"])
        aba.write(l, 3, r.cofre.nome_conta(conta.codigo), f["texto"])
        if n_ind:
            pesos = f"${_coluna(c_sub)}${LINHA_PESOS + 1}:${_coluna(c_sub + n_ind - 1)}${LINHA_PESOS + 1}"
            subs = f"{_coluna(c_sub)}{n_linha}:{_coluna(c_sub + n_ind - 1)}{n_linha}"
            cob = f"G{n_linha}"
            aba.write_formula(l, 6, f"=SUMPRODUCT({pesos},--ISNUMBER({subs}))/SUM({pesos})", f["pct_frac"], conta.cobertura)
            aba.write_formula(
                l, 4,
                f'=IF(OR({cob}=0,{cob}<$E${LINHA_PARAM + 1}),"",ROUND(SUMPRODUCT({pesos},{subs})/SUMPRODUCT({pesos},--ISNUMBER({subs})),0))',
                f["int"], "" if conta.nota is None else conta.nota,
            )
        else:
            aba.write_blank(l, 4, None, f["int"])
            aba.write(l, 6, 0, f["pct_frac"])
        nota_ref = f"E{n_linha}"
        aba.write_formula(
            l, 5,
            f'=IF({nota_ref}="","{NOME_FAIXAS["sem_nota"]}",IF({nota_ref}<{FAIXA_VERMELHA},"{NOME_FAIXAS["possivel_churn"]}",IF({nota_ref}<{FAIXA_VERDE},"{NOME_FAIXAS["pode_melhorar"]}","{NOME_FAIXAS["saudavel"]}")))',
            f["centro"], NOME_FAIXAS[conta.faixa],
        )
        aba.write_formula(l, 7, f'=IF(G{n_linha}>=0.8,"alta",IF(G{n_linha}>=0.5,"média","baixa"))', f["centro"], conta.grau)
        _ou_preencher(aba, f, l, 8, conta.campos.get("segmento"))
        _ou_preencher(aba, f, l, 9, conta.campos.get("responsavel"))
        _ou_preencher(aba, f, l, 10, conta.receita, "moeda")
        if r.cfg.recompra:  # sem contrato, não há renovação para preencher
            aba.write_blank(l, 11, None, f["texto"])
        else:
            _ou_preencher(aba, f, l, 11, conta.campos.get("renovacao"), "data")
        for j, ind in enumerate(inds):
            sub = conta.subnotas.get(ind.id)
            if sub is None:
                aba.write_blank(l, c_sub + j, None, f["editavel"])
            else:
                aba.write_number(l, c_sub + j, sub, f["int"])
        e = c_empaca
        if r.cfg.recompra and not r.cfg.etapas:  # quem não usa etapas não precisa preencher isso
            aba.write_blank(l, e, None, f["texto"])
        else:
            _ou_preencher(aba, f, l, e, conta.etapa or conta.etapa_rotulo)
        if conta.dias_etapa is None:
            aba.write_blank(l, e + 1, None, f["editavel"])
        else:
            aba.write_number(l, e + 1, conta.dias_etapa, f["int"])
        if conta.prazo is None:
            aba.write_blank(l, e + 2, None, f["int"])
        else:
            aba.write_number(l, e + 2, conta.prazo, f["int"])
        etapa_ref, dias_ref, prazo_ref = f"{_coluna(e)}{n_linha}", f"{_coluna(e + 1)}{n_linha}", f"{_coluna(e + 2)}{n_linha}"
        situacao = conta.situacao if conta.etapa or conta.etapa_rotulo else "sem etapa"
        if situacao == "etapa sem ligação":
            aba.write(l, e + 3, situacao, f["centro"])
        else:
            aba.write_formula(
                l, e + 3,
                f'=IF(OR({etapa_ref}="a preencher",{etapa_ref}=""),"sem etapa",IF({prazo_ref}="","sem prazo",IF({dias_ref}="","sem data",IF({dias_ref}>{prazo_ref},"empacado","no prazo"))))',
                f["centro"], situacao,
            )
        if conta.motivo:
            aba.write(l, e + 4, conta.motivo, f["editavel"])
        else:
            aba.write_blank(l, e + 4, None, f["editavel"])
        aba.data_validation(l, e + 4, l, e + 4, {"validate": "list", "source": ["do cliente", "nosso"]})
        passo = conta.campos.get("proximo_passo")
        if passo:
            aba.write(l, e + 5, passo, f["editavel"])
        else:
            aba.write_blank(l, e + 5, None, f["editavel"])
        proximo = conta.campos.get("data_proximo_contato")
        if proximo:
            aba.write_datetime(l, e + 6, _dt(proximo), f["editavel_data"])
        else:
            aba.write_blank(l, e + 6, None, f["editavel_data"])

    ultima = PRIMEIRA + len(contas)
    if contas:
        _semaforo(aba, f, f"F{PRIMEIRA + 1}:F{ultima}")
        aba.conditional_format(f"{_coluna(c_empaca + 3)}{PRIMEIRA + 1}:{_coluna(c_empaca + 3)}{ultima}", {"type": "cell", "criteria": "==", "value": '"empacado"', "format": f["vermelho"]})
        aba.conditional_format(f"{_coluna(c_empaca + 3)}{PRIMEIRA + 1}:{_coluna(c_empaca + 3)}{ultima}", {"type": "cell", "criteria": "==", "value": '"no prazo"', "format": f["verde"]})
        aba.conditional_format(f"H{PRIMEIRA + 1}:H{ultima}", {"type": "cell", "criteria": "==", "value": '"baixa"', "format": f["amarelo"]})
        aba.autofilter(LINHA_CAB, 0, ultima - 1, len(colunas) - 1)
    aba.freeze_panes(PRIMEIRA, 4)
    return {"primeira": PRIMEIRA + 1, "ultima": ultima}


def _ref(intervalo: dict, coluna: str) -> str:
    return f"'{ABA_NOTA}'!${coluna}${intervalo['primeira']}:${coluna}${intervalo['ultima']}"


def _formatar_metrica(aba, f, linha, col, valor, unidade) -> None:
    if valor is None:
        aba.write(linha, col, "a preencher", f["a_preencher"])
        return
    aba.write(linha, col, valor, f[{"moeda": "moeda", "pct": "pct", "int": "int", "num": "num"}[unidade]])


def _aba_painel(livro, f, r, intervalo: dict):
    aba = livro.add_worksheet("Painel geral")
    _titulo(aba, f, "Painel geral do CS", f"Rodada de {r.data.strftime('%d/%m/%Y')}. O que estiver como 'a preencher' ainda não tem dado.", 6)
    aba.set_column(0, 0, 34)
    aba.set_column(1, 1, 16)
    aba.set_column(2, 2, 16)
    aba.set_column(3, 5, 16)
    linha = 3
    aba.write(linha, 0, "Saúde da carteira", f["secao"])
    linha += 1
    for i, nome in enumerate(("Faixa", "Contas", "Receita")):
        aba.write(linha, i, nome, f["cab"])
    linha += 1
    inicio_faixas = linha
    tem_receita = r.painel["valores"]["receita_ativa"] is not None
    for chave in ("saudavel", "pode_melhorar", "possivel_churn", "sem_nota"):
        nome = NOME_FAIXAS[chave]
        aba.write(linha, 0, nome, f["centro"])
        dados = r.painel["faixas"][chave]
        if intervalo["ultima"] >= intervalo["primeira"]:
            aba.write_formula(linha, 1, f'=COUNTIF({_ref(intervalo, "F")},"{nome}")', f["int"], dados["contas"])
            if tem_receita:
                aba.write_formula(linha, 2, f'=SUMIF({_ref(intervalo, "F")},"{nome}",{_ref(intervalo, "K")})', f["moeda"], dados["receita"])
            else:
                aba.write(linha, 2, "a preencher", f["a_preencher"])
        else:
            aba.write(linha, 1, 0, f["int"])
            aba.write(linha, 2, "a preencher", f["a_preencher"])
        linha += 1
    _semaforo(aba, f, f"A{inicio_faixas + 1}:A{linha}")

    linha += 1
    aba.write(linha, 0, "Metas do CS", f["secao"])
    linha += 1
    if r.metas:
        for i, nome in enumerate(("Meta", "Alvo", "Atual", "Situação", "Prazo", "Responsável")):
            aba.write(linha, i, nome, f["cab"])
        linha += 1
        inicio = linha
        for meta in r.metas:
            aba.write(linha, 0, meta["meta"], f["quebra"])
            _formatar_metrica(aba, f, linha, 1, meta["alvo"], meta["unidade"])
            _formatar_metrica(aba, f, linha, 2, meta["atual"], meta["unidade"])
            aba.write(linha, 3, meta["situacao"], f["centro"])
            aba.write(linha, 4, meta["prazo"], f["texto"])
            aba.write(linha, 5, meta["responsavel"], f["texto"])
            linha += 1
        aba.conditional_format(f"D{inicio + 1}:D{linha}", {"type": "cell", "criteria": "==", "value": '"atrás"', "format": f["vermelho"]})
        aba.conditional_format(f"D{inicio + 1}:D{linha}", {"type": "cell", "criteria": "==", "value": '"no alvo"', "format": f["verde"]})
    else:
        aba.write(linha, 0, "a preencher: defina as metas em 2-metas/metas.md", f["a_preencher"])
        linha += 1

    linha += 1
    aba.write(linha, 0, "Métricas", f["secao"])
    linha += 1
    for i, nome in enumerate(("Métrica", "Valor")):
        aba.write(linha, i, nome, f["cab"])
    aba.merge_range(linha, 2, linha, 5, "Como é calculada", f["cab"])
    linha += 1
    for m in r.painel["metricas"]:
        aba.write(linha, 0, m["nome"], f["texto"])
        _formatar_metrica(aba, f, linha, 1, m["valor"], m["unidade"])
        como = f"{m['como']} ({m['detalhe']})" if m.get("detalhe") else m["como"]
        aba.merge_range(linha, 2, linha, 5, como, f["quebra"])
        if len(como) > 60:  # célula mesclada não ajusta a altura sozinha
            aba.set_row(linha, 28)
        linha += 1

    for titulo, grupos in (("Por responsável", r.painel["por_responsavel"]), ("Por segmento", r.painel["por_segmento"])):
        if not grupos:
            continue
        linha += 1
        aba.write(linha, 0, titulo, f["secao"])
        linha += 1
        for i, nome in enumerate(("Grupo", "Contas", "Receita", "Nota média", "Empacadas", "Em risco")):
            aba.write(linha, i, nome, f["cab"])
        linha += 1
        for g in grupos:
            nome = r.cofre.nome_de(g["grupo"]) if g["grupo"] != "sem informação" else g["grupo"]
            aba.write(linha, 0, nome, f["texto"])
            aba.write(linha, 1, g["contas"], f["int"])
            _formatar_metrica(aba, f, linha, 2, g["receita"], "moeda")
            _formatar_metrica(aba, f, linha, 3, g["nota_media"], "num")
            aba.write(linha, 4, g["empacadas"], f["int"])
            aba.write(linha, 5, g["em_risco"], f["int"])
            linha += 1

    linha += 1
    aba.write(linha, 0, "Contas-chave", f["secao"])
    linha += 1
    chave = r.contas_chave
    if chave.get("existe"):
        aba.merge_range(linha, 0, linha, 5, f"{chave['quantas']} de {chave['de_um_total_de']} contas somam {chave['pct_receita']}% da receita:", f["simples"])
        linha += 1
        for codigo in chave["contas"]:
            aba.write(linha, 0, r.cofre.nome_conta(codigo), f["texto"])
            aba.write(linha, 1, codigo, f["centro"])
            linha += 1
    elif chave.get("existe") is False:
        aba.merge_range(linha, 0, linha, 5, f"Não há grupo pequeno que concentre a receita: são {chave['quantas']} das {chave['de_um_total_de']} contas com receita para chegar a 80%.", f["simples"])
    else:
        aba.write(linha, 0, "a preencher: falta a receita por conta", f["a_preencher"])
    return aba


def _aba_prioridades(livro, f, r) -> None:
    aba = livro.add_worksheet("Quem olhar primeiro")
    colunas = [("#", 4), ("ID", 11), ("Cliente", 30), ("Nota", 7), ("Faixa", 15), ("Valor", 13), ("Renovação", 12), ("Matriz", 10), ("Por quê", 60), ("Quem age", 26), ("Próximo passo", 28), ("Próximo contato", 13)]
    _titulo(aba, f, "Quem olhar primeiro", "Ordem: pontos dos sinais vezes a receita da conta. A combinação de sinais pesa mais que um sinal só.", len(colunas))
    _cabecalho(aba, f, 3, colunas)
    por_codigo = {c.codigo: c for c in r.contas}
    for i, p in enumerate(r.prioridades):
        l = 4 + i
        conta = por_codigo[p["conta"]]
        aba.write(l, 0, i + 1, f["int"])
        aba.write(l, 1, p["conta"], f["centro"])
        aba.write(l, 2, r.cofre.nome_conta(p["conta"]), f["texto"])
        _ou_preencher(aba, f, l, 3, p["nota"], "int")
        aba.write(l, 4, NOME_FAIXAS[p["faixa"]], f["centro"])
        _ou_preencher(aba, f, l, 5, p["receita"], "moeda")
        _ou_preencher(aba, f, l, 6, conta.campos.get("renovacao"), "data")
        aba.write(l, 7, p["matriz"], f["centro"])
        aba.write(l, 8, ". ".join(p["por_que"]), f["quebra"])
        aba.write(l, 9, p["quem_age"], f["quebra"])
        if conta.campos.get("proximo_passo"):
            aba.write(l, 10, conta.campos["proximo_passo"], f["editavel"])
        else:
            aba.write_blank(l, 10, None, f["editavel"])
        if conta.campos.get("data_proximo_contato"):
            aba.write_datetime(l, 11, _dt(conta.campos["data_proximo_contato"]), f["editavel_data"])
        else:
            aba.write_blank(l, 11, None, f["editavel_data"])
    if r.prioridades:
        _semaforo(aba, f, f"E5:E{4 + len(r.prioridades)}")
    else:
        aba.merge_range(4, 0, 4, 8, "Nenhuma conta com sinal nesta rodada, ou ainda não há dado para ver sinais. Veja a aba O que falta medir.", f["simples"])
    aba.freeze_panes(4, 3)


def _aba_empaca(livro, f, r) -> None:
    aba = livro.add_worksheet("O que empaca")
    colunas = [("ID", 11), ("Cliente", 30), ("Etapa", 18), ("Dias na etapa", 9), ("Prazo", 8), ("Dias além", 8), ("Nota", 7), ("Motivo", 12), ("Quem age", 28), ("Próximo passo", 30), ("Próximo contato", 13)]
    _titulo(aba, f, "O que empaca", "Conta parada além do prazo da etapa, mesmo com a nota verde. O motivo muda quem precisa agir.", len(colunas))
    _cabecalho(aba, f, 3, colunas)
    for i, conta in enumerate(r.empacadas):
        l = 4 + i
        n = l + 1
        aba.write(l, 0, conta.codigo, f["centro"])
        aba.write(l, 1, r.cofre.nome_conta(conta.codigo), f["texto"])
        aba.write(l, 2, conta.etapa, f["texto"])
        aba.write(l, 3, conta.dias_etapa, f["int"])
        aba.write(l, 4, conta.prazo, f["int"])
        aba.write_formula(l, 5, f"=D{n}-E{n}", f["int"], conta.dias_etapa - conta.prazo)
        _ou_preencher(aba, f, l, 6, conta.nota, "int")
        if conta.motivo:
            aba.write(l, 7, conta.motivo, f["editavel"])
        else:
            aba.write_blank(l, 7, None, f["editavel"])
        aba.data_validation(l, 7, l, 7, {"validate": "list", "source": ["do cliente", "nosso"]})
        aba.write(l, 8, quem_age(conta), f["quebra"])
        if conta.campos.get("proximo_passo"):
            aba.write(l, 9, conta.campos["proximo_passo"], f["editavel"])
        else:
            aba.write_blank(l, 9, None, f["editavel"])
        if conta.campos.get("data_proximo_contato"):
            aba.write_datetime(l, 10, _dt(conta.campos["data_proximo_contato"]), f["editavel_data"])
        else:
            aba.write_blank(l, 10, None, f["editavel_data"])
    if not r.empacadas:
        aba.merge_range(4, 0, 4, 8, "Nenhuma conta empacada, ou ainda não há etapa, prazo e data para saber. Veja a aba O que falta medir.", f["simples"])
    aba.freeze_panes(4, 2)


def _aba_alertas(livro, f, r) -> None:
    aba = livro.add_worksheet("Alertas de padrão")
    colunas = [("ID", 11), ("Cliente", 30), ("Rotina", 26), ("Antes", 9), ("Agora", 9), ("Mudança", 9), ("Leitura", 11), ("Nota", 7), ("Criticidade", 10)]
    _titulo(aba, f, "Mudança de padrão", "A conta comparada com ela mesma. A mudança serve de alerta mesmo com a nota boa.", len(colunas))
    _cabecalho(aba, f, 3, colunas)
    linhas = r.alertas_ruins + r.alertas_bons
    for i, a in enumerate(linhas):
        l = 4 + i
        aba.write(l, 0, a["conta"], f["centro"])
        aba.write(l, 1, r.cofre.nome_conta(a["conta"]), f["texto"])
        aba.write(l, 2, a["rotina"], f["quebra"])
        aba.write(l, 3, a["antes"], f["int"])
        aba.write(l, 4, a["agora"], f["int"])
        if a["variacao_pct"] is None:
            aba.write(l, 5, "novo", f["centro"])
        else:
            aba.write(l, 5, a["variacao_pct"] / 100, f["pct_frac"])
        aba.write(l, 6, a["leitura"], f["centro"])
        _ou_preencher(aba, f, l, 7, a["nota"], "int")
        aba.write(l, 8, {"media": "média"}.get(a["criticidade"], a["criticidade"]), f["centro"])
    if linhas:
        aba.conditional_format(f"G5:G{4 + len(linhas)}", {"type": "cell", "criteria": "==", "value": '"alerta"', "format": f["vermelho"]})
        aba.conditional_format(f"G5:G{4 + len(linhas)}", {"type": "cell", "criteria": "==", "value": '"bom sinal"', "format": f["verde"]})
    else:
        aba.merge_range(4, 0, 4, 8, "Nenhuma mudança de padrão. Na primeira rodada, isso só aparece se o export trouxer a coluna do período anterior.", f["simples"])
    aba.freeze_panes(4, 2)


def _aba_contas_chave(livro, f, r) -> None:
    chave = r.contas_chave
    if not chave.get("existe"):
        return
    aba = livro.add_worksheet("Contas-chave")
    colunas = [
        ("ID", 11), ("Cliente", 30), ("Valor", 13), ("% da receita", 9), ("Nota", 7), ("Faixa", 15), ("Contrato", 10), ("Renovação", 12), ("Etapa", 18),
        ("Responsável", 16), ("Patrocinador anotado?", 11), ("Decisor anotado?", 10), ("Usuário-chave anotado?", 11), ("Sinais", 50),
        ("Objetivo: verbo, de X para Y, até quando", 36), ("O que mais ajudamos vocês hoje?", 36), ("Próxima reunião", 13),
    ]
    _titulo(aba, f, "Contas-chave", f"{chave['quantas']} de {chave['de_um_total_de']} contas somam {chave['pct_receita']}% da receita. Campos claros são para preencher antes da reunião.", len(colunas))
    _cabecalho(aba, f, 3, colunas, destaque_de=14)
    por_codigo = {c.codigo: c for c in r.ativas}
    total = sum(c.receita or 0 for c in r.ativas)
    for i, codigo in enumerate(chave["contas"]):
        conta = por_codigo[codigo]
        l = 4 + i
        aba.write(l, 0, codigo, f["centro"])
        aba.write(l, 1, r.cofre.nome_conta(codigo), f["texto"])
        _ou_preencher(aba, f, l, 2, conta.receita, "moeda")
        aba.write(l, 3, (conta.receita or 0) / total if total else 0, f["pct_frac"])
        _ou_preencher(aba, f, l, 4, conta.nota, "int")
        aba.write(l, 5, NOME_FAIXAS[conta.faixa], f["centro"])
        _ou_preencher(aba, f, l, 6, conta.contrato)
        _ou_preencher(aba, f, l, 7, conta.campos.get("renovacao") if conta.contrato != "mensal" else None, "data")
        _ou_preencher(aba, f, l, 8, conta.etapa or conta.etapa_rotulo)
        _ou_preencher(aba, f, l, 9, conta.campos.get("responsavel"))
        for j, papel in enumerate(("patrocinador", "decisor", "usuario_chave")):
            aba.write(l, 10 + j, "sim" if conta.campos.get(papel) else "não", f["centro"])
        aba.write(l, 13, ". ".join(s[1] for s in conta.sinais), f["quebra"])
        aba.write_blank(l, 14, None, f["editavel"])
        aba.write_blank(l, 15, None, f["editavel"])
        aba.write_blank(l, 16, None, f["editavel_data"])
    fim = 4 + len(chave["contas"])
    _semaforo(aba, f, f"F5:F{fim}")
    aba.freeze_panes(4, 2)


def _aba_oportunidades(livro, f, r) -> None:
    aba = livro.add_worksheet("Oportunidades")
    colunas = [("ID", 11), ("Cliente", 30), ("Valor", 13), ("Nota", 7), ("Oportunidade", 30), ("O que a rodada mostrou", 48), ("O que oferecer", 26), ("Insatisfação?", 11), ("Valor estimado", 13), ("Próximo passo", 30)]
    _titulo(aba, f, "Oportunidades de upgrade", "A rodada aponta onde olhar. Se a área já está no plano do cliente, é adoção, não upgrade. Com insatisfação, resolva isso primeiro.", len(colunas))
    _cabecalho(aba, f, 3, colunas, destaque_de=8)
    for i, o in enumerate(r.oportunidades):
        l = 4 + i
        aba.write(l, 0, o["conta"], f["centro"])
        aba.write(l, 1, r.cofre.nome_conta(o["conta"]), f["texto"])
        _ou_preencher(aba, f, l, 2, o["receita"], "moeda")
        _ou_preencher(aba, f, l, 3, o["nota"], "int")
        aba.write(l, 4, o["oportunidade"], f["quebra"])
        aba.write(l, 5, o["detalhe"], f["quebra"])
        aba.write(l, 6, o["oferta"], f["quebra"])
        aba.write(l, 7, "sim" if o["com_insatisfacao"] else "não", f["centro"])
        aba.write_blank(l, 8, None, f["editavel"])
        aba.write_blank(l, 9, None, f["editavel"])
    if r.oportunidades:
        aba.conditional_format(f"H5:H{4 + len(r.oportunidades)}", {"type": "cell", "criteria": "==", "value": '"sim"', "format": f["vermelho"]})
    else:
        aba.merge_range(4, 0, 4, 7, "Nenhuma oportunidade nesta rodada. Defina o que configura oportunidade em 4-dados/como-medir.md.", f["simples"])
    aba.freeze_panes(4, 2)


def _aba_previsoes(livro, f, r, contas: list) -> None:
    from .relatorios import resumo_das_previsoes

    prev = r.previsoes
    aba = livro.add_worksheet("Previsões")
    churn, uso, aumento = prev.get("churn") or {}, prev.get("engajamento") or {}, prev.get("incremento") or {}
    rotinas = sorted({(c["indicador"], c["rotina"]) for c in uso.get("contas", [])})
    colunas = [("ID", 11), ("Cliente", 30), ("Nota", 7), ("Valor", 13)]
    if churn.get("status") == "ok":
        colunas += [("Chance de cancelar", 11), ("O que pesou no cancelamento", 46)]
    colunas += [(f"{rotina}: tendência", 16) for _, rotina in rotinas]
    if aumento.get("status") == "ok":
        colunas += [("Chance de aumentar a receita", 11), ("Valor estimado", 13), ("O que pesou no aumento", 46)]
    _titulo(aba, f, "Previsões", "Modelo treinado com o histórico desta empresa, neste computador. É chance, não certeza. Só aparece o que passou no teste.", max(len(colunas), 6))
    aba.set_column(0, 0, 11)
    aba.set_column(1, 1, 30)
    linha = 3
    for texto in resumo_das_previsoes(prev):
        aba.merge_range(linha, 0, linha, max(len(colunas), 6) - 1, texto, f["simples"])
        aba.set_row(linha, 30)
        linha += 1
    tem_tabela = len(colunas) > 4
    if not tem_tabela:
        aba.freeze_panes(3, 0)
        return
    linha += 1
    _cabecalho(aba, f, linha, colunas)
    linha_cab = linha
    de_churn = {c["conta"]: c for c in churn.get("contas", [])}
    de_aumento = {c["conta"]: c for c in aumento.get("contas", [])}
    de_uso = {(c["conta"], c["indicador"]): c for c in uso.get("contas", [])}
    ordenadas = sorted(contas, key=lambda c: (-de_churn.get(c.codigo, {}).get("chance_pct", -1), -de_aumento.get(c.codigo, {}).get("chance_pct", -1), c.codigo))
    for conta in ordenadas:
        linha += 1
        aba.write(linha, 0, conta.codigo, f["centro"])
        aba.write(linha, 1, r.cofre.nome_conta(conta.codigo), f["texto"])
        _ou_preencher(aba, f, linha, 2, conta.nota, "int")
        _ou_preencher(aba, f, linha, 3, conta.receita, "moeda")
        col = 4
        if churn.get("status") == "ok":
            item = de_churn.get(conta.codigo)
            if item:
                aba.write(linha, col, item["chance_pct"], f["pct_int"])
                aba.write(linha, col + 1, ". ".join(item["motivos"]), f["quebra"])
            else:
                aba.write_blank(linha, col, None, f["texto"])
                aba.write_blank(linha, col + 1, None, f["texto"])
            col += 2
        for id_, _ in rotinas:
            item = de_uso.get((conta.codigo, id_))
            aba.write(linha, col, f"{item['tendencia']} ({item['chance_pct']}%)" if item else "estável", f["centro"])
            col += 1
        if aumento.get("status") == "ok":
            item = de_aumento.get(conta.codigo)
            if item:
                aba.write(linha, col, item["chance_pct"], f["pct_int"])
                if item["valor_estimado"] is None:  # o teste mostrou que a porcentagem errou de tamanho
                    aba.write(linha, col + 1, "não estimado", f["centro"])
                else:
                    aba.write(linha, col + 1, item["valor_estimado"], f["moeda"])
                aba.write(linha, col + 2, ". ".join(item["motivos"]), f["quebra"])
            else:
                for extra in range(3):
                    aba.write_blank(linha, col + extra, None, f["texto"])
    if churn.get("status") == "ok" and ordenadas:
        aba.conditional_format(linha_cab + 1, 4, linha, 4, {"type": "cell", "criteria": ">=", "value": prev["chance_para_tendencia_pct"], "format": f["vermelho"]})
    aba.freeze_panes(linha_cab + 1, 2)


def _aba_faltas(livro, f, r) -> None:
    aba = livro.add_worksheet("O que falta medir")
    colunas = [("Prioridade", 10), ("O que falta", 44), ("Por que importa", 50), ("Primeiro passo", 56)]
    _titulo(aba, f, "O que falta medir", "Em ordem de prioridade. Sem dado, a skill deixa o campo vazio em vez de inventar.", len(colunas))
    _cabecalho(aba, f, 3, colunas)
    for i, item in enumerate(r.faltas):
        l = 4 + i
        aba.write(l, 0, item["prioridade"], f["centro"])
        aba.write(l, 1, item["o_que_falta"], f["quebra"])
        aba.write(l, 2, item["por_que_importa"], f["quebra"])
        aba.write(l, 3, item["primeiro_passo"], f["quebra"])
    if r.faltas:
        aba.conditional_format(f"A5:A{4 + len(r.faltas)}", {"type": "cell", "criteria": "==", "value": '"alta"', "format": f["vermelho"]})
        aba.conditional_format(f"A5:A{4 + len(r.faltas)}", {"type": "cell", "criteria": "==", "value": '"média"', "format": f["amarelo"]})
    aba.freeze_panes(4, 0)


def _aba_perdidas(livro, f, r) -> None:
    if not r.perdidas:
        return
    aba = livro.add_worksheet("Conta perdida")
    colunas = [("ID", 11), ("Cliente", 30), ("Cancelou em", 12), ("Valor", 13), ("Nota antes de sair", 10), ("A skill teria avisado?", 14), ("Por quê", 56)]
    p = r.perdidas
    _titulo(aba, f, "Teste da conta perdida", f"Das {p['total']} contas que saíram, a skill teria avisado {p['sim']} ({p['sim_pela_nota']} pela nota, {p['sim_por_alerta']} só pelo alerta), não teria avisado {p['nao']} e em {p['sem_dado']} não dá para saber.", len(colunas))
    _cabecalho(aba, f, 3, colunas)
    import datetime as dt

    for i, d in enumerate(p["detalhes"]):
        l = 4 + i
        aba.write(l, 0, d["conta"], f["centro"])
        aba.write(l, 1, r.cofre.nome_conta(d["conta"]), f["texto"])
        _ou_preencher(aba, f, l, 2, dt.date.fromisoformat(d["cancelou_em"]) if d["cancelou_em"] else None, "data")
        _ou_preencher(aba, f, l, 3, d["receita"], "moeda")
        _ou_preencher(aba, f, l, 4, d["nota"], "int")
        aba.write(l, 5, d["avisaria"], f["centro"])
        aba.write(l, 6, d["por_que"], f["quebra"])
    fim = 4 + len(p["detalhes"])
    aba.conditional_format(f"F5:F{fim}", {"type": "cell", "criteria": "==", "value": '"sim"', "format": f["verde"]})
    aba.conditional_format(f"F5:F{fim}", {"type": "cell", "criteria": "==", "value": '"não"', "format": f["vermelho"]})
    aba.conditional_format(f"F5:F{fim}", {"type": "cell", "criteria": "==", "value": '"não dá para saber"', "format": f["cinza"]})


def _aba_medicoes(livro, f, r, contas: list) -> None:
    aba = livro.add_worksheet("Medições")
    inds = r.cfg.indicadores
    colunas = [("ID", 11), ("Cliente", 30)]
    for ind in inds:
        colunas += [(ind.rotina, 11), ("antes", 8)]
    _titulo(aba, f, "Medições", "O valor bruto de cada rotina. Em 'última data', o número é a quantidade de dias desde o registro.", max(len(colunas), 3))
    _cabecalho(aba, f, 3, colunas)
    for i, conta in enumerate(contas):
        l = 4 + i
        aba.write(l, 0, conta.codigo, f["centro"])
        aba.write(l, 1, r.cofre.nome_conta(conta.codigo), f["texto"])
        c = 2
        for ind in inds:
            medicao = conta.medicoes.get(ind.id)
            if medicao is None:
                aba.write_blank(l, c, None, f["editavel"])
            else:
                aba.write(l, c, medicao, f["texto"] if isinstance(medicao, str) else f["int"])
            antes = conta.antes.get(ind.id)
            if antes is None:
                aba.write_blank(l, c + 1, None, f["texto"])
            else:
                aba.write(l, c + 1, antes, f["int"])
            c += 2
    aba.freeze_panes(4, 2)


def _aba_como_usar(livro, f, r, tema: dict) -> None:
    aba = livro.add_worksheet("Como usar")
    aba.set_column(0, 0, 110)
    aba.set_row(0, 26)
    aba.write(0, 0, "Como usar esta planilha", f["titulo"])
    formula = r.formula
    linhas = [
        ("secao", "Por onde começar"),
        ("", "1. Painel geral: como está a carteira e quais metas estão atrás."),
        ("", "2. Quem olhar primeiro: a lista da semana, com o motivo de cada conta."),
        ("", "3. O que empaca: conta parada além do prazo, separando o que é do cliente do que é nosso."),
        ("", "4. Previsões: quem pode cancelar, para onde vai o uso e quem pode aumentar a receita, quando há histórico e o modelo passa no teste."),
        ("", "5. O que falta medir: o que trazer na próxima rodada, em ordem de prioridade."),
        ("secao", "Como ler a nota"),
        ("", "Abaixo de 30: possível churn. De 30 a 69: pode melhorar. De 70 para cima: saudável."),
        ("", "A nota vem das rotinas definidas no checklist da empresa, com peso pela criticidade: alta vale 3, média vale 2, baixa vale 1."),
        ("", "Confiança: quanto do peso total tem dado nesta conta. Alta de 80% para cima, média de 50% a 79%, baixa abaixo de 50%."),
        ("", f"Sem dado em pelo menos {arredondar(r.cfg.regras['cobertura minima'])}% do peso, a conta fica sem nota. A skill não inventa."),
        ("", "A nota sozinha não basta. Por isso a conta parada na etapa e a mudança de padrão acendem alerta mesmo com a nota boa."),
        ("secao", "O que você pode mudar aqui"),
        ("", "Campos claros são para anotar no seu trabalho. Os pesos da aba Health score mudam a nota na hora."),
        ("", "A próxima rodada lê só os exports, não esta planilha. Para o que você anotou continuar valendo, registre também no sistema de origem."),
        ("", "Para valer nas próximas rodadas, mude a criticidade em 4-dados/como-medir.md. Mudar pesos quebra a comparação com o passado: a data da mudança fica marcada."),
        ("", f"Versão da fórmula: {formula['versao']}." + (f" Mudou em {formula['mudou_em']}: a nota não é comparável com a rodada anterior." if formula["mudou_nesta_rodada"] else "")),
        ("secao", "Privacidade"),
        ("", "Esta planilha tem os nomes reais. Ela é só para a pessoa, e o script a gera no seu computador."),
        ("", "Para trocar as cores, edite 4-dados/tema.json na pasta da empresa ou modelos/tema.json no plugin."),
    ]
    linha = 2
    for tipo, texto in linhas:
        if tipo == "secao":
            linha += 1
            aba.write(linha, 0, texto, f["secao"])
        else:
            aba.write(linha, 0, texto, f["simples"])
        linha += 1


def gerar_planilha(r, caminho: Path, pasta: Path) -> None:
    import xlsxwriter

    tema = carregar_tema(pasta)
    livro = xlsxwriter.Workbook(str(caminho))
    f = _formatos(livro, tema)
    contas = sorted(r.ativas, key=lambda c: (c.nota is None, c.nota if c.nota is not None else 0, -(c.receita or 0), c.codigo))
    _aba_como_usar(livro, f, r, tema)
    # o Painel referencia o Health score, então calculamos o intervalo antes de criar as abas
    intervalo = {"primeira": PRIMEIRA + 1, "ultima": PRIMEIRA + len(contas)}
    painel = _aba_painel(livro, f, r, intervalo)
    _aba_prioridades(livro, f, r)
    _aba_nota(livro, f, r, contas)
    _aba_empaca(livro, f, r)
    _aba_alertas(livro, f, r)
    _aba_contas_chave(livro, f, r)
    _aba_oportunidades(livro, f, r)
    _aba_previsoes(livro, f, r, contas)
    _aba_faltas(livro, f, r)
    _aba_perdidas(livro, f, r)
    _aba_medicoes(livro, f, r, contas)
    painel.activate()
    livro.set_properties({"title": "Health score", "comments": "Gerado por gestao-de-cs"})
    livro.close()
