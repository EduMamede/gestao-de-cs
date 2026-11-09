# Melhoria contínua

Olhe o que cresce e pergunte por quê. Os chamados de estoque estão crescendo: por quê? O que melhorar para diminuir? O churn aumentou: por quê? O que dá muito trabalho, e como reduzir?

## A regra principal

**Este agente propõe, não muda sozinho.** A sugestão vai para `5-melhoria/sugestoes.md`, a pessoa aprova, e a mudança fica registrada em `5-melhoria/mudancas.md`, com data, motivo e se funcionou.

Mudar peso ou rotina da nota quebra a comparação com o passado. Essa sugestão sempre vem com esse aviso. Em geral, vale manter a fórmula por um tempo antes de mexer.

## O que o comando mostra

`cs.py melhoria` traz:

- **O que mudou na carteira:** a soma de cada rotina, antes e agora, quando muda 10% ou mais.
- **Temas que cresceram:** precisa de uma coluna de categoria no arquivo de eventos, ligada ao campo `tema_evento`. No modo protegido, o tema vira um código como TEMA-02, e a pessoa vê o nome real em `com-nomes/`.
- **Quem saiu:** quantas contas por período, os motivos e quantas saíram sem motivo específico.
- **Com quem conversar:** os grupos abaixo, em ordem de receita.

O número mostra **o que** mudou. **Por que** mudou só a conversa responde. Sem conversa, escreva como hipótese.

## Motivo de saída

"Não viu valor" e "outros" não ensinam nada. Se muita conta saiu assim, esse é o primeiro problema: volte nessas contas e registre a causa real.

## Conversar com três grupos e comparar

| grupo | o que perguntar |
| --- | --- |
| **Engajados** | O que faz vocês continuarem? Se o produto sumisse amanhã, o que fariam? O que mais ajudamos? |
| **Novos** | O que esperavam quando compraram? O que já aconteceu e o que ainda não? Onde travou? |
| **Ex-clientes** | O que mudou antes de decidir sair? Quando começou? O que teria feito ficar? O que usam hoje? |

Compare as respostas: a diferença entre quem fica e quem sai costuma dizer mais que cada resposta sozinha. Pergunte sobre o que aconteceu, não sobre o que a pessoa faria.

## NPS e indicação

- **NPS serve para ver a tendência da base,** não para avaliar conta a conta.
- **Feche o ciclo com quem respondeu.** Detrator recebe uma conversa, não um e-mail automático.
- **Indicação precisa de processo.** Com promotor: peça na hora certa, de um jeito específico e com o material pronto. Meça quantas indicações vieram e quantas viraram cliente.

## Efeito WOW e casos de sucesso

- Uma entrega inesperada, um encontro presencial ou um reconhecimento público marcam mais que outra funcionalidade.
- Caso de sucesso também orienta marketing e vendas: mostra que perfil retém mais e para quem não vender.
- Uma consultoria grátis a cada 6 meses é uma forma de levantar valor e abrir conversa com as contas mais importantes.

## Como registrar

| arquivo | o que entra |
| --- | --- |
| `5-melhoria/problemas.md` | o que dá muito trabalho, por quê, a ação e o resultado |
| `5-melhoria/sugestoes.md` | a mudança proposta, o motivo e se foi aprovada |
| `5-melhoria/mudancas.md` | só o que foi aprovado: quando mudou, por quê e se funcionou |
