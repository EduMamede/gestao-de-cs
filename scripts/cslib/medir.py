"""O coração da rodada: junta os arquivos, mede as rotinas e calcula nota e alertas.

Toda regra aqui é simples de propósito e está explicada em referencias/nota-e-alertas.md.
Dado que falta fica vazio. Nada é estimado para fechar uma conta.
"""

from __future__ import annotations

import csv
import datetime as dt
import decimal
import hashlib
import statistics
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path

from . import plural
from .config import CAMPOS, Config, Indicador
from .leitura import (
    eh_linha_de_total,
    eh_vazio,
    inferir_formato_numero,
    inferir_ordem_data,
    ler_tabela,
    normalizar,
    parse_data,
    parse_numero,
)
from .privacidade import Cofre, Rotulos, escrever_csv

FAIXA_VERDE = 70
FAIXA_VERMELHA = 30
NOME_FAIXAS = {"saudavel": "saudável", "pode_melhorar": "pode melhorar", "possivel_churn": "possível churn", "sem_nota": "sem nota"}
PONTOS = {
    "nota_vermelha": 3,
    "cancelamento_agendado": 3,
    "empacado": 2,
    "padrao_ruim": 2,
    "renovacao_com_risco": 2,
    "nota_amarela": 1,
    "financeiro": 1,
    "queda_de_nota": 1,
    "sem_contato": 1,
    "renovacao_vencida": 1,
    "renovacao_sozinha": 0.5,
}
MOTIVOS_VAGOS = ("nao viu valor", "sem valor", "outros", "outro", "nao informado", "desconhecido")


def arredondar(valor, casas: int = 0):
    """Arredonda como o Excel (0,5 para cima), para a planilha e o script baterem."""
    if valor is None:
        return None
    q = decimal.Decimal(1).scaleb(-casas)
    r = decimal.Decimal(str(valor)).quantize(q, rounding=decimal.ROUND_HALF_UP)
    return int(r) if casas == 0 else float(r)


def faixa_da_nota(nota) -> str:
    if nota is None:
        return "sem_nota"
    if nota < FAIXA_VERMELHA:
        return "possivel_churn"
    if nota < FAIXA_VERDE:
        return "pode_melhorar"
    return "saudavel"


def grau_de_confianca(cobertura: float) -> str:
    if cobertura >= 0.8:
        return "alta"
    if cobertura >= 0.5:
        return "média"
    return "baixa"


@dataclass
class Conta:
    codigo: str
    campos: dict = field(default_factory=dict)
    brutos: dict = field(default_factory=dict)
    anteriores: dict = field(default_factory=dict)
    eventos: dict = field(default_factory=dict)
    quem_registrou: dict = field(default_factory=dict)  # arquivo -> [(data, usuário)]. Só para contar: nunca sai do script
    temas_evento: dict = field(default_factory=dict)  # arquivo -> [(data, tema)]
    medicoes: dict = field(default_factory=dict)
    antes: dict = field(default_factory=dict)
    subnotas: dict = field(default_factory=dict)
    limites: dict = field(default_factory=dict)
    cobertura: float = 0.0
    nota: int | None = None
    faixa: str = "sem_nota"
    grau: str = "baixa"
    status: str = "ativa"
    contrato: str | None = None
    cancelamento_agendado: bool = False
    etapa: str | None = None
    etapa_rotulo: str | None = None
    dias_etapa: float | None = None
    prazo: float | None = None
    situacao: str = "sem etapa"
    motivo: str = ""
    sinais: list = field(default_factory=list)
    pontos: float = 0.0
    alertas: list = field(default_factory=list)

    @property
    def receita(self):
        return self.campos.get("receita")


@dataclass
class Resultado:
    data: dt.date
    modo: str
    cfg: Config
    cofre: Cofre
    rotulos: Rotulos
    contas: list = field(default_factory=list)
    ativas: list = field(default_factory=list)
    canceladas: list = field(default_factory=list)
    estado_indicadores: dict = field(default_factory=dict)
    alertas_ruins: list = field(default_factory=list)
    alertas_bons: list = field(default_factory=list)
    prioridades: list = field(default_factory=list)
    empacadas: list = field(default_factory=list)
    renovacoes: list = field(default_factory=list)
    comparacoes: int = 0
    contas_chave: dict = field(default_factory=dict)
    maiores: list = field(default_factory=list)
    perdidas: dict = field(default_factory=dict)
    painel: dict = field(default_factory=dict)
    metas: list = field(default_factory=list)
    faltas: list = field(default_factory=list)
    previsoes: dict = field(default_factory=dict)
    oportunidades: list = field(default_factory=list)
    melhoria: dict = field(default_factory=dict)
    avisos: list = field(default_factory=list)
    formula: dict = field(default_factory=dict)
    campos_presentes: dict = field(default_factory=dict)
    rodada_anterior: dt.date | None = None
    arquivos_lidos: list = field(default_factory=list)


# ---------------------------------------------------------------- carga dos arquivos


def _achar_arquivo(entrada: Path, padrao: str):
    candidatos = [f for f in sorted(entrada.iterdir()) if f.is_file() and fnmatch(f.name.casefold(), padrao.casefold())]
    return candidatos[-1] if candidatos else None


def _indice_colunas(tabela) -> dict:
    return {normalizar(c): i for i, c in enumerate(tabela.colunas)}


