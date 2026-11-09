"""Biblioteca do gestao-de-cs: lê exports, mede rotinas e gera os arquivos da rodada."""

VERSAO = "0.1.0"


def plural(n: int, singular: str, varios: str) -> str:
    """'1 conta parada' e '3 contas paradas', sem o feio 'conta(s)'."""
    return f"{n} {singular if n == 1 else varios}"


class ErroDeUso(Exception):
    """Erro que a pessoa consegue resolver. A mensagem nunca traz valores dos dados."""
