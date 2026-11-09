"""A lista de tarefas e o arquivo de agenda: o que fazer, até quando e quem faz.

As tarefas saem do que já existe: a semana, as ações dos planos aprovados e as reuniões. A pessoa acrescenta as dela
e marca o que fez. tarefas.md é dela: o script só acrescenta linhas e preenche campo em branco.

O arquivo de agenda (.ics) entra em qualquer calendário, sem conexão e sem custo. Ele traz os nomes reais, então fica em
com-nomes/. Quem quiser ver os horários livres e criar os eventos de verdade conecta o calendário no Claude:
isso é conversa, e fica na skill /gestao-de-cs:hoje.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from pathlib import Path

from . import ErroDeUso, plural
from .mesa import SEM_CONTA, ler_data
from .privacidade import Cofre

ARQUIVO = "tarefas.md"
AGENDA = "agenda.ics"
CABECALHO = "| tarefa | até | conta | o que fazer | quem | de onde | feita em |"
MODELO = (
    "# Tarefas\n\n"
    "A lista do que fazer. Sai da semana, dos planos aprovados e das reuniões, e você acrescenta as suas.\n\n"
    "## O que fazer\n\n"
    "- Terminou? Escreva x na coluna \"feita em\", ou diga ao agente o número da tarefa.\n"
    "- Não quer fazer? Marque do mesmo jeito, em vez de apagar: a linha apagada pode voltar.\n"
    "- Para acrescentar, escreva uma linha nova na tabela, com o que fazer e, se quiser, a data.\n\n"
    "## O que foi conversado\n\n- Nada ainda.\n\n"
    f"## As tarefas\n\n{CABECALHO}\n| --- | --- | --- | --- | --- | --- | --- |\n"
)
LIMITE_NA_PAGINA = 90
MAX_POR_DIA = 3  # uma lista que não cabe no dia ninguém segue
FUTURO_DA_RENOVACAO = 120
LARGURA_DO_ICS = 75


def ler_data_curta(texto: str, hoje: dt.date):
    """Aceita 2026-11-07, 07/11/2026 e 07/11."""
    achado = re.fullmatch(r"(\d{2})/(\d{2})", (texto or "").strip())
    return ler_data(f"{achado.group(1)}/{achado.group(2)}/{hoje.year}") if achado else ler_data(texto)


def _limpar(texto) -> str:
    return " ".join(str(texto or "").split()).replace("|", "/")


def nova(texto: str, ate=None, conta: str | None = None, quem: str | None = None, de_onde: str = "você") -> dict:
    return {"tarefa": "", "ate": ate.isoformat() if ate else "", "conta": conta or SEM_CONTA, "texto": _limpar(texto), "quem": _limpar(quem), "de_onde": de_onde, "feita_em": ""}


def _texto(pasta: Path) -> str:
    caminho = pasta / ARQUIVO
    return caminho.read_text(encoding="utf-8") if caminho.exists() else MODELO


def _posicoes(texto: str) -> list:
    """Devolve (posição, tarefa) de cada linha da tabela, inclusive a que a pessoa escreveu sem número."""
    saida, dentro = [], False
    for posicao, linha in enumerate(texto.splitlines()):
        if linha.lstrip().startswith("| tarefa "):
            dentro = True
            continue
        if not dentro or not linha.lstrip().startswith("|") or re.match(r"^\s*\|\s*-+", linha):
            continue
        c = [x.strip() for x in linha.strip().strip("|").split("|")]
        if len(c) >= 7 and c[3]:
            saida.append((posicao, {"tarefa": c[0], "ate": c[1], "conta": c[2] or SEM_CONTA, "texto": c[3], "quem": c[4], "de_onde": c[5], "feita_em": c[6]}))
    return saida


def ler_tarefas(pasta: Path) -> list:
    return [t for _, t in _posicoes(_texto(pasta))] if (pasta / ARQUIVO).exists() else []


def _linha(t: dict) -> str:
    return f"| {t['tarefa']} | {t['ate']} | {t['conta']} | {t['texto']} | {t['quem']} | {t['de_onde']} | {t['feita_em']} |"


def _chave(t: dict) -> tuple:
    # Na semana, o texto muda quando o número muda: o que identifica é a origem e a conta.
    return (t["de_onde"], t["conta"]) if t["de_onde"].startswith("semana-") else (t["de_onde"], t["texto"])


def acrescentar(pasta: Path, hoje: dt.date, novas: list) -> list:
    """Acrescenta o que falta, numera o que a pessoa escreveu e completa a data do que ela marcou."""
    texto = _texto(pasta)
    linhas = texto.splitlines()
    posicoes = _posicoes(texto)
    existentes = [t for _, t in posicoes]
    numero = max((int(re.sub(r"\D", "", t["tarefa"]) or 0) for t in existentes), default=0) + 1
    conhecidas = {_chave(t): t for t in existentes}

    for t in novas:
        ja = conhecidas.get(_chave(t))
        # O prazo do plano pode ter mudado: a tarefa em aberto acompanha. O que a pessoa marcou fica.
        if ja is not None and not ja["feita_em"] and not t["de_onde"].startswith("semana-") and ja["ate"] != t["ate"]:
            ja["ate"] = t["ate"]
    for posicao, t in posicoes:
        if not t["tarefa"]:
            t["tarefa"] = f"T-{numero:03d}"
            t["de_onde"] = t["de_onde"] or "você"
            numero += 1
        data = ler_data_curta(t["ate"], hoje)
        if data:
            t["ate"] = data.isoformat()
        if t["feita_em"] and not ler_data(t["feita_em"]):
            t["feita_em"] = hoje.isoformat()
        linhas[posicao] = _linha(t)

    fim = max((i for i, l in enumerate(linhas) if l.lstrip().startswith("|")), default=len(linhas) - 1) + 1
    acrescentadas = []
    for t in novas:
        if _chave(t) in conhecidas:
            continue
        t = {**t, "tarefa": f"T-{numero:03d}"}
        numero += 1
        conhecidas[_chave(t)] = t
        linhas.insert(fim, _linha(t))
        fim += 1
        acrescentadas.append(t)
    (pasta / ARQUIVO).write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return acrescentadas


def marcar_feita(pasta: Path, codigo: str, hoje: dt.date) -> dict:
    acrescentar(pasta, hoje, [])
    texto = _texto(pasta)
    linhas = texto.splitlines()
    for posicao, t in _posicoes(texto):
        if t["tarefa"].casefold() == codigo.casefold():
            if t["feita_em"]:
                raise ErroDeUso(f"a tarefa {t['tarefa']} já está feita.")
            t["feita_em"] = hoje.isoformat()
            linhas[posicao] = _linha(t)
            (pasta / ARQUIVO).write_text("\n".join(linhas) + "\n", encoding="utf-8")
            return t
    raise ErroDeUso(f"não achei a tarefa {codigo}.")


def abertas(tarefas: list) -> list:
    """Atrasada primeiro, depois pela data. Sem data, por último."""
    return sorted((t for t in tarefas if not t["feita_em"]), key=lambda t: (not t["ate"], t["ate"], t["tarefa"]))


def _rotulo(item: dict) -> str:
    return item["conta"]


def tarefas_da_semana(segunda: dt.date, resumo: dict, hoje: dt.date) -> list:
    """A agenda da semana vira lista, dia a dia. O que era de um dia que já passou entra hoje."""

    def dia(n: int) -> dt.date:
        return max(segunda + dt.timedelta(days=n), hoje)

    origem = f"semana-{segunda.isoformat()}"
    saida = []
    crucial = [p for p in resumo["prioridades"] if p["pontos"] >= 1][:MAX_POR_DIA]
    na_lista = {p["conta"] for p in crucial}  # a conta crucial já tem tarefa: duas para o mesmo motivo só confundem
    empacadas = [e for e in resumo["empacadas"] if e["conta"] not in na_lista]
    for e in [e for e in empacadas if e["motivo"] == "nosso"][:MAX_POR_DIA]:
        saida.append(nova(f"Destravar: parada em {e['etapa']}, e o motivo é nosso", dia(0), e["conta"], "CS", f"{origem}:destravar"))
    for p in crucial:  # a tarefa é curta, porque também vira título na agenda. O motivo inteiro está na semana
        saida.append(nova(f"Agir na conta: {p['por_que'][0]}", dia(1), p["conta"], p["quem_age"], f"{origem}:crucial"))
    if resumo["recompra"]:
        fora = {a["conta"]: a for a in resumo["alertas_de_padrao"]}
        for conta, a in list(fora.items())[:MAX_POR_DIA]:
            saida.append(nova(f"Fora do próprio ritmo: {a['rotina']}", dia(2), conta, "CS", f"{origem}:ritmo"))
        bons = {a["conta"]: a for a in resumo["sinais_bons"]}
        for conta, a in list(bons.items())[:MAX_POR_DIA]:
            saida.append(nova(f"Comprando mais: {a['rotina']}. Vale conversar", dia(3), conta, "CS", f"{origem}:crescendo"))
    else:
        for e in [e for e in empacadas if e["motivo"] == "do cliente"][:MAX_POR_DIA]:
            saida.append(nova(f"Cobrar e ajudar: pendência do cliente em {e['etapa']}", dia(2), e["conta"], "CS", f"{origem}:cliente"))
        for x in [x for x in resumo["renovacoes"] if x["com_risco"]][:MAX_POR_DIA]:
            saida.append(nova("Renovação com risco: preparar a conversa", dia(3), x["conta"], "CS", f"{origem}:renovacao"))
    saida.append(nova("Olhar o que andou e atualizar a situação das metas", dia(4), None, "CS", f"{origem}:metas"))
    faltas = resumo["falta_medir"]
    if faltas:
        saida.append(nova(f"Trazer um dado: {faltas[0]['o_que_falta']}", dia(4), None, "CS", f"{origem}:dado"))
    return saida


def _curta(data: dt.date) -> str:
    return data.strftime("%d/%m")


def _descricao(t: dict, nome_de) -> str:
    conta = "" if t["conta"] == SEM_CONTA else f"{nome_de(t['conta'])}: "
    return f"{t['tarefa']} · {conta}{t['texto']}"


def para_a_pagina(tarefas: list, hoje: dt.date, nome_de, limite: int) -> list:
    """O que fazer hoje: o atrasado, o de hoje e o que não tem data."""
    lista = abertas(tarefas)
    de_hoje = [t for t in lista if not t["ate"] or ler_data(t["ate"]) is None or ler_data(t["ate"]) <= hoje]
    linhas = []
    for t in de_hoje[:limite]:
        data = ler_data(t["ate"])
        atraso = f"**Atrasada, era {_curta(data)}.** " if data and data < hoje else ""
        descricao = _descricao(t, nome_de)
        linhas.append(f"- {atraso}{descricao[:LIMITE_NA_PAGINA + 30]}.")
    depois = len(lista) - len(de_hoje[:limite])
    if depois:
        linhas.append(f"- Mais {depois} em tarefas.md.")
    return linhas


def texto_tarefas(tarefas: list, hoje: dt.date, nome_de) -> str:
    lista = abertas(tarefas)
    if not lista:
        return "Nenhuma tarefa em aberto."

    def data_de(t):
        return ler_data(t["ate"])

    grupos = (
        ("Atrasadas", [t for t in lista if data_de(t) and data_de(t) < hoje]),
        ("Hoje", [t for t in lista if data_de(t) == hoje]),
        ("Nos próximos dias", [t for t in lista if data_de(t) and data_de(t) > hoje]),
        ("Sem data", [t for t in lista if not data_de(t)]),
    )
    linhas = [f"Tarefas em aberto: {len(lista)}. Feitas: {sum(1 for t in tarefas if t['feita_em'])}."]
    for titulo, grupo in grupos:
        if grupo:
            linhas += ["", f"{titulo}:"]
            for t in grupo:
                quando = f"{_curta(data_de(t))}, " if data_de(t) else ""
                quem = f" Quem: {t['quem']}." if t["quem"] else ""
                linhas.append(f"- {quando}{_descricao(t, nome_de)}.{quem}")
    return "\n".join(linhas)


# ---------------------------------------------------------------- arquivo de agenda


def _escapar(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _dobrar(linha: str) -> list:
    """O formato pede linhas de até 75 bytes, sem cortar um acento no meio."""
    saida, atual, tamanho = [], "", 0
    for letra in linha:
        n = len(letra.encode("utf-8"))
        if tamanho + n > LARGURA_DO_ICS:
            saida.append(atual)
            atual, tamanho = " ", 1
        atual += letra
        tamanho += n
    return saida + [atual]


def _evento(chave: str, data: dt.date, titulo: str, descricao: str, carimbo: str) -> list:
    uid = hashlib.sha1(chave.encode("utf-8")).hexdigest()[:24]
    return [
        "BEGIN:VEVENT",
        f"UID:{uid}@gestao-de-cs",
        f"DTSTAMP:{carimbo}",
        f"DTSTART;VALUE=DATE:{data.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{(data + dt.timedelta(days=1)).strftime('%Y%m%d')}",
        f"SUMMARY:{_escapar(titulo)}",
        f"DESCRIPTION:{_escapar(descricao)}",
        "TRANSP:TRANSPARENT",  # o dia todo, sem bloquear horário
        "END:VEVENT",
    ]


def texto_da_agenda(tarefas: list, fatos: dict, hoje: dt.date, nome_de) -> str:
    """Só do que vem pela frente, em eventos de dia inteiro: sem ler a agenda, o script não sabe o horário livre."""
    carimbo = dt.datetime.combine(hoje, dt.time(12)).strftime("%Y%m%dT%H%M%SZ")
    linhas = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//gestao-de-cs//agenda//PT", "CALSCALE:GREGORIAN", "X-WR-CALNAME:Rotina de CS"]
    for t in abertas(tarefas):
        data = ler_data(t["ate"])
        if data and data >= hoje:
            conta = "" if t["conta"] == SEM_CONTA else f"{nome_de(t['conta'])}: "
            quem = f" Quem: {t['quem']}." if t["quem"] else ""
            linhas += _evento("|".join(_chave(t)), data, f"CS {t['tarefa']} · {conta}{t['texto']}", f"Tarefa da skill gestao-de-cs.{quem}", carimbo)
    for item in fatos.values():
        renova = ler_data(item.get("renovacao"))
        if renova and 0 <= (renova - hoje).days <= FUTURO_DA_RENOVACAO:
            linhas += _evento(f"renova|{item['conta']}|{renova}", renova, f"CS · Renovação: {nome_de(item['conta'])}", "Data de renovação do export.", carimbo)
        contato = ler_data(item.get("proximo_contato"))
        if contato and contato >= hoje:
            linhas += _evento(f"contato|{item['conta']}|{contato}", contato, f"CS · Contato marcado: {nome_de(item['conta'])}", "Próximo contato do export.", carimbo)
    linhas.append("END:VCALENDAR")
    return "\r\n".join(parte for linha in linhas for parte in _dobrar(linha)) + "\r\n"


def gravar_copias(pasta: Path, hoje: dt.date, fatos: dict) -> None:
    """As cópias com nomes reais, só para a pessoa. O script grava, e a IA não abre no modo protegido."""
    destino = pasta / "com-nomes"
    destino.mkdir(exist_ok=True)
    cofre = Cofre(pasta)
    tarefas = ler_tarefas(pasta)
    if (pasta / ARQUIVO).exists():
        (destino / ARQUIVO).write_text(cofre.restaurar(_texto(pasta)), encoding="utf-8")
    with (destino / AGENDA).open("w", encoding="utf-8", newline="") as f:
        f.write(texto_da_agenda(tarefas, fatos, hoje, cofre.restaurar))


def resumo_das_tarefas(tarefas: list, hoje: dt.date) -> str:
    lista = abertas(tarefas)
    atrasadas = sum(1 for t in lista if ler_data(t["ate"]) and ler_data(t["ate"]) < hoje)
    return f"{plural(len(lista), 'tarefa em aberto', 'tarefas em aberto')}, {plural(atrasadas, 'atrasada', 'atrasadas')}"