def _conversor(tipo: str, valores: list):
    if tipo == "numero":
        formato = inferir_formato_numero(valores)
        return lambda v: parse_numero(v, formato)
    if tipo == "data":
        ordem = inferir_ordem_data(valores)
        return lambda v: parse_data(v, ordem)
    return lambda v: None if eh_vazio(v) else str(v).strip()


def carregar_dados(pasta: Path, cfg: Config, entrada: Path, cofre: Cofre, r: Resultado) -> dict:
    contas: dict = {}
    duplicatas: list = []
    r.campos_presentes = {}
    ordem_arquivos = sorted(cfg.arquivos.items(), key=lambda x: x[1] != "contas")
    for padrao, tipo in ordem_arquivos:
        caminho = _achar_arquivo(entrada, padrao)
        if caminho is None:
            r.avisos.append(f"O arquivo '{padrao}' está em colunas.md, mas não está nesta rodada.")
            continue
        tabela = ler_tabela(caminho)
        r.arquivos_lidos.append(caminho.name)
        indice = _indice_colunas(tabela)
        mapa = cfg.colunas.get(padrao, {})
        bloqueadas = {normalizar(c) for c in cfg.bloqueadas.get(padrao, [])}

        colunas_campo = {}
        for campo, coluna in mapa.items():
            pos = indice.get(normalizar(coluna))
            if pos is None:
                r.avisos.append(f"A coluna '{coluna}' não apareceu em '{caminho.name}'. Confira colunas.md.")
                continue
            if normalizar(coluna) in bloqueadas and campo != "proximo_passo":
                continue
            valores = [l[pos] for l in tabela.linhas]
            colunas_campo[campo] = (pos, _conversor(CAMPOS[campo][0], valores))
            preenchidos = sum(1 for v in valores if not eh_vazio(v))
            atual = r.campos_presentes.get(campo)
            total = len(valores)
            if atual is None or preenchidos > atual[0]:
                r.campos_presentes[campo] = (preenchidos, total)
        if "conta_id" not in colunas_campo and "conta_nome" not in colunas_campo:
            r.avisos.append(f"'{caminho.name}' não tem coluna de conta ligada. O arquivo foi ignorado.")
            continue

        colunas_ind = []
        for ind in cfg.indicadores:
            if not (ind.arquivo and fnmatch(caminho.name.casefold(), ind.arquivo.casefold()) or ind.arquivo.casefold() == padrao.casefold()):
                continue
            if tipo == "eventos":
                continue
            pos = indice.get(normalizar(ind.coluna)) if ind.coluna else None
            if ind.coluna and pos is None:
                r.avisos.append(f"A coluna '{ind.coluna}' do indicador '{ind.id}' não apareceu em '{caminho.name}'.")
                continue
            if pos is None:
                continue
            valores = [l[pos] for l in tabela.linhas]
            tipo_col = {"contagem": "numero", "ultima-data": "data", "categoria": "texto"}.get(ind.medida, "texto")
            pos_ant = indice.get(normalizar(ind.coluna_anterior)) if ind.coluna_anterior else None
            if ind.coluna_anterior and pos_ant is None:
                r.avisos.append(f"A coluna anterior '{ind.coluna_anterior}' do indicador '{ind.id}' não apareceu em '{caminho.name}'.")
            valores_ant = [l[pos_ant] for l in tabela.linhas] if pos_ant is not None else []
            colunas_ind.append((ind, pos, _conversor(tipo_col, valores), pos_ant, _conversor(tipo_col, valores_ant)))

        pos_id = colunas_campo.get("conta_id", (None,))[0]
        pos_nome = colunas_campo.get("conta_nome", (None,))[0]
        pos_data_evento = colunas_campo.get("data_evento", (None,))[0]
        conv_data_evento = colunas_campo.get("data_evento", (None, None))[1]
        vistos: dict = {}
        ignoradas_total = sem_chave = sem_conta = iguais = 0
        conflitos: list = []
        ilegiveis: dict = {}

        def marcar_ilegivel(pos_coluna: int) -> None:
            nome_coluna = tabela.colunas[pos_coluna]
            ilegiveis[nome_coluna] = ilegiveis.get(nome_coluna, 0) + 1

        for n_linha, linha in enumerate(tabela.linhas):
            id_cru = linha[pos_id] if pos_id is not None else None
            nome_cru = linha[pos_nome] if pos_nome is not None else None
            if eh_linha_de_total(id_cru, nome_cru):
                ignoradas_total += 1
                continue
            if eh_vazio(id_cru) and eh_vazio(nome_cru):
                sem_chave += 1
                continue
            existe_arquivo_contas = any(t == "contas" for t in cfg.arquivos.values())
            total_antes = len(cofre.contas)
            codigo = cofre.codigo_conta(id_cru, nome_cru)
            if tipo == "eventos" and existe_arquivo_contas and codigo not in contas:
                sem_conta += 1
                if len(cofre.contas) > total_antes:  # não guarda conta que só existe no evento
                    registro = cofre.contas.pop()
                    cofre.por_id.pop(registro["chave_id"], None)
                    cofre.por_nome.pop(registro["chave_nome"], None)
                continue
            conta = contas.setdefault(codigo, Conta(codigo=codigo))

            if tipo == "eventos":
                data = conv_data_evento(linha[pos_data_evento]) if pos_data_evento is not None else None
                if data is None:
                    if pos_data_evento is not None and not eh_vazio(linha[pos_data_evento]):
                        marcar_ilegivel(pos_data_evento)
                    continue
                conta.eventos.setdefault(padrao, []).append(data)
                if "usuario_evento" in colunas_campo and not eh_vazio(linha[colunas_campo["usuario_evento"][0]]):
                    conta.quem_registrou.setdefault(padrao, []).append((data, normalizar(linha[colunas_campo["usuario_evento"][0]])))
                if "tema_evento" in colunas_campo and not eh_vazio(linha[colunas_campo["tema_evento"][0]]):
                    conta.temas_evento.setdefault(padrao, []).append((data, str(linha[colunas_campo["tema_evento"][0]]).strip()))
                continue

            novos_campos = {}
            for campo, (pos, conv) in colunas_campo.items():
                if campo in ("conta_id", "conta_nome"):
                    continue
                valor = conv(linha[pos])
                if valor is None and not eh_vazio(linha[pos]) and CAMPOS[campo][0] in ("numero", "data"):
                    marcar_ilegivel(pos)
                if valor is not None:
                    novos_campos[campo] = valor
            novos_ind, novos_ant = {}, {}
            for ind, pos, conv, pos_ant, conv_ant in colunas_ind:
                valor = conv(linha[pos])
                if valor is None and not eh_vazio(linha[pos]) and ind.medida in ("contagem", "ultima-data"):
                    marcar_ilegivel(pos)
                if valor is not None:
                    novos_ind[ind.id] = valor
                if pos_ant is not None:
                    anterior = conv_ant(linha[pos_ant])
                    if anterior is not None:
                        novos_ant[ind.id] = anterior

            assinatura = (tuple(sorted((k, str(v)) for k, v in novos_campos.items())), tuple(sorted((k, str(v)) for k, v in novos_ind.items())))
            if codigo in vistos:
                if vistos[codigo] == assinatura:
                    iguais += 1
                    continue
                conflitos.append(codigo)
                duplicatas.append([codigo, cofre.nome_conta(codigo), caminho.name, n_linha + 1])
            vistos[codigo] = assinatura
            conta.campos.update(novos_campos)
            conta.brutos.update(novos_ind)
            conta.anteriores.update(novos_ant)

        if ignoradas_total:
            r.avisos.append(f"'{caminho.name}': {plural(ignoradas_total, 'linha de total ignorada', 'linhas de total ignoradas')}.")
        if sem_chave:
            r.avisos.append(f"'{caminho.name}': {plural(sem_chave, 'linha sem conta ignorada', 'linhas sem conta ignoradas')}.")
        if sem_conta:
            r.avisos.append(f"'{caminho.name}': {plural(sem_conta, 'linha de evento de conta que não está', 'linhas de evento de contas que não estão')} no arquivo de contas.")
        if iguais:
            r.avisos.append(f"'{caminho.name}': {plural(iguais, 'linha repetida idêntica removida', 'linhas repetidas idênticas removidas')}.")
        if conflitos:
            r.avisos.append(
                f"'{caminho.name}': {plural(len(conflitos), 'conta repetida', 'contas repetidas')} com dados diferentes ({', '.join(sorted(set(conflitos)))}). "
                "Usei a última linha de cada campo. A lista está em 4-dados/.privado/duplicatas.csv."
            )
        if ilegiveis:
            detalhe = ", ".join(f"{coluna}: {n}" for coluna, n in sorted(ilegiveis.items()))
            r.avisos.append(f"'{caminho.name}': não deu para ler {plural(sum(ilegiveis.values()), 'valor', 'valores')}, que ficaram vazios ({detalhe}).")
    if duplicatas:
        escrever_csv(pasta / "4-dados" / ".privado" / "duplicatas.csv", ["codigo", "nome", "arquivo", "linha"], duplicatas)
    return contas


