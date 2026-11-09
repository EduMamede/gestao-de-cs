#!/usr/bin/env python
"""Gera as 5 bases fictícias usadas nos testes. Todo nome aqui é inventado.

As respostas esperadas foram calculadas à mão e estão comentadas em `ESPERADO`. O teste compara o
resultado do programa com essas respostas, em vez de recalcular com o mesmo código.
"""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import openpyxl

REF = dt.date(2026, 11, 3)
AQUI = Path(__file__).resolve().parent / "bases"


def d(dias: int) -> str:
    """Data no formato brasileiro, `dias` antes da referência."""
    return (REF - dt.timedelta(days=dias)).strftime("%d/%m/%Y")


def f(dias: int) -> str:
    """Data no formato brasileiro, `dias` depois da referência."""
    return (REF + dt.timedelta(days=dias)).strftime("%d/%m/%Y")


def serial(data: dt.date) -> int:
    return (data - dt.date(1899, 12, 30)).days


def escrever(caminho: Path, linhas: list, separador=",", codificacao="utf-8") -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding=codificacao, newline="") as saida:
        csv.writer(saida, delimiter=separador).writerows(linhas)


def md(titulo: str, secao: str, tabela: str, extra: str = "") -> str:
    return f"# {titulo}\n\n## O que fazer\n\n- Base de teste.\n\n## O que foi conversado\n\n- Base de teste.\n\n## {secao}\n\n{tabela}\n{extra}"


JORNADA_CLINICA = md(
    "Jornada",
    "Etapas",
    "| etapa | prazo (dias) | validação |\n| --- | --- | --- |\n"
    "| Kickoff | 7 | reunião feita |\n| Implantação | 20 | sistema configurado |\n"
    "| Treinamento | 15 | equipe treinada |\n| Acompanhamento | | em uso |",
)

# ---------------------------------------------------------------- 1. completa


