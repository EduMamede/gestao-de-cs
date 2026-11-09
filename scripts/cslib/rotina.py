"""A rotina que roda sozinha: lê o export novo, atualiza a nota, monta a semana, reavalia o urgente e refaz a página.

Só script, sem IA: não gasta limite do Claude e nenhum dado sai do computador. O que precisa de conversa, como a
leitura do líder e os rascunhos, fica para quando a pessoa abrir /gestao-de-cs:hoje.

O export continua vindo da pessoa ou do sistema dela: a skill não conecta em banco. Ele chega em
4-dados/entradas/novos, que a trava de privacidade já cobre.
"""

from __future__ import annotations

import datetime as dt
import getpass
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
import unicodedata
from pathlib import Path
from xml.sax.saxutils import escape

from . import ErroDeUso, config as config_mod, plural
from .ciclo import para_a_semana
from .hoje import ARQUIVO as PAGINA, gerar_hoje, preparar
from .medir import rodar
from .pasta import NOVOS, modo_privacidade
from .privacidade import Cofre
from .relatorios import gravar_rodada
from .semana import texto_semana, ultima_rodada

EXTENSOES = {".csv", ".tsv", ".txt", ".xlsx", ".xlsm"}
IDADE_MINIMA = 60  # arquivo mais novo que isso pode estar sendo gravado
DIA_DA_ULTIMA_SEMANA = 3  # na sexta, a semana que vale planejar já é a próxima
HORA_PADRAO = "08:00"


def _caminho_do_registro(pasta: Path) -> Path:
    return pasta / "4-dados" / "rotina.log"


def registrar(pasta: Path, agora: dt.datetime, texto: str) -> None:
    """Só contagens e datas, nunca nome: a IA pode ler este arquivo."""
    caminho = _caminho_do_registro(pasta)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("a", encoding="utf-8") as f:
        f.write(f"{agora.strftime('%Y-%m-%d %H:%M')} | {texto}\n")


def ultimo_registro(pasta: Path) -> str | None:
    caminho = _caminho_do_registro(pasta)
    if not caminho.exists():
        return None
    linhas = [l for l in caminho.read_text(encoding="utf-8").splitlines() if l.strip()]
    return linhas[-1] if linhas else None


def mover_novos(pasta: Path, hoje: dt.date) -> tuple:
    """Guarda o que chegou em entradas/<hoje>. Devolve (movidos, esperando). Nada é apagado nem sobrescrito."""
    base = pasta / "4-dados" / "entradas"
    novos = base / NOVOS
    novos.mkdir(parents=True, exist_ok=True)
    arquivos = [f for f in sorted(novos.iterdir()) if f.is_file() and f.suffix.casefold() in EXTENSOES and not f.name.startswith(("~$", "."))]
    if not arquivos:
        return 0, 0
    if (pasta / "4-dados" / "rodadas" / hoje.isoformat()).exists():
        return 0, len(arquivos)  # já houve rodada hoje: o arquivo fica para a próxima vez
    destino = base / hoje.isoformat()
    movidos = esperando = 0
    for arquivo in arquivos:
        alvo = destino / arquivo.name
        if alvo.exists() or time.time() - arquivo.stat().st_mtime < IDADE_MINIMA:
            esperando += 1
            continue
        destino.mkdir(parents=True, exist_ok=True)
        try:
            arquivo.rename(alvo)
            movidos += 1
        except OSError:  # outro programa ainda está gravando
            esperando += 1
    return movidos, esperando


def _datas_das_pastas(base: Path) -> list:
    saida = []
    if base.exists():
        for d in base.iterdir():
            try:
                saida.append(dt.date.fromisoformat(d.name))
            except ValueError:
                continue
    return sorted(saida)


