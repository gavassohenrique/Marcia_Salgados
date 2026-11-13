# Auditoria de código e execução — 13/11/2026

Base examinada: `0f2aa8f143d702c32e9270842ac183da4c4b0da6`, branch `main` de `gavassohenrique/Marcia_Salgados`.

## Escopo e comparação

Foi recuperada a conversa anterior, que registrava a intenção de implementar itens/quantidades e responsividade, sem comprovar conclusão. O histórico Git tem 12 commits. A comparação detalhada `3bce6c4..0f2aa8f` abrange 9 arquivos, com 689 inserções e 273 remoções, incluindo mudanças de final de linha.

| Commit | Conteúdo e constatação |
|---|---|
| `6c720d8` | Implementou formulário com vários itens, quantidades, snapshots de nome/preço, bloqueios de produtos em ordem fixa, transação de pedido/itens/saldos/movimentações, migração aditiva, testes PostgreSQL e CSS responsivo. |
| `0f2aa8f` | Acrescentou revalidação do frontend e versão de CSS/JS. `no-cache` permite armazenamento com revalidação; não é garantia de ausência de cache nem atualiza abas abertas. |
| `3bce6c4` e anteriores | Foram examinados histórico, estatísticas dos diffs anteriores e implementação atual de autenticação, infraestrutura e documentação. A implementação atual foi lida integralmente; não foi feita execução de cada revisão histórica. |

Todos os 41 arquivos versionados na base foram inventariados. Os arquivos de código, testes, manifests e documentação textual foram lidos. Dos dois PDFs acadêmicos foi extraído o texto, sem auditoria visual completa das páginas; a imagem de fundo foi observada na interface. Não há `AGENTS.md` ou `SECURITY.md` dentro do repositório. Nenhum banco existente do usuário foi consultado ou alterado.

## Problemas corrigidos nesta branch

| Prioridade | Problema e evidência | Correção |
|---|---|---|
| Alta funcional | Cadastro de usuário era salvo, mas o navegador mostrava `Cannot read properties of null (reading 'reset')`. `Event.currentTarget` é limpo depois do despacho do evento; os handlers de troca e redefinição de senha tinham o mesmo padrão. | Guardar a referência do formulário antes de `await`. Cadastro reproduzido antes e confirmado depois em navegador com API/PostgreSQL reais; handlers de senha cobertos pelos testes de regressão e suas rotas pelos testes PostgreSQL. |
| Média funcional | Cadastro de produto com saldo inicial não gerava movimentação; a origem do saldo não aparecia no histórico. | Registrar ENTRADA com saldo 0→inicial, motivo e autor na mesma transação do produto, apenas se saldo >0. Sem backfill ou atribuição de registros históricos. Atualizar histórico no frontend após o cadastro. |
| Média funcional | Logout ignorava falha de rede/resposta e apresentava tela desconectada mesmo que o cookie ainda fosse válido no servidor. | Exigir confirmação da API; em erro, informar que é preciso tentar sair novamente. 401 já significa sessão inválida. |
| Baixa funcional | Filtro “Somente disponíveis” excluía produtos com saldo positivo abaixo do mínimo. | Disponibilidade agora significa saldo >0; o filtro de estoque baixo permanece independente. |
| Baixa UI | Menu “Novo produto” aparecia para funcionário, embora a seção estivesse oculta. Diálogos abertos podiam bloquear o login após expiração. Texto longo no histórico podia exceder sua coluna. | Ocultar link por perfil, fechar diálogos ao mostrar login, impedir foco no conteúdo principal sem sessão e quebrar texto longo no histórico. |
| Documentação/CI | README e roteiro descreviam pedidos antigos e senha do painel no `.env`. Relatório de etapa tinha afirmações históricas apresentadas como atuais. CI só verificava sintaxe JS. | Documentação atualizada e marcada como histórica quando aplicável; testes de frontend e validação do Compose local adicionados ao workflow. |

## Verificações efetivamente executadas

