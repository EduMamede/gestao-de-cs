"""Oportunidades de upgrade: o que a conta não usa, quem está sobrecarregado e o que a empresa definiu.

A rodada só aponta onde olhar. Se a área já está no plano do cliente, é adoção, não upgrade: quem confirma é
a pessoa. Valor, preço e proposta nunca saem daqui. O mapa em 3-clientes/oportunidades.md é da pessoa: o script
só acrescenta linhas novas.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from .medir import arredondar

SINAIS_DE_INSATISFACAO = ("nota_vermelha", "nota_amarela", "cancelamento_agendado", "empacado", "padrao_ruim", "financeiro", "queda_de_nota", "sem_contato")
CONCENTRACAO_PADRAO_PCT = 70.0  # ponto de partida, não benchmark: mude na coluna limite
MIN_CONTAS_PARA_COMPARAR = 5
MIN_REGISTROS_PARA_CONCENTRACAO = 10
ARQUIVO_DO_MAPA = ("3-clientes", "oportunidades.md")
CABECALHO_DO_MAPA = "| conta | oportunidade | o que a rodada mostrou | achada em | situação | valor estimado | próximo passo |"


def _texto_numero(valor) -> str:
    valor = float(valor)
    return str(int(valor)) if valor.is_integer() else f"{valor:.1f}".replace(".", ",")


def _numero_da_rotina(conta, id_: str):
    valor = conta.medicoes.get(id_)
    return float(valor) if isinstance(valor, (int, float)) else None


def _concentracao(conta, ind, ref: dt.date):
    """Quanto do período o usuário que mais registra fez sozinho. Devolve (pct, registros, usuários)."""
    registros = next((v for k, v in conta.quem_registrou.items() if k.casefold() == ind.arquivo.casefold()), [])
    inicio = ref - dt.timedelta(days=ind.janela)
    contagem: dict = {}
    for data, usuario in registros:
        if inicio < data <= ref:
            contagem[usuario] = contagem.get(usuario, 0) + 1
    total = sum(contagem.values())
    if total < MIN_REGISTROS_PARA_CONCENTRACAO:
        return None
    return 100 * max(contagem.values()) / total, total, len(contagem)


def _avaliar(regra, ind, conta, ref: dt.date):
    """Devolve o que a rodada mostrou, ou None quando a regra não se aplica ou não há dado."""
    if regra.tipo == "um_usuario":
        achado = _concentracao(conta, ind, ref)
        limite = regra.limite if regra.limite is not None else CONCENTRACAO_PADRAO_PCT
        if achado is None or achado[0] < limite:
            return None
        pct, total, usuarios = achado
        quem = "um usuário só fez" if usuarios == 1 else f"um dos {usuarios} usuários fez"
        return f"{ind.rotina}: {quem} {arredondar(pct)}% dos {total} registros"
    agora = _numero_da_rotina(conta, ind.id)
    if agora is None:
        return None
    if regra.tipo == "sem_uso":
        return f"{ind.rotina}: sem uso no período" if agora == 0 else None
    if regra.tipo == "acima_de":
        return f"{ind.rotina}: {_texto_numero(agora)}, acima de {_texto_numero(regra.limite)}" if agora >= regra.limite else None
    if regra.tipo == "abaixo_de":
        return f"{ind.rotina}: {_texto_numero(agora)}, abaixo de {_texto_numero(regra.limite)}" if agora <= regra.limite else None
    usuarios = conta.campos.get("usuarios")
    if not usuarios or usuarios <= 0:
        return None
    por_usuario = agora / usuarios
    if por_usuario < regra.limite:
        return None
    quantos = "1 usuário" if usuarios == 1 else f"{_texto_numero(usuarios)} usuários"
    return f"{ind.rotina}: {_texto_numero(arredondar(por_usuario, 1))} por usuário, com {quantos}. O limite é {_texto_numero(regra.limite)}"


def _sem_uso_automatico(r, por_id: dict) -> list:
    """Rotina que a conta não usa e a maioria das outras usa. Não precisa de regra: a própria carteira é a comparação."""
    achados = []
    for ind in r.cfg.indicadores:
        if ind.bloco != "rotina" or ind.direcao != "bom" or ind.medida not in ("eventos", "contagem"):
            continue
        medidas = [(c, _numero_da_rotina(c, ind.id)) for c in r.ativas]
        medidas = [(c, v) for c, v in medidas if v is not None]
        usam = sum(1 for _, v in medidas if v > 0)
        if len(medidas) < MIN_CONTAS_PARA_COMPARAR or usam * 2 < len(medidas):
            continue
        for conta, valor in medidas:
            if valor == 0:
                achados.append((conta, f"{ind.rotina} sem uso", "sem_uso", ind.id, f"{ind.rotina}: sem uso, e {usam} de {len(medidas)} contas usam", ""))
    return achados


def achar_oportunidades(r) -> list:
    por_id = {i.id: i for i in r.cfg.indicadores}
    achados = _sem_uso_automatico(r, por_id)
    ja_vistos = {(a[0].codigo, a[3], a[2]) for a in achados}
    for regra in r.cfg.oportunidades:
        ind = por_id[regra.indicador]
        for conta in r.ativas:
            detalhe = _avaliar(regra, ind, conta, r.data)
            if detalhe is None:
                continue
            chave = (conta.codigo, regra.indicador, regra.tipo)
            if chave in ja_vistos:  # o nome e a oferta que a empresa escolheu valem mais que o automático
                achados = [a for a in achados if (a[0].codigo, a[3], a[2]) != chave]
            ja_vistos.add(chave)
            achados.append((conta, regra.nome, regra.tipo, regra.indicador, detalhe, regra.oferta))
    lista = []
    for conta, nome, tipo, id_, detalhe, oferta in achados:
        if conta.cancelamento_agendado:
            continue
        lista.append(
            {
                "conta": conta.codigo,
                "oportunidade": nome,
                "tipo": tipo,
                "indicador": id_,
                "detalhe": detalhe,
                "oferta": oferta,
                "receita": conta.receita,
                "nota": conta.nota,
                "com_insatisfacao": any(s[0] in SINAIS_DE_INSATISFACAO for s in conta.sinais),
            }
        )
    lista.sort(key=lambda o: (o["com_insatisfacao"], -(o["receita"] or 0), o["conta"], o["oportunidade"]))
    return lista


def resumo_das_oportunidades(lista: list, limite: int = 30) -> dict:
    contas = {o["conta"]: o["receita"] or 0 for o in lista}
    return {"total": len(lista), "contas": len(contas), "receita_das_contas": sum(contas.values()), "lista": lista[:limite]}


def _linhas_do_mapa(texto: str) -> list:
    return [[c.strip() for c in linha.strip().strip("|").split("|")] for linha in texto.splitlines() if re.match(r"^\|\s*CONTA-\d+", linha)]


def atualizar_mapa(pasta: Path, data: dt.date, lista: list) -> tuple:
    """Acrescenta o que é novo e não toca no resto: a situação, o valor e o próximo passo são da pessoa."""
    caminho = pasta.joinpath(*ARQUIVO_DO_MAPA)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if caminho.exists():
        texto = caminho.read_text(encoding="utf-8")
    else:
        texto = (
            "# Oportunidades mapeadas\n\n"
            "A rodada aponta onde olhar. Quem confirma é você: se a área já está no plano do cliente, é adoção, não upgrade.\n\n"
            "## O que fazer\n\n- Confirmar cada linha e atualizar a situação: mapeada, conversada, proposta, ganha, perdida ou descartada.\n\n"
            "## O que foi conversado\n\n- Nada ainda.\n\n"
            f"## As oportunidades\n\n{CABECALHO_DO_MAPA}\n| --- | --- | --- | --- | --- | --- | --- |\n"
        )
    existentes = _linhas_do_mapa(texto)
    conhecidas = {(l[0], l[1]) for l in existentes if len(l) > 1}
    novas = [o for o in lista if (o["conta"], o["oportunidade"]) not in conhecidas]
    if novas:
        linhas = texto.splitlines()
        posicao = max((i for i, l in enumerate(linhas) if l.lstrip().startswith("|")), default=len(linhas) - 1) + 1
        for deslocamento, o in enumerate(novas):
            detalhe = o["detalhe"].replace("|", "/")
            linhas.insert(posicao + deslocamento, f"| {o['conta']} | {o['oportunidade']} | {detalhe} | {data.isoformat()} | mapeada | {{{{ }}}} | {{{{ }}}} |")
        texto = "\n".join(linhas) + "\n"
    caminho.write_text(texto, encoding="utf-8")
    situacoes: dict = {}
    for linha in _linhas_do_mapa(texto):
        if len(linha) > 4:
            situacoes[linha[4]] = situacoes.get(linha[4], 0) + 1
    return caminho, len(novas), situacoes
