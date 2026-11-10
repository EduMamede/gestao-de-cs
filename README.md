# Gestão de CS

Um plugin para o Claude Code que ajuda uma empresa a gerenciar o Customer Success, a partir de um checklist e dos exports que ela já tem.

Conversa com cliente sem dado é opinião. E o maior erro que vejo em CS é o time sem sistema, apagando incêndio. Este plugin é o método que usei nas consultorias, empacotado para qualquer pessoa rodar no próprio computador.

**Estado:** em fase de teste. Os seis agentes estão construídos, mas só foram testados com dados inventados.

## O que ele faz

| agente | comando | o que entrega |
| --- | --- | --- |
| **Consultor de CS** | `/gestao-de-cs:consultor` | conduz o checklist, sugere e cria a pasta da empresa, registra o que foi conversado |
| **Analista de dados** | `/gestao-de-cs:analista` | liga as colunas, mede as rotinas, gera a planilha de health score, o painel geral e as previsões |
| **Líder da rotina** | `/gestao-de-cs:semana` | monta a semana: o mais crucial, o que está atrás, quem precisa agir |
| **Contas e receita** | `/gestao-de-cs:contas` | o resumo de uma página da conta antes de qualquer conversa, contas-chave, renovação por tipo de contrato, pedido de desconto, oportunidades de upgrade, reunião em 4 passos e apresentação em PowerPoint, com gráficos de evolução em barras e espaço para prints |
| **Guardião da carteira** | `/gestao-de-cs:guardiao` | onboarding, o que empaca, troca de contato e plano para conta em risco |
| **Melhoria contínua** | `/gestao-de-cs:melhoria` | o que cresce e por quê, quem saiu, pesquisa, NPS e entrevistas. Propõe, e você aprova |

Os agentes preparam, e **você decide em um lugar só**.

- **A central (`/gestao-de-cs:central`).** Uma conversa só para o dia inteiro. Roda o que falta, reconhece o dia da semana (na segunda, a semana; de terça a quinta, o foco do dia; na sexta, o balanço), junta o que ficou pendente e depois encaminha cada pedido para o agente certo, sem você lembrar comando.
- **A mesa (`/gestao-de-cs:hoje`).** Onde você decide o que foi preparado, marca tarefas e leva o que fazer para a agenda. A central chama a mesa quando precisa.
- **A mesa de aprovação (`mesa.md`).** Plano, reunião e sugestão entram sozinhos e esperam a sua decisão. Nada é enviado por você.
- **A página do dia (`hoje.md`).** O que melhorou, o que fazer hoje, o que está marcado e o que espera você, com o que está parado na mesa há mais de 3 dias. Muda com o dia: a segunda abre com a semana e a sexta fecha com o balanço. Sai só dos seus arquivos, sem IA.
- **A lista de tarefas (`tarefas.md`).** O que fazer, até quando e quem faz. Sai da semana, dos planos aprovados e das reuniões, e você acrescenta as suas.
- **A agenda.** Com o Google Agenda conectado no Claude, a IA vê os horários livres, propõe os blocos e cria só o que você aprovar. Sem conexão, o arquivo `com-nomes/agenda.ics` entra em qualquer calendário, em eventos de dia inteiro.
- **O ciclo de resultado.** Compara a rodada de antes da decisão com a de depois e leva o que não melhorou para a semana. Mostra que o número mudou depois da ação, não que a ação causou a mudança. Com 5 casos ou mais de cada lado, mostra também as contas da mesma faixa que não tiveram a ação.
- **A rotina que roda sozinha.** Se você pedir, de segunda a sexta, no seu computador e sem IA: na primeira vez da semana, monta a semana e prepara planos e reuniões; todo dia, reavalia o urgente e refaz a página. Quando um export novo chega em `4-dados/entradas/novos`, ela atualiza o health score.

**O que entra como urgente:** cancelamento agendado novo, conta que caiu para a faixa vermelha, problema financeiro novo, renovação nos próximos 30 dias com sinal de insatisfação e ação aprovada que passou do prazo. Os 30 dias são um ponto de partida, não um benchmark.

**A rotina precisa de você em três pontos:** o export continua vindo de você ou do seu sistema, porque não há conexão com banco. Sem export novo, o health score não muda e só as datas geram urgência. E a página não avisa ninguém: você abre `hoje.md` ou roda o comando.

## O que muda em relação a uma planilha de health score comum

Quase nenhum health score entrega o que promete. A nota sozinha suaviza a curva, e a conta sai sem ninguém ver. Por isso:

- **A nota nasce do checklist, não de uma lista pronta.** Você define a dor que o produto resolve e quais rotinas provam valor.
- **Conta parada acende alerta mesmo com a nota verde.** E o motivo é separado em "do cliente" ou "nosso", porque isso muda quem precisa agir.
- **A conta é comparada com ela mesma.** Lançava 40 planos e agora lança 12? Avisa, mesmo com a nota boa.
- **Cada nota diz quanto dá para confiar nela.** Sem dado suficiente, a conta fica sem nota.
- **Teste da conta perdida.** Mostra quantas das contas que saíram a skill teria avisado, e quantas passaram sem aviso.
- **Oportunidade também se mapeia.** Área que o cliente não usa, usuário sobrecarregado e o que a sua empresa definir, numa lista que você acompanha e mostra à liderança.

**Nunca inventa número.** Sem dado, fica um campo para preencher e o item entra em "o que falta medir", com o primeiro passo.

## Previsões, sem LLM e no seu computador

Quando há histórico, o plugin treina um modelo estatístico com os dados da própria empresa e tenta prever três coisas: quem pode cancelar em 90 dias, para onde vai o uso de cada rotina e quem pode aumentar a receita em 90 dias.

**O modelo precisa provar antes de mostrar.** Ele volta no tempo, treina só com o que se sabia em cada data e compara com o que aconteceu depois. A previsão só aparece se ele acertou mais que a comparação simples, junto com o placar. Com poucos casos, responde "ainda não dá". Sem ganho, diz que não ganhou.

Em carteira pequena, o churn vai ficar muito tempo em "ainda não dá": poucos cancelamentos não ensinam nada. Até agora, o método foi testado só com empresas inventadas. Detalhes em `referencias/previsao.md`.

## Instalar