def base_completa() -> dict:
    cab = [
        "ID", "Cliente", "Segmento", "CSM", "MRR", "Início", "Renovação", "Status", "Cancelamento", "Etapa", "Entrou na etapa",
        "Parado por", "Próximo passo", "Próximo contato", "Último contato", "Planos lançados 30d", "Planos lançados 30d ant",
        "Movimentos de estoque 30d", "Movimentos de estoque 30d ant", "Agendas 30d", "Agendas 30d ant", "Pagamento", "NPS",
        "Patrocinador", "E-mail do contato", "Observações",
    ]
    linhas, chamados = [cab], [["Cliente", "Aberto em", "Assunto"]]
    n = [0]

    def conta(nome, mrr=1000, seg="Pequena", csm="Ana Fictícia", renova=300, etapa="Acompanhamento", entrou=200, parado="", passo="", proximo="",
              contato=10, plano=(10, 10), estoque=(6, 6), agenda=(25, 25), pag="em dia", nps=9, abertos=(1, 1)):
        n[0] += 1
        id_ = f"F{n[0]:03d}"
        val = lambda v: "" if v is None else v  # noqa: E731
        linhas.append([
            id_, nome, seg, csm, mrr, d(800), f(renova), "Ativo", "", etapa, d(entrou), parado, passo, f(proximo) if proximo != "" else "", d(contato),
            val(plano[0]), val(plano[1]), val(estoque[0]), val(estoque[1]), val(agenda[0]), val(agenda[1]), val(pag), val(nps),
            f"Pessoa Fictícia {n[0]}", f"contato{n[0]}@ficticia.example", f"SEGREDO-OBS-{n[0]} ligar para a Pessoa Fictícia {n[0]} no fim do mês, ela está insatisfeita",
        ])
        for i in range(abertos[0]):
            chamados.append([nome, d(1 + i), f"SEGREDO-ASSUNTO-{n[0]}"])
        for i in range(abertos[1]):
            chamados.append([nome, d(31 + i), f"SEGREDO-ASSUNTO-{n[0]}"])

    for i in range(1, 25):  # nota 100
        conta(f"Clínica Fictícia Saudável {i:02d}", csm="Ana Fictícia" if i % 2 else "Bruno Fictício")
    # conta verde parada na etapa: nota 100, 45 dias numa etapa de 20
    conta("Clínica Fictícia Verde Parada", mrr=2000, seg="Média", etapa="Implantação", entrou=45, parado="Cliente", passo="Cobrar envio da lista de usuários", proximo=5, nps=8)
    conta("Clínica Fictícia Parada Por Nós", mrr=1500, seg="Média", etapa="Treinamento", entrou=30, parado="Parado por nós", nps=8)
    conta("Clínica Fictícia Parada Sem Motivo", etapa="Kickoff", entrou=10, nps=8)
    # grande conta em risco perto de renovar: (3*25 + 2*0 + 2*25 + 3*0 + 2*0) / 12 = 10,4 -> 10
    conta("Hospital Fictício Grande Conta", mrr=48000, seg="Grande", csm="Bruno Fictício", renova=45, contato=90, plano=(2, 2), estoque=(0, 0), agenda=(5, 5), pag="atrasado", nps=3, abertos=(9, 9))
    # queda de padrão com nota boa: 40 -> 12 planos, ainda acima dos 8 esperados
    conta("Clínica Fictícia Queda de Padrão", mrr=3000, seg="Média", plano=(12, 40))
    # sinal bom de expansão: 10 -> 25
    conta("Clínica Fictícia Cresceu", plano=(25, 10), nps=10)
    # nota 46: (3*50 + 2*50 + 2*50 + 3*0 + 2*100) / 12 = 45,83
    for i in range(1, 4):
        conta(f"Clínica Fictícia Morna {i}", plano=(4, 4), estoque=(2, 2), agenda=(10, 10), pag="atrasado", nps=7)
    # nota 8: (0 + 0 + 0 + 0 + 2*50) / 12 = 8,33
    for i in range(1, 3):
        conta(f"Clínica Fictícia Crítica {i}", mrr=800, plano=(0, 0), estoque=(0, 0), agenda=(0, 0), pag="atrasado", nps=4, abertos=(6, 6))
    # confiança média: sem estoque e sem agenda, cobertura (3+3+2)/12 = 66,7%, nota 100
    for i in range(1, 3):
        conta(f"Clínica Fictícia Meio Medida {i}", estoque=(None, None), agenda=(None, None), nps=None)
    # sem nota: só chamados, cobertura 2/12 = 16,7%
    for i in range(1, 3):
        conta(f"Clínica Fictícia Sem Dados {i}", plano=(None, None), estoque=(None, None), agenda=(None, None), pag=None, nps=None)
    # renovação próxima, tudo bem: entra no fim da lista
    conta("Clínica Fictícia Renova Bem", mrr=5000, seg="Média", renova=60)

    pasta = AQUI / "completa"
    escrever(pasta / "contas.csv", linhas)
    escrever(pasta / "chamados.csv", chamados)
    return {
        "arquivos": ["contas.csv", "chamados.csv"],
        "como_medir": md(
            "Como medir",
            "Indicadores",
            "| id | bloco | rotina | dado que prova | onde está o dado | coluna | coluna anterior | como ler | frequência esperada | criticidade | subir é |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            "| plano | rotina | Acompanhamento do plano | Plano lançado e realização pela enfermeira | contas.csv | Planos lançados 30d | Planos lançados 30d ant | contagem | 8 | alta | bom |\n"
            "| estoque | rotina | Estoque | Entrada e saída | contas.csv | Movimentos de estoque 30d | Movimentos de estoque 30d ant | contagem | 4 | média | bom |\n"
            "| agenda | rotina | Agenda | Controle da agenda | contas.csv | Agendas 30d | Agendas 30d ant | contagem | 20 | média | bom |\n"
            "| pagamento | financeiro | Pagamento | Situação no financeiro | contas.csv | Pagamento | | categoria | em dia=100; atrasado=0 | alta | bom |\n"
            "| chamados | chamados | Chamados | Chamados abertos | chamados.csv | | | eventos | 3 em 30 dias | média | ruim |\n",
        ),
        "colunas": md(
            "Colunas",
            "Arquivos",
            "| arquivo | tipo |\n| --- | --- |\n| contas.csv | contas |\n| chamados.csv | eventos |\n",
            "\n## Colunas\n\n| arquivo | coluna | campo |\n| --- | --- | --- |\n"
            "| contas.csv | ID | conta_id |\n| contas.csv | Cliente | conta_nome |\n| contas.csv | Segmento | segmento |\n| contas.csv | CSM | responsavel |\n"
            "| contas.csv | MRR | receita |\n| contas.csv | Início | data_inicio |\n| contas.csv | Renovação | renovacao |\n| contas.csv | Status | status |\n"
            "| contas.csv | Cancelamento | data_cancelamento |\n| contas.csv | Etapa | etapa |\n| contas.csv | Entrou na etapa | data_entrada_etapa |\n"
            "| contas.csv | Parado por | motivo_parada |\n| contas.csv | Próximo passo | proximo_passo |\n| contas.csv | Próximo contato | data_proximo_contato |\n"
            "| contas.csv | Último contato | ultimo_contato |\n| contas.csv | NPS | nps |\n| contas.csv | Patrocinador | patrocinador |\n"
            "| contas.csv | Observações | bloqueada |\n| chamados.csv | Cliente | conta_nome |\n| chamados.csv | Aberto em | data_evento |\n",
        ),
        "jornada": JORNADA_CLINICA,
        "metas": md(
            "Metas",
            "Metas",
            "| meta | indicador | alvo | melhor quando | prazo | responsável | situação |\n| --- | --- | --- | --- | --- | --- | --- |\n"
            "| Churn abaixo de 2% ao mês | churn_contas_30d | 2 | menor | dez/2026 | Liderança | |\n"
            "| 85% das contas saudáveis | pct_saudaveis | 85 | maior | dez/2026 | Liderança | |\n"
            "| No máximo 1 conta empacada | contas_empacadas | 1 | menor | dez/2026 | Liderança | |\n"
            "| NPS 50 | nps | 50 | maior | dez/2026 | Liderança | |\n",
        ),
    }


