# Como medir: {{EMPRESA}}

A nota nasce daqui. Cada linha é uma rotina que prova que o cliente está tendo valor.

## O que fazer

- Preencher os indicadores com o Consultor. Começar com poucos: os que provam valor, mais financeiro e chamados.

## O que foi conversado

- {{DATA}}: arquivo criado.

## Indicadores

- **como ler:** `contagem` (número no período), `última data` (data do último registro), `eventos` (uma linha por registro no arquivo) ou `categoria` (rótulo, como "em dia").
- **frequência esperada:** `8` em contagem; `30 dias` em última data; `padrão da conta` para usar o intervalo da própria conta; `8 em 30 dias` em eventos; `em dia=100; atrasado=0` em categoria.
- **subir é:** `bom`, `ruim` ou por etapa, como `Implantação: bom; demais: ruim`. Em `última data`, deixe vazio.
- **onde está o dado:** o nome exato do arquivo, como `contas.csv`. Antes de o export chegar, pode ser o nome do sistema. Sem dado hoje, deixe vazio: a rotina entra em "o que falta medir".
- **coluna:** a coluna do export. Em `eventos`, deixe vazia.
- **coluna anterior:** a mesma medida no período anterior. É o que permite comparar a conta com ela mesma já na primeira rodada.

| id | bloco | rotina | dado que prova | onde está o dado | coluna | coluna anterior | como ler | frequência esperada | criticidade | subir é |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| {{id}} | {{rotina, financeiro ou chamados}} | {{rotina}} | {{dado}} | {{arquivo}} | {{coluna}} | {{coluna}} | {{como ler}} | {{frequência}} | {{alta, média ou baixa}} | {{bom ou ruim}} |

## Oportunidades

O que configura uma oportunidade de upgrade nesta empresa. O limite é decisão da empresa, não um número de mercado. Mesmo sem nada aqui, a rodada aponta a rotina que a conta não usa e as outras usam.

| oportunidade | rotina | como ler | limite | o que oferecer |
| --- | --- | --- | --- | --- |
| {{exemplo: usuário sobrecarregado}} | {{id da rotina}} | {{sem uso, um usuário concentra, volume por usuário, acima de ou abaixo de}} | {{ }} | {{exemplo: mais acessos}} |

## Regras

Valores usados nos alertas. São pontos de partida da skill, não benchmark de mercado: ajuste para a sua empresa.

| regra | valor |
| --- | --- |
| modelo de receita | {{assinatura ou recompra}} |
| contrato padrão | {{anual ou mensal, se for igual para todas as contas}} |
| variação para alerta | 30 |
| mínimo absoluto | 2 |
| cobertura mínima | 40 |
| renovação próxima | 90 |
| sem contato | 60 |
| queda de nota | 15 |
| mínimo de casos para prever | 30 |
| aumento mínimo de receita | 5 |
