# Campos padrão

Liga as colunas do export da pessoa aos campos da skill em `4-dados/colunas.md`. Todo arquivo precisa de `conta_id` ou `conta_nome`. Os nomes da terceira coluna são pistas: o nome real varia, e a pessoa confirma.

| campo | para que serve | costuma se chamar |
| --- | --- | --- |
| `conta_id` | código da conta | ID, Cód., Código, CNPJ |
| `conta_nome` | nome da conta | Cliente, Conta, Razão Social, Empresa |
| `receita` | quanto a conta paga | MRR, Valor, Mensalidade, Valor Mensal |
| `receita_anterior` | quanto pagava antes | MRR 12 meses atrás |
| `data_inicio` | quando virou cliente | Início, Data do contrato, Primeira compra |
| `renovacao` | quando renova | Renovação, Fim do contrato, Dt. Renov. |
| `contrato` | anual, mensal ou outro | Contrato, Tipo de contrato, Periodicidade |
| `usuarios` | quantos usuários ou acessos a conta tem | Usuários, Acessos, Licenças |
| `segmento` | grupo da conta | Segmento, Porte, Plano, Carteira |
| `responsavel` | quem do CS cuida | CSM, Responsável, Dono da conta |
| `status` | ativa ou cancelada | Status, Situação |
| `data_cancelamento` | quando cancelou | Cancelamento, Data de saída, Churn em |
| `motivo_cancelamento` | por que cancelou | Motivo, Motivo do churn |
| `etapa` | etapa atual da jornada | Etapa, Fase, Coluna do Kanban |
| `data_entrada_etapa` | quando entrou na etapa | Entrou em, Data da fase |
| `dias_na_etapa` | dias na etapa, se vier pronto | Dias na fase |
| `motivo_parada` | do cliente ou nosso | Parado por, Pendência de, Responsável pela pendência |
| `proximo_passo` | próximo passo (texto livre: só vai para a planilha) | Próxima ação, Próximo passo |
| `data_proximo_contato` | próxima data combinada | Próximo contato, Próxima reunião |
| `ultimo_contato` | última conversa | Último contato, Última reunião |
| `nps` | nota de 0 a 10 | NPS, Nota |
| `patrocinador` | quem patrocina (só contamos se está preenchido) | Sponsor, Patrocinador |
| `decisor` | quem decide (só contamos se está preenchido) | Decisor |
| `usuario_chave` | usuário-chave (só contamos se está preenchido) | Key user, Usuário-chave |
| `data_evento` | a data do registro, em arquivo de eventos | Aberto em, Data do pedido |
| `usuario_evento` | quem fez o registro, em arquivo de eventos (só contamos, para ver sobrecarga: o nome nunca sai do script) | Usuário, Lançado por, Criado por |

As colunas das rotinas não entram aqui: elas ficam em `como-medir.md`, nos campos `onde está o dado` e `coluna`.

Coluna com aviso de TEXTO LIVRE fica fora, pois pode ter nomes, telefones e histórico. Para deixar isso registrado, marque o campo como `bloqueada`. Coluna que não interessa pode ser omitida ou marcada como `ignorar`.

## Como escrever `4-dados/colunas.md`

| arquivo | tipo |
| --- | --- |
| contas.csv | contas |
| chamados.csv | eventos |

| arquivo | coluna | campo |
| --- | --- | --- |
| contas.csv | Razão Social | conta_nome |
| contas.csv | Valor Mensal | receita |
| contas.csv | Observações | bloqueada |
| chamados.csv | Cliente | conta_nome |
| chamados.csv | Aberto em | data_evento |

## O que o script já resolve

Separador `;` ou `,`, texto em Latin-1 ou UTF-8, linhas de título antes do cabeçalho, linhas de total, `R$ 1.234,56`, datas misturadas (`03/11/2026`, `2026-11-03`, `3/11/26`, número de série do Excel), contas repetidas e o mesmo nome escrito de formas diferentes ("CLÍNICA BETA LTDA" e "Clinica Beta"). O que não der para ler fica vazio e entra nos avisos da rodada.