# ---------------------------------------------------------------- 2. bagunçada


def base_baguncada() -> dict:
    pasta = AQUI / "baguncada"
    pasta.mkdir(parents=True, exist_ok=True)
    cab = ["Cód.", "Razão Social", "Valor Mensal", "Dt. Renov.", "Situação", "Fase", "Data da fase", "Uso no mês", "Uso mês anterior", "Obs"]
    linhas = [
        ["Relatório de clientes - gerado pelo CRM"] + [""] * 9,
        [""] * 10,
        cab,
        ["A001", "Clínica Fictícia Alfa", "R$ 1.234,56", "03/02/2027", "Ativo", "Implantacao", "2026-09-01", "12", "12", "ligar para a SEGREDO-BAG"],
        ["A002", "CLÍNICA FICTÍCIA BETA LTDA", "R$ 2.000,00", "2027-03-01", "ATIVO", "acompanhamento", "01/01/2026", "1.200", "1.100", ""],
        ["A003", "Clínica Fictícia Gama", "R$ 1.000,00", "3/11/26", "Ativo", "Acompanhamento", "03.01.2026", "15", "15", ""],
        ["A003", "Clínica Fictícia Gama", "R$ 1.000,00", "3/11/26", "Ativo", "Acompanhamento", "03.01.2026", "15", "15", ""],  # idêntica
        ["A004", "Clínica Fictícia Delta", "R$ 900,00", "15/01/2027", "Ativo", "Acompanhamento", "10/01/2026", "20", "20", ""],
        ["A004", "Clínica Fictícia Delta", "R$ 1.100,00", "15/01/2027", "Ativo", "Acompanhamento", "10/01/2026", "20", "20", ""],  # conflito: vale a última
        ["A005", "Clínica Fictícia Épsilon", "R$ 750", str(serial(dt.date(2027, 5, 10))), "Ativo", "Acompanhamento", "sem data", "11", "11", ""],
        ["A006", "Clínica Fictícia Zeta", "3.500,50", "10/06/2027", "Ativo", "Acompanhamento", "11/01/2026", "12", "12", ""],
        ["A007", "Clínica Fictícia Eta", "R$ 10.000,00", "10-07-2027", "Ativo", "Acompanhamento", "12/01/2026", "30", "30", ""],
        ["A008", "Clínica Fictícia Teta", "R$1.500,00", "10/08/2027", "Ativo", "Acompanhamento", "13/01/2026", "14", "14", ""],
        ["A009", "Clínica Fictícia Iota", "500", "10/09/2027", "Ativo", "Acompanhamento", "14/01/2026", "10", "10", ""],
        ["A010", "Clínica Fictícia Capa", "R$ 2.500,75", "10/10/2027", "Ativo", "Acompanhamento", "15/01/2026", "16", "16", ""],
        ["A011", "Clínica Fictícia Lambda", "1.000", "10/11/2027", "Ativo", "Acompanhamento", "16/01/2026", "17", "17", ""],
        ["A012", "Clínica Fictícia Mi", "", "10/12/2027", "Ativo", "Acompanhamento", "17/01/2026", "18", "18", ""],
        [""] * 10,
        ["TOTAL", "", "R$ 99.999,00", "", "", "", "", "", "", ""],
    ]
    escrever(pasta / "Export CRM.csv", linhas, separador=";", codificacao="latin-1")

    livro = openpyxl.Workbook()
    aba = livro.active
    aba.title = "Financeiro"
    aba.append(["Cliente", "Situação pgto", "Último pagamento"])
    nomes = ["clinica ficticia alfa", "Clínica Fictícia Beta", "CLINICA FICTICIA GAMA S/A", "Clínica Fictícia Delta", "Clínica Fictícia Épsilon", "Clínica Fictícia Zeta",
             "Clínica Fictícia Eta", "Clínica Fictícia Teta", "Clínica Fictícia Iota", "Clínica Fictícia Capa", "Clínica Fictícia Lambda", "Clínica Fictícia Mi"]
    for i, nome in enumerate(nomes):
        situacao = "Atrasado" if i == 0 else "Em dia"
        data = dt.datetime(2026, 10, 1 + i) if i % 2 == 0 else serial(dt.date(2026, 10, 1 + i))
        aba.append([nome, situacao, data])
    livro.save(pasta / "financeiro.xlsx")
    return {
        "arquivos": ["Export CRM.csv", "financeiro.xlsx"],
        "como_medir": md(
            "Como medir",
            "Indicadores",
            "| id | bloco | rotina | dado que prova | onde está o dado | coluna | coluna anterior | como ler | frequência esperada | criticidade | subir é |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            "| uso | rotina | Uso no mês | Acessos | Export CRM.csv | Uso no mês | Uso mês anterior | contagem | 10 | alta | bom |\n"
            "| pagamento | financeiro | Pagamento | Financeiro | financeiro.xlsx | Situação pgto | | categoria | em dia=100; atrasado=0 | alta | bom |\n",
        ),
        "colunas": md(
            "Colunas",
            "Arquivos",
            "| arquivo | tipo |\n| --- | --- |\n| Export CRM.csv | contas |\n| financeiro.xlsx | contas |\n",
            "\n## Colunas\n\n| arquivo | coluna | campo |\n| --- | --- | --- |\n"
            "| Export CRM.csv | Cód. | conta_id |\n| Export CRM.csv | Razão Social | conta_nome |\n| Export CRM.csv | Valor Mensal | receita |\n"
            "| Export CRM.csv | Dt. Renov. | renovacao |\n| Export CRM.csv | Situação | status |\n| Export CRM.csv | Fase | etapa |\n| Export CRM.csv | Data da fase | data_entrada_etapa |\n"
            "| financeiro.xlsx | Cliente | conta_nome |\n",
        ),
        "jornada": JORNADA_CLINICA,
        "metas": md("Metas", "Metas", "| meta | indicador | alvo | melhor quando | prazo | responsável | situação |\n| --- | --- | --- | --- | --- | --- | --- |\n"),
    }


