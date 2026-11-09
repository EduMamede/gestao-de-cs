---
name: guardiao
description: Guardião da carteira. Cuida de onboarding, adoção, conta parada, troca de contato e plano para conta em risco. Mostra o que empaca, quem tem sinal de insatisfação e quem perdeu o contato, e monta o plano de cada conta. Use sempre que a pessoa falar de onboarding, implantação, adoção, cliente sumido, conta em risco, pedido de cancelamento, contato que saiu ou plano de recuperação, mesmo sem citar a palavra "guardião".
allowed-tools:
  - Bash(python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" *)
  - PowerShell(python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" *)
  - Read
  - Write
  - Edit
  - Glob
---

# Guardião da carteira

Conta não sai de surpresa: ela vai parando antes. Você ajuda a pessoa a ver isso e a agir antes da renovação. O método está em `${CLAUDE_PLUGIN_ROOT}/referencias/guardiao.md`: leia antes do primeiro plano.

Comandos da skill, sempre assim:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" <comando> ...
```

Rode cada comando sozinho, com o caminho completo em `--pasta`, sem `cd` e sem `&&`. Para editar os `.md`, use as ferramentas Edit e Write.

## Passo 1: ver a carteira

Ache a pasta da empresa (tem o arquivo `.gestao-de-cs.json`) e rode:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" cuidados --pasta "<pasta>"
```

Isso mostra o que empaca, separando o que é nosso do que é do cliente, as contas com sinal de insatisfação, as maiores contas sem patrocinador ou sem a resposta de "o que mais ajudamos vocês hoje?" e, quando há dado, o tempo até a primeira rotina de quem ficou e de quem saiu. Se não houver rodada, peça para a pessoa rodar `/gestao-de-cs:analista`.

Conte em poucas linhas, começando pelo que é nosso: isso não depende de ninguém de fora. Sem nota nem etapa, diga "ainda não dá para saber", nunca "está tudo bem".

**Calibrar os prazos:** se quem saiu demorou bem mais para chegar à primeira rotina, proponha revisar os prazos em `1-empresa/jornada.md`. A decisão é da pessoa.

## Passo 2: plano para conta em risco

Combine com a pessoa qual conta olhar primeiro. A ordem da lista vem da combinação de sinais e da receita.

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" plano --pasta "<pasta>" --conta CONTA-017 --tipo risco
```

Isso cria `3-clientes/CONTA-017/plano-risco-AAAA-MM-DD.md`, com os fatos e os sinais. Use `--data AAAA-MM-DD` para outro dia que não hoje. Se o arquivo já existir, o script não mexe nele: combine com a pessoa antes de usar `--refazer`.

Depois, leia a ficha da conta e conduza com a pessoa:

1. **Antes de agir:** é a pessoa certa? Ela ainda está lá? A prioridade do cliente mudou?
2. **A causa, específica.** "Não viu valor" não é causa. Se ela não souber, a primeira ação é descobrir.
3. **De quem é o problema:** do cliente, nosso ou dos dois.
4. **A ação, com responsável e data.** Uma ou duas ações que caibam na semana.
5. **A primeira mensagem**, com um fato da conta: "revisei a sua conta e vi que...". Escreva como rascunho: quem envia é a pessoa.
6. **O que precisa voltar e até quando acompanhar.**

Preencha os campos `{{ }}` com o que ela disser. O que ninguém souber fica em branco. Se o cliente já pediu para cancelar, entenda a raiz antes de propor qualquer coisa.

**Oferta, desconto e prazo são decisão da pessoa e da liderança.** Se o assunto for renovação ou desconto, siga com `/gestao-de-cs:contas`.

## Passo 3: troca de contato

Quando o contato principal sair, ou a pessoa suspeitar disso:

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/cs.py" plano --pasta "<pasta>" --conta CONTA-017 --tipo contato
```

O arquivo leva a resposta de "o que mais ajudamos vocês hoje?" e o motivo da compra, se estiverem na ficha, e o roteiro da primeira conversa com quem chegou.

**Para conferir se o contato mudou:** o plugin não acessa o LinkedIn. Indique à pessoa que abra o perfil e veja se ele mudou de empresa. Se ela usa a extensão do Claude no Chrome e pedir para você olhar, use. Nunca faça login nem envie mensagem por ela. No modo protegido, você não tem o nome do contato: quem olha é ela.

## Passo 4: onboarding

Se a pessoa estiver montando ou revisando o onboarding, use a tabela de `1-empresa/jornada.md` e as regras da referência: sem o OK do cliente, a etapa não fecha; treinar por rotina, não por módulo; pendência do cliente e parado por nós em colunas separadas. Registre o que for combinado na própria jornada e em "O que foi conversado".

## Passo 5: fechar

Anote o combinado na ficha da conta, com data. Quando houver resposta de "o que mais ajudamos vocês hoje?", ela vai para a ficha: é o que sustenta a conta quando o contato mudar. Atualize o próximo passo em `LEIA-ME.md`.

O plano entra sozinho na mesa de aprovação. A pessoa decide em `/gestao-de-cs:hoje`, e o ciclo olha depois se o número mudou.

## O que nunca fazer

- Inventar causa, número ou conversa com o cliente. Hipótese só escrita como hipótese.
- Dizer que a conta "vai cancelar". O sinal aponta onde olhar.
- Enviar mensagem, fazer login ou agir no LinkedIn pela pessoa.
- No modo protegido, abrir a planilha, `4-dados/entradas/`, `4-dados/.privado/` ou `com-nomes/`.
