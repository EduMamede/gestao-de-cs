"""Lê o que a pessoa combinou no checklist, a partir das tabelas dos arquivos .md.

O .md é a única fonte da verdade: a pessoa consegue ler e corrigir sem programar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .leitura import normalizar, parse_numero

PESOS = {"alta": 3, "media": 2, "baixa": 1}

# campo padrão -> (tipo, para que serve)
CAMPOS = {
    "conta_id": ("id", "código da conta no sistema da pessoa"),
    "conta_nome": ("nome", "nome da conta"),
    "receita": ("numero", "quanto a conta paga"),
    "receita_anterior": ("numero", "quanto pagava no período anterior"),
    "data_inicio": ("data", "quando virou cliente"),
    "renovacao": ("data", "quando renova"),
    "contrato": ("rotulo", "tipo de contrato: anual, mensal ou outro"),
    "segmento": ("segmento", "grupo da conta"),
    "responsavel": ("pessoa", "quem do CS cuida"),
    "status": ("rotulo", "ativa ou cancelada"),
    "data_cancelamento": ("data", "quando cancelou"),
    "motivo_cancelamento": ("rotulo", "por que cancelou"),
    "etapa": ("rotulo", "etapa atual da jornada"),
    "data_entrada_etapa": ("data", "quando entrou na etapa"),
    "dias_na_etapa": ("numero", "dias na etapa, se o sistema já der pronto"),
    "motivo_parada": ("rotulo", "por que parou: do cliente ou nosso"),
    "proximo_passo": ("texto", "próximo passo combinado (texto livre, só vai para a planilha)"),
    "data_proximo_contato": ("data", "data do próximo contato"),
    "ultimo_contato": ("data", "data do último contato"),
    "nps": ("numero", "nota de NPS de 0 a 10"),
    "patrocinador": ("contato", "quem patrocina (só contamos se está preenchido)"),
    "decisor": ("contato", "quem decide (só contamos se está preenchido)"),
    "usuario_chave": ("contato", "usuário-chave (só contamos se está preenchido)"),
    "data_evento": ("data", "data do registro, em arquivos com uma linha por evento"),
    "usuario_evento": ("pessoa", "quem fez o registro, em arquivos de eventos (só contamos, o nome nunca sai do script)"),
    "usuarios": ("numero", "quantos usuários ou acessos a conta tem"),
    "tema_evento": ("rotulo", "assunto do registro, de uma lista curta, como a categoria do chamado"),
}

# como ler -> tipo. Quais precisam de um limite dito pela pessoa está em REGRA_PRECISA_DE_LIMITE.
TIPOS_DE_OPORTUNIDADE = {"sem uso": "sem_uso", "um usuario concentra": "um_usuario", "volume por usuario": "por_usuario", "acima de": "acima_de", "abaixo de": "abaixo_de"}
REGRA_PRECISA_DE_LIMITE = ("por_usuario", "acima_de", "abaixo_de")

REGRAS_PADRAO = {
    "modelo de receita": "assinatura",
    "contrato padrao": "",
    "variacao para alerta": 30.0,
    "minimo absoluto": 2.0,
    "cobertura minima": 40.0,
    "renovacao proxima": 90.0,
    "sem contato": 60.0,
    "queda de nota": 15.0,
    "minimo de casos para prever": 30.0,
    "aumento minimo de receita": 5.0,
}


@dataclass
class Indicador:
    id: str
    rotina: str
    bloco: str = "rotina"
    dado_prova: str = ""
    arquivo: str = ""
    coluna: str = ""
    coluna_anterior: str = ""
    medida: str = ""
    esperado_txt: str = ""
    esperado: float | None = None
    janela: int = 30
    padrao_da_conta: bool = False
    valores: dict = field(default_factory=dict)
    criticidade: str = "media"
    peso: int = 2
    direcao: str = "bom"
    direcao_etapas: dict = field(default_factory=dict)
    erros: list = field(default_factory=list)  # travam a rodada: o que está escrito está errado
    pendencias: list = field(default_factory=list)  # não travam: a pessoa ainda não respondeu

    @property
    def tem_fonte(self) -> bool:
        return bool(self.arquivo and (self.coluna or self.medida in ("eventos", "ultima-data")))


@dataclass
class Etapa:
    nome: str
    prazo: float | None
    chave: str


@dataclass
class Meta:
    meta: str
    indicador: str
    alvo: float | None
    alvo_txt: str = ""
    melhor_quando: str = ""
    prazo: str = ""
    responsavel: str = ""


@dataclass
class RegraDeOportunidade:
    nome: str
    tipo: str
    indicador: str
    limite: float | None = None
    oferta: str = ""


@dataclass
class Config:
    indicadores: list[Indicador] = field(default_factory=list)
    oportunidades: list[RegraDeOportunidade] = field(default_factory=list)
    etapas: list[Etapa] = field(default_factory=list)
    metas: list[Meta] = field(default_factory=list)
    arquivos: dict = field(default_factory=dict)  # arquivo -> "contas" ou "eventos"
    colunas: dict = field(default_factory=dict)  # arquivo -> {campo: coluna}
    bloqueadas: dict = field(default_factory=dict)  # arquivo -> colunas marcadas como bloqueadas
    regras: dict = field(default_factory=lambda: dict(REGRAS_PADRAO))
    erros: list = field(default_factory=list)
    pendencias: list = field(default_factory=list)

    def etapa(self, chave: str):
        for etapa in self.etapas:
            if etapa.chave == chave:
                return etapa
        return None

    @property
    def recompra(self) -> bool:
        return "recompra" in normalizar(self.regras.get("modelo de receita", ""))


def tabela_md(texto: str, secao: str) -> list[dict]:
    """Devolve a tabela que vem logo depois do primeiro título com `secao` que tenha uma."""
    linhas = texto.splitlines()
    alvo = normalizar(secao)
    for i, linha in enumerate(linhas):
        if linha.lstrip().startswith("#") and alvo in normalizar(linha):
            tabela = _primeira_tabela(linhas[i + 1:])
            if tabela:
                return tabela
    return []


def _celulas(linha: str) -> list[str]:
    linha = linha.strip().strip("|").replace("\\|", "\u0000")
    return [c.strip().replace("\u0000", "|") for c in linha.split("|")]


def _primeira_tabela(linhas: list[str]) -> list[dict]:
    cabecalho, corpo = None, []
    for linha in linhas:
        if linha.lstrip().startswith("#"):
            break
        if not linha.strip().startswith("|"):
            if cabecalho is not None:
                break
            continue
        celulas = _celulas(linha)
        if all(re.fullmatch(r":?-{2,}:?", c) for c in celulas if c):
            continue
        if cabecalho is None:
            cabecalho = [normalizar(c) for c in celulas]
            continue
        registro = {}
        for nome, valor in zip(cabecalho, celulas):
            valor = "" if valor in ("—", "–", "-") else valor
            if "{{" in valor:  # campo do modelo ainda sem resposta
                valor = ""
            registro[nome] = valor
        if any(registro.values()):
            corpo.append(registro)
    return corpo


def _pegar(registro: dict, *nomes) -> str:
    for nome in nomes:
        if registro.get(nome):
            return registro[nome]
    return ""


def _medida(texto: str) -> str:
    t = normalizar(texto)
    if "evento" in t or "registro" in t:
        return "eventos"
    if "ultima" in t or t == "data":
        return "ultima-data"
    if "categoria" in t or "situacao" in t:
        return "categoria"
    if "contagem" in t or "quantidade" in t or "numero" in t:
        return "contagem"
    return ""


def _direcao(texto: str) -> tuple[str, dict]:
    """Aceita 'bom', 'ruim' ou 'Onboarding: bom; demais: ruim'."""
    if ":" not in texto:
        t = normalizar(texto)
        return ("ruim" if "ruim" in t else "bom"), {}
    base, por_etapa = "bom", {}
    for parte in texto.split(";"):
        if ":" not in parte:
            continue
        etapa, valor = parte.split(":", 1)
        valor = "ruim" if "ruim" in normalizar(valor) else "bom"
        chave = normalizar(etapa)
        if chave in ("demais", "resto", "outras", "outros"):
            base = valor
        else:
            por_etapa[chave] = valor
    return base, por_etapa


def _ler_esperado(ind: Indicador) -> None:
    t = ind.esperado_txt.strip()
    if ind.medida == "categoria":
        for parte in re.split(r"[;\n]", t):
            if "=" in parte:
                rotulo, nota = parte.split("=", 1)
                numero = parse_numero(nota)
                if numero is None:
                    ind.erros.append("nota inválida em 'frequência esperada'")
                else:
                    ind.valores[normalizar(rotulo)] = numero
        return
    if not t:
        ind.pendencias.append("falta a frequência esperada")
        return
    norm = normalizar(t)
    if ind.medida == "ultima-data" and "padrao" in norm:
        ind.padrao_da_conta = True
        return
    numeros = re.findall(r"\d+(?:[.,]\d+)?", t)
    if not numeros:
        ind.pendencias.append("falta a frequência esperada em número")
        return
    ind.esperado = parse_numero(numeros[0])
    if ind.medida == "eventos":
        m = re.search(r"(\d+)\s*(dias?|semanas?|mes|meses)", norm)
        if m:
            fator = {"d": 1, "s": 7, "m": 30}[m.group(2)[0]]
            ind.janela = int(m.group(1)) * fator
        elif "semana" in norm:
            ind.janela = 7
        elif "mes" in norm:
            ind.janela = 30
    elif ind.medida == "ultima-data":
        if "semana" in norm:
            ind.esperado *= 7
        elif "mes" in norm:
            ind.esperado *= 30


def _ler_oportunidade(r: dict, cfg: Config) -> None:
    nome = _pegar(r, "oportunidade")
    if not nome:
        return
    como = normalizar(_pegar(r, "como ler"))
    if not como:
        cfg.pendencias.append(f"como-medir.md, oportunidade '{nome}': falta dizer como ler")
        return
    tipo = TIPOS_DE_OPORTUNIDADE.get(como)
    if tipo is None:
        cfg.erros.append(f"como-medir.md, oportunidade '{nome}': como ler deve ser {', '.join(TIPOS_DE_OPORTUNIDADE)}")
        return
    rotina = normalizar(_pegar(r, "rotina"))
    ind = next((i for i in cfg.indicadores if rotina and rotina in (normalizar(i.id), normalizar(i.rotina))), None)
    if ind is None:
        cfg.erros.append(f"como-medir.md, oportunidade '{nome}': a rotina não está na tabela de indicadores")
        return
    limite = parse_numero(_pegar(r, "limite")) if _pegar(r, "limite") else None
    if limite is None and tipo in REGRA_PRECISA_DE_LIMITE:
        cfg.pendencias.append(f"como-medir.md, oportunidade '{nome}': falta o limite")
        return
    cfg.oportunidades.append(RegraDeOportunidade(nome=nome, tipo=tipo, indicador=ind.id, limite=limite, oferta=_pegar(r, "o que oferecer")))


def ler_como_medir(caminho: Path, cfg: Config) -> None:
    if not caminho.exists():
        return
    texto = caminho.read_text(encoding="utf-8")
    vistos = set()
    for r in tabela_md(texto, "Indicadores"):
        rotina = _pegar(r, "rotina")
        id_ = normalizar(_pegar(r, "id") or rotina).replace(" ", "-")
        if not id_:
            continue
        ind = Indicador(id=id_, rotina=rotina or id_)
        ind.bloco = normalizar(_pegar(r, "bloco")) or "rotina"
        ind.dado_prova = _pegar(r, "dado que prova")
        ind.arquivo = _pegar(r, "onde esta o dado", "arquivo")
        ind.coluna = _pegar(r, "coluna")
        ind.coluna_anterior = _pegar(r, "coluna anterior")
        ind.medida = _medida(_pegar(r, "como ler", "medida"))
        ind.esperado_txt = _pegar(r, "frequencia esperada", "esperado")
        crit = normalizar(_pegar(r, "criticidade"))
        if crit and crit not in PESOS:
            ind.erros.append("criticidade deve ser alta, média ou baixa")
        if not crit:
            ind.pendencias.append("falta a criticidade: usei média")
        ind.criticidade = crit if crit in PESOS else "media"
        ind.peso = PESOS[ind.criticidade]
        direcao_txt = _pegar(r, "subir e", "se subir e", "subir e bom ou ruim")
        ind.direcao, ind.direcao_etapas = _direcao(direcao_txt or "bom")
        if not direcao_txt and ind.medida in ("contagem", "eventos"):
            ind.pendencias.append("falta dizer se subir é bom ou ruim: usei bom")
        if not ind.medida and ind.arquivo:
            ind.pendencias.append("falta dizer como ler: contagem, última data, eventos ou categoria")
        if ind.medida:
            _ler_esperado(ind)
        if id_ in vistos:
            ind.erros.append("id repetido")
        vistos.add(id_)
        cfg.indicadores.append(ind)
        for erro in ind.erros:
            cfg.erros.append(f"como-medir.md, indicador '{ind.id}': {erro}")
        for pendencia in ind.pendencias:
            cfg.pendencias.append(f"como-medir.md, indicador '{ind.id}': {pendencia}")
    for r in tabela_md(texto, "Oportunidades"):
        _ler_oportunidade(r, cfg)
    for r in tabela_md(texto, "Regras"):
        chave = normalizar(_pegar(r, "regra"))
        valor = _pegar(r, "valor")
        if not chave or not valor:
            continue
        if chave in ("modelo de receita", "contrato padrao"):
            cfg.regras[chave] = valor
        elif chave in cfg.regras:
            numero = parse_numero(valor)
            if numero is not None:
                cfg.regras[chave] = numero


def ler_jornada(caminho: Path, cfg: Config) -> None:
    if not caminho.exists():
        return
    for r in tabela_md(caminho.read_text(encoding="utf-8"), "Etapas"):
        nome = _pegar(r, "etapa")
        if not nome:
            continue
        prazo_txt = _pegar(r, "prazo dias", "prazo", "tempo de estagnacao dias", "tempo de estagnacao")
        numeros = re.findall(r"\d+", prazo_txt)
        cfg.etapas.append(Etapa(nome=nome, prazo=float(numeros[0]) if numeros else None, chave=normalizar(nome)))


def ler_metas(caminho: Path, cfg: Config) -> None:
    if not caminho.exists():
        return
    for r in tabela_md(caminho.read_text(encoding="utf-8"), "Metas"):
        meta = _pegar(r, "meta")
        if not meta:
            continue
        alvo_txt = _pegar(r, "alvo")
        cfg.metas.append(
            Meta(
                meta=meta,
                indicador=normalizar(_pegar(r, "indicador")).replace(" ", "_"),
                alvo=parse_numero(alvo_txt),
                alvo_txt=alvo_txt,
                melhor_quando=normalizar(_pegar(r, "melhor quando")),
                prazo=_pegar(r, "prazo"),
                responsavel=_pegar(r, "responsavel"),
            )
        )


def ler_colunas(caminho: Path, cfg: Config) -> None:
    if not caminho.exists():
        return
    texto = caminho.read_text(encoding="utf-8")
    for r in tabela_md(texto, "Arquivos"):
        arquivo = _pegar(r, "arquivo")
        if arquivo:
            cfg.arquivos[arquivo] = "eventos" if "evento" in normalizar(_pegar(r, "tipo")) else "contas"
    for r in tabela_md(texto, "Colunas"):
        arquivo, coluna = _pegar(r, "arquivo"), _pegar(r, "coluna")
        campo = normalizar(_pegar(r, "campo")).replace(" ", "_")
        if not arquivo or not coluna or not campo:
            continue
        cfg.arquivos.setdefault(arquivo, "contas")
        if campo in ("bloqueada", "bloquear"):
            cfg.bloqueadas.setdefault(arquivo, []).append(coluna)
            continue
        if campo in ("ignorar", "ignorada"):
            continue
        if campo not in CAMPOS:
            cfg.erros.append(f"colunas.md: campo '{campo}' não existe (veja referencias/campos-padrao.md)")
            continue
        cfg.colunas.setdefault(arquivo, {})[campo] = coluna


def carregar(pasta: Path) -> Config:
    cfg = Config()
    ler_como_medir(pasta / "4-dados" / "como-medir.md", cfg)
    ler_colunas(pasta / "4-dados" / "colunas.md", cfg)
    ler_jornada(pasta / "1-empresa" / "jornada.md", cfg)
    ler_metas(pasta / "2-metas" / "metas.md", cfg)
    return cfg