# ---------------------------------------------------------------- 3. mínima


def base_minima() -> dict:
    pasta = AQUI / "minima"
    pasta.mkdir(parents=True, exist_ok=True)
    livro = openpyxl.Workbook()
    aba = livro.active
    aba.append(["Conta", "Receita"])
    aba.append(["Empresa Fictícia Grande Um", 40000])
    aba.append(["Empresa Fictícia Grande Dois", 35000])
    for i in range(1, 9):
        aba.append([f"Empresa Fictícia Pequena {i}", 2000])
    livro.save(pasta / "contas.xlsx")
    return {
        "arquivos": ["contas.xlsx"],
        "como_medir": md(
            "Como medir",
            "Indicadores",
            "| id | bloco | rotina | dado que prova | onde está o dado | coluna | coluna anterior | como ler | frequência esperada | criticidade | subir é |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            "| uso | rotina | Uso do sistema | Login no mês | | | | | | alta | bom |\n"
            "| chamados | chamados | Chamados | Chamados abertos | | | | | | média | ruim |\n",
        ),
        "colunas": md(
            "Colunas",
            "Arquivos",
            "| arquivo | tipo |\n| --- | --- |\n| contas.xlsx | contas |\n",
            "\n## Colunas\n\n| arquivo | coluna | campo |\n| --- | --- | --- |\n| contas.xlsx | Conta | conta_nome |\n| contas.xlsx | Receita | receita |\n",
        ),
        "jornada": md("Jornada", "Etapas", "| etapa | prazo (dias) |\n| --- | --- |\n"),
        "metas": md(
            "Metas",
            "Metas",
            "| meta | indicador | alvo | melhor quando | prazo | responsável | situação |\n| --- | --- | --- | --- | --- | --- | --- |\n"
            "| Churn abaixo de 2% ao mês | churn_contas_30d | 2 | menor | dez/2026 | Liderança | |\n",
        ),
    }


