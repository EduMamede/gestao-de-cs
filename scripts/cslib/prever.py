"""Previsões por aprendizado de máquina, feitas no computador da pessoa. Nenhum LLM entra aqui.

Três perguntas: quem vai cancelar, para onde vai o uso e quem vai aumentar a receita.
O método está em referencias/previsao.md. O essencial:

- Cada linha de treino só vê o que já tinha acontecido naquela data.
- Com poucos casos, não treina: responde "ainda não dá" e diz o que falta.
- Só mostra a previsão se, em datas que o modelo não viu, acertou mais que a comparação simples.

A biblioteca só é carregada quando há dado para treinar. Sem ela, o resto do plugin funciona igual.
"""

from __future__ import annotations

import bisect
import datetime as dt
import importlib.util
import math
import statistics
import traceback
import warnings
from dataclasses import dataclass
from pathlib import Path

from .medir import FAIXA_VERDE, _eh_arquivo_de_eventos, _nota_dias, _nota_quantidade, arredondar, calcular_nota, intervalo_da_conta, ler_valores, rodadas_anteriores

HORIZONTE = 90  # dias à frente nas previsões de churn e de aumento de receita
PASSO = 30  # distância entre as fotos do histórico; precisa dividir o horizonte
TOLERANCIA = 15  # uma rodada vale como foto da data até esta distância, em dias
TOPO_PCT = 20  # no teste: quantas das contas mais apontadas a pessoa conseguiria olhar
CHANCE_PARA_TENDENCIA_PCT = 50
AUC_MINIMA = 0.65  # 0,5 é o acerto de um sorteio. Churn e aumento têm poucos casos, e o acaso pesa mais
AUC_MINIMA_USO = 0.6  # o uso tem muitos casos, e a comparação dele já é um modelo
MIN_CONTAS = 20  # com menos, sortear as contas no teste dá uma segurança que não existe
SORTEIOS = 500
MAX_FOTOS = 40
MAX_DATAS_DE_TESTE = 8
TEXTO_BIBLIOTECA = "Rode: python -m pip install scikit-learn. Depois, gere a rodada de novo com --refazer."


@dataclass
class Linha:
    data: dt.date
    conta: str
    x: dict
    base: float | None  # a comparação simples: quanto maior, mais ela aponta para o caso
    y: int
    conhecido_em: dt.date  # a partir de quando já se sabe o resultado


def _numero(valor):
    if valor in (None, ""):
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _resultado(status: str, motivo: str, **extras) -> dict:
    return {"status": status, "motivo": motivo, **extras}


def _tem_biblioteca() -> bool:
    return all(importlib.util.find_spec(nome) is not None for nome in ("numpy", "scipy", "sklearn"))


def _foto_de_hoje(conta, cfg) -> dict:
    foto = {"status": conta.status, "nota": conta.nota, "receita": conta.receita}
    for ind in cfg.indicadores:
        medicao = conta.medicoes.get(ind.id)
        foto[f"ind:{ind.id}"] = medicao if isinstance(medicao, (int, float)) else None
    return foto


