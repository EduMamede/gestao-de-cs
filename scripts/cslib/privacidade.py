"""Códigos no lugar de nomes, e a volta dos nomes só no fim.

No modo protegido, o Claude só vê CONTA-017, CSM-01 e SEG-02. A tabela que liga o
código ao nome real fica em 4-dados/.privado/ e só o script a abre.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from .leitura import ler_tabela, normalizar, normalizar_id, normalizar_nome_conta, eh_vazio

RE_CODIGO = re.compile(r"\b(CONTA-\d{3,}|CSM-\d{2,}|SEG-\d{2,}|TEMA-\d{2,})\b")


def escrever_csv(caminho: Path, cabecalho: list[str], linhas: list[list]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8-sig", newline="") as saida:
        escritor = csv.writer(saida, delimiter=";")
        escritor.writerow(cabecalho)
        escritor.writerows(linhas)


def _ler_csv_simples(caminho: Path) -> list[dict]:
    if not caminho.exists():
        return []
    tabela = ler_tabela(caminho)
    nomes = [normalizar(c) for c in tabela.colunas]
    registros = []
    for linha in tabela.linhas:
        registros.append({n: ("" if eh_vazio(v) else str(v).strip()) for n, v in zip(nomes, linha)})
    return registros


class Cofre:
    """Guarda a ligação entre código e nome real, estável de uma rodada para a outra."""

    def __init__(self, pasta: Path):
        self.dir = pasta / "4-dados" / ".privado"
        self.contas: list[dict] = []
        self.por_id: dict = {}
        self.por_nome: dict = {}
        self.pessoas: dict = {}
        self.segmentos: dict = {}
        self.temas: dict = {}
        for r in _ler_csv_simples(self.dir / "mapa-temas.csv"):
            self.temas[r["chave"]] = (r["codigo"], r["nome"])
        for r in _ler_csv_simples(self.dir / "mapa-contas.csv"):
            self._guardar(r["codigo"], r.get("chave id", ""), r.get("chave nome", ""), r.get("nome", ""), r.get("id original", ""))
        for r in _ler_csv_simples(self.dir / "mapa-pessoas.csv"):
            self.pessoas[r["chave"]] = (r["codigo"], r["nome"])
        for r in _ler_csv_simples(self.dir / "mapa-segmentos.csv"):
            self.segmentos[r["chave"]] = (r["codigo"], r["nome"])

    def _guardar(self, codigo, chave_id, chave_nome, nome, id_original):
        registro = {"codigo": codigo, "chave_id": chave_id, "chave_nome": chave_nome, "nome": nome, "id_original": id_original}
        self.contas.append(registro)
        if chave_id:
            self.por_id[chave_id] = registro
        if chave_nome:
            self.por_nome[chave_nome] = registro
        return registro

    def codigo_conta(self, id_original, nome) -> str:
        chave_id = normalizar_id(id_original) if not eh_vazio(id_original) else ""
        chave_nome = normalizar_nome_conta(nome) if not eh_vazio(nome) else ""
        registro = self.por_id.get(chave_id) if chave_id else None
        if registro is None and chave_nome:
            registro = self.por_nome.get(chave_nome)
        if registro is None:
            numero = max((int(r["codigo"].split("-")[1]) for r in self.contas), default=0) + 1
            codigo = f"CONTA-{numero:03d}"
            texto_nome = "" if eh_vazio(nome) else str(nome).strip()
            texto_id = "" if eh_vazio(id_original) else str(id_original).strip()
            registro = self._guardar(codigo, chave_id, chave_nome, texto_nome, texto_id)
        else:
            if chave_id and not registro["chave_id"]:
                registro["chave_id"] = chave_id
                registro["id_original"] = str(id_original).strip()
                self.por_id[chave_id] = registro
            if chave_nome and not registro["chave_nome"]:
                registro["chave_nome"] = chave_nome
                registro["nome"] = str(nome).strip()
                self.por_nome[chave_nome] = registro
        return registro["codigo"]

    def registro(self, codigo: str) -> dict:
        for r in self.contas:
            if r["codigo"] == codigo:
                return r
        return {}

    def nome_conta(self, codigo: str) -> str:
        r = self.registro(codigo)
        return r.get("nome") or r.get("id_original") or codigo

    def _codigo_lista(self, mapa: dict, prefixo: str, nome) -> str:
        chave = normalizar(nome)
        if chave not in mapa:
            mapa[chave] = (f"{prefixo}-{len(mapa) + 1:02d}", str(nome).strip())
        return mapa[chave][0]

    def codigo_pessoa(self, nome) -> str:
        return self._codigo_lista(self.pessoas, "CSM", nome)

    def codigo_segmento(self, nome) -> str:
        return self._codigo_lista(self.segmentos, "SEG", nome)

    def codigo_tema(self, nome) -> str:
        return self._codigo_lista(self.temas, "TEMA", nome)

    def nome_de(self, codigo: str) -> str:
        if codigo.startswith("CONTA-"):
            return self.nome_conta(codigo)
        mapa = self.pessoas if codigo.startswith("CSM-") else (self.temas if codigo.startswith("TEMA-") else self.segmentos)
        for cod, nome in mapa.values():
            if cod == codigo:
                return nome
        return codigo

    def restaurar(self, texto: str) -> str:
        return RE_CODIGO.sub(lambda m: self.nome_de(m.group(1)), texto)

    def salvar(self) -> None:
        escrever_csv(
            self.dir / "mapa-contas.csv",
            ["codigo", "chave id", "chave nome", "nome", "id original"],
            [[r["codigo"], r["chave_id"], r["chave_nome"], r["nome"], r["id_original"]] for r in self.contas],
        )
        escrever_csv(self.dir / "mapa-pessoas.csv", ["codigo", "chave", "nome"], [[c, k, n] for k, (c, n) in self.pessoas.items()])
        if self.temas:
            escrever_csv(self.dir / "mapa-temas.csv", ["codigo", "chave", "nome"], [[c, k, n] for k, (c, n) in self.temas.items()])
        escrever_csv(self.dir / "mapa-segmentos.csv", ["codigo", "chave", "nome"], [[c, k, n] for k, (c, n) in self.segmentos.items()])


class Rotulos:
    """Liga cada rótulo dos dados ao que ele significa para a skill.

    Os rótulos ficam em 4-dados/.privado/rotulos.csv. O script preenche o que for óbvio;
    o resto a pessoa completa. No modo protegido o Claude só vê a contagem de pendências.
    """

    SIGNIFICADOS_VALIDOS = {
        "status": {"ativa", "cancelada"},
        "motivo_parada": {"do cliente", "nosso"},
    }

    def __init__(self, pasta: Path, cfg, zerar_contagem: bool = True):
        self.caminho = pasta / "4-dados" / ".privado" / "rotulos.csv"
        self.cfg = cfg
        self.dados: dict = {}
        for r in _ler_csv_simples(self.caminho):
            self.dados[(r["campo"], normalizar(r["rotulo"]))] = {
                "rotulo": r["rotulo"],
                "significa": r.get("significa", ""),
                # a rodada conta de novo; quem só quer mostrar usa a contagem da última rodada
                "contas": 0 if zerar_contagem else int(float(r.get("contas") or 0)),
            }

    def _automatico(self, campo: str, chave: str) -> str:
        palavras = set(chave.split())
        if campo == "etapa":
            for etapa in self.cfg.etapas:
                if etapa.chave == chave:
                    return etapa.nome
            candidatas = [e for e in self.cfg.etapas if e.chave in chave or chave in e.chave]
            return candidatas[0].nome if len(candidatas) == 1 else ""
        if campo == "status":
            if any(p.startswith(("cancel", "churn", "inativ", "encerr", "perdid", "resc", "saiu", "desativ")) for p in palavras):
                return "cancelada"
            if any(p.startswith(("ativ", "vigent", "em dia", "cliente", "ok")) for p in palavras) or "em uso" in chave:
                return "ativa"
            return ""
        if campo == "motivo_parada":
            if "cliente" in palavras or "contratante" in palavras:
                return "do cliente"
            if palavras & {"nos", "nosso", "nossa", "interno", "interna", "equipe", "time", "suporte", "implantacao", "produto", "desenvolvimento", "dev", "cs"}:
                return "nosso"
            return ""
        return ""

    def significa(self, campo: str, rotulo) -> str:
        """Registra o rótulo visto e devolve o significado (vazio se ainda não sabemos)."""
        if eh_vazio(rotulo):
            return ""
        chave = normalizar(rotulo)
        item = self.dados.get((campo, chave))
        if item is None:
            item = {"rotulo": str(rotulo).strip(), "significa": "", "contas": 0}
            self.dados[(campo, chave)] = item
        if not item["significa"]:
            item["significa"] = self._automatico(campo, chave)
        item["contas"] += 1
        return item["significa"]

    def consultar(self, campo: str, rotulo) -> str:
        """Só lê o significado, sem contar a conta de novo."""
        if eh_vazio(rotulo):
            return ""
        chave = normalizar(rotulo)
        item = self.dados.get((campo, chave))
        return item["significa"] if item else self._automatico(campo, chave)

    def definir(self, campo: str, rotulo, significado) -> None:
        chave = normalizar(rotulo)
        item = self.dados.setdefault((campo, chave), {"rotulo": str(rotulo).strip(), "significa": "", "contas": 0})
        if isinstance(significado, float) and significado.is_integer():
            significado = int(significado)
        item["significa"] = str(significado)

    def pendentes(self) -> dict:
        contagem: dict = {}
        for (campo, _), item in self.dados.items():
            if self.precisa_de_significado(campo) and not item["significa"] and item["contas"]:
                contagem[campo] = contagem.get(campo, 0) + 1
        return contagem

    @staticmethod
    def precisa_de_significado(campo: str) -> bool:
        return campo in ("etapa", "status", "motivo_parada") or campo.startswith("indicador:")

    def resumo_sem_rotulos(self) -> dict:
        """Por campo, o que os rótulos viraram. Seguro no modo protegido: fala só o significado."""
        saida: dict = {}
        for (campo, _), item in sorted(self.dados.items()):
            if not item["contas"] or not self.precisa_de_significado(campo):
                continue
            grupo = saida.setdefault(campo, {"rotulos": 0, "sem_ligacao": 0, "contas": {}})
            grupo["rotulos"] += 1
            if item["significa"]:
                grupo["contas"][item["significa"]] = grupo["contas"].get(item["significa"], 0) + item["contas"]
            else:
                grupo["sem_ligacao"] += 1
        return saida

    def salvar(self) -> None:
        linhas = [
            [campo, item["rotulo"], item["significa"], item["contas"]]
            for (campo, _), item in sorted(self.dados.items(), key=lambda x: (x[0][0], x[1]["rotulo"]))
        ]
        escrever_csv(self.caminho, ["campo", "rotulo", "significa", "contas"], linhas)