def entrada_sem_rodada(pasta: Path):
    """A entrada mais nova, se ela for mais nova que a última rodada. Pega também o que falhou numa vez anterior."""
    entradas = [d for d in _datas_das_pastas(pasta / "4-dados" / "entradas") if any((pasta / "4-dados" / "entradas" / d.isoformat()).iterdir())]
    if not entradas:
        return None
    rodadas = _datas_das_pastas(pasta / "4-dados" / "rodadas")
    return entradas[-1] if not rodadas or entradas[-1] > rodadas[-1] else None


def _fazer_rodada(pasta: Path, data: dt.date) -> dict:
    cfg = config_mod.carregar(pasta)
    if cfg.erros:
        raise ErroDeUso("há problemas nos arquivos do checklist. Rode /gestao-de-cs:analista para corrigir")
    if not cfg.arquivos:
        raise ErroDeUso("as colunas ainda não foram ligadas. Rode /gestao-de-cs:analista")
    r = rodar(pasta, data, pasta / "4-dados" / "entradas" / data.isoformat(), cfg, modo_privacidade(pasta))
    if not r.contas:
        raise ErroDeUso("nenhuma conta foi lida no export. Confira o arquivo ou rode /gestao-de-cs:analista")
    return gravar_rodada(r, pasta, pasta / "4-dados" / "rodadas" / data.isoformat())


def _copia_com_nomes(pasta: Path, relativo: str, texto: str) -> None:
    if modo_privacidade(pasta) == "protegido":
        destino = pasta / "com-nomes" / Path(relativo).name
        destino.parent.mkdir(exist_ok=True)
        destino.write_text(Cofre(pasta).restaurar(texto), encoding="utf-8")


def _montar_semana(pasta: Path, hoje: dt.date, nome_de):
    """Monta a semana na primeira vez que a rotina roda nela. Segunda desligado? Monta na terça."""
    if hoje.weekday() > DIA_DA_ULTIMA_SEMANA:
        return None
    segunda = hoje - dt.timedelta(days=hoje.weekday())
    caminho = pasta / "2-metas" / f"semana-{segunda.isoformat()}.md"
    if caminho.exists():
        return None
    _, resumo = ultima_rodada(pasta)
    texto = texto_semana(segunda, resumo, hoje, para_a_semana(pasta, hoje, nome_de))
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(texto, encoding="utf-8")
    _copia_com_nomes(pasta, caminho.name, texto)
    return caminho


def executar(pasta: Path, hoje: dt.date, nome_de) -> dict:
    agora = dt.datetime.combine(hoje, dt.datetime.now().time())
    saida = {"movidos": 0, "esperando": 0, "rodada": None, "erro_da_rodada": None, "avisos_da_rodada": [], "semana": None, "preparados": [], "urgentes": {"entraram": [], "ficaram": 0}, "pagina": None, "sem_rodada": False}
    saida["movidos"], saida["esperando"] = mover_novos(pasta, hoje)
    topo = []

    data_entrada = entrada_sem_rodada(pasta)
    if data_entrada:
        try:
            resumo = _fazer_rodada(pasta, data_entrada)
            saida["rodada"] = data_entrada.isoformat()
            saida["avisos_da_rodada"] = resumo["avisos_sobre_os_dados"]
        except ErroDeUso as erro:
            saida["erro_da_rodada"] = str(erro)
            topo.append(f"O export de {data_entrada.strftime('%d/%m/%Y')} não rodou: {erro}. Os números abaixo são da rodada anterior.")
    if saida["esperando"]:
        topo.append(f"{plural(saida['esperando'], 'arquivo ficou', 'arquivos ficaram')} em entradas/novos para a próxima vez: já houve rodada hoje, o nome se repete ou ainda estava sendo gravado.")

    try:
        semana = _montar_semana(pasta, hoje, nome_de)
        if semana:
            saida["semana"] = semana.relative_to(pasta).as_posix()
            saida["preparados"] = preparar(pasta, hoje)
        texto, _, _, saida["urgentes"] = gerar_hoje(pasta, hoje, nome_de, topo)
    except ErroDeUso:  # ainda não há rodada
        saida["sem_rodada"] = True
        texto = "\n".join(
            [f"# Hoje, {hoje.strftime('%d/%m/%Y')}", "", *[f"> {t}" for t in topo], "", "Ainda não há rodada, então não dá para dizer como as contas estão.", "", "Deixe o export em `4-dados/entradas/novos` ou rode `/gestao-de-cs:analista`.", ""]
        )
        (pasta / PAGINA).write_text(texto, encoding="utf-8")
    _copia_com_nomes(pasta, PAGINA, texto)
    saida["pagina"] = texto

    partes = [f"export: {saida['movidos']} arquivos", f"esperando: {saida['esperando']}"]
    partes.append(f"rodada: {saida['rodada'] or ('erro' if saida['erro_da_rodada'] else 'sem novidade')}")
    partes.append(f"semana: {'criada' if saida['semana'] else 'sem mudança'}")
    partes.append(f"preparados: {len(saida['preparados'])}")
    partes.append(f"urgentes: {len(saida['urgentes']['entraram'])}, de fora: {saida['urgentes']['ficaram']}")
    registrar(pasta, agora, "; ".join(partes))
    return saida


