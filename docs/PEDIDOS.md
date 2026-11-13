# Pedidos, documentos e cancelamento

Todo registro novo é ORÇAMENTO. Salvar, editar, baixar documentos ou cancelar um
orçamento não reserva nem movimenta estoque. Somente a ação **Confirmar e gerar
pedido** transforma o orçamento em PEDIDO e baixa os itens atomicamente. PDF/TXT
identificam ORÇAMENTO ou PEDIDO; não são documentos fiscais ou comprovantes de
pagamento. A recuperação de senha por e-mail permanece removida.

## Interface e documentos

A lista tem Visualizar PDF, Baixar PDF, Baixar TXT, Editar, Cancelar e, para
orçamentos ativos, Confirmar e gerar pedido.
É possível editar cliente, referência, produtos e quantidades, ou descartar a
edição. Confirmar exige confirmação explícita e valida saldo atual (orçamento
não reserva saldo). Cancelar exige confirmação, devolve estoque apenas para
pedidos confirmados e mantém a
ficha marcada CANCELADO com seus downloads. Cancelados não podem ser editados,
cancelados novamente ou vinculados a outra saída. A lista mantém o limite de
100 pedidos mais recentes.

Os documentos contêm Márcia Salgados, número, data de criação em Brasília,
tipo, status, cliente, referência, nomes/preços históricos, quantidades, subtotais e
total em BRL. PDF tem tabela com cabeçalho repetido, rodapé e paginação; TXT usa
UTF-8. O download reflete a versão atual; versões anteriores ficam na auditoria.
Valores de cancelados são mantidos apenas para histórico. O mesmo identificador
é preservado na conversão, com data de confirmação nos novos pedidos. Preços do
orçamento são mantidos na confirmação, mesmo que o catálogo tenha mudado.

## API

Prefixo `/api` no Nginx; sessão autenticada obrigatória. ADMIN e FUNCIONARIO
podem gerenciar pedidos. Mutações exigem `X-CSRF-Token`.

| Método e rota | Corpo / resultado |
| --- | --- |
| POST /pedidos | `{cliente, referencia, itens: [{produto_id, quantidade}]}`; cria ORCAMENTO sem baixa, evento CRIACAO, retorna 201 |
| POST /pedidos/{id}/confirmar | `{versao}`; converte ORCAMENTO ativo em PEDIDO, baixa estoque e retorna 200 |
| GET /pedidos | Últimos 100 com tipo, status, versão, confirmado_em e itens ativos |
| GET /pedidos/{id} | Detalhes e histórico de eventos com usuário, data, antes/depois |
| PUT /pedidos/{id} | Corpo completo como POST, mais `versao` obtida no GET; retorna nova versão |
| DELETE /pedidos/{id} | `{versao}`; cancela logicamente sem apagar registros; devolve estoque apenas de PEDIDO |
| GET /pedidos/{id}/documento.pdf | Baixa PDF; `?visualizar=1` abre inline |
| GET /pedidos/{id}/documento.txt | Baixa TXT UTF-8 |

Cliente: 1–150 caracteres; referência: até 80; itens: 1–100 produtos distintos;
quantidades inteiras de 1 a 2147483647. Erros: 400 para validação, 404 inexistente,
409 para saldo insuficiente/overflow, versão desatualizada, cancelado ou legado
sem dados suficientes, 503 para falha de banco. Erros retornam JSON com `erro`,
sem detalhes SQL. Documentos usam `Content-Disposition`, tipo de conteúdo,
`Cache-Control: no-store` e `nosniff`.

## Transações, preços e histórico

Confirmação/edição/cancelamento bloqueiam primeiro o registro com SELECT FOR UPDATE, depois
todos os produtos em ID crescente. Criação também bloqueia produtos nessa ordem;
saída manual vinculada bloqueia pedido antes do produto. A versão é conferida
sob o bloqueio: duas ações sobre a mesma versão têm apenas um vencedor.

Orçamentos aceitam quantidades acima do saldo disponível, pois não reservam
estoque. A confirmação valida todos os produtos e baixa as quantidades salvas;
insuficiência ou falha SQL deixa o orçamento ativo e os saldos intactos. Uma
segunda confirmação retorna 409, inclusive com versão atualizada. Saída manual
vinculada a orçamento é bloqueada. Campos tipo/estoque_processado enviados pelo
cliente não permitem pular a confirmação.

Em pedidos confirmados, delta = quantidade nova - anterior; saldo novo = saldo atual
- delta. Qualquer falha reverte a transação inteira, incluindo itens, saldos,
movimentações e auditoria. Delta zero não cria movimentação. Cancelamento usa
quantidade nova zero e registra entradas; cancelar orçamento usa delta zero.
CANCELADO impede segunda devolução ou confirmação posterior.
`estoque_processado` continua verdadeiro, impedindo outra baixa manual vinculada.

Itens removidos ficam inativos, sem perder registros/vínculos. Recolocar produto
já registrado nesse pedido conserva nome/preço históricos. Produtos incluídos
pela primeira vez usam o catálogo atual. Movimentos registram usuário, motivo,
pedido/item e saldos anterior/posterior. `pedido_eventos` guarda CRIACAO, EDICAO,
CONFIRMACAO e CANCELAMENTO com fotografias antes/depois. O histórico anterior à migração
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

A migração 004 acrescenta tipo e data de confirmação, e permite CONFIRMACAO na
auditoria. Todos os registros anteriores permanecem PEDIDO, inclusive cancelados
e referências legadas: não se repetem baixas, não se devolve estoque e não se
inventa data de confirmação histórica. Novos orçamentos são gravados explicitamente
como ORCAMENTO. Reiniciar ou repetir a migração não transforma orçamentos existentes.

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
2. Salvar orçamento com dois produtos: saldo inalterado e documento ORÇAMENTO.
   Editar ou cancelar um orçamento também deve manter o saldo.
3. Visualizar/baixar PDF e TXT: acentos, referência, preços, totais e impressão
   no navegador usado em casa.
4. Confirmar orçamento: só agora deve surgir PEDIDO e uma baixa por item.
   Editar pedido confirmado ajusta somente diferenças no estoque.
5. Orçamento sem saldo suficiente pode ser salvo, mas confirmar deve recusar
   sem alterar orçamento ou estoque. Corrigir quantidades e confirmar novamente.
6. Duas abas editando o mesmo pedido: salvar uma e tentar a outra deve indicar
   conflito; atualizar a lista e reabrir para continuar.
7. Cancelar pedido confirmado: devolução única, ficha CANCELADO, downloads marcados,
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

O CI também executa `frontend/tests/orcamentos-ui.cjs` com Playwright e API
simulada, cobrindo orçamento, edição, download, confirmação explícita,
cancelamento e larguras desktop/tablet/celular. Isso complementa a suíte de
PostgreSQL real, sem substituí-la. Capturas são anexadas à execução no GitHub.
