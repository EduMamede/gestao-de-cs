"""A semana do CS: o script põe os fatos e o Líder da rotina escreve a leitura.

Separar assim garante que todo número do arquivo saiu da rodada, e não da conversa.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from . import ErroDeUso
from .leitura import parse_numero
from .relatorios import _tabela, moeda, numero, resumo_das_previsoes, valor_formatado

MARCA_LEITURA = "{{leitura do líder: escreva aqui, em 3 a 6 linhas, o que estes números querem dizer}}"
DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def segunda_da_semana(data: dt.date) -> dt.date:
    """Na sexta, sábado e domingo, a semana a planejar é a próxima."""
    if data.weekday() >= 4:
        return data + dt.timedelta(days=7 - data.weekday())
    return data - dt.timedelta(days=data.weekday())


def ultima_rodada(pasta: Path) -> tuple:
    base = pasta / "4-dados" / "rodadas"
    candidatas = []
    if base.exists():
        for d in base.iterdir():
            try:
                candidatas.append((dt.date.fromisoformat(d.name), d))
            except ValueError:
                continue
    candidatas = [c for c in candidatas if (c[1] / "resumo.json").exists()]
    if not candidatas:
        raise ErroDeUso("ainda não há rodada. Rode o Analista de dados antes de montar a semana.")
    candidatas.sort()
    data, caminho = candidatas[-1]
    return data, json.loads((caminho / "resumo.json").read_text(encoding="utf-8"))


def _rotulo(item: dict) -> str:
    return f"{item['conta']} · {item['nome']}" if item.get("nome") else item["conta"]


def _lista(itens: list, vazio: str) -> str:
    return ", ".join(itens) + "." if itens else vazio


def _agenda(resumo: dict, crucial: list) -> list[str]:
    dados = resumo["dados_disponiveis"]
    empacadas = resumo["empacadas"]
    nossas = [_rotulo(e) for e in empacadas if e["motivo"] == "nosso"]
    linhas = [
        f"- **Segunda: ajuste do funil.** Abrir a rodada, confirmar esta lista e destravar o que é nosso{': ' + ', '.join(nossas) if nossas else ''}.",
        f"- **Terça: o mais crucial.** {_lista([_rotulo(p) for p in crucial], 'Sem conta crucial: use o dia para a primeira medição que falta.')}",
    ]
    if resumo["recompra"]:
        fora_do_ritmo = sorted({_rotulo(a) for a in resumo["alertas_de_padrao"]})
        crescendo = sorted({_rotulo(a) for a in resumo["sinais_bons"]})
        sem_comparacao = "Ainda não há com o que comparar." if not dados["comparacao_de_padrao"] else None
        linhas += [
            f"- **Quarta: contas fora do ritmo.** {_lista(fora_do_ritmo, sem_comparacao or 'Nenhuma conta fora do próprio ritmo.')}",
            f"- **Quinta: quem está comprando mais.** {_lista(crescendo, sem_comparacao or 'Nenhum sinal bom nesta rodada.')}",
        ]
    else:
        cliente = [_rotulo(e) for e in empacadas if e["motivo"] == "do cliente"]
        vazio_cliente = "Nenhuma pendência do cliente nesta rodada." if dados["etapa"] else "Ainda não dá para saber: falta etapa, prazo ou data de entrada na etapa."
        renov = [_rotulo(x) for x in resumo["renovacoes"] if x["com_risco"]]
        vazio_renov = "Nenhuma renovação com risco na janela." if dados["renovacao"] else "Ainda não dá para saber: falta a data de renovação."
        linhas += [
            f"- **Quarta: pendências do cliente.** {_lista(cliente, vazio_cliente)}",
            f"- **Quinta: renovações com risco.** {_lista(renov, vazio_renov)}",
        ]
    linhas += ["- **Sexta: metas e dados.** Olhar o que andou, atualizar a situação das metas e trazer um item de 'o que falta medir'.", ""]
    return linhas


def _secao_previsoes(resumo: dict) -> list[str]:
    """Só o que passou no teste. O resto fica em previsoes.md: a semana é para agir."""
    prev = resumo.get("previsoes") or {}
    churn, uso, aumento = prev.get("churn") or {}, prev.get("engajamento") or {}, prev.get("incremento") or {}
    if "ok" not in (churn.get("status"), uso.get("status"), aumento.get("status")):
        return []
    linhas = ["## O que o modelo prevê", ""]
    linhas += [f"- {linha}" for linha in resumo_das_previsoes(prev) if ": pronta." in linha] + [""]
    if churn.get("status") == "ok":
        linhas += [f"**Quem pode cancelar em {prev['horizonte_dias']} dias**", ""]
        linhas += _tabela(["conta", "chance", "o que pesou"], [[_rotulo(c), f"{c['chance_pct']}%", ". ".join(c["motivos"])] for c in churn["contas"][:3]])
    caem = [c for c in uso.get("contas", []) if c["tendencia"] == "cai"][:3]
    if caem:
        linhas += ["**Onde o uso deve cair**", ""]
        linhas += _tabela(["conta", "rotina", "normal da conta", "agora", "chance"], [[_rotulo(c), c["rotina"], numero(c["normal"]), numero(c["agora"]), f"{c['chance_pct']}%"] for c in caem])
    if aumento.get("status") == "ok":
        linhas += [f"**Quem pode aumentar a receita em {prev['horizonte_dias']} dias**", ""]
        linhas += _tabela(["conta", "chance", "receita", "o que pesou"], [[_rotulo(c), f"{c['chance_pct']}%", moeda(c["receita"]), ". ".join(c["motivos"])] for c in aumento["contas"][:3]])
    return linhas


def texto_semana(semana: dt.date, resumo: dict, hoje: dt.date | None = None, ciclo: dict | None = None) -> str:
    ciclo = ciclo or {"fazer": [], "secao": []}
    # Renovação sozinha, em conta sem risco, fica na lista completa, mas não é o mais crucial.
    crucial = [p for p in resumo["prioridades"] if p["pontos"] >= 1][:3]
    metas_atras = [m for m in resumo["metas"] if m["situacao"] == "atrás"]
    empacadas = resumo["empacadas"]
    faltas = resumo["falta_medir"]
    dados = resumo["dados_disponiveis"]
    tem_como_ver = dados["nota"] or dados["etapa"]

    fazer = []
    for p in crucial:
        fazer.append(f"{_rotulo(p)}: {'. '.join(p['por_que'])}. Quem age: {p['quem_age']}.")
    for m in metas_atras[:2]:
        fazer.append(f"Meta atrás: {m['meta']} (atual {valor_formatado(m['atual'], m['unidade'])}, alvo {valor_formatado(m['alvo'], m['unidade'])}).")
    if not tem_como_ver and faltas:
        fazer.append(f"Ainda sem dado para priorizar contas. Esta semana, comece a medir: {faltas[0]['o_que_falta']}.")
    fazer += ciclo["fazer"]
    linhas = [f"# Semana de {semana.strftime('%d/%m/%Y')}", "", f"Dados da rodada de {resumo['rodada']}.", "", "## O que fazer", ""]
    linhas += [f"- {item}" for item in fazer] or ["- Nenhuma conta com sinal de risco e nenhuma meta atrás nesta rodada."]
    linhas += ["", "## O que foi conversado", "", "- Nada ainda.", "", "## Leitura do líder", "", MARCA_LEITURA, ""]

    linhas += ["## O mais crucial da semana", ""]
    if crucial:
        com_dono = any(p.get("responsavel") for p in crucial)
        cabecalho = ["#", "conta", "nota", "receita", "por quê", "quem age"] + (["responsável"] if com_dono else [])
        corpo = []
        for i, p in enumerate(crucial):
            linha = [i + 1, _rotulo(p), numero(p["nota"]) if p["nota"] is not None else "sem nota", moeda(p["receita"]), ". ".join(p["por_que"]), p["quem_age"]]
            corpo.append(linha + ([p.get("responsavel") or "a definir"] if com_dono else []))
        linhas += _tabela(cabecalho, corpo)
    elif tem_como_ver:
        linhas += ["Nenhuma conta com sinal de risco nesta rodada.", ""]
    else:
        linhas += ["Ainda não dá para saber: nenhuma conta tem nota nem etapa medida.", ""]
    if not tem_como_ver and resumo["maiores_contas"]:
        maiores = ", ".join(f"{_rotulo(m)} ({moeda(m['receita'])})" for m in resumo["maiores_contas"])
        linhas += [f"Para começar, as maiores contas (por receita, não por risco): {maiores}.", ""]
    renovam_bem = [x for x in resumo["renovacoes"] if not x["com_risco"]]
    if renovam_bem:
        linhas += ["Renovam na janela, sem sinal de risco: " + ", ".join(_rotulo(x) for x in renovam_bem) + ".", ""]

    linhas += ["## O que está atrás", ""]
    if resumo["metas"]:
        abertas = [m for m in resumo["metas"] if m["situacao"] != "no alvo"]
        no_alvo = [m for m in resumo["metas"] if m["situacao"] == "no alvo"]
        if abertas:
            linhas += _tabela(
                ["meta", "alvo", "atual", "situação", "responsável"],
                [[m["meta"], valor_formatado(m["alvo"], m["unidade"]), valor_formatado(m["atual"], m["unidade"]), m["situacao"], m["responsavel"]] for m in abertas],
            )
        if no_alvo:
            linhas += ["No alvo: " + "; ".join(f"{m['meta']} ({valor_formatado(m['atual'], m['unidade'])})" for m in no_alvo) + ".", ""]
    else:
        linhas += ["As metas ainda não foram definidas: sem elas, não dá para dizer o que está atrás.", ""]

    linhas += _secao_previsoes(resumo)
    linhas += ciclo["secao"]

    linhas += ["## Quem precisa agir nas contas paradas", ""]
    if empacadas:
        nossas = [e for e in empacadas if e["motivo"] == "nosso"]
        cliente = [e for e in empacadas if e["motivo"] == "do cliente"]
        sem = [e for e in empacadas if e["motivo"] not in ("nosso", "do cliente")]
        for titulo, grupo in (("Parado por nós: destravar internamente", nossas), ("Pendência do cliente: CS cobra e ajuda", cliente), ("Sem motivo: descobrir primeiro", sem)):
            if grupo:
                linhas += [f"**{titulo}**", ""]
                linhas += _tabela(["conta", "etapa", "dias", "prazo", "nota"], [[_rotulo(e), e["etapa"], numero(e["dias_na_etapa"]), numero(e["prazo"]), numero(e["nota"]) if e["nota"] is not None else "sem nota"] for e in grupo])
    elif dados["etapa"]:
        linhas += ["Nenhuma conta parada nesta rodada.", ""]
    elif resumo["recompra"]:
        linhas += ["Esta empresa não usa etapas. Veja as contas fora do ritmo em \"A semana\".", ""]
    else:
        linhas += ["Ainda não dá para saber: falta etapa, prazo ou data de entrada na etapa.", ""]

    perdidas = resumo.get("conta_perdida") or {}
    if perdidas:
        linhas += ["## Quem saiu", ""]
        linhas += [f"Das {perdidas['total']} contas que saíram, a skill teria avisado {perdidas['sim']} ({perdidas['sim_pela_nota']} pela nota, {perdidas['sim_por_alerta']} só pelo alerta), não teria avisado {perdidas['nao']}, e em {perdidas['sem_dado']} não dá para saber."]
        nao_viu = [_rotulo(d) for d in perdidas["detalhes"] if d["avisaria"] == "não"]
        if nao_viu:
            linhas += [f"Vale entender o que a nota não viu: {', '.join(nao_viu)}."]
        linhas += [""]

    linhas += ["## A semana", ""]
    if hoje is not None and semana < hoje < semana + dt.timedelta(days=5):
        linhas += [f"Hoje é {DIAS[hoje.weekday()]}: o que era dos dias anteriores entra hoje.", ""]
    linhas += _agenda(resumo, crucial)

    linhas += ["## Um dado para trazer nesta semana", ""]
    if faltas:
        linhas += [f"**{faltas[0]['o_que_falta']}.** {faltas[0]['primeiro_passo']}", ""]
    else:
        linhas += ["Nada em aberto.", ""]
    if resumo["formula"].get("mudou_nesta_rodada"):
        linhas += ["> Os pesos ou as rotinas mudaram nesta rodada: a nota não é comparável com a rodada anterior.", ""]
    return "\n".join(linhas)


def _numeros_do_resumo(obj, saida: set) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        saida.add(round(float(obj), 2))
    elif isinstance(obj, str):
        for trecho in re.findall(r"\d+(?:[.,]\d+)*", obj):
            numero_lido = parse_numero(trecho)
            if numero_lido is not None:
                saida.add(round(numero_lido, 2))
    elif isinstance(obj, dict):
        for valor in obj.values():
            _numeros_do_resumo(valor, saida)
    elif isinstance(obj, list):
        for valor in obj:
            _numeros_do_resumo(valor, saida)


def conferir_numeros(texto: str, resumo: dict, metas_md: str = "") -> list[str]:
    """Aponta reais, percentuais, dias, contagens de contas e notas que não vieram da rodada nem das metas."""
    conhecidos: set = set()
    _numeros_do_resumo(resumo, conhecidos)
    _numeros_do_resumo(metas_md, conhecidos)
    estranhos = []
    for padrao in (r"R\$\s?[\d.,]*\d", r"\d[\d.,]*\s?%", r"\b\d[\d.,]*\s+(?:dias?|contas?)\b", r"\b[Nn]ota\s+\d[\d.,]*"):
        for achado in re.findall(padrao, texto):
            trecho = re.search(r"\d[\d.,]*\d|\d", achado)
            lido = parse_numero(trecho.group(0)) if trecho else None
            if lido is None:
                continue
            if not any(abs(lido - k) <= 0.05 for k in conhecidos):
                estranhos.append(achado)
    return sorted(set(estranhos))