class Historia:
    """Como cada conta estava em qualquer data, sem olhar nada depois dela."""

    def __init__(self, pasta: Path, r):
        self.r, self.cfg = r, r.cfg
        self.ref = r.data
        self.minimo_cobertura = r.cfg.regras["cobertura minima"] / 100
        self.eventos = {c.codigo: {arquivo.casefold(): sorted(datas) for arquivo, datas in c.eventos.items()} for c in r.contas}
        self.arquivos_com_eventos = {arquivo for por_arquivo in self.eventos.values() for arquivo in por_arquivo}
        self.fotos = [(quando, ler_valores(d)) for quando, d in rodadas_anteriores(pasta, r.data)]
        self.fotos.append((r.data, {c.codigo: _foto_de_hoje(c, r.cfg) for c in r.contas}))
        self.datas_fotos = [quando for quando, _ in self.fotos]
        primeiras = [datas[0] for por_arquivo in self.eventos.values() for datas in por_arquivo.values() if datas]
        self.mais_antiga = min(primeiras + self.datas_fotos)
        self.comparacoes = 2 + 2 * len(_rotinas_de_uso(r.cfg))  # churn, aumento, e queda e alta em cada rotina
        self._guardadas: dict = {}

    def foto_em(self, data: dt.date) -> dict:
        i = bisect.bisect_right(self.datas_fotos, data) - 1
        if i < 0 or (data - self.datas_fotos[i]).days >= TOLERANCIA:
            return {}
        return self.fotos[i][1]

    def inicio(self, conta):
        if conta.campos.get("data_inicio") is not None:
            return conta.campos["data_inicio"]
        primeiras = [datas[0] for datas in self.eventos[conta.codigo].values() if datas]
        return min(primeiras) if primeiras else None

    def ativa_em(self, conta, data: dt.date) -> bool:
        cancelou = conta.campos.get("data_cancelamento")
        if conta.status == "cancelada" and cancelou is None:  # sem a data, não dá para saber quando saiu
            return False
        if cancelou is not None and cancelou <= data:
            return False
        inicio = self.inicio(conta)
        if inicio is not None:
            return inicio <= data
        return conta.codigo in self.foto_em(data)

    def medida_em(self, conta, ind, data: dt.date) -> tuple:
        """Devolve (valor, valor do período anterior). Só conta o que aconteceu até a data."""
        if ind.medida == "eventos" or (ind.medida == "ultima-data" and _eh_arquivo_de_eventos(ind, self.cfg)):
            arquivo = ind.arquivo.casefold()
            if arquivo not in self.arquivos_com_eventos:
                return None, None
            datas = self.eventos[conta.codigo].get(arquivo, [])
            ate_a_data = bisect.bisect_right(datas, data)
            if ind.medida == "ultima-data":
                return (float((data - datas[ate_a_data - 1]).days), None) if ate_a_data else (None, None)
            janela = dt.timedelta(days=ind.janela)
            uma = bisect.bisect_right(datas, data - janela)
            duas = bisect.bisect_right(datas, data - 2 * janela)
            return float(ate_a_data - uma), float(uma - duas)
        coluna = f"ind:{ind.id}"
        agora = _numero(self.foto_em(data).get(conta.codigo, {}).get(coluna))
        antes = _numero(self.foto_em(data - dt.timedelta(days=PASSO)).get(conta.codigo, {}).get(coluna))
        return agora, antes

    def valor_de_longe(self, conta, ind, data: dt.date):
        """O valor de dois períodos atrás: mostra a mudança lenta, que a comparação com o período anterior não pega."""
        if ind.medida == "ultima-data":
            return None
        recuo = data - dt.timedelta(days=2 * (ind.janela if ind.medida == "eventos" else PASSO))
        inicio = self.inicio(conta)
        if inicio is not None and inicio > recuo:
            return None
        return self.medida_em(conta, ind, recuo)[0]

    def _subnota_em(self, conta, ind, data: dt.date):
        valor, _ = self.medida_em(conta, ind, data)
        if valor is None:
            return None
        if ind.medida == "eventos":
            return None if ind.esperado is None else _nota_quantidade(valor, ind.esperado, ind.direcao, ind.direcao)
        limite = ind.esperado
        if ind.padrao_da_conta:
            datas = self.eventos[conta.codigo].get(ind.arquivo.casefold(), [])
            limite = intervalo_da_conta([d for d in datas if d <= data])
        return None if limite is None else _nota_dias(valor, limite)

    def nota_em(self, conta, data: dt.date):
        """A nota real, se havia rodada na data. Se não, a nota refeita só com as rotinas que têm data."""
        salva = _numero(self.foto_em(data).get(conta.codigo, {}).get("nota"))
        if salva is not None:
            return salva
        subnotas = {}
        for ind in self.cfg.indicadores:
            if ind.medida == "eventos" or (ind.medida == "ultima-data" and _eh_arquivo_de_eventos(ind, self.cfg)):
                subnotas[ind.id] = self._subnota_em(conta, ind, data)
        nota, _ = calcular_nota(subnotas, self.cfg.indicadores, self.minimo_cobertura)
        return nota

    def receita_em(self, conta, data: dt.date):
        return _numero(self.foto_em(data).get(conta.codigo, {}).get("receita"))

    def sinais(self, conta, data: dt.date) -> dict:
        chave = (conta.codigo, data)
        if chave in self._guardadas:
            return self._guardadas[chave]
        x = {}
        for ind in self.cfg.indicadores:
            valor, antes = self.medida_em(conta, ind, data)
            if valor is None:
                continue
            x[f"v:{ind.id}"] = math.log1p(max(valor, 0))
            if antes is not None:
                x[f"d:{ind.id}"] = math.log1p(max(valor, 0)) - math.log1p(max(antes, 0))
            longe = self.valor_de_longe(conta, ind, data)
            if longe is not None:
                x[f"t:{ind.id}"] = math.log1p(max(valor, 0)) - math.log1p(max(longe, 0))
        nota = self.nota_em(conta, data)
        if nota is not None:
            x["nota"] = nota
        inicio = self.inicio(conta)
        if inicio is not None:
            x["idade"] = (data - inicio).days / 365
        receita = self.receita_em(conta, data)  # só de rodada: o export de hoje não diz quanto ela pagava antes
        if receita is not None:
            x["receita"] = math.log1p(max(receita, 0))
        self._guardadas[chave] = x
        return x


