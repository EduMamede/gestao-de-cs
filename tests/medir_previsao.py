#!/usr/bin/env python
"""Mede as previsões em muitas empresas inventadas: quantas vezes passam por engano e quantas acham o que existe.

Leva alguns minutos, por isso não faz parte dos testes automáticos. Rode depois de mudar o modelo, os sinais ou os cortes.
A resposta certa é zero no ruído. Use sementes diferentes das que serviram para escolher o corte.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
sys.path.insert(0, str(RAIZ / "tests"))

from cslib import config as config_mod, pasta as pasta_mod  # noqa: E402
from cslib.medir import rodar  # noqa: E402
import gerar_historico  # noqa: E402
from gerar_bases import REF  # noqa: E402

CASOS = (("ruido", 40, 20), ("ruido", 140, 30), ("ruido", 220, 15), ("padrao", 40, 10), ("padrao", 140, 8), ("padrao", 220, 5))


def medir(cenario: str, contas: int, empresas: int, primeira_semente: int) -> None:
    placar = {"churn": Counter(), "engajamento": Counter(), "incremento": Counter()}
    falsos = []
    tempo = 0.0
    for semente in range(primeira_semente, primeira_semente + empresas):
        tmp = Path(tempfile.mkdtemp(prefix="csmedir-"))
        try:
            pasta = tmp / "empresa"
            pasta_mod.criar_pasta(pasta, "Empresa inventada", "protegido")
            gerar_historico.montar(pasta, cenario, contas=contas, semente=semente)
            inicio = time.time()
            r = rodar(pasta, REF, pasta / "4-dados" / "entradas" / REF.isoformat(), config_mod.carregar(pasta), "protegido")
            tempo += time.time() - inicio
            for nome, contagem in placar.items():
                status = r.previsoes[nome]["status"]
                contagem[status] += 1
                if cenario == "ruido" and status == "ok":
                    falsos.append(f"{nome} na semente {semente}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    resultado = "; ".join(f"{nome} {dict(contagem)}" for nome, contagem in placar.items())
    print(f"{cenario}, {contas} contas, {empresas} empresas: {resultado}. Falsos positivos: {falsos or 'nenhum'}. Rodada média: {tempo / empresas:.1f}s", flush=True)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--semente", type=int, default=201, help="primeira semente")
    args = parser.parse_args()
    for cenario, contas, empresas in CASOS:
        medir(cenario, contas, empresas, args.semente)
    return 0


if __name__ == "__main__":
    sys.exit(main())
