"""O que falta medir: cada lacuna com o motivo e o primeiro passo, em ordem de prioridade."""

from __future__ import annotations

from . import plural

ORDEM = {"alta": 0, "média": 1, "baixa": 2}


def _item(prioridade: str, falta: str, por_que: str, passo: str) -> dict:
    return {"prioridade": prioridade, "o_que_falta": falta, "por_que_importa": por_que, "primeiro_passo": passo}


def listar_faltas(r) -> list:
    cfg = r.cfg
    presentes = r.campos_presentes
    itens = []
    n_ativas = len(r.ativas)

    def falta_campo(campo, prioridade, falta, por_que, passo, cobrar_preenchimento=True):
        if campo not in presentes:
            itens.append(_item(prioridade, falta, por_que, passo))
            return True
        preenchidos, total = presentes[campo]
        if cobrar_preenchimento and total and preenchidos / total < 0.5:
            itens.append(
                _item(
                    "média",
                    f"{falta} (só {round(100 * preenchidos / total)}% das linhas têm)",
                    por_que,
                    "Complete no sistema de origem, para vir no próximo export.",
                )
            )
            return True
        return False

    if not cfg.indicadores:
        itens.append(
            _item(
                "alta",
                "Nenhuma rotina foi definida no checklist",
                "A nota nasce das rotinas que provam valor. Sem elas, não existe nota.",
                "Rode o Consultor e responda: qual dor o produto resolve e quais rotinas provam que o cliente está tendo valor?",
            )
        )
    for ind in cfg.indicadores:
        estado = r.estado_indicadores.get(ind.id, {"medidos": 0, "total": 0})
        prioridade = {"alta": "alta", "media": "média", "baixa": "baixa"}[ind.criticidade]
        if estado["medidos"] == 0:
            sem_frequencia = any("frequência" in p for p in ind.pendencias)
            passo = f"Exporte o dado que prova esta rotina ({ind.dado_prova})." if ind.dado_prova else "Defina qual registro prova esta rotina e exporte."
            if sem_frequencia and ind.arquivo and ind.arquivo.casefold() in {a.casefold() for a in cfg.arquivos}:
                itens.append(_item(prioridade, f"Rotina '{ind.rotina}' sem frequência esperada", "Tem dado, mas sem saber o normal não dá para dar nota.", "Defina quantas vezes uma conta saudável faz isso. Pode ser uma hipótese."))
                continue
            if sem_frequencia:
                passo += " Depois, defina quantas vezes uma conta saudável faz isso."
            itens.append(_item(prioridade, f"Rotina '{ind.rotina}' sem dado", "A nota desta rotina fica vazia e a confiança da nota cai.", passo))
        elif estado["total"] and estado["medidos"] / estado["total"] < 0.5:
            pct = round(100 * estado["medidos"] / estado["total"])
            itens.append(_item("média", f"Rotina '{ind.rotina}' medida em só {pct}% das contas", "As outras contas ficam com nota menos confiável.", "Veja por que essas contas não têm o registro."))

    if not r.cfg.metas:
        itens.append(_item("alta", "Metas do CS não definidas", "Sem meta, o painel mostra números, mas não diz o que está atrás.", "Preencha 2-metas/metas.md com o Líder da rotina."))
    for meta in r.metas:
        if meta["situacao"] == "sem dado":
            itens.append(_item("média", f"Meta '{meta['meta']}' sem dado", "Não dá para saber se a meta está atrás.", f"Traga o dado do indicador '{meta['indicador']}'."))
        elif meta["situacao"] == "indicador não medido pela skill":
            itens.append(_item("baixa", f"Meta '{meta['meta']}' com indicador que a skill não mede", "A situação desta meta precisa ser anotada à mão.", "Escolha um indicador do catálogo ou anote o número em metas.md."))

    falta_campo("receita", "alta", "Receita por conta", "Sem receita, não dá para saber quanto está em risco nem quais contas pesam mais.", "Inclua o valor mensal ou anual de cada conta no export.")
    if cfg.recompra:
        itens.append(_item("média", "Regra de conta perdida", "Sem contrato, não existe data de cancelamento. Sem essa regra, a conta que parou de comprar segue como ativa.", "Combine depois de quantos dias sem comprar a conta conta como perdida, e anote em 1-empresa/estrategia.md."))
    else:
        tinha_coluna = not falta_campo(
            "data_cancelamento",
            "alta",
            "Data de cancelamento",
            "Sem ela não há churn e nem o teste da conta perdida.",
            "Exporte também as contas canceladas, com a data de saída.",
            cobrar_preenchimento=False,
        )
        if tinha_coluna and not r.canceladas:
            itens.append(_item("alta", "O export não traz nenhuma conta cancelada", "Quase sempre é export só de ativas. Sem as canceladas, não dá para saber o churn nem fazer o teste da conta perdida.", "Exporte também quem saiu, com a data de saída."))
        sem_data = sum(1 for c in r.canceladas if not c.campos.get("data_cancelamento"))
        if sem_data:
            itens.append(_item("alta", f"{plural(sem_data, 'conta cancelada', 'contas canceladas')} sem data", "Ficam fora do churn, que pode estar menor do que é.", "Registre a data de saída no sistema de origem."))
        contratos = [c.contrato for c in r.ativas]
        so_mensal = bool(contratos) and all(c == "mensal" for c in contratos)
        if not so_mensal:  # no mensal, não há data de decisão para acompanhar
            falta_campo("renovacao", "alta", "Data de renovação", "É o que diz quais contas em risco são urgentes.", "Inclua a data de renovação de cada contrato.")
        if contratos and all(c is None for c in contratos):
            itens.append(_item("baixa", "Tipo de contrato", "No anual, a renovação é uma decisão com data. No mensal, a insatisfação acumula até cancelar, e o cuidado é outro.", "Inclua o tipo de contrato no export, ou anote 'contrato padrão' em 4-dados/como-medir.md."))
    prioridade_etapa = "baixa" if cfg.recompra else "alta"  # na recompra, o padrão de compra avisa antes
    tem_etapa = not falta_campo("etapa", prioridade_etapa, "Etapa atual de cada conta", "Sem etapa, não dá para ver a conta parada, que é o que avisa antes.", "Comece a registrar em que etapa cada conta está.")
    if tem_etapa:
        if "data_entrada_etapa" not in presentes and "dias_na_etapa" not in presentes:
            itens.append(_item("alta", "Não há data de entrada na etapa", "Sem ela, não dá para saber quem está parado.", "Comece a registrar a data sempre que a conta mudar de etapa."))
        if not cfg.etapas:
            itens.append(_item("alta", "Jornada sem etapas definidas", "Sem etapas e prazos, não há alerta de conta parada.", "Preencha 1-empresa/jornada.md com o Consultor."))
        elif all(e.prazo is None for e in cfg.etapas):
            itens.append(_item("alta", "Jornada sem prazo por etapa", "O prazo é o que define quando a conta empacou.", "Defina o tempo máximo em cada etapa, mesmo que seja uma hipótese."))
        falta_campo("motivo_parada", "alta", "Motivo da parada: do cliente ou nosso", "Muda quem precisa agir.", "Crie um campo com duas opções: pendência do cliente ou parado por nós.", cobrar_preenchimento=False)
        sem_motivo = [c for c in r.empacadas if not c.motivo]
        if sem_motivo and "motivo_parada" in presentes:
            itens.append(_item("alta", f"{plural(len(sem_motivo), 'conta empacada', 'contas empacadas')} sem motivo", "Sem o motivo, ninguém sabe quem precisa agir.", "Registre o motivo no sistema de origem, para vir no próximo export. Para decidir já, anote na aba O que empaca."))
        falta_campo("proximo_passo", "média", "Próximo passo", "Conta parada sem próximo passo continua parada.", "Traga esse campo do CRM no próximo export. Para decidir já, anote na planilha.")
        falta_campo("data_proximo_contato", "média", "Data do próximo contato", "Mostra quem ficou sem data combinada.", "Registre a próxima data depois de cada conversa.")

    falta_campo("data_inicio", "média", "Data de início do cliente", "Permite calcular churn sobre a base certa e olhar por safra.", "Inclua a data do início do contrato ou da primeira compra.")
    falta_campo("segmento", "média", "Segmento da conta", "Sem grupos, todo cliente recebe o mesmo atendimento.", "Use a segmentação combinada com o Consultor.")
    falta_campo("responsavel", "média", "Responsável pela conta", "Sem ele, o painel não mostra a carteira de cada pessoa do time.", "Inclua quem do CS cuida de cada conta.")
    falta_campo("ultimo_contato", "média", "Data do último contato", "Mostra quem está sem conversa há muito tempo.", "Exporte do CRM ou comece a registrar.")
    contatos = [c for c in ("patrocinador", "decisor", "usuario_chave") if c in presentes]
    if not contatos:
        itens.append(_item("baixa" if cfg.recompra else "média", "Nenhuma conta tem patrocinador anotado", "Quando o contato principal sai, o risco sobe e ninguém vê.", "Comece pelas contas maiores: anote patrocinador, decisor e usuário-chave."))
    falta_campo("nps", "baixa", "NPS", "Serve para ver a tendência da base, não para avaliar conta a conta.", "Inclua a última nota de NPS de cada conta, se a pesquisa existir.")
    falta_campo("receita_anterior", "baixa", "Receita do período anterior", "Sem ela não dá para calcular retenção bruta e líquida.", "Exporte a receita de 12 meses atrás junto com a atual.")

    if r.canceladas:
        vagos = _motivos_vagos(r)
        if vagos:
            itens.append(_item("média", f"{plural(vagos, 'cancelamento', 'cancelamentos')} sem motivo específico", "Motivo vago não ensina nada sobre o que corrigir.", "Volte nessas contas e registre a causa real, nunca só 'não viu valor'."))
        sem_saber = r.perdidas.get("sem_dado", 0)
        if sem_saber:
            itens.append(_item("média", f"{plural(sem_saber, 'conta perdida', 'contas perdidas')} sem histórico para o teste", "Não dá para saber se a nota teria avisado.", "Guarde as rodadas: a partir da próxima, o teste usa o dado real da época."))

    sem_nota = sum(1 for c in r.ativas if c.nota is None)
    if sem_nota and cfg.indicadores and n_ativas and sem_nota < n_ativas:
        itens.append(_item("média", f"{plural(sem_nota, 'conta', 'contas')} sem nota por falta de dado", "Conta sem nota não entra na comparação.", "Veja na aba Medições o que está vazio nessas contas."))

    itens += _faltas_de_previsao(r)
    if cfg.indicadores and not cfg.oportunidades:
        itens.append(_item("baixa", "O que configura oportunidade de upgrade nesta empresa", "Sem isso, a rodada só aponta a rotina sem uso. Sobrecarga de usuário e limite de plano ficam de fora.", "Pergunte o que já virou upgrade aqui e anote na tabela Oportunidades de 4-dados/como-medir.md."))
    itens.sort(key=lambda x: ORDEM[x["prioridade"]])
    return itens


