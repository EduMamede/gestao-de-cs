"""A regra que não pode quebrar: no modo protegido, a IA só vê códigos, totais e nomes de colunas."""

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import RAIZ, REF, Empresa, rodar, textos_para_ia

GUARDA = RAIZ / "scripts" / "guarda_privacidade.py"
sys.path.insert(0, str(RAIZ / "scripts"))
import guarda_privacidade  # noqa: E402

# Tudo que não pode aparecer para a IA em nenhuma das bases.
PROIBIDO = re.compile(
    r"Clínica Fictícia|CLÍNICA FICTÍCIA|clinica ficticia|Hospital Fictício|Empresa Fictícia|Distribuidora Fictícia|Pessoa Fictícia|Ana Fictícia|Bruno Fictício"
    r"|ficticia\.example|SEGREDO|Cobrar envio|Parado por nós,|Pequena|Média\b(?! )",
)
BASES = ("completa", "baguncada", "minima", "canceladas", "recompra")


class TestModoProtegido(unittest.TestCase):
    def test_nada_vaza_nas_5_bases(self):
        for nome in BASES:
            with self.subTest(base=nome):
                e = Empresa(nome)
                try:
                    saidas = {}
                    saidas["colunas"] = rodar("colunas", "--pasta", e.pasta, "--entrada", REF)[1]
                    saidas["validar"] = rodar("validar", "--pasta", e.pasta)[1]
                    saidas["rodada"] = e.rodada()[1]
                    saidas["rotulos"] = rodar("rotulos", "--pasta", e.pasta)[1]
                    saidas["semana"] = rodar("semana", "--pasta", e.pasta, "--data", REF)[1]
                    for comando, texto in saidas.items():
                        achado = PROIBIDO.search(texto)
                        self.assertIsNone(achado, f"{comando}: {achado and achado.group(0)}")
                    for arquivo, texto in textos_para_ia(e.pasta).items():
                        if arquivo.startswith("1-empresa") or arquivo.endswith(("metas.md", "colunas.md", "como-medir.md")):
                            continue  # escritos pela pessoa no checklist
                        achado = PROIBIDO.search(texto)
                        self.assertIsNone(achado, f"{arquivo}: {achado and achado.group(0)}")
                finally:
                    e.fechar()

    def test_colunas_nao_mostra_valor_nenhum(self):
        e = Empresa("completa")
        try:
            saida = rodar("colunas", "--pasta", e.pasta, "--entrada", REF)[1]
            self.assertIn("Observações", saida)  # o nome da coluna pode
            self.assertIn("TEXTO LIVRE: bloqueada", saida)
            self.assertIn("dado pessoal: e-mail", saida)
            self.assertNotIn("exemplos:", saida)
            self.assertNotRegex(saida, r"R\$|\d{2}/\d{2}/\d{4}")
        finally:
            e.fechar()

    def test_texto_livre_nao_entra_nem_na_planilha(self):
        import openpyxl

        e = Empresa("completa")
        try:
            e.rodada()
            livro = openpyxl.load_workbook(e.pasta / "4-dados" / "rodadas" / REF / "health-score.xlsx", data_only=True)
            tudo = " ".join(str(c.value) for aba in livro.worksheets for l in aba.iter_rows() for c in l if c.value is not None)
            livro.close()
            self.assertNotIn("SEGREDO", tudo)
            self.assertNotIn("ficticia.example", tudo)
            # o próximo passo foi ligado de propósito: vai só para a planilha
            self.assertIn("Cobrar envio", tudo)
        finally:
            e.fechar()

    def test_nomes_reais_voltam_no_fim(self):
        e = Empresa("completa")
        try:
            e.rodada()
            alertas = (e.pasta / "com-nomes" / f"alertas-{REF}.md").read_text(encoding="utf-8")
            self.assertIn("Hospital Fictício Grande Conta", alertas)
            self.assertNotRegex(alertas, r"CONTA-\d{3}")
        finally:
            e.fechar()

    def test_erro_interno_nao_mostra_o_dado(self):
        # Uma mensagem de erro do Python pode trazer o valor da célula. A nossa nunca traz.
        import cs  # type: ignore
        from io import StringIO
        from contextlib import redirect_stdout

        saida = StringIO()
        with redirect_stdout(saida):
            codigo = cs._erro_interno(_erro_com_segredo())
        self.assertEqual(codigo, 1)
        self.assertNotIn("SEGREDO", saida.getvalue())
        self.assertIn("omitida", saida.getvalue())

    def test_rotulo_desconhecido_vai_para_a_pessoa_nao_para_a_ia(self):
        e = Empresa("completa")
        try:
            contas = e.entrada / "contas.csv"
            contas.write_text(contas.read_text(encoding="utf-8").replace("Treinamento", "ROTULO-SEGREDO-X"), encoding="utf-8")
            saida = e.rodada()[1]
            self.assertNotIn("ROTULO-SEGREDO-X", saida)
            self.assertIn("1 rótulo de 'etapa' sem ligação", saida)
            # a saída de rotulos mostra no que eles viraram, nunca o rótulo
            rotulos = rodar("rotulos", "--pasta", e.pasta)[1]
            self.assertNotIn("ROTULO-SEGREDO-X", rotulos)
            self.assertNotIn("atrasado", rotulos)
            self.assertIn("Implantação (1)", rotulos)
            self.assertRegex(rotulos, r"indicador:pagamento \| 2 \| 0 \| 0 \(\d+\), 100 \(\d+\)")
            self.assertNotIn("ROTULO-SEGREDO-X", (e.pasta / "4-dados" / "rodadas" / REF / "resumo.json").read_text(encoding="utf-8"))
            self.assertIn("ROTULO-SEGREDO-X", (e.pasta / "4-dados" / ".privado" / "rotulos.csv").read_text(encoding="utf-8-sig"))
            # a pessoa liga o rótulo e a conta volta a ser medida
            caminho = e.pasta / "4-dados" / ".privado" / "rotulos.csv"
            texto = caminho.read_text(encoding="utf-8-sig").replace("ROTULO-SEGREDO-X;;", "ROTULO-SEGREDO-X;Treinamento;")
            caminho.write_text(texto, encoding="utf-8-sig")
            saida = e.rodada(REF, "--refazer")[1]
            self.assertNotIn("sem ligação", saida)
        finally:
            e.fechar()