# ---------------------------------------------------------------- subnotas


def direcao_na_etapa(ind: Indicador, chave_etapa: str | None) -> str:
    if chave_etapa and chave_etapa in ind.direcao_etapas:
        return ind.direcao_etapas[chave_etapa]
    return ind.direcao


def _nota_quantidade(valor: float, esperado: float, direcao_base: str, direcao: str) -> float:
    if direcao_base == "ruim":
        if direcao == "bom":  # nesta etapa da jornada, subir não é problema
            return 100.0
        if esperado <= 0:
            return 100.0 if valor <= 0 else 0.0
        if valor <= esperado:
            return 100.0
        return max(0.0, 100.0 - 100.0 * (valor - esperado) / (2 * esperado))
    if direcao == "ruim":
        return _nota_quantidade(valor, esperado, "ruim", "ruim")
    if esperado <= 0:
        return 100.0
    return min(100.0, 100.0 * valor / esperado)


def _nota_dias(dias: float, limite: float) -> float:
    if limite <= 0:
        return 100.0 if dias <= 0 else 0.0
    if dias <= limite:
        return 100.0
    if dias >= 3 * limite:
        return 0.0
    return 100.0 * (3 * limite - dias) / (2 * limite)


def _nota_categoria(ind: Indicador, valor, rotulos=None) -> float | None:
    """Vale o combinado no checklist; depois, o que a pessoa ligou em rotulos.csv; por último, o óbvio."""
    chave = normalizar(valor)
    campo = f"indicador:{ind.id}"
    if rotulos is not None:
        significado = rotulos.significa(campo, valor)
    else:
        significado = ""
    if chave in ind.valores:
        if rotulos is not None:
            rotulos.definir(campo, valor, ind.valores[chave])
        return ind.valores[chave]
    numero = parse_numero(significado) if significado else None
    if numero is not None:
        return numero
    if ind.valores:
        return None
    palavras = set(chave.split())
    nota = None
    if chave in ("em dia", "pago", "ok", "adimplente", "sim", "regular", "verde") or palavras & {"adimplente", "pago", "paga"}:
        nota = 100.0
    elif chave in ("nao", "inadimplente", "vencido", "pendente", "vermelho") or palavras & {"atrasado", "atrasada", "atraso", "vencido", "inadimplente"}:
        nota = 0.0
    if nota is not None and rotulos is not None:
        rotulos.definir(campo, valor, nota)
    return nota


