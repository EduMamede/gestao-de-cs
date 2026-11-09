"""Melhoria contínua: o que cresce, quem saiu e com quem conversar. Só conta: o porquê vem da conversa.

No modo protegido, tema e motivo viram códigos como TEMA-02. Coluna com valores demais parece texto livre e fica de fora.
"""

from __future__ import annotations

import datetime as dt
import statistics

from .leitura import normalizar
from .medir import FAIXA_VERDE, MOTIVOS_VAGOS, _eh_arquivo_de_eventos, arredondar
from .oportunidades import SINAIS_DE_INSATISFACAO

JANELA = 30
MUDANCA_MINIMA_PCT = 10
MINIMO_DE_CASOS = 5
MAX_TEMAS = 30  # acima disso, a coluna parece texto livre
MIN_CONTAS_POR_GRUPO = 5
DIAS_DE_CONTA_NOVA = 90
DIAS_DE_EX_CLIENTE = 180
TAMANHO_DO_GRUPO = 10


def primeiro_valor(r) -> list:
    """Quanto tempo a conta levou até a primeira rotina. Comparar quem ficou com quem saiu calibra os prazos da etapa."""
    saida = []
    for ind in r.cfg.indicadores:
        if ind.bloco != "rotina" or ind.direcao != "bom" or not _eh_arquivo_de_eventos(ind, r.cfg):
            continue
        grupos: dict = {"ficou": [], "saiu": []}
        for conta in r.contas:
            inicio = conta.campos.get("data_inicio")
            datas = next((v for k, v in conta.eventos.items() if k.casefold() == ind.arquivo.casefold()), [])
            depois = [d for d in datas if inicio is not None and d >= inicio]
            if depois:
                grupos["ficou" if conta.status == "ativa" else "saiu"].append((min(depois) - inicio).days)
        if len(grupos["ficou"]) < MIN_CONTAS_POR_GRUPO or len(grupos["saiu"]) < MIN_CONTAS_POR_GRUPO:
            continue
        saida.append(
            {
                "rotina": ind.rotina,
                "dias_de_quem_ficou": arredondar(statistics.median(grupos["ficou"])),
                "dias_de_quem_saiu": arredondar(statistics.median(grupos["saiu"])),
                "contas_que_ficaram": len(grupos["ficou"]),
                "contas_que_sairam": len(grupos["saiu"]),
            }
        )
    return saida


def o_que_mudou(r) -> list:
    """A soma de cada rotina na carteira, agora e antes. Só com as contas que têm os dois números."""
    saida = []
    for ind in r.cfg.indicadores:
        pares = [(c.medicoes.get(ind.id), c.antes.get(ind.id)) for c in r.ativas]
        pares = [(a, b) for a, b in pares if isinstance(a, (int, float)) and isinstance(b, (int, float))]
        if len(pares) < MIN_CONTAS_POR_GRUPO:
            continue
        agora, antes = sum(p[0] for p in pares), sum(p[1] for p in pares)
        if antes <= 0 or 100 * abs(agora - antes) / antes < MUDANCA_MINIMA_PCT:
            continue
        subiu = agora > antes
        saida.append(
            {
                "rotina": ind.rotina,
                "bloco": ind.bloco,
                "contas": len(pares),
                "antes": arredondar(antes, 1),
                "agora": arredondar(agora, 1),
                "variacao_pct": arredondar(100 * (agora - antes) / antes),
                "leitura": "preocupa" if subiu == (ind.direcao == "ruim") else "melhorou",
            }
        )
    saida.sort(key=lambda m: (m["leitura"] != "preocupa", -abs(m["variacao_pct"])))
    return saida


