"""Cria e reconhece a pasta da empresa. Ela nunca fica dentro do plugin."""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
from pathlib import Path

from . import ErroDeUso

MARCADOR = ".gestao-de-cs.json"
MODOS = ("aberto", "protegido")
NOVOS = "novos"  # 4-dados/entradas/novos: onde o export chega para a rotina. A trava de privacidade já cobre


def raiz_plugin() -> Path:
    return Path(__file__).resolve().parents[2]


def ler_marcador(pasta: Path) -> dict:
    caminho = pasta / MARCADOR
    if not caminho.exists():
        return {}
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def modo_privacidade(pasta: Path) -> str:
    """Sem escolha registrada, protege: um script não pode perguntar à pessoa."""
    modo = ler_marcador(pasta).get("modo_privacidade")
    return modo if modo in MODOS else "protegido"


def definir_modo(pasta: Path, modo: str) -> None:
    if modo not in MODOS:
        raise ErroDeUso("o modo de privacidade deve ser 'aberto' ou 'protegido'.")
    dados = ler_marcador(pasta)
    dados["modo_privacidade"] = modo
    dados["modo_escolhido_em"] = dt.date.today().isoformat()
    (pasta / MARCADOR).write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    leia_me = pasta / "LEIA-ME.md"
    if leia_me.exists():
        texto = re.sub(r"(\*\*Modo de privacidade:\*\* ).*", lambda m: m.group(1) + modo, leia_me.read_text(encoding="utf-8"))
        leia_me.write_text(texto, encoding="utf-8")


def exigir_pasta(pasta) -> Path:
    pasta = Path(pasta).resolve()
    if not (pasta / MARCADOR).exists():
        raise ErroDeUso(f"esta pasta não foi criada pela skill (falta {MARCADOR}). Rode criar-pasta primeiro.")
    return pasta


def criar_pasta(destino, empresa: str, modo: str | None = None, permitir_no_plugin: bool = False) -> tuple[Path, list[str]]:
    destino = Path(destino).resolve()
    raiz = raiz_plugin()
    if not permitir_no_plugin and (destino == raiz or raiz in destino.parents):
        raise ErroDeUso("a pasta da empresa não pode ficar dentro do plugin. Escolha outro lugar.")
    modelos = raiz / "modelos" / "pasta-empresa"
    hoje = dt.date.today().isoformat()
    criados: list[str] = []
    for origem in sorted(modelos.rglob("*")):
        relativo = origem.relative_to(modelos)
        alvo = destino / relativo
        if origem.is_dir():
            alvo.mkdir(parents=True, exist_ok=True)
            continue
        if alvo.exists():  # nunca sobrescreve o que a pessoa já escreveu
            continue
        alvo.parent.mkdir(parents=True, exist_ok=True)
        if origem.suffix == ".md":
            texto = origem.read_text(encoding="utf-8").replace("{{EMPRESA}}", empresa).replace("{{DATA}}", hoje)
            alvo.write_text(texto, encoding="utf-8")
        else:
            shutil.copyfile(origem, alvo)
        criados.append(str(relativo).replace("\\", "/"))
    for vazia in ("4-dados/entradas", f"4-dados/entradas/{NOVOS}", "4-dados/rodadas", "4-dados/.privado", "com-nomes", "3-clientes"):
        (destino / vazia).mkdir(parents=True, exist_ok=True)
    if not (destino / MARCADOR).exists():
        (destino / MARCADOR).write_text(
            json.dumps({"empresa": empresa, "criada_em": hoje, "modo_privacidade": None}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    gitignore = destino / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("# A pasta da empresa nunca vai para o GitHub.\n*\n", encoding="utf-8")
    if modo:
        definir_modo(destino, modo)
    return destino, criados


def nova_ficha(pasta: Path, codigo: str) -> Path:
    modelo = raiz_plugin() / "modelos" / "ficha-conta.md"
    ficha = pasta / "3-clientes" / codigo / "ficha.md"
    (ficha.parent / "reunioes").mkdir(parents=True, exist_ok=True)
    if not ficha.exists():
        ficha.write_text(modelo.read_text(encoding="utf-8").replace("{{CONTA}}", codigo), encoding="utf-8")
    return ficha
