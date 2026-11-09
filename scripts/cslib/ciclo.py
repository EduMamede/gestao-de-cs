"""Ciclo de resultado: o que aconteceu com o número depois de cada ação aprovada.

Só compara a rodada de antes da decisão com a rodada depois dela. Isso mostra que o número mudou depois da ação,
não que a ação causou a mudança: conta em baixa costuma subir de qualquer jeito. Por isso, com casos suficientes,
o ciclo mostra também as contas da mesma faixa que não tiveram ação.
"""

from __future__ import annotations

import datetime as dt

from . import config as config_mod
from . import plural
from .medir import ler_formula_anterior, ler_valores, rodadas_anteriores
from .mesa import SEM_CONTA, data_legivel, eh_aviso, ler_data
from .relatorios import numero

MINIMO_PARA_COMPARAR = 5
MOVIMENTOS = ("melhorou", "igual", "piorou")


def _numero_da_celula(linha: dict, coluna: str):
    try:
        return float(linha.get(coluna))
    except (TypeError, ValueError):
        return None


def _direcao_do_movimento(antes: float, depois: float, direcao: str = "bom") -> str:
    if depois == antes:
        return "igual"
    return "melhorou" if (depois > antes) == (direcao != "ruim") else "piorou"


def _indicador(cfg, texto: str):
    alvo = (texto or "").casefold()
    return next((i for i in cfg.indicadores if alvo and alvo in (i.rotina.casefold(), i.id.casefold())), None)


def _rodada_antes_e_depois(rodadas: list, decidido: dt.date) -> tuple:
    antes = [r for r in rodadas if r[0] <= decidido]
    depois = [r for r in rodadas if r[0] > decidido]
    return (antes[-1] if antes else None), (depois[-1] if depois else None)


def _soma_da_carteira(rodada_antes, rodada_depois, coluna: str) -> tuple:
    valores_antes, valores_depois = ler_valores(rodada_antes[1]), ler_valores(rodada_depois[1])
    pares = []
    for codigo, linha in valores_depois.items():
        a, d = _numero_da_celula(valores_antes.get(codigo, {}), coluna), _numero_da_celula(linha, coluna)
        if a is not None and d is not None and linha.get("status") == "ativa":
            pares.append((a, d))
    return (sum(p[0] for p in pares), sum(p[1] for p in pares)) if pares else (None, None)


def medir_item(item: dict, cfg, rodadas: list) -> dict:
    """Devolve o item com a situação: melhorou, igual, piorou, saiu, sem_medida, sem_dado, sem_base ou espera_rodada."""
    decidido = ler_data(item["decidido_em"])
    saida = {"item": item["item"], "conta": item["conta"], "o_que_e": item["o_que_e"], "decidido_em": item["decidido_em"], "medida": None, "antes": None, "depois": None, "nota_antes": None, "nota_depois": None, "faixa_antes": None, "cedo": False, "rodada_antes": None, "rodada_depois": None}
    indicador = _indicador(cfg, item["acompanhar"])
    tem_conta = item["conta"] != SEM_CONTA
    if decidido is None:
        return {**saida, "situacao": "sem_dado"}
    if not tem_conta and indicador is None:
        return {**saida, "situacao": "sem_medida"}
    rodada_antes, rodada_depois = _rodada_antes_e_depois(rodadas, decidido)
    if rodada_antes is None:
        return {**saida, "situacao": "sem_base"}
    if rodada_depois is None:
        return {**saida, "situacao": "espera_rodada", "rodada_antes": rodada_antes[0].isoformat()}

    saida["rodada_antes"], saida["rodada_depois"] = rodada_antes[0].isoformat(), rodada_depois[0].isoformat()
    # A rotina conta um período para trás. Enquanto o período alcança dias de antes da decisão, o número ainda mistura os dois lados.
    janela = indicador.janela if indicador else max((i.janela for i in cfg.indicadores), default=30)
    saida["cedo"] = (rodada_depois[0] - decidido).days < janela

    if not tem_conta:
        antes, depois = _soma_da_carteira(rodada_antes, rodada_depois, f"ind:{indicador.id}")
        saida.update(medida=indicador.rotina, antes=antes, depois=depois)
        situacao = "sem_dado" if antes is None else _direcao_do_movimento(antes, depois, indicador.direcao)
        return {**saida, "situacao": situacao}

    linha_antes = ler_valores(rodada_antes[1]).get(item["conta"], {})
    linha_depois = ler_valores(rodada_depois[1]).get(item["conta"])
    if linha_depois is None:
        return {**saida, "situacao": "sem_dado"}
    if linha_depois.get("status") != "ativa":
        return {**saida, "situacao": "saiu"}
    formula_igual = ler_formula_anterior(rodada_antes[1]) == ler_formula_anterior(rodada_depois[1])
    nota_antes, nota_depois = _numero_da_celula(linha_antes, "nota"), _numero_da_celula(linha_depois, "nota")
    if formula_igual and nota_antes is not None and nota_depois is not None:
        saida.update(nota_antes=nota_antes, nota_depois=nota_depois, faixa_antes=linha_antes.get("faixa"))
    if indicador is not None:
        antes, depois = _numero_da_celula(linha_antes, f"ind:{indicador.id}"), _numero_da_celula(linha_depois, f"ind:{indicador.id}")
        saida.update(medida=indicador.rotina, antes=antes, depois=depois)
        situacao = "sem_dado" if antes is None or depois is None else _direcao_do_movimento(antes, depois, indicador.direcao)
        return {**saida, "situacao": situacao}
    if saida["nota_antes"] is None:  # sem nota, ou a fórmula mudou entre as duas rodadas: as notas não se comparam
        return {**saida, "situacao": "sem_dado"}
    saida.update(medida="nota", antes=nota_antes, depois=nota_depois)
    return {**saida, "situacao": _direcao_do_movimento(nota_antes, nota_depois)}


