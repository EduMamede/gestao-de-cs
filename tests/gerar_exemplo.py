#!/usr/bin/env python
"""Refaz exemplos/empresa-exemplo a partir da base completa. Tudo é inventado."""

from __future__ import annotations

import datetime as dt
import shutil
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(RAIZ / "scripts"))
sys.path.insert(0, str(AQUI))

import gerar_bases  # noqa: E402
from cslib import config as config_mod  # noqa: E402
from cslib.medir import rodar  # noqa: E402
from cslib.pasta import criar_pasta, modo_privacidade  # noqa: E402
from cslib.privacidade import Cofre  # noqa: E402
from cslib.relatorios import gravar_rodada  # noqa: E402
from cslib.semana import MARCA_LEITURA, texto_semana  # noqa: E402

DESTINO = RAIZ / "exemplos" / "empresa-exemplo"
EMPRESA = "Sistema Clínico Fictício"
DATA = gerar_bases.REF

LEITURA = (
    "Duas metas estão atrás, e a saúde geral parece boa: a maioria das contas é saudável. O risco está concentrado. "
    "A primeira conta da lista responde por boa parte da receita, renova em 45 dias e está com pagamento em atraso. É a preocupação da semana.\n\n"
    "O que a nota não mostra: duas contas com nota máxima precisam de atenção. Uma mudou de padrão, outra está parada na implantação. "
    "Se a gente olhasse só a nota, nenhuma das duas estaria na lista.\n\n"
    "Para depois: as contas mornas de receita menor podem esperar a próxima semana, se a agenda apertar."
)


def preencher(pasta: Path, relativo: str, trocas: dict) -> None:
    caminho = pasta / relativo
    texto = caminho.read_text(encoding="utf-8")
    for antes, depois in trocas.items():
        texto = texto.replace(antes, depois)
    caminho.write_text(texto, encoding="utf-8")


def main() -> None:
    bases = gerar_bases.gerar_todas()
    base = bases["completa"]
    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    criar_pasta(DESTINO, EMPRESA, modo="protegido", permitir_no_plugin=True)

    (DESTINO / "4-dados" / "como-medir.md").write_text(base["como_medir"].replace("Base de teste.", "Exemplo com dados inventados."), encoding="utf-8")
    (DESTINO / "4-dados" / "colunas.md").write_text(base["colunas"].replace("Base de teste.", "Exemplo com dados inventados."), encoding="utf-8")
    (DESTINO / "1-empresa" / "jornada.md").write_text(base["jornada"].replace("Base de teste.", "Exemplo com dados inventados."), encoding="utf-8")
    (DESTINO / "2-metas" / "metas.md").write_text(base["metas"].replace("Base de teste.", "Exemplo com dados inventados."), encoding="utf-8")

    preencher(DESTINO, "1-empresa/perfil.md", {
        "{{ }}": "Exemplo inventado",
        "{{assinatura ou recompra}}": "assinatura",
        "{{vendas ainda cuida, primeiro CSM, time com segmentos...}}": "time de 2 pessoas com líder",
        "{{use cargos ou códigos se preferir não expor nomes}}": "duas CSMs, uma para cada carteira",
    })
    preencher(DESTINO, "1-empresa/conversas-consultor.md", {
        "{{próximo passo}}": "fazer a próxima rodada com o export de dezembro",
    })
    conversas = DESTINO / "1-empresa" / "conversas-consultor.md"
    conversas.write_text(
        conversas.read_text(encoding="utf-8")
        + f"- {DATA.isoformat()}: exemplo inventado. Dor principal: acompanhar o plano do paciente. Rotinas que provam valor: plano, estoque e agenda, além de financeiro e chamados.\n"
        + f"- {DATA.isoformat()}: escolhido o modo protegido, porque há dado de clínica.\n",
        encoding="utf-8",
    )
    preencher(DESTINO, "LEIA-ME.md", {
        "{{o Consultor atualiza esta linha a cada conversa}}": "rodar a próxima semana a partir do export de dezembro.",
        "{{aberto ou protegido}}": "protegido",
        "{{o que já foi respondido}}": "completo neste exemplo",
        "{{data}}": DATA.isoformat(),
        "{{arquivo em 2-metas}}": "semana-2026-11-02.md",
    })

    entrada = DESTINO / "4-dados" / "entradas" / DATA.isoformat()
    entrada.mkdir(parents=True, exist_ok=True)
    for arquivo in base["arquivos"]:
        shutil.copyfile(AQUI / "bases" / "completa" / arquivo, entrada / arquivo)

    cfg = config_mod.carregar(DESTINO)
    resultado = rodar(DESTINO, DATA, entrada, cfg, modo_privacidade(DESTINO))
    destino_rodada = DESTINO / "4-dados" / "rodadas" / DATA.isoformat()
    resumo = gravar_rodada(resultado, DESTINO, destino_rodada)

    segunda = dt.date(2026, 11, 2)
    texto = texto_semana(segunda, resumo).replace(MARCA_LEITURA, LEITURA)
    (DESTINO / "2-metas" / f"semana-{segunda.isoformat()}.md").write_text(texto, encoding="utf-8")
    (DESTINO / "com-nomes" / f"semana-{segunda.isoformat()}.md").write_text(Cofre(DESTINO).restaurar(texto), encoding="utf-8")
    print(f"Exemplo pronto em {DESTINO}")


if __name__ == "__main__":
    main()
