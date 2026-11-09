"""Mesa de aprovação: o que os agentes prepararam espera a decisão da pessoa, em um lugar só.

A mesa não envia nada. O script acha o que foi preparado e anota a decisão. Quem decide é a pessoa, por isso
o comando decidir não entra na lista de liberados da trava de privacidade.

mesa.md é da pessoa: o script acrescenta linhas e só preenche campos em branco.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from . import ErroDeUso, plural
from .contas import NOME_TIPO, TIPOS as TIPOS_DE_REUNIAO

ARQUIVO = "mesa.md"
SUGESTOES = "5-melhoria/sugestoes.md"
DECISOES = ("aprovado", "recusado", "resolvido")
SEM_CONTA = "-"
JANELA_DE_ENTRADA = 30  # arquivo mais antigo que isso não entra: a mesa não pode nascer lotada
AVISOS = ("Passou do prazo", "Rever ")  # avisam de algo, e não há o que aprovar: não contam como ação no ciclo
CABECALHO = "| item | chegou em | conta | o que é | urgente | arquivo | decisão | decidido em | acompanhar |"
MODELO = (
    "# Mesa de aprovação\n\n"
    "Tudo que os agentes prepararam espera a sua decisão aqui. Nada sai sozinho: quem envia, apresenta ou muda é você.\n\n"
    "## O que fazer\n\n"
    "- Abrir cada arquivo e escrever a decisão: aprovado, recusado ou resolvido. Ou dizer ao agente, pelo número do item.\n"
    "- O que tem motivo na coluna urgente vem primeiro.\n\n"
    "## O que foi conversado\n\n- Nada ainda.\n\n"
    f"## A mesa\n\n{CABECALHO}\n| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
)
PALAVRAS_DE_DECISAO = {
    "aprovado": "aprovado",
    "aprovada": "aprovado",
    "sim": "aprovado",
    "ok": "aprovado",
    "recusado": "recusado",
    "recusada": "recusado",
    "nao": "recusado",
    "não": "recusado",
    "resolvido": "resolvido",
    "resolvida": "resolvido",
    "feito": "resolvido",
    "feita": "resolvido",
}
LINHA_DO_ITEM = re.compile(r"^\|\s*M-\d+\s*\|")


def ler_data(texto: str):
    texto = (texto or "").strip()
    achado = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", texto)
    if achado:
        texto = f"{achado.group(3)}-{achado.group(2)}-{achado.group(1)}"
    try:
        return dt.date.fromisoformat(texto)
    except ValueError:
        return None


def data_legivel(texto: str) -> str:
    data = ler_data(texto)
    return data.strftime("%d/%m/%Y") if data else texto


def eh_aviso(item: dict) -> bool:
    return item["o_que_e"].startswith(AVISOS)


def _celulas(linha: str) -> list:
    return [c.strip() for c in linha.strip().strip("|").split("|")]


def _item_da_linha(linha: str) -> dict | None:
    c = _celulas(linha)
    if len(c) < 9:
        return None
    return {"item": c[0], "chegou_em": c[1], "conta": c[2], "o_que_e": c[3], "urgente": c[4], "arquivo": c[5], "decisao": c[6], "decidido_em": c[7], "acompanhar": c[8]}


def _linha_do_item(i: dict) -> str:
    return f"| {i['item']} | {i['chegou_em']} | {i['conta']} | {i['o_que_e']} | {i['urgente']} | {i['arquivo']} | {i['decisao']} | {i['decidido_em']} | {i['acompanhar']} |"


def _novo_item(numero: int, hoje: dt.date, conta: str, o_que_e: str, arquivo: str, urgente: str = "") -> dict:
    return {"item": f"M-{numero:03d}", "chegou_em": hoje.isoformat(), "conta": conta, "o_que_e": o_que_e, "urgente": urgente, "arquivo": arquivo, "decisao": "", "decidido_em": "", "acompanhar": ""}


def _texto_da_mesa(pasta: Path) -> str:
    caminho = pasta / ARQUIVO
    return caminho.read_text(encoding="utf-8") if caminho.exists() else MODELO


def ler_itens(pasta: Path) -> list:
    """Só lê. Quem não tem mesa.md recebe uma lista vazia, e o resto da skill segue igual."""
    if not (pasta / ARQUIVO).exists():
        return []
    itens = (_item_da_linha(linha) for linha in _texto_da_mesa(pasta).splitlines() if LINHA_DO_ITEM.match(linha))
    return [i for i in itens if i]


def _proximo_numero(itens: list) -> int:
    numeros = [int(re.sub(r"\D", "", i["item"]) or 0) for i in itens]
    return max(numeros, default=0) + 1


def _o_que_o_arquivo_e(caminho: Path):
    """Devolve (o que é, data do nome do arquivo). Só reconhece o que os comandos da skill criam."""
    achado = re.fullmatch(r"plano-(risco|contato)-(\d{4}-\d{2}-\d{2})\.md", caminho.name)
    if achado:
        return ("Plano para conta em risco" if achado.group(1) == "risco" else "Troca de contato"), ler_data(achado.group(2))
    achado = re.fullmatch(r"(\d{4}-\d{2}-\d{2})-(\w+)\.md", caminho.name)
    if achado and caminho.parent.name == "reunioes" and achado.group(2) in TIPOS_DE_REUNIAO:
        return f"Reunião de {NOME_TIPO[achado.group(2)]}", ler_data(achado.group(1))
    return None, None


def _preparados_nas_contas(pasta: Path, hoje: dt.date) -> list:
    base = pasta / "3-clientes"
    saida = []
    if not base.exists():
        return saida
    for conta in sorted(d for d in base.iterdir() if d.is_dir() and d.name.startswith("CONTA-")):
        for caminho in sorted(list(conta.glob("plano-*.md")) + list((conta / "reunioes").glob("*.md"))):
            o_que_e, data = _o_que_o_arquivo_e(caminho)
            if o_que_e and data and (hoje - data).days <= JANELA_DE_ENTRADA:
                saida.append({"conta": conta.name, "o_que_e": o_que_e, "arquivo": caminho.relative_to(pasta).as_posix()})
    return saida


def _linhas_das_sugestoes(texto: str) -> list:
    """Devolve (posição, data, o que mudar, aprovada?) de cada linha da tabela de sugestões."""
    saida = []
    linhas = texto.splitlines()
    dentro = False
    for posicao, linha in enumerate(linhas):
        if linha.lstrip().startswith("| data "):
            dentro = True
            continue
        if not dentro or not linha.lstrip().startswith("|") or re.match(r"^\s*\|\s*-+", linha):
            continue
        c = _celulas(linha)
        if len(c) >= 4 and c[1] and "{{" not in c[1]:
            saida.append((posicao, c[0], c[1], "" if "{{" in c[3] else c[3]))
    return saida


def _sugestoes(pasta: Path) -> list:
    caminho = pasta / SUGESTOES
    if not caminho.exists():
        return []
    return [{"conta": SEM_CONTA, "o_que_e": f"Sugestão: {o_que_mudar}", "arquivo": SUGESTOES, "resposta": resposta} for _, _, o_que_mudar, resposta in _linhas_das_sugestoes(caminho.read_text(encoding="utf-8"))]


def _gravar(pasta: Path, texto: str, itens_novos: list, alterados: dict) -> None:
    linhas = texto.splitlines()
    for posicao, linha in enumerate(linhas):
        if LINHA_DO_ITEM.match(linha):
            item = _item_da_linha(linha)
            if item and item["item"] in alterados:
                linhas[posicao] = _linha_do_item(alterados[item["item"]])
    if itens_novos:
        fim = max((i for i, l in enumerate(linhas) if l.lstrip().startswith("|")), default=len(linhas) - 1) + 1
        for deslocamento, item in enumerate(itens_novos):
            linhas.insert(fim + deslocamento, _linha_do_item(item))
    (pasta / ARQUIVO).write_text("\n".join(linhas) + "\n", encoding="utf-8")


def sincronizar(pasta: Path, hoje: dt.date) -> tuple:
    """Traz o que foi preparado e completa a data do que a pessoa decidiu à mão. Devolve (itens, novos, avisos)."""
    texto = _texto_da_mesa(pasta)
    itens = [i for i in (_item_da_linha(l) for l in texto.splitlines() if LINHA_DO_ITEM.match(l)) if i]
    conhecidos = {(i["arquivo"], i["o_que_e"]) for i in itens}
    arquivos = {i["arquivo"] for i in itens if i["arquivo"]}
    numero = _proximo_numero(itens)
    novos, alterados, avisos = [], {}, []

    for preparado in _preparados_nas_contas(pasta, hoje) + _sugestoes(pasta):
        # Plano e reunião são um item por arquivo. No arquivo de sugestões, cada linha é um item.
        ja_tem = (preparado["arquivo"], preparado["o_que_e"]) in conhecidos if preparado["arquivo"] == SUGESTOES else preparado["arquivo"] in arquivos
        if ja_tem:
            continue
        novo = _novo_item(numero, hoje, preparado["conta"], preparado["o_que_e"], preparado["arquivo"])
        numero += 1
        novos.append(novo)
        conhecidos.add((novo["arquivo"], novo["o_que_e"]))
        arquivos.add(novo["arquivo"])

    respostas = {s["o_que_e"]: s["resposta"] for s in _sugestoes(pasta)}
    for item in itens + novos:
        decisao = item["decisao"].casefold()
        if not decisao and item["o_que_e"] in respostas:  # a pessoa pode ter respondido em sugestoes.md
            decisao = respostas[item["o_que_e"]].casefold()
        if not decisao:
            continue
        lida = PALAVRAS_DE_DECISAO.get(decisao)
        if lida is None:
            avisos.append(f"{item['item']}: a decisão escrita não é aprovado, recusado nem resolvido. Ficou como em aberto.")
            continue
        if item["decisao"] != lida or not item["decidido_em"]:
            item["decisao"] = lida
            item["decidido_em"] = item["decidido_em"] or hoje.isoformat()
            alterados[item["item"]] = item

    _gravar(pasta, texto, novos, alterados)
    return itens + novos, novos, avisos


def adicionar(pasta: Path, o_que_e: str, conta: str | None, arquivo: str | None, hoje: dt.date) -> dict:
    """Para o que não sai de um comando da skill, como o rascunho de uma pesquisa."""
    o_que_e = " ".join(o_que_e.split()).replace("|", "/")
    if not o_que_e:
        raise ErroDeUso("diga o que é o item.")
    itens, _, _ = sincronizar(pasta, hoje)
    novo = _novo_item(_proximo_numero(itens), hoje, conta or SEM_CONTA, o_que_e, arquivo or "")
    _gravar(pasta, _texto_da_mesa(pasta), [novo], {})
    return novo


def por_na_fila(pasta: Path, hoje: dt.date, conta: str, arquivo: str, motivo: str, aviso: str) -> bool:
    """Marca como urgente. O item em aberto sobe. Se o arquivo já foi decidido, entra um aviso para rever, uma vez só."""
    itens, _, _ = sincronizar(pasta, hoje)
    do_arquivo = [i for i in itens if i["arquivo"] == arquivo]
    if any(motivo in i["urgente"] for i in do_arquivo):
        return False
    aberto = next((i for i in do_arquivo if i["decisao"] not in DECISOES), None)
    if aberto:
        aberto["urgente"] = "; ".join(filter(None, (aberto["urgente"], motivo)))
        _gravar(pasta, _texto_da_mesa(pasta), [], {aberto["item"]: aberto})
    else:
        _gravar(pasta, _texto_da_mesa(pasta), [_novo_item(_proximo_numero(itens), hoje, conta, aviso, arquivo, motivo)], {})
    return True


def avisar(pasta: Path, hoje: dt.date, conta: str, arquivo: str, o_que_e: str, motivo: str) -> bool:
    """Um aviso sem nada a aprovar. Entra uma vez: quem resolveu não vê de novo."""
    o_que_e = " ".join(o_que_e.split()).replace("|", "/")
    itens, _, _ = sincronizar(pasta, hoje)
    if any(i["arquivo"] == arquivo and i["o_que_e"] == o_que_e for i in itens):
        return False
    _gravar(pasta, _texto_da_mesa(pasta), [_novo_item(_proximo_numero(itens), hoje, conta, o_que_e, arquivo, motivo)], {})
    return True


def campos_em_branco(pasta: Path, item: dict) -> int:
    if not item["arquivo"] or item["arquivo"] == SUGESTOES or eh_aviso(item):
        return 0
    caminho = pasta / item["arquivo"]
    return caminho.read_text(encoding="utf-8").count("{{") if caminho.is_file() else 0


def _responder_a_sugestao(pasta: Path, item: dict, decisao: str) -> None:
    """Preenche o aprovada? em branco. Se já houver resposta, não mexe."""
    caminho = pasta / SUGESTOES
    if not caminho.exists() or decisao not in ("aprovado", "recusado"):
        return
    texto = caminho.read_text(encoding="utf-8")
    alvo = item["o_que_e"].removeprefix("Sugestão: ")
    linhas = texto.splitlines()
    for posicao, _, o_que_mudar, resposta in _linhas_das_sugestoes(texto):
        if o_que_mudar == alvo and not resposta:
            c = _celulas(linhas[posicao])
            c[3] = "sim" if decisao == "aprovado" else "não"
            linhas[posicao] = "| " + " | ".join(c) + " |"
            caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
            return


def decidir(pasta: Path, codigo: str, decisao: str, hoje: dt.date, acompanhar: str | None = None, mesmo_assim: bool = False) -> dict:
    if decisao not in DECISOES:
        raise ErroDeUso("use --decisao aprovado, recusado ou resolvido.")
    itens, _, _ = sincronizar(pasta, hoje)
    item = next((i for i in itens if i["item"].casefold() == codigo.casefold()), None)
    if item is None:
        raise ErroDeUso(f"não achei o item {codigo} na mesa.")
    if item["decisao"] in DECISOES:
        raise ErroDeUso(f"o item {item['item']} já foi decidido: {item['decisao']} em {data_legivel(item['decidido_em'])}. Para mudar, edite {ARQUIVO}.")
    if decisao == "aprovado" and eh_aviso(item):
        raise ErroDeUso(f"o item {item['item']} é um aviso, e não há o que aprovar. Use resolvido ou recusado.")
    faltam = campos_em_branco(pasta, item)
    if decisao == "aprovado" and faltam and not mesmo_assim:
        raise ErroDeUso(f"o arquivo ainda tem {plural(faltam, 'campo em branco', 'campos em branco')}. Complete com a pessoa ou, se ela quiser aprovar assim, use --mesmo-assim.")
    item["decisao"] = decisao
    item["decidido_em"] = hoje.isoformat()
    if acompanhar:
        item["acompanhar"] = acompanhar.replace("|", "/")
    _gravar(pasta, _texto_da_mesa(pasta), [], {item["item"]: item})
    if item["arquivo"] == SUGESTOES:
        _responder_a_sugestao(pasta, item, decisao)
    return item


def em_aberto(itens: list) -> list:
    """O urgente vem primeiro. Depois, do mais antigo para o mais novo."""
    return sorted((i for i in itens if i["decisao"] not in DECISOES), key=lambda i: (not i["urgente"], i["chegou_em"], i["item"]))


def linha_em_aberto(pasta: Path, item: dict, nome_de) -> str:
    conta = "" if item["conta"] == SEM_CONTA else f"{nome_de(item['conta'])} · "
    urgente = f"**Urgente: {item['urgente']}.** " if item["urgente"] else ""
    texto = f"{urgente}{item['item']} · {conta}{item['o_que_e']}"
    if item["arquivo"] and not (pasta / item["arquivo"]).is_file():
        return f"{texto}: o arquivo não existe mais"
    faltam = campos_em_branco(pasta, item)
    return f"{texto}: {'falta 1 campo' if faltam == 1 else f'faltam {faltam} campos'}" if faltam else texto


def texto_mesa(pasta: Path, itens: list, novos: list, avisos: list, nome_de) -> str:
    abertos = em_aberto(itens)
    contagem = {d: sum(1 for i in itens if i["decisao"] == d) for d in DECISOES}
    linhas = [f"Mesa de aprovação: {len(abertos)} em aberto, {contagem['aprovado']} aprovados, {contagem['recusado']} recusados, {contagem['resolvido']} resolvidos. Novos agora: {len(novos)}."]
    linhas += ["", "Esperam a decisão da pessoa, com o urgente primeiro:" if abertos else "Nada espera decisão."]
    for item in abertos:
        onde = f" Arquivo: {item['arquivo']}." if item["arquivo"] else ""
        linhas.append(f"- {linha_em_aberto(pasta, item, nome_de)} (chegou em {data_legivel(item['chegou_em'])}).{onde}")
    if avisos:
        linhas += ["", "Avisos:"] + [f"- {a}" for a in avisos]
    return "\n".join(linhas)