def intervalo_da_conta(datas: list) -> float | None:
    unicas = sorted(set(datas))
    if len(unicas) < 3:
        return None
    return float(statistics.median((b - a).days for a, b in zip(unicas, unicas[1:])))


def _eh_arquivo_de_eventos(ind: Indicador, cfg: Config) -> bool:
    for padrao, tipo in cfg.arquivos.items():
        if tipo == "eventos" and padrao.casefold() == ind.arquivo.casefold():
            return True
    return False


def medir_indicador(conta: Conta, ind: Indicador, cfg: Config, ref: dt.date, chave_etapa, arquivos_ok: set, rotulos=None):
    """Devolve (medição, antes, subnota, limite_usado). Vazio quando não há dado."""
    direcao = direcao_na_etapa(ind, chave_etapa)
    if not ind.arquivo or ind.arquivo.casefold() not in arquivos_ok:
        return None, None, None, None

    if ind.medida == "eventos":
        datas = conta.eventos.get(ind.arquivo) or next((v for k, v in conta.eventos.items() if k.casefold() == ind.arquivo.casefold()), [])
        atual = sum(1 for d in datas if ref - dt.timedelta(days=ind.janela) < d <= ref)
        antes = sum(1 for d in datas if ref - dt.timedelta(days=2 * ind.janela) < d <= ref - dt.timedelta(days=ind.janela))
        if ind.esperado is None:
            return float(atual), float(antes), None, None
        return float(atual), float(antes), arredondar(_nota_quantidade(atual, ind.esperado, ind.direcao, direcao), 1), ind.esperado

    if ind.medida == "ultima-data":
        limite = ind.esperado
        if _eh_arquivo_de_eventos(ind, cfg):
            datas = conta.eventos.get(ind.arquivo) or next((v for k, v in conta.eventos.items() if k.casefold() == ind.arquivo.casefold()), [])
            passadas = [d for d in datas if d <= ref]
            if not passadas:
                return None, None, None, None
            ultima = max(passadas)
            if ind.padrao_da_conta:
                limite = intervalo_da_conta(passadas)
        else:
            ultima = conta.brutos.get(ind.id)
            if ultima is None:
                return None, None, None, None
        dias = float((ref - ultima).days)
        if limite is None:
            return dias, None, None, None
        return dias, None, arredondar(_nota_dias(dias, limite), 1), limite

    valor = conta.brutos.get(ind.id)
    if valor is None:
        return None, None, None, None
    if ind.medida == "categoria":
        return valor, None, _nota_categoria(ind, valor, rotulos), None
    antes = conta.anteriores.get(ind.id)
    if ind.esperado is None:
        return valor, antes, None, None
    return valor, antes, arredondar(_nota_quantidade(valor, ind.esperado, ind.direcao, direcao), 1), ind.esperado


def calcular_nota(subnotas: dict, indicadores: list, cobertura_minima: float):
    total = sum(i.peso for i in indicadores)
    medidos = [(i.peso, subnotas[i.id]) for i in indicadores if subnotas.get(i.id) is not None]
    peso_medido = sum(p for p, _ in medidos)
    cobertura = peso_medido / total if total else 0.0
    if not medidos or cobertura < cobertura_minima:
        return None, cobertura
    return arredondar(sum(p * n for p, n in medidos) / peso_medido), cobertura


# ---------------------------------------------------------------- rodada anterior


def rodadas_anteriores(pasta: Path, data: dt.date) -> list:
    base = pasta / "4-dados" / "rodadas"
    saida = []
    if not base.exists():
        return saida
    for d in sorted(base.iterdir()):
        try:
            quando = dt.date.fromisoformat(d.name)
        except ValueError:
            continue
        if quando < data and (d / "valores.csv").exists():
            saida.append((quando, d))
    return saida


def ler_valores(pasta_rodada: Path) -> dict:
    caminho = pasta_rodada / "valores.csv"
    with caminho.open(encoding="utf-8-sig", newline="") as f:
        return {linha["codigo"]: linha for linha in csv.DictReader(f, delimiter=";")}


def ler_formula_anterior(pasta_rodada: Path) -> str:
    import json

    caminho = pasta_rodada / "resumo.json"
    if not caminho.exists():
        return ""
    try:
        return json.loads(caminho.read_text(encoding="utf-8")).get("formula", {}).get("versao", "")
    except ValueError:
        return ""


def versao_da_formula(cfg: Config) -> str:
    base = [(i.id, i.medida, i.esperado_txt, i.peso) for i in cfg.indicadores]
    return hashlib.sha1(repr(base).encode("utf-8")).hexdigest()[:8]


# ---------------------------------------------------------------- a rodada