def _erro_com_segredo():
    try:
        raise KeyError("SEGREDO-Clínica")
    except KeyError as erro:
        return erro


class TestModoAberto(unittest.TestCase):
    def test_ia_ve_nomes_e_exemplos(self):
        e = Empresa("completa", modo="aberto")
        try:
            saida = e.rodada()[1]
            self.assertIn("Hospital Fictício Grande Conta", saida)
            colunas = rodar("colunas", "--pasta", e.pasta, "--entrada", REF)[1]
            self.assertIn("exemplos:", colunas)
            self.assertIn("Hospital Fictício Grande Conta", (e.pasta / "4-dados" / "rodadas" / REF / "alertas.md").read_text(encoding="utf-8"))
            rotulos = rodar("rotulos", "--pasta", e.pasta)[1]
            self.assertIn("Implantação", rotulos)
        finally:
            e.fechar()

    def test_texto_livre_e_email_nao_viram_exemplo(self):
        e = Empresa("completa", modo="aberto")
        try:
            colunas = rodar("colunas", "--pasta", e.pasta, "--entrada", REF)[1]
            self.assertNotIn("SEGREDO", colunas)
            self.assertNotIn("ficticia.example", colunas)
        finally:
            e.fechar()

    def test_sem_escolha_fica_protegido(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp) / "x"
            codigo, saida = rodar("criar-pasta", "--destino", pasta, "--empresa", "X")
            self.assertEqual(codigo, 0)
            self.assertIn("protegido", saida)
            self.assertIn("ainda não escolhido", rodar("validar", "--pasta", pasta)[1])


