# Marcia Salgados

Sistema de gestão e publicidade para a empresa Marcia Salgados, com foco em controle de estoque e rastreabilidade de pedidos.

## Tecnologias

- HTML
- CSS
- JavaScript
- Python
- Flask
- PostgreSQL
- Docker
- Kubernetes
- Pytest

## Funcionalidades

- Cadastro de produtos
- Consulta de produtos
- Controle de estoque
- Entrada de estoque
- Saída de estoque
- Histórico de movimentações
- Associação de saída ao pedido
- Alertas de estoque mínimo
- Validação e tratamento de erros
- Painel responsivo com indicadores de estoque
- Identificação visual de produtos abaixo do estoque mínimo

## Interface

A interface foi organizada como um painel de trabalho, com resumo do estoque, catálogo de produtos, formulário de cadastro e histórico de movimentações. O visual é responsivo e mantém as principais ações acessíveis em computadores e celulares.

O roteiro completo, com falas divididas entre os integrantes e passos da demonstração, está em [`ROTEIRO_APRESENTACAO.md`](ROTEIRO_APRESENTACAO.md).

## Integração implementada

O fluxo principal da atividade está integrado:

1. **Interface:** o usuário cadastra produtos e registra entradas ou saídas de estoque.
2. **Processamento:** o frontend envia os dados para a API Python/Flask, que valida as informações e aplica a movimentação.
3. **Banco de dados:** o PostgreSQL armazena produtos e o histórico de movimentações.
4. **Resultado:** a interface consulta a API novamente e apresenta o estoque atualizado e o histórico.

O backend também impede saídas maiores que o estoque disponível e informa erros de validação ao usuário.

## Docker

Executar:

```bash
docker compose up -d --build
```

Frontend:

http://localhost:8080

Backend:

http://localhost:3000

Health check:

http://localhost:3000/health

## Verificação do banco de dados

O banco PostgreSQL pode ser verificado diretamente pelo container para confirmar que os dados enviados pelo sistema estão sendo armazenados corretamente.

Com os containers em execução, abra o PostgreSQL pelo PowerShell:

```bash
docker exec -it postgres_db psql -U user -d appdb
```

Para consultar os produtos cadastrados:

```sql
SELECT * FROM produtos ORDER BY id DESC;
```

Para consultar o histórico de entradas e saídas:

```sql
SELECT * FROM movimentacoes ORDER BY id DESC;
```

Também é possível consultar as movimentações junto ao nome do produto:

```sql
SELECT
    m.id,
    p.nome AS produto,
    m.tipo,
    m.quantidade,
    m.estoque_anterior,
    m.estoque_posterior,
    m.motivo,
    m.pedido_id,
    m.criado_em
FROM movimentacoes m
JOIN produtos p ON p.id = m.produto_id
ORDER BY m.id DESC;
```

Para sair do PostgreSQL:

```sql
\q
```

Esse procedimento permite demonstrar no vídeo que o cadastro e as movimentações realizados pela interface realmente são processados pelo backend Python/Flask e persistidos no PostgreSQL.

## Testes

```bash
cd backend
pip install -r requirements.txt
pytest
```

Os testes verificam a rota inicial e validações de dados do backend.

## Roteiro curto para o vídeo

1. Mostre as pastas `frontend`, `backend`, `database` e `k8s`.
2. Abra o sistema em `http://localhost:8080`.
3. Cadastre um produto com preço, estoque inicial e estoque mínimo.
4. Registre uma entrada e mostre o saldo sendo atualizado.
5. Registre uma saída e mostre o novo saldo e o histórico.
6. Tente retirar uma quantidade maior que o estoque e mostre o tratamento do erro.
7. Abra o PostgreSQL pelo comando `docker exec -it postgres_db psql -U user -d appdb` e execute `SELECT * FROM produtos;` e `SELECT * FROM movimentacoes;` para comprovar a persistência dos dados.
8. Explique: “o formulário envia os dados, a API Python processa e valida, o PostgreSQL armazena e a interface apresenta o resultado”.

## Kubernetes

Construir imagens:

```bash
docker build -t msalgados-backend:1.0 ./backend
docker build -t msalgados-frontend:1.0 ./frontend
```

Aplicar:

```bash
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/postgres-deployment.yaml
kubectl apply -f k8s/postgres-service.yaml
kubectl apply -f k8s/backend-deployment.yaml
kubectl apply -f k8s/backend-service.yaml
kubectl apply -f k8s/frontend-deployment.yaml
kubectl apply -f k8s/frontend-service.yaml
kubectl apply -f k8s/ingress.yaml
```

Verificar:

```bash
kubectl get pods
kubectl get services
kubectl get deployments
```


## Melhorias recentes

- **Busca de produtos:** localiza itens pelo nome sem alterar os dados armazenados.
- **Filtros de estoque:** permite exibir todos os produtos, somente os que atingiram o estoque mínimo ou somente os disponíveis acima do mínimo.
- **Edição de produtos:** permite atualizar nome, preço e estoque mínimo pela interface. O saldo atual é preservado; alterações de saldo devem ser registradas pela movimentação para manter a rastreabilidade.
- **Validação no frontend e backend:** confere nome obrigatório, preço positivo e quantidades inteiras não negativas. O backend continua sendo a validação definitiva.
- **Preço em formato brasileiro:** o formulário aceita separador decimal por vírgula ou ponto, como `8,50` e `8.50`.
- **Tooltips acessíveis:** dicas de contexto nos campos de nome, preço e estoque, disponíveis por mouse e foco do teclado.
- **Inicialização mais confiável:** o Docker Compose verifica a disponibilidade do PostgreSQL antes de iniciar o backend e configura o endereço do backend para o proxy do frontend.

### Como atualizar e testar

Depois de obter as alterações:

```powershell
git pull
docker compose config
docker compose up -d --build
docker compose ps
```

Abra http://localhost:8080 e teste a busca, o filtro de estoque, as dicas de contexto, a edição de um produto e uma movimentação de entrada ou saída. Confira a persistência no PostgreSQL seguindo a seção **Verificação do banco de dados** acima.

> Observação: as funcionalidades devem ser validadas no ambiente local após a reconstrução dos containers. O módulo completo de pedidos, autenticação de usuários, exportação de relatórios e backup automatizado permanece como evolução futura.
