"""Guardião da carteira: o que empaca, quem está em risco, quem perdeu o contato e o plano de cada conta.

O script traz os fatos. A causa e a ação vêm da conversa: o plano sai com campos em branco de propósito.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from . import ErroDeUso, plural
from .contas import carregar_fatos, rotulo, sinais_de_insatisfacao, tabela_de_fatos, valor_da_ficha
from .pasta import nova_ficha
from .relatorios import moeda, numero

TIPOS = ("risco", "contato")
LISTA = 10


def _peso_do_risco(item: dict) -> float:
    """A combinação de sinais pesa mais que um sinal só, e a receita diz quanto está em jogo."""
    return len(sinais_de_insatisfacao(item)) * (item["receita"] or 1)


def texto_cuidados(pasta: Path, data: dt.date, resumo: dict, fatos: dict) -> str:
    linhas = [f"Guardião da carteira, rodada de {data.isoformat()}.", "", "O que empaca:"]
    empacadas = resumo["empacadas"]
    if empacadas:
        grupos = (("nosso", "Parado por nós, destravar primeiro"), ("do cliente", "Pendência do cliente"), (None, "Sem motivo, descobrir"))
        for motivo, titulo in grupos:
            grupo = [e for e in empacadas if e["motivo"] == motivo or (motivo is None and e["motivo"] not in ("nosso", "do cliente"))]
            if grupo:
                linhas.append(f"- {titulo}: " + "; ".join(f"{rotulo(e)} há {numero(e['dias_na_etapa'])} dias em {e['etapa']} (prazo {numero(e['prazo'])})" for e in grupo))
    elif resumo["dados_disponiveis"]["etapa"]:
        linhas.append("- Nenhuma conta empacada nesta rodada.")
    else:
        linhas.append("- Ainda não dá para saber: falta etapa, prazo ou data de entrada na etapa.")

    risco = sorted((i for i in fatos.values() if sinais_de_insatisfacao(i)), key=lambda i: (-_peso_do_risco(i), i["conta"]))
    linhas += ["", f"Contas com sinal de insatisfação ({len(risco)}; até {LISTA}):"]
    for item in risco[:LISTA]:
        linhas.append(f"- {rotulo(item)}: {moeda(item['receita'])}. {'. '.join(sinais_de_insatisfacao(item))}")
    if not risco:
        tem_como_ver = resumo["dados_disponiveis"]["nota"] or resumo["dados_disponiveis"]["etapa"]
        linhas.append("- Nenhuma nesta rodada." if tem_como_ver else "- Ainda não dá para saber: nenhuma conta tem nota nem etapa medida.")

    grandes = sorted(fatos.values(), key=lambda i: -(i["receita"] or 0))[:LISTA]
    sem_patrocinador = [i for i in grandes if not i["contatos_anotados"]["patrocinador"]]
    sem_valor = [i for i in grandes if not valor_da_ficha(pasta, i["conta"])]
    linhas += ["", f"Nas {plural(len(grandes), 'maior conta', 'maiores contas')}:"]
    linhas.append("- Sem patrocinador anotado: " + (", ".join(rotulo(i) for i in sem_patrocinador) or "nenhuma") + ".")
    linhas.append("- Sem a resposta de 'o que mais ajudamos vocês hoje?' na ficha: " + (", ".join(rotulo(i) for i in sem_valor) or "nenhuma") + ".")

    tempos = (resumo.get("melhoria") or {}).get("primeiro_valor") or []
    if tempos:
        linhas += ["", "Tempo até a primeira rotina, para calibrar os prazos:"]
        for t in tempos:
            linhas.append(f"- {t['rotina']}: quem ficou levou {t['dias_de_quem_ficou']} dias; quem saiu levou {t['dias_de_quem_saiu']} dias ({t['contas_que_ficaram']} e {t['contas_que_sairam']} contas).")
    return "\n".join(linhas)


def _plano_de_risco(pasta: Path, data_rodada: dt.date, item: dict, hoje: dt.date) -> list:
    sinais = sinais_de_insatisfacao(item)
    linhas = [f"# Plano para conta em risco: {rotulo(item)}, {hoje.isoformat()}", "", f"Dados da rodada de {data_rodada.isoformat()}.", ""]
    linhas += ["## O que fazer", "", "- Conferir as três perguntas, achar a causa e escrever o plano com responsável e data.", ""]
    linhas += ["## O que foi conversado", "", "- Nada ainda.", ""]
    linhas += tabela_de_fatos(item)
    linhas += ["## Os sinais", "", "A combinação de sinais pesa mais que um sinal só.", ""]
    linhas += [f"- {s}." for s in sinais] or ["- Nenhum sinal de insatisfação nesta rodada. Se você está vendo risco, anote aqui o que os dados não mostram: {{o que você viu}}"]
    linhas += ["", "## Antes de agir, confira", ""]
    linhas += ["- **É a pessoa certa?** {{quem responde pela conta do lado do cliente}}", "- **Ela ainda está lá?** {{confira no LinkedIn, ou pergunte}}", "- **A prioridade do cliente mudou?** {{o que mudou no negócio dele}}", ""]
    linhas += ["## A causa", "", "{{a causa específica. 'Não viu valor' não é causa: pergunte o que mudou e desde quando}}", "", "**O problema é:** {{do cliente, nosso ou dos dois}}", ""]
    linhas += ["## O plano", "", "| ação | quem | até quando | resultado esperado |", "| --- | --- | --- | --- |", "| {{ }} | {{ }} | {{ }} | {{ }} |", ""]
    linhas += ["## A primeira mensagem", "", "Revisei a sua conta e vi que {{o fato da conta}}. {{por que isso importa para ele}}. Podemos falar {{quando}}?", ""]
    linhas += ["## Como saber que funcionou", "", "- **O que precisa voltar:** {{a rotina e o número}}", "- **Acompanhar até:** {{data. Conta salva pede acompanhamento mais perto por um tempo}}", ""]
    if item["dias_ate_renovar"] is not None:
        linhas.insert(4, f"> Renova em {item['dias_ate_renovar']} dias: este plano precisa andar antes disso.")
        linhas.insert(5, "")
    return linhas


def _plano_de_contato(pasta: Path, data_rodada: dt.date, item: dict, hoje: dt.date) -> list:
    codigo = item["conta"]
    valor = valor_da_ficha(pasta, codigo)
    motivo = valor_da_ficha(pasta, codigo, "Motivo da compra")
    linhas = [f"# Troca de contato: {rotulo(item)}, {hoje.isoformat()}", "", f"Dados da rodada de {data_rodada.isoformat()}.", ""]
    linhas += ["## O que fazer", "", "- Quem chega não sabe o que a conta já ganhou com a gente. Mostrar isso primeiro, antes que ele reavalie o contrato.", ""]
    linhas += ["## O que foi conversado", "", "- Nada ainda.", ""]
    linhas += ["## Quem saiu e quem chegou", "", "Use cargos, não nomes, se a pasta estiver em modo protegido.", "", "- **Quem saiu:** {{cargo}}", "- **Quem chegou:** {{cargo}}", "- **Como descobrimos:** {{conversa, e-mail ou LinkedIn}}", ""]
    linhas += tabela_de_fatos(item)
    linhas += ["## O que levar para quem chegou", ""]
    linhas += [f"**O que mais ajudamos vocês hoje?** {valor or '{{não está na ficha. Pergunte a quem usa no dia a dia antes da conversa}}'}", "", f"**Por que compraram:** {motivo or '{{anote na ficha: por que comprou e o que foi prometido}}'}", ""]
    linhas += ["## A conversa", ""]
    linhas += [
        "1. **Apresente-se e diga por que está ali.** {{preencher}}",
        "2. **Mostre o que a conta já ganhou, com o número dela.** {{preencher}}",
        "3. **Pergunte o que é importante para ele agora.** {{preencher depois da conversa}}",
        "4. **Combine o próximo passo, com data.** {{preencher depois da conversa}}",
        "",
    ]
    linhas += ["## Depois da conversa", "", "- Atualizar os contatos na ficha: patrocinador, decisor e usuário-chave.", "- Se a prioridade mudou, atualizar o motivo da compra e o objetivo da conta.", ""]
    return linhas


def criar_plano(pasta: Path, codigo: str, tipo: str, hoje: dt.date, refazer: bool = False) -> tuple:
    if tipo not in TIPOS:
        raise ErroDeUso("use --tipo risco ou contato.")
    data_rodada, _, fatos = carregar_fatos(pasta)
    item = fatos.get(codigo)
    if item is None:
        raise ErroDeUso(f"não achei a conta {codigo} entre as contas ativas da rodada de {data_rodada.isoformat()}.")
    nova_ficha(pasta, codigo)
    caminho = pasta / "3-clientes" / codigo / f"plano-{tipo}-{hoje.isoformat()}.md"
    montar = _plano_de_risco if tipo == "risco" else _plano_de_contato
    texto = "\n".join(montar(pasta, data_rodada, item, hoje))
    criou = refazer or not caminho.exists()
    if criou:
        caminho.write_text(texto, encoding="utf-8")
    return caminho, texto, criou


def texto_melhoria(data: dt.date, resumo: dict, nome_de) -> str:
    dados = resumo.get("melhoria")
    linhas = [f"Melhoria contínua, rodada de {data.isoformat()}. Isto mostra o que mudou. O porquê vem da conversa.", "", "O que mudou na carteira (soma das contas):"]
    for m in dados["o_que_mudou"]:
        linhas.append(f"- {m['rotina']}: de {numero(m['antes'])} para {numero(m['agora'])} ({m['variacao_pct']}%, {m['contas']} contas). {m['leitura'].capitalize()}.")
    if not dados["o_que_mudou"]:
        linhas.append("- Nenhuma rotina mudou 10% ou mais, ou ainda não há com o que comparar.")
    if dados["temas_que_crescem"]:
        linhas += ["", "Temas que cresceram nos últimos 30 dias:"]
        for t in dados["temas_que_crescem"][:10]:
            nome = f"{t['tema']} · {t['nome']}" if t.get("nome") else t["tema"]
            linhas.append(f"- {nome} ({t['arquivo']}): de {t['antes']} para {t['agora']}.")
    else:
        linhas += ["", "Temas: nenhum cresceu, ou o export ainda não traz a categoria (campo tema_evento)."]
    saiu = dados["quem_saiu"]
    linhas += ["", f"Quem saiu: {saiu['ultimos_30_dias']} contas nos últimos 30 dias ({saiu['30_dias_antes']} nos 30 antes); {saiu['ultimos_90_dias']} nos últimos 90 ({saiu['90_dias_antes']} nos 90 antes)."]
    if saiu["motivos"]:
        linhas.append("Motivos: " + "; ".join(f"{m.get('nome') or m['motivo']}: {m['contas']}" for m in saiu["motivos"][:8]) + ".")
    if saiu["sem_motivo_especifico"]:
        linhas.append(f"Sem motivo específico: {plural(saiu['sem_motivo_especifico'], 'conta', 'contas')}. Esse é o primeiro problema a resolver.")
    metricas = {m["id"]: m for m in resumo["painel"]["metricas"] if m.get("id")}
    if metricas.get("nps", {}).get("valor") is not None:
        linhas.append(f"NPS da base: {numero(metricas['nps']['valor'])}. Serve para ver a tendência, não para avaliar conta a conta.")
    titulos = (("engajados", "Engajados"), ("novos", "Novos"), ("ex_clientes", "Ex-clientes"), ("promotores", "Promotores, para pedir indicação"), ("detratores", "Detratores, para fechar o ciclo"))
    linhas += ["", "Com quem conversar (até 10 por grupo, pela receita):"]
    for chave, titulo in titulos:
        linhas.append(f"- {titulo}: " + (", ".join(nome_de(c) for c in dados["grupos"][chave]) or "nenhuma conta") + ".")
    return "\n".join(linhas)