class TestPastaDaEmpresa(unittest.TestCase):
    def test_nao_cria_dentro_do_plugin(self):
        codigo, saida = rodar("criar-pasta", "--destino", RAIZ / "exemplos" / "x", "--empresa", "X")
        self.assertEqual(codigo, 2)
        self.assertIn("dentro do plugin", saida)
        self.assertFalse((RAIZ / "exemplos" / "x").exists())

    def test_nao_sobrescreve_o_que_a_pessoa_escreveu(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp) / "x"
            rodar("criar-pasta", "--destino", pasta, "--empresa", "X")
            perfil = pasta / "1-empresa" / "perfil.md"
            perfil.write_text("ANOTADO", encoding="utf-8")
            rodar("criar-pasta", "--destino", pasta, "--empresa", "X")
            self.assertEqual(perfil.read_text(encoding="utf-8"), "ANOTADO")

    def test_estrutura_e_gitignore(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp) / "x"
            rodar("criar-pasta", "--destino", pasta, "--empresa", "Empresa X")
            for caminho in (
                "LEIA-ME.md", "1-empresa/perfil.md", "1-empresa/estrategia.md", "1-empresa/jornada.md", "1-empresa/conversas-consultor.md",
                "2-metas/metas.md", "3-clientes/contas-chave.md", "4-dados/como-medir.md", "4-dados/colunas.md", "4-dados/entradas", "4-dados/rodadas",
                "5-melhoria/sugestoes.md", "5-melhoria/problemas.md", "5-melhoria/mudancas.md", ".gitignore", ".gestao-de-cs.json",
            ):
                self.assertTrue((pasta / caminho).exists(), caminho)
            self.assertIn("*", (pasta / ".gitignore").read_text(encoding="utf-8"))
            self.assertIn("Empresa X", (pasta / "LEIA-ME.md").read_text(encoding="utf-8"))
            codigo, saida = rodar("nova-ficha", "--pasta", pasta, "--conta", "CONTA-017")
            self.assertEqual(codigo, 0, saida)
            ficha = (pasta / "3-clientes" / "CONTA-017" / "ficha.md").read_text(encoding="utf-8")
            self.assertIn("O que mais ajudamos vocês hoje?", ficha)
            self.assertTrue((pasta / "3-clientes" / "CONTA-017" / "reunioes").is_dir())

    def test_referencias_nao_dependem_da_variavel_do_plugin(self):
        # a variável só é substituída em skill e agente carregados, não em arquivo lido com Read
        for caminho in (RAIZ / "referencias").glob("*.md"):
            self.assertNotIn("CLAUDE_PLUGIN_ROOT", caminho.read_text(encoding="utf-8"), caminho)

    def test_modelos_nao_citam_nada_proibido(self):
        # A lista fica fora do plugin, senão os próprios nomes iriam junto. Sem ela, o teste é pulado.
        lista = RAIZ.parent / "gestao-de-cs-pacote" / "nomes-proibidos.txt"
        if not lista.exists():
            self.skipTest("lista de nomes proibidos não encontrada")
        nomes = [n.strip() for n in lista.read_text(encoding="utf-8").splitlines() if n.strip()]
        proibidas = re.compile("|".join(rf"\b{re.escape(n)}\b" for n in nomes), re.IGNORECASE)
        for pasta in ("modelos", "skills", "agents", "referencias", "scripts", "hooks"):
            for caminho in (RAIZ / pasta).rglob("*"):
                if caminho.is_file() and caminho.suffix in (".md", ".py", ".json"):
                    self.assertIsNone(proibidas.search(caminho.read_text(encoding="utf-8")), caminho)


