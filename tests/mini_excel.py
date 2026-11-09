"""Um avaliador pequeno das fórmulas que a planilha usa.

Não substitui o Excel. Serve para pegar o erro mais provável aqui: uma fórmula apontando para
a célula errada, ou o valor gravado discordando da fórmula.
"""

from __future__ import annotations

import decimal
import re

TOKEN = re.compile(
    r"""\s*(?:
    (?P<num>\d+(?:\.\d+)?)
  | (?P<str>"(?:[^"]|"")*")
  | (?P<ref>(?:'[^']+'!|[A-Za-z_]+!)?\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?)
  | (?P<func>[A-Z][A-Z0-9.]*)\(
  | (?P<op><=|>=|<>|[-+*/=<>(),])
    )""",
    re.VERBOSE,
)


def _tokens(texto: str) -> list:
    pos, saida = 0, []
    while pos < len(texto):
        m = TOKEN.match(texto, pos)
        if not m:
            if texto[pos:].strip() == "":
                break
            raise ValueError(f"não entendi a fórmula em: {texto[pos:pos + 20]}")
        pos = m.end()
        saida.append((m.lastgroup, m.group(m.lastgroup)))
    return saida


def _col(nome: str) -> int:
    n = 0
    for c in nome:
        n = n * 26 + ord(c) - 64
    return n


def _letra(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


class Avaliador:
    def __init__(self, livro_formulas, livro_valores=None, trocas=None):
        self.livro = livro_formulas
        self.memo = {}
        self.trocas = trocas or {}

    def celula(self, aba: str, ref: str):
        chave = (aba, ref)
        if chave in self.trocas:
            return self.trocas[chave]
        if chave in self.memo:
            return self.memo[chave]
        valor = self.livro[aba][ref].value
        if isinstance(valor, str) and valor.startswith("="):
            valor = self.avaliar(valor[1:], aba)
        self.memo[chave] = valor
        return valor

    def avaliar(self, formula: str, aba: str):
        self.toks = getattr(self, "toks", None)
        return _Parser(_tokens(formula), self, aba).expr()


class _Parser:
    def __init__(self, toks, av: Avaliador, aba: str):
        self.toks, self.av, self.aba, self.i = toks, av, aba, 0

    def _ver(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def _come(self, valor=None):
        t = self._ver()
        if valor is not None and t[1] != valor:
            raise ValueError(f"esperava {valor}, veio {t}")
        self.i += 1
        return t

    def expr(self):
        esq = self._soma()
        while self._ver()[1] in ("=", "<>", "<", ">", "<=", ">="):
            op = self._come()[1]
            dir_ = self._soma()
            esq = _comparar(esq, op, dir_)
        return esq

    def _soma(self):
        esq = self._mult()
        while self._ver()[1] in ("+", "-"):
            op = self._come()[1]
            dir_ = self._mult()
            esq = (esq or 0) + (dir_ or 0) if op == "+" else (esq or 0) - (dir_ or 0)
        return esq

    def _mult(self):
        esq = self._unario()
        while self._ver()[1] in ("*", "/"):
            op = self._come()[1]
            dir_ = self._unario()
            esq = esq * dir_ if op == "*" else esq / dir_
        return esq

    def _unario(self):
        if self._ver()[1] == "-":
            self._come()
            valor = self._unario()
            if isinstance(valor, list):
                return [[-(1 if c is True else 0 if c is False else (c or 0)) for c in l] for l in valor]
            return -(valor or 0)
        return self._primario()

    def _primario(self):
        tipo, valor = self._come()
        if tipo == "num":
            return float(valor)
        if tipo == "str":
            return valor[1:-1].replace('""', '"')
        if tipo == "ref":
            return self._referencia(valor)
        if tipo == "func":
            argumentos = []
            if self._ver()[1] != ")":
                argumentos.append(self._lazy_arg())
                while self._ver()[1] == ",":
                    self._come()
                    argumentos.append(self._lazy_arg())
            self._come(")")
            return _FUNCS[valor](*argumentos)
        if valor == "(":
            r = self.expr()
            self._come(")")
            return r
        raise ValueError(f"token inesperado {tipo} {valor}")

    def _lazy_arg(self):
        return self.expr()

    def _referencia(self, texto: str):
        aba = self.aba
        if "!" in texto:
            aba, texto = texto.rsplit("!", 1)
            aba = aba.strip("'")
        texto = texto.replace("$", "")
        if ":" not in texto:
            return self.av.celula(aba, texto)
        a, b = texto.split(":")
        ma, mb = re.match(r"([A-Z]+)(\d+)", a), re.match(r"([A-Z]+)(\d+)", b)
        return [
            [self.av.celula(aba, f"{_letra(c)}{l}") for c in range(_col(ma.group(1)), _col(mb.group(1)) + 1)]
            for l in range(int(ma.group(2)), int(mb.group(2)) + 1)
        ]


def _comparar(a, op, b):
    a = "" if a is None else a
    b = "" if b is None else b
    if isinstance(a, str) != isinstance(b, str):
        # no Excel, texto é sempre maior que número
        if op == "=":
            return False
        if op == "<>":
            return True
        return (isinstance(b, str) and op in ("<", "<=")) or (isinstance(a, str) and op in (">", ">="))
    return {"=": a == b, "<>": a != b, "<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[op]


def _plano(v):
    if isinstance(v, list):
        return [c for l in v for c in (l if isinstance(l, list) else [l])]
    return [v]


def _eh_numero(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _sumproduct(*listas):
    planas = [_plano(l) for l in listas]
    total = 0.0
    for tupla in zip(*planas):
        produto = 1.0
        for v in tupla:
            produto *= v if _eh_numero(v) else 0
        total += produto
    return total


def _arred(v, casas):
    q = decimal.Decimal(1).scaleb(-int(casas))
    return float(decimal.Decimal(str(v)).quantize(q, rounding=decimal.ROUND_HALF_UP))


def _isnumber(v):
    if isinstance(v, list):
        return [[_eh_numero(c) for c in l] for l in v]
    return _eh_numero(v)


_FUNCS = {
    "IF": lambda c, a, b=False: a if c else b,
    "OR": lambda *a: any(a),
    "ROUND": _arred,
    "SUM": lambda *a: sum(v for l in a for v in _plano(l) if _eh_numero(v)),
    "SUMPRODUCT": _sumproduct,
    "ISNUMBER": _isnumber,
    "COUNTIF": lambda r, x: sum(1 for v in _plano(r) if v == x),
    "SUMIF": lambda r, x, s: sum(b for a, b in zip(_plano(r), _plano(s)) if a == x and _eh_numero(b)),
}