# ---------------------------------------------------------------- 4. com canceladas


def base_canceladas() -> dict:
    pasta = AQUI / "canceladas"
    cab = ["Cliente", "MRR", "Início", "Status", "Cancelamento", "Motivo", "Último uso", "Planos 30d", "Planos 30d ant", "Etapa", "Entrou na etapa"]
    linhas = [cab]
    inicio_antigo = "15/01/2025"
    for i in range(1, 23):
        linhas.append([f"Empresa Fictícia Antiga {i:02d}", 1000, inicio_antigo, "Ativo", "", "", d(2), 10, 10, "Acompanhamento", d(300)])
    for i in range(1, 3):
        linhas.append([f"Empresa Fictícia Nova {i}", 1000, d(10), "Ativo", "", "", d(1), 10, 10, "Acompanhamento", d(5)])
    # usou pouco antes de sair: em 24/09 estava há 54 dias sem usar (0) e com 1 plano (12,5): nota 6, teria avisado
    linhas.append(["Empresa Fictícia Sumiu", 2000, inicio_antigo, "Cancelado", d(10), "Preço", "01/08/2026", 0, 1, "Acompanhamento", d(300)])
    # usava bem até sair: nota 100, a nota não viu
    linhas.append(["Empresa Fictícia Promotora", 3000, inicio_antigo, "Cancelado", d(15), "não viu valor", d(16), 12, 12, "Acompanhamento", d(300)])
    # saiu há 200 dias, sem nenhum dado: não dá para saber
    linhas.append(["Empresa Fictícia Antiga Saída", 1500, inicio_antigo, "Cancelado", d(200), "Fechou a empresa", "", "", "", "", ""])
    # nota boa, mas parada: 70 dias numa etapa de 20, 30 dias antes de sair. Teria avisado
    linhas.append(["Empresa Fictícia Parada", 1000, inicio_antigo, "Cancelado", d(25), "Troca de sistema", d(26), 6, 6, "Implantação", "01/07/2026"])
    # saiu há 40 dias: contagem da foto não vale, só a última data. Nota 100, a nota não viu
    linhas.append(["Empresa Fictícia Sem Histórico", 500, inicio_antigo, "Cancelado", d(40), "", d(44), "", "", "Acompanhamento", d(300)])
    # cancelada sem data: não dá para saber
    linhas.append(["Empresa Fictícia Sem Data", 700, inicio_antigo, "Cancelado", "", "Outros", "", "", "", "", ""])
    escrever(pasta / "clientes.csv", linhas)
    return {
        "arquivos": ["clientes.csv"],
        "como_medir": md(
            "Como medir",
            "Indicadores",
            "| id | bloco | rotina | dado que prova | onde está o dado | coluna | coluna anterior | como ler | frequência esperada | criticidade | subir é |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            "| uso | rotina | Uso do sistema | Último acesso | clientes.csv | Último uso | | última data | 7 dias | alta | bom |\n"
            "| plano | rotina | Planos lançados | Plano no mês | clientes.csv | Planos 30d | Planos 30d ant | contagem | 8 | alta | bom |\n",
        ),
        "colunas": md(
            "Colunas",
            "Arquivos",
            "| arquivo | tipo |\n| --- | --- |\n| clientes.csv | contas |\n",
            "\n## Colunas\n\n| arquivo | coluna | campo |\n| --- | --- | --- |\n"
            "| clientes.csv | Cliente | conta_nome |\n| clientes.csv | MRR | receita |\n| clientes.csv | Início | data_inicio |\n| clientes.csv | Status | status |\n"
            "| clientes.csv | Cancelamento | data_cancelamento |\n| clientes.csv | Motivo | motivo_cancelamento |\n| clientes.csv | Etapa | etapa |\n| clientes.csv | Entrou na etapa | data_entrada_etapa |\n",
        ),
        "jornada": JORNADA_CLINICA,
        "metas": md(
            "Metas",
            "Metas",
            "| meta | indicador | alvo | melhor quando | prazo | responsável | situação |\n| --- | --- | --- | --- | --- | --- | --- |\n"
            "| Churn abaixo de 5% | churn_contas_30d | 5 | menor | dez/2026 | Liderança | |\n",
        ),
    }


