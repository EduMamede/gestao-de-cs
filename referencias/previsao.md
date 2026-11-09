# Previsões

O plugin tenta responder três perguntas: quem pode cancelar em 90 dias, para onde vai o uso de cada rotina e quem pode aumentar a receita em 90 dias. Quem faz isso é um modelo estatístico, a regressão logística da biblioteca gratuita scikit-learn, rodando no computador da pessoa. Nenhum LLM entra nessa conta e nenhum dado sai do computador para treinar.

A biblioteca é opcional. Sem ela, todo o resto funciona igual:

```bash
python -m pip install scikit-learn
```

As previsões saem junto com a `rodada`, em `previsoes.md`, na aba Previsões da planilha e em `previsoes`, no `resumo.json`. O comando `prever` mostra as da última rodada.

## As três regras

1. **Só olha o passado.** Para cada data do histórico, o modelo vê só o que já tinha acontecido naquele dia. Dado do export que não tem data, como a receita de hoje, não entra nas fotos antigas.
2. **Com poucos casos, não treina.** Responde "ainda não dá", diz quantos casos já há e o item entra em "o que falta medir". O mínimo começa em 30 casos. É um ponto de partida nosso, não um benchmark: mude em `4-dados/como-medir.md`, na tabela Regras, em "mínimo de casos para prever".
3. **Só mostra o que passou no teste.** O plugin volta no tempo, treina só com o que se sabia em cada data e compara com o que aconteceu depois. A previsão aparece só se o modelo acertou mais que a comparação simples. Se não acertou, ele diz isso e não lista conta nenhuma.

"Acertou mais" tem três exigências:

- **Pelo menos 20 contas no teste.** Com menos, sortear as contas dá uma segurança que não existe.
- **Acerto mínimo na medida AUC, em que 0,5 é sorteio:** 0,65 em churn e aumento, que têm poucos casos e sofrem mais com o acaso, e 0,6 no uso, que tem muitos casos e uma comparação mais forte.
- **Ganho que continua positivo ao sortear as contas do teste 500 vezes.** O corte começa em 1 de cada 20 sorteios e é dividido pelo número de previsões testadas, porque quem testa várias coisas de uma vez acerta alguma por sorte. Com 2 rotinas, são 6 previsões, e o corte fica em cerca de 1 em 120.

## O que cada previsão usa

| previsão | o caso que ela aprende | comparação simples | de onde vem o histórico |
| --- | --- | --- | --- |
| **Churn** | a conta cancelou nos 90 dias seguintes | a nota do health score | contas canceladas com data, e atividades com data ou rodadas |
| **Engajamento** | o uso do período seguinte mudou contra o normal da conta | um modelo só com o nível e o movimento da própria rotina | atividades com data, ou rodadas |
| **Aumento de receita** | a receita subiu pelo menos 5% em 90 dias | a nota do health score | receita em várias rodadas |

- **Mudança de uso** segue a mesma régua da mudança de padrão: "variação para alerta" e "mínimo absoluto". O normal da conta é a média dos três últimos períodos. Só as rotinas contadas por período, em que subir é bom, entram aqui. Uma conta só aparece com 50% ou mais de chance.
- **Aumento mínimo** muda em "aumento mínimo de receita", na mesma tabela.
- **Churn conta contas; uso conta mudanças.** Uma conta só cancela uma vez, e muda de uso várias. Por isso o uso pode ficar pronto antes do churn, mas nunca com menos de 20 contas. O churn costuma demorar, porque poucos cancelamentos não ensinam nada.
- **Recompra:** sem contrato, não há data de cancelamento, então o churn fica de fora. O uso e o aumento de receita continuam valendo.

## Como ter histórico mais cedo

- **Atividades com data** (um arquivo de `eventos`): uma única exportação já traz os meses passados, e o plugin remonta como cada conta estava em cada data.
- **Contas canceladas:** exporte também quem saiu, com a data de saída.
- **Receita e rotinas sem data:** só existem nas rodadas. Toda rodada guarda uma foto. Quem tem exports antigos pode gerar as rodadas dos meses passados, do mais antigo para o mais novo:

```bash
python scripts/cs.py receber --pasta "<pasta>" --arquivo "<export antigo>" --data 2026-01-31
python scripts/cs.py rodada --pasta "<pasta>" --data 2026-01-31 --entrada 2026-01-31
```

## Como ler o resultado

- **É chance, não certeza.** Serve para escolher onde olhar primeiro.
- **"O que pesou" mostra o que veio junto, não a causa.** O número da conta está certo. O motivo real de um cliente sair, só a conversa revela.
- **O teste diz quanto confiar.** "De 28 contas que cancelaram, 25 estavam entre as 20% mais apontadas; a nota apontaria 9" é a melhor forma de explicar o resultado.
- **Porcentagem errou de tamanho?** Se a média prevista ficou longe do que aconteceu no teste, o plugin avisa, não calcula a receita em risco nem o valor estimado e pede para usar a lista só como ordem de prioridade.
- **A previsão não muda a ordem do "mais crucial".** Ela aparece ao lado, em seção própria. Quem decide é a pessoa.

## Como foi testado

Em empresas inventadas, em `tests/gerar_historico.py`: uma com padrão plantado, que a nota não enxerga e o modelo tem que achar, e outra em que cancelamento e aumento são sorteados, e o modelo tem que admitir que não ganhou. **Ainda não foi testado com dados reais de uma empresa.** O número de acerto de cada empresa é o do teste dela, e não vale como benchmark para outra.

Os cortes acima vieram dessa medição. Com um corte mais frouxo, o modelo passou por engano em algumas empresas só de ruído, inclusive numa com 12 contas. A medição final usou sementes que não serviram para escolher o corte, e dá para repetir com `python tests/medir_previsao.py`:

| cenário | contas | empresas | churn pronto | uso pronto | aumento pronto |
| --- | --- | --- | --- | --- | --- |
| só ruído | 40 | 20 | 0 | 0 | 0 |
| só ruído | 140 | 30 | 0 | 0 | 0 |
| só ruído | 220 | 15 | 0 | 0 | 0 |
| padrão plantado | 40 | 10 | 0 (poucos casos) | 3 | 0 (poucos casos) |
| padrão plantado | 140 | 8 | 5 | 7 | 6 |
| padrão plantado | 220 | 5 | 5 | 5 | 5 |

Zero em 65 não prova que um falso positivo nunca vai acontecer. Prova que ele ficou raro nesses cenários. Com 1.000 contas, a rodada levou cerca de 20 segundos.

## Privacidade

O modelo roda dentro do `cs.py`. No modo protegido, a IA lê só código da conta, chance, nome da rotina e números da própria conta. Texto livre e dado pessoal não entram no modelo. Uma mensagem de erro nunca traz valor dos dados.