def texto_da_rotina(s: dict, hoje: dt.date) -> str:
    linhas = [f"Rotina de {hoje.strftime('%d/%m/%Y')}."]
    if s["rodada"]:
        chegaram = f" ({plural(s['movidos'], 'arquivo', 'arquivos')})" if s["movidos"] else ""
        linhas.append(f"Export novo{chegaram}: o health score foi atualizado na rodada de {dt.date.fromisoformat(s['rodada']).strftime('%d/%m/%Y')}.")
    elif s["erro_da_rodada"]:
        linhas.append(f"O export não rodou: {s['erro_da_rodada']}.")
    else:
        linhas.append("Sem export novo: o health score não mudou.")
    linhas += [f"Aviso sobre os dados: {a}" for a in s["avisos_da_rodada"][:5]]
    if s["semana"]:
        linhas.append(f"Semana criada em {s['semana']}. A leitura do líder fica em branco até a pessoa abrir /gestao-de-cs:hoje.")
    if s["preparados"]:
        linhas.append(f"Preparados: {plural(len(s['preparados']), 'arquivo', 'arquivos')}, só com os fatos da rodada.")
    linhas.append(f"Urgentes novos na fila: {len(s['urgentes']['entraram'])}.")
    return "\n".join(linhas) + "\n\n" + s["pagina"]


def registrar_falha(pasta: Path, hoje: dt.date, erro: Exception) -> None:
    """A rotina roda sem ninguém olhando. Se falhar, a pessoa precisa saber ao abrir a página, sem expor dado."""
    ultimo = traceback.extract_tb(erro.__traceback__)[-1]
    registrar(pasta, dt.datetime.combine(hoje, dt.datetime.now().time()), f"ERRO: {type(erro).__name__} em {Path(ultimo.filename).name}, linha {ultimo.lineno}")
    pagina = pasta / PAGINA
    anterior = pagina.read_text(encoding="utf-8") if pagina.exists() else ""
    pagina.write_text(f"> A rotina de {hoje.strftime('%d/%m/%Y')} não terminou. O que está abaixo pode estar desatualizado. Veja 4-dados/rotina.log.\n\n{anterior}", encoding="utf-8")


# ---------------------------------------------------------------- agendamento


def nome_da_tarefa(pasta: Path) -> str:
    sem_acento = unicodedata.normalize("NFKD", pasta.name).encode("ascii", "ignore").decode()
    apelido = re.sub(r"[^A-Za-z0-9]+", "-", sem_acento).strip("-")[:40] or "empresa"
    return f"gestao-de-cs-{apelido}-{hashlib.sha1(str(pasta).casefold().encode()).hexdigest()[:6]}"


