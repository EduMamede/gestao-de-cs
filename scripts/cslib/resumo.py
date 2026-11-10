"""O resumo da conta antes de uma conversa: uma página com os últimos 90 dias (pedido do Eduardo em 10/11/2026).

Sai só do que já existe: as rodadas, a ficha, a mesa, as tarefas e as reuniões. Nada de IA e nenhum número
inventado: o que não tem dado fica dito como "sem dado". As perguntas saem de regras fixas, a partir dos fatos.
O arquivo é refeito a cada vez, como a página do dia: o que a pessoa quiser guardar vai para a ficha.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from . import ErroDeUso, plural
from . import config as config_mod
from .contas import carregar_fatos, rotulo, sinais_de_insatisfacao, valor_da_ficha
from .medir import ler_formula_anterior, ler_valores, rodadas_anteriores
from .mesa import em_aberto, ler_data, ler_itens, linha_em_aberto
from .pasta import modo_privacidade
from .privacidade import Cofre
from .relatorios import moeda, numero
from .tarefas import abertas, ler_tarefas

JANELA = 90
MAX_POR_BLOCO = 5
MAX_PERGUNTAS = 5
QUEDA_QUE_PERGUNTA = 0.2  # a rotina caiu 20% ou mais: vale perguntar o que mudou
DIAS_SEM_CONTATO = 30
RENOVACAO_PERTO = 120
NOMES_DA_FAIXA = {"saudavel": "saudável", "pode_melhorar": "pode melhorar", "possivel_churn": "possível churn", "sem_nota": "sem nota"}


def _curta(data: dt.date) -> str:
    return data.strftime("%d/%m")


def _numero_da_celula(linha: dict, coluna: str):
    try:
        return float(linha.get(coluna))
    except (TypeError, ValueError):
        return None


def _historico(pasta: Path, data: dt.date, codigo: str) -> list:
    """As rodadas da janela que têm a conta, da mais antiga para a mais nova, incluindo a última."""
    saida = []
    for quando, caminho in rodadas_anteriores(pasta, data + dt.timedelta(days=1)):
        if quando < data - dt.timedelta(days=JANELA):
            continue
        linha = ler_valores(caminho).get(codigo)
        if linha is not None:
            saida.append((quando, caminho, linha))
    return saida


def _em_uma_linha(item: dict, historico: list, nome_de) -> str:
    faixa = NOMES_DA_FAIXA.get(item["faixa"], item["faixa"])
    nota = f"nota {numero(item['nota'])} ({faixa})" if item["nota"] is not None else "sem nota"
    tendencia = ""
    if len(historico) >= 2:
        (q0, c0, l0), (_, c1, _) = historico[0], historico[-1]
        antes = _numero_da_celula(l0, "nota")
        if ler_formula_anterior(c0) != ler_formula_anterior(c1):
            tendencia = ", e a fórmula mudou na janela, então a nota não se compara"
        elif antes is not None and item["nota"] is not None:
            tendencia = ", estável desde " + _curta(q0) if antes == item["nota"] else f", de {numero(antes)} desde {_curta(q0)}"
    elif historico:
        tendencia = ", primeira rodada: ainda sem histórico"
    renova = f"renova em {ler_data(item['renovacao']).strftime('%d/%m/%Y')}" if item.get("renovacao") else ("contrato mensal" if item.get("contrato") == "mensal" else "sem data de renovação")
    return f"{nome_de(item['conta'])}: {nota}{tendencia}. {moeda(item['receita'])}, {renova}."


def _mudancas(item: dict, historico: list, cfg) -> tuple:
    """Devolve (linhas, quedas). Quedas são as rotinas que caíram e merecem pergunta."""
    direcao = {i.id: i.direcao for i in cfg.indicadores}
    linhas, quedas = [], []
    if len(historico) < 2:
        return ["- Ainda sem rodada anterior na janela para comparar."], quedas
    q0, _, l0 = historico[0]
    for rotina in item["rotinas"]:
        antes, agora = _numero_da_celula(l0, f"ind:{rotina['id']}"), rotina["agora"]
        if antes is None or agora is None or antes == agora:
            continue
        ruim = direcao.get(rotina["id"]) == "ruim"
        piorou = (agora < antes) != ruim
        linhas.append(f"- {rotina['rotina']}: de {numero(antes)} para {numero(agora)} desde {_curta(q0)}{', piorou' if piorou else ', melhorou'}.")
        if piorou and rotina["bloco"] != "chamados" and antes > 0 and (antes - agora) / antes >= QUEDA_QUE_PERGUNTA:
            quedas.append((rotina["rotina"], q0))
        if piorou and rotina["bloco"] == "chamados":
            quedas.append((rotina["rotina"], q0))
    return (linhas or ["- Nenhuma rotina mudou na janela."]), quedas


def _secao_da_ficha(texto: str, titulo: str) -> str:
    achado = re.search(rf"^##\s*{re.escape(titulo)}\s*$(.*?)(?=^##\s|\Z)", texto, re.M | re.S)
    return achado.group(1) if achado else ""


def _contatos(pasta: Path, codigo: str) -> list:
    ficha = pasta / "3-clientes" / codigo / "ficha.md"
    if not ficha.exists():
        return []
    saida = []
    for linha in _secao_da_ficha(ficha.read_text(encoding="utf-8"), "Contatos").splitlines():
        c = [x.strip() for x in linha.strip().strip("|").split("|")]
        if len(c) >= 2 and c[0] and c[0] != "papel" and not set(c[0]) <= set("- ") and c[1] and "{{" not in c[1]:
            saida.append(f"{c[0]}: {c[1]}" + (f" ({c[2]})" if len(c) > 2 and c[2] else ""))
    return saida


def _conversas(pasta: Path, codigo: str) -> list:
    """As anotações de "O que foi conversado", da ficha, das reuniões e dos planos. Devolve (data do arquivo, origem, linha)."""
    base = pasta / "3-clientes" / codigo
    fontes = [(None, "ficha", base / "ficha.md")]
    for caminho in sorted(list(base.glob("plano-*.md")) + list((base / "reunioes").glob("*.md"))):
        achado = re.search(r"\d{4}-\d{2}-\d{2}", caminho.name)
        origem = "plano" if caminho.name.startswith("plano-") else "reunião"
        fontes.append((ler_data(achado.group(0)) if achado else None, origem, caminho))
    saida = []
    for data, origem, caminho in fontes:
        if not caminho.exists():
            continue
        for linha in _secao_da_ficha(caminho.read_text(encoding="utf-8"), "O que foi conversado").splitlines():
            linha = linha.strip()
            if linha.startswith("- ") and "{{" not in linha and linha != "- Nada ainda.":
                saida.append((data or dt.date.min, origem, linha[2:]))
    return saida


def _perguntas(item: dict, quedas: list, valor: str, contatos: list, hoje: dt.date) -> list:
    saida = []
    for rotina, desde in quedas:
        saida.append(f"O que mudou em {rotina} desde {_curta(desde)}?")
    if item["etapa"] and item["situacao"] == "empacado":
        if item.get("motivo_parada") == "nosso":
            saida.append(f"Antes da conversa: destravar do nosso lado o que está parado em {item['etapa']}.")
        else:
            saida.append(f"O que falta para fechar a etapa {item['etapa']}?")
    if not valor:
        saida.append("O que mais ajudamos vocês hoje?")
    tem_patrocinador = item["contatos_anotados"]["patrocinador"] or any(c.lower().startswith("patrocinador") for c in contatos)
    renova = ler_data(item.get("renovacao"))
    if renova and 0 <= (renova - hoje).days <= RENOVACAO_PERTO:
        saida.append("O que precisa acontecer até a renovação para valer a pena continuar?")
    if not tem_patrocinador:
        saida.append("Quem decide a renovação do lado de vocês?")
    if item["dias_sem_contato"] is not None and item["dias_sem_contato"] > DIAS_SEM_CONTATO:
        saida.append("O que aconteceu desde a nossa última conversa?")
    for oportunidade in item["oportunidades"][:1]:
        if oportunidade["tipo"] == "sem_uso":
            nome = oportunidade["oportunidade"].removesuffix(" sem uso")
            saida.append(f"Como vocês fazem {nome} hoje?")
    return saida[:MAX_PERGUNTAS]


def texto_resumo(pasta: Path, codigo: str, hoje: dt.date, nome_de) -> str:
    data_rodada, _, fatos = carregar_fatos(pasta)
    item = fatos.get(codigo)
    if item is None:
        raise ErroDeUso(f"não achei a conta {codigo} entre as contas ativas da rodada de {data_rodada.isoformat()}.")
    cfg = config_mod.carregar(pasta)
    historico = _historico(pasta, data_rodada, codigo)
    valor = valor_da_ficha(pasta, codigo)
    motivo = valor_da_ficha(pasta, codigo, "Motivo da compra")
    contatos = _contatos(pasta, codigo)

    linhas = [f"# Resumo de {nome_de(codigo)}, {hoje.strftime('%d/%m/%Y')}", "", f"Os últimos {JANELA} dias, com os dados da rodada de {data_rodada.strftime('%d/%m/%Y')}.", ""]
    if (hoje - data_rodada).days > 7:
        linhas += [f"> A rodada tem {plural((hoje - data_rodada).days, 'dia', 'dias')}: os números podem ter mudado.", ""]
    linhas += ["## Em uma linha", "", _em_uma_linha(item, historico, nome_de), ""]

    mudancas, quedas = _mudancas(item, historico, cfg)
    linhas += ["## O que mudou", ""] + mudancas[:MAX_POR_BLOCO]
    linhas += [f"- Atenção: {s}." for s in sinais_de_insatisfacao(item)][:MAX_POR_BLOCO]
    linhas += [""]

    linhas += ["## O que já ganharam", ""]
    linhas += [f"- **O que mais ajudamos vocês hoje?** {valor}" if valor else "- **O que mais ajudamos vocês hoje?** Ainda não está na ficha."]
    linhas += [f"- **Por que compraram:** {motivo}" if motivo else "- **Por que compraram:** ainda não está na ficha.", ""]

    linhas += ["## Em aberto", ""]
    em_aberto_linhas = [f"- Na mesa: {linha_em_aberto(pasta, i, nome_de)}." for i in em_aberto(ler_itens(pasta)) if i["conta"] == codigo]
    for t in abertas(ler_tarefas(pasta)):
        if t["conta"] == codigo:
            quando = ler_data(t["ate"])
            em_aberto_linhas.append(f"- Tarefa {t['tarefa']}{', até ' + _curta(quando) if quando else ''}: {t['texto']}.")
    em_aberto_linhas += [f"- Oportunidade: {o['oportunidade']}. {o['detalhe']}." + (" Resolva a insatisfação primeiro." if o["com_insatisfacao"] else "") for o in item["oportunidades"]]
    # chamado alto já aparece em "O que mudou", como atenção: aqui entra só o que não foi dito
    ja_dito = " ".join(sinais_de_insatisfacao(item))
    chamados = [r for r in item["rotinas"] if r["bloco"] == "chamados" and r["agora"] is not None and r["rotina"] not in ja_dito]
    em_aberto_linhas += [f"- {r['rotina']}: {numero(r['agora'])} no período medido." for r in chamados]
    linhas += em_aberto_linhas[:MAX_POR_BLOCO] or ["- Nada em aberto registrado."]
    if len(em_aberto_linhas) > MAX_POR_BLOCO:
        linhas += [f"- Mais {len(em_aberto_linhas) - MAX_POR_BLOCO} itens: veja a mesa e as tarefas."]
    linhas += [""]

    linhas += ["## Quem é quem", ""]
    linhas += [f"- {c}" for c in contatos] or ["- Nenhum contato anotado na ficha."]
    if item["responsavel"]:
        linhas += [f"- Responsável do nosso lado: {nome_de(item['responsavel'])}."]
    sem_contato = f"{item['dias_sem_contato']} dias" if item["dias_sem_contato"] is not None else "sem dado"
    proximo = ler_data(item.get("proximo_contato"))
    linhas += [f"- Sem contato há: {sem_contato}." + (f" Próximo contato marcado para {_curta(proximo)}." if proximo else ""), ""]

    linhas += ["## A última conversa", ""]
    conversas = sorted(_conversas(pasta, codigo), key=lambda c: c[0])[-3:]
    linhas += [f"- {'Na ' + origem if origem != 'ficha' else 'Na ficha'}{' de ' + _curta(data) if data != dt.date.min else ''}: {texto}" for data, origem, texto in conversas] or ["- Nada anotado ainda. Depois da conversa, anote na ficha o que foi combinado."]
    linhas += [""]

    linhas += ["## O que perguntar", ""]
    linhas += [f"- {p}" for p in _perguntas(item, quedas, valor, contatos, hoje)] or ["- Nada puxa uma pergunta dos dados. Comece pelo que o cliente quer resolver agora."]
    linhas += ["", "_Resumo refeito pelo script a cada vez. O que você quiser guardar, anote na ficha da conta._", ""]
    return "\n".join(linhas)


def gravar_resumo(pasta: Path, codigo: str, hoje: dt.date, nome_de) -> tuple:
    texto = texto_resumo(pasta, codigo, hoje, nome_de)
    caminho = pasta / "3-clientes" / codigo / f"resumo-{hoje.isoformat()}.md"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(texto, encoding="utf-8")
    if modo_privacidade(pasta) == "protegido":  # a versão com os nomes reais, só para a pessoa
        copia = pasta / "com-nomes" / f"resumo-{codigo}-{hoje.isoformat()}.md"
        copia.parent.mkdir(exist_ok=True)
        copia.write_text(Cofre(pasta).restaurar(texto), encoding="utf-8")
    return caminho, texto


def resumos_das_reunioes(pasta: Path, hoje: dt.date, nome_de) -> list:
    """Deixa pronto o resumo de quem tem reunião hoje ou amanhã. Conta que saiu da carteira fica de fora."""
    feitos = []
    for caminho in sorted((pasta / "3-clientes").glob("CONTA-*/reunioes/*.md")):
        achado = re.fullmatch(r"(\d{4}-\d{2}-\d{2})-\w+\.md", caminho.name)
        data = ler_data(achado.group(1)) if achado else None
        codigo = caminho.parent.parent.name
        if not data or not 0 <= (data - hoje).days <= 1 or codigo in feitos:
            continue
        try:
            gravar_resumo(pasta, codigo, hoje, nome_de)
            feitos.append(codigo)
        except ErroDeUso:
            continue
    return feitos