def _sem_acao_na_mesma_faixa(resultados: list, rodadas_por_data: dict, com_acao: set) -> dict:
    """Quantas contas da mesma faixa, sem ação aprovada, também subiram a nota nas mesmas rodadas."""
    vistas: dict = {}
    for r in resultados:
        if r["nota_antes"] is None or r["cedo"]:
            continue
        valores_antes = ler_valores(rodadas_por_data[r["rodada_antes"]])
        valores_depois = ler_valores(rodadas_por_data[r["rodada_depois"]])
        for codigo, linha in valores_antes.items():
            if codigo in com_acao or codigo in vistas or linha.get("faixa") != r["faixa_antes"]:
                continue
            depois = valores_depois.get(codigo, {})
            a, d = _numero_da_celula(linha, "nota"), _numero_da_celula(depois, "nota")
            if a is not None and d is not None and depois.get("status") == "ativa":
                vistas[codigo] = d > a
    return {"contas": len(vistas), "subiram": sum(vistas.values())}


def calcular(pasta, itens: list, hoje: dt.date) -> dict:
    aprovados = [i for i in itens if i["decisao"] == "aprovado" and not eh_aviso(i)]
    if not aprovados:
        return {"resultados": [], "por_tipo": []}
    cfg = config_mod.carregar(pasta)
    rodadas = rodadas_anteriores(pasta, hoje + dt.timedelta(days=1))
    resultados = [medir_item(i, cfg, rodadas) for i in aprovados]
    por_data = {quando.isoformat(): caminho for quando, caminho in rodadas}
    com_acao = {r["conta"] for r in resultados}

    por_tipo = []
    for tipo in sorted({r["o_que_e"] for r in resultados if not r["o_que_e"].startswith("Sugestão")}):
        grupo = [r for r in resultados if r["o_que_e"] == tipo and not r["cedo"] and r["situacao"] in (*MOVIMENTOS, "saiu")]
        if not grupo:
            continue
        linha = {"tipo": tipo, "total": len(grupo), **{m: sum(1 for r in grupo if r["situacao"] == m) for m in (*MOVIMENTOS, "saiu")}, "comparacao": None}
        com_nota = [r for r in grupo if r["nota_antes"] is not None]
        if len(com_nota) >= MINIMO_PARA_COMPARAR:
            sem_acao = _sem_acao_na_mesma_faixa(com_nota, por_data, com_acao)
            if sem_acao["contas"] >= MINIMO_PARA_COMPARAR:
                linha["comparacao"] = {"com_acao_contas": len(com_nota), "com_acao_subiram": sum(1 for r in com_nota if r["nota_depois"] > r["nota_antes"]), **sem_acao}
        por_tipo.append(linha)
    return {"resultados": resultados, "por_tipo": por_tipo}


def _nome_da_medida(r: dict) -> str:
    return "Nota" if r["medida"] == "nota" else r["medida"]


