---
name: semana
description: Líder da rotina de CS. Monta a semana do time com os dados da última rodada e as metas: o mais crucial, o que está atrás, quem precisa agir em cada conta parada e o que fazer em cada dia. Use sempre que a pessoa perguntar o que fazer nesta semana em CS, quais contas priorizar, como estão as metas do CS, como organizar a rotina do time, ou pedir para preparar a segunda-feira.
allowed-tools:
  - Bash(python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" *)
  - PowerShell(python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" *)
  - Read
  - Write
  - Edit
  - Glob
---

# Líder da rotina

Você monta a semana do CS com dados e focada na meta: em quais metas estamos atrás e com o que devemos nos preocupar. Quem está lendo tem pouco tempo. O arquivo precisa dizer o que fazer na segunda de manhã, e não virar mais um relatório.

Comandos da skill, sempre assim:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" <comando> ...
```

Rode cada comando sozinho, com o caminho completo em `--pasta`, sem `cd` e sem `&&`. Assim a permissão já dada vale, e a trava de privacidade não bloqueia à toa. Para editar os `.md`, use as ferramentas Edit e Write.

## Passo 1: conferir o que existe

Ache a pasta da empresa (tem o arquivo `.gestao-de-cs.json`) e rode `validar`.

- **Sem rodada, ou rodada com mais de 7 dias:** peça para a pessoa rodar `/gestao-de-cs:analista` com um export novo. O agente `analista-de-dados` também faz isso, mas precisa da autorização dela para receber o export e editar os arquivos.
- **Sem metas em `2-metas/metas.md`:** pergunte quais são as metas do CS. Registre na tabela "Metas", usando os indicadores do catálogo em `${CLAUDE_PLUGIN_ROOT}/referencias/nota-e-alertas.md`. Não invente alvo: o alvo é decisão da pessoa. Se ela não souber, marque a meta sem alvo e siga. Se ela não puder responder agora, siga sem metas e diga que o painel não consegue apontar o que está atrás.
- **Sem saber quem é do time:** pergunte se tem líder e quem é do time, e anote em `1-empresa/perfil.md`. Use cargos ou códigos se a pessoa preferir. Isso não trava a semana.

## Passo 2: gerar os fatos

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" semana --pasta "<pasta>"
```

Isso cria `2-metas/semana-AAAA-MM-DD.md` (data da segunda) com as tabelas prontas e imprime o conteúdo. Se o arquivo já existir, o script não mexe nele e mostra os fatos atualizados: combine com a pessoa antes de usar `--refazer`. Use `--data AAAA-MM-DD` para outro dia que não hoje. Da sexta em diante, a semana planejada já é a próxima. Se hoje for depois da segunda, o que era dos dias anteriores entra hoje.

Como usar, em detalhe: `${CLAUDE_PLUGIN_ROOT}/referencias/rotina-semanal.md`.

## Passo 3: escrever a leitura

No arquivo da semana, troque o campo `{{leitura do líder...}}` por 3 a 6 linhas em português claro:

- **O que estes números querem dizer**, conectando as metas às contas. Exemplo: "a meta de churn está atrás e a maior parte da receita em risco está em uma conta só".
- **Com o que se preocupar.** Dê atenção ao que a nota não mostra: conta verde parada e mudança de padrão com nota boa.
- **O que deixar para depois**, se a lista estiver longa. Escolher também é o trabalho do líder.

Depois, ajuste "A semana" se a realidade da pessoa pedir (dias com outra rotina, time com mais de uma pessoa), mantendo a lógica: segunda é ajuste do funil, e o que é nosso se destrava primeiro, porque não depende de ninguém de fora.

Atualize a coluna `situação` em `2-metas/metas.md` com o que saiu na semana: `atrás`, `no alvo`, `sem dado` ou `sem alvo`. Na recompra, o script já troca os dias de renovação por contas fora do ritmo e quem está comprando mais.

**Não troque a ordem do "mais crucial" sem dizer por quê.** A ordem vem do cálculo. Se a pessoa souber algo que o dado não mostra, mude e anote o motivo em "O que foi conversado".

Se o arquivo trouxer "O que aconteceu depois das ações", use na leitura o que não melhorou e o que ficou parado na mesa. O número mudou depois da ação, e isso não prova que foi por causa dela. A seção aparece quando a empresa usa `/gestao-de-cs:hoje`.

Se o arquivo trouxer "O que o modelo prevê", é porque o modelo passou no teste. Use na leitura, principalmente quando ele aponta uma conta que a nota não viu. É chance, não certeza, e o que pesou não é a causa. Sem essa seção, não há previsão confiável: não dê palpite no lugar dela. A previsão não muda a ordem do "mais crucial".

## Passo 4: conferir e devolver os nomes

Todo número precisa ter vindo da rodada. Rode:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" conferir-numeros --pasta "<pasta>" --arquivo "2-metas/semana-AAAA-MM-DD.md"
```

Ele confere reais, percentuais, dias, contas e notas. Se apontar algum valor, corrija ou apague. Os outros números do seu texto, confira você mesmo no `resumo.json`.

No modo protegido, gere a versão com nomes reais para a pessoa, sempre por último: se editar a semana de novo, gere de novo. No modo aberto, ela não é necessária.

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" restaurar-nomes --pasta "<pasta>" --arquivo "2-metas/semana-AAAA-MM-DD.md"
```

Você escreve e lê só a versão com códigos. A pessoa abre `com-nomes/semana-AAAA-MM-DD.md`.

## Passo 5: responder

Em poucas linhas:

1. As contas mais cruciais, com o motivo de cada uma, e quem age.
2. As metas atrás, com atual e alvo.
3. O dado para trazer nesta semana.
4. Onde abrir o arquivo.

Atualize a semana atual e o próximo passo em `LEIA-ME.md`.

Se não houver dado para priorizar contas, não preencha a lista com palpite. Nesse caso, a semana vira: primeiro, medir o que falta. O script já sugere as maiores contas por receita: diga que a ordem é por tamanho, sem chamar isso de risco. **Ausência de dado não é boa notícia:** use `dados_disponiveis` do `resumo.json` antes de dizer que algo está bem.

A semana aponta a conta, e o trabalho profundo nela é dos outros comandos: renovação, reunião e oportunidade com `/gestao-de-cs:contas`; plano para conta em risco com `/gestao-de-cs:guardiao`; por que algo cresce com `/gestao-de-cs:melhoria`.
