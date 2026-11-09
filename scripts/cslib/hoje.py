"""A página do dia e o que entra na fila: o que melhorou, o que está marcado e o que espera a pessoa.

Tudo sai dos arquivos da pasta da empresa, sem IA. Por isso pode rodar sozinho, em uma tarefa agendada.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from . import plural
from . import ciclo as ciclo_mod
from . import tarefas as tarefas_mod
from .contas import NOME_TIPO, TIPOS as TIPOS_DE_REUNIAO, carregar_fatos, criar_reuniao, rotulo, sinais_de_insatisfacao
from .guardiao import criar_plano
from .medir import rodadas_anteriores
from .mesa import avisar, decidir, em_aberto, eh_aviso, ler_data, linha_em_aberto, por_na_fila, sincronizar
from .relatorios import moeda, numero
from .semana import _agenda, segunda_da_semana

ARQUIVO = "hoje.md"
MAX_POR_BLOCO = 5
DIAS_A_FRENTE = 7
DIAS_DE_CONTATO = 2
DIAS_DE_ATRASO = 14  # prazo mais antigo que isso não vira aviso novo: a fila não pode nascer lotada
RODADA_ANTIGA = 7
LIMITE_DA_ACAO = 90
JANELA_DE_PLANO = 30
JANELA_DE_REUNIAO = 60
LIMITE_DE_PREPARO = 3
RENOVACAO_URGENTE = 30  # ponto de partida, sugestão do autor da skill, não benchmark
LIMITE_DE_URGENTES = 10  # o que passar disso entra na próxima vez, e a página avisa quantos ficaram
VERMELHA = "possivel_churn"


def _curta(data: dt.date) -> str:
    return data.strftime("%d/%m")


def _acoes_aprovadas(pasta: Path, itens: list, hoje: dt.date) -> list:
    """As ações da tabela do plano aprovado. Devolve (data ou None, conta, ação, arquivo, quem)."""
    saida = []
    for item in itens:
        if item["decisao"] != "aprovado" or eh_aviso(item) or not item["arquivo"].endswith(".md") or "plano-" not in item["arquivo"]:
            continue
        caminho = pasta / item["arquivo"]
        if not caminho.is_file():
            continue
        dentro = False
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            if not linha.lstrip().startswith("|"):
                dentro = False
                continue
            celulas = [c.strip() for c in linha.strip().strip("|").split("|")]
            if "até quando" in [c.casefold() for c in celulas]:
                dentro = True
                continue
            if not dentro or re.match(r"^-+$", celulas[0]) or len(celulas) < 3 or "{{" in celulas[0]:
                continue
            saida.append((tarefas_mod.ler_data_curta(celulas[2], hoje), item["conta"], celulas[0][:LIMITE_DA_ACAO], item["arquivo"], "" if "{{" in celulas[1] else celulas[1]))
    return saida


def _reunioes(pasta: Path, hoje: dt.date, nome_de) -> list:
    saida = []
    for caminho in (pasta / "3-clientes").glob("CONTA-*/reunioes/*.md"):
        achado = re.fullmatch(r"(\d{4}-\d{2}-\d{2})-(\w+)\.md", caminho.name)
        data = ler_data(achado.group(1)) if achado else None
        if data and achado.group(2) in TIPOS_DE_REUNIAO and 0 < (data - hoje).days <= DIAS_A_FRENTE:  # a de hoje está em "Para fazer"
            saida.append((data, f"Reunião de {NOME_TIPO[achado.group(2)]}: {nome_de(caminho.parent.parent.name)}"))
    return saida


def _o_que_esta_marcado(pasta: Path, hoje: dt.date, resumo: dict, fatos: dict, tarefas: list, nome_de) -> list:
    linhas = []
    com_data = []
    for t in tarefas_mod.abertas(tarefas):  # da semana e de reunião ficam fora: a lista completa está em tarefas.md
        data = ler_data(t["ate"])
        if data and 0 < (data - hoje).days <= DIAS_A_FRENTE and "plano-" in t["de_onde"]:
            com_data.append((data, f"{nome_de(t['conta'])}: {t['texto']}"))
    com_data += _reunioes(pasta, hoje, nome_de)
    for item in fatos.values():
        contato = ler_data(item.get("proximo_contato"))
        if contato and 0 <= (contato - hoje).days <= DIAS_DE_CONTATO:
            com_data.append((contato, f"Contato marcado: {rotulo(item)}"))
    janela = resumo["regras"]["renovacao proxima"]
    for item in fatos.values():
        renova = ler_data(item.get("renovacao"))
        if renova and 0 <= (renova - hoje).days <= janela:
            com_data.append((renova, f"{rotulo(item)} renova, {moeda(item['receita'])}"))
    linhas += [f"{'Hoje' if d == hoje else _curta(d)}: {t}" for d, t in sorted(com_data, key=lambda a: (a[0], a[1]))]

    if len(linhas) > MAX_POR_BLOCO:
        linhas = linhas[:MAX_POR_BLOCO] + [f"Mais {len(linhas) - MAX_POR_BLOCO} nos próximos dias."]
    if not linhas:
        linhas = ["Nada marcado nos próximos dias."]
    if not resumo["dados_disponiveis"]["renovacao"] and not resumo["recompra"]:  # ausência de dado não é boa notícia
        linhas.append("Ainda não dá para ver renovações: falta a data no export.")
    return linhas


def _para_fazer(hoje: dt.date, resumo: dict, tarefas: list, nome_de) -> list:
    linhas = tarefas_mod.para_a_pagina(tarefas, hoje, nome_de, MAX_POR_BLOCO)
    if linhas:
        return linhas
    if hoje.weekday() < 5:  # sem lista, ao menos o que a agenda da semana pede para o dia
        crucial = [p for p in resumo["prioridades"] if p["pontos"] >= 1][:3]
        return [_agenda(resumo, crucial)[hoje.weekday()]]
    return ["- Nada para hoje."]


def texto_hoje(pasta: Path, hoje: dt.date, data_rodada: dt.date, resumo: dict, fatos: dict, itens: list, ciclo: dict, nome_de, topo: list | None = None, tarefas: list | None = None) -> str:
    tarefas = tarefas or []
    grupos = ciclo_mod.separar(ciclo)
    linhas = [f"# Hoje, {hoje.strftime('%d/%m/%Y')}", "", f"Dados da rodada de {data_rodada.strftime('%d/%m/%Y')}."]
    idade = (hoje - data_rodada).days
    if idade > RODADA_ANTIGA:
        linhas += [f"Esta rodada tem {plural(idade, 'dia', 'dias')}: vale trazer um export novo."]
    linhas += [f"> {aviso}" for aviso in topo or []]

    linhas += ["", "## O que melhorou", ""]
    melhorou = [f"- {ciclo_mod.frase(r, nome_de)}." for r in grupos["melhorou"]]
    cedo = [f"- Ainda é cedo. {ciclo_mod.frase(r, nome_de)}." for r in grupos["cedo"]]
    # Sinal bom pode ser número caindo, como chamados. Por isso a frase mostra de quanto para quanto.
    bons = [f"- Nesta rodada: {rotulo(b)}, {b['rotina']} de {numero(b['antes'])} para {numero(b['agora'])}." for b in resumo["sinais_bons"]]
    if melhorou or cedo:
        linhas += (melhorou + cedo)[:MAX_POR_BLOCO] + ["", ciclo_mod.AVISO]
    elif ciclo["resultados"]:
        linhas += ["- Nenhuma ação aprovada mostrou melhora até agora."]
    else:
        linhas += ["- Ainda não há ação aprovada para acompanhar."]
    if bons:
        linhas += ([""] if melhorou or cedo else []) + bons[: max(1, MAX_POR_BLOCO - len(melhorou) - len(cedo))]

    linhas += ["", "## Para fazer", ""]
    linhas += _para_fazer(hoje, resumo, tarefas, nome_de)

    linhas += ["", "## O que está marcado", ""]
    linhas += [f"- {t}" for t in _o_que_esta_marcado(pasta, hoje, resumo, fatos, tarefas, nome_de)]

    linhas += ["", "## O que espera você", ""]
    abertos = em_aberto(itens)
    rever = [f"- Rever: {ciclo_mod.frase(r, nome_de)}." for r in grupos["rever"]]
    saiu = [f"- Entender por quê: {ciclo_mod.frase(r, nome_de)}." for r in grupos["saiu"]]
    pendentes = [f"- {linha_em_aberto(pasta, i, nome_de)}." for i in abertos] + rever + saiu
    linhas += pendentes[:MAX_POR_BLOCO] or ["- Nada espera a sua decisão."]
    if len(pendentes) > MAX_POR_BLOCO:
        linhas += [f"- Mais {len(pendentes) - MAX_POR_BLOCO}: veja mesa.md."]
    linhas += ["", "_Página refeita pelo script a cada vez. O que você escrever aqui se perde: decida em mesa.md e marque em tarefas.md._", ""]
    return "\n".join(linhas)


def _arquivo_recente(pasta: Path, conta: str, padrao: str, janela: int, hoje: dt.date):
    candidatos = []
    for caminho in (pasta / "3-clientes" / conta).glob(padrao):
        achado = re.search(r"\d{4}-\d{2}-\d{2}", caminho.name)
        data = ler_data(achado.group(0)) if achado else None
        if data and abs((hoje - data).days) <= janela:
            candidatos.append((data, caminho))
    return max(candidatos)[1] if candidatos else None


def _fatos_da_rodada_anterior(pasta: Path, data_rodada: dt.date) -> dict:
    """Compara com a rodada de antes, sem guardar estado: rodar de novo no mesmo dia não muda a resposta."""
    anteriores = rodadas_anteriores(pasta, data_rodada)
    if not anteriores:
        return {}
    caminho = anteriores[-1][1] / "contas.json"
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}


def gatilhos_de_urgencia(hoje: dt.date, resumo: dict, fatos: dict, anteriores: dict) -> list:
    """O que ficou urgente, da maior receita para a menor. Devolve (item, ação, motivo)."""
    saida = []
    formula_mudou = (resumo.get("formula") or {}).get("mudou_nesta_rodada")
    for item in sorted(fatos.values(), key=lambda i: (-(i["receita"] or 0), i["conta"])):
        antes = anteriores.get(item["conta"])
        codigos = {s["codigo"] for s in item["sinais"]}
        codigos_antes = {s["codigo"] for s in antes["sinais"]} if antes else set()
        novos = codigos - codigos_antes
        if "cancelamento_agendado" in novos:
            saida.append((item, "plano", "cancelamento agendado"))
        # Com a fórmula nova, a faixa pode mudar sem nada ter mudado na conta.
        if item["faixa"] == VERMELHA and antes and antes["faixa"] != VERMELHA and not formula_mudou:
            saida.append((item, "plano", "caiu para a faixa vermelha"))
        # Sem rodada anterior, não dá para dizer que o problema é novo. Conta que entrou agora é nova.
        if "financeiro" in novos and anteriores:
            saida.append((item, "plano", "problema financeiro novo"))
        renova = ler_data(item.get("renovacao"))
        if renova and 0 <= (renova - hoje).days <= RENOVACAO_URGENTE and sinais_de_insatisfacao(item):
            saida.append((item, "reuniao", f"renova em {_curta(renova)}, com sinal de insatisfação"))
    return saida


def reavaliar_urgentes(pasta: Path, hoje: dt.date) -> dict:
    """Coloca na fila o que ficou urgente. Rodar duas vezes não duplica nada."""
    data_rodada, resumo, fatos = carregar_fatos(pasta)
    entraram, ficaram = [], 0
    for item, acao, motivo in gatilhos_de_urgencia(hoje, resumo, fatos, _fatos_da_rodada_anterior(pasta, data_rodada)):
        if acao == "plano":
            padrao, janela, aviso = "plano-risco-*.md", JANELA_DE_PLANO, "Rever o plano"
        else:
            padrao, janela, aviso = "reunioes/*-renovacao.md", JANELA_DE_REUNIAO, "Rever a reunião de renovação"
        caminho = _arquivo_recente(pasta, item["conta"], padrao, janela, hoje)
        relativo = caminho.relative_to(pasta).as_posix() if caminho else None
        if relativo and any(i["arquivo"] == relativo and motivo in i["urgente"] for i in sincronizar(pasta, hoje)[0]):
            continue
        if len(entraram) >= LIMITE_DE_URGENTES:
            ficaram += 1
            continue
        if caminho is None:
            caminho = (criar_plano(pasta, item["conta"], "risco", hoje) if acao == "plano" else criar_reuniao(pasta, item["conta"], "renovacao", hoje))[0]
            relativo = caminho.relative_to(pasta).as_posix()
        if por_na_fila(pasta, hoje, item["conta"], relativo, motivo, aviso):
            entraram.append({"conta": item["conta"], "motivo": motivo})

    itens = sincronizar(pasta, hoje)[0]
    feitas = {(t["de_onde"], t["texto"]) for t in tarefas_mod.ler_tarefas(pasta) if t["feita_em"]}
    for data, conta, acao, arquivo, _ in _acoes_aprovadas(pasta, itens, hoje):
        if not data or (arquivo, acao) in feitas or not 0 < (hoje - data).days <= DIAS_DE_ATRASO:
            continue
        if avisar(pasta, hoje, conta, arquivo, f"Passou do prazo em {_curta(data)}: {acao}", "prazo vencido"):
            entraram.append({"conta": conta, "motivo": "prazo vencido"})
    return {"entraram": entraram, "ficaram": ficaram}


def atualizar_tarefas(pasta: Path, hoje: dt.date, resumo: dict, itens: list) -> list:
    """A lista sai do que já existe: as ações dos planos aprovados, as reuniões e, com a semana montada, os dias dela."""
    novas = [tarefas_mod.nova(acao, data, conta, quem, arquivo) for data, conta, acao, arquivo, quem in _acoes_aprovadas(pasta, itens, hoje)]
    for caminho in (pasta / "3-clientes").glob("CONTA-*/reunioes/*.md"):
        achado = re.fullmatch(r"(\d{4}-\d{2}-\d{2})-(\w+)\.md", caminho.name)
        data = ler_data(achado.group(1)) if achado else None
        if data and achado.group(2) in TIPOS_DE_REUNIAO and data >= hoje:
            novas.append(tarefas_mod.nova(f"Reunião de {NOME_TIPO[achado.group(2)]}: preparar e marcar", data, caminho.parent.parent.name, "CS", caminho.relative_to(pasta).as_posix()))
    segunda = segunda_da_semana(hoje)
    if (pasta / "2-metas" / f"semana-{segunda.isoformat()}.md").exists():
        novas += tarefas_mod.tarefas_da_semana(segunda, resumo, hoje)
    tarefas_mod.acrescentar(pasta, hoje, novas)
    return tarefas_mod.ler_tarefas(pasta)


def _alinhar_prazos(pasta: Path, hoje: dt.date, itens: list) -> None:
    """Aviso de prazo e tarefa falam da mesma ação: resolver um resolve o outro. Foi a pessoa que marcou."""
    for item in itens:
        if not item["o_que_e"].startswith("Passou do prazo"):
            continue
        for t in tarefas_mod.ler_tarefas(pasta):
            if t["de_onde"] != item["arquivo"] or t["texto"] not in item["o_que_e"]:
                continue
            if item["decisao"] == "resolvido" and not t["feita_em"]:
                tarefas_mod.marcar_feita(pasta, t["tarefa"], hoje)
            elif not item["decisao"] and t["feita_em"]:
                decidir(pasta, item["item"], "resolvido", hoje)


def gerar_hoje(pasta: Path, hoje: dt.date, nome_de, topo: list | None = None) -> tuple:
    data_rodada, resumo, fatos = carregar_fatos(pasta)
    atualizar_tarefas(pasta, hoje, resumo, sincronizar(pasta, hoje)[0])
    urgentes = reavaliar_urgentes(pasta, hoje)
    _alinhar_prazos(pasta, hoje, sincronizar(pasta, hoje)[0])
    itens, novos, avisos = sincronizar(pasta, hoje)
    tarefas = atualizar_tarefas(pasta, hoje, resumo, itens)
    ciclo = ciclo_mod.calcular(pasta, itens, hoje)
    topo = list(topo or [])
    if urgentes["ficaram"]:
        topo.append(f"Mais {plural(urgentes['ficaram'], 'urgente ficou', 'urgentes ficaram')} de fora por hoje, para a fila não lotar. Entram na próxima vez.")
    texto = texto_hoje(pasta, hoje, data_rodada, resumo, fatos, itens, ciclo, nome_de, topo, tarefas)
    (pasta / ARQUIVO).write_text(texto, encoding="utf-8")
    tarefas_mod.gravar_copias(pasta, hoje, fatos)
    return texto, novos, avisos, urgentes


def preparar(pasta: Path, hoje: dt.date, limite: int = LIMITE_DE_PREPARO) -> list:
    """Prepara o que a rodada pede: plano para quem tem sinal e reunião para quem renova. Fatos sim, conclusão não.

    Tem limite por vez e não repete o que foi feito há pouco, para a mesa não virar mais uma fila que ninguém olha.
    """
    _, resumo, fatos = carregar_fatos(pasta)
    feitos = []
    for prioridade in resumo["prioridades"]:
        item = fatos.get(prioridade["conta"])
        if len(feitos) >= limite:
            return feitos
        if item and prioridade["pontos"] >= 1 and sinais_de_insatisfacao(item) and not _arquivo_recente(pasta, item["conta"], "plano-risco-*.md", JANELA_DE_PLANO, hoje):
            caminho, _, _ = criar_plano(pasta, item["conta"], "risco", hoje)
            feitos.append({"conta": item["conta"], "o_que_e": "Plano para conta em risco", "arquivo": caminho.relative_to(pasta).as_posix()})
    janela = resumo["regras"]["renovacao proxima"]
    renovam = sorted((i for i in fatos.values() if i["dias_ate_renovar"] is not None and 0 <= i["dias_ate_renovar"] <= janela), key=lambda i: i["dias_ate_renovar"])
    for item in renovam:
        if len(feitos) >= limite:
            return feitos
        if not _arquivo_recente(pasta, item["conta"], "reunioes/*-renovacao.md", JANELA_DE_REUNIAO, hoje):
            caminho, _, _ = criar_reuniao(pasta, item["conta"], "renovacao", hoje)
            feitos.append({"conta": item["conta"], "o_que_e": "Reunião de renovação", "arquivo": caminho.relative_to(pasta).as_posix()})
    return feitos
