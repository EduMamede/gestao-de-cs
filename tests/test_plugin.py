"""Cada agente carrega uma skill que existe. Sem isso, ele precisa ler o método fora da pasta de trabalho, e a leitura é recusada."""
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


class TestAgentes(unittest.TestCase):
    def test_cada_agente_carrega_uma_skill_que_existe(self):
        agentes = sorted((RAIZ / "agents").glob("*.md"))
        self.assertEqual(len(agentes), 6)
        for agente in agentes:
            texto = agente.read_text(encoding="utf-8")
            achado = re.search(r"^skills:\s*\n\s*-\s*gestao-de-cs:([\w-]+)\s*$", texto, re.M)
            self.assertIsNotNone(achado, agente.name)
            self.assertTrue((RAIZ / "skills" / achado.group(1) / "SKILL.md").exists(), agente.name)


if __name__ == "__main__":
    unittest.main()