class TestTrava(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.protegida = Path(cls.tmp.name) / "protegida"
        cls.aberta = Path(cls.tmp.name) / "aberta"
        rodar("criar-pasta", "--destino", cls.protegida, "--empresa", "P", "--modo", "protegido")
        rodar("criar-pasta", "--destino", cls.aberta, "--empresa", "A", "--modo", "aberto")
        cls.fora = Path(cls.tmp.name) / "outro-lugar"
        cls.fora.mkdir()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def bloqueia(self, ferramenta, entrada, cwd=None):
        return guarda_privacidade.decidir({"tool_name": ferramenta, "tool_input": entrada, "cwd": str(cwd or self.fora)})

    def test_bloqueia_os_dados_brutos(self):
        p = self.protegida
        for caminho in (p / "4-dados" / "entradas" / REF / "contas.csv", p / "4-dados" / ".privado" / "mapa-contas.csv", p / "com-nomes" / "semana-2026-11-02.md", p / "4-dados" / "rodadas" / REF / "health-score.xlsx"):
            self.assertTrue(self.bloqueia("Read", {"file_path": str(caminho)}), caminho)

    def test_libera_o_que_a_ia_pode_ler(self):
        p = self.protegida
        for caminho in (p / "4-dados" / "rodadas" / REF / "resumo.json", p / "4-dados" / "rodadas" / REF / "alertas.md", p / "1-empresa" / "perfil.md", p / "2-metas" / "semana-2026-11-02.md", p / "4-dados" / "rodadas" / REF / "valores.csv"):
            self.assertFalse(self.bloqueia("Read", {"file_path": str(caminho)}), caminho)

    def test_modo_aberto_libera_tudo(self):
        a = self.aberta
        for caminho in (a / "4-dados" / "entradas" / REF / "contas.csv", a / "com-nomes" / "x.md", a / "4-dados" / "rodadas" / REF / "health-score.xlsx"):
            self.assertFalse(self.bloqueia("Read", {"file_path": str(caminho)}), caminho)

    def test_fora_de_pasta_de_empresa_nao_atrapalha(self):
        self.assertFalse(self.bloqueia("Read", {"file_path": str(self.fora / "4-dados" / "entradas" / "x.csv")}))
        self.assertFalse(self.bloqueia("Bash", {"command": f'cat "{self.fora / "dados.csv"}"'}))

    def test_comandos(self):
        p = self.protegida
        arquivo = p / "4-dados" / "entradas" / REF / "contas.csv"
        self.assertTrue(self.bloqueia("Bash", {"command": f'cat "{arquivo}"'}))
        self.assertTrue(self.bloqueia("PowerShell", {"command": f'Get-Content "{arquivo}"'}))
        self.assertTrue(self.bloqueia("Bash", {"command": 'python -c "import csv; print(open(\'4-dados/entradas/x.csv\').read())"'}, cwd=p))
        self.assertTrue(self.bloqueia("Bash", {"command": "cat com-nomes/semana.md"}, cwd=p))
        self.assertTrue(self.bloqueia("Bash", {"command": "head contas.csv"}, cwd=p))

    def test_scripts_da_skill_passam(self):
        p = self.protegida
        cs = RAIZ / "scripts" / "cs.py"
        comando = f'python "{cs}" rodada --pasta "{p}" --entrada {REF}'
        self.assertFalse(self.bloqueia("Bash", {"command": comando}))
        self.assertFalse(self.bloqueia("PowerShell", {"command": f'python "{cs}" receber --pasta "{p}" --arquivo "{p}/4-dados/entradas/x.csv"'}))
        self.assertTrue(self.bloqueia("Bash", {"command": comando + f' ; cat "{p}/com-nomes/x.md"'}))
        self.assertTrue(self.bloqueia("Bash", {"command": f'python "{cs}" colunas --pasta "{p}" && type "{p}/4-dados/.privado/rotulos.csv"'}))

    def test_grep_na_raiz_e_bloqueado(self):
        p = self.protegida
        self.assertTrue(self.bloqueia("Grep", {"pattern": "x", "path": str(p)}))
        self.assertTrue(self.bloqueia("Grep", {"pattern": "x", "path": str(p / "4-dados")}))
        self.assertTrue(self.bloqueia("Grep", {"pattern": "x"}, cwd=p))
        self.assertFalse(self.bloqueia("Grep", {"pattern": "x", "path": str(p / "1-empresa")}))

    def test_processo_de_verdade(self):
        p = self.protegida
        entrada = {"tool_name": "Read", "tool_input": {"file_path": str(p / "com-nomes" / "x.md")}, "cwd": str(self.fora)}
        r = subprocess.run([sys.executable, str(GUARDA)], input=json.dumps(entrada), capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0)
        saida = json.loads(r.stdout)
        self.assertEqual(saida["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertTrue(r.stdout.isascii())  # no Windows, a saída do Python não sai em UTF-8 por padrão
        entrada["tool_input"]["file_path"] = str(p / "1-empresa" / "perfil.md")
        r = subprocess.run([sys.executable, str(GUARDA)], input=json.dumps(entrada), capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.stdout.strip(), "")

    def test_json_invalido_nao_trava_a_sessao(self):
        r = subprocess.run([sys.executable, str(GUARDA)], input="não é json", capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0)


class TestLiberacao(unittest.TestCase):
    """O plugin dispensa a autorização só para o próprio script, dentro dos próprios agentes."""

    CS = RAIZ / "scripts" / "cs.py"
    PASTA = "D:/empresa teste"

    def libera(self, comando, ferramenta="Bash", agente="gestao-de-cs:analista-de-dados", cwd=None):
        dados = {"tool_name": ferramenta, "tool_input": {"command": comando}, "cwd": str(cwd or RAIZ)}
        if agente:
            dados["agent_type"] = agente
        return guarda_privacidade.liberar(dados)

    def comando(self, resto):
        return f'python "{self.CS}" {resto}'

    def test_libera_o_trabalho_do_agente(self):
        for resto in (
            f'validar --pasta "{self.PASTA}"',
            f'colunas --pasta "{self.PASTA}" --entrada {REF}',
            f'rotulos --pasta "{self.PASTA}"',
            f'rodada --pasta "{self.PASTA}" --data {REF} --entrada {REF}',
            f'prever --pasta "{self.PASTA}"',
            f'semana --pasta "{self.PASTA}" --data {REF}',
            f'conferir-numeros --pasta "{self.PASTA}" --arquivo "2-metas/semana.md"',
            f'restaurar-nomes --pasta "{self.PASTA}" --arquivo "2-metas/semana.md"',
            f'nova-ficha --pasta "{self.PASTA}" --conta CONTA-017',
        ):
            for ferramenta in ("Bash", "PowerShell"):
                self.assertTrue(self.libera(self.comando(resto), ferramenta), resto)

    def test_aceita_as_formas_do_caminho(self):
        self.assertTrue(self.libera(f"python '{self.CS}' validar --pasta '{self.PASTA}'"))
        self.assertTrue(self.libera(f'python scripts/cs.py validar --pasta "{self.PASTA}"', cwd=RAIZ))
        if sys.platform == "win32":
            msys = "/" + self.CS.as_posix().replace(":", "", 1)
            self.assertTrue(self.libera(f'python "{msys}" validar --pasta "{self.PASTA}"'))

    def test_fora_dos_agentes_do_plugin_continua_pedindo(self):
        resto = f'validar --pasta "{self.PASTA}"'
        for agente in (None, "Explore", "outro:gestao-de-cs:analista-de-dados", "gestao-de-cs"):
            self.assertFalse(self.libera(self.comando(resto), agente=agente), agente)

    def test_decisoes_da_pessoa_continuam_pedindo(self):
        for resto in (
            f'privacidade --pasta "{self.PASTA}" --modo aberto',
            f'privacidade --pasta "{self.PASTA}"',
            f'criar-pasta --destino "{self.PASTA}" --empresa X --modo aberto',
            f'receber --pasta "{self.PASTA}" --arquivo "C:/Downloads/x.csv"',
            f'rodada --pasta "{self.PASTA}" --refazer',
            f'rodada --pasta "{self.PASTA}" --ref',  # o argparse aceitaria a abreviação
            f'semana --pasta "{self.PASTA}" "--refazer"',
            f'semana --pasta --refazer --data {REF}',
            f'colunas --arquivo "C:/Downloads/x.csv"',
            f'colunas --pasta "{self.PASTA}" --arquivo "C:/Downloads/x.csv"',
            f'--pasta "{self.PASTA}"',
            f'validar --pasta="{self.PASTA}"',
            f'validar --pasta "{self.PASTA}" --pasta "D:/outra"',
            "validar",
            "",
        ):
            self.assertFalse(self.libera(self.comando(resto)), resto)

    def test_so_este_script_e_este_interpretador(self):
        resto = f'validar --pasta "{self.PASTA}"'
        for comando in (
            f'python "D:/outro-lugar/scripts/cs.py" {resto}',
            f'python "{self.CS}.py" {resto}',
            f'python "{RAIZ / "scripts" / "guarda_privacidade.py"}" {resto}',
            f'python -c "print(1)" "{self.CS}" {resto}',
            f'python -I "{self.CS}" {resto}',
            f'./python "{self.CS}" {resto}',
            f'D:/malicioso/python "{self.CS}" {resto}',
            f'bash "{self.CS}" {resto}',
            f'cat "{self.CS}" {resto}',
        ):
            self.assertFalse(self.libera(comando), comando)

    def test_nada_junto_com_o_comando(self):
        base = self.comando(f'validar --pasta "{self.PASTA}"')
        for extra in (
            " ; rm -rf x",
            " && rm x",
            " || rm x",
            " | tee x",
            " > x.txt",
            " < x.txt",
            " & rm x",
            "\nrm x",
            "\r\nrm x",
            " $(rm x)",
            " `rm x`",
            " (Remove-Item x)",
            " @(Remove-Item x)",
            " --% rm x",
            " # comentario",
        ):
            self.assertFalse(self.libera(base + extra), repr(extra))
        for valor in (
            '"$(rm x)"',
            '"`rm x`"',
            '"$HOME"',
            '"a\\" "b; rm x; echo " "c"',  # no Bash, \" não fecha a aspa
            '"a\u201d ; rm x ; \u201cb"',  # no PowerShell, aspa curva fecha a aspa
            "'a\u2019 ; rm x ; \u2018b'",
            "'a''b'",
            '"a""b"',
            '"a\nb"',
            "a*",
            "~/x",
            "$HOME",
        ):
            self.assertFalse(self.libera(self.comando(f"validar --pasta {valor}")), valor)

    def test_so_libera_o_script_nunca_a_leitura_de_arquivo(self):
        for ferramenta in ("Read", "Edit", "Write"):
            dados = {"tool_name": ferramenta, "tool_input": {"file_path": str(RAIZ / "referencias" / "guardiao.md")}, "cwd": str(RAIZ), "agent_type": "gestao-de-cs:guardiao-da-carteira"}
            self.assertFalse(guarda_privacidade.liberar(dados), ferramenta)

    def test_lista_vazia_desliga_a_liberacao(self):  # é o que o README manda fazer para desligar
        with mock.patch.dict(guarda_privacidade.LIBERADOS, clear=True):
            self.assertFalse(self.libera(self.comando(f'validar --pasta "{self.PASTA}"')))

    def test_processo_de_verdade(self):
        entrada = {"tool_name": "Bash", "tool_input": {"command": self.comando(f'validar --pasta "{self.PASTA}"')}, "cwd": str(RAIZ), "agent_type": "gestao-de-cs:lider-da-rotina"}
        r = subprocess.run([sys.executable, str(GUARDA)], input=json.dumps(entrada), capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "allow")
        self.assertTrue(r.stdout.isascii())
        del entrada["agent_type"]
        r = subprocess.run([sys.executable, str(GUARDA)], input=json.dumps(entrada), capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.stdout.strip(), "")


class TestComandosLiberadosFicamNaPasta(unittest.TestCase):
    """O hook olha só o comando. Quem segura o caminho é o próprio script."""

    @classmethod
    def setUpClass(cls):
        cls.e = Empresa("completa")
        cls.e.rodada()

    @classmethod
    def tearDownClass(cls):
        cls.e.fechar()

    def test_conferir_nao_le_o_dado_bruto(self):
        pasta = self.e.pasta
        fora = pasta.parent / "fora-da-pasta.md"
        fora.write_text("R$ 123.456,78", encoding="utf-8")
        self.addCleanup(fora.unlink)
        (pasta / "com-nomes").mkdir(exist_ok=True)
        (pasta / "com-nomes" / "x.md").write_text("R$ 123.456,78", encoding="utf-8")
        for arquivo in (f"4-dados/entradas/{REF}/contas.csv", "4-dados/.privado/rotulos.csv", "4-dados/.PRIVADO/rotulos.csv", "com-nomes/x.md", "../fora-da-pasta.md", fora):
            for comando in ("conferir-numeros", "restaurar-nomes"):
                codigo, saida = rodar(comando, "--pasta", pasta, "--arquivo", arquivo)
                self.assertEqual(codigo, 2, f"{comando} {arquivo}: {saida}")
                self.assertNotIn("123.456", saida)

    def test_arquivo_que_nao_existe(self):
        codigo, saida = rodar("conferir-numeros", "--pasta", self.e.pasta, "--arquivo", "2-metas/nao-existe.md")
        self.assertEqual(codigo, 2)
        self.assertIn("não achei", saida)

    def test_nomes_nao_viram_caminho(self):
        pasta = self.e.pasta
        for conta in ("../../fora", "..\\..\\fora", "..", "a/b"):
            codigo, _ = rodar("nova-ficha", "--pasta", pasta, "--conta", conta)
            self.assertEqual(codigo, 2, conta)
        self.assertFalse((pasta.parent / "fora").exists())
        codigo, _ = rodar("colunas", "--pasta", pasta, "--entrada", "../..")
        self.assertEqual(codigo, 2)


if __name__ == "__main__":
    unittest.main()
