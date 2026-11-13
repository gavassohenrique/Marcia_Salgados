# Pedidos, documentos e cancelamento

Cada pedido salvo já baixa estoque. PDF/TXT são documentos comerciais de
pedido/orçamento: não são documentos fiscais, comprovantes de pagamento nem
orçamentos pendentes de confirmação. Não foi criada uma categoria não confirmada.
A recuperação de senha por e-mail permanece removida.

## Interface e documentos

A lista tem Visualizar PDF, Baixar PDF, Baixar TXT, Editar e Cancelar pedido.
É possível editar cliente, referência, produtos e quantidades, ou descartar a
edição. Cancelar exige confirmação, informa a devolução de estoque e mantém a
ficha marcada CANCELADO com seus downloads. Cancelados não podem ser editados,
cancelados novamente ou vinculados a outra saída. A lista mantém o limite de
100 pedidos mais recentes.

Os documentos contêm Márcia Salgados, número, data de criação em Brasília,
status, cliente, referência, nomes/preços históricos, quantidades, subtotais e
total em BRL. PDF tem tabela com cabeçalho repetido, rodapé e paginação; TXT usa
UTF-8. O download reflete a versão atual; versões anteriores ficam na auditoria.
Valores de cancelados são mantidos apenas para histórico.

## API

Prefixo `/api` no Nginx; sessão autenticada obrigatória. ADMIN e FUNCIONARIO
podem gerenciar pedidos. Mutações exigem `X-CSRF-Token`.

| Método e rota | Corpo / resultado |
| --- | --- |
| POST /pedidos | `{cliente, referencia, itens: [{produto_id, quantidade}]}`; cria com baixa e evento CRIACAO, retorna 201 |
| GET /pedidos | Últimos 100 com status, versão e itens ativos |
| GET /pedidos/{id} | Detalhes e histórico de eventos com usuário, data, antes/depois |
| PUT /pedidos/{id} | Corpo completo como POST, mais `versao` obtida no GET; retorna nova versão |
| DELETE /pedidos/{id} | `{versao}`; cancela logicamente e devolve estoque sem apagar registros |
| GET /pedidos/{id}/documento.pdf | Baixa PDF; `?visualizar=1` abre inline |
| GET /pedidos/{id}/documento.txt | Baixa TXT UTF-8 |

Cliente: 1–150 caracteres; referência: até 80; itens: 1–100 produtos distintos;
quantidades inteiras de 1 a 2147483647. Erros: 400 para validação, 404 inexistente,
409 para saldo insuficiente/overflow, versão desatualizada, cancelado ou legado
sem dados suficientes, 503 para falha de banco. Erros retornam JSON com `erro`,
sem detalhes SQL. Documentos usam `Content-Disposition`, tipo de conteúdo,
`Cache-Control: no-store` e `nosniff`.

## Transações, preços e histórico

Edição/cancelamento bloqueiam primeiro o pedido com SELECT FOR UPDATE, depois
todos os produtos em ID crescente. Criação também bloqueia produtos nessa ordem;
saída manual vinculada bloqueia pedido antes do produto. A versão é conferida
sob o bloqueio: duas ações sobre a mesma versão têm apenas um vencedor.

Para cada produto, delta = quantidade nova - anterior; saldo novo = saldo atual
- delta. Qualquer falha reverte a transação inteira, incluindo itens, saldos,
movimentações e auditoria. Delta zero não cria movimentação. Cancelamento usa
quantidade nova zero e registra entradas; CANCELADO impede segunda devolução.
`estoque_processado` continua verdadeiro, impedindo outra baixa manual vinculada.

Itens removidos ficam inativos, sem perder registros/vínculos. Recolocar produto
já registrado nesse pedido conserva nome/preço históricos. Produtos incluídos
pela primeira vez usam o catálogo atual. Movimentos registram usuário, motivo,
pedido/item e saldos anterior/posterior. `pedido_eventos` guarda CRIACAO, EDICAO
e CANCELAMENTO com fotografias antes/depois. O histórico anterior à migração
não recebe eventos ou valores inventados.

Pedidos antigos sem itens detalhados permanecem como referências e aceitam a
vinculação manual anterior. Edição, cancelamento automático e documentos
calculados ficam indisponíveis: é necessário reconciliar o histórico antes de
ajustar estoque. A migração não infere esses valores.

## Migrações e atualização no PC de casa

A migração 003 roda automaticamente na inicialização. Acrescenta status, versão,
itens ativos e auditoria. Substitui o índice único de movimentação por item por
índice comum para permitir vários deltas, sem eliminar registros. A 002 deixa
de recriar o índice único nas reinicializações. Migrações são idempotentes;
produtos, pedidos, usuários e movimentos existentes permanecem.

Depois da publicação do commit na main, dentro da pasta do projeto:

1. Faça backup do banco pelo procedimento habitual. Mantenha seu `.env` local.
2. Execute `git status` e resolva alterações locais antes da atualização.
3. Execute `git pull --ff-only origin main`.
4. Execute `docker compose up -d --build`.
5. Confira `docker compose ps`; se necessário, `docker compose logs --tail=80 backend`.
6. Abra `http://localhost:8080` e atualize a página com Ctrl+F5.

Não exclua volumes nem execute `down -v`. Não compartilhe `.env`, senhas ou
segredos. Para Oracle, siga `docs/ORACLE_CLOUD.md` com `compose.oracle.yaml`,
preservando o volume do ambiente.

### O que conferir em casa

Para ensaios, use ambiente separado com dados explicitamente de teste.

1. Login e mostrar/ocultar senha; recuperação por e-mail continua ausente.
2. Pedido com dois produtos: uma única baixa automática no histórico.
3. Visualizar/baixar PDF e TXT: acentos, referência, preços, totais e impressão
   no navegador usado em casa.
4. Editar cliente/referência; aumentar um item e diminuir/remover outro:
   conferir somente diferenças no estoque e nos movimentos.
5. Quantidade sem saldo: recusa sem alterar pedido ou estoque.
6. Duas abas editando o mesmo pedido: salvar uma e tentar a outra deve indicar
   conflito; atualizar a lista e reabrir para continuar.
7. Cancelamento: devolução única, ficha CANCELADO, downloads marcados,
   histórico preservado e ausência de botões de editar/cancelar.
8. `docker compose restart backend`: conferir persistência; repetir acesso
   como funcionário/administrador e com largura de tela de celular.

## Testes reproduzíveis

`python -m pytest backend/tests -q` executa unitários e pula PostgreSQL sem
TEST_POSTGRES=1. O CI executa todos com PostgreSQL 15 exclusivo `test_*`.
Para rodar sem instalar Python localmente:

```sh
docker compose -p marcia-testes -f compose.tests.yaml up --build --abort-on-container-exit --exit-code-from tests
docker compose -p marcia-testes -f compose.tests.yaml down
```

Esse projeto usa PostgreSQL em tmpfs, sem portas nem volumes de produção.
Encerre o projeto de teste entre execuções para obter banco novo. Não aponte a
suíte para banco real. Cobertura: documentos, preços históricos, permissões/CSRF,
deltas, cancelamentos repetidos/concorrentes, conflitos de edição, corrida por
saldo, rollback em falha SQL e migrações repetidas preservando dados.
