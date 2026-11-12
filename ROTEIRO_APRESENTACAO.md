# Roteiro de apresentação — Márcia Salgados

**Duração estimada:** 5 a 7 minutos  
**Apresentadores:** João Emanuel de Souza da Silva e Henrique Gavasso Neto

## Antes de começar

1. Execute `docker compose up -d --build` na pasta do projeto.
2. Abra `http://127.0.0.1:8080/index.html` no navegador.
3. Deixe o terminal aberto para mostrar o banco de dados no final.
4. Se já houver muitos dados de teste, escolha um produto fácil de identificar.

## 1. Abertura — João (30 segundos)

> Boa tarde. Nós somos João Emanuel de Souza da Silva e Henrique Gavasso Neto. Nosso projeto é o sistema Márcia Salgados, desenvolvido para organizar o cadastro de produtos e o controle de estoque da empresa. A ideia surgiu da necessidade de substituir controles manuais por um processo mais simples, centralizado e confiável.

**Na tela:** mostrar a página inicial e descer rapidamente até os indicadores.

## 2. Problema e objetivo — Henrique (40 segundos)

> O problema que buscamos resolver é a dificuldade de saber quanto existe de cada produto, quais itens estão próximos do limite mínimo e o que entrou ou saiu do estoque. Sem um sistema, essas informações podem ficar espalhadas ou desatualizadas. Por isso, nosso objetivo foi criar uma aplicação que receba os dados do usuário, processe as regras de estoque e apresente o resultado atualizado na própria interface.

**Na tela:** apontar os cartões “Produtos cadastrados”, “Estoque total” e “Estoque baixo”.

## 3. Tecnologias e funcionamento — João (50 segundos)

> O sistema possui três partes principais. A primeira é o front-end, construído com HTML, CSS e JavaScript, responsável pelas telas e pela interação com o usuário. A segunda é o back-end, desenvolvido em Python com Flask, responsável por validar e processar os dados. A terceira é o banco PostgreSQL, onde os produtos e as movimentações ficam armazenados. Usamos Docker para executar essas partes de forma integrada.

> O fluxo é simples: o usuário preenche o formulário, o JavaScript envia os dados para a API, o back-end valida as informações e grava no PostgreSQL. Depois, a interface consulta os dados novamente e mostra o resultado atualizado.

**Na tela:** mostrar rapidamente as pastas `frontend`, `backend` e `database` no VS Code. Depois voltar ao navegador.

## 4. Demonstração do cadastro — Henrique (1 minuto)

> Agora vamos demonstrar a principal funcionalidade do projeto, que é o cadastro de produtos. Vou informar o nome, o preço, o estoque inicial e o estoque mínimo.

**Na tela:** preencher um exemplo:

- Nome: `Risoles de queijo`
- Preço: `6,50`
- Estoque inicial: `20`
- Estoque mínimo: `5`

> Ao clicar em “Cadastrar produto”, essas informações são enviadas para o back-end. O sistema valida os campos, grava o produto no banco e retorna uma mensagem de sucesso. Podemos ver que o produto apareceu no catálogo e que os indicadores do painel também foram atualizados.

**Na tela:** clicar em “Cadastrar produto”, mostrar a confirmação, o novo cartão e o resumo.

## 5. Entrada, saída e automação — João (1 minuto e 20 segundos)

> Além do cadastro, o sistema controla as movimentações. Primeiro, vamos registrar uma entrada de 10 unidades com o motivo “Nova produção”. O sistema soma essa quantidade ao estoque atual e registra a operação no histórico.

**Na tela:** no produto cadastrado, selecionar `Entrada`, informar `10`, escrever `Nova produção` e confirmar.

> Agora vamos registrar uma saída de 4 unidades com o motivo “Venda”. Nesse caso, o sistema subtrai a quantidade e atualiza novamente o saldo e o histórico.

**Na tela:** selecionar `Saída`, informar `4`, escrever `Venda` e confirmar.

> A automação está justamente nesse processamento. O usuário não precisa calcular o novo saldo manualmente. A cada entrada ou saída, o sistema calcula o estoque, atualiza os indicadores, identifica automaticamente os produtos com estoque baixo e mantém a rastreabilidade da operação.

## 6. Validação de erro — Henrique (40 segundos)

> Também implementamos regras para evitar dados incorretos. Por exemplo, não é possível cadastrar um produto sem nome ou com preço negativo. O sistema também impede uma saída maior do que a quantidade disponível.

**Na tela:** tentar retirar uma quantidade maior do que o estoque do produto.

> Nesse teste, a operação é recusada e o sistema informa o estoque disponível. Assim, o banco não fica com valores negativos.

## 7. Histórico e banco de dados — João (50 segundos)

> Todas as entradas e saídas ficam registradas no histórico, com o nome do produto, o tipo da movimentação, a quantidade, o motivo, o saldo anterior, o saldo posterior e a data. Isso permite acompanhar o que aconteceu no estoque.

**Na tela:** descer até “Histórico de movimentações”.

> Também podemos confirmar que os dados não estão apenas na tela. Eles estão armazenados no PostgreSQL.

**No terminal:** executar:

```bash
docker exec -it postgres_db psql -U user -d appdb
```

Depois executar:

```sql
SELECT * FROM produtos ORDER BY id DESC;
SELECT * FROM movimentacoes ORDER BY id DESC;
```

## 8. Encerramento — Henrique (30 segundos)

> Como resultado, entregamos uma funcionalidade completa de entrada, processamento e saída de dados. O usuário informa o produto ou a movimentação, a API aplica as regras, o banco armazena as informações e a interface apresenta o estoque atualizado. O projeto também possui testes de validação no back-end e uma interface responsiva, que funciona em computador e celular. Obrigado.

## Resposta curta caso o professor pergunte “qual é a principal funcionalidade?”

> A principal funcionalidade é o cadastro de produtos integrado ao banco de dados. Ela recebe nome, preço, estoque inicial e estoque mínimo, valida os dados no back-end, grava no PostgreSQL e mostra o produto cadastrado e os indicadores atualizados na interface.

## Resposta curta caso o professor pergunte “onde está a automação?”

> A automação está no processamento das movimentações: o sistema calcula o novo saldo após cada entrada ou saída, impede estoque negativo, identifica estoque baixo e atualiza automaticamente o painel e o histórico.
