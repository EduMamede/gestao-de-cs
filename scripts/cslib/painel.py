"""Painel geral: as métricas para gerenciar o CS inteiro e a situação das metas.

Métrica sem dado fica None e vira 'a preencher'. Nunca sai um número estimado.
"""

from __future__ import annotations

import datetime as dt
import statistics

from .medir import Conta, arredondar
from .relatorios import moeda

# id -> (nome, unidade, melhor quando, como é calculado)
CATALOGO = {
    "contas_ativas": ("Contas ativas", "int", "maior", "contas que não cancelaram"),
    "receita_ativa": ("Receita ativa", "moeda", "maior", "soma da receita das contas ativas"),
    "nota_media": ("Nota média", "num", "maior", "média simples das contas com nota"),
    "nota_ponderada": ("Nota média pela receita", "num", "maior", "média das notas com peso pela receita"),
    "pct_saudaveis": ("Contas saudáveis", "pct", "maior", "contas com nota de 70 para cima, entre as que têm nota"),
    "pct_receita_saudavel": ("Receita em contas saudáveis", "pct", "maior", "receita das saudáveis sobre a receita das contas com nota"),
    "contas_sem_nota": ("Contas sem nota", "int", "menor", "contas sem dado suficiente para dar nota"),
    "receita_em_risco": ("Receita em possível churn", "moeda", "menor", "receita das contas com nota abaixo de 30"),
    "contas_empacadas": ("Contas empacadas", "int", "menor", "contas além do prazo da etapa"),
    "empacadas_nosso": ("Empacadas por nós", "int", "menor", "empacadas com motivo nosso"),
    "empacadas_cliente": ("Empacadas pelo cliente", "int", "menor", "empacadas com motivo do cliente"),
    "alertas_de_padrao": ("Alertas de mudança de padrão", "int", "menor", "contas que mudaram o próprio padrão para pior"),
    "renovacoes_90d": ("Renovações na janela", "int", None, "contas que renovam dentro da janela combinada"),
    "receita_renovando": ("Receita renovando na janela", "moeda", None, "receita das contas que renovam dentro da janela"),
    "churn_contas_30d": ("Churn de contas em 30 dias", "pct", "menor", "canceladas em 30 dias sobre as contas que existiam no início"),
    "churn_contas_90d": ("Churn de contas em 90 dias", "pct", "menor", "canceladas em 90 dias sobre as contas que existiam no início"),
    "churn_contas_12m": ("Churn de contas em 12 meses", "pct", "menor", "canceladas em 365 dias sobre as contas que existiam no início"),
    "churn_receita_30d": ("Churn de receita em 30 dias", "pct", "menor", "receita cancelada em 30 dias sobre a receita de quem existia no início"),
    "churn_receita_90d": ("Churn de receita em 90 dias", "pct", "menor", "receita cancelada em 90 dias sobre a receita de quem existia no início"),
    "churn_receita_12m": ("Churn de receita em 12 meses", "pct", "menor", "receita cancelada em 365 dias sobre a receita de quem existia no início"),
    "nps": ("NPS consolidado", "num", "maior", "promotores menos detratores, sobre quem respondeu. Serve para ver a tendência da base"),
    "nps_respostas": ("Respostas de NPS", "int", "maior", "contas com nota de NPS"),
    "chamados_total": ("Chamados no período", "int", "menor", "soma dos indicadores do bloco chamados"),
    "grr": ("Retenção bruta (GRR)", "pct", "maior", "receita mantida, sem contar expansão, sobre a receita anterior"),
    "nrr": ("Retenção líquida (NRR)", "pct", "maior", "receita atual, com expansão, sobre a receita anterior"),
}


def _churn(r, dias: int) -> tuple:
    # Export sem nenhuma cancelada quase sempre é export só de ativas. Dizer "churn 0%" seria inventar.
    if r.cfg.recompra or "data_cancelamento" not in r.campos_presentes or not r.canceladas:
        return None, None, None, None
    inicio = r.data - dt.timedelta(days=dias)
    tem_inicio = "data_inicio" in r.campos_presentes
    saidas = [c for c in r.canceladas if c.campos.get("data_cancelamento") and inicio < c.campos["data_cancelamento"] <= r.data]

    def existia(conta: Conta) -> bool:
        comecou = conta.campos.get("data_inicio")
        return not tem_inicio or comecou is None or comecou <= inicio

    base = [c for c in r.ativas if existia(c)] + [c for c in saidas if existia(c)]
    saidas_base = [c for c in saidas if existia(c)]
    if not base:
        return None, None, None, None
    churn_contas = arredondar(100 * len(saidas_base) / len(base), 1)
    detalhe_contas = f"{len(saidas_base)} de {len(base)} contas"
    receita_base = sum(c.receita or 0 for c in base)
    receita_saiu = sum(c.receita or 0 for c in saidas_base)
    if not receita_base or "receita" not in r.campos_presentes:
        return churn_contas, None, detalhe_contas, None
    return churn_contas, arredondar(100 * receita_saiu / receita_base, 1), detalhe_contas, f"{moeda(receita_saiu)} de {moeda(receita_base)}"


