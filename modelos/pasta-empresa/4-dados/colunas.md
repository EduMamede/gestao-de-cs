# Ligação das colunas: {{EMPRESA}}

Liga o nome das colunas dos seus exports aos campos padrão da skill. O Analista sugere e você confirma.

## O que fazer

- Confirmar a ligação a cada export novo que mudar de formato.

## O que foi conversado

- {{DATA}}: arquivo criado.

## Arquivos

`contas` tem uma linha por conta. `eventos` tem uma linha por registro (chamado, pedido, login) e precisa de uma coluna de data.

| arquivo | tipo |
| --- | --- |
| {{arquivo.csv}} | {{contas ou eventos}} |

## Colunas

Use `conta_nome` ou `conta_id` em todo arquivo. Coluna de texto livre fica de fora: não ligue, ou marque como `bloqueada`.

| arquivo | coluna | campo |
| --- | --- | --- |
| {{arquivo.csv}} | {{coluna}} | {{campo}} |
