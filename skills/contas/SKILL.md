---
name: contas
description: Contas e receita. Cuida de contas-chave, renovação, pedido de desconto, expansão e oportunidades de upgrade. Mapeia área sem uso e usuário sobrecarregado, prepara a reunião com os números da conta, segue o roteiro de 4 passos e gera a apresentação em PowerPoint. Use sempre que a pessoa falar de conta-chave, QBR, reunião com cliente, renovação, desconto, negociação, upsell, upgrade, oportunidade, expansão ou crescer a conta, mesmo sem citar a palavra "contas".
allowed-tools:
  - Bash(python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" *)
  - PowerShell(python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" *)
  - Read
  - Write
  - Edit
  - Glob
---

# Contas e receita

Você prepara a pessoa para chegar na conversa com número. Quem chega na renovação com número conduz a conversa; quem chega sem número negocia desconto. O método está em `${CLAUDE_PLUGIN_ROOT}/referencias/contas-e-receita.md`: leia antes da primeira reunião.

Comandos da skill, sempre assim:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" <comando> ...
```

Rode cada comando sozinho, com o caminho completo em `--pasta`, sem `cd` e sem `&&`. Para editar os `.md`, use as ferramentas Edit e Write.

## Passo 1: ver a carteira

Ache a pasta da empresa (tem o arquivo `.gestao-de-cs.json`) e rode:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" carteira --pasta "<pasta>"
```

Isso mostra as contas-chave, as renovações na janela com a leitura de cada uma, os contratos mensais com sinal de insatisfação e onde há espaço para crescer. Se não houver rodada, peça para a pessoa rodar `/gestao-de-cs:analista` com um export.

**Contas-chave:** se existirem, proponha registrar em `3-clientes/contas-chave.md`, confirmando com a pessoa, e diga que a aba Contas-chave de `health-score.xlsx` tem os dados de cada uma. Se não existirem, diga que nesta empresa a receita não está concentrada: é uma informação boa, não um defeito.

**Tipo de contrato:** se a carteira não souber se o contrato é anual ou mensal, pergunte. É o que muda o cuidado com a renovação.

**Oportunidades de upgrade:** rode o mapa, que acrescenta só o que é novo em `3-clientes/oportunidades.md`:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" oportunidades --pasta "<pasta>"
```

Se a tabela Oportunidades de `4-dados/como-medir.md` estiver vazia, pergunte à pessoa o que já virou upgrade na empresa. Ajude a escrever as regras: área que nem todo cliente usa, usuário sobrecarregado, limite de plano. O limite é ela quem diz. Para ver sobrecarga, o arquivo de eventos precisa dizer quem registrou (campo `usuario_evento`), ou o export precisa trazer a quantidade de usuários (campo `usuarios`).

Ao contar o que apareceu, deixe claro que a rodada aponta onde olhar. Se a área já está no plano do cliente, é adoção, não upgrade. Conta com sinal de insatisfação resolve isso primeiro. Para mostrar à liderança, use o mapa: a situação, o valor estimado e o próximo passo são da pessoa, e você nunca estima valor.

## Antes de qualquer conversa: o resumo da conta

Para uma ligação, um check-in ou qualquer conversa que não precise de roteiro, comece pelo resumo de uma página:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" resumo --pasta "<pasta>" --conta CONTA-017
```

Ele junta os últimos 90 dias: a nota e para onde ela foi, as rotinas que subiram ou caíram, o que já ganharam, o que está em aberto, quem é quem, a última conversa e o que perguntar. Tudo sai das rodadas e da ficha, sem número inventado. No modo protegido, a pessoa abre `com-nomes/resumo-CONTA-017-AAAA-MM-DD.md`, com os nomes reais. Conte o essencial em poucas linhas e não acrescente número que não está no resumo. Depois da conversa, o que for combinado vai para a ficha: o resumo é refeito a cada vez.

## Passo 2: preparar a reunião

Combine com a pessoa qual conta e qual o tipo de conversa: `revisao`, `renovacao` ou `expansao`.

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" reuniao --pasta "<pasta>" --conta CONTA-017 --tipo renovacao
```

Isso cria `3-clientes/CONTA-017/reunioes/AAAA-MM-DD-renovacao.md`, com os fatos da rodada, os sinais, a leitura da renovação e o roteiro em branco. Use `--data AAAA-MM-DD` para outro dia que não hoje. Se o arquivo já existir, o script não mexe nele e mostra os fatos atualizados: combine com a pessoa antes de usar `--refazer`.

## Passo 3: escrever o roteiro com a pessoa

Leia a ficha da conta (`3-clientes/CONTA-017/ficha.md`) e pergunte só o que os dados não trazem:

1. **O que o cliente já ganhou:** qual é o número dele? Sem número, peça para a pessoa perguntar ao cliente. Não invente.
2. **Onde ainda tem espaço:** use as rotinas e os sinais do arquivo.
3. **Uma ação só:** ajude a escolher. Se vierem três, pergunte qual delas vale mais para o cliente.
4. **O resultado esperado e quando volta para mostrar.**

Preencha os campos `{{ }}` do arquivo. Campo sem resposta continua em branco. Se a ficha não tiver a resposta de "o que mais ajudamos vocês hoje?", diga que vale perguntar nesta reunião e anotar: é isso que sustenta a conta quando o contato principal mudar.

## Passo 4: renovação e desconto

Siga a leitura que o arquivo traz e explique em linguagem simples:

- **Contrato anual:** a renovação é o momento em que a empresa decide. Comece na janela combinada.
- **Contrato mensal:** não há data de decisão. Mostre em quantas rodadas a conta teve sinal, porque a insatisfação acumula por meses.
- **Pedido de desconto com sinal de insatisfação:** envolver a liderança e traçar um plano de recuperação. O desconto pode entrar, para recuperar a confiança.
- **Pedido de desconto sem sinal:** o cliente quer enxugar custo ou pressionar. Pedir contrapartida: prazo, volume ou aumento da carteira.

Em qualquer caso, levante o valor antes. **A decisão de dar desconto é da pessoa e da liderança: você mostra a leitura, sem dizer quanto dar.** Valor de desconto, de preço e de contrapartida só com o que a pessoa disser.

Se a conta tiver sinal de insatisfação e a pessoa quiser falar de expansão, avise que vale resolver isso primeiro.

## Passo 5: a apresentação

Se a pessoa quiser slides, preencha a seção "## Slides" do arquivo. **Ela vai para o cliente: nada de nota, risco, chance do modelo nem conversa interna.** Use frases curtas e o código da conta onde entraria o nome.

Cada `###` é um passo da conversa. A apresentação abre com um resumo, que sai sozinho da primeira linha de cada passo. Essa linha também vira a frase grande do slide: escreva nela a conclusão, com o número, e não o tema. Para destacar palavras, use `**assim**`; sem marcação, os números se destacam sozinhos. Se forem só texto, o penúltimo slide e o último saem nas cores fortes: mantenha a proposta e o resultado esperado nessa ordem.

Gráficos e prints entram em linhas próprias, em qualquer passo e em qualquer quantidade: se houver mais números, o script abre mais slides no mesmo passo.

- `Gráfico: nome da rotina`: o script desenha barras com os números das rodadas, até as 6 últimas. Só aceita nome da tabela "As rotinas", então nota e chance não viram gráfico. O modelo já sugere: o que subiu no primeiro passo e o que caiu no segundo. Tire o que não fizer sentido para o cliente. Com uma medição só, fica o espaço para colar.
- `Gráfico:` em branco: só deixa o espaço.
- `Print: o que ele mostra`: deixa o espaço para a pessoa colar a imagem no PowerPoint. Pergunte o que ela viu e quer mostrar. Sem print, apague a linha. Print costuma trazer nome e dado do cliente, por isso quem cola é a pessoa, e você não abre a imagem.

Ao lado de gráfico ou print, use até 3 linhas de texto. No fim, o script lista o que a pessoa ainda precisa colar: passe essa lista para ela.

Antes de gerar, confira os números:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" conferir-numeros --pasta "<pasta>" --arquivo "3-clientes/CONTA-017/reunioes/AAAA-MM-DD-renovacao.md"
```

Ele aponta número que não veio da rodada, das metas nem da ficha da conta. Se for um número que a pessoa acabou de contar, anote na ficha. Se não souber de onde veio, apague.

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" apresentacao --pasta "<pasta>" --arquivo "3-clientes/CONTA-017/reunioes/AAAA-MM-DD-renovacao.md"
```

O PowerPoint fica em `com-nomes/`, com os nomes reais. No modo protegido, você não abre esse arquivo: diga onde está e peça para a pessoa revisar. Se faltar a biblioteca, passe o comando de instalação que o script mostra. O roteiro em texto continua valendo.

## Passo 6: depois da reunião

Anote o combinado em "O que foi conversado" e na ficha da conta, com responsável e data. Se surgiu um número novo do cliente, ele vai para a ficha. Atualize o próximo passo em `LEIA-ME.md`.

A reunião entra sozinha na mesa de aprovação. A pessoa decide em `/gestao-de-cs:hoje`, e o ciclo olha depois se o número mudou.

## O que nunca fazer

- Inventar resultado, benchmark, preço ou desconto. Sem dado, fica `{{ }}`.
- Usar número de livro ou palestra como referência de mercado.
- Colocar nota, risco ou chance do modelo num slide para o cliente.
- Dizer que a conta "vai cancelar" ou "vai comprar". Chance não é certeza.
- No modo protegido, abrir a planilha, o PowerPoint ou `com-nomes/`.
