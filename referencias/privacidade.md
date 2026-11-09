# Privacidade: os dois modos

Pergunte sempre, antes de ler qualquer dado. Por padrão a IA pode ver os dados. Sugira o modo protegido a quem se preocupar, ou quando aparecer LGPD, dado de saúde, cláusula de sigilo ou dado de pessoa física. Enquanto a pessoa não escolher, os scripts tratam a pasta como protegida.

| | modo aberto | modo protegido |
| --- | --- | --- |
| Nomes de colunas | a IA vê | a IA vê |
| Totais e contas | a IA vê | a IA vê |
| Conta | código e nome real | só o código (CONTA-017) |
| Responsável e segmento | nome real | só o código (CSM-01, SEG-02) |
| Rótulos (etapa, status, motivo, categoria) | a IA vê | a IA não vê o rótulo, só no que ele virou ("Implantação", "cancelada", nota 100). A pessoa confere em `.privado/rotulos.csv` |
| Amostra de valores | até 3 por coluna | nenhuma |
| Coluna de texto livre e de dado pessoal | fora da amostra e dos relatórios, mas a IA pode abrir o arquivo | a IA não vê |
| Planilha `health-score.xlsx` | a IA pode abrir | só a pessoa abre |
| Pasta `com-nomes/` | não é usada | só a pessoa abre |

## Regras que valem nos dois modos

- As contas são feitas pelos scripts, no computador da pessoa. A IA nunca faz conta de cabeça.
- O texto da pasta da empresa (perfil, jornada, fichas, metas) é lido pela IA. Se a pessoa escrever um nome real numa ficha, a IA lê esse nome. Em caso de dúvida, use cargos e códigos.
- A pasta da empresa nunca entra no repositório da skill: o script recusa criar lá dentro e deixa um `.gitignore` que ignora tudo.

## O caminho no modo protegido

1. **Receber:** `receber` copia o export para `4-dados/entradas/`, sem a IA abrir o arquivo. A rotina faz o mesmo com o que chega em `4-dados/entradas/novos`. Quando ela roda agendada, é só script: nenhum dado vai para a IA.
2. **Ligar:** `colunas` mostra só nome, tipo, preenchimento e avisos. A IA propõe a ligação pelos nomes e a pessoa confirma.
3. **Rodar:** `rodada` processa o arquivo inteiro e entrega resumos só com códigos. A tabela que liga código e nome fica em `4-dados/.privado/`.
4. **Devolver os nomes:** os scripts, e nunca a IA, colocam os nomes em `health-score.xlsx` e em `com-nomes/`.

Coluna bloqueada nem é carregada. A exceção é `proximo_passo`, que vai só para a planilha da pessoa.

## A trava técnica

O hook `scripts/guarda_privacidade.py` roda antes de cada ferramenta do Claude Code. No modo protegido, ele nega leituras e comandos que apontem para `4-dados/entradas/`, `4-dados/.privado/`, `com-nomes/` e `health-score*.xlsx`. Também nega abrir CSV ou XLSX quando a sessão está dentro da pasta da empresa, e busca de texto na raiz dela.

**É uma trava contra engano, não um cofre.** Ela não enxerga um export fora da pasta, como em Downloads, se a sessão não estiver na pasta da empresa. Por isso, use `receber`. Um comando muito criativo também poderia escapar. Para garantia forte, trate o arquivo como você trataria qualquer dado sensível no seu computador.

**O mesmo hook dispensa uma autorização.** Quando um agente do plugin roda o script dele, sem nenhum outro comando junto, a autorização não é pedida. Isso vale só para `validar`, `colunas`, `rotulos`, `rodada`, `prever`, `carteira`, `oportunidades`, `reuniao`, `apresentacao`, `cuidados`, `plano`, `melhoria`, `semana`, `conferir-numeros`, `restaurar-nomes` e `nova-ficha`, que ficam na pasta da empresa e seguem as mesmas regras de saída. `conferir-numeros` e `restaurar-nomes` aceitam só um `.md` da pasta, fora de `com-nomes/`, `4-dados/entradas/` e `4-dados/.privado/`.

## Mudar de modo

A decisão é da pessoa, nunca da IA. Use o comando `privacidade` do `cs.py`, com `--pasta` e `--modo`, e anote a mudança em `1-empresa/conversas-consultor.md`.