Ambiente: Windows com Docker Desktop/Linux Engine; imagens construídas a partir dos Dockerfiles do repositório; PostgreSQL 15 exclusivo, descartável, em `tmpfs`; serviços sob projeto Compose separado `marcia-audit-20261113`. Portas de teste: 18080/13001, ambas em loopback. Credenciais fictícias exclusivas do teste. O Compose de auditoria fica fora do repositório para não interferir na configuração existente.

| Verificação | Resultado |
|---|---|
| Suíte original em banco novo, `TEST_POSTGRES=1` | **60 passed in 1.34s**. Nenhum teste de integração ignorado. |
| Suíte após correções em outro banco novo | **64 passed in 1.71s**. Inclui 4 casos novos: saldo inicial 0/positivo, ciclo de troca/reset com revogação de sessões e bloqueio de login/liberação após prazo. |
| Primeira rodada após mudança de estoque inicial | 63 passaram e 1 falhou porque o teste antigo esperava uma única movimentação. A expectativa foi corrigida para conferir ENTRADA/admin e SAIDA/funcionário em ordem; depois houve a aprovação completa acima. |
| Frontend, `node --test frontend/tests/forms.test.cjs` | **6 aprovados**. Usa os handlers reais em um DOM mínimo simulado; reproduz a perda de `currentTarget`, verifica logout com falha, atualização do histórico e filtro de disponibilidade. Não substitui navegador real. |
| Sintaxe JS | `node --check frontend/script.js`: aprovado. |
| Compose local e Oracle | `docker compose config --quiet` e `docker compose -f compose.oracle.yaml config --quiet`, com valores fictícios: aprovados. |
| Docker real | Build e inicialização de PostgreSQL, backend e Nginx aprovados na configuração isolada; `/api/health` e login funcionando através do proxy. |
| Navegador com API real | Login admin, cadastro de usuário antes/depois da correção, produto com nome de 100 caracteres e saldo inicial, pedido com 2 produtos (2 e 3 unidades), lista dos itens e autor, saídas no histórico, logout e login de funcionário com cadastro/admin ocultos. Sem erros/warnings capturados no console na consulta final. |
| Responsividade | Medições de toda a página e inspeção visual em 1920×1080, 768×1024, 390×844 e 320×740; nenhum elemento medido de main/header/footer excedeu a largura da viewport. Capturas foram entregues com a auditoria. São viewports de navegador desktop, não dispositivos físicos ou Safari/iOS. |
| Revisão do patch | `git -c core.whitespace=cr-at-eol diff --check`: aprovado. A opção respeita os finais CRLF já presentes na base. |

Os testes existentes cobrem Argon2id, validações, proteção de rotas, funcionário sem administração, CSRF, revogação por versão, identificação do autor, rollback de erros e de falha SQL induzida, produtos inexistentes/repetidos, quantidades inválidas, estoque insuficiente, pedidos simultâneos em ordem inversa, snapshots e migração antiga executada duas vezes sem alteração dos registros preservados.

## CI confirmado no GitHub antes das correções

As execuções abaixo retornaram `completed/success` na API de Actions. O conector de execuções por commit retornava apenas eventos de PR; foi necessário consultar as execuções push pela API pública, sem credenciais descobertas no repositório.

- `0f2aa8f`: https://github.com/gavassohenrique/Marcia_Salgados/actions/runs/43358412773
- `6c720d8`: https://github.com/gavassohenrique/Marcia_Salgados/actions/runs/43357723558
- `3bce6c4`: https://github.com/gavassohenrique/Marcia_Salgados/actions/runs/43292167519

O resultado da CI desta branch deve ser consultado no PR correspondente; o resultado anterior não valida mudanças posteriores.

## Consistência e segurança