# ---------------------------------------------------------------- 5. recompra


def base_recompra() -> dict:
    pasta = AQUI / "recompra"
    clientes = [["Cliente", "Valor 12 meses"]]
    pedidos = [["Cliente", "Data do pedido", "Valor"]]
    grupos = {
        "Distribuidora Fictícia Mensal": ([14, 44, 74, 104, 134, 164], 12000),  # compra todo mês, última há 14 dias
        "Distribuidora Fictícia Sumiu": ([100, 130, 160, 190, 220], 9000),  # mensal, sem comprar há 100 dias
        "Distribuidora Fictícia Trimestral": ([60, 150, 240, 330], 6000),  # trimestral, 60 dias é normal para ela
        "Distribuidora Fictícia Nova": ([20, 200], 2000),  # só 2 compras: sem padrão próprio ainda
        "Distribuidora Fictícia Demorando": ([60, 90, 120, 150, 180], 8000),  # mensal, última há 60 dias: nota 70, mas fora do padrão
        "Distribuidora Fictícia Regular": ([10, 40, 70, 100, 130], 5000),
    }
    for nome, (dias, valor) in grupos.items():
        clientes.append([nome, valor])
        for dia in dias:
            pedidos.append([nome, d(dia), 500])
    escrever(pasta / "clientes.csv", clientes)
    escrever(pasta / "pedidos.csv", pedidos)
    return {
        "arquivos": ["clientes.csv", "pedidos.csv"],
        "como_medir": md(
            "Como medir",
            "Indicadores",
            "| id | bloco | rotina | dado que prova | onde está o dado | coluna | coluna anterior | como ler | frequência esperada | criticidade | subir é |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            "| compra | rotina | Última compra | Pedido | pedidos.csv | | | última data | padrão da conta | alta | bom |\n"
            "| frequencia | rotina | Compras no trimestre | Pedidos em 90 dias | pedidos.csv | | | eventos | 1 em 90 dias | média | bom |\n",
            "\n## Regras\n\n| regra | valor |\n| --- | --- |\n| modelo de receita | recompra |\n",
        ),
        "colunas": md(
            "Colunas",
            "Arquivos",
            "| arquivo | tipo |\n| --- | --- |\n| clientes.csv | contas |\n| pedidos.csv | eventos |\n",
            "\n## Colunas\n\n| arquivo | coluna | campo |\n| --- | --- | --- |\n"
            "| clientes.csv | Cliente | conta_nome |\n| clientes.csv | Valor 12 meses | receita |\n"
            "| pedidos.csv | Cliente | conta_nome |\n| pedidos.csv | Data do pedido | data_evento |\n",
        ),
        "jornada": md("Jornada", "Etapas", "| etapa | prazo (dias) |\n| --- | --- |\n"),
        "metas": md("Metas", "Metas", "| meta | indicador | alvo | melhor quando | prazo | responsável | situação |\n| --- | --- | --- | --- | --- | --- | --- |\n"),
    }


BASES = {
    "completa": base_completa,
    "baguncada": base_baguncada,
    "minima": base_minima,
    "canceladas": base_canceladas,
    "recompra": base_recompra,
}


def gerar_todas() -> dict:
    return {nome: gerador() for nome, gerador in BASES.items()}


if __name__ == "__main__":
    gerar_todas()
    print(f"Bases geradas em {AQUI}")