def _retencao(r) -> tuple:
    if "receita_anterior" not in r.campos_presentes:
        return None, None, None
    inicio = churn = reducao = expansao = 0.0
    for conta in r.contas:
        anterior = conta.campos.get("receita_anterior")
        if anterior is None or anterior <= 0:
            continue
        inicio += anterior
        atual = 0.0 if conta.status == "cancelada" else (conta.receita or 0.0)
        if atual <= 0:
            churn += anterior
        elif atual < anterior:
            reducao += anterior - atual
        else:
            expansao += atual - anterior
    if inicio <= 0:
        return None, None, None
    grr = arredondar(100 * (inicio - churn - reducao) / inicio, 1)
    nrr = arredondar(100 * (inicio - churn - reducao + expansao) / inicio, 1)
    return grr, nrr, {"inicio": inicio, "churn": churn, "reducao": reducao, "expansao": expansao, "fim": inicio - churn - reducao + expansao}


def _nps(r) -> tuple:
    notas = [c.campos["nps"] for c in r.ativas if c.campos.get("nps") is not None]
    if not notas:
        return None, 0
    promotores = sum(1 for n in notas if n >= 9)
    detratores = sum(1 for n in notas if n <= 6)
    return arredondar(100 * (promotores - detratores) / len(notas)), len(notas)


def calcular_painel(r) -> dict:
    ativas = r.ativas
    com_nota = [c for c in ativas if c.nota is not None]
    tem_receita = "receita" in r.campos_presentes
    receita_total = sum(c.receita or 0 for c in ativas) if tem_receita else None
    faixas = {}
    for chave in ("saudavel", "pode_melhorar", "possivel_churn", "sem_nota"):
        grupo = [c for c in ativas if c.faixa == chave]
        faixas[chave] = {"contas": len(grupo), "receita": sum(c.receita or 0 for c in grupo) if tem_receita else None}
    com_etapa = "etapa" in r.campos_presentes and r.cfg.etapas
    valores = {
        "contas_ativas": len(ativas),
        "receita_ativa": receita_total,
        "nota_media": arredondar(statistics.mean(c.nota for c in com_nota), 1) if com_nota else None,
        "pct_saudaveis": arredondar(100 * faixas["saudavel"]["contas"] / len(com_nota), 1) if com_nota else None,
        "contas_sem_nota": faixas["sem_nota"]["contas"] if r.cfg.indicadores else None,
        "alertas_de_padrao": len({a["conta"] for a in r.alertas_ruins}) if com_nota else None,
        "contas_empacadas": len(r.empacadas) if com_etapa else None,
        "empacadas_nosso": sum(1 for c in r.empacadas if c.motivo == "nosso") if com_etapa else None,
        "empacadas_cliente": sum(1 for c in r.empacadas if c.motivo == "do cliente") if com_etapa else None,
        "renovacoes_90d": len(r.renovacoes) if "renovacao" in r.campos_presentes else None,
        "receita_renovando": sum(x["receita"] or 0 for x in r.renovacoes) if "renovacao" in r.campos_presentes and tem_receita else None,
    }
    if tem_receita and com_nota:
        receita_com_nota = sum(c.receita or 0 for c in com_nota)
        valores["nota_ponderada"] = arredondar(sum((c.receita or 0) * c.nota for c in com_nota) / receita_com_nota, 1) if receita_com_nota else None
        valores["pct_receita_saudavel"] = arredondar(100 * (faixas["saudavel"]["receita"] or 0) / receita_com_nota, 1) if receita_com_nota else None
        valores["receita_em_risco"] = faixas["possivel_churn"]["receita"]
    else:
        valores["nota_ponderada"] = valores["pct_receita_saudavel"] = valores["receita_em_risco"] = None
    detalhes = {}
    for dias, sufixo in ((30, "30d"), (90, "90d"), (365, "12m")):
        contas, receita, detalhe_contas, detalhe_receita = _churn(r, dias)
        valores[f"churn_contas_{sufixo}"] = contas
        valores[f"churn_receita_{sufixo}"] = receita
        detalhes[f"churn_contas_{sufixo}"] = detalhe_contas
        detalhes[f"churn_receita_{sufixo}"] = detalhe_receita
    valores["nps"], valores["nps_respostas"] = _nps(r)
    if not valores["nps_respostas"]:
        valores["nps_respostas"] = None
    chamados = [i for i in r.cfg.indicadores if i.bloco == "chamados"]
    soma = [c.medicoes.get(i.id) for c in ativas for i in chamados]
    soma = [v for v in soma if isinstance(v, (int, float))]
    valores["chamados_total"] = arredondar(sum(soma)) if soma else None
    valores["grr"], valores["nrr"], cascata = _retencao(r)

    nao_se_aplica = set()
    if r.cfg.recompra:  # sem contrato: não há renovação nem cancelamento para contar
        nao_se_aplica |= {"renovacoes_90d", "receita_renovando", "grr", "nrr"} | {k for k in CATALOGO if k.startswith("churn_")}
        if not r.cfg.etapas:
            nao_se_aplica |= {"contas_empacadas", "empacadas_nosso", "empacadas_cliente"}
    metricas = []
    for id_, (nome, unidade, melhor, como) in CATALOGO.items():
        if id_ not in nao_se_aplica:
            metricas.append({"id": id_, "nome": nome, "valor": valores.get(id_), "unidade": unidade, "melhor_quando": melhor, "como": como, "detalhe": detalhes.get(id_)})

    por_responsavel = _agrupar(r, "responsavel", r.cofre.codigo_pessoa)
    por_segmento = _agrupar(r, "segmento", r.cofre.codigo_segmento)
    return {"metricas": metricas, "valores": valores, "faixas": faixas, "cascata": cascata, "por_responsavel": por_responsavel, "por_segmento": por_segmento}