# ---------------------------------------------------------------- modelo e teste


class Modelo:
    """Regressão logística: cada sinal ganha um peso, e dá para dizer o que pesou em cada conta."""

    def __init__(self, linhas: list, chaves=None):
        import numpy as np
        from sklearn.linear_model import LogisticRegression

        self.np = np
        presentes = {nome for l in linhas for nome in l.x}
        self.nomes = sorted(presentes if chaves is None else presentes & set(chaves))
        X = self._crua(linhas)
        faltando = np.isnan(X)
        self.com_falta = np.flatnonzero(faltando.any(axis=0))
        self.medianas = np.nanmedian(X, axis=0) if self.nomes else np.zeros(0)
        cheia = np.where(faltando, self.medianas, X)
        self.medias, self.desvios = cheia.mean(axis=0), cheia.std(axis=0)
        self.desvios[self.desvios == 0] = 1.0
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.clf = LogisticRegression(C=1.0, max_iter=2000).fit(self._z(linhas), [l.y for l in linhas])

    def _crua(self, linhas: list):
        np = self.np
        X = np.full((len(linhas), len(self.nomes)), np.nan)
        for i, l in enumerate(linhas):
            for j, nome in enumerate(self.nomes):
                valor = l.x.get(nome)
                if valor is not None:
                    X[i, j] = valor
        return X

    def _z(self, linhas: list):
        np = self.np
        X = self._crua(linhas)
        faltando = np.isnan(X)
        cheia = np.where(faltando, self.medianas, X)
        return np.hstack([(cheia - self.medias) / self.desvios, faltando[:, self.com_falta].astype(float)])

    def chances(self, linhas: list):
        return self.clf.predict_proba(self._z(linhas))[:, 1]

    def o_que_pesou(self, linha: Linha) -> list:
        """Os sinais que mais empurraram a chance para cima nesta conta, do maior para o menor."""
        pesos = self.clf.coef_[0][: len(self.nomes)] * self._z([linha])[0][: len(self.nomes)]
        ordem = self.np.argsort(-pesos)
        return [self.nomes[j] for j in ordem if pesos[j] > 0 and self.nomes[j] in linha.x]


def _auc(y, score):
    from scipy.stats import rankdata

    positivos = int(y.sum())
    negativos = len(y) - positivos
    if not positivos or not negativos:
        return None
    return float((rankdata(score)[y == 1].sum() - positivos * (positivos + 1) / 2) / (positivos * negativos))


def _pegou_no_topo(y, score) -> float:
    """Quantos casos ficaram entre os mais apontados. Empate divide a vaga, para a ordem do arquivo não decidir."""
    import numpy as np

    ordem = np.argsort(-score, kind="stable")
    ys, ss = y[ordem], score[ordem]
    vagas = math.ceil(TOPO_PCT / 100 * len(y))
    total, i = 0.0, 0
    while i < len(y) and vagas > 0:
        j = i
        while j < len(y) and ss[j] == ss[i]:
            j += 1
        usar = min(vagas, j - i)
        total += float(ys[i:j].sum()) * usar / (j - i)
        vagas -= usar
        i = j
    return total