- Nginx encaminha `/api/` para Flask removendo o prefixo. Frontend usa sessão same-origin e CSRF nas escritas. Perfis são impostos no servidor, além da ocultação na interface.
- Sessões têm HttpOnly, SameSite Strict e prazo de 8 horas; versão/estado da conta são consultados no banco. Argon2id e bloqueio por conta após falhas estão implementados. Cookie Secure é habilitado em Oracle/Kubernetes e desabilitado no Compose HTTP local.
- SQL recebe parâmetros, estoque usa bloqueios e commits/rollbacks. Itens preservam nome/preço; histórico de movimentações usa nome atual do catálogo. Pedidos novos bloqueiam nova saída manual vinculada; pedidos legados continuam aceitando vínculo manual.
- `database/init.sql` e ConfigMap inicializam o esquema base; `preparar_banco()` complementa a migração de itens ao iniciar. Dockerfile inclui as migrações. O comando Oracle migra antes de subir Gunicorn. Não é falha que a migração de itens não esteja duplicada no init.sql.
- Banco sem porta pública nos Composes. Compose local limita portas a loopback; Oracle expõe apenas Caddy em 80/443. Kubernetes permanece exemplo acadêmico com TLS a provisionar.
- Texto dinâmico é escapado na interface e CSV trata prefixos de fórmula. Não foi confirmado SQL injection, XSS, bypass de autenticação/perfil ou segredo operacional embutido no estado atual revisado. Essa conclusão é limitada à análise executada, não uma certificação de segurança ou ausência de vulnerabilidades.
- Segredos reais, volumes e `.env` do usuário não foram copiados, impressos, publicados ou alterados. `docker compose config` foi substituído por `--quiet` na instrução local para evitar impressão acidental de variáveis.

## Pendências e limites explícitos

1. **Reenvio de pedido:** POST não tem chave de idempotência. A UI bloqueia clique simultâneo, mas reenviar depois de perda de resposta pode criar outro pedido e outra baixa. É comportamento documentado, ainda requer uma decisão de contrato para garantir reenvio idempotente. Não houve backfill nem deduplicação automática de pedidos existentes.
2. **Consulta de pedidos:** somente os últimos 100 são listados; não há busca/paginação, edição/cancelamento ou estorno vinculado de pedido. Pedidos antigos fora do limite não aparecem para vínculo manual na interface.
3. **Rastreabilidade histórica:** não se inventou saldo inicial/autor de registros antigos. Não há trilha própria de todas as alterações de produtos/perfis/senhas nem snapshots de nome do autor; nomes exibidos são os atuais.
4. **Relatórios previstos:** não há geração automática de PDF, envio de e-mail ou rotina periódica implementados. Documentos acadêmicos antigos são propostas/registro histórico. Não foram reescritos PDFs nem dados pessoais presentes neles; revisar adequação antes de divulgação.
5. **Operação real:** não executados Oracle/ARM64, emissão/renovação HTTPS, Kubernetes, restauração de backup, atualização do volume real do usuário, browsers/dispositivos físicos, acessibilidade com leitor de tela e testes de carga/soak. Foram usados esquema antigo sintético e dados fictícios, não o banco existente.
6. **Dependências e disponibilidade:** não houve auditoria CVE ou scanner dinâmico externo. Versões por intervalo/tags reduzem reprodutibilidade. Não há rate limit global de login nem paginação do catálogo; esses pontos merecem endurecimento antes de uso público com volume relevante.

## Como reproduzir os testes

Em ambiente exclusivo, crie um PostgreSQL 15 novo com banco `test_*` e configure `DB_HOST`, `DB_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `FLASK_SECRET_KEY` e `TEST_POSTGRES=1`. Não aponte a suíte para um banco de trabalho. O teste inicial espera tabela de usuários vazia.

```text
python -m pip install -r backend/requirements.txt
python -m pytest backend/tests -q
node --check frontend/script.js
node --test frontend/tests/forms.test.cjs
docker compose config --quiet
docker compose -f compose.oracle.yaml config --quiet
```

Preserve backups e volumes existentes. A publicação de código nesta branch não atualiza automaticamente a instalação do usuário nem a VM.
