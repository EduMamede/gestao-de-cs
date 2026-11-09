# Como a nota e os alertas funcionam

Nada aqui é benchmark de mercado. São pontos de partida, simples de propósito para qualquer pessoa conseguir conferir à mão.

## A nota de cada rotina (0 a 100)

| como ler | conta |
| --- | --- |
| contagem ou eventos, subir é bom | valor dividido pelo esperado, com teto em 100 |
| contagem ou eventos, subir é ruim | 100 até o limite, caindo até 0 em 3 vezes o limite |
| última data | 100 até o intervalo esperado, caindo até 0 em 3 vezes o intervalo |
| última data, padrão da conta | igual, usando a mediana dos intervalos da própria conta. Precisa de pelo menos 3 registros |
| categoria | o valor combinado em `frequência esperada`. Sem combinar, `em dia` e `pago` valem 100, `atrasado` e `vencido` valem 0 |

## A nota da conta

Média das rotinas com peso pela criticidade: alta vale 3, média vale 2, baixa vale 1.

Rotina sem dado fica fora da média e derruba a confiança. Nunca vira zero, porque falta de dado não é o mesmo que cliente sem uso.

**Faixas:** abaixo de 30, possível churn. De 30 a 69, pode melhorar. De 70 para cima, saudável.

**Grau de confiança:** quanto do peso total tem dado nesta conta. Alta de 80% para cima, média de 50% a 79%, baixa abaixo de 50%.

**Sem nota:** abaixo de 40% do peso com dado (`cobertura mínima`, editável em Regras), a conta fica sem nota.

## O que a nota não vê

A nota compara contas, mas suaviza a curva. Por isso, dois alertas funcionam mesmo com a nota verde:

**O que empaca.** Conta além do prazo da etapa fica como `empacado`. O motivo separa `do cliente` (o CS cobra e ajuda) de `nosso` (destravar internamente). Essa separação muda quem precisa agir.

**Mudança de padrão.** A conta é comparada com ela mesma: com a coluna do período anterior, com a janela anterior de eventos ou com a rodada anterior. Acende quando a variação passa de 30% e de 2 unidades (`variação para alerta` e `mínimo absoluto`, editáveis). Se o movimento for para pior, é alerta. Se for para melhor, é bom sinal, útil para a futura conversa de expansão.

Na recompra, também acende quando os dias sem comprar passam em 30% o intervalo normal da conta.

## Quem olhar primeiro

Cada conta soma pontos pelos sinais. Combinação de sinais pesa mais que um sinal só.

| sinal | pontos |
| --- | --- |
| nota abaixo de 30 | 3 |
| cancelamento agendado | 3 |
| empacada | 2 |
| mudança de padrão para pior | 2 |
| renova na janela e tem outro sinal de risco | 2 |
| nota de 30 a 69 | 1 |
| bloco financeiro com problema | 1 |
| nota caiu 15 pontos ou mais desde a rodada anterior | 1 |
| sem contato além do combinado | 1 |
| renovação vencida | 1 |
| renova na janela, sem outro sinal | 0,5 |

A ordem é pontos vezes receita. Empate vai pelo código da conta. As 3 primeiras com pelo menos 1 ponto formam o "mais crucial": renovação sozinha, em conta sem risco, fica na lista, mas não é crucial.

A coluna **matriz** cruza saúde e receita, usando a receita mediana como corte: salvar (receita alta, nota abaixo de 70), crescer (receita alta, nota boa), manter (receita baixa, nota boa), observar (receita baixa, nota abaixo de 70).

## Contas-chave

A skill soma a receita das maiores contas até chegar a 80%. Se isso der no máximo 20% das contas com receita, existe um grupo de contas-chave. Se não, ela diz que não existe, porque nem toda empresa tem.

## Quando não dá para saber

Ausência de dado não é boa notícia. Por isso, a skill separa os dois casos em tudo que escreve:

- **Churn:** sem nenhuma conta cancelada no export, fica "a preencher", e não 0%. Quase sempre é export só de ativas.
- **Conta cancelada sem data:** fica fora do churn, e isso vira um item de "o que falta medir".
- **Recompra:** não há churn, renovação nem retenção de contrato. Essas métricas somem do painel, e a skill pede para combinar quando uma conta sem comprar conta como perdida.

## Metas: como preencher

- **Alvo:** o número, como `5` ou `5%`. Valor igual ao alvo conta como "no alvo".
- **Prazo:** texto livre, como `dez/2026`. Serve para leitura, e a skill não calcula ritmo até o prazo.
- **Situação:** `atrás`, `no alvo`, `sem dado` ou `sem alvo`. O Líder da rotina atualiza toda semana.
- **`pct_saudaveis`:** conta só as contas que têm nota. As sem nota aparecem em `contas_sem_nota`.

## Teste da conta perdida

Para cada conta cancelada: a skill teria avisado antes de ela sair, pela nota ou pelo alerta de conta parada? O resultado separa os dois casos.

1. Se houver rodada anterior ao cancelamento, usa o dado real daquela rodada.
2. Se não houver, olha a conta 30 dias antes de cancelar: datas e eventos dão para calcular; a contagem do export só vale se a conta saiu nos últimos 30 dias e existir a coluna anterior; rótulos como "em dia" não valem, porque são a foto de hoje.
3. Sem nada disso, a resposta é "não dá para saber".

Quando nada avisou, o resultado é útil: mostra o que ajustar, sempre com a aprovação da pessoa. Se quase todas as contas ativas estiverem saudáveis e mesmo assim houver saída sem aviso, a rodada alerta que a régua pode estar frouxa.

## Catálogo de indicadores para as metas

Use estes nomes na coluna `indicador` de `2-metas/metas.md`:

| indicador | o que é | melhor quando |
| --- | --- | --- |
| `contas_ativas` | contas que não cancelaram | maior |
| `receita_ativa` | receita das contas ativas | maior |
| `nota_media` | média das notas | maior |
| `nota_ponderada` | média das notas com peso pela receita | maior |
| `pct_saudaveis` | % de contas saudáveis, entre as que têm nota | maior |
| `pct_receita_saudavel` | % da receita em contas saudáveis | maior |
| `contas_sem_nota` | contas sem dado suficiente | menor |
| `receita_em_risco` | receita em possível churn | menor |
| `contas_empacadas` | contas além do prazo | menor |
| `empacadas_nosso` | empacadas por nós | menor |
| `empacadas_cliente` | empacadas pelo cliente | menor |
| `alertas_de_padrao` | contas que mudaram para pior | menor |
| `renovacoes_90d` | contas renovando na janela | sem direção |
| `receita_renovando` | receita renovando na janela | sem direção |
| `churn_contas_30d`, `churn_contas_90d`, `churn_contas_12m` | canceladas sobre as que existiam no início | menor |
| `churn_receita_30d`, `churn_receita_90d`, `churn_receita_12m` | receita cancelada sobre a receita do início | menor |
| `nps` | promotores menos detratores | maior |
| `nps_respostas` | contas com nota de NPS | maior |
| `chamados_total` | soma do bloco chamados | menor |
| `grr` | retenção bruta, sem expansão | maior |
| `nrr` | retenção líquida, com expansão | maior |

O NPS fica no painel, e não na nota da conta, porque serve para ver a tendência da base, não para avaliar cliente a cliente. A pessoa pode incluí-lo como rotina se quiser.
