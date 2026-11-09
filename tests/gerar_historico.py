#!/usr/bin/env python
"""Monta empresas inventadas, com meses de histórico, para testar as previsões. Todo nome aqui é inventado.

Os cenários têm respostas conhecidas, e é isso que os testes cobram:

- "padrao": a queda em Estoque vem antes da queda em Planos e do cancelamento. A alta em Estoque vem antes
  da alta em Planos e do aumento de receita. A nota não enxerga nada disso, porque as contas seguem bem
  acima do esperado. O modelo tem que achar.
- "ruido": os mesmos números, mas cancelamento e aumento são sorteados. Não há o que achar, e o modelo tem
  que admitir.
"""

from __future__ import annotations

import datetime as dt
import math
import random
import sys
from pathlib import Path

from gerar_bases import REF, escrever, md

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

NOME = "Cliente Fictício {:03d}"
COMO_MEDIR = md(
    "Como medir",
    "Indicadores",
    "| id | bloco | rotina | dado que prova | onde está o dado | coluna | coluna anterior | como ler | frequência esperada | criticidade | subir é |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
    "| plano | rotina | Planos lançados | Plano no sistema | plano.csv | | | eventos | 2 em 30 dias | alta | bom |\n"
    "| estoque | rotina | Movimentos de estoque | Entrada e saída | estoque.csv | | | eventos | 2 em 30 dias | média | bom |\n",
)
COLUNAS = md(
    "Colunas",
    "Arquivos",
    "| arquivo | tipo |\n| --- | --- |\n| contas.csv | contas |\n| plano.csv | eventos |\n| estoque.csv | eventos |\n",
    "\n## Colunas\n\n| arquivo | coluna | campo |\n| --- | --- | --- |\n"
    "| contas.csv | ID | conta_id |\n| contas.csv | Cliente | conta_nome |\n| contas.csv | MRR | receita |\n| contas.csv | Início | data_inicio |\n"
    "| contas.csv | Status | status |\n| contas.csv | Cancelamento | data_cancelamento |\n"
    "| plano.csv | ID | conta_id |\n| plano.csv | Data | data_evento |\n| estoque.csv | ID | conta_id |\n| estoque.csv | Data | data_evento |\n",
)


def _poisson(rng: random.Random, media: float) -> int:
    limite, k, p = math.exp(-media), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limite:
            return k
        k += 1


def _br(data: dt.date) -> str:
    return data.strftime("%d/%m/%Y")


def _simular_conta(rng: random.Random, cenario: str, meses: int) -> dict:
    """Mês a mês, a partir da entrada da conta. Depois do cancelamento, não há mais nada."""
    comeco = REF - dt.timedelta(days=30 * meses)
    primeiro_mes = rng.randint(0, 8)
    ritmo_plano, ritmo_estoque = rng.uniform(8, 16), rng.uniform(8, 16)
    receita = rng.choice([800.0, 1000.0, 1500.0, 2000.0, 3000.0])
    fator_plano, fator_estoque = [1.0] * meses, [1.0] * meses
    receitas = [receita] * meses
    cancelou = None
    evento_em = None
    for mes in range(primeiro_mes, meses):
        if evento_em is not None:
            break
        sorteio = rng.random()
        if cenario == "padrao" and sorteio < 0.018:  # queda: Estoque cai, Planos cai um mês depois, e a conta costuma sair
            evento_em = mes
            for m in range(mes, meses):
                fator_estoque[m] = 0.3
            for m in range(mes + 1, meses):
                fator_plano[m] = 0.35
            if rng.random() < 0.8:
                cancelou = comeco + dt.timedelta(days=30 * mes + rng.randint(70, 110))
        elif cenario == "padrao" and sorteio < 0.036:  # alta: Estoque sobe, Planos sobe um mês depois, e a receita sobe três meses depois
            evento_em = mes
            for m in range(mes, meses):
                fator_estoque[m] = 2.2
            for m in range(mes + 1, meses):
                fator_plano[m] = 2.0
            for m in range(mes + 3, meses):
                receitas[m] = receita * 1.25
        elif cenario == "ruido" and sorteio < 0.014:  # sai sem aviso
            evento_em = mes
            cancelou = comeco + dt.timedelta(days=30 * mes + rng.randint(0, 29))
        elif cenario == "ruido" and sorteio < 0.028:  # aumenta sem aviso
            evento_em = mes
            for m in range(mes, meses):
                receitas[m] = receita * 1.25
    if cancelou is not None and cancelou > REF:
        cancelou = None
    plano, estoque = [], []
    for mes in range(primeiro_mes, meses):
        inicio_mes = comeco + dt.timedelta(days=30 * mes)
        for lista, ritmo, fator in ((plano, ritmo_plano, fator_plano), (estoque, ritmo_estoque, fator_estoque)):
            for _ in range(_poisson(rng, ritmo * fator[mes])):
                data = inicio_mes + dt.timedelta(days=rng.randint(0, 29))
                if data <= REF and (cancelou is None or data < cancelou):
                    lista.append(data)
    return {
        "inicio": comeco + dt.timedelta(days=30 * primeiro_mes),
        "cancelou": cancelou,
        "receitas": receitas,
        "plano": plano,
        "estoque": estoque,
        "comeco": comeco,
        "queda": fator_estoque[-1] < 1,
        "alta": fator_estoque[-1] > 1,
    }