def _temas_que_crescem(r) -> list:
    por_arquivo: dict = {}
    for conta in r.contas:
        for arquivo, registros in conta.temas_evento.items():
            por_arquivo.setdefault(arquivo, []).extend(registros)
    saida = []
    agora_ini = r.data - dt.timedelta(days=JANELA)
    antes_ini = r.data - dt.timedelta(days=2 * JANELA)
    for arquivo, registros in por_arquivo.items():
        rotulos = {normalizar(t): t for _, t in registros}
        if len(rotulos) > MAX_TEMAS:
            r.avisos.append(f"A coluna de tema de '{arquivo}' tem mais de {MAX_TEMAS} valores diferentes e parece texto livre. Ela ficou de fora.")
            continue
        for chave, original in rotulos.items():
            agora = sum(1 for d, t in registros if normalizar(t) == chave and agora_ini < d <= r.data)
            antes = sum(1 for d, t in registros if normalizar(t) == chave and antes_ini < d <= agora_ini)
            if agora + antes < MINIMO_DE_CASOS or agora <= antes:
                continue
            item = {"arquivo": arquivo, "tema": r.cofre.codigo_tema(original), "antes": antes, "agora": agora, "variacao_pct": arredondar(100 * (agora - antes) / antes) if antes else None}
            if r.modo == "aberto":
                item["nome"] = original
            saida.append(item)
    saida.sort(key=lambda t: -(t["agora"] - t["antes"]))
    return saida


def _quem_saiu(r) -> dict:
    datas = [c.campos["data_cancelamento"] for c in r.canceladas if c.campos.get("data_cancelamento")]

    def entre(inicio: int, fim: int) -> int:
        return sum(1 for d in datas if r.data - dt.timedelta(days=fim) < d <= r.data - dt.timedelta(days=inicio))

    motivos: dict = {}
    vagos = 0
    for conta in r.canceladas:
        motivo = conta.campos.get("motivo_cancelamento")
        if motivo is None or normalizar(motivo) in MOTIVOS_VAGOS:
            vagos += 1
            continue
        chave = r.cofre.codigo_tema(motivo)
        item = motivos.setdefault(chave, {"motivo": chave, "contas": 0})
        if r.modo == "aberto":
            item["nome"] = str(motivo).strip()
        item["contas"] += 1
    return {
        "ultimos_30_dias": entre(0, 30),
        "30_dias_antes": entre(30, 60),
        "ultimos_90_dias": entre(0, 90),
        "90_dias_antes": entre(90, 180),
        "sem_motivo_especifico": vagos,
        "motivos": sorted(motivos.values(), key=lambda m: -m["contas"]),
    }


def _grupos(r) -> dict:
    """Com quem conversar. A ordem é pela receita, e o tamanho é o de uma lista que dá para ligar."""

    def por_receita(contas: list) -> list:
        return [c.codigo for c in sorted(contas, key=lambda c: (-(c.receita or 0), c.codigo))[:TAMANHO_DO_GRUPO]]

    def com_sinal(conta) -> bool:
        return any(s[0] in SINAIS_DE_INSATISFACAO for s in conta.sinais)

    def dias_desde(data) -> int:
        return (r.data - data).days

    grupos = {
        "engajados": por_receita([c for c in r.ativas if c.nota is not None and c.nota >= FAIXA_VERDE and not com_sinal(c)]),
        "novos": por_receita([c for c in r.ativas if c.campos.get("data_inicio") and dias_desde(c.campos["data_inicio"]) <= DIAS_DE_CONTA_NOVA]),
        "ex_clientes": por_receita([c for c in r.canceladas if c.campos.get("data_cancelamento") and dias_desde(c.campos["data_cancelamento"]) <= DIAS_DE_EX_CLIENTE]),
        "promotores": por_receita([c for c in r.ativas if c.campos.get("nps") is not None and c.campos["nps"] >= 9]),
        "detratores": por_receita([c for c in r.ativas if c.campos.get("nps") is not None and c.campos["nps"] <= 6]),
    }
    return grupos


def dados_de_melhoria(r) -> dict:
    return {"o_que_mudou": o_que_mudou(r), "temas_que_crescem": _temas_que_crescem(r), "quem_saiu": _quem_saiu(r), "primeiro_valor": primeiro_valor(r), "grupos": _grupos(r)}
