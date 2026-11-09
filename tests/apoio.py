"""Apoio dos testes: monta uma empresa de mentira e roda o programa de verdade."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
CS = RAIZ / "scripts" / "cs.py"
sys.path.insert(0, str(RAIZ / "scripts"))
sys.path.insert(0, str(AQUI))

import gerar_bases  # noqa: E402

REF = gerar_bases.REF.isoformat()
_bases = None


def bases() -> dict:
    global _bases
    if _bases is None:
        _bases = gerar_bases.gerar_todas()
    return _bases


def rodar(*args) -> tuple:
    processo = subprocess.run(
        [sys.executable, str(CS), *[str(a) for a in args]], capture_output=True, text=True, encoding="utf-8", env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"}
    )
    return processo.returncode, processo.stdout + processo.stderr


class Empresa:
    def __init__(self, nome_base: str, modo: str = "protegido", destino=None):
        self.nome_base = nome_base
        self.tmp = None
        if destino is None:
            self.tmp = tempfile.TemporaryDirectory(prefix="csteste-")
            destino = Path(self.tmp.name) / "empresa"
        self.pasta = Path(destino)
        base = bases()[nome_base]
        codigo, saida = rodar("criar-pasta", "--destino", self.pasta, "--empresa", f"Empresa de teste {nome_base}", "--modo", modo)
        assert codigo == 0, saida
        (self.pasta / "4-dados" / "como-medir.md").write_text(base["como_medir"], encoding="utf-8")
        (self.pasta / "4-dados" / "colunas.md").write_text(base["colunas"], encoding="utf-8")
        (self.pasta / "1-empresa" / "jornada.md").write_text(base["jornada"], encoding="utf-8")
        (self.pasta / "2-metas" / "metas.md").write_text(base["metas"], encoding="utf-8")
        self.entrada = self.pasta / "4-dados" / "entradas" / REF
        self.entrada.mkdir(parents=True, exist_ok=True)
        for arquivo in base["arquivos"]:
            shutil.copyfile(AQUI / "bases" / nome_base / arquivo, self.entrada / arquivo)

    def rodada(self, data: str = REF, *extras):
        return rodar("rodada", "--pasta", self.pasta, "--data", data, "--entrada", REF, *extras)

    def resumo(self, data: str = REF) -> dict:
        return json.loads((self.pasta / "4-dados" / "rodadas" / data / "resumo.json").read_text(encoding="utf-8"))

    def mapa(self) -> dict:
        """Nome -> código, lido do arquivo privado, como só o teste pode fazer."""
        import csv

        with (self.pasta / "4-dados" / ".privado" / "mapa-contas.csv").open(encoding="utf-8-sig", newline="") as f:
            return {linha["nome"]: linha["codigo"] for linha in csv.DictReader(f, delimiter=";")}

    def fechar(self):
        if self.tmp:
            self.tmp.cleanup()


def textos_para_ia(pasta: Path) -> dict:
    """Tudo que a IA pode ler no modo protegido, na rodada e nas outras pastas."""
    saida = {}
    for caminho in pasta.rglob("*"):
        if not caminho.is_file():
            continue
        partes = set(caminho.relative_to(pasta).parts)
        if ".privado" in partes or "com-nomes" in partes or "entradas" in partes:
            continue
        if caminho.suffix == ".xlsx":
            continue
        saida[str(caminho.relative_to(pasta))] = caminho.read_text(encoding="utf-8-sig", errors="replace")
    return saida