def _python_sem_janela() -> str:
    """No Windows, pythonw não abre aquela janela preta às 8h da manhã."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return str(pythonw) if pythonw.exists() else sys.executable


def xml_da_tarefa(pasta: Path, hora: str, python: str, cs: Path, usuario: str, inicio: dt.date) -> str:
    argumentos = f'"{cs}" rotina --pasta "{pasta}"'
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Rotina da skill gestao-de-cs. Só script, sem IA. Para remover: cs.py agendar --remover.</Description></RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{inicio.isoformat()}T{hora}:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByWeek>
        <WeeksInterval>1</WeeksInterval>
        <DaysOfWeek><Monday /><Tuesday /><Wednesday /><Thursday /><Friday /></DaysOfWeek>
      </ScheduleByWeek>
    </CalendarTrigger>
  </Triggers>
  <Principals><Principal id="Author"><UserId>{escape(usuario)}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author"><Exec><Command>{escape(python)}</Command><Arguments>{escape(argumentos)}</Arguments><WorkingDirectory>{escape(str(pasta))}</WorkingDirectory></Exec></Actions>
</Task>
"""


def _schtasks(*args) -> tuple:
    processo = subprocess.run(["schtasks", *args], capture_output=True, text=True, errors="replace")
    return processo.returncode, (processo.stdout + processo.stderr).strip()


def _conferir_hora(hora: str) -> str:
    achado = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", hora or "")
    if not achado:
        raise ErroDeUso("use a hora no formato HH:MM, como 08:00.")
    return hora


def agendar(pasta: Path, hora: str, cs: Path, hoje: dt.date) -> str:
    hora = _conferir_hora(hora)
    if os.name != "nt":
        h, m = hora.split(":")
        return (
            "Neste sistema, a skill não agenda sozinha. Ainda não foi testado fora do Windows.\n"
            "Para rodar de segunda a sexta, abra `crontab -e` e acrescente esta linha:\n"
            f'{int(m)} {int(h)} * * 1-5 "{sys.executable}" "{cs}" rotina --pasta "{pasta}"\n'
            "Com o computador desligado na hora, o cron não roda depois."
        )
    usuario = f"{os.environ.get('USERDOMAIN', '')}\\{getpass.getuser()}".lstrip("\\")
    nome = nome_da_tarefa(pasta)
    with tempfile.TemporaryDirectory(prefix="csagenda-") as tmp:
        arquivo = Path(tmp) / "tarefa.xml"
        arquivo.write_text(xml_da_tarefa(pasta, hora, _python_sem_janela(), cs, usuario, hoje), encoding="utf-16")
        codigo, saida = _schtasks("/Create", "/TN", nome, "/XML", str(arquivo), "/F")
    if codigo != 0:
        raise ErroDeUso(f"o Windows não aceitou a tarefa: {saida}")
    return (
        f"Rotina agendada: de segunda a sexta, às {hora}. Nome da tarefa: {nome}.\n"
        "Com o computador desligado na hora, ela roda quando ele ligar. Não usa IA nem gasta o limite do Claude.\n"
        "Se a skill mudar de lugar no computador, rode agendar de novo."
    )


def remover_agendamento(pasta: Path) -> str:
    if os.name != "nt":
        return "Neste sistema, a linha fica no cron. Para remover, abra `crontab -e` e apague a linha."
    nome = nome_da_tarefa(pasta)
    codigo, _ = _schtasks("/Delete", "/TN", nome, "/F")
    return f"Rotina removida: {nome}." if codigo == 0 else "Não há rotina agendada para esta pasta."


def ver_agendamento(pasta: Path) -> str:
    ultimo = ultimo_registro(pasta)
    linhas = []
    if os.name == "nt":
        nome = nome_da_tarefa(pasta)
        codigo, _ = _schtasks("/Query", "/TN", nome)
        linhas.append(f"Rotina agendada: {nome}." if codigo == 0 else "Não há rotina agendada para esta pasta.")
    else:
        linhas.append("Neste sistema, confira com `crontab -l`.")
    linhas.append(f"Última vez: {ultimo}." if ultimo else "A rotina ainda não rodou nesta pasta.")
    return "\n".join(linhas)
