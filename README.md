# Márcia Salgados — Controle de estoque e rastreabilidade

Sistema web acadêmico para cadastro de produtos, controle de estoque e associação de **saídas de estoque a pedidos de referência**. O frontend é HTML/CSS/JavaScript; a API utiliza Python/Flask; a persistência fica no PostgreSQL. Os três serviços são integrados com Docker Compose.

> **Escopo:** pedidos de referência permitem identificar cliente e vincular movimentações de saída, mas **não** constituem um módulo financeiro de vendas, faturamento, emissão fiscal ou baixa automática de vários itens. Relatórios PDF e envio por e-mail são ideias para evolução futura.

## Funcionalidades

- Login por senha configurada fora do código; sessão com cookie HttpOnly e proteção CSRF.
- Cadastro, edição e pesquisa de produtos; estoque mínimo e indicadores.
- Entrada e saída com transações, bloqueio SQL (`FOR UPDATE`) para não perder atualizações concorrentes e validação contra estoque negativo.
- Cadastro de pedido de referência com cliente, e vínculo opcional de pedido na saída de estoque.
- Histórico de movimentações (50 por página), carregamento incremental e exportação CSV dos registros carregados.
- Formatação monetária brasileira, edição em modal, status real da API e layout móvel com navegação acessível.
- Docker Compose, configuração de Kubernetes para ambiente de demonstração e testes automatizados em Python.

## Início rápido (Windows / PowerShell)

Requisitos: Git, Docker Desktop com Compose, porta local 8080 disponível.

```powershell
# Execute na pasta do projeto:
Copy-Item .env.example .env
notepad .env
```

**Troque as três configurações sensíveis** por valores fortes: `POSTGRES_PASSWORD`, `APP_ADMIN_PASSWORD` e `FLASK_SECRET_KEY` (mínimo recomendado de 32 bytes aleatórios). O `.env` está no `.gitignore` e **não deve ser enviado para o GitHub**.

Para gerar uma chave aleatória para copiar no `.env`:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Em seguida:

```powershell
docker compose config
docker compose up -d --build
docker compose ps
```

- **Painel:** http://localhost:8080
- **API (local):** http://localhost:3000
- **Saúde da API e do banco:** http://localhost:3000/health

Faça login no painel com `APP_ADMIN_PASSWORD` do arquivo `.env`. Os serviços foram publicados apenas em `127.0.0.1`, para uso local. A porta PostgreSQL não é publicada na máquina host.

### Conferir os dados no banco

```powershell
docker compose exec postgres psql -U user -d appdb
```

Se alterar `POSTGRES_USER` ou `POSTGRES_DB` no `.env`, use seus valores no comando. Consultas úteis:

```sql
SELECT id, nome, estoque, estoque_minimo FROM produtos ORDER BY id DESC;
SELECT id, cliente, referencia FROM pedidos ORDER BY id DESC;
SELECT id, produto_id, tipo, quantidade, pedido_id, criado_em FROM movimentacoes ORDER BY id DESC;
```

O arquivo `database/init.sql` é aplicado **somente ao criar um volume vazio**. Se o volume já existir, a API cria as tabelas ausentes sem apagar registros anteriores. Não execute `docker compose down -v` para tentar corrigir erros: **o `-v` apaga o volume do banco**.

**Atenção ao banco anterior:** se um volume antigo foi criado com a senha `password`, mudar `POSTGRES_PASSWORD` no `.env` **não altera a senha armazenada no PostgreSQL**. Para preservar dados, entre no banco localmente com `docker compose exec postgres psql -U user -d appdb`, execute `ALTER ROLE "user" WITH PASSWORD 'SUA_NOVA_SENHA_FORTE';`, saia com `\q` e reinicie o backend. Substitua os valores de exemplo pelos da sua instalação e não grave a senha no histórico de comandos. Nunca apague o volume para contornar esse problema.

## Problemas de login: `Forbidden` ou resposta inválida

O painel **não é uma página estática independente**: ele depende da API Flask, acessível via proxy Nginx em `/api/`.

1. Abra o endereço **http://localhost:8080** depois de executar `docker compose up -d --build`. Não use "Open with Live Server", `file://`, GitHub Pages ou visualização estática do VS Code para realizar o login.
2. No navegador, confira **http://localhost:8080/api/health**. A resposta esperada, quando o backend e banco estiverem saudáveis, é JSON como `{"status":"ok","banco":"conectado"}`.
3. No PowerShell, na pasta do projeto, execute os comandos a seguir e confira o status e os logs:

```powershell
docker compose config
docker compose ps
docker compose logs --tail=100 frontend
docker compose logs --tail=100 backend
curl.exe -i http://localhost:8080/api/health
curl.exe -i http://localhost:8080/api/auth/status
```

O caminho `/api/auth/status` deve retornar JSON com `configurado` e `autenticado`; não precisa de senha. O login é `POST /api/auth/login`, não uma página HTML. Se a resposta começar com `Forbidden` e não for JSON, o bloqueio pode estar no endereço/hospedagem ou no proxy, **não é possível concluir que a senha esteja incorreta**. Se os testes acima retornarem JSON válido, verifique a aba Rede (Network) do navegador para a requisição `POST /api/auth/login` e confira apenas o status HTTP e o tipo da resposta; **não compartilhe sua senha nem tokens de sessão**.

Se a porta 8080 já estiver em uso por outra aplicação, encerre esse serviço antes de iniciar o Compose ou ajuste a publicação da porta no `docker-compose.yaml`.

## Testes

Para instalar e executar os testes Python em um ambiente com acesso às dependências:

```powershell
python -m pip install -r backend/requirements.txt
python -m pytest backend/tests -q
node --check frontend/script.js
```

O comando `npm test` (se Node estiver instalado) chama os mesmos testes Python. Os arquivos de testes antigos de Express/Node foram removidos, pois o backend atual utiliza Flask.

Os testes Python cobrem validações, autenticação/CSRF e rotas usando **mocks de banco**. Eles não substituem testes de integração com PostgreSQL real e Docker. O uso completo deve ser verificado com Compose na máquina de apresentação.

Para ver logs:

```powershell
docker compose logs --tail=100 backend
docker compose logs --tail=100 frontend
docker compose logs --tail=100 postgres
```

## Rotas principais

| Método | Rota | Descrição |
|---|---|---|
| GET | `/health` | Consulta de saúde do banco, sem exigir login |
| GET / POST | `/auth/status`, `/auth/login` | Estado de sessão e autenticação |
| POST | `/auth/logout` | Termina sessão (requer CSRF) |
| GET / POST | `/produtos` | Listagem e cadastro |
| PUT | `/produtos/{id}` | Edição sem alterar saldo |
| GET / POST | `/pedidos` | Pedido de referência |
| POST | `/estoque/movimentacao` | Entrada/saída; aceita `pedido_id` apenas em saídas |
| GET | `/movimentacoes?limite=50&offset=0` | Histórico paginado |

No navegador, as rotas são acessadas via proxy Nginx em `/api/`. A API exige login e cabeçalho `X-CSRF-Token` para gravações, conforme o estado retornado por `/auth/status`.

## Kubernetes (opcional)

O diretório `k8s/` é um exemplo de implantação acadêmica, **não um pacote de produção pronto**. Possui PVC persistente, schema SQL alinhado ao backend e acesso via Ingress HTTPS (exige TLS válido e controlador Ingress Nginx).

1. Crie `k8s/secret.yaml` a partir de `k8s/secret.example.yaml`; substitua os valores. O arquivo real é ignorado pelo Git.
2. Configure um secret TLS `msalgados-tls` para o host de demonstração, `msalgados.local`.
3. Ajuste as imagens e o armazenamento ao seu cluster e aplique os manifests. Dependendo do cluster, é necessário provisionamento de PV/StorageClass.
4. Monitore rollout, saúde do banco e logs; **não considere essa implantação testada apenas porque os YAMLs são válidos**.

Para implantação pública real ainda são necessários HTTPS com certificado confiável, rotação de segredos, proteção contra tentativas repetidas de login, backups, observabilidade e testes completos de segurança.

## Organização

```text
backend/     API Flask e testes pytest
database/    SQL para bootstrap inicial
frontend/    Painel web e Nginx
k8s/         Exemplo de deployment, services, PVC e segredos de exemplo
PDF/         Documentos acadêmicos
```

## Apresentação acadêmica

O arquivo [ROTEIRO_APRESENTACAO.md](ROTEIRO_APRESENTACAO.md) apresenta uma demonstração proposta. Mostre apenas o que funcionar efetivamente no computador da apresentação. **Não declare execução de Docker, pytest ou PostgreSQL se esses testes não tiverem sido realizados.**
