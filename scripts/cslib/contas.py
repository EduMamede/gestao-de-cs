"""Contas e receita: os fatos de cada conta para a reunião, a renovação e a conversa de expansão.

O script põe os números, e o agente escreve a conversa. Assim, nada que vai para o cliente nasce da IA
sem ter vindo da rodada ou da ficha. O método está em referencias/contas-e-receita.md.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from . import ErroDeUso, plural
from .medir import rodadas_anteriores, ler_valores
from .oportunidades import SINAIS_DE_INSATISFACAO
from .pasta import nova_ficha
from .relatorios import _tabela, moeda, numero
from .semana import ultima_rodada

TIPOS = ("revisao", "renovacao", "expansao")
NOME_TIPO = {"revisao": "revisão", "renovacao": "renovação", "expansao": "expansão"}
CAPA = {"revisao": "Revisão de resultados", "renovacao": "Revisão de resultados e próximos passos", "expansao": "Revisão de resultados"}
MARCA_VALOR = "{{pergunte na reunião e anote na ficha: o que mais ajudamos vocês hoje?}}"
JANELA_DE_SINAIS = 90
CHANCE_ALTA_PCT = 50
MAX_GRAFICOS_NO_MODELO = 6
MAX_BARRAS = 6


def carregar_fatos(pasta: Path) -> tuple:
    data, resumo = ultima_rodada(pasta)
    caminho = pasta / "4-dados" / "rodadas" / data.isoformat() / "contas.json"
    if not caminho.exists():
        raise ErroDeUso(f"a rodada de {data.isoformat()} é de antes desta função. Para incluir, gere de novo com rodada --refazer.")
    return data, resumo, json.loads(caminho.read_text(encoding="utf-8"))


def rotulo(item: dict) -> str:
    return f"{item['conta']} · {item['nome']}" if item.get("nome") else item["conta"]


def sinais_de_insatisfacao(item: dict) -> list:
    motivos = [s["texto"] for s in item["sinais"] if s["codigo"] in SINAIS_DE_INSATISFACAO]
    for rotina in item["rotinas"]:
        if rotina["bloco"] == "chamados" and rotina["subnota"] is not None and rotina["subnota"] <= 30:
            motivos.append(f"Muitos chamados: {rotina['rotina']} em {numero(rotina['agora'])}")
    if item["chance_churn_pct"] is not None and item["chance_churn_pct"] >= CHANCE_ALTA_PCT:
        motivos.append(f"O modelo aponta {item['chance_churn_pct']}% de chance de cancelar em 90 dias")
    return motivos


def caminho_da_conversa(item: dict) -> tuple:
    """Com sinal de insatisfação, recupera. Sem sinal, pede contrapartida. Sem dado, não dá para saber."""
    motivos = sinais_de_insatisfacao(item)
    if motivos:
        return "recuperacao", motivos
    if item["nota"] is None:
        return "sem_dados", []
    return "contrapartida", []


def rodadas_com_sinal(pasta: Path, data: dt.date, codigo: str, item: dict) -> tuple:
    """Quantas rodadas recentes mostraram sinal. No mensal, é assim que a insatisfação aparece."""
    inicio = data - dt.timedelta(days=JANELA_DE_SINAIS)
    total = com_sinal = 0
    for quando, pasta_rodada in rodadas_anteriores(pasta, data):
        if quando < inicio:
            continue
        valores = ler_valores(pasta_rodada).get(codigo)
        if valores is None:
            continue
        total += 1
        if valores.get("alertas") or valores.get("faixa") in ("pode_melhorar", "possivel_churn") or valores.get("situacao") == "empacado":
            com_sinal += 1
    total += 1
    if sinais_de_insatisfacao(item):
        com_sinal += 1
    return com_sinal, total


def valor_da_ficha(pasta: Path, codigo: str, titulo: str = "O que mais ajudamos vocês hoje?") -> str:
    ficha = pasta / "3-clientes" / codigo / "ficha.md"
    if not ficha.exists():
        return ""
    achado = re.search(rf"^##\s*{re.escape(titulo)}\s*$(.*?)(?=^##\s|\Z)", ficha.read_text(encoding="utf-8"), re.M | re.S)
    texto = achado.group(1).strip() if achado else ""
    return "" if not texto or "{{" in texto else texto


def texto_carteira(pasta: Path, data: dt.date, resumo: dict, fatos: dict) -> str:
    linhas = [f"Contas e receita, rodada de {data.isoformat()}."]
    chave = resumo["contas_chave"]
    linhas += ["", "Contas-chave:"]
    if chave.get("existe"):
        linhas.append(f"- {chave['quantas']} de {chave['de_um_total_de']} contas somam {chave['pct_receita']}% da receita.")
        for codigo in chave["contas"]:
            item = fatos.get(codigo)
            if not item:
                continue
            faltam = [] if valor_da_ficha(pasta, codigo) else ["valor ainda não levantado"]
            if not item["contatos_anotados"]["patrocinador"]:
                faltam.append("sem patrocinador anotado")
            linhas.append(f"- {rotulo(item)}: {moeda(item['receita'])}, nota {numero(item['nota']) if item['nota'] is not None else 'sem nota'}" + (f". Falta: {', '.join(faltam)}" if faltam else ""))
    elif chave.get("existe") is False:
        linhas.append(f"- Não há grupo pequeno que concentre a receita: são {chave['quantas']} das {chave['de_um_total_de']} contas para chegar a 80%.")
    else:
        linhas.append("- Ainda não dá para saber: falta a receita por conta.")

    janela = resumo["regras"]["renovacao proxima"]
    com_data = sorted((i for i in fatos.values() if i["dias_ate_renovar"] is not None and 0 <= i["dias_ate_renovar"] <= janela), key=lambda i: i["dias_ate_renovar"])
    linhas += ["", f"Renovações nos próximos {numero(janela)} dias:"]
    for item in com_data:
        caminho, motivos = caminho_da_conversa(item)
        leitura = {"recuperacao": "recuperar primeiro: " + ". ".join(motivos), "contrapartida": "sem sinal de insatisfação", "sem_dados": "sem nota: ainda não dá para ler"}[caminho]
        linhas.append(f"- {rotulo(item)}: em {item['dias_ate_renovar']} dias, {moeda(item['receita'])}. {leitura}")
    if not com_data:
        tem_data = any(i["dias_ate_renovar"] is not None for i in fatos.values())
        linhas.append("- Nenhuma na janela." if tem_data else "- Ainda não dá para saber: nenhuma conta tem data de renovação.")

    mensais = [i for i in fatos.values() if i["contrato"] == "mensal" and sinais_de_insatisfacao(i)]
    if mensais:
        linhas += ["", "Contrato mensal com sinal de insatisfação:"]
        for item in sorted(mensais, key=lambda i: -(i["receita"] or 0))[:10]:
            com_sinal, total = rodadas_com_sinal(pasta, data, item["conta"], item)
            linhas.append(f"- {rotulo(item)}: {moeda(item['receita'])}, sinal em {com_sinal} de {plural(total, 'rodada', 'rodadas')} dos últimos {JANELA_DE_SINAIS} dias. {'. '.join(sinais_de_insatisfacao(item))}")

    crescendo = sorted((i for i in fatos.values() if (i["sinais_bons"] or (i["chance_aumento_pct"] or 0) >= CHANCE_ALTA_PCT) and not sinais_de_insatisfacao(i)), key=lambda i: -(i["receita"] or 0))[:5]
    linhas += ["", "Onde há espaço para crescer, sem sinal de insatisfação (até 5):"]
    for item in crescendo:
        bons = [f"{b['rotina']}: de {numero(b['antes'])} para {numero(b['agora'])}" for b in item["sinais_bons"]]
        if item["chance_aumento_pct"] is not None:
            bons.append(f"o modelo aponta {item['chance_aumento_pct']}% de chance de aumentar a receita")
        linhas.append(f"- {rotulo(item)}: {moeda(item['receita'])}. {'. '.join(bons)}")
    if not crescendo:
        linhas.append("- Nenhuma conta com sinal bom nesta rodada.")

    oportunidades = resumo.get("oportunidades") or {}
    linhas += ["", f"Oportunidades de upgrade ({oportunidades.get('total', 0)} em {oportunidades.get('contas', 0)} contas; até 10):"]
    for o in (oportunidades.get("lista") or [])[:10]:
        nome = fatos[o["conta"]] if o["conta"] in fatos else o
        aviso = ". Resolva a insatisfação primeiro" if o["com_insatisfacao"] else ""
        linhas.append(f"- {rotulo(nome)}: {o['oportunidade']}. {o['detalhe']}{aviso}")
    if not oportunidades.get("lista"):
        linhas.append("- Nenhuma nesta rodada.")
    return "\n".join(linhas)


def _leitura_da_renovacao(item: dict, com_sinal: int, total: int) -> list:
    linhas = ["## A conversa de renovação", ""]
    if item["contrato"] == "mensal":
        linhas += [f"Contrato mensal: não há uma data em que o cliente decide. A insatisfação acumula por meses até cancelar. Sinal em {com_sinal} de {plural(total, 'rodada', 'rodadas')} dos últimos {JANELA_DE_SINAIS} dias.", ""]
    elif item["dias_ate_renovar"] is not None:
        linhas += [f"Renova em {item['dias_ate_renovar']} dias. No contrato anual, a renovação é o momento em que a empresa decide se continua.", ""]
    else:
        linhas += ["{{quando renova e qual o tipo de contrato: não veio no export}}", ""]
    caminho, motivos = caminho_da_conversa(item)
    if caminho == "recuperacao":
        linhas += ["**Se pedirem desconto: recuperar primeiro.** A conta mostra sinal de insatisfação:", ""]
        linhas += [f"- {m}" for m in motivos] + ["", "Envolva a liderança e trace um plano de recuperação antes de falar de preço. O desconto pode entrar, com o foco de recuperar a confiança.", ""]
    elif caminho == "contrapartida":
        linhas += ["**Se pedirem desconto: pedir contrapartida.** Não há sinal de insatisfação: o pedido parece corte de custo ou pressão. Peça algo que interesse à empresa: prazo, volume ou aumento da carteira. Exemplo: menos por usuário, com mais usuários.", ""]
    else:
        linhas += ["**Se pedirem desconto: ainda não dá para ler a conta.** Ela não tem nota. Descubra com o responsável se há insatisfação antes de responder.", ""]
    linhas += ["Em qualquer caso, levante o valor antes: entenda o que a solução significa para este cliente. Isso não fica só para a renovação.", ""]
    return linhas


def tabela_de_fatos(item: dict) -> list:
    contatos = [papel.replace("_", "-") for papel, tem in item["contatos_anotados"].items() if tem]
    renova = f"em {item['dias_ate_renovar']} dias ({item['renovacao']})" if item["dias_ate_renovar"] is not None else "sem data"
    linhas = ["## Fatos da conta", ""]
    linhas += _tabela(
        ["item", "valor"],
        [
            ["Nota", f"{numero(item['nota'])} ({item['faixa'].replace('_', ' ')}, confiança {item['confianca']})" if item["nota"] is not None else "sem nota"],
            ["Receita", moeda(item["receita"]) + (f" ({numero(item['pct_receita'])}% da carteira)" if item["pct_receita"] is not None else "")],
            ["Contrato", item["contrato"] or "a preencher"],
            ["Renovação", renova],
            ["Etapa", f"{item['etapa']}, {item['situacao']}" if item["etapa"] else item["situacao"]],
            ["Responsável", item["responsavel"] or "a preencher"],
            ["Sem contato há", f"{item['dias_sem_contato']} dias" if item["dias_sem_contato"] is not None else "a preencher"],
            ["Contatos anotados", ", ".join(contatos) or "nenhum"],
        ],
    )
    medidas = [r for r in item["rotinas"] if r["agora"] is not None]
    if medidas:
        linhas += ["## As rotinas", ""]
        linhas += _tabela(["rotina", "esperado", "antes", "agora"], [[r["rotina"], numero(r["esperado"]) if r["esperado"] is not None else "", numero(r["antes"]) if r["antes"] is not None else "", numero(r["agora"])] for r in medidas])
    return linhas


def serie_da_rotina(pasta: Path, data: dt.date, codigo: str, rotina: dict) -> list:
    """Os números da rotina nas rodadas, do mais antigo ao mais novo. Rodada sem o dado fica de fora: nada é preenchido por conta."""
    coluna = f"ind:{rotina['id']}"
    pontos = []
    for quando, pasta_rodada in rodadas_anteriores(pasta, data):
        try:
            pontos.append((quando.strftime("%d/%m"), float(ler_valores(pasta_rodada).get(codigo, {}).get(coluna))))
        except (TypeError, ValueError):
            continue
    if rotina["agora"] is not None:
        if not pontos and rotina["antes"] is not None:
            pontos.append(("Período anterior", rotina["antes"]))
        pontos.append((data.strftime("%d/%m"), rotina["agora"]))
    return pontos[-MAX_BARRAS:]


def rotinas_para_grafico(pasta: Path, data: dt.date, item: dict) -> tuple:
    """O que o modelo sugere mostrar: o que subiu vai para o que o cliente ganhou, e o que caiu para onde ainda tem espaço. Chamados e o que ficou igual ficam de fora."""
    variacoes = []
    for rotina in item["rotinas"]:
        serie = serie_da_rotina(pasta, data, item["conta"], rotina)
        if rotina["bloco"] != "chamados" and len(serie) >= 2 and serie[-1][1] != serie[0][1]:
            variacoes.append(((serie[-1][1] - serie[0][1]) / (abs(serie[0][1]) or 1), rotina["rotina"]))
    variacoes.sort(key=lambda v: -v[0])
    subiu = [nome for variacao, nome in variacoes if variacao > 0]
    caiu = [nome for variacao, nome in reversed(variacoes) if variacao < 0]
    return subiu[:MAX_GRAFICOS_NO_MODELO], caiu[:MAX_GRAFICOS_NO_MODELO]


def texto_reuniao(pasta: Path, data_rodada: dt.date, item: dict, tipo: str, hoje: dt.date) -> str:
    codigo = item["conta"]
    com_sinal, total = rodadas_com_sinal(pasta, data_rodada, codigo, item)
    motivo_compra = valor_da_ficha(pasta, codigo, "Motivo da compra")
    valor = valor_da_ficha(pasta, codigo)
    linhas = [f"# Reunião de {NOME_TIPO[tipo]} com {rotulo(item)}, {hoje.isoformat()}", "", f"Dados da rodada de {data_rodada.isoformat()}.", ""]
    linhas += ["## O que fazer", "", "- Preencher os campos entre chaves e o roteiro.", "- Depois da reunião, anotar aqui e na ficha o que foi combinado, com responsável e data.", ""]
    linhas += ["## O que foi conversado", "", "- Nada ainda.", ""]
    linhas += tabela_de_fatos(item)
    medidas = [r for r in item["rotinas"] if r["agora"] is not None]
    linhas += ["## Sinais", ""]
    insatisfacao = sinais_de_insatisfacao(item)
    linhas += [f"- Atenção: {s}." for s in insatisfacao] or ["- Nenhum sinal de insatisfação nesta rodada."]
    linhas += [f"- Bom sinal: {b['rotina']}, de {numero(b['antes'])} para {numero(b['agora'])}." for b in item["sinais_bons"]]
    if item["chance_aumento_pct"] is not None:
        linhas += [f"- O modelo aponta {item['chance_aumento_pct']}% de chance de aumentar a receita em 90 dias. É chance, não certeza."]
    linhas += [""]
    linhas += ["## O valor para este cliente", ""]
    linhas += [f"**O que mais ajudamos vocês hoje?** {valor or MARCA_VALOR}", "", f"**Por que comprou:** {motivo_compra or '{{anote na ficha: por que comprou e o que foi prometido}}'}", ""]
    chamados = [r for r in medidas if r["bloco"] == "chamados"]
    if chamados:
        linhas += ["**Chamados:** " + "; ".join(f"{r['rotina']}: {numero(r['agora'])} abertos no período" for r in chamados) + ". Resolvidos: {{traga do sistema, para o cliente ver a proporção}}.", ""]
    linhas += ["**Resultado que ajudamos a alcançar:** {{o número do cliente. Sem número, pergunte a ele}}", ""]
    if item.get("oportunidades"):
        linhas += ["## Oportunidades mapeadas", "", "Confirme antes de falar: se a área já está no plano do cliente, é adoção, não upgrade.", ""]
        for o in item["oportunidades"]:
            linhas.append(f"- **{o['oportunidade']}.** {o['detalhe']}." + (f" O que oferecer: {o['oferta']}." if o["oferta"] else ""))
        linhas += [""]
    if tipo == "renovacao":
        linhas += _leitura_da_renovacao(item, com_sinal, total)
    if tipo == "expansao" and insatisfacao:
        linhas += ["> Esta conta mostra sinal de insatisfação. Resolva isso antes de propor crescimento: empurrar agora vira telemarketing.", ""]
    linhas += ["## Roteiro da conversa", ""]
    linhas += [
        "1. **O que o cliente já ganhou, com o número dele:** {{preencher}}",
        "2. **Onde ainda tem espaço (o que vende, o que caiu, o que não usa):** {{preencher}}",
        "3. **Uma ação só:** {{preencher}}",
        "4. **O resultado esperado e quando voltamos para mostrar:** {{preencher}}",
        "",
    ]
    linhas += ["## Slides", "", "Isto vai para o cliente: nada de nota, risco, chance do modelo nem conversa interna.", ""]
    linhas += ["Cada ### é um passo da conversa, e o resumo do início da apresentação sai sozinho da primeira linha de cada um. Essa linha vira a frase grande: escreva nela a conclusão. Para destacar palavras, use **assim**; sem isso, os números se destacam sozinhos.", ""]
    linhas += ["`Gráfico: nome da rotina` sai em barras, com os números das rodadas, e `Gráfico:` em branco só deixa o espaço. `Print: o que ele mostra` deixa o espaço para colar a imagem no PowerPoint. Pode pôr quantos precisar: o script abre mais slides no mesmo passo. Ao lado de gráfico ou print, até 3 linhas de texto. Sem print, apague a linha.", ""]
    linhas += [f"Capa: {CAPA[tipo]}", f"Cliente: {codigo}", ""]
    subiu, caiu = rotinas_para_grafico(pasta, data_rodada, item)
    slides = (
        ("O que vocês já ganharam", ["- {{o número do cliente}}", "", *([f"Gráfico: {nome}" for nome in subiu] or ["Gráfico:"]), "Print: {{o que este print mostra}}"]),
        ("Onde ainda tem espaço", ["- {{o que vende, o que caiu, o que não usa}}", *(["", *[f"Gráfico: {nome}" for nome in caiu]] if caiu else [])]),
        ("Próximos passos", ["- {{uma ação só}}"]),
        ("O que esperamos", ["- {{o resultado e quando voltamos para mostrar}}"]),
    )
    for titulo, conteudo in slides:
        linhas += [f"### {titulo}", "", *conteudo, ""]
    return "\n".join(linhas)


def criar_reuniao(pasta: Path, codigo: str, tipo: str, hoje: dt.date, refazer: bool = False) -> tuple:
    if tipo not in TIPOS:
        raise ErroDeUso("use --tipo revisao, renovacao ou expansao.")
    data_rodada, _, fatos = carregar_fatos(pasta)
    item = fatos.get(codigo)
    if item is None:
        raise ErroDeUso(f"não achei a conta {codigo} entre as contas ativas da rodada de {data_rodada.isoformat()}.")
    nova_ficha(pasta, codigo)
    caminho = pasta / "3-clientes" / codigo / "reunioes" / f"{hoje.isoformat()}-{tipo}.md"
    texto = texto_reuniao(pasta, data_rodada, item, tipo, hoje)
    criou = refazer or not caminho.exists()
    if criou:
        caminho.write_text(texto, encoding="utf-8")
    return caminho, texto, criou
