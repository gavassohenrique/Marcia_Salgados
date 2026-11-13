# Verificações e limites — autenticação por usuários (12/11/2026)

> Registro histórico. Para as verificações de 13/11/2026 com Docker e PostgreSQL reais, correções, testes de frontend e limites atuais, veja [a auditoria atual](docs/AUDITORIA-2026-11-13.md). As restrições de ambiente abaixo se referem à execução de 12/11, não à auditoria posterior.

## Executados neste ambiente

- Arquivos Python compilados/analisados sintaticamente via `py_compile` e `ast`.
- Sintaxe de JavaScript verificada com `node --check frontend/script.js`.
- Parse do `docker-compose.yaml` e dos manifests Kubernetes com PyYAML (não equivale a validar com Docker ou kubectl).
- Hash Argon2id criado e verificado com a biblioteca `argon2-cffi` local.
- Navegador Chromium com respostas da API **simuladas**: login de administrador, cadastro de funcionário, logout, login do funcionário, visualização de permissões e ausência de erros JavaScript.
- Revisão estática das migrações aditivas e das rotas da API.

## Não executados aqui

- Testes Pytest do backend: Flask e psycopg2 não estão instalados neste ambiente e a instalação por pip falhou por DNS/rede.
- PostgreSQL real e Docker Compose: não disponíveis neste ambiente. Por isso a migração de um volume já existente e a execução ponta a ponta **não foram validadas**.
- Kubernetes e acesso público: não implantados.

Uma rotina GitHub Actions foi adicionada para instalar dependências, rodar testes unitários e um teste de integração com banco PostgreSQL isolado e descartável. O resultado dela deve ser confirmado no GitHub; não presuma sucesso somente porque o workflow existe.

## Antes de apresentar

1. No PC de casa, siga o `README.md`: `.env`, `docker compose up -d --build` e `python manage.py criar-admin` dentro do container.
2. Faça login, crie um funcionário, registre movimentações e confirme a coluna `usuario_id` no PostgreSQL.
3. Execute os testes Pytest e confira o status do GitHub Actions.
4. Não apague volumes existentes; dados do PostgreSQL não vêm com o `git clone`.