def _agrupar(r, campo: str, codificar) -> list:
    if campo not in r.campos_presentes:
        return []
    grupos: dict = {}
    for conta in r.ativas:
        valor = conta.campos.get(campo)
        chave = codificar(valor) if valor else "sem informação"
        grupos.setdefault(chave, []).append(conta)
    saida = []
    for chave in sorted(grupos):
        contas = grupos[chave]
        notas = [c.nota for c in contas if c.nota is not None]
        saida.append(
            {
                "grupo": chave,
                "contas": len(contas),
                "receita": sum(c.receita or 0 for c in contas) if "receita" in r.campos_presentes else None,
                "nota_media": arredondar(statistics.mean(notas), 1) if notas else None,
                "empacadas": sum(1 for c in contas if c.situacao == "empacado"),
                "em_risco": sum(1 for c in contas if c.faixa == "possivel_churn"),
                "renovacoes": sum(1 for c in contas if any(x["conta"] == c.codigo for x in r.renovacoes)),
            }
        )
    return saida


def calcular_metas(r) -> list:
    saida = []
    valores = r.painel["valores"]
    for meta in r.cfg.metas:
        info = CATALOGO.get(meta.indicador)
        atual = valores.get(meta.indicador) if info else None
        melhor = "menor" if "menor" in meta.melhor_quando else ("maior" if "maior" in meta.melhor_quando else (info[2] if info else None))
        if info is None:
            situacao = "indicador não medido pela skill"
        elif atual is None:
            situacao = "sem dado"
        elif meta.alvo is None:
            situacao = "sem alvo"
        elif melhor == "menor":
            situacao = "atrás" if atual > meta.alvo else "no alvo"
        else:
            situacao = "atrás" if atual < meta.alvo else "no alvo"
        saida.append(
            {
                "meta": meta.meta,
                "indicador": meta.indicador,
                "alvo": meta.alvo,
                "atual": atual,
                "unidade": info[1] if info else "num",
                "melhor_quando": melhor,
                "prazo": meta.prazo,
                "responsavel": meta.responsavel,
                "situacao": situacao,
            }
        )
    ordem = {"atrás": 0, "sem dado": 1, "indicador não medido pela skill": 2, "sem alvo": 3, "no alvo": 4}
    saida.sort(key=lambda m: ordem.get(m["situacao"], 9))
    return saida
