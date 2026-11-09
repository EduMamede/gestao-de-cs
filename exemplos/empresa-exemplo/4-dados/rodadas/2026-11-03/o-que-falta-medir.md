# O que falta medir na rodada de 2026-11-03

## O que fazer

- O export não traz nenhuma conta cancelada: Exporte também quem saiu, com a data de saída.

## O que foi conversado

- Nada ainda. Anote aqui o que for combinado sobre esta rodada.

## A lista, em ordem de prioridade

| prioridade | o que falta | por que importa | primeiro passo |
| --- | --- | --- | --- |
| alta | O export não traz nenhuma conta cancelada | Quase sempre é export só de ativas. Sem as canceladas, não dá para saber o churn nem fazer o teste da conta perdida. | Exporte também quem saiu, com a data de saída. |
| alta | 1 conta empacada sem motivo | Sem o motivo, ninguém sabe quem precisa agir. | Registre o motivo no sistema de origem, para vir no próximo export. Para decidir já, anote na aba O que empaca. |
| média | Meta 'Churn abaixo de 2% ao mês' sem dado | Não dá para saber se a meta está atrás. | Traga o dado do indicador 'churn_contas_30d'. |
| média | Próximo passo (só 2% das linhas têm) | Conta parada sem próximo passo continua parada. | Complete no sistema de origem, para vir no próximo export. |
| média | Data do próximo contato (só 2% das linhas têm) | Mostra quem ficou sem data combinada. | Complete no sistema de origem, para vir no próximo export. |
| média | 2 contas sem nota por falta de dado | Conta sem nota não entra na comparação. | Veja na aba Medições o que está vazio nessas contas. |
| baixa | Tipo de contrato | No anual, a renovação é uma decisão com data. No mensal, a insatisfação acumula até cancelar, e o cuidado é outro. | Inclua o tipo de contrato no export, ou anote 'contrato padrão' em 4-dados/como-medir.md. |
| baixa | Receita do período anterior | Sem ela não dá para calcular retenção bruta e líquida. | Exporte a receita de 12 meses atrás junto com a atual. |
| baixa | Histórico para prever churn: 0 de 30 casos | Com pouco histórico, o modelo não treina e a previsão fica de fora. | Exporte também quem saiu, com a data de saída, e as atividades com data dos meses passados. |
| baixa | Histórico para prever o uso: 0 de 20 contas | Com pouco histórico, o modelo não treina e a previsão fica de fora. | Exporte as atividades com data dos meses passados, ou guarde uma rodada por semana. |
| baixa | Histórico para prever aumento de receita: 0 de 30 casos | Com pouco histórico, o modelo não treina e a previsão fica de fora. | Rode toda semana, ou gere rodadas dos meses passados a partir de exports antigos, com --data e --entrada. |
| baixa | O que configura oportunidade de upgrade nesta empresa | Sem isso, a rodada só aponta a rotina sem uso. Sobrecarga de usuário e limite de plano ficam de fora. | Pergunte o que já virou upgrade aqui e anote na tabela Oportunidades de 4-dados/como-medir.md. |