def montar(pasta: Path, cenario: str, contas: int = 220, meses: int = 28, semente: int = 7, com_rodadas: bool = True) -> dict:
    """Escreve os arquivos numa pasta de empresa já criada. Devolve as contas simuladas, para o teste conferir."""
    from cslib.privacidade import Cofre, escrever_csv

    rng = random.Random(semente)
    simuladas = {f"I{i:03d}": _simular_conta(rng, cenario, meses) for i in range(1, contas + 1)}
    entrada = pasta / "4-dados" / "entradas" / REF.isoformat()
    linhas = [["ID", "Cliente", "MRR", "Início", "Status", "Cancelamento"]]
    plano, estoque = [["ID", "Data"]], [["ID", "Data"]]
    for i, (id_, s) in enumerate(simuladas.items(), 1):
        linhas.append([id_, NOME.format(i), s["receitas"][-1], _br(s["inicio"]), "Cancelado" if s["cancelou"] else "Ativo", _br(s["cancelou"]) if s["cancelou"] else ""])
        plano += [[id_, _br(d)] for d in sorted(s["plano"])]
        estoque += [[id_, _br(d)] for d in sorted(s["estoque"])]
    escrever(entrada / "contas.csv", linhas)
    escrever(entrada / "plano.csv", plano)
    escrever(entrada / "estoque.csv", estoque)
    (pasta / "4-dados" / "como-medir.md").write_text(COMO_MEDIR, encoding="utf-8")
    (pasta / "4-dados" / "colunas.md").write_text(COLUNAS, encoding="utf-8")

    cofre = Cofre(pasta)
    codigos = {id_: cofre.codigo_conta(id_, NOME.format(i)) for i, id_ in enumerate(simuladas, 1)}
    cofre.salvar()
    if com_rodadas:  # a foto de cada mês, como se a empresa rodasse o plugin desde o começo
        for k in range(1, meses):
            data = REF - dt.timedelta(days=30 * k)
            corpo = []
            for id_, s in simuladas.items():
                mes = (data - s["comeco"]).days // 30
                if s["inicio"] > data or mes < 0:
                    continue
                status = "cancelada" if s["cancelou"] and s["cancelou"] <= data else "ativa"
                corpo.append([codigos[id_], status, "", "sem_nota", 0, "sem etapa", "", s["receitas"][min(mes, meses - 1)], "", ""])
            escrever_csv(pasta / "4-dados" / "rodadas" / data.isoformat() / "valores.csv", ["codigo", "status", "nota", "faixa", "cobertura", "situacao", "alertas", "receita", "ind:plano", "ind:estoque"], corpo)
    return {"simuladas": simuladas, "codigos": codigos}