def _status_da_conta(conta: Conta, r: Resultado) -> None:
    significado = r.rotulos.significa("status", conta.campos.get("status"))
    cancelamento = conta.campos.get("data_cancelamento")
    if cancelamento is not None:
        if cancelamento <= r.data:
            conta.status = "cancelada"
        else:
            conta.cancelamento_agendado = True
    if significado == "cancelada" and not conta.cancelamento_agendado:
        conta.status = "cancelada"


def tipo_de_contrato(texto) -> str | None:
    """No anual, a renovação é uma decisão com data. No mensal, a insatisfação acumula até cancelar."""
    if eh_vazio(texto):
        return None
    chave = normalizar(texto)
    palavras = set(chave.split())
    if "anual" in chave or palavras & {"ano", "anos"} or chave in ("12", "12 meses", "24 meses", "36 meses"):
        return "anual"
    if "mensal" in chave or chave in ("mes", "1 mes", "30 dias", "recorrente mensal"):
        return "mensal"
    return "outro"


def _etapa_da_conta(conta: Conta, r: Resultado, ref: dt.date) -> None:
    rotulo = conta.campos.get("etapa")
    if rotulo is None:
        return
    conta.etapa_rotulo = rotulo
    nome = r.rotulos.significa("etapa", rotulo)
    etapa = r.cfg.etapa(normalizar(nome)) if nome else None
    if etapa is None:
        conta.situacao = "etapa sem ligação"
        return
    conta.etapa = etapa.nome
    conta.prazo = etapa.prazo
    entrada = conta.campos.get("data_entrada_etapa")
    if entrada is not None:
        conta.dias_etapa = float((ref - entrada).days)
    elif conta.campos.get("dias_na_etapa") is not None:
        conta.dias_etapa = conta.campos["dias_na_etapa"]
    if conta.prazo is None:
        conta.situacao = "sem prazo"
    elif conta.dias_etapa is None:
        conta.situacao = "sem data"
    elif conta.dias_etapa > conta.prazo:
        conta.situacao = "empacado"
    else:
        conta.situacao = "no prazo"
    conta.motivo = r.rotulos.significa("motivo_parada", conta.campos.get("motivo_parada"))


def _comparar_padrao(conta: Conta, ind: Indicador, r: Resultado, atual, antes, chave_etapa) -> None:
    variacao_min = r.cfg.regras["variacao para alerta"] / 100
    minimo = r.cfg.regras["minimo absoluto"]
    if ind.medida not in ("contagem", "eventos") or atual is None or antes is None:
        return
    r.comparacoes += 1
    diferenca = atual - antes
    if abs(diferenca) < minimo:
        return
    if antes > 0 and abs(diferenca) / antes < variacao_min:
        return
    direcao = direcao_na_etapa(ind, chave_etapa)
    subiu = diferenca > 0
    ruim = (subiu and direcao == "ruim") or (not subiu and direcao == "bom")
    alerta = {
        "conta": conta.codigo,
        "indicador": ind.id,
        "rotina": ind.rotina,
        "antes": antes,
        "agora": atual,
        "variacao_pct": arredondar(100 * diferenca / antes) if antes > 0 else None,
        "leitura": "alerta" if ruim else "bom sinal",
        "nota": conta.nota,
        "criticidade": ind.criticidade,
    }
    (r.alertas_ruins if ruim else r.alertas_bons).append(alerta)
    if ruim:
        conta.alertas.append(alerta)


def _comparar_intervalo(conta: Conta, ind: Indicador, r: Resultado, dias, limite) -> None:
    """Na recompra, o padrão é o intervalo da própria conta."""
    if ind.medida != "ultima-data" or not ind.padrao_da_conta or dias is None or limite is None:
        return
    r.comparacoes += 1
    if dias < limite * (1 + r.cfg.regras["variacao para alerta"] / 100):
        return
    alerta = {
        "conta": conta.codigo,
        "indicador": ind.id,
        "rotina": ind.rotina,
        "antes": limite,
        "agora": dias,
        "variacao_pct": arredondar(100 * (dias - limite) / limite) if limite else None,
        "leitura": "alerta",
        "nota": conta.nota,
        "criticidade": ind.criticidade,
        "tipo": "intervalo",
    }
    r.alertas_ruins.append(alerta)
    conta.alertas.append(alerta)


