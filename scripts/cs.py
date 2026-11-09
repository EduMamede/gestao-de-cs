#!/usr/bin/env python
"""Linha de comando do gestao-de-cs. Tudo que este programa imprime é o que a IA lê.

Por isso, no modo protegido, a saída nunca traz nome de cliente, rótulo nem valor de célula.
Veja referencias/privacidade.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cslib import ErroDeUso, VERSAO, plural  # noqa: E402
from cslib import config as config_mod  # noqa: E402
from cslib import pasta as pasta_mod  # noqa: E402
from cslib.leitura import exemplos_da_coluna, ler_tabela, perfil_tabela  # noqa: E402
from cslib.privacidade import Cofre, Rotulos  # noqa: E402


def _data(texto) -> dt.date:
    if not texto:
        return dt.date.today()
    try:
        return dt.date.fromisoformat(texto)
    except ValueError as erro:
        raise ErroDeUso("use a data no formato AAAA-MM-DD.") from erro


def _nome_simples(texto: str) -> str:
    if re.search(r"[\\/]", texto) or texto.strip(". ") == "":
        raise ErroDeUso("use só o nome, sem caminho.")
    return texto


def _arquivo_de_trabalho(pasta: Path, texto: str) -> Path:
    """Só um .md da pasta da empresa, fora do que a IA não pode ler: o resultado desses comandos vai para ela."""
    caminho = Path(texto)
    if not caminho.is_absolute():
        caminho = pasta / caminho
    caminho = caminho.resolve()
    partes = tuple(p.casefold() for p in caminho.relative_to(pasta).parts) if caminho.is_relative_to(pasta) else ()
    if not partes or caminho.suffix.casefold() != ".md" or partes[0] == "com-nomes" or partes[:2] in (("4-dados", "entradas"), ("4-dados", ".privado")):
        raise ErroDeUso("use um arquivo .md da pasta da empresa, fora de com-nomes/, 4-dados/entradas/ e 4-dados/.privado/.")
    if not caminho.is_file():
        raise ErroDeUso("não achei esse arquivo.")
    return caminho


def _nomeador(pasta: Path):
    """No modo aberto, código e nome. No protegido, só o código: tudo que este programa imprime a IA lê."""
    if pasta_mod.modo_privacidade(pasta) != "aberto":
        return lambda codigo: codigo
    cofre = Cofre(pasta)
    return lambda codigo: f"{codigo} · {cofre.nome_de(codigo)}"


def _copia_com_nomes(pasta: Path, nome: str, texto: str) -> None:
    destino = pasta / "com-nomes" / nome
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(Cofre(pasta).restaurar(texto), encoding="utf-8")


def _pasta_entrada(pasta: Path, data_txt) -> Path:
    base = pasta / "4-dados" / "entradas"
    if data_txt:
        entrada = base / _nome_simples(data_txt)
        if not entrada.exists():
            raise ErroDeUso(f"não achei 4-dados/entradas/{data_txt}.")
        return entrada
    candidatas = sorted(d for d in base.iterdir() if d.is_dir() and d.name != pasta_mod.NOVOS) if base.exists() else []
    if not candidatas:
        raise ErroDeUso("não há arquivos em 4-dados/entradas. Use o comando receber ou coloque o export em uma pasta com a data (AAAA-MM-DD).")
    return candidatas[-1]


# ---------------------------------------------------------------- comandos


def cmd_criar_pasta(args) -> int:
    destino, criados = pasta_mod.criar_pasta(args.destino, args.empresa, args.modo)
    print(f"Pasta da empresa pronta em: {destino}")
    print(f"Arquivos criados: {len(criados)}")
    print(f"Modo de privacidade: {pasta_mod.modo_privacidade(destino)}" + ("" if args.modo else " (ainda não escolhido: fica protegido até a pessoa decidir)"))
    print("Próximo passo: conduzir o checklist e registrar as respostas nos arquivos da pasta.")
    return 0


def cmd_privacidade(args) -> int:
    pasta = pasta_mod.exigir_pasta(args.pasta)
    if args.modo:
        pasta_mod.definir_modo(pasta, args.modo)
    print(f"Modo de privacidade: {pasta_mod.modo_privacidade(pasta)}")
    return 0


def cmd_receber(args) -> int:
    pasta = pasta_mod.exigir_pasta(args.pasta)
    data = _data(args.data)
    destino = pasta / "4-dados" / "entradas" / data.isoformat()
    destino.mkdir(parents=True, exist_ok=True)
    origem = Path(args.arquivo)
    if not origem.is_file():
        raise ErroDeUso("não achei esse arquivo. Confira o caminho.")
    alvo = destino / origem.name
    if alvo.exists():
        raise ErroDeUso(f"já existe um arquivo com esse nome em entradas/{data.isoformat()}. Renomeie ou apague antes.")
    shutil.copyfile(origem, alvo)
    print(f"Arquivo guardado em 4-dados/entradas/{data.isoformat()}/{origem.name}")
    if pasta_mod.modo_privacidade(pasta) == "protegido":
        print("O arquivo original continua onde estava. A trava de privacidade não cobre aquele lugar: a pessoa pode apagar ou mover o original, se quiser.")
    return 0


def _imprimir_perfil(tabela, perfil: dict, modo: str) -> None:
    print(f"\nArquivo: {perfil['arquivo']}")
    print(f"Linhas de dados: {perfil['linhas']} | linhas ignoradas: {perfil['linhas_ignoradas']} | texto: {perfil['codificacao']} | separador: {perfil['separador']}")
    print("coluna | tipo | preenchido | distintos | avisos")
    for i, c in enumerate(perfil["colunas"]):
        avisos = []
        if c["bloqueada"]:
            avisos.append("TEXTO LIVRE: bloqueada")
        if c["dado_pessoal"]:
            avisos.append(f"dado pessoal: {c['dado_pessoal']}")
        if c.get("sem_leitura"):
            avisos.append(f"{c['sem_leitura']} sem leitura")
        print(f"{c['coluna']} | {c['tipo']} | {c['preenchimento_pct']}% | {c['distintos']} | {'; '.join(avisos) or '-'}")
        if modo == "aberto" and not c["bloqueada"] and not c["dado_pessoal"]:
            exemplos = exemplos_da_coluna([l[i] for l in tabela.linhas])
            if exemplos:
                print(f"    exemplos: {' / '.join(exemplos)}")


def cmd_colunas(args) -> int:
    if args.arquivo:
        pasta = None
        arquivos = [Path(args.arquivo)]
        modo = "protegido"
    else:
        pasta = pasta_mod.exigir_pasta(args.pasta)
        entrada = _pasta_entrada(pasta, args.entrada)
        arquivos = sorted(f for f in entrada.iterdir() if f.is_file() and f.suffix.lower() in (".csv", ".xlsx", ".xlsm", ".txt", ".tsv"))
        modo = pasta_mod.modo_privacidade(pasta)
        print(f"Pasta de entrada: {entrada.name}")
    if not arquivos:
        raise ErroDeUso("não há CSV nem XLSX nessa pasta.")
    print(f"Modo de privacidade: {modo}")
    for arquivo in arquivos:
        tabela = ler_tabela(arquivo)
        _imprimir_perfil(tabela, perfil_tabela(tabela), modo)
    print("\nCampos padrão (detalhes em referencias/campos-padrao.md): " + ", ".join(config_mod.CAMPOS))
    return 0


def cmd_validar(args) -> int:
    pasta = pasta_mod.exigir_pasta(args.pasta)
    cfg = config_mod.carregar(pasta)
    modo = pasta_mod.ler_marcador(pasta).get("modo_privacidade")
    arquivos_ligados = {a.casefold() for a in cfg.arquivos}
    ligadas = [i for i in cfg.indicadores if i.arquivo and i.arquivo.casefold() in arquivos_ligados]
    print(f"Modo de privacidade: {modo or 'ainda não escolhido (protegido até a pessoa decidir)'}")
    print(f"Rotinas no checklist: {len(cfg.indicadores)} | ligadas a um arquivo: {len(ligadas)}")
    print(f"Etapas da jornada: {len(cfg.etapas)} | com prazo: {sum(1 for e in cfg.etapas if e.prazo is not None)}")
    print(f"Metas: {len(cfg.metas)} | com indicador do catálogo: {sum(1 for m in cfg.metas if _no_catalogo(m.indicador))}")
    print(f"Arquivos ligados em colunas.md: {len(cfg.arquivos)}")
    print(f"Modelo de receita: {cfg.regras['modelo de receita']}")
    entradas = pasta / "4-dados" / "entradas"
    rodadas = pasta / "4-dados" / "rodadas"
    datas_entrada = sorted(d.name for d in entradas.iterdir() if d.is_dir() and d.name != pasta_mod.NOVOS) if entradas.exists() else []
    datas_rodada = sorted(d.name for d in rodadas.iterdir() if d.is_dir()) if rodadas.exists() else []
    print(f"Última entrada: {datas_entrada[-1] if datas_entrada else 'nenhuma'} | última rodada: {datas_rodada[-1] if datas_rodada else 'nenhuma'}")
    pasta_novos = entradas / pasta_mod.NOVOS
    novos = sum(1 for f in pasta_novos.iterdir() if f.is_file()) if pasta_novos.exists() else 0
    if novos:
        print(f"Esperando em entradas/{pasta_mod.NOVOS}: {plural(novos, 'arquivo', 'arquivos')}. O comando rotina guarda e roda.")

    # Erro trava a rodada. Em aberto é o que a pessoa ainda não respondeu: a skill registra e segue.
    em_aberto = list(cfg.pendencias)
    if cfg.indicadores:
        for ind in cfg.indicadores:
            if ind.arquivo and ind.arquivo.casefold() not in arquivos_ligados:
                em_aberto.append(f"como-medir.md, indicador '{ind.id}': ainda aponta para '{ind.arquivo}', que não está em colunas.md. O Analista liga quando o export chegar")
        if not cfg.etapas and not cfg.recompra:
            em_aberto.append("1-empresa/jornada.md: sem etapas. A rodada funciona, mas sem o alerta de conta parada")
        if not cfg.metas:
            em_aberto.append("2-metas/metas.md: sem metas. A rodada funciona, mas o painel não diz o que está atrás")
    for meta in cfg.metas:
        if meta.indicador and not _no_catalogo(meta.indicador):
            em_aberto.append(f"metas.md: o indicador '{meta.indicador}' não está no catálogo")
    for relativo in ("1-empresa/perfil.md", "1-empresa/estrategia.md", "1-empresa/jornada.md", "2-metas/metas.md", "4-dados/como-medir.md", "LEIA-ME.md"):
        caminho = pasta / relativo
        if caminho.exists():
            sem_resposta = caminho.read_text(encoding="utf-8").count("{{")
            if sem_resposta:
                em_aberto.append(f"{relativo}: {plural(sem_resposta, 'campo sem resposta', 'campos sem resposta')}")
    if cfg.erros:
        print("\nPara corrigir (trava a rodada):")
        for erro in cfg.erros:
            print(f"- {erro}")
    if em_aberto:
        print("\nEm aberto (não trava a rodada):")
        for item in em_aberto:
            print(f"- {item}")
    print("\nPróximo passo: " + _proximo_passo(pasta, cfg, modo, datas_entrada, datas_rodada))
    return 1 if cfg.erros else 0


def _no_catalogo(indicador: str) -> bool:
    from cslib.painel import CATALOGO

    return indicador in CATALOGO


def _proximo_passo(pasta, cfg, modo, entradas, rodadas) -> str:
    from cslib.semana import segunda_da_semana

    if not modo:
        return "perguntar à pessoa como ela quer tratar a privacidade dos dados."
    if not cfg.indicadores:
        return "Consultor: conduzir o checklist (dor, rotinas e como medir)."
    if not entradas:
        return "Analista: receber o primeiro export em CSV ou XLSX."
    if not cfg.arquivos:
        return "Analista: ligar as colunas do export aos campos padrão."
    if not rodadas:
        return "Analista: rodar a primeira rodada."
    if not (pasta / "2-metas" / f"semana-{segunda_da_semana(dt.date.fromisoformat(rodadas[-1])).isoformat()}.md").exists():
        return "Líder da rotina: montar a semana."
    return "Analista: na próxima semana, receber um export novo e rodar de novo."


def cmd_rotulos(args) -> int:
    pasta = pasta_mod.exigir_pasta(args.pasta)
    modo = pasta_mod.modo_privacidade(pasta)
    cfg = config_mod.carregar(pasta)
    rotulos = Rotulos(pasta, cfg, zerar_contagem=False)
    if not rotulos.dados:
        print("Ainda não há rótulos. Eles aparecem depois da primeira rodada.")
        return 0
    if modo == "aberto":
        print("campo | rótulo | significa")
        for (campo, _), item in sorted(rotulos.dados.items()):
            print(f"{campo} | {item['rotulo']} | {item['significa'] or 'SEM LIGAÇÃO'}")
    else:
        print("No modo protegido, os rótulos não aparecem aqui: só no que eles viraram.")
        print("campo | rótulos | sem ligação | ligados a (contas)")
        for campo, grupo in rotulos.resumo_sem_rotulos().items():
            ligados = ", ".join(f"{significado} ({contas})" for significado, contas in sorted(grupo["contas"].items())) or "nada"
            print(f"{campo} | {grupo['rotulos']} | {grupo['sem_ligacao']} | {ligados}")
        print("A pessoa confere e completa em 4-dados/.privado/rotulos.csv.")
    return 0


def cmd_rodada(args) -> int:
    from cslib.medir import rodar
    from cslib.relatorios import gravar_rodada, moeda, numero, resumo_das_previsoes, valor_formatado

    pasta = pasta_mod.exigir_pasta(args.pasta)
    data = _data(args.data)
    destino = pasta / "4-dados" / "rodadas" / data.isoformat()
    if destino.exists() and any(destino.iterdir()) and not args.refazer:
        raise ErroDeUso(f"já existe uma rodada de {data.isoformat()}. Para gerar de novo por cima dela, confirme com a pessoa e use --refazer.")
    cfg = config_mod.carregar(pasta)
    if cfg.erros:
        print("Há problemas nos arquivos do checklist:")
        for erro in cfg.erros:
            print(f"- {erro}")
        return 1
    if not cfg.arquivos:
        raise ErroDeUso("colunas.md ainda não liga nenhum arquivo. Ligue as colunas antes da rodada.")
    entrada = _pasta_entrada(pasta, args.entrada)
    modo = pasta_mod.modo_privacidade(pasta)
    r = rodar(pasta, data, entrada, cfg, modo)
    if not r.contas:
        raise ErroDeUso("nenhuma conta foi lida. Confira se a coluna de conta está ligada em colunas.md.")
    resumo = gravar_rodada(r, pasta, destino)

    print(f"Rodada de {data.isoformat()} pronta (modo {modo}).")
    print(f"Contas ativas: {resumo['contas']['ativas']} | canceladas: {resumo['contas']['canceladas']} | com nota: {resumo['contas']['com_nota']} | sem nota: {resumo['contas']['sem_nota']}")
    print(f"Receita ativa: {moeda(r.painel['valores']['receita_ativa'])}")
    print("Faixas: " + ", ".join(f"{k}={v['contas']}" for k, v in resumo["faixas"].items()))
    contas_com_alerta = len({a["conta"] for a in resumo["alertas_de_padrao"]})
    print(f"Empacadas: {len(resumo['empacadas'])} | alertas de padrão: {len(resumo['alertas_de_padrao'])} (em {contas_com_alerta} contas) | sinais bons: {len(resumo['sinais_bons'])} | renovações na janela: {len(resumo['renovacoes'])}")
    if resumo["conta_perdida"]:
        p = resumo["conta_perdida"]
        print(f"Teste da conta perdida: avisaria {p['sim']} ({p['sim_pela_nota']} pela nota, {p['sim_por_alerta']} só pelo alerta), não avisaria {p['nao']}, sem dado {p['sem_dado']}, de {p['total']}.")
    print("\nQuem olhar primeiro (até 5):")
    if not resumo["prioridades"]:
        dados = resumo["dados_disponiveis"]
        print("Nenhuma conta com sinal." if dados["nota"] or dados["etapa"] else "Ainda não dá para saber: nenhuma conta tem nota nem etapa medida.")
    for i, p in enumerate(resumo["prioridades"][:5], 1):
        rotulo = f"{p['conta']} · {p['nome']}" if p.get("nome") else p["conta"]
        print(f"{i}. {rotulo} | nota {numero(p['nota']) if p['nota'] is not None else 'sem nota'} | {moeda(p['receita'])} | {'. '.join(p['por_que'])} | quem age: {p['quem_age']}")
    if resumo["metas"]:
        print("\nMetas:")
        for m in resumo["metas"]:
            print(f"- {m['meta']}: {m['situacao']} (atual {valor_formatado(m['atual'], m['unidade'])}, alvo {valor_formatado(m['alvo'], m['unidade'])})")
    print("\nPrevisões:")
    for linha in resumo_das_previsoes(resumo["previsoes"]):
        print(f"- {linha}")
    print("\nO que falta medir (até 5):")
    for f in resumo["falta_medir"][:5]:
        print(f"- [{f['prioridade']}] {f['o_que_falta']}: {f['primeiro_passo']}")
    if resumo["avisos_sobre_os_dados"]:
        print("\nAvisos sobre os dados:")
        for a in resumo["avisos_sobre_os_dados"]:
            print(f"- {a}")
    print(f"\nPasta da rodada: {destino}")
    print("Arquivos: health-score.xlsx (com nomes reais), alertas.md, painel-geral.md, previsoes.md, o-que-falta-medir.md, resumo.json, valores.csv")
    if modo == "protegido":
        print("Cópias com nomes reais, só para a pessoa, em com-nomes/.")
    return 0


def cmd_prever(args) -> int:
    from cslib.relatorios import resumo_das_previsoes
    from cslib.semana import ultima_rodada

    pasta = pasta_mod.exigir_pasta(args.pasta)
    data, resumo = ultima_rodada(pasta)
    prev = resumo.get("previsoes")
    if not prev:
        print(f"A rodada de {data.isoformat()} é de antes das previsões. Para incluí-las, gere de novo com rodada --refazer.")
        return 0
    print(f"Previsões da rodada de {data.isoformat()} (detalhes em previsoes.md, na pasta da rodada):")
    for linha in resumo_das_previsoes(prev):
        print(f"- {linha}")

    def rotulo(c: dict) -> str:
        return f"{c['conta']} · {c['nome']}" if c.get("nome") else c["conta"]

    for nome, titulo in (("churn", "Mais chance de cancelar"), ("incremento", "Mais chance de aumentar a receita")):
        contas = (prev.get(nome) or {}).get("contas", [])[:5]
        if contas:
            print(f"\n{titulo} (até 5):")
            for c in contas:
                print(f"- {rotulo(c)}: {c['chance_pct']}%. {'. '.join(c['motivos'])}")
    contas = (prev.get("engajamento") or {}).get("contas", [])[:5]
    if contas:
        print("\nUso que deve mudar (até 5):")
        for c in contas:
            print(f"- {rotulo(c)}: {c['rotina']} {c['tendencia']} ({c['chance_pct']}%)")
    return 0


def cmd_semana(args) -> int:
    from cslib.ciclo import para_a_semana
    from cslib.semana import segunda_da_semana, texto_semana, ultima_rodada

    pasta = pasta_mod.exigir_pasta(args.pasta)
    data = _data(args.data)
    data_rodada, resumo = ultima_rodada(pasta)
    segunda = segunda_da_semana(data)
    caminho = pasta / "2-metas" / f"semana-{segunda.isoformat()}.md"
    texto = texto_semana(segunda, resumo, data, para_a_semana(pasta, data, _nomeador(pasta)))
    if caminho.exists() and not args.refazer:
        print(f"O arquivo {caminho.name} já existe: não mexi nele. Os fatos atualizados estão abaixo.\n")
    else:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(texto, encoding="utf-8")
        print(f"Criei 2-metas/{caminho.name}.\n")
    idade = (data - data_rodada).days
    if idade > 7:
        print(f"Atenção: a rodada mais recente tem {idade} dias. Vale pedir um export novo antes.\n")
    print(texto)
    return 0


def cmd_restaurar(args) -> int:
    pasta = pasta_mod.exigir_pasta(args.pasta)
    origem = _arquivo_de_trabalho(pasta, args.arquivo)
    destino = pasta / "com-nomes" / origem.name
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(Cofre(pasta).restaurar(origem.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"Versão com nomes reais gravada em com-nomes/{origem.name}.")
    return 0


def cmd_conferir(args) -> int:
    from cslib.semana import conferir_numeros, ultima_rodada

    pasta = pasta_mod.exigir_pasta(args.pasta)
    origem = _arquivo_de_trabalho(pasta, args.arquivo)
    data, resumo = ultima_rodada(pasta)
    metas = pasta / "2-metas" / "metas.md"
    extras = metas.read_text(encoding="utf-8") if metas.exists() else ""
    contas_json = pasta / "4-dados" / "rodadas" / data.isoformat() / "contas.json"
    if contas_json.exists():
        extras += "\n" + contas_json.read_text(encoding="utf-8")
    partes = origem.relative_to(pasta).parts
    if partes[0] == "3-clientes" and len(partes) > 2:  # número que a pessoa anotou na ficha da conta também vale
        ficha = pasta / "3-clientes" / partes[1] / "ficha.md"
        if ficha.exists():
            extras += "\n" + ficha.read_text(encoding="utf-8")
    estranhos = conferir_numeros(origem.read_text(encoding="utf-8"), resumo, extras)
    if estranhos:
        print("Estes números não vieram da rodada nem das metas. Corrija ou apague:")
        for item in estranhos:
            print(f"- {item}")
        return 1
    print("Reais, percentuais, dias, contas e notas vieram da rodada ou das metas. Outros números não são conferidos: compare com o resumo.json.")
    return 0


def cmd_carteira(args) -> int:
    from cslib.contas import carregar_fatos, texto_carteira

    pasta = pasta_mod.exigir_pasta(args.pasta)
    data, resumo, fatos = carregar_fatos(pasta)
    print(texto_carteira(pasta, data, resumo, fatos))
    return 0


def cmd_oportunidades(args) -> int:
    from cslib.contas import carregar_fatos, rotulo
    from cslib.oportunidades import atualizar_mapa

    pasta = pasta_mod.exigir_pasta(args.pasta)
    data, resumo, fatos = carregar_fatos(pasta)
    lista = [o for item in fatos.values() for o in item.get("oportunidades", [])]
    caminho, novas, situacoes = atualizar_mapa(pasta, data, lista)
    print(f"Oportunidades da rodada de {data.isoformat()}: {len(lista)} em {len({o['conta'] for o in lista})} contas.")
    print(f"Mapa em {caminho.relative_to(pasta).as_posix()}: {novas} novas. Situação: " + (", ".join(f"{k} {v}" for k, v in sorted(situacoes.items())) or "vazio") + ".")
    for o in sorted(lista, key=lambda x: (x["com_insatisfacao"], -(x["receita"] or 0)))[:15]:
        aviso = " Resolva a insatisfação primeiro." if o["com_insatisfacao"] else ""
        print(f"- {rotulo(fatos[o['conta']])}: {o['oportunidade']}. {o['detalhe']}.{aviso}")
    return 0


def cmd_reuniao(args) -> int:
    from cslib.contas import criar_reuniao

    pasta = pasta_mod.exigir_pasta(args.pasta)
    caminho, texto, criou = criar_reuniao(pasta, _nome_simples(args.conta), args.tipo, _data(args.data), args.refazer)
    print(f"Criei {caminho.relative_to(pasta).as_posix()}.\n" if criou else f"O arquivo {caminho.relative_to(pasta).as_posix()} já existe: não mexi nele. Os fatos atualizados estão abaixo.\n")
    print(texto)
    return 0


def cmd_apresentacao(args) -> int:
    from cslib.apresentacao import gerar_apresentacao

    pasta = pasta_mod.exigir_pasta(args.pasta)
    destino, pendencias = gerar_apresentacao(pasta, _arquivo_de_trabalho(pasta, args.arquivo))
    print(f"Apresentação gravada em com-nomes/{destino.name}, com os nomes reais. A pessoa abre e ajusta no PowerPoint.")
    if pendencias:
        print("A pessoa precisa fazer antes de mostrar ao cliente:")
        for pendencia in pendencias:
            print(f"- {pendencia}")
    return 0


def cmd_cuidados(args) -> int:
    from cslib.contas import carregar_fatos
    from cslib.guardiao import texto_cuidados

    pasta = pasta_mod.exigir_pasta(args.pasta)
    data, resumo, fatos = carregar_fatos(pasta)
    print(texto_cuidados(pasta, data, resumo, fatos))
    return 0


def cmd_plano(args) -> int:
    from cslib.guardiao import criar_plano

    pasta = pasta_mod.exigir_pasta(args.pasta)
    caminho, texto, criou = criar_plano(pasta, _nome_simples(args.conta), args.tipo, _data(args.data), args.refazer)
    print(f"Criei {caminho.relative_to(pasta).as_posix()}.\n" if criou else f"O arquivo {caminho.relative_to(pasta).as_posix()} já existe: não mexi nele. Os fatos atualizados estão abaixo.\n")
    print(texto)
    return 0


def cmd_melhoria(args) -> int:
    from cslib.guardiao import texto_melhoria
    from cslib.semana import ultima_rodada

    pasta = pasta_mod.exigir_pasta(args.pasta)
    data, resumo = ultima_rodada(pasta)
    if not resumo.get("melhoria"):
        print(f"A rodada de {data.isoformat()} é de antes desta função. Para incluir, gere de novo com rodada --refazer.")
        return 0
    cofre = Cofre(pasta)
    aberto = pasta_mod.modo_privacidade(pasta) == "aberto"
    print(texto_melhoria(data, resumo, (lambda c: f"{c} · {cofre.nome_de(c)}") if aberto else (lambda c: c)))
    return 0


def cmd_mesa(args) -> int:
    from cslib.mesa import ARQUIVO, adicionar, sincronizar, texto_mesa

    pasta = pasta_mod.exigir_pasta(args.pasta)
    data = _data(args.data)
    if args.adicionar:
        arquivo = _arquivo_de_trabalho(pasta, args.arquivo).relative_to(pasta).as_posix() if args.arquivo else None
        item = adicionar(pasta, args.adicionar, _nome_simples(args.conta) if args.conta else None, arquivo, data)
        print(f"Item {item['item']} na mesa. Quem decide é a pessoa.\n")
    elif args.arquivo or args.conta:
        raise ErroDeUso("--arquivo e --conta só valem junto com --adicionar.")
    itens, novos, avisos = sincronizar(pasta, data)
    print(texto_mesa(pasta, itens, novos, avisos, _nomeador(pasta)))
    _copia_com_nomes(pasta, ARQUIVO, (pasta / ARQUIVO).read_text(encoding="utf-8"))
    print(f"\nA tabela está em {ARQUIVO}. A cópia com nomes reais está em com-nomes/{ARQUIVO}.")
    return 0


def cmd_decidir(args) -> int:
    from cslib.ciclo import _indicador
    from cslib.mesa import ARQUIVO, SEM_CONTA, data_legivel, decidir

    pasta = pasta_mod.exigir_pasta(args.pasta)
    rotina = None
    if args.acompanhar:
        cfg = config_mod.carregar(pasta)
        indicador = _indicador(cfg, args.acompanhar)
        if indicador is None:
            raise ErroDeUso("essa rotina não está em como-medir.md. Use um destes nomes: " + ", ".join(i.rotina for i in cfg.indicadores) + ".")
        rotina = indicador.rotina
    item = decidir(pasta, args.item, args.decisao, _data(args.data), rotina, args.mesmo_assim)
    print(f"Anotei em {ARQUIVO}: {item['item']} {item['decisao']} em {data_legivel(item['decidido_em'])}.")
    if item["decisao"] == "aprovado":
        print("A skill não envia nem muda nada sozinha: quem age é a pessoa.")
        if item["acompanhar"] or item["conta"] != SEM_CONTA:
            print(f"Na próxima rodada, o ciclo compara {item['acompanhar'] or 'a nota'} com a rodada de antes da decisão.")
        else:
            print("Este item não tem conta nem rotina: o ciclo não tem número para comparar. Se houver uma rotina que deve mudar, anote na coluna acompanhar.")
    _copia_com_nomes(pasta, ARQUIVO, (pasta / ARQUIVO).read_text(encoding="utf-8"))
    return 0


def cmd_resultado(args) -> int:
    from cslib.ciclo import calcular, texto_resultado
    from cslib.mesa import sincronizar

    pasta = pasta_mod.exigir_pasta(args.pasta)
    data = _data(args.data)
    itens, _, _ = sincronizar(pasta, data)
    print(texto_resultado(calcular(pasta, itens, data), _nomeador(pasta)))
    return 0


def cmd_rotina(args) -> int:
    from cslib.rotina import executar, registrar_falha, texto_da_rotina

    pasta = pasta_mod.exigir_pasta(args.pasta)
    data = _data(args.data)
    try:
        saida = executar(pasta, data, _nomeador(pasta))
    except Exception as erro:  # noqa: BLE001
        registrar_falha(pasta, data, erro)
        raise
    print(texto_da_rotina(saida, data))
    return 0


def cmd_agendar(args) -> int:
    from cslib.rotina import agendar, remover_agendamento, ver_agendamento

    pasta = pasta_mod.exigir_pasta(args.pasta)
    if args.remover:
        print(remover_agendamento(pasta))
    elif args.ver:
        print(ver_agendamento(pasta))
    else:
        print(agendar(pasta, args.hora, Path(__file__).resolve(), dt.date.today()))
    return 0


def cmd_hoje(args) -> int:
    from cslib.hoje import ARQUIVO, gerar_hoje

    pasta = pasta_mod.exigir_pasta(args.pasta)
    texto, novos, avisos, _ = gerar_hoje(pasta, _data(args.data), _nomeador(pasta))
    print(texto)
    for aviso in avisos:
        print(f"Aviso: {aviso}")
    if pasta_mod.modo_privacidade(pasta) == "protegido":
        _copia_com_nomes(pasta, ARQUIVO, texto)
        print(f"A pessoa abre com-nomes/{ARQUIVO}, com os nomes reais.")
    else:
        print(f"A página está em {ARQUIVO}.")
    return 0


def cmd_tarefas(args) -> int:
    from cslib.contas import carregar_fatos
    from cslib.hoje import atualizar_tarefas
    from cslib.mesa import sincronizar
    from cslib.tarefas import acrescentar, gravar_copias, ler_data_curta, ler_tarefas, marcar_feita, nova, texto_tarefas

    pasta = pasta_mod.exigir_pasta(args.pasta)
    data = _data(args.data)
    if args.feita:
        tarefa = marcar_feita(pasta, args.feita, data)
        print(f"Tarefa {tarefa['tarefa']} marcada como feita.\n")
    if args.adicionar:
        ate = ler_data_curta(args.ate, data) if args.ate else None
        if args.ate and ate is None:
            raise ErroDeUso("use a data no formato 2026-11-07 ou 07/11.")
        tarefa = acrescentar(pasta, data, [nova(args.adicionar, ate, _nome_simples(args.conta) if args.conta else None, args.quem)])
        print(f"Tarefa {tarefa[0]['tarefa']} na lista.\n" if tarefa else "Essa tarefa já está na lista.\n")
    elif args.ate or args.conta or args.quem:
        raise ErroDeUso("--ate, --conta e --quem só valem junto com --adicionar.")
    try:
        _, resumo, fatos = carregar_fatos(pasta)
    except ErroDeUso:  # sem rodada, a lista ainda vale para as tarefas da pessoa
        resumo, fatos = None, {}
    if resumo:
        atualizar_tarefas(pasta, data, resumo, sincronizar(pasta, data)[0])
    else:
        acrescentar(pasta, data, [])
    gravar_copias(pasta, data, fatos)
    print(texto_tarefas(ler_tarefas(pasta), data, _nomeador(pasta)))
    print("\nA lista está em tarefas.md. O arquivo para a agenda está em com-nomes/agenda.ics, com os nomes reais: a pessoa importa no calendário dela.")
    return 0


def cmd_preparar(args) -> int:
    from cslib.hoje import preparar

    pasta = pasta_mod.exigir_pasta(args.pasta)
    if args.limite < 1:
        raise ErroDeUso("use um --limite de 1 ou mais.")
    nome_de = _nomeador(pasta)
    feitos = preparar(pasta, _data(args.data), args.limite)
    if not feitos:
        print("Nada novo para preparar: quem tem sinal ou renova já tem arquivo recente.")
        return 0
    print(f"Preparei {plural(len(feitos), 'arquivo', 'arquivos')}, só com os fatos da rodada. A causa e a decisão vêm da conversa:")
    for feito in feitos:
        print(f"- {nome_de(feito['conta'])}: {feito['o_que_e']}. {feito['arquivo']}")
    return 0


def cmd_nova_ficha(args) -> int:
    pasta = pasta_mod.exigir_pasta(args.pasta)
    ficha = pasta_mod.nova_ficha(pasta, _nome_simples(args.conta))
    print(f"Ficha em 3-clientes/{args.conta}/{ficha.name}.")
    return 0


def montar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cs.py", description=f"gestao-de-cs {VERSAO}")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("criar-pasta", help="cria a pasta da empresa")
    p.add_argument("--destino", required=True)
    p.add_argument("--empresa", required=True)
    p.add_argument("--modo", choices=pasta_mod.MODOS)
    p.set_defaults(func=cmd_criar_pasta)

    p = sub.add_parser("privacidade", help="mostra ou muda o modo de privacidade")
    p.add_argument("--pasta", required=True)
    p.add_argument("--modo", choices=pasta_mod.MODOS)
    p.set_defaults(func=cmd_privacidade)

    p = sub.add_parser("receber", help="guarda um export em 4-dados/entradas")
    p.add_argument("--pasta", required=True)
    p.add_argument("--arquivo", required=True)
    p.add_argument("--data")
    p.set_defaults(func=cmd_receber)

    p = sub.add_parser("colunas", help="mostra as colunas dos exports")
    p.add_argument("--pasta")
    p.add_argument("--entrada")
    p.add_argument("--arquivo")
    p.set_defaults(func=cmd_colunas)

    p = sub.add_parser("validar", help="confere a pasta e diz o próximo passo")
    p.add_argument("--pasta", required=True)
    p.set_defaults(func=cmd_validar)

    p = sub.add_parser("rotulos", help="mostra a ligação dos rótulos")
    p.add_argument("--pasta", required=True)
    p.set_defaults(func=cmd_rotulos)

    p = sub.add_parser("rodada", help="roda as contas e gera os arquivos")
    p.add_argument("--pasta", required=True)
    p.add_argument("--data")
    p.add_argument("--entrada")
    p.add_argument("--refazer", action="store_true")
    p.set_defaults(func=cmd_rodada)

    p = sub.add_parser("prever", help="mostra as previsões da última rodada")
    p.add_argument("--pasta", required=True)
    p.set_defaults(func=cmd_prever)

    p = sub.add_parser("semana", help="monta os fatos da semana")
    p.add_argument("--pasta", required=True)
    p.add_argument("--data")
    p.add_argument("--refazer", action="store_true")
    p.set_defaults(func=cmd_semana)

    p = sub.add_parser("restaurar-nomes", help="gera a versão com nomes reais em com-nomes/")
    p.add_argument("--pasta", required=True)
    p.add_argument("--arquivo", required=True)
    p.set_defaults(func=cmd_restaurar)

    p = sub.add_parser("conferir-numeros", help="aponta números que não vieram da rodada")
    p.add_argument("--pasta", required=True)
    p.add_argument("--arquivo", required=True)
    p.set_defaults(func=cmd_conferir)

    p = sub.add_parser("nova-ficha", help="cria a ficha de uma conta")
    p.add_argument("--pasta", required=True)
    p.add_argument("--conta", required=True)
    p.set_defaults(func=cmd_nova_ficha)

    p = sub.add_parser("carteira", help="contas-chave, renovações e onde há espaço para crescer")
    p.add_argument("--pasta", required=True)
    p.set_defaults(func=cmd_carteira)

    p = sub.add_parser("cuidados", help="o que empaca, quem está em risco e quem perdeu o contato")
    p.add_argument("--pasta", required=True)
    p.set_defaults(func=cmd_cuidados)

    p = sub.add_parser("plano", help="prepara o plano de uma conta em risco ou de uma troca de contato")
    p.add_argument("--pasta", required=True)
    p.add_argument("--conta", required=True)
    p.add_argument("--tipo", default="risco", choices=("risco", "contato"))
    p.add_argument("--data")
    p.add_argument("--refazer", action="store_true")
    p.set_defaults(func=cmd_plano)

    p = sub.add_parser("melhoria", help="o que cresce, quem saiu e com quem conversar")
    p.add_argument("--pasta", required=True)
    p.set_defaults(func=cmd_melhoria)

    p = sub.add_parser("oportunidades", help="mapeia as oportunidades de upgrade da última rodada")
    p.add_argument("--pasta", required=True)
    p.set_defaults(func=cmd_oportunidades)

    p = sub.add_parser("reuniao", help="prepara os fatos e o roteiro de uma reunião com a conta")
    p.add_argument("--pasta", required=True)
    p.add_argument("--conta", required=True)
    p.add_argument("--tipo", default="revisao", choices=("revisao", "renovacao", "expansao"))
    p.add_argument("--data")
    p.add_argument("--refazer", action="store_true")
    p.set_defaults(func=cmd_reuniao)

    p = sub.add_parser("apresentacao", help="gera o PowerPoint a partir da seção Slides de uma reunião")
    p.add_argument("--pasta", required=True)
    p.add_argument("--arquivo", required=True)
    p.set_defaults(func=cmd_apresentacao)

    p = sub.add_parser("mesa", help="mostra o que espera a decisão da pessoa")
    p.add_argument("--pasta", required=True)
    p.add_argument("--data")
    p.add_argument("--adicionar", help="o que é o item, para o que não sai de um comando da skill")
    p.add_argument("--conta")
    p.add_argument("--arquivo")
    p.set_defaults(func=cmd_mesa)

    p = sub.add_parser("decidir", help="anota a decisão da pessoa sobre um item da mesa")
    p.add_argument("--pasta", required=True)
    p.add_argument("--item", required=True)
    p.add_argument("--decisao", required=True, choices=("aprovado", "recusado", "resolvido"))
    p.add_argument("--acompanhar", help="a rotina que deve mudar; sem ela, o ciclo olha a nota")
    p.add_argument("--mesmo-assim", action="store_true", help="aprova mesmo com campos em branco no arquivo")
    p.add_argument("--data")
    p.set_defaults(func=cmd_decidir)

    p = sub.add_parser("resultado", help="o que aconteceu com o número depois de cada ação aprovada")
    p.add_argument("--pasta", required=True)
    p.add_argument("--data")
    p.set_defaults(func=cmd_resultado)

    p = sub.add_parser("hoje", help="gera a página do dia")
    p.add_argument("--pasta", required=True)
    p.add_argument("--data")
    p.set_defaults(func=cmd_hoje)

    p = sub.add_parser("preparar", help="prepara os planos e reuniões que a rodada pede")
    p.add_argument("--pasta", required=True)
    p.add_argument("--data")
    p.add_argument("--limite", type=int, default=3)
    p.set_defaults(func=cmd_preparar)

    p = sub.add_parser("tarefas", help="a lista do que fazer e o arquivo para a agenda")
    p.add_argument("--pasta", required=True)
    p.add_argument("--data")
    p.add_argument("--adicionar", help="o que fazer")
    p.add_argument("--ate", help="data da tarefa: 2026-11-07 ou 07/11")
    p.add_argument("--conta")
    p.add_argument("--quem")
    p.add_argument("--feita", help="o número da tarefa que a pessoa terminou")
    p.set_defaults(func=cmd_tarefas)

    p = sub.add_parser("rotina", help="lê o export novo, atualiza a nota, monta a semana, reavalia o urgente e refaz a página, sem IA")
    p.add_argument("--pasta", required=True)
    p.add_argument("--data")
    p.set_defaults(func=cmd_rotina)

    p = sub.add_parser("agendar", help="deixa a rotina rodando sozinha neste computador")
    p.add_argument("--pasta", required=True)
    p.add_argument("--hora", default="08:00")
    p.add_argument("--remover", action="store_true")
    p.add_argument("--ver", action="store_true")
    p.set_defaults(func=cmd_agendar)
    return parser


def main(argv=None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8")
    args = montar_parser().parse_args(argv)
    try:
        return args.func(args)
    except ErroDeUso as erro:
        print(f"ERRO: {erro}")
        return 2
    except ImportError as erro:
        print(f"ERRO: falta uma biblioteca do Python ({type(erro).__name__}). Rode: python -m pip install openpyxl xlsxwriter")
        return 3
    except ValueError as erro:
        if "formato não suportado" in str(erro):
            print(f"ERRO: {erro}")
            return 2
        return _erro_interno(erro)
    except Exception as erro:  # noqa: BLE001
        return _erro_interno(erro)


def _erro_interno(erro: Exception) -> int:
    # A mensagem original pode trazer valores dos dados. Mostra só onde aconteceu.
    ultimo = traceback.extract_tb(erro.__traceback__)[-1]
    print(f"ERRO interno: {type(erro).__name__} em {Path(ultimo.filename).name}, linha {ultimo.lineno}. A mensagem foi omitida para não expor dados.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
