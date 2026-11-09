---
name: melhoria
description: Melhoria contínua. Olha o que cresce e pergunta por quê, organiza pesquisa, NPS, entrevistas e indicação, mapeia o que dá muito trabalho e propõe mudanças para a pessoa aprovar. Use sempre que a pessoa perguntar por que os chamados ou o churn aumentaram, quiser fazer pesquisa com clientes, NPS, entrevista, caso de sucesso, indicação ou reduzir o que dá trabalho, mesmo sem citar a palavra "melhoria".
allowed-tools:
  - Bash(python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" *)
  - PowerShell(python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" *)
  - Read
  - Write
  - Edit
  - Glob
---

# Melhoria contínua

Olhe o que cresce e pergunte por quê. **Você propõe, não muda sozinho:** a pessoa aprova, e a mudança fica registrada. O método está em `${CLAUDE_PLUGIN_ROOT}/referencias/melhoria.md`.

Comandos da skill, sempre assim:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" <comando> ...
```

Rode cada comando sozinho, com o caminho completo em `--pasta`, sem `cd` e sem `&&`. Para editar os `.md`, use as ferramentas Edit e Write.

## Passo 1: ver o que mudou

Ache a pasta da empresa (tem o arquivo `.gestao-de-cs.json`) e rode:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" melhoria --pasta "<pasta>"
```

Isso mostra o que mudou na carteira, os temas que cresceram, quem saiu e com quem conversar. Se não houver rodada, peça para a pessoa rodar `/gestao-de-cs:analista`. Para ver os temas, o arquivo de eventos precisa de uma coluna de categoria, ligada ao campo `tema_evento`: uma lista curta, como a categoria do chamado, nunca texto livre.

## Passo 2: perguntar por quê

O número mostra o que mudou. O porquê vem da conversa. Para cada mudança que preocupa, pergunte à pessoa o que ela vê no dia a dia. Sem resposta, escreva como hipótese e proponha como descobrir: quem ouvir e o que olhar.

Registre em `5-melhoria/problemas.md`: o que dá trabalho, por quê, a ação e, depois, o resultado.

Se muita conta saiu sem motivo específico, esse é o primeiro problema. "Não viu valor" não ensina nada.

## Passo 3: ouvir os clientes

Quando a pessoa quiser pesquisa ou entrevista, use os grupos do comando e as perguntas da referência, adaptando à empresa. Entreviste engajados, novos e ex-clientes, e compare as respostas. Pergunte sobre o que aconteceu, não sobre o que a pessoa faria.

- **Detratores:** proponha uma conversa para fechar o ciclo.
- **Promotores:** proponha o pedido de indicação, com processo e medindo quantas vieram.
- **NPS:** use para ver a tendência da base, nunca para avaliar uma conta sozinha.

Roteiro e mensagem são rascunhos: quem envia é a pessoa. Anote as respostas em `5-melhoria/problemas.md` ou na ficha da conta. No modo protegido, use só códigos e cargos.

## Passo 4: propor mudanças

Toda proposta vai para `5-melhoria/sugestoes.md`, com a data, o que mudar, o motivo e `aprovada?` em branco. Pode ser mudar a jornada, um prazo, um processo, uma rotina da nota ou algo para levar ao produto.

**Se a proposta mexe em peso ou rotina da nota, avise:** quebra a comparação com o passado. Em geral, vale manter a fórmula por um tempo. A rodada marca a data da mudança.

A sugestão entra sozinha na mesa de aprovação, e a pessoa pode decidir em `/gestao-de-cs:hoje` ou na própria tabela. Se houver uma rotina que deve mudar, anote-a na decisão: o comando `resultado` compara a carteira antes e depois.

**Só altere `como-medir.md`, `jornada.md` ou qualquer regra depois que a pessoa aprovar.** Aí, registre em `5-melhoria/mudancas.md` e, na rodada seguinte, olhe se funcionou.

## O que nunca fazer

- Afirmar a causa só pelo número. Correlação não é causa.
- Mudar regra, peso ou processo sem aprovação.
- Inventar resposta de cliente, nota ou benchmark.
- Mandar pesquisa ou mensagem pela pessoa.
- No modo protegido, abrir a planilha, `4-dados/entradas/`, `4-dados/.privado/` ou `com-nomes/`.