Você precisa do [Claude Code](https://code.claude.com), de Python 3.10 ou mais novo e de duas bibliotecas:

```bash
python -m pip install openpyxl xlsxwriter
```

As previsões e a apresentação em PowerPoint precisam de mais duas, gratuitas e opcionais. Sem elas, todo o resto funciona igual:

```bash
python -m pip install scikit-learn python-pptx
```

Depois, dentro do Claude Code, dois comandos:

```
/plugin marketplace add EduMamede/gestao-de-cs
/plugin install gestao-de-cs@gestao-de-cs
```

Abra uma sessão nova e digite `/gestao-de-cs:consultor`.

Prefere sem comando? Baixe o zip em [edumamede.github.io/gestao-de-cs](https://edumamede.github.io/gestao-de-cs/) e siga o `COMECE-AQUI.html` que vem dentro: o Claude confere o Python e instala para você.

Para testar a partir de uma pasta, sem instalar:

```bash
claude --plugin-dir "caminho/para/gestao-de-cs"
```

No Mac e no Linux, se `python` não existir, crie um atalho para `python3`.

## Como usar

1. Rode `/gestao-de-cs:consultor`. Ele pergunta sobre privacidade, sugere a pasta da empresa e conduz o checklist.
2. Exporte seus dados em CSV ou XLSX e rode `/gestao-de-cs:analista`. Ele liga as colunas com você e gera a rodada.
3. Abra `4-dados/rodadas/<data>/health-score.xlsx` no Excel.
4. Rode `/gestao-de-cs:semana` para montar a semana.
5. Na semana seguinte, um export novo e `/gestao-de-cs:analista` de novo. A cada rodada, a comparação fica melhor.
6. Quando precisar: `/gestao-de-cs:contas` para reunião, renovação e oportunidades; `/gestao-de-cs:guardiao` para onboarding e conta em risco; `/gestao-de-cs:melhoria` para entender o que cresce e ouvir os clientes.
7. No dia a dia, comece por `/gestao-de-cs:central` e peça o resto na mesma conversa.

Quer ver como fica antes de usar? A pasta `exemplos/empresa-exemplo/` tem uma rodada pronta, com dados inventados.

**Não há conexão direta com banco de dados.** A entrada é sempre um export. É mais simples e mais seguro.

## O que vai para a IA

Leia esta parte antes de usar dados de verdade. As contas são feitas por scripts, no seu computador. O que a IA lê depende do modo que você escolher no começo:

| | modo aberto (padrão) | modo protegido |
| --- | --- | --- |
| Nomes de colunas e totais | vê | vê |
| Nome do cliente | vê | **não vê**: só CONTA-017 |
| Nome do responsável e do segmento | vê | **não vê**: só CSM-01 e SEG-02 |
| Rótulos dos dados (etapa, status, motivo) | vê | **não vê** |
| Exemplos de valores das colunas | vê até 3 por coluna | **não vê** |
| Coluna de texto livre e de dado pessoal | fora dos relatórios, mas a IA pode abrir o arquivo | **não vê** |
| Sua planilha `health-score.xlsx` | pode abrir | **não abre** |
| Previsões | vê | vê só código da conta, chance, rotina e números da conta |

O modelo das previsões roda no seu computador, dentro do script. A IA só lê o resultado. Se você ligar quem fez cada registro, o script só conta para achar sobrecarga: o nome do usuário nunca sai dele. Tema e motivo viram códigos como TEMA-02 no modo protegido. A apresentação em PowerPoint leva os nomes reais e fica em `com-nomes/`, onde a IA não abre. Os gráficos dela saem das suas rodadas, pelo script, e os prints você mesmo cola no PowerPoint, então a IA não vê essas imagens. No modo protegido, `mesa.md` e `hoje.md` trazem só códigos, e as cópias com nomes ficam em `com-nomes/`. O que você escreve em um plano, como uma ação, aparece na página, e a IA lê. A rotina agendada não usa IA: quando ela roda sozinha, nenhum dado sai do computador. Com o calendário conectado, a IA olha os horários livres, com o seu OK, e o que ela criar fica no seu calendário. Se ela precisar ler os títulos dos seus compromissos, avisa antes, inclusive no modo protegido. O que chega em `4-dados/entradas/novos` tem a mesma trava de `4-dados/entradas/`.

**Quando usar o modo protegido:** se você se preocupa com isso, ou se há LGPD, dado de saúde, contrato com cláusula de sigilo ou dado de pessoa física. A skill pergunta logo no início e sugere esse modo. Enquanto você não escolher, os scripts tratam a pasta como protegida. Você também pode mudar depois.

No modo protegido, os nomes reais voltam só no fim, colocados pelo script, na planilha e na pasta `com-nomes/`.

**Dois avisos importantes:**

1. **O que você escreve nos arquivos da pasta da empresa, a IA lê.** Se você escrever um nome real numa ficha de cliente, a IA lê esse nome, inclusive no modo protegido. Na dúvida, use cargos e códigos.
2. **A trava técnica é contra engano, não é um cofre.** Ela impede a IA de abrir os dados brutos dentro da pasta da empresa, mas não enxerga um export parado em Downloads, por exemplo. Por isso a skill pede para guardar o arquivo com o comando `receber` antes de tudo.

O que a IA processa segue as regras da sua conta na Anthropic. Veja se elas atendem à sua empresa. Detalhes em `referencias/privacidade.md`.

**A pasta da empresa nunca vai para o GitHub.** O script recusa criá-la dentro do plugin e deixa um `.gitignore` que ignora tudo.

## O que tem em cada pasta

```
gestao-de-cs/
├── .claude-plugin/   ficha do plugin
├── skills/           os 7 comandos: o método de cada agente e o comando do dia
├── agents/           os 6 agentes, usados quando um chama o outro
├── hooks/            a trava de privacidade e a liberação do script
├── scripts/          as contas, em Python
├── modelos/          modelo da pasta da empresa e as cores (tema.json)
├── referencias/      o método, em detalhe
├── exemplos/         uma empresa de exemplo, com dados inventados
└── tests/            5 bases fictícias e os testes automáticos
```

## Trocar as cores

As cores da planilha ficam em `modelos/tema.json`. Para mudar só em uma empresa, copie esse arquivo para `4-dados/tema.json` na pasta dela e troque o que quiser.

## Rodar os testes

```bash
python -m unittest discover -s tests
```

## Limites que você precisa conhecer

- É uma primeira versão, testada com bases fictícias.
- Os pontos de corte (faixas, 30% para alertar, janela de 90 dias, 30 casos para treinar) são pontos de partida, não benchmark. Ajuste em `4-dados/como-medir.md`.
- As previsões mostram chance, não certeza. O que pesou para o modelo veio junto com o resultado, e isso não prova a causa.
- O avaliador de fórmulas dos testes não é o Excel. A planilha grava o valor calculado junto com a fórmula e o Excel recalcula ao abrir.
- Feito para o Claude Code. Não foi testado no Claude.ai, onde os dados subiriam para a conversa.
- **O plugin dispensa uma autorização sua, e você precisa saber disso.** Os seis comandos rodam direto. Se o Claude chamar um dos agentes, a trava libera o script do próprio plugin nestes comandos: `validar`, `colunas`, `rotulos`, `rodada`, `prever`, `carteira`, `oportunidades`, `reuniao`, `apresentacao`, `cuidados`, `plano`, `melhoria`, `semana`, `conferir-numeros`, `restaurar-nomes` e `nova-ficha`. Continuam pedindo: mudar o modo de privacidade, criar a pasta, trazer um arquivo de fora (`receber`), gravar por cima de uma rodada ou semana (`--refazer`), editar arquivos e qualquer outro comando junto com o script. Para desligar, esvazie a lista `LIBERADOS` em `scripts/guarda_privacidade.py`.

## Créditos e licença

O método é meu, construído em cima de muita gente que ensinou antes. Veja `CREDITOS.md`. Uso livre, sem revenda: veja `LICENSE`.

Feito por Eduardo Mamede.
