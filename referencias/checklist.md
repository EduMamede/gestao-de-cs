# O checklist

A nota não vem de uma lista pronta de indicadores. Ela nasce do que prova valor nesta empresa, nesta ordem. Faça um bloco por vez.

## 1. O que é importante

- Qual a dor principal que o produto resolve?
- Quais rotinas provam que o cliente está tendo valor? Comece com três a cinco.

Exemplo, um sistema para clínica: acompanhamento do plano, estoque e agenda. A pergunta não é "ele entrou no sistema?", e sim "ele fez o que o sistema existe para fazer?".

## 2. Como medir cada rotina

Para cada rotina: qual registro mostra que ela aconteceu, e onde esse dado está?

| rotina | dado que prova | onde está |
| --- | --- | --- |
| Acompanhamento do plano | há plano lançado e realização pela enfermeira? | sistema |
| Estoque | há entrada e saída? | sistema |
| Agenda | há controle da agenda? | sistema |

Se o dado não existir hoje, mas a rotina importar, anote mesmo assim: deixe vazios `onde está o dado`, `coluna`, `como ler` e, se ninguém souber, a frequência. A rotina entra em "o que falta medir", e esse item vale mais do que um indicador fácil que não prova nada. A confiança da nota cai de propósito, porque falta olhar algo que você disse que importa. Se a rotina não se aplica nesta empresa, não crie a linha.

Antes de o export chegar, `onde está o dado` pode ser o nome do sistema ("CRM"). O Analista troca pelo nome exato do arquivo.

Pergunte também a frequência esperada: quantas vezes por mês uma conta saudável faz isso? Se ninguém souber, deixe vazio: a rotina fica sem nota até definir. Se a pessoa quiser arriscar uma hipótese, escreva o número e anote em "O que foi conversado" que é para rever. Não existe número certo de mercado aqui. "8 por mês" e `8` numa coluna de 30 dias são a mesma coisa.

## 3. Os blocos comuns

- **Financeiro:** o pagamento está em dia? De onde vem esse dado?
- **Chamados:** quantos por conta? Qual o limite aceitável por mês?

## 4. Criticidade

Para cada indicador: alta, média ou baixa. Alta vale 3, média vale 2, baixa vale 1. Pergunte: "se isso parar, o cliente está em risco de sair?".

Mudar a criticidade depois quebra a comparação com o passado. Por isso, é melhor manter a fórmula por um tempo: a ideia de manter a fórmula por 6 a 10 meses vem do livro da SenseData.

## 5. O padrão da própria conta

- A conta fazia X antes. Agora aumentou ou diminuiu?
- Subir é bom ou ruim?

A mudança serve de alerta mesmo com a nota boa. Uma conta que lançava 40 planos e agora lança 12 ainda está acima dos 8 esperados, e a nota não vê. O padrão vê.

Só se fizer sentido, pergunte se a resposta muda por etapa da jornada. Chamado subindo na implantação pode ser engajamento; no 12º mês é alerta. O campo fica assim: `Implantação: bom; demais: ruim`.

Para comparar já na primeira rodada, peça um export com a coluna do período anterior. Sem ela, a comparação começa na segunda rodada.

## 6. Contrato e oportunidades

- **O contrato é anual, mensal ou os dois?** No anual, a renovação é uma decisão com data. No mensal, a insatisfação acumula até cancelar. Se for igual para todas as contas, anote em "contrato padrão", na tabela Regras. Se variar, traga a coluna no export.
- **O que já virou upgrade aqui?** Área que nem todo cliente usa, usuário sobrecarregado que precisa dividir o trabalho, limite de plano. Anote na tabela Oportunidades. O limite é decisão da empresa: se ninguém souber, deixe vazio. Mesmo sem regra, a rodada aponta a rotina que a conta não usa e as outras usam.

## Como preencher `4-dados/como-medir.md`

Uma linha por indicador. Campos pedidos no checklist: rotina, dado que prova, onde está o dado, frequência esperada, criticidade e se subir é bom ou ruim. As colunas `como ler`, `coluna` e `coluna anterior` costumam ser preenchidas depois, com o Analista, quando o export chegar.

| como ler | quando usar | frequência esperada |
| --- | --- | --- |
| `contagem` | o export traz um número por conta no período | `8` |
| `última data` | o export traz a data do último registro | `30 dias` |
| `última data` | a recompra, com o intervalo da própria conta | `padrão da conta` |
| `eventos` | o arquivo tem uma linha por registro | `8 em 30 dias` |
| `categoria` | o export traz um rótulo | `em dia=100; atrasado=0` |

Em `última data`, `subir é` não se aplica: deixe vazio. Em `eventos`, a `coluna` fica vazia, porque a data vem do campo `data_evento` em `colunas.md`. Escolha um nome de rotina que funcione sozinho, porque ele aparece nos alertas: "Pagamento", e não "Pagamento em dia".

Exemplo:

| id | bloco | rotina | dado que prova | onde está o dado | coluna | coluna anterior | como ler | frequência esperada | criticidade | subir é |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| plano | rotina | Acompanhamento do plano | realização lançada | sistema.csv | Planos 30d | Planos 30d ant | contagem | 8 | alta | bom |
| pagamento | financeiro | Pagamento | situação no financeiro | financeiro.xlsx | Situação | | categoria | em dia=100; atrasado=0 | alta | bom |
| chamados | chamados | Chamados | chamado aberto | chamados.csv | | | eventos | 3 em 30 dias | média | ruim |

## Empresa que não é de software

Sem login nem assinatura, a última compra entra no lugar do uso. Em "Regras", use `modelo de receita: recompra`. A pergunta vira: a conta compra menos ou aumentou o intervalo de compra? Compare a conta com o intervalo dela mesma (`padrão da conta`): quem compra a cada trimestre não está em risco depois de 60 dias sem comprar, mas quem compra todo mês está.
