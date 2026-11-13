# Márcia Salgados — Controle de estoque e rastreabilidade

Projeto acadêmico em **Flask + PostgreSQL + HTML/CSS/JavaScript + Docker Compose**, com cadastro de produtos, pedidos com itens e quantidades, baixa automática e rastreabilidade de quem movimentou os produtos.

> Escopo: salvar um pedido com itens registra as saídas de estoque na mesma transação. Este sistema não faz faturamento, pagamentos ou emissão de notas fiscais. O Compose padrão é local; a configuração Oracle é uma base de implantação que exige validação no servidor.

## Funcionalidades

- Login com **e-mail e senha individual**, usuários armazenados no **PostgreSQL** e senhas com **hash Argon2id** (nunca texto puro).
- Perfis **ADMIN** e **FUNCIONARIO**. Administradores criam usuários, alteram permissões, desativam contas, redefinem senhas e cadastram/editam produtos. Funcionários consultam produtos, registram pedidos e movimentam estoque.
- Alteração da própria senha. Mudanças de senha, perfil ou desativação invalidam as sessões anteriores do usuário.
- Proteção CSRF, cookie de sessão HttpOnly/SameSite, bloqueio temporário após cinco senhas erradas para uma conta, e respostas de erro em JSON.
- Cadastro e edição de produtos; filtro por estoque mínimo; entradas e saídas transacionais usando `SELECT ... FOR UPDATE`.
- Pedidos com 1 a 100 produtos distintos, quantidades positivas, nomes/preços preservados e baixa transacional. Veja [regras e limites](docs/PEDIDOS.md).
- Produtos novos com saldo inicial positivo geram uma entrada auditada. Saldos históricos não são reconstruídos nem atribuídos retroativamente.
- Histórico com identificação de quem realizou cada movimentação; registros anteriores à implantação do recurso continuam preservados, sem atribuição de usuário.
- Integração local com Nginx no frontend, Flask no backend e PostgreSQL, sem expor o banco na rede.

## Implantação pública gratuita: Oracle Cloud Always Free

O projeto dispõe de um Compose específico para servidores públicos: [`compose.oracle.yaml`](compose.oracle.yaml), com Gunicorn, cookies Secure, rede interna para o banco e proxy HTTPS automático via Caddy. O `docker-compose.yaml` original continua destinado ao uso local.

**Leia o [guia completo da Oracle Cloud](docs/ORACLE_CLOUD.md)** antes de liberar a aplicação na internet. Não exponha PostgreSQL ou Flask diretamente. Os recursos Always Free podem estar indisponíveis ou ser recuperados por ociosidade; não há garantia de disponibilidade e é necessário manter backups externos.

## Primeira configuração no PC de casa (Windows / PowerShell)

**Requisitos:** Git, Docker Desktop instalado e iniciado. Não precisa instalar Flask ou PostgreSQL separadamente — o Docker cuida disso. O Live Server do VS Code não executa a API.

Abra o PowerShell **na pasta do projeto** (a que contém `docker-compose.yaml`) e execute:

```powershell
git pull origin main
# Só copie o exemplo se você AINDA não tiver um .env configurado:
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Configure as quatro variáveis no arquivo **`.env` (nunca em `.env.example`)**:

```dotenv
POSTGRES_USER=user
POSTGRES_DB=appdb
POSTGRES_PASSWORD=SUBSTITUA_POR_SENHA_FORTE_DO_BANCO
FLASK_SECRET_KEY=SUBSTITUA_POR_CHAVE_ALEATORIA
```

- `POSTGRES_PASSWORD`: senha **da conexão ao banco**. Não é a senha do painel.
- `FLASK_SECRET_KEY`: chave usada para assinar os cookies de sessão; mantenha privada e estável entre reinicializações.
- `POSTGRES_USER` e `POSTGRES_DB`: podem ficar com os valores de exemplo se o banco for novo.
- **Não use `APP_ADMIN_PASSWORD`:** o login do painel não depende mais dessa variável. Senhas de usuários serão guardadas como hashes no PostgreSQL.

Para gerar uma chave aleatória para `FLASK_SECRET_KEY`:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Se não tiver Python instalado no Windows, você pode gerar a chave em um terminal PowerShell com:

```powershell
$b = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
[BitConverter]::ToString($b).Replace('-','').ToLower()
```

Depois de salvar `.env`, verifique e suba os serviços:

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

**Primeiro administrador (uma única vez, depois que o backend estiver saudável):**

```powershell
docker compose exec backend python manage.py criar-admin
```

O comando pede **nome, e-mail, senha e confirmação**. A senha não aparece enquanto você digita, não fica no histórico do terminal e é persistida no banco **apenas como hash Argon2id**. Use uma senha exclusiva de pelo menos 8 caracteres, com uma letra maiúscula, uma minúscula e um símbolo especial (como !, @, # ou _). Números são opcionais; recomendamos senhas mais longas, sempre que possível. Se já houver usuários, o comando não recriará nem sobrescreverá contas; use o painel administrativo para adicionar outras.

Abra **http://localhost:8080** e entre com o e-mail e senha criados. Para verificar os serviços:

- http://localhost:8080/api/health — JSON com `status: ok` e `banco: conectado` quando ambos estiverem saudáveis.
- http://localhost:8080/api/auth/status — JSON de status de autenticação (sem exibir senhas).

## Criar usuários e registrar operações

1. Entre como **Administrador**.
2. Abra **Usuários** no menu. Preencha nome, e-mail, senha inicial e perfil (Administrador ou Funcionário). A senha deve ter pelo menos 8 caracteres, maiúscula, minúscula e símbolo especial; números são opcionais.
3. Um funcionário pode consultar produtos, salvar pedidos com itens e registrar entradas/saídas. O pedido já baixa o estoque; não registre outra saída para a mesma entrega. Não pode cadastrar/editar produtos nem administrar usuários.
4. Cada entrada/saída registra o **nome do usuário autenticado** no histórico. Registros antigos são mantidos sem autor identificado.
5. Para trocar sua senha, use **Minha senha**. O administrador também pode redefinir senhas de outros usuários ou desativá-los.

Contas não são cadastradas publicamente. A primeira conta é criada por um comando local autorizado. Caso a senha de todos os administradores seja perdida, será necessária recuperação administrativa controlada no servidor; não há formulário público de redefinição.

## Apresentação acadêmica em outro computador

Se você apresentar **no mesmo computador de casa**, basta iniciar o Docker e entrar com suas credenciais.

Se apresentar **em outro computador**, clone o repositório, instale o Docker Desktop, crie um `.env` próprio (não copie suas senhas pessoais), execute `docker compose up -d --build`, e cadastre **um novo administrador** pelo comando acima. A instalação começa com seu próprio banco de dados local. Cadastre usuários e produtos **fictícios** para demonstração. O GitHub **não sincroniza automaticamente os dados** do PostgreSQL entre computadores.

Para comprovar o fluxo na apresentação: faça login como admin, crie um funcionário, entre como funcionário, registre uma movimentação, volte para o admin e mostre o autor no histórico. Prepare isso antes da aula; não conte com a instalação de última hora.

## Banco de dados antigo: preservar os dados

A inicialização do backend executa migrações **aditivas**: cria a tabela `usuarios` e a coluna `movimentacoes.usuario_id` se ainda não existirem, sem apagar produtos e movimentações. Não apague volumes para tentar corrigir um erro: **NÃO use `docker compose down -v`**.

O `database/init.sql` só roda automaticamente quando o volume PostgreSQL é criado pela primeira vez. Para volumes antigos, a API também prepara o esquema ao iniciar.

**Atenção:** se a instância antiga foi criada com `POSTGRES_PASSWORD=password`, trocar a variável no `.env` não altera automaticamente a senha já armazenada dentro do banco. Você precisa atualizar a senha **no banco existente** de forma controlada, ou reutilizar temporariamente a senha anterior até migrar. Nunca apague o volume para contornar isso. Se encontrar falha de autenticação do PostgreSQL, preserve o volume e confira os logs antes de executar mudanças.

Os dados ficam no volume `postgres_data` do Compose, não dentro do repositório Git. Faça backups para dados que importem. Para conferência local (valores padrão do exemplo):

```powershell
docker compose exec postgres psql -U user -d appdb
```

```sql
SELECT id, nome, email, perfil, ativo FROM usuarios ORDER BY id;
SELECT id, nome, estoque FROM produtos ORDER BY id;
SELECT id, produto_id, tipo, quantidade, usuario_id FROM movimentacoes ORDER BY id DESC;
```

## Testes e diagnóstico

Testes de unidade/mocks de banco (em ambiente com Python e dependências instaladas):

```powershell
python -m pip install -r backend/requirements.txt
python -m pytest backend/tests -q
node --check frontend/script.js
node --test frontend/tests/*.test.cjs
```

Para verificar e testar a aplicação completa, use Docker/PostgreSQL reais, depois confira no navegador login, permissões, cadastro, estoque, histórico, alteração de senha e invalidação de sessões. Os testes Python com mocks **não substituem** testes de integração com PostgreSQL real.

```powershell
docker compose ps
docker compose logs --tail=100 backend
docker compose logs --tail=100 frontend
docker compose logs --tail=100 postgres
curl.exe -i http://localhost:8080/api/health
curl.exe -i http://localhost:8080/api/auth/status
```

Se vir `Forbidden`, HTML inesperado ou `Failed to parse JSON` ao entrar, verifique se abriu **http://localhost:8080** com Docker em execução. **Não use Live Server** para o sistema completo.

## Organização

```text
backend/app.py               API Flask, autenticação e migrações aditivas
backend/manage.py            cadastro interativo do primeiro administrador
backend/tests/              testes automatizados
database/init.sql            inicialização de banco novo
frontend/                    painel web, administração e Nginx
k8s/                         exemplo acadêmico opcional de Kubernetes
PDF/                         documentos acadêmicos
```

O diretório `k8s/` é um **exemplo acadêmico**, não uma implantação pública pronta. Exige instalação de TLS, armazenamento persistente e configuração própria; a versão Docker Compose local é a recomendada para apresentação.

**Status de validação:** a sintaxe e os fluxos com API simulada podem ser verificados sem banco; um resultado de navegação simulada ou YAML válido não comprova execução real de Flask + PostgreSQL ou implantação Kubernetes. Antes de apresentar, faça os testes locais.