def frase(r: dict, nome_de) -> str:
    """A frase de um resultado, sem dizer que a ação causou o movimento."""
    conta = "A carteira toda" if r["conta"] == SEM_CONTA else nome_de(r["conta"])
    origem = f"{r['o_que_e']}, aprovado em {data_legivel(r['decidido_em'])}"
    if r["situacao"] in MOVIMENTOS:
        return f"{conta} ({origem}): {_nome_da_medida(r)} de {numero(r['antes'])} para {numero(r['depois'])}"
    return {
        "saiu": f"{conta} ({origem}): a conta saiu",
        "espera_rodada": f"{conta} ({origem}): falta uma rodada depois da decisão",
        "sem_base": f"{conta} ({origem}): não há rodada de antes da decisão para comparar",
        "sem_medida": f"{conta} ({origem}): sem rotina para acompanhar",
    }.get(r["situacao"], f"{conta} ({origem}): sem número para comparar")


def separar(ciclo: dict) -> dict:
    """Agrupa pelo que a pessoa precisa fazer com o resultado."""
    grupos = {"melhorou": [], "cedo": [], "rever": [], "saiu": [], "espera": []}
    for r in ciclo["resultados"]:
        if r["situacao"] == "saiu":
            grupos["saiu"].append(r)
        elif r["situacao"] in MOVIMENTOS and r["cedo"]:
            grupos["cedo"].append(r)
        elif r["situacao"] == "melhorou":
            grupos["melhorou"].append(r)
        elif r["situacao"] in ("igual", "piorou"):
            grupos["rever"].append(r)
        else:
            grupos["espera"].append(r)
    return grupos


AVISO = "O número mudou depois da ação. Isso não prova que foi por causa dela."


def frase_por_tipo(linha: dict) -> str:
    texto = f"{linha['tipo']}, {plural(linha['total'], 'caso', 'casos')}: melhorou em {linha['melhorou']}, ficou igual em {linha['igual']}, piorou em {linha['piorou']} e a conta saiu em {linha['saiu']}"
    comparacao = linha["comparacao"]
    if comparacao:
        texto += f". Nota: subiu em {comparacao['com_acao_subiram']} de {comparacao['com_acao_contas']} com a ação, e em {comparacao['subiram']} de {comparacao['contas']} da mesma faixa sem ela"
    else:
        texto += ". Ainda são poucos casos para comparar com quem não teve a ação"
    return texto


def texto_resultado(ciclo: dict, nome_de) -> str:
    if not ciclo["resultados"]:
        return "Ainda não há ação aprovada na mesa para acompanhar."
    grupos = separar(ciclo)
    titulos = (
        ("melhorou", "Melhorou depois da ação"),
        ("cedo", "Mudou, mas ainda é cedo: o período medido inclui dias de antes da decisão"),
        ("rever", "Não melhorou: rever a causa"),
        ("saiu", "Saiu mesmo com a ação"),
        ("espera", "Sem como comparar ainda"),
    )
    linhas = [AVISO]
    for chave, titulo in titulos:
        if grupos[chave]:
            linhas += ["", f"{titulo}:"] + [f"- {frase(r, nome_de)}." for r in grupos[chave]]
    if ciclo["por_tipo"]:
        linhas += ["", "Por tipo de ação:"] + [f"- {frase_por_tipo(t)}." for t in ciclo["por_tipo"]]
    return "\n".join(linhas)


def para_a_semana(pasta, hoje: dt.date, nome_de) -> dict:
    """O que a semana precisa saber. Sem mesa.md, não muda nada na semana."""
    from .mesa import em_aberto, ler_itens

    itens = ler_itens(pasta)
    if not itens:
        return {"fazer": [], "secao": []}
    ciclo = calcular(pasta, itens, hoje)
    grupos = separar(ciclo)
    fazer = [f"{frase(r, nome_de)}. Rever a causa." for r in grupos["rever"]]
    abertos = em_aberto(itens)
    if abertos:
        fazer.append(f"Mesa de aprovação: {len(abertos)} em aberto, a começar por {abertos[0]['item']}.")
    secao = []
    if ciclo["resultados"]:
        secao = ["## O que aconteceu depois das ações", "", AVISO, ""]
        for chave, titulo in (("melhorou", "Melhorou"), ("cedo", "Mudou, ainda é cedo"), ("rever", "Não melhorou"), ("saiu", "Saiu mesmo com a ação"), ("espera", "Sem como comparar ainda")):
            if grupos[chave]:
                secao += [f"**{titulo}**", ""] + [f"- {frase(r, nome_de)}." for r in grupos[chave]] + [""]
        secao += [f"- {frase_por_tipo(t)}." for t in ciclo["por_tipo"]] + ([""] if ciclo["por_tipo"] else [])
    return {"fazer": fazer, "secao": secao}
