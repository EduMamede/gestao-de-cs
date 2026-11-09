#!/usr/bin/env python
"""Trava de privacidade: impede a IA de abrir os dados brutos no modo protegido.

Roda antes de cada ferramenta do Claude Code (hook PreToolUse). É uma trava contra engano,
não um cofre: um comando muito criativo poderia passar, e o README diz isso.
Só atua dentro de uma pasta de empresa em modo protegido.

Também dispensa a autorização quando um agente do plugin roda o próprio script, nos comandos
de LIBERADOS. O README diz isso. Todo o resto continua pedindo.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

MARCADOR = ".gestao-de-cs.json"
# Só o que fica na pasta da empresa e não grava por cima do que a pessoa escreveu. Fora da lista continua pedindo:
# criar-pasta e privacidade são decisão da pessoa, receber traz arquivo de fora, --refazer grava por cima.
LIBERADOS = {
    "colunas": {"--pasta", "--entrada"},
    "validar": {"--pasta"},
    "rotulos": {"--pasta"},
    "rodada": {"--pasta", "--data", "--entrada"},
    "prever": {"--pasta"},
    "carteira": {"--pasta"},
    "oportunidades": {"--pasta"},
    "cuidados": {"--pasta"},
    "plano": {"--pasta", "--conta", "--tipo", "--data"},
    "melhoria": {"--pasta"},
    "reuniao": {"--pasta", "--conta", "--tipo", "--data"},
    "apresentacao": {"--pasta", "--arquivo"},
    "semana": {"--pasta", "--data"},
    "conferir-numeros": {"--pasta", "--arquivo"},
    "restaurar-nomes": {"--pasta", "--arquivo"},
    "nova-ficha": {"--pasta", "--conta"},
}
# Texto entre aspas, ou palavra sem nada que o Bash ou o PowerShell interpretem.
# De U+2018 a U+201F: o PowerShell aceita aspas curvas como aspas.
PEDACO = re.compile(r"""[ \t]*("[^"$`\x00-\x1f‘-‟]*(?<!\\)"|'[^'\x00-\x1f‘-‟]*'|[\w./\\:+-]+)(?=[ \t]|\Z)""")
PROTEGIDOS = re.compile(
    r"4-dados[\\/]+entradas|4-dados[\\/]+\.privado|(?:^|[\s\"'\\/=])com-nomes(?:[\\/\s\"']|$)|health-score[^\"'\s]*\.xlsx",
    re.IGNORECASE,
)
EXTENSOES_BRUTAS = re.compile(r"\.(csv|tsv|xlsx|xlsm|xls)\b", re.IGNORECASE)
ENCADEAMENTO = re.compile(r"[;&|<>`]|\$\(")
MOTIVO = (
    "Modo protegido: este dado só é aberto pelos scripts da skill (cs.py). "
    "Use o resumo da rodada, ou peça para a pessoa abrir o arquivo. "
    "Para mudar o modo, a pessoa precisa decidir: cs.py privacidade."
)
MOTIVO_LIBERADO = "Script do plugin gestao-de-cs, pedido por um agente dele."


def _pasta_da_empresa(caminho: Path):
    atual = caminho
    for _ in range(40):
        if (atual / MARCADOR).exists():
            return atual
        if atual.parent == atual:
            return None
        atual = atual.parent
    return None


def _modo(pasta: Path) -> str:
    try:
        modo = json.loads((pasta / MARCADOR).read_text(encoding="utf-8")).get("modo_privacidade")
    except (OSError, ValueError):
        modo = None
    return "aberto" if modo == "aberto" else "protegido"


def _protegida(caminho_texto: str, cwd: Path):
    """Devolve a pasta de empresa protegida a que o caminho pertence, se houver."""
    caminho = Path(caminho_texto)
    if not caminho.is_absolute():
        caminho = cwd / caminho
    pasta = _pasta_da_empresa(caminho)
    if pasta is None:
        return None
    return pasta if _modo(pasta) == "protegido" else None


def _trecho_do_caminho(texto: str, inicio: int, fim: int) -> str:
    antes = texto[:inicio]
    corte = max(antes.rfind('"'), antes.rfind("'"))
    if corte >= 0:
        return texto[corte + 1 : fim]
    pedacos = antes.split()
    return (pedacos[-1] if pedacos and not antes.endswith(" ") else "") + texto[inicio:fim]


def _so_cs_py(comando: str) -> bool:
    comando = comando.strip().removeprefix("&").strip()  # o "&" inicial é o operador de chamada do PowerShell
    if ENCADEAMENTO.search(comando):
        return False
    return bool(re.match(r"[\"']?(?:[^\"'\s]*[\\/])?python[0-9.]*(?:\.exe)?[\"']?\s+(?:\"[^\"]*cs\.py\"|'[^']*cs\.py'|\S*cs\.py)\s", comando + " "))


def _bloqueia_comando(comando: str, cwd: Path) -> bool:
    if _so_cs_py(comando):
        return False
    for achado in PROTEGIDOS.finditer(comando):
        trecho = _trecho_do_caminho(comando, achado.start(), achado.end()).strip(" \"'")
        if _protegida(trecho, cwd) is not None:
            return True
        if _protegida(".", cwd) is not None:
            return True
    return _protegida(".", cwd) is not None and bool(EXTENSOES_BRUTAS.search(comando)) and "valores.csv" not in comando


def _bloqueia_caminho(ferramenta: str, entrada: dict, cwd: Path) -> bool:
    caminhos = [entrada.get(k) for k in ("file_path", "path", "notebook_path") if entrada.get(k)]
    for caminho in caminhos:
        norm = str(caminho)
        if PROTEGIDOS.search(norm) and _protegida(norm, cwd) is not None:
            return True
    if ferramenta in ("Read", "NotebookRead"):
        arquivo = str(entrada.get("file_path") or "")
        if EXTENSOES_BRUTAS.search(arquivo) and not arquivo.endswith("valores.csv") and _protegida(".", cwd) is not None:
            return True
    if ferramenta == "Grep":
        raiz = Path(str(entrada.get("path") or cwd))
        if not raiz.is_absolute():
            raiz = cwd / raiz
        pasta = _protegida(str(raiz), cwd)
        if pasta is not None and raiz.resolve() in (pasta.resolve(), (pasta / "4-dados").resolve()):
            return True
    if ferramenta == "Glob":
        padrao = str(entrada.get("pattern") or "")
        base = str(entrada.get("path") or cwd)
        if PROTEGIDOS.search(padrao) and _protegida(base, cwd) is not None:
            return True
    return False


def decidir(dados: dict) -> bool:
    """True quando a ferramenta deve ser bloqueada."""
    ferramenta = dados.get("tool_name") or ""
    entrada = dados.get("tool_input") or {}
    cwd = Path(dados.get("cwd") or ".")
    if ferramenta in ("Bash", "PowerShell"):
        return _bloqueia_comando(str(entrada.get("command") or ""), cwd)
    return _bloqueia_caminho(ferramenta, entrada, cwd)


def _pedacos(comando: str):
    """Separa o comando, ou devolve None se houver qualquer coisa que o shell possa interpretar."""
    comando = comando.strip()
    pedacos, posicao = [], 0
    while posicao < len(comando):
        achado = PEDACO.match(comando, posicao)
        if achado is None:
            return None
        pedaco = achado.group(1)
        pedacos.append(pedaco[1:-1] if pedaco[0] in "\"'" else pedaco)
        posicao = achado.end()
    return pedacos


def _e_o_cs_py(texto: str, cwd: Path) -> bool:
    if os.name == "nt":  # no Bash do Windows, /d/pasta é D:/pasta
        texto = re.sub(r"^/([A-Za-z])/", r"\1:/", texto)
    caminho = Path(texto) if Path(texto).is_absolute() else cwd / texto
    try:
        return os.path.normcase(caminho.resolve()) == os.path.normcase(Path(__file__).resolve().parent / "cs.py")
    except (OSError, ValueError):
        return False


def liberar(dados: dict) -> bool:
    """True quando um agente do plugin roda o script dele, em um comando de LIBERADOS, sem mais nada junto."""
    if not str(dados.get("agent_type") or "").startswith("gestao-de-cs:"):
        return False
    if dados.get("tool_name") not in ("Bash", "PowerShell"):
        return False
    pedacos = _pedacos(str((dados.get("tool_input") or {}).get("command") or ""))
    if not pedacos or len(pedacos) < 3 or pedacos[0] != "python":
        return False
    if not _e_o_cs_py(pedacos[1], Path(dados.get("cwd") or ".")):
        return False
    permitidas = LIBERADOS.get(pedacos[2])
    opcoes, valores = pedacos[3::2], pedacos[4::2]
    if permitidas is None or len(opcoes) != len(valores) or len(set(opcoes)) != len(opcoes):
        return False
    return "--pasta" in opcoes and set(opcoes) <= permitidas and not any(v.startswith("-") for v in valores)


def main() -> int:
    try:
        dados = json.load(sys.stdin)
    except ValueError:
        return 0
    # Só ASCII na saída: no Windows, a saída do Python não sai em UTF-8 por padrão.
    if decidir(dados):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": MOTIVO}}))
    elif liberar(dados):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow", "permissionDecisionReason": MOTIVO_LIBERADO}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