def _sinais(conta: Conta, r: Resultado, nota_anterior, formula_mudou: bool) -> None:
    sinais = conta.sinais
    regras = r.cfg.regras
    if conta.faixa == "possivel_churn":
        sinais.append(("nota_vermelha", f"Nota {conta.nota} ({NOME_FAIXAS[conta.faixa]})"))
    elif conta.faixa == "pode_melhorar":
        sinais.append(("nota_amarela", f"Nota {conta.nota} ({NOME_FAIXAS[conta.faixa]})"))
    if conta.cancelamento_agendado:
        sinais.append(("cancelamento_agendado", "Cancelamento já agendado"))
    if conta.situacao == "empacado":
        motivo = f"motivo {conta.motivo}" if conta.motivo else "motivo não informado"
        sinais.append(("empacado", f"Empacada há {arredondar(conta.dias_etapa)} dias em {conta.etapa} (prazo {arredondar(conta.prazo)}), {motivo}"))
    for alerta in conta.alertas:
        if alerta.get("tipo") == "intervalo":
            texto = f"{alerta['rotina']}: {arredondar(alerta['agora'])} dias, o normal desta conta é {arredondar(alerta['antes'])}"
        elif alerta["variacao_pct"] is None:
            texto = f"{alerta['rotina']}: de {_num(alerta['antes'])} para {_num(alerta['agora'])}"
        else:
            verbo = "subiu" if alerta["agora"] > alerta["antes"] else "caiu"
            texto = f"{alerta['rotina']} {verbo} {abs(alerta['variacao_pct'])}% (de {_num(alerta['antes'])} para {_num(alerta['agora'])})"
        if conta.faixa == "saudavel":
            texto += ", com nota boa"
        sinais.append(("padrao_ruim", texto))
    for ind in r.cfg.indicadores:
        if ind.bloco == "financeiro" and conta.subnotas.get(ind.id) is not None and conta.subnotas[ind.id] <= 30:
            sinais.append(("financeiro", f"Financeiro com problema: {ind.rotina} com nota {_num(conta.subnotas[ind.id])}"))
    if nota_anterior is not None and conta.nota is not None and not formula_mudou and nota_anterior - conta.nota >= regras["queda de nota"]:
        sinais.append(("queda_de_nota", f"Nota caiu de {arredondar(nota_anterior)} para {conta.nota}"))
    contato = conta.campos.get("ultimo_contato")
    if contato is not None and (r.data - contato).days > regras["sem contato"]:
        sinais.append(("sem_contato", f"Sem contato há {(r.data - contato).days} dias"))

    renovacao = conta.campos.get("renovacao") if conta.contrato != "mensal" else None
    tem_risco = any(s[0] in ("nota_vermelha", "nota_amarela", "empacado", "padrao_ruim", "financeiro", "cancelamento_agendado", "queda_de_nota") for s in sinais)
    if renovacao is not None:
        dias = (renovacao - r.data).days
        if 0 <= dias <= regras["renovacao proxima"]:
            texto = "Renova hoje" if dias == 0 else ("Renova amanhã" if dias == 1 else f"Renova em {dias} dias")
            sinais.append(("renovacao_com_risco" if tem_risco else "renovacao_sozinha", texto))
            r.renovacoes.append({"conta": conta.codigo, "dias": dias, "receita": conta.receita, "nota": conta.nota, "com_risco": tem_risco})
        elif dias < 0:
            sinais.append(("renovacao_vencida", f"Renovação vencida há {-dias} dias"))
    conta.pontos = sum(PONTOS[s[0]] for s in sinais)


def _num(valor) -> str:
    if valor is None:
        return ""
    valor = float(valor)
    return str(int(valor)) if valor.is_integer() else f"{valor:.1f}".replace(".", ",")


def _matriz(conta: Conta, mediana) -> str:
    if conta.nota is None or mediana is None or conta.receita is None:
        return ""
    receita_alta = conta.receita >= mediana
    if conta.nota >= FAIXA_VERDE:
        return "crescer" if receita_alta else "manter"
    return "salvar" if receita_alta else "observar"


def quem_age(conta: Conta) -> str:
    if conta.situacao == "empacado":
        if conta.motivo == "nosso":
            return "nós (destravar internamente)"
        if conta.motivo == "do cliente":
            return "cliente (CS cobra e ajuda)"
        return "a definir (falta o motivo)"
    return "CS"


def _montar_prioridades(r: Resultado) -> None:
    receitas = [c.receita for c in r.ativas if c.receita is not None]
    mediana = statistics.median(receitas) if receitas else None
    lista = []
    for conta in r.ativas:
        if conta.pontos <= 0:
            continue
        peso = conta.pontos * (conta.receita if conta.receita else 1)
        lista.append(
            {
                "conta": conta.codigo,
                "responsavel": r.cofre.codigo_pessoa(conta.campos["responsavel"]) if conta.campos.get("responsavel") else None,
                "pontos": conta.pontos,
                "peso": peso,
                "receita": conta.receita,
                "nota": conta.nota,
                "faixa": conta.faixa,
                "matriz": _matriz(conta, mediana),
                "por_que": [s[1] for s in conta.sinais],
                "sinais": [s[0] for s in conta.sinais],
                "quem_age": quem_age(conta),
                "renovacao": conta.campos.get("renovacao").isoformat() if conta.campos.get("renovacao") else None,
                "proximo_contato": conta.campos.get("data_proximo_contato").isoformat() if conta.campos.get("data_proximo_contato") else None,
                "tem_proximo_passo": bool(conta.campos.get("proximo_passo")),
            }
        )
    lista.sort(key=lambda x: (-x["peso"], x["conta"]))
    r.prioridades = lista


def _contas_chave(r: Resultado) -> None:
    com_receita = sorted((c for c in r.ativas if c.receita and c.receita > 0), key=lambda c: -c.receita)
    total = sum(c.receita for c in com_receita)
    if not com_receita:
        r.contas_chave = {"existe": None, "motivo": "sem receita nas contas"}
        return
    acumulado, grupo = 0.0, []
    for conta in com_receita:
        grupo.append(conta)
        acumulado += conta.receita
        if acumulado >= 0.8 * total:
            break
    limite = max(1, int(round(0.2 * len(com_receita))))
    existe = len(grupo) <= limite and len(grupo) < len(com_receita)
    r.contas_chave = {
        "existe": existe,
        "quantas": len(grupo),
        "de_um_total_de": len(com_receita),
        "sem_receita": len(r.ativas) - len(com_receita),
        "pct_receita": arredondar(100 * acumulado / total),
    }
    if existe:
        r.contas_chave["contas"] = [c.codigo for c in grupo]
    r.maiores = [{"conta": c.codigo, "receita": c.receita} for c in com_receita[:5]]