def _ganho_garantido(y, modelo, base, contas, comparacoes: int = 1) -> float:
    """Sorteia as contas muitas vezes. É o ganho que sobra no pior 1 de cada 20 sorteios.

    Quem testa várias coisas de uma vez acerta alguma por sorte. Por isso, com mais comparações, o corte fica mais duro.
    """
    import numpy as np

    rng = np.random.default_rng(7)
    unicas = sorted(set(contas))
    vetor = np.array(contas)
    posicoes = [np.flatnonzero(vetor == c) for c in unicas]
    ganhos = []
    for _ in range(SORTEIOS):
        idx = np.concatenate([posicoes[i] for i in rng.integers(0, len(unicas), len(unicas))])
        a, b = _auc(y[idx], modelo[idx]), _auc(y[idx], base[idx])
        if a is not None and b is not None:
            ganhos.append(a - b)
    return float(np.percentile(ganhos, 5 / comparacoes)) if ganhos else -1.0


def _casos(linhas: list, por_conta: bool) -> int:
    if por_conta:
        return len({l.conta for l in linhas if l.y})
    return sum(l.y for l in linhas)


def _testar(linhas: list, ref: dt.date, passo: int, minimo: int, comparacoes: int, por_conta: bool = True, chaves_base=None, auc_minima: float = AUC_MINIMA):
    """Volta no tempo: treina só com o que já se sabia em cada data e compara com o que aconteceu depois."""
    import numpy as np

    minimo_treino, minimo_teste = max(1, minimo // 2), max(1, minimo // 3)
    chances, bases, ys, contas, datas = [], [], [], [], []
    pegou_modelo = pegou_base = 0.0
    for k in range(1, MAX_DATAS_DE_TESTE + 1):
        corte = ref - dt.timedelta(days=k * passo)
        treino = [l for l in linhas if l.conhecido_em <= corte]
        if _casos(treino, por_conta) < minimo_treino:
            break
        teste = [l for l in linhas if l.data == corte]
        if not teste or all(l.y for l in treino):
            continue
        chance = Modelo(treino).chances(teste)
        if chaves_base is not None:
            base = Modelo(treino, chaves_base).chances(teste)
        else:
            conhecidas = [l.base for l in teste if l.base is not None]
            neutra = statistics.median(conhecidas) if conhecidas else 0.0
            base = np.array([neutra if l.base is None else l.base for l in teste], dtype=float)
        y = np.array([l.y for l in teste])
        pegou_modelo += _pegou_no_topo(y, chance)
        pegou_base += _pegou_no_topo(y, base)
        chances.append(chance)
        bases.append(base)
        ys.append(y)
        contas += [l.conta for l in teste]
        datas.append(corte)
    if not datas:
        return None
    chance, base, y = np.concatenate(chances), np.concatenate(bases), np.concatenate(ys)
    if int(y.sum()) < minimo_teste or len(set(contas)) < MIN_CONTAS:
        return None
    auc_modelo, auc_base = _auc(y, chance), _auc(y, base)
    if auc_modelo is None:
        return None
    ganho = _ganho_garantido(y, chance, base, contas, comparacoes)
    previsto, aconteceu = float(chance.mean()), float(y.mean())
    return {
        "datas": [d.isoformat() for d in sorted(datas)],
        "contas_testadas": len(set(contas)),
        "casos": int(y.sum()),
        "pegou_modelo": arredondar(pegou_modelo),
        "pegou_base": arredondar(pegou_base),
        "auc_modelo": round(auc_modelo, 3),
        "auc_base": round(auc_base if auc_base is not None else 0.5, 3),
        "ganho_garantido": round(ganho, 3),
        "previsto_pct": arredondar(100 * previsto, 1),
        "aconteceu_pct": arredondar(100 * aconteceu, 1),
        "tamanho_confere": bool(aconteceu > 0 and 2 / 3 <= previsto / aconteceu <= 1.5),
        "passou": bool(auc_modelo >= auc_minima and ganho > 0),
    }


def _pct(chance) -> int:
    return arredondar(100 * float(chance))


def _numero_curto(valor) -> str:
    valor = float(valor)
    return str(int(valor)) if valor.is_integer() else f"{valor:.1f}".replace(".", ",")


def _motivos(h: Historia, conta, modelo: Modelo, linha: Linha, data: dt.date, mostrar_nota_baixa: bool = False) -> list:
    """Traduz o que pesou no modelo para o que a pessoa entende, com o número da própria conta."""
    por_id = {i.id: i for i in h.cfg.indicadores}
    textos: list = []
    vistos: set = set()
    for nome in modelo.o_que_pesou(linha):
        if ":" in nome:
            tipo, id_ = nome.split(":", 1)
            if id_ in vistos:
                continue
            vistos.add(id_)
            ind = por_id[id_]
            valor, antes = h.medida_em(conta, ind, data)
            if valor is None:
                continue
            if tipo != "d":
                antes = h.valor_de_longe(conta, ind, data)
            if ind.medida == "ultima-data":
                textos.append(f"{ind.rotina}: {_numero_curto(valor)} dias desde o último registro")
            elif antes is not None and antes != valor:
                textos.append(f"{ind.rotina}: de {_numero_curto(antes)} para {_numero_curto(valor)}")
            else:
                textos.append(f"{ind.rotina}: {_numero_curto(valor)}")
        elif nome == "nota" and mostrar_nota_baixa and linha.x[nome] < FAIXA_VERDE:
            textos.append(f"Nota {_numero_curto(linha.x[nome])}")
        if len(textos) == 3:
            break
    return textos


# ---------------------------------------------------------------- churn


def _linhas_churn(h: Historia) -> list:
    canceladas = [c.campos["data_cancelamento"] for c in h.r.canceladas if c.campos.get("data_cancelamento")]
    # Antes do primeiro cancelamento do export, não dá para saber se ninguém saiu ou se a saída não foi exportada.
    primeira = min(canceladas) - dt.timedelta(days=HORIZONTE)
    linhas = []
    for k in range(HORIZONTE // PASSO, MAX_FOTOS + 1):
        data = h.ref - dt.timedelta(days=k * PASSO)
        if data < primeira:
            break
        prazo = data + dt.timedelta(days=HORIZONTE)
        for conta in h.r.contas:
            if not h.ativa_em(conta, data):
                continue
            x = h.sinais(conta, data)
            if not x:
                continue
            cancelou = conta.campos.get("data_cancelamento")
            nota = x.get("nota")
            linhas.append(Linha(data, conta.codigo, x, None if nota is None else -nota, int(cancelou is not None and cancelou <= prazo), prazo))
    return linhas


def prever_churn(h: Historia) -> dict:
    minimo = int(h.cfg.regras["minimo de casos para prever"])
    com_data = sum(1 for c in h.r.canceladas if c.campos.get("data_cancelamento"))
    if com_data < minimo:
        return _resultado("sem_dados", f"Há {com_data} contas canceladas com data. O mínimo para treinar é {minimo}.", tem=com_data, minimo=minimo)
    linhas = _linhas_churn(h)
    if not any(":" in nome for l in linhas for nome in l.x):
        return _resultado("sem_dados", "Nenhuma rotina tem histórico: traga as atividades com data, ou guarde as rodadas.", tem=com_data, minimo=minimo)
    casos = _casos(linhas, True)
    if casos < minimo:
        return _resultado("sem_dados", f"Só {casos} contas canceladas têm histórico de antes da saída. O mínimo para treinar é {minimo}.", tem=casos, minimo=minimo)
    if not _tem_biblioteca():
        return _resultado("sem_biblioteca", f"Há dado para treinar, mas falta a biblioteca de previsão. {TEXTO_BIBLIOTECA}")
    teste = _testar(linhas, h.ref, HORIZONTE, minimo, h.comparacoes)
    if teste is None:
        return _resultado("sem_dados", "Os cancelamentos estão muito juntos no tempo: não deu para separar treino e teste.", tem=casos, minimo=minimo)
    if not teste["passou"]:
        return _resultado("sem_ganho", "O modelo foi testado e não acertou mais que a nota. Continue usando a nota e os alertas.", teste=teste)
    modelo = Modelo(linhas)
    contas = []
    receita_em_risco = 0.0
    for conta in h.r.ativas:
        if conta.cancelamento_agendado:  # já se sabe que vai sair: está na lista de prioridades
            continue
        x = h.sinais(conta, h.ref)
        if not x:
            continue
        linha = Linha(h.ref, conta.codigo, x, None, 0, h.ref)
        chance = float(modelo.chances([linha])[0])
        receita_em_risco += chance * (conta.receita or 0)
        contas.append({"conta": conta.codigo, "chance_pct": _pct(chance), "nota": conta.nota, "receita": conta.receita, "motivos": _motivos(h, conta, modelo, linha, h.ref, mostrar_nota_baixa=True)})
    contas.sort(key=lambda c: (-c["chance_pct"], -(c["receita"] or 0), c["conta"]))
    return _resultado("ok", "O modelo acertou mais que a nota nas datas do teste.", teste=teste, contas=contas, receita_em_risco=arredondar(receita_em_risco) if teste["tamanho_confere"] else None)


# ---------------------------------------------------------------- engajamento


def _rotinas_de_uso(cfg) -> list:
    return [i for i in cfg.indicadores if i.bloco == "rotina" and i.direcao == "bom" and i.medida in ("eventos", "contagem")]


def _sinais_de_uso(h: Historia, conta, ind, data: dt.date, janela: int):
    """Os sinais da conta mais o histórico desta rotina. Devolve (x, nível normal da conta) ou None."""
    passo = dt.timedelta(days=janela)
    inicio = h.inicio(conta)
    if inicio is not None and inicio > data - 2 * passo:  # conta nova: zero aqui seria falta de tempo, não de uso
        return None
    valores = [h.medida_em(conta, ind, data - i * passo)[0] for i in range(3)]
    if any(v is None for v in valores):
        return None
    nivel = sum(valores) / 3
    x = dict(h.sinais(conta, data))
    x.update({"nivel": math.log1p(nivel), "movimento": math.log1p(valores[0]) - math.log1p(nivel), "l1": math.log1p(valores[1]), "l2": math.log1p(valores[2])})
    return x, nivel


def _mudanca(depois: float, nivel: float, regras: dict) -> int:
    """A mesma régua da mudança de padrão, contra o nível normal da própria conta."""
    diferenca = depois - nivel
    if abs(diferenca) < regras["minimo absoluto"]:
        return 0
    if nivel > 0 and abs(diferenca) / nivel < regras["variacao para alerta"] / 100:
        return 0
    return 1 if diferenca > 0 else -1


def _linhas_de_uso(h: Historia, ind, janela: int) -> tuple:
    cai, sobe = [], []
    passo = dt.timedelta(days=janela)
    for k in range(1, MAX_FOTOS + 1):
        data = h.ref - k * passo
        if data - 2 * passo < h.mais_antiga:
            break
        prazo = data + passo
        for conta in h.r.contas:
            if not h.ativa_em(conta, data):
                continue
            cancelou = conta.campos.get("data_cancelamento")
            if cancelou is not None and cancelou <= prazo:  # saiu no meio: é churn, não é queda de uso
                continue
            sinais = _sinais_de_uso(h, conta, ind, data, janela)
            depois = h.medida_em(conta, ind, prazo)[0]
            if sinais is None or depois is None:
                continue
            x, nivel = sinais
            mudou = _mudanca(depois, nivel, h.cfg.regras)
            cai.append(Linha(data, conta.codigo, x, None, int(mudou < 0), prazo))
            sobe.append(Linha(data, conta.codigo, x, None, int(mudou > 0), prazo))
    return cai, sobe


def _avaliar_uso(linhas: list, h: Historia, janela: int, minimo: int) -> dict:
    contas = len({l.conta for l in linhas})
    if contas < MIN_CONTAS:
        return _resultado("sem_dados", f"Há {contas} contas com histórico de uso. O mínimo para testar é {MIN_CONTAS}.", tem=contas, minimo=MIN_CONTAS, unidade="contas")
    casos = _casos(linhas, False)
    if casos < minimo:
        return _resultado("sem_dados", f"Há {casos} casos no histórico. O mínimo para treinar é {minimo}.", tem=casos, minimo=minimo)
    if not _tem_biblioteca():
        return _resultado("sem_biblioteca", f"Há dado para treinar, mas falta a biblioteca de previsão. {TEXTO_BIBLIOTECA}")
    teste = _testar(linhas, h.ref, janela, minimo, h.comparacoes, por_conta=False, chaves_base=("nivel", "movimento"), auc_minima=AUC_MINIMA_USO)
    if teste is None:
        return _resultado("sem_dados", "Não deu para separar treino e teste com este histórico.", tem=casos, minimo=minimo)
    if not teste["passou"]:
        return _resultado("sem_ganho", "O modelo foi testado e não acertou mais que o histórico da própria rotina.", teste=teste)
    return _resultado("ok", "O modelo acertou mais que o histórico da própria rotina nas datas do teste.", teste=teste)


def prever_engajamento(h: Historia) -> dict:
    rotinas = _rotinas_de_uso(h.cfg)
    if not rotinas:
        return _resultado("sem_dados", "Nenhuma rotina de uso é contada por período: não há o que prever aqui.")
    minimo = int(h.cfg.regras["minimo de casos para prever"])
    por_rotina, contas = [], []
    for ind in rotinas:
        janela = ind.janela if ind.medida == "eventos" else PASSO
        linhas_cai, linhas_sobe = _linhas_de_uso(h, ind, janela)
        cai, sobe = _avaliar_uso(linhas_cai, h, janela, minimo), _avaliar_uso(linhas_sobe, h, janela, minimo)
        por_rotina.append({"id": ind.id, "rotina": ind.rotina, "janela_dias": janela, "cai": cai, "sobe": sobe})
        modelos = {}
        if cai["status"] == "ok":
            modelos["cai"] = Modelo(linhas_cai)
        if sobe["status"] == "ok":
            modelos["sobe"] = Modelo(linhas_sobe)
        if not modelos:
            continue
        for conta in h.r.ativas:
            if conta.cancelamento_agendado:
                continue
            sinais = _sinais_de_uso(h, conta, ind, h.ref, janela)
            if sinais is None:
                continue
            linha = Linha(h.ref, conta.codigo, sinais[0], None, 0, h.ref)
            for tendencia, modelo in modelos.items():
                chance = _pct(modelo.chances([linha])[0])
                if chance >= CHANCE_PARA_TENDENCIA_PCT:
                    contas.append(
                        {
                            "conta": conta.codigo,
                            "indicador": ind.id,
                            "rotina": ind.rotina,
                            "agora": h.medida_em(conta, ind, h.ref)[0],
                            "normal": arredondar(sinais[1], 1),
                            "tendencia": tendencia,
                            "chance_pct": chance,
                            "motivos": _motivos(h, conta, modelo, linha, h.ref),
                        }
                    )
    contas.sort(key=lambda c: (c["tendencia"] != "cai", -c["chance_pct"], c["conta"]))
    situacoes = [p[lado]["status"] for p in por_rotina for lado in ("cai", "sobe")]
    for status, motivo in (
        ("ok", "O modelo acertou mais que o histórico da própria rotina em pelo menos uma rotina."),
        ("sem_biblioteca", f"Há dado para treinar, mas falta a biblioteca de previsão. {TEXTO_BIBLIOTECA}"),
        ("sem_ganho", "O modelo foi testado e não acertou mais que o histórico da própria rotina."),
    ):
        if status in situacoes:
            return _resultado(status, motivo, rotinas=por_rotina, contas=contas)
    blocos = [p[lado] for p in por_rotina for lado in ("cai", "sobe")]
    faltam_contas = [b for b in blocos if b.get("unidade") == "contas"]
    if faltam_contas:
        melhor = max(faltam_contas, key=lambda b: b["tem"])
        return _resultado("sem_dados", melhor["motivo"], rotinas=por_rotina, contas=contas, tem=melhor["tem"], minimo=melhor["minimo"], unidade="contas")
    tem = max(b.get("tem", 0) for b in blocos)
    return _resultado("sem_dados", f"A rotina com mais histórico tem {tem} casos de mudança de uso. O mínimo para treinar é {minimo}.", rotinas=por_rotina, contas=contas, tem=tem, minimo=minimo)


# ---------------------------------------------------------------- incremento de receita


def _linhas_aumento(h: Historia, aumento_minimo: float) -> tuple:
    linhas, aumentos = [], []
    for k in range(HORIZONTE // PASSO, MAX_FOTOS + 1):
        data = h.ref - dt.timedelta(days=k * PASSO)
        if data < h.datas_fotos[0]:
            break
        prazo = data + dt.timedelta(days=HORIZONTE)
        for conta in h.r.contas:
            agora, depois = h.receita_em(conta, data), h.receita_em(conta, prazo)
            if not agora or agora <= 0 or not h.ativa_em(conta, data):
                continue
            cancelou = conta.campos.get("data_cancelamento")
            if cancelou is not None and cancelou <= prazo:
                variacao = None  # saiu no caminho: não aumentou
            elif depois is None:
                continue
            else:
                variacao = 100 * (depois - agora) / agora
            cresceu = variacao is not None and variacao >= aumento_minimo
            if cresceu:
                aumentos.append(variacao)
            x = h.sinais(conta, data)
            linhas.append(Linha(data, conta.codigo, x, x.get("nota"), int(cresceu), prazo))
    return linhas, aumentos


def prever_incremento(h: Historia) -> dict:
    minimo = int(h.cfg.regras["minimo de casos para prever"])
    if (h.ref - h.datas_fotos[0]).days < 2 * HORIZONTE:
        return _resultado(
            "sem_dados",
            f"O histórico de receita vem das rodadas, e a mais antiga é de {h.datas_fotos[0].isoformat()}. Para treinar e testar, são pelo menos {2 * HORIZONTE} dias de rodadas.",
            tem=0,
            minimo=minimo,
        )
    linhas, aumentos = _linhas_aumento(h, h.cfg.regras["aumento minimo de receita"])
    casos = _casos(linhas, True)
    if casos < minimo:
        return _resultado("sem_dados", f"Há {casos} contas que aumentaram a receita no histórico. O mínimo para treinar é {minimo}.", tem=casos, minimo=minimo)
    if not _tem_biblioteca():
        return _resultado("sem_biblioteca", f"Há dado para treinar, mas falta a biblioteca de previsão. {TEXTO_BIBLIOTECA}")
    teste = _testar(linhas, h.ref, HORIZONTE, minimo, h.comparacoes)
    if teste is None:
        return _resultado("sem_dados", "Os aumentos estão muito juntos no tempo: não deu para separar treino e teste.", tem=casos, minimo=minimo)
    if not teste["passou"]:
        return _resultado("sem_ganho", "O modelo foi testado e não acertou mais que a nota. Use os sinais bons para a conversa de expansão.", teste=teste)
    modelo = Modelo(linhas)
    aumento_tipico = statistics.median(aumentos)
    contas = []
    for conta in h.r.ativas:
        if conta.cancelamento_agendado or not conta.receita or conta.receita <= 0:
            continue
        linha = Linha(h.ref, conta.codigo, h.sinais(conta, h.ref), None, 0, h.ref)
        chance = float(modelo.chances([linha])[0])
        estimado = arredondar(chance * aumento_tipico / 100 * conta.receita) if teste["tamanho_confere"] else None
        contas.append({"conta": conta.codigo, "chance_pct": _pct(chance), "receita": conta.receita, "valor_estimado": estimado, "motivos": _motivos(h, conta, modelo, linha, h.ref)})
    contas.sort(key=lambda c: (-c["chance_pct"], -(c["receita"] or 0), c["conta"]))
    return _resultado("ok", "O modelo acertou mais que a nota nas datas do teste.", teste=teste, contas=contas, aumento_tipico_pct=arredondar(aumento_tipico, 1))


# ---------------------------------------------------------------- juntando tudo


def _erro(erro: Exception) -> dict:
    # A mensagem original pode trazer valores dos dados. Mostra só onde aconteceu.
    ultimo = traceback.extract_tb(erro.__traceback__)[-1]
    return _resultado("erro", f"A previsão não rodou: {type(erro).__name__} em {Path(ultimo.filename).name}, linha {ultimo.lineno}. O resto da rodada não foi afetado.")


def prever(pasta: Path, r) -> dict:
    saida = {
        "horizonte_dias": HORIZONTE,
        "topo_pct": TOPO_PCT,
        "chance_para_tendencia_pct": CHANCE_PARA_TENDENCIA_PCT,
        "minimo_de_casos": int(r.cfg.regras["minimo de casos para prever"]),
    }
    try:
        h = Historia(pasta, r)
    except Exception as erro:  # noqa: BLE001
        return {**saida, **{nome: _erro(erro) for nome in ("churn", "engajamento", "incremento")}}
    for nome, funcao in (("churn", prever_churn), ("engajamento", prever_engajamento), ("incremento", prever_incremento)):
        try:
            saida[nome] = funcao(h)
        except Exception as erro:  # noqa: BLE001
            saida[nome] = _erro(erro)
    return saida
