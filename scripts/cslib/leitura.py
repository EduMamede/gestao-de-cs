"""Lê exports CSV e XLSX e entende números e datas do jeito que vêm na vida real.

O perfil das colunas (perfil_tabela) nunca devolve valores no modo protegido: só
nome da coluna, tipo, preenchimento e contagens.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
import statistics
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

VAZIOS = {
    "", "-", "--", "---", "—", "–", "n/a", "na", "n.a.", "nd", "n/d", "null", "none",
    "nan", "#n/a", "sem dado", "sem dados", "s/d", "#ref!", "#value!", "#valor!", "?",
}
CODIFICACOES = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
SEPARADORES = (";", ",", "\t", "|")
SUFIXOS_EMPRESA = {"ltda", "me", "epp", "eireli", "sa", "mei", "ss"}
LINHAS_DE_TOTAL = {"total", "total geral", "totais", "subtotal", "soma", "soma total"}
DICAS_TEXTO_LIVRE = (
    "obs", "observ", "comentario", "anotac", "descri", "historico", "nota livre",
    "notas", "detalhe", "assunto", "mensagem", "resumo", "relato", "proximo passo", "proxima acao",
)
DICAS_PESSOA = ("patrocinador", "sponsor", "decisor", "usuario chave", "key user", "contato", "gerente", "nome do")
DICAS_DATA = ("data", "dt ", "dt", "venc", "inicio", "renov", "ultim", "cancel", "entrada", "desde", "em")
MESES = {
    "jan": 1, "fev": 2, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "mai": 5, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "aug": 8, "set": 9, "sep": 9, "out": 10, "oct": 10, "nov": 11, "dez": 12, "dec": 12,
}
RE_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
RE_TELEFONE = re.compile(r"^\+?[\d\s().-]{10,18}$")
RE_DOCUMENTO = re.compile(r"^\d{3}\.?\d{3}\.?\d{3}-?\d{2}$|^\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}$")


@dataclass
class Tabela:
    arquivo: str
    colunas: list[str]
    linhas: list[list]
    codificacao: str = ""
    separador: str = ""
    linhas_ignoradas: int = 0
    abas: list[str] = field(default_factory=list)


def eh_vazio(valor) -> bool:
    if valor is None:
        return True
    if isinstance(valor, str):
        return valor.strip().casefold() in VAZIOS
    return False


def normalizar(texto) -> str:
    """Sem acento, sem pontuação, minúsculo e com espaços simples."""
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^0-9a-zA-Z]+", " ", texto).strip().casefold()


def normalizar_nome_conta(texto) -> str:
    """Trata 'CLÍNICA BETA LTDA' e 'Clinica Beta' como a mesma conta."""
    partes = normalizar(texto).split()
    if len(partes) >= 3 and partes[-2:] == ["s", "a"]:
        partes = partes[:-2]
    while len(partes) > 1 and partes[-1] in SUFIXOS_EMPRESA:
        partes = partes[:-1]
    return " ".join(partes)


def normalizar_id(texto) -> str:
    if isinstance(texto, float) and texto.is_integer():
        texto = int(texto)
    return re.sub(r"\s", "", normalizar(texto))


def eh_linha_de_total(*valores) -> bool:
    return any(not eh_vazio(v) and normalizar(v) in LINHAS_DE_TOTAL for v in valores)


# ---------------------------------------------------------------- números


def _limpar_numero(texto: str) -> str:
    return re.sub(r"(?i)r\$|brl|us\$|\$|%|\s| ", "", texto)


def inferir_formato_numero(valores) -> str:
    """'br' para 1.234,56 e 'en' para 1,234.56. Sem pista nenhuma, assume 'br'."""
    br = en = 0
    for valor in valores:
        if not isinstance(valor, str):
            continue
        t = _limpar_numero(valor).lstrip("(-").rstrip(")")
        if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?|\d+,\d{1,2}", t):
            br += 1
        elif re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?|\d+\.\d{1,2}", t):
            en += 1
    return "en" if en > br else "br"


def parse_numero(valor, formato: str = "br"):
    if eh_vazio(valor) or isinstance(valor, (bool, dt.date, dt.datetime)):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    t = str(valor).strip()
    negativo = False
    if t.startswith("(") and t.endswith(")"):
        negativo = True
        t = t[1:-1]
    t = _limpar_numero(t)
    if t.startswith("-"):
        negativo = True
        t = t[1:]
    elif t.endswith("-"):
        negativo = True
        t = t[:-1]
    if not re.fullmatch(r"[\d.,]*\d[\d.,]*", t):
        return None
    tem_ponto, tem_virgula = "." in t, "," in t
    if tem_ponto and tem_virgula:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif tem_virgula:
        partes = t.split(",")
        if len(partes) > 2 or (formato == "en" and len(partes[-1]) == 3):
            t = t.replace(",", "")
        else:
            t = t.replace(",", ".")
    elif tem_ponto:
        partes = t.split(".")
        if len(partes) > 2 or (formato == "br" and len(partes[-1]) == 3):
            t = t.replace(".", "")
    try:
        numero = float(t)
    except ValueError:
        return None
    return -numero if negativo else numero


# ---------------------------------------------------------------- datas


def _data_valida(ano, mes, dia):
    try:
        return dt.date(ano, mes, dia)
    except ValueError:
        return None


def _serial_excel(numero):
    if 20000 <= numero <= 80000:
        return dt.date(1899, 12, 30) + dt.timedelta(days=int(numero))
    return None


def inferir_ordem_data(valores) -> str:
    """'dmy' é o padrão brasileiro. Só vira 'mdy' se a coluna não deixar dúvida."""
    dmy = mdy = 0
    for valor in valores:
        if not isinstance(valor, str):
            continue
        m = re.match(r"\s*(\d{1,2})[-/.](\d{1,2})[-/.]\d{2,4}", valor)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > 12:
                dmy += 1
            elif b > 12:
                mdy += 1
    return "mdy" if mdy > 0 and dmy == 0 else "dmy"


def parse_data(valor, ordem: str = "dmy", aceita_serial: bool = True):
    if eh_vazio(valor) or isinstance(valor, bool):
        return None
    if isinstance(valor, dt.datetime):
        return valor.date()
    if isinstance(valor, dt.date):
        return valor
    if isinstance(valor, (int, float)):
        return _serial_excel(valor) if aceita_serial else None
    t = str(valor).strip().casefold()
    if aceita_serial and re.fullmatch(r"\d{5}([.,]0+)?", t):
        return _serial_excel(int(t[:5]))
    m = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", t)
    if m:
        return _data_valida(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", t)
    if m:
        a, b, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
        ano = ano + 2000 if ano < 100 else ano
        dia, mes = (a, b) if ordem == "dmy" else (b, a)
        if mes > 12:
            dia, mes = mes, dia
        return _data_valida(ano, mes, dia)
    m = re.match(r"(\d{1,2})[\s/-]+(?:de\s+)?([a-zç]{3,})\.?[\s/-]+(?:de\s+)?(\d{2,4})", t)
    if m and m.group(2)[:3] in MESES:
        ano = int(m.group(3))
        return _data_valida(ano + 2000 if ano < 100 else ano, MESES[m.group(2)[:3]], int(m.group(1)))
    m = re.fullmatch(r"([a-zç]{3,})\.?[\s/-]+(?:de\s+)?(\d{2,4})", t)
    if m and m.group(1)[:3] in MESES:
        ano = int(m.group(2))
        return _data_valida(ano + 2000 if ano < 100 else ano, MESES[m.group(1)[:3]], 1)
    return None


# ---------------------------------------------------------------- arquivos


def _decodificar(bruto: bytes):
    for codificacao in CODIFICACOES:
        try:
            return bruto.decode(codificacao), codificacao
        except UnicodeDecodeError:
            continue
    return bruto.decode("latin-1", errors="replace"), "latin-1"


def _achar_separador(texto: str) -> str:
    amostra = [l for l in texto.splitlines() if l.strip()][:40]
    melhor, melhor_nota = ";", (-1.0, 0)
    for separador in SEPARADORES:
        contagens = [len(l) for l in csv.reader(amostra, delimiter=separador)]
        contagens = [c for c in contagens if c > 0]
        if not contagens:
            continue
        moda = statistics.mode(contagens)
        if moda < 2:
            continue
        nota = (round(contagens.count(moda) / len(contagens), 1), moda)
        if nota > melhor_nota:
            melhor, melhor_nota = separador, nota
    return melhor


def _achar_cabecalho(linhas: list[list]) -> int:
    """Pula linhas de título: o cabeçalho é a primeira linha cheia e sem números soltos."""
    larguras = [sum(1 for c in l if not eh_vazio(c)) for l in linhas[:60]]
    largura = max(larguras) if larguras else 0
    for i, linha in enumerate(linhas[:20]):
        cheias = [c for c in linha if not eh_vazio(c)]
        if len(cheias) < max(2, 0.6 * largura):
            continue
        numericas = sum(1 for c in cheias if parse_numero(c) is not None or parse_data(c) is not None)
        if numericas <= 0.3 * len(cheias):
            return i
    return 0


def _montar(arquivo: str, linhas: list[list], **extras) -> Tabela:
    if not linhas:
        return Tabela(arquivo=arquivo, colunas=[], linhas=[], **extras)
    inicio = _achar_cabecalho(linhas)
    cabecalho = ["" if c is None else str(c).strip() for c in linhas[inicio]]
    while cabecalho and not cabecalho[-1]:
        cabecalho.pop()
    colunas: list[str] = []
    for i, nome in enumerate(cabecalho):
        nome = re.sub(r"\s+", " ", nome) or f"coluna_{i + 1}"
        repetidas = sum(1 for c in colunas if normalizar(c) == normalizar(nome))
        colunas.append(f"{nome} ({repetidas + 1})" if repetidas else nome)
    corpo, ignoradas = [], inicio
    for linha in linhas[inicio + 1:]:
        linha = list(linha[: len(colunas)]) + [None] * (len(colunas) - len(linha))
        if all(eh_vazio(c) for c in linha):
            ignoradas += 1
            continue
        corpo.append(linha)
    return Tabela(arquivo=arquivo, colunas=colunas, linhas=corpo, linhas_ignoradas=ignoradas, **extras)


def _ler_csv(caminho: Path) -> Tabela:
    texto, codificacao = _decodificar(caminho.read_bytes())
    separador = _achar_separador(texto)
    linhas = [l for l in csv.reader(io.StringIO(texto), delimiter=separador)]
    return _montar(caminho.name, linhas, codificacao=codificacao, separador=separador)


def _ler_xlsx(caminho: Path, aba=None) -> Tabela:
    try:
        import openpyxl
    except ImportError as erro:
        raise ImportError("openpyxl") from erro
    livro = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    try:
        nomes = livro.sheetnames
        escolhida = None
        if aba and aba in nomes:
            escolhida = aba
        else:
            for nome in nomes:
                if livro[nome].sheet_state == "visible":
                    escolhida = nome
                    break
        linhas = [list(l) for l in livro[escolhida or nomes[0]].iter_rows(values_only=True)]
    finally:
        livro.close()
    while linhas and all(eh_vazio(c) for c in linhas[-1]):
        linhas.pop()
    return _montar(caminho.name, linhas, abas=nomes)


def ler_tabela(caminho, aba=None) -> Tabela:
    caminho = Path(caminho)
    extensao = caminho.suffix.lower()
    if extensao in (".xlsx", ".xlsm"):
        return _ler_xlsx(caminho, aba)
    if extensao in (".csv", ".txt", ".tsv"):
        return _ler_csv(caminho)
    raise ValueError(f"formato não suportado: {extensao}. Exporte em CSV ou XLSX.")


# ---------------------------------------------------------------- perfil sem valores


def perfil_coluna(nome: str, valores: list) -> dict:
    cheios = [v for v in valores if not eh_vazio(v)]
    total = len(valores)
    perfil = {
        "coluna": nome,
        "tipo": "vazia",
        "preenchimento_pct": round(100 * len(cheios) / total) if total else 0,
        "distintos": 0,
        "dado_pessoal": None,
        "bloqueada": False,
    }
    if not cheios:
        return perfil
    textos = [str(v).strip() for v in cheios]
    distintos = len({normalizar(t) for t in textos})
    tamanho = sum(len(t) for t in textos) / len(textos)
    perfil["distintos"] = distintos
    nome_norm = normalizar(nome)

    emails = sum(1 for t in textos if RE_EMAIL.search(t))
    documentos = sum(1 for t in textos if RE_DOCUMENTO.fullmatch(t))
    telefones = sum(1 for t in textos if RE_TELEFONE.fullmatch(t) and not RE_DOCUMENTO.fullmatch(t))
    if emails / len(textos) >= 0.5:
        perfil["dado_pessoal"] = "e-mail"
    elif documentos / len(textos) >= 0.5:
        perfil["dado_pessoal"] = "documento (CPF ou CNPJ)"
    elif telefones / len(textos) >= 0.5 and any(p in nome_norm for p in ("tel", "cel", "fone", "whats", "contato")):
        perfil["dado_pessoal"] = "telefone"

    parece_data_pelo_nome = any(d in nome_norm for d in DICAS_DATA)
    ordem = inferir_ordem_data(cheios)
    datas = sum(1 for v in cheios if parse_data(v, ordem, aceita_serial=parece_data_pelo_nome) is not None)
    formato = inferir_formato_numero(cheios)
    numeros = sum(1 for v in cheios if parse_numero(v, formato) is not None)
    if datas / len(cheios) >= 0.7:
        perfil["tipo"] = "data"
        perfil["sem_leitura"] = len(cheios) - datas
    elif numeros / len(cheios) >= 0.7:
        perfil["tipo"] = "numero"
        perfil["sem_leitura"] = len(cheios) - numeros
    elif any(d in nome_norm for d in DICAS_TEXTO_LIVRE) or tamanho >= 40:
        perfil["tipo"] = "texto-livre"
        perfil["bloqueada"] = True
    elif distintos <= 15 and distintos <= max(3, 0.5 * len(cheios)):
        perfil["tipo"] = "categoria"
    else:
        perfil["tipo"] = "texto"
    if perfil["tipo"] in ("texto", "categoria") and not perfil["dado_pessoal"] and any(p in nome_norm for p in DICAS_PESSOA):
        perfil["dado_pessoal"] = "pode ter nome de pessoa"
    return perfil


def perfil_tabela(tabela: Tabela) -> dict:
    colunas = []
    for i, nome in enumerate(tabela.colunas):
        colunas.append(perfil_coluna(nome, [l[i] for l in tabela.linhas]))
    return {
        "arquivo": tabela.arquivo,
        "linhas": len(tabela.linhas),
        "linhas_ignoradas": tabela.linhas_ignoradas,
        "codificacao": tabela.codificacao or "planilha",
        "separador": {"\t": "tab"}.get(tabela.separador, tabela.separador) or "planilha",
        "colunas": colunas,
    }


def exemplos_da_coluna(valores: list, quantos: int = 3) -> list[str]:
    """Só para o modo aberto: amostra curta para ajudar a ligar as colunas."""
    vistos, saida = set(), []
    for valor in valores:
        if eh_vazio(valor):
            continue
        texto = str(valor).strip()
        if texto not in vistos:
            vistos.add(texto)
            saida.append(texto[:40])
        if len(saida) == quantos:
            break
    return saida
