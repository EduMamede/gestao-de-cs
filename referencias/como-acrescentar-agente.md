# Como acrescentar um agente

Os seis agentes leem a mesma pasta da empresa, o mesmo `resumo.json` e o mesmo `contas.json`. Um agente novo entra sem mudar o que já existe.

Para acrescentar um agente:

1. `skills/<nome>/SKILL.md`, com o método e o `allowed-tools`.
2. `agents/<nome>.md`, fino, carregando a skill com `skills:`.
3. A referência do método em `referencias/`.
4. Se precisar de comando novo em `cs.py`, inclua em `LIBERADOS`, em `scripts/guarda_privacidade.py`, só se ele ficar na pasta da empresa e não gravar por cima do que a pessoa escreveu. Atualize a lista do README e de `privacidade.md`.
5. Uma linha nas tabelas do README e do `LEIA-ME.md` da empresa.
6. Testes, com resposta conferida à mão.

## O que já está pronto para usar

| de onde | o que traz |
| --- | --- |
| `contas.json` | a foto de cada conta ativa: nota, receita, contrato, sinais, rotinas, chances do modelo e oportunidades |
| `resumo.json` | a carteira: prioridades, metas, `previsoes`, `oportunidades` e `melhoria` |
| `valores.csv` de cada rodada | a tendência de cada conta ao longo do tempo |
| `3-clientes/` | fichas, reuniões, planos e o mapa de oportunidades |
| `5-melhoria/` | sugestões, problemas e mudanças |

## Regras que continuam valendo

Os mesmos modos de privacidade. Só citar número que veio do script. Nomes reais só voltam pelo script, inclusive em apresentação. Previsão só vale com `status` igual a `ok`. Quem propõe não muda sozinho.
