# Roteiro de apresentação — Márcia Salgados

**Projeto acadêmico:** Automação de controle de estoque e rastreabilidade de pedidos  
**Integrantes:** Henrique Gavasso Neto e João Emanuel de Souza da Silva  
**Duração sugerida:** 5 a 7 minutos

## Antes da demonstração

- Copiar `.env.example` para `.env`, definir senhas próprias e executar `docker compose up -d --build`.
- Confirmar, **no computador da apresentação**, que `docker compose ps` mostra os serviços saudáveis, que `/health` responde, e que o painel em `http://localhost:8080` permite login.
- Manter dados fictícios de demonstração e anotar previamente o que foi realmente verificado.

## 1. Contexto e objetivo

Apresentar o problema do controle manual de estoque de salgados: produtos acabados, entradas de produção, saídas para pontos de venda e dificuldade de rastrear movimentações. O objetivo é centralizar cadastro, saldo e histórico.

## 2. Arquitetura

Mostrar as pastas: frontend HTML/CSS/JavaScript, backend Flask, database PostgreSQL e Docker Compose. Explicar que a aplicação web chama uma API, que faz validações e grava as operações no banco.

## 3. Acesso

Abrir o painel, entrar com a senha de demonstração. Explicar que ela fica configurada fora do código em `.env`, não no GitHub. Mostrar o indicador de saúde, que consulta a API.

## 4. Cadastro e busca

Cadastrar um produto fictício, por exemplo Risoles de queijo, preço R$ 6,50, estoque 20 e mínimo 5. Mostrar catálogo, indicadores, busca, filtro de estoque baixo e modal de edição. Explicar que editar dados cadastrais **não** altera o saldo.

## 5. Entrada de estoque

Registrar 10 unidades do produto, motivo "Nova produção". Verificar o novo saldo e o histórico.

## 6. Pedido e saída de estoque

Cadastrar um **pedido de referência**, por exemplo cliente "Posto Central". Na ficha do produto, selecionar Saída, informar 4 unidades e vincular o pedido. Mostrar a movimentação no histórico com o identificador do pedido. Esclarecer: o sistema ainda **não é um módulo financeiro de pedidos**, nem processa automaticamente um carrinho com vários itens.

## 7. Proteções e rastreabilidade

Tentar retirar mais unidades do que o estoque disponível e mostrar a mensagem de erro. Mostrar histórico e opção de exportação CSV dos registros carregados. Se a conexão com PostgreSQL tiver sido validada, consultar as tabelas pelo terminal:

```powershell
docker compose exec postgres psql -U user -d appdb
```

```sql
SELECT * FROM produtos ORDER BY id DESC;
SELECT * FROM pedidos ORDER BY id DESC;
SELECT * FROM movimentacoes ORDER BY id DESC;
```

## 8. Conclusão

Destacar ganhos de organização, histórico, validação e base para próximas automações. Como futuras melhorias, citar relatórios em PDF, envio de e-mail, relatórios consolidados por pedido, perfis de usuário e implantação com autenticação mais robusta.

**Nota de precisão:** este documento é roteiro; não é evidência de que Docker, banco ou testes ponta a ponta foram executados. Ajustar as falas conforme o resultado real da demonstração.
