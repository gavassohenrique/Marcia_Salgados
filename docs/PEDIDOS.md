# Pedidos com itens

`POST /api/pedidos` exige sessão válida e `X-CSRF-Token`, tanto para administrador
como funcionário. Exemplo de corpo (IDs devem existir):

```json
{
  "cliente": "Cliente exemplo",
  "referencia": "Entrega de sexta-feira",
  "itens": [
    {"produto_id": 1, "quantidade": 20},
    {"produto_id": 2, "quantidade": 15}
  ]
}
```

De 1 a 100 produtos distintos, com quantidades inteiras de 1 a 2147483647.
Produtos repetidos, quantidades inválidas e lista vazia retornam 400;
produto inexistente retorna 404; saldo insuficiente retorna 409. Nenhum desses
casos grava parcialmente o pedido. Erros de banco retornam 503 sem detalhes internos.

Ao salvar, o servidor bloqueia os produtos por ID em ordem crescente, verifica
todos os saldos e grava pedido, itens, baixa e movimentações em uma única
transação PostgreSQL. Uma disputa por saldo é reavaliada após obter o bloqueio.
Nome e preço unitário são fotografados nos itens; alterações futuras no catálogo
não reescrevem o pedido. Cada saída referencia seu item, pedido e usuário, com
saldos anterior e posterior. A interface impede cliques simultâneos no botão;
o endpoint não oferece chave de idempotência para reenvios independentes.

`GET /api/pedidos` mantém o formato de lista (últimos 100 pedidos), acrescentando
`itens`, `usuario_id`, `usuario_nome` e `estoque_processado`. O POST retorna o
pedido criado com seus itens. Não há edição, exclusão ou cancelamento de pedidos
nesta versão. Não se trata de um módulo financeiro.

## Atualização preservando dados

A migração `backend/migrations/002_pedido_itens.sql` é aditiva e idempotente.
`preparar_banco()` a executa na inicialização do backend, inclusive no deploy
Gunicorn existente, na mesma transação das verificações anteriores de schema.
A imagem Docker inclui a pasta de migrações. Basta atualizar o código/imagens
e recriar os serviços da aplicação com o procedimento normal do projeto.
Faça backup antes de atualizar um ambiente real. Não exclua volumes.

Pedidos anteriores permanecem com `estoque_processado=false`, sem inventar
itens nem repetir movimentações históricas. A vinculação manual de saída
continua disponível apenas para esses pedidos antigos. Pedidos novos já
baixados rejeitam outra vinculação manual com 409. A coluna histórica
`movimentacoes.pedido_id` não recebe uma nova restrição que pudesse invalidar
registros antigos; os novos itens possuem chaves estrangeiras restritivas.

## Verificação

`python -m pytest backend/tests -q` executa as validações unitárias.
Com `TEST_POSTGRES=1`, configure um PostgreSQL exclusivo cujo banco comece com
`test_`, nunca o banco em uso. O teste de integração de autenticação espera
um banco novo. A suíte cobre itens, quantidades, permissões/CSRF, auditoria,
preservação do schema antigo, rollback de falha SQL e pedidos concorrentes
em ordem inversa de produtos. O CI já executa essa suíte com PostgreSQL 15.

Interface revisada em 1920×1080, 768×1024 e 390×844: cabeçalho com ações e menu
separados, indicadores sem sobreposição, formulários adaptáveis, itens em
linhas removíveis, lista de pedidos e ações administrativas com quebra de linha.