def _teste_conta_perdida(pasta: Path, r: Resultado) -> None:
    if not r.canceladas:
        r.perdidas = {}
        return
    cfg = r.cfg
    anteriores = rodadas_anteriores(pasta, r.data)
    minimo = cfg.regras["cobertura minima"] / 100
    detalhes = []
    for conta in r.canceladas:
        cancelou = conta.campos.get("data_cancelamento")
        item = {"conta": conta.codigo, "cancelou_em": cancelou.isoformat() if cancelou else None, "receita": conta.receita}
        if cancelou is None:
            detalhes.append({**item, "avisaria": "não dá para saber", "avisou_por": None, "por_que": "Cancelada sem data de cancelamento", "nota": None})
            continue
        fonte_rodada = None
        for quando, pasta_rodada in reversed(anteriores):
            if quando <= cancelou:
                valores = ler_valores(pasta_rodada).get(conta.codigo)
                if valores:
                    fonte_rodada = (quando, valores)
                    break
        if fonte_rodada:
            quando, valores = fonte_rodada
            nota = float(valores["nota"]) if valores.get("nota") else None
            parada = valores.get("situacao") == "empacado"
            avisos_salvos = valores.get("alertas") or ""
            pela_nota = nota is not None and nota < FAIXA_VERDE
            por_alerta = parada or bool(avisos_salvos)
            detalhes.append(
                {
                    **item,
                    "avisaria": "sim" if pela_nota or por_alerta else ("não" if nota is not None else "não dá para saber"),
                    "avisou_por": "nota" if pela_nota else ("alerta" if por_alerta else None),
                    "por_que": f"Dado real da rodada de {quando.isoformat()}",
                    "nota": arredondar(nota) if nota is not None else None,
                }
            )
            continue
        antes = cancelou - dt.timedelta(days=30)
        subnotas = {}
        for ind in cfg.indicadores:
            subnotas[ind.id] = _subnota_retroativa(conta, ind, cfg, antes, cancelou, r.data)
        nota, cobertura = calcular_nota(subnotas, cfg.indicadores, minimo)
        parada = False
        entrada = conta.campos.get("data_entrada_etapa")
        rotulo = conta.campos.get("etapa")
        if entrada is not None and rotulo is not None:
            nome = r.rotulos.consultar("etapa", rotulo)
            etapa = cfg.etapa(normalizar(nome)) if nome else None
            if etapa and etapa.prazo is not None and (antes - entrada).days > etapa.prazo:
                parada = True
        avisou_por = None
        if nota is not None and nota < FAIXA_VERDE:
            avisaria, por_que, avisou_por = "sim", f"Nota {nota} 30 dias antes de cancelar", "nota"
        elif parada:
            complemento = f", com nota {nota}" if nota is not None else ""
            avisaria, por_que, avisou_por = "sim", f"Estava empacada 30 dias antes de cancelar{complemento}", "alerta"
        elif nota is None:
            avisaria, por_que = "não dá para saber", "Não há dado de antes do cancelamento"
        else:
            avisaria, por_que = "não", f"Nota {nota} 30 dias antes de cancelar: a nota não viu"
        detalhes.append({**item, "avisaria": avisaria, "avisou_por": avisou_por, "por_que": por_que, "nota": nota})
    contagem = {"sim": 0, "não": 0, "não dá para saber": 0}
    for d in detalhes:
        contagem[d["avisaria"]] += 1
    r.perdidas = {
        "detalhes": detalhes,
        "sim": contagem["sim"],
        "sim_pela_nota": sum(1 for d in detalhes if d["avisou_por"] == "nota"),
        "sim_por_alerta": sum(1 for d in detalhes if d["avisou_por"] == "alerta"),
        "nao": contagem["não"],
        "sem_dado": contagem["não dá para saber"],
        "total": len(detalhes),
    }


def _avisar_se_a_regua_esta_frouxa(r: Resultado) -> None:
    """Dado que não separa ninguém também é problema, e ausência de sinal não prova que está tudo bem."""
    com_nota = [c for c in r.ativas if c.nota is not None]
    if len(com_nota) < 5 or not r.perdidas.get("nao"):
        return
    if sum(1 for c in com_nota if c.faixa == "saudavel") / len(com_nota) >= 0.9:
        r.avisos.append(
            "Quase todas as contas estão saudáveis, e mesmo assim houve conta que saiu sem a nota avisar. "
            "A régua pode estar frouxa: reveja com a pessoa as frequências esperadas e as rotinas."
        )


def _subnota_retroativa(conta: Conta, ind: Indicador, cfg: Config, quando: dt.date, cancelou: dt.date, hoje: dt.date):
    """Mede como a conta estava antes de sair, sem contar o que aconteceu depois."""
    if ind.medida == "eventos" or (ind.medida == "ultima-data" and _eh_arquivo_de_eventos(ind, cfg)):
        arquivos = {ind.arquivo.casefold()}
        _, _, subnota, _ = medir_indicador(conta, ind, cfg, quando, None, arquivos)
        return subnota
    if ind.medida == "ultima-data":
        ultima = conta.brutos.get(ind.id)
        if ultima is None or ind.esperado is None:
            return None
        dias = max(0, (quando - ultima).days)
        return arredondar(_nota_dias(dias, ind.esperado), 1)
    if ind.medida == "contagem":
        anterior = conta.anteriores.get(ind.id)
        if anterior is None or ind.esperado is None or (hoje - cancelou).days > 30:
            return None
        return arredondar(_nota_quantidade(anterior, ind.esperado, ind.direcao, ind.direcao), 1)
    return None


