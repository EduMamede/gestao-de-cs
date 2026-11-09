"""Grava os arquivos da rodada. No modo protegido, tudo aqui usa só códigos.

Todo .md abre com duas partes: "O que fazer" e "O que foi conversado".
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from . import plural
from .medir import NOME_FAIXAS, quem_age, arredondar
from .oportunidades import resumo_das_oportunidades
from .privacidade import escrever_csv


def moeda(valor) -> str:
    if valor is None:
        return "a preencher"
    inteiro = abs(valor - round(valor)) < 0.005
    texto = f"{valor:,.0f}" if inteiro else f"{valor:,.2f}"
    return "R$ " + texto.replace(",", "§").replace(".", ",").replace("§", ".")


def numero(valor) -> str:
    if valor is None:
        return "a preencher"
    valor = float(valor)
    if valor.is_integer():
        return f"{int(valor):,}".replace(",", ".")
    return f"{valor:.1f}".replace(".", ",")


def valor_formatado(valor, unidade: str) -> str:
    if valor is None:
        return "a preencher"
    if unidade == "moeda":
        return moeda(valor)
    if unidade == "pct":
        return f"{numero(valor)}%"
    return numero(valor)


def nome_para_ia(r, codigo: str) -> str:
    """Modo protegido: só o código. Modo aberto: código e nome."""
    if r.modo == "aberto":
        return f"{codigo} · {r.cofre.nome_de(codigo)}"
    return codigo


def dados_disponiveis(r) -> dict:
    """O que deu para medir. É o que separa 'nada de errado' de 'ainda não dá para saber'."""
    return {
        "nota": any(c.nota is not None for c in r.ativas),
        "etapa": any(c.situacao in ("no prazo", "empacado", "sem prazo") for c in r.ativas),
        "renovacao": "renovacao" in r.campos_presentes,
        "comparacao_de_padrao": r.comparacoes > 0,
        "canceladas": bool(r.canceladas),
    }


TITULOS_PREVISAO = {"churn": "Churn em 90 dias", "engajamento": "Engajamento", "incremento": "Aumento de receita em 90 dias"}
LISTA_PREVISAO = 20
SITUACAO_PREVISAO = {"sem_dados": "ainda não dá", "sem_ganho": "testado, sem ganho", "sem_biblioteca": "falta a biblioteca", "erro": "não rodou"}


def _frase_do_teste(teste: dict, casos: str, base: str, topo_pct: int) -> str:
    return f"Em {plural(len(teste['datas']), 'data passada', 'datas passadas')} que o modelo não tinha visto, de {teste['casos']} {casos}, {teste['pegou_modelo']} estavam entre as {topo_pct}% das contas mais apontadas. {base} apontaria {teste['pegou_base']}."


def resumo_das_previsoes(prev: dict) -> list[str]:
    """Uma linha por previsão: se está pronta e o que o teste mostrou. Serve para a tela, os .md e a planilha."""
    linhas = []
    topo = prev.get("topo_pct", 20)
    for nome in ("churn", "incremento"):
        bloco = prev.get(nome) or {}
        if bloco.get("status") == "ok":
            casos = "contas que cancelaram" if nome == "churn" else "contas que aumentaram a receita"
            linhas.append(f"{TITULOS_PREVISAO[nome]}: pronta. {_frase_do_teste(bloco['teste'], casos, 'A nota', topo)}")
        elif bloco:
            linhas.append(f"{TITULOS_PREVISAO[nome]}: {SITUACAO_PREVISAO[bloco['status']]}. {bloco['motivo']}")
    bloco = prev.get("engajamento") or {}
    if bloco.get("status") == "ok":
        for rotina in bloco["rotinas"]:
            for lado, casos in (("cai", "quedas"), ("sobe", "altas")):
                if rotina[lado]["status"] == "ok":
                    linhas.append(f"Engajamento, {rotina['rotina']}, {casos}: pronta. {_frase_do_teste(rotina[lado]['teste'], f'{casos} reais', 'O histórico da própria rotina', topo)}")
    elif bloco:
        linhas.append(f"{TITULOS_PREVISAO['engajamento']}: {SITUACAO_PREVISAO[bloco['status']]}. {bloco['motivo']}")
    return linhas


def montar_resumo(r) -> dict:
    def conta_base(codigo: str) -> dict:
        base = {"conta": codigo}
        if r.modo == "aberto":
            base["nome"] = r.cofre.nome_de(codigo)
        return base

    empacadas = []
    for c in r.empacadas:
        empacadas.append(
            {
                **conta_base(c.codigo),
                "responsavel": r.cofre.codigo_pessoa(c.campos["responsavel"]) if c.campos.get("responsavel") else None,
                "etapa": c.etapa,
                "dias_na_etapa": c.dias_etapa,
                "prazo": c.prazo,
                "motivo": c.motivo or "não informado",
                "quem_age": quem_age(c),
                "nota": c.nota,
                "receita": c.receita,
                "tem_proximo_passo": bool(c.campos.get("proximo_passo")),
                "proximo_contato": c.campos["data_proximo_contato"].isoformat() if c.campos.get("data_proximo_contato") else None,
            }
        )
    def alerta_publico(a):
        return {**conta_base(a["conta"]), **{k: v for k, v in a.items() if k != "conta"}}

    perdidas = dict(r.perdidas)
    if perdidas:
        perdidas["detalhes"] = [{**conta_base(d["conta"]), **{k: v for k, v in d.items() if k != "conta"}} for d in perdidas["detalhes"]]
    chave = dict(r.contas_chave)
    previsoes = dict(r.previsoes)
    for nome in TITULOS_PREVISAO:  # a lista inteira fica na planilha; aqui, o que cabe numa leitura
        bloco = previsoes.get(nome)
        if bloco and "contas" in bloco:
            lista = [{**conta_base(c["conta"]), **{k: v for k, v in c.items() if k != "conta"}} for c in bloco["contas"][:LISTA_PREVISAO]]
            previsoes[nome] = {**bloco, "contas": lista, "contas_no_total": len(bloco["contas"])}
    resumo = {
        "rodada": r.data.isoformat(),
        "modo_privacidade": r.modo,
        "rodada_anterior": r.rodada_anterior.isoformat() if r.rodada_anterior else None,
        "arquivos_lidos": r.arquivos_lidos,
        "recompra": r.cfg.recompra,
        "dados_disponiveis": dados_disponiveis(r),
        "contas": {
            "ativas": len(r.ativas),
            "canceladas": len(r.canceladas),
            "com_nota": sum(1 for c in r.ativas if c.nota is not None),
            "sem_nota": sum(1 for c in r.ativas if c.nota is None),
            "confianca": {g: sum(1 for c in r.ativas if c.nota is not None and c.grau == g) for g in ("alta", "média", "baixa")},
        },
        "faixas": r.painel["faixas"],
        "formula": r.formula,
        "regras": r.cfg.regras,
        "indicadores": [
            {
                "id": i.id,
                "rotina": i.rotina,
                "bloco": i.bloco,
                "criticidade": i.criticidade,
                "peso": i.peso,
                "contas_medidas": r.estado_indicadores[i.id]["medidos"],
                "contas_ativas": r.estado_indicadores[i.id]["total"],
            }
            for i in r.cfg.indicadores
        ],
        "prioridades": [{**conta_base(p["conta"]), **{k: v for k, v in p.items() if k != "conta"}} for p in r.prioridades],
        "empacadas": empacadas,
        "alertas_de_padrao": [alerta_publico(a) for a in r.alertas_ruins],
        "sinais_bons": [alerta_publico(a) for a in r.alertas_bons],
        "renovacoes": [{**conta_base(x["conta"]), **{k: v for k, v in x.items() if k != "conta"}} for x in r.renovacoes],
        "contas_chave": chave,
        "maiores_contas": [{**conta_base(m["conta"]), "receita": m["receita"]} for m in r.maiores],
        "conta_perdida": perdidas,
        "painel": {
            "metricas": r.painel["metricas"],
            "cascata_receita": r.painel["cascata"],
            "por_responsavel": r.painel["por_responsavel"],
            "por_segmento": r.painel["por_segmento"],
        },
        "metas": r.metas,
        "previsoes": previsoes,
        "oportunidades": resumo_das_oportunidades([{**conta_base(o["conta"]), **{k: v for k, v in o.items() if k != "conta"}} for o in r.oportunidades]),
        "melhoria": r.melhoria,
        "falta_medir": r.faltas,
        "avisos_sobre_os_dados": r.avisos,
    }
    if r.modo == "aberto":
        chave["nomes"] = {c: r.cofre.nome_de(c) for c in chave.get("contas", [])}
    return resumo


def _abertura(o_que_fazer: list[str]) -> list[str]:
    linhas = ["## O que fazer", ""]
    linhas += [f"- {item}" for item in o_que_fazer] or ["- Nada urgente nesta rodada."]
    linhas += ["", "## O que foi conversado", "", "- Nada ainda. Anote aqui o que for combinado sobre esta rodada.", ""]
    return linhas


def _tabela(cabecalho: list[str], linhas: list[list]) -> list[str]:
    saida = ["| " + " | ".join(cabecalho) + " |", "| " + " | ".join("---" for _ in cabecalho) + " |"]
    for linha in linhas:
        saida.append("| " + " | ".join(str(c).replace("|", "/") for c in linha) + " |")
    saida.append("")
    return saida


def texto_alertas(r) -> str:
    dados = dados_disponiveis(r)
    tem_como_ver = dados["nota"] or dados["etapa"]
    fazer = []
    for p in r.prioridades[:3]:
        fazer.append(f"{nome_para_ia(r, p['conta'])}: {'. '.join(p['por_que'])}. Quem age: {p['quem_age']}.")
    if not fazer and tem_como_ver:
        fazer.append("Nenhuma conta com sinal nesta rodada.")
    elif not fazer and r.faltas:
        fazer.append(f"Ainda não dá para ver alertas, porque nenhuma conta tem nota nem etapa medida. Comece por: {r.faltas[0]['o_que_falta']}.")
    linhas = [f"# Alertas da rodada de {r.data.isoformat()}", ""] + _abertura(fazer)
    if r.formula["mudou_nesta_rodada"]:
        linhas += [f"> Os pesos ou as rotinas mudaram em {r.formula['mudou_em']}. A nota não é comparável com a da rodada anterior.", ""]
    linhas += ["## Quem olhar primeiro", ""]
    if r.prioridades:
        linhas += _tabela(
            ["#", "conta", "nota", "receita", "por quê", "quem age"],
            [[i + 1, nome_para_ia(r, p["conta"]), numero(p["nota"]) if p["nota"] is not None else "sem nota", moeda(p["receita"]), ". ".join(p["por_que"]), p["quem_age"]] for i, p in enumerate(r.prioridades)],
        )
    elif tem_como_ver:
        linhas += ["Nenhuma conta com sinal nesta rodada.", ""]
    else:
        linhas += ["Ainda não dá para saber: nenhuma conta tem nota nem etapa medida.", ""]
    linhas += ["## O que empaca", ""]
    if r.empacadas:
        linhas += _tabela(
            ["conta", "etapa", "dias", "prazo", "nota", "motivo", "quem age"],
            [[nome_para_ia(r, c.codigo), c.etapa, numero(c.dias_etapa), numero(c.prazo), numero(c.nota) if c.nota is not None else "sem nota", c.motivo or "não informado", quem_age(c)] for c in r.empacadas],
        )
    elif dados["etapa"]:
        linhas += ["Nenhuma conta empacada nesta rodada.", ""]
    elif r.cfg.recompra and not r.cfg.etapas:
        linhas += ["Esta empresa não usa etapas. O alerta aqui é a mudança de padrão, logo abaixo.", ""]
    else:
        linhas += ["Ainda não dá para saber: falta etapa, prazo ou data de entrada na etapa.", ""]
    linhas += ["## Mudança de padrão", ""]
    if r.alertas_ruins or r.alertas_bons:
        linhas += _tabela(
            ["conta", "rotina", "antes", "agora", "mudança", "leitura", "nota"],
            [
                [nome_para_ia(r, a["conta"]), a["rotina"], numero(a["antes"]), numero(a["agora"]), f"{a['variacao_pct']}%" if a["variacao_pct"] is not None else "novo", a["leitura"], numero(a["nota"]) if a["nota"] is not None else "sem nota"]
                for a in r.alertas_ruins + r.alertas_bons
            ],
        )
    elif dados["comparacao_de_padrao"]:
        linhas += ["Nenhuma mudança de padrão nesta rodada.", ""]
    else:
        linhas += ["Ainda não há com o que comparar: traga a coluna do período anterior, ou espere a próxima rodada.", ""]
    if r.renovacoes:
        linhas += ["## Renovações na janela", ""]
        linhas += _tabela(
            ["conta", "dias", "receita", "nota", "com risco?"],
            [[nome_para_ia(r, x["conta"]), x["dias"], moeda(x["receita"]), numero(x["nota"]) if x["nota"] is not None else "sem nota", "sim" if x["com_risco"] else "não"] for x in r.renovacoes],
        )
    if r.perdidas:
        p = r.perdidas
        linhas += ["## Teste da conta perdida", "", f"Das {p['total']} contas que saíram: a skill teria avisado {p['sim']} ({p['sim_pela_nota']} pela nota, {p['sim_por_alerta']} só pelo alerta), não teria avisado {p['nao']}, e em {p['sem_dado']} não dá para saber.", ""]
        linhas += _tabela(["conta", "cancelou em", "nota antes", "teria avisado?", "por quê"], [[nome_para_ia(r, d["conta"]), d["cancelou_em"] or "sem data", numero(d["nota"]) if d["nota"] is not None else "sem nota", d["avisaria"], d["por_que"]] for d in p["detalhes"]])
    if r.avisos:
        linhas += ["## Avisos sobre os dados", ""] + [f"- {a}" for a in r.avisos] + [""]
    return "\n".join(linhas)


def texto_painel(r) -> str:
    atras = [m for m in r.metas if m["situacao"] == "atrás"]
    fazer = [f"Meta atrás: {m['meta']} (atual {valor_formatado(m['atual'], m['unidade'])}, alvo {valor_formatado(m['alvo'], m['unidade'])})." for m in atras]
    if not r.metas:
        fazer.append("Definir as metas do CS em 2-metas/metas.md.")
    if r.prioridades:
        fazer.append(f"{plural(len(r.prioridades), 'conta para olhar', 'contas para olhar')}. A lista está em alertas.md.")
    if not any(c.nota is not None for c in r.ativas):
        fazer.append("Ainda não há nota: veja o que trazer em o-que-falta-medir.md.")
    linhas = [f"# Painel geral da rodada de {r.data.isoformat()}", ""] + _abertura(fazer)
    linhas += ["## Saúde da carteira", ""]
    linhas += _tabela(["faixa", "contas", "receita"], [[NOME_FAIXAS[k], v["contas"], moeda(v["receita"])] for k, v in r.painel["faixas"].items()])
    linhas += ["## Metas", ""]
    if r.metas:
        linhas += _tabela(["meta", "alvo", "atual", "situação", "prazo"], [[m["meta"], valor_formatado(m["alvo"], m["unidade"]), valor_formatado(m["atual"], m["unidade"]), m["situacao"], m["prazo"]] for m in r.metas])
    else:
        linhas += ["a preencher", ""]
    linhas += ["## Métricas", ""]
    linhas += _tabela(
        ["métrica", "valor", "como é calculada"],
        [[m["nome"], valor_formatado(m["valor"], m["unidade"]), f"{m['como']} ({m['detalhe']})" if m.get("detalhe") else m["como"]] for m in r.painel["metricas"]],
    )
    cascata = r.painel["cascata"]
    if cascata:
        linhas += ["## Cascata da receita", ""]
        linhas += _tabela(["início", "churn", "redução", "expansão", "fim"], [[moeda(cascata["inicio"]), moeda(cascata["churn"]), moeda(cascata["reducao"]), moeda(cascata["expansao"]), moeda(cascata["fim"])]])
    for titulo, grupos in (("Por responsável", r.painel["por_responsavel"]), ("Por segmento", r.painel["por_segmento"])):
        if grupos:
            linhas += [f"## {titulo}", ""]
            linhas += _tabela(
                ["grupo", "contas", "receita", "nota média", "empacadas", "em risco", "renovações"],
                [[nome_para_ia(r, g["grupo"]) if g["grupo"] != "sem informação" else g["grupo"], g["contas"], moeda(g["receita"]), numero(g["nota_media"]), g["empacadas"], g["em_risco"], g["renovacoes"]] for g in grupos],
            )
    chave = r.contas_chave
    linhas += ["## Contas-chave", ""]
    if chave.get("existe"):
        linhas += [f"{chave['quantas']} de {chave['de_um_total_de']} contas somam {chave['pct_receita']}% da receita: " + ", ".join(nome_para_ia(r, c) for c in chave["contas"]) + ".", ""]
    elif chave.get("existe") is False:
        linhas += [f"Nesta empresa não há grupo pequeno que concentre a receita: são {chave['quantas']} das {chave['de_um_total_de']} contas com receita para chegar a 80%.", ""]
    else:
        linhas += ["a preencher: falta a receita por conta.", ""]
    if r.oportunidades:
        por_nome: dict = {}
        for o in r.oportunidades:
            por_nome.setdefault(o["oportunidade"], []).append(o)
        linhas += ["## Oportunidades de upgrade", "", "A rodada aponta onde olhar. Se a área já está no plano do cliente, é adoção, não upgrade.", ""]
        linhas += _tabela(["oportunidade", "contas", "receita dessas contas"], [[nome, len(grupo), moeda(sum(o["receita"] or 0 for o in grupo))] for nome, grupo in sorted(por_nome.items(), key=lambda x: -len(x[1]))])
    return "\n".join(linhas)


def texto_faltas(r) -> str:
    fazer = [f"{r.faltas[0]['o_que_falta']}: {r.faltas[0]['primeiro_passo']}"] if r.faltas else []
    linhas = [f"# O que falta medir na rodada de {r.data.isoformat()}", ""] + _abertura(fazer) + ["## A lista, em ordem de prioridade", ""]
    if r.faltas:
        linhas += _tabela(["prioridade", "o que falta", "por que importa", "primeiro passo"], [[f["prioridade"], f["o_que_falta"], f["por_que_importa"], f["primeiro_passo"]] for f in r.faltas])
    else:
        linhas += ["Nada em aberto nesta rodada.", ""]
    return "\n".join(linhas)


def _aviso_de_tamanho(teste: dict) -> list[str]:
    if teste["tamanho_confere"]:
        return []
    return [f"No teste, o modelo previu {numero(teste['previsto_pct'])}% em média, e aconteceu {numero(teste['aconteceu_pct'])}%. Use como ordem de prioridade, não como porcentagem exata.", ""]


def texto_previsoes(r) -> str:
    prev = r.previsoes
    churn, uso, aumento = prev.get("churn") or {}, prev.get("engajamento") or {}, prev.get("incremento") or {}
    fazer = []
    for c in churn.get("contas", [])[:3]:
        fazer.append(f"{nome_para_ia(r, c['conta'])}: {c['chance_pct']}% de chance de cancelar em {prev['horizonte_dias']} dias. {'. '.join(c['motivos'])}.")
    for c in [c for c in uso.get("contas", []) if c["tendencia"] == "cai"][:3]:
        fazer.append(f"{nome_para_ia(r, c['conta'])}: {c['rotina']} deve cair ({c['chance_pct']}% de chance).")
    for c in aumento.get("contas", [])[:3]:
        fazer.append(f"{nome_para_ia(r, c['conta'])}: {c['chance_pct']}% de chance de aumentar a receita em {prev['horizonte_dias']} dias.")
    linhas = [f"# Previsões da rodada de {r.data.isoformat()}", ""] + _abertura(fazer)
    linhas += [
        "## Como ler",
        "",
        "Um modelo estatístico treinado com o histórico desta empresa, neste computador. Só aparece aqui o que passou no teste: em datas passadas, que o modelo não tinha visto, ele precisa acertar mais que a comparação simples. É chance, não certeza. Serve para escolher onde olhar primeiro.",
        "",
    ]
    linhas += [f"- {linha}" for linha in resumo_das_previsoes(prev)] + [""]
    if churn.get("status") == "ok":
        linhas += [f"## Quem pode cancelar em {prev['horizonte_dias']} dias", ""] + _aviso_de_tamanho(churn["teste"])
        if churn["receita_em_risco"] is not None:
            linhas += [f"Receita em risco prevista: {moeda(churn['receita_em_risco'])}, somando a chance de cada conta vezes a receita dela.", ""]
        linhas += _tabela(
            ["conta", "chance", "nota", "receita", "o que pesou"],
            [[nome_para_ia(r, c["conta"]), f"{c['chance_pct']}%", numero(c["nota"]) if c["nota"] is not None else "sem nota", moeda(c["receita"]), ". ".join(c["motivos"])] for c in churn["contas"][:LISTA_PREVISAO]],
        )
    if uso.get("status") == "ok":
        linhas += ["## Para onde o uso vai", ""]
        if uso["contas"]:
            linhas += _tabela(
                ["conta", "rotina", "normal da conta", "agora", "tendência", "chance", "o que pesou"],
                [[nome_para_ia(r, c["conta"]), c["rotina"], numero(c["normal"]), numero(c["agora"]), c["tendencia"], f"{c['chance_pct']}%", ". ".join(c["motivos"])] for c in uso["contas"][:LISTA_PREVISAO]],
            )
        else:
            linhas += [f"Nenhuma conta com {prev['chance_para_tendencia_pct']}% ou mais de chance de mudar o uso.", ""]
    if aumento.get("status") == "ok":
        linhas += [f"## Quem pode aumentar a receita em {prev['horizonte_dias']} dias", ""] + _aviso_de_tamanho(aumento["teste"])
        if aumento["teste"]["tamanho_confere"]:
            linhas += [f"Valor estimado: a chance da conta, vezes o aumento típico do histórico ({numero(aumento['aumento_tipico_pct'])}%), vezes a receita dela.", ""]
        linhas += _tabela(
            ["conta", "chance", "receita", "valor estimado", "o que pesou"],
            [[nome_para_ia(r, c["conta"]), f"{c['chance_pct']}%", moeda(c["receita"]), "não estimado" if c["valor_estimado"] is None else moeda(c["valor_estimado"]), ". ".join(c["motivos"])] for c in aumento["contas"][:LISTA_PREVISAO]],
        )
    return "\n".join(linhas)


def gravar_valores(r, caminho: Path) -> None:
    ids = [i.id for i in r.cfg.indicadores]
    linhas = []
    for c in r.contas:
        medidas = [c.medicoes.get(i) if isinstance(c.medicoes.get(i), (int, float)) else "" for i in ids]
        alertas = ",".join(sorted({a["indicador"] for a in c.alertas}))
        linhas.append([c.codigo, c.status, "" if c.nota is None else c.nota, c.faixa, round(c.cobertura, 3), c.situacao, alertas, "" if c.receita is None else c.receita] + medidas)
    escrever_csv(caminho, ["codigo", "status", "nota", "faixa", "cobertura", "situacao", "alertas", "receita"] + [f"ind:{i}" for i in ids], linhas)


def fatos_das_contas(r) -> dict:
    """A foto de cada conta ativa, para reunião, renovação e risco. No modo protegido, só códigos e números."""
    prev = r.previsoes
    churn = {c["conta"]: c["chance_pct"] for c in (prev.get("churn") or {}).get("contas", [])}
    aumento = {c["conta"]: c["chance_pct"] for c in (prev.get("incremento") or {}).get("contas", [])}
    uso: dict = {}
    for c in (prev.get("engajamento") or {}).get("contas", []):
        uso.setdefault(c["conta"], []).append({"rotina": c["rotina"], "tendencia": c["tendencia"], "chance_pct": c["chance_pct"]})
    bons: dict = {}
    for a in r.alertas_bons:
        bons.setdefault(a["conta"], []).append({"rotina": a["rotina"], "antes": a["antes"], "agora": a["agora"]})
    total = sum(c.receita or 0 for c in r.ativas)
    fatos = {}
    for c in r.ativas:
        rotinas = []
        for ind in r.cfg.indicadores:
            agora, antes = c.medicoes.get(ind.id), c.antes.get(ind.id)
            rotinas.append(
                {
                    "id": ind.id,
                    "rotina": ind.rotina,
                    "bloco": ind.bloco,
                    "esperado": ind.esperado,
                    "agora": agora if isinstance(agora, (int, float)) else None,  # rótulo do export nunca entra aqui
                    "antes": antes if isinstance(antes, (int, float)) else None,
                    "subnota": c.subnotas.get(ind.id),
                }
            )
        renovacao, ultimo, proximo = c.campos.get("renovacao"), c.campos.get("ultimo_contato"), c.campos.get("data_proximo_contato")
        item = {
            "conta": c.codigo,
            "nota": c.nota,
            "faixa": c.faixa,
            "confianca": c.grau,
            "receita": c.receita,
            "pct_receita": arredondar(100 * c.receita / total, 1) if c.receita and total else None,
            "contrato": c.contrato,
            "renovacao": renovacao.isoformat() if renovacao and c.contrato != "mensal" else None,
            "dias_ate_renovar": (renovacao - r.data).days if renovacao and c.contrato != "mensal" else None,
            "etapa": c.etapa,
            "situacao": c.situacao,
            "dias_na_etapa": c.dias_etapa,
            "prazo_da_etapa": c.prazo,
            "motivo_parada": c.motivo or None,
            "quem_age": quem_age(c),
            "responsavel": r.cofre.codigo_pessoa(c.campos["responsavel"]) if c.campos.get("responsavel") else None,
            "dias_sem_contato": (r.data - ultimo).days if ultimo else None,
            "proximo_contato": proximo.isoformat() if proximo else None,
            "tem_proximo_passo": bool(c.campos.get("proximo_passo")),
            "contatos_anotados": {papel: bool(c.campos.get(papel)) for papel in ("patrocinador", "decisor", "usuario_chave")},
            "sinais": [{"codigo": s[0], "texto": s[1]} for s in c.sinais],
            "sinais_bons": bons.get(c.codigo, []),
            "rotinas": rotinas,
            "chance_churn_pct": churn.get(c.codigo),
            "chance_aumento_pct": aumento.get(c.codigo),
            "tendencias_de_uso": uso.get(c.codigo, []),
            "oportunidades": [o for o in r.oportunidades if o["conta"] == c.codigo],
        }
        if r.modo == "aberto":
            item["nome"] = r.cofre.nome_de(c.codigo)
        fatos[c.codigo] = item
    return fatos


def gravar_rodada(r, pasta: Path, destino: Path) -> dict:
    from .planilha import gerar_planilha

    destino.mkdir(parents=True, exist_ok=True)
    resumo = montar_resumo(r)
    (destino / "resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (destino / "contas.json").write_text(json.dumps(fatos_das_contas(r), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    gravar_valores(r, destino / "valores.csv")
    textos = {"alertas.md": texto_alertas(r), "painel-geral.md": texto_painel(r), "o-que-falta-medir.md": texto_faltas(r), "previsoes.md": texto_previsoes(r)}
    com_nomes = pasta / "com-nomes"
    for nome, texto in textos.items():
        (destino / nome).write_text(texto, encoding="utf-8")
        if r.modo == "protegido":
            com_nomes.mkdir(exist_ok=True)
            base = nome.removesuffix(".md")
            (com_nomes / f"{base}-{r.data.isoformat()}.md").write_text(r.cofre.restaurar(texto), encoding="utf-8")
    gerar_planilha(r, destino / "health-score.xlsx", pasta)
    r.cofre.salvar()
    r.rotulos.salvar()
    return resumo