def _faltas_de_previsao(r) -> list:
    prev = r.previsoes
    itens = []
    textos = (
        ("churn", "prever churn", "Exporte também quem saiu, com a data de saída, e as atividades com data dos meses passados."),
        ("engajamento", "prever o uso", "Exporte as atividades com data dos meses passados, ou guarde uma rodada por semana."),
        ("incremento", "prever aumento de receita", "Rode toda semana, ou gere rodadas dos meses passados a partir de exports antigos, com --data e --entrada."),
    )
    for nome, para_que, passo in textos:
        bloco = prev.get(nome) or {}
        if bloco.get("status") != "sem_dados" or "tem" not in bloco:
            continue
        if nome == "churn" and r.cfg.recompra:  # sem contrato, o que falta é a regra de conta perdida, que já está na lista
            continue
        itens.append(_item("baixa", f"Histórico para {para_que}: {bloco['tem']} de {bloco['minimo']} {bloco.get('unidade', 'casos')}", "Com pouco histórico, o modelo não treina e a previsão fica de fora.", passo))
    if any((prev.get(nome) or {}).get("status") == "sem_biblioteca" for nome in ("churn", "engajamento", "incremento")):
        from .prever import TEXTO_BIBLIOTECA

        itens.append(_item("média", "Biblioteca de previsão não instalada", "Já há histórico para treinar, mas o modelo não roda sem ela.", TEXTO_BIBLIOTECA))
    return itens


def _motivos_vagos(r) -> int:
    from .leitura import normalizar
    from .medir import MOTIVOS_VAGOS

    quantos = 0
    for conta in r.canceladas:
        motivo = conta.campos.get("motivo_cancelamento")
        if motivo is None or normalizar(motivo) in MOTIVOS_VAGOS:
            quantos += 1
    return quantos