def rodar(pasta: Path, data: dt.date, entrada: Path, cfg: Config, modo: str) -> Resultado:
    cofre = Cofre(pasta)
    rotulos = Rotulos(pasta, cfg)
    r = Resultado(data=data, modo=modo, cfg=cfg, cofre=cofre, rotulos=rotulos)
    contas = carregar_dados(pasta, cfg, entrada, cofre, r)
    r.contas = sorted(contas.values(), key=lambda c: c.codigo)
    for conta in r.contas:
        _status_da_conta(conta, r)
        conta.contrato = tipo_de_contrato(conta.campos.get("contrato")) or tipo_de_contrato(cfg.regras["contrato padrao"])
    r.ativas =[c for c in r.contas if c.status == "ativa"]
    r.canceladas = [c for c in r.contas if c.status == "cancelada"]

    anteriores = rodadas_anteriores(pasta, data)
    valores_anteriores = {}
    formula_anterior = ""
    if anteriores:
        r.rodada_anterior = anteriores[-1][0]
        valores_anteriores = ler_valores(anteriores[-1][1])
        formula_anterior = ler_formula_anterior(anteriores[-1][1])
    versao = versao_da_formula(cfg)
    formula_mudou = bool(formula_anterior) and formula_anterior != versao
    r.formula = {"versao": versao, "mudou_nesta_rodada": formula_mudou, "mudou_em": data.isoformat() if formula_mudou else None}
    if formula_mudou:
        r.avisos.append("Os pesos ou as rotinas mudaram nesta rodada: a nota não é comparável com a da rodada anterior.")
    r.avisos.extend(cfg.pendencias)

    arquivos_ok = {a.casefold() for a in cfg.arquivos}
    # o indicador só conta como medido se o arquivo veio nesta rodada
    arquivos_presentes = set()
    for padrao in cfg.arquivos:
        if _achar_arquivo(entrada, padrao) is not None:
            arquivos_presentes.add(padrao.casefold())
    arquivos_ok &= arquivos_presentes

    minimo = cfg.regras["cobertura minima"] / 100
    for ind in cfg.indicadores:
        r.estado_indicadores[ind.id] = {"medidos": 0, "total": 0}
    for conta in r.contas:
        ativa = conta.status == "ativa"
        _etapa_da_conta(conta, r, data)
        chave = normalizar(conta.etapa) if conta.etapa else None
        for ind in cfg.indicadores:
            medicao, antes, subnota, limite = medir_indicador(conta, ind, cfg, data, chave, arquivos_ok, rotulos)
            if antes is None and ind.medida == "contagem" and not ind.coluna_anterior:
                salvo = valores_anteriores.get(conta.codigo, {}).get(f"ind:{ind.id}")
                antes = float(salvo) if salvo else None
            conta.medicoes[ind.id] = medicao
            conta.antes[ind.id] = antes
            conta.subnotas[ind.id] = subnota
            conta.limites[ind.id] = limite
            if ativa:
                r.estado_indicadores[ind.id]["total"] += 1
                if subnota is not None:
                    r.estado_indicadores[ind.id]["medidos"] += 1
        conta.nota, conta.cobertura = calcular_nota(conta.subnotas, cfg.indicadores, minimo)
        conta.faixa = faixa_da_nota(conta.nota)
        conta.grau = grau_de_confianca(conta.cobertura)
        if ativa:
            for ind in cfg.indicadores:
                _comparar_padrao(conta, ind, r, conta.medicoes[ind.id], conta.antes[ind.id], chave)
                _comparar_intervalo(conta, ind, r, conta.medicoes[ind.id], conta.limites.get(ind.id))

    for conta in r.ativas:
        salvo = valores_anteriores.get(conta.codigo, {}).get("nota")
        _sinais(conta, r, float(salvo) if salvo else None, formula_mudou)
    ordem_crit = {"alta": 0, "media": 1, "baixa": 2}
    receita_de = {c.codigo: (c.receita or 0) for c in r.contas}
    for lista in (r.alertas_ruins, r.alertas_bons):
        lista.sort(key=lambda a: (ordem_crit[a["criticidade"]], -receita_de.get(a["conta"], 0), a["conta"]))
    r.empacadas = sorted([c for c in r.ativas if c.situacao == "empacado"], key=lambda c: -(c.dias_etapa - c.prazo))
    r.renovacoes.sort(key=lambda x: x["dias"])
    _montar_prioridades(r)
    _contas_chave(r)
    _teste_conta_perdida(pasta, r)
    _avisar_se_a_regua_esta_frouxa(r)

    from .painel import calcular_metas, calcular_painel
    from .faltas import listar_faltas
    from .melhoria import dados_de_melhoria
    from .oportunidades import achar_oportunidades
    from .prever import prever

    r.painel = calcular_painel(r)
    r.metas = calcular_metas(r)
    r.previsoes = prever(pasta, r)
    r.oportunidades = achar_oportunidades(r)
    r.melhoria = dados_de_melhoria(r)
    r.faltas = listar_faltas(r)
    pendentes = rotulos.pendentes()
    for campo, quantos in pendentes.items():
        r.avisos.append(f"{plural(quantos, 'rótulo', 'rótulos')} de '{campo}' sem ligação. Complete em 4-dados/.privado/rotulos.csv.")
    return r
