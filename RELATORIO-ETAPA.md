# Relatório de Análise do Estado Atual — Marcia Salgados

## 1. Situação atual do projeto

O projeto Marcia Salgados encontra-se em uma etapa funcional avançada. A funcionalidade principal de controle de estoque já foi desenvolvida e integrada à branch `main`.

O sistema possui uma aplicação web com frontend, backend em Python/Flask e banco de dados PostgreSQL. A estrutura também contempla Docker e arquivos de implantação em Kubernetes.

O fluxo principal está implementado: o usuário interage com a interface, os dados são enviados à API, o backend realiza validações e o PostgreSQL armazena os dados, permitindo que a interface apresente o estoque atualizado.

Atualmente existem as branches `main`, `feat/controle-estoque-funcional`, `feat/melhoria-design-apresentacao` e `docs/relatorio-etapa`. A branch de controle de estoque já foi incorporada à `main`. A branch de melhoria de design possui o Pull Request #2 aberto.

## 2. Funcionalidades já desenvolvidas

- Cadastro e listagem de produtos;
- Registro de entradas e saídas de estoque;
- Validação de preço e estoque;
- Retorno do estoque atualizado;
- Integração do frontend com a API;
- Persistência dos dados no PostgreSQL;
- Histórico/rastreabilidade de estoque;
- Testes automatizados do backend;
- Containerização com Docker;
- Estrutura de implantação com Kubernetes;
- Interface com melhorias de usabilidade, tooltips e acessibilidade;
- Identidade visual e apresentação em processo de melhoria.

## 3. Funcionalidades ainda pendentes

1. Finalizar e incorporar o Pull Request #2 à `main`.
2. Realizar uma validação completa após a integração das melhorias visuais.
3. Padronizar a documentação sobre a quantidade e o tipo de testes executados.
4. Validar o fluxo completo de cadastro, entrada, saída, histórico e tratamento de erros.
5. Confirmar a execução da aplicação por Docker em ambiente limpo.
6. Validar a implantação em Kubernetes, caso exigida na entrega.
7. Finalizar o roteiro e a gravação da demonstração.

## 4. Principais problemas encontrados

### 4.1 Pull Request de melhoria ainda não integrado

O Pull Request #2, relacionado à modernização da interface e à apresentação, permanece aberto. Portanto, essas alterações ainda não fazem parte da `main`.

### 4.2 Divergência na documentação dos testes

O Pull Request #1 registra uma suíte com 6 testes, enquanto o Pull Request #2 informa 4 testes do backend aprovados com Pytest. Essa informação precisa ser conferida e padronizada antes da entrega.

### 4.3 Necessidade de validação final integrada

As partes principais do sistema já estão desenvolvidas, mas é necessária uma validação final considerando frontend, backend, PostgreSQL e movimentações de estoque funcionando em conjunto.

### 4.4 Implantação precisa ser comprovada

O projeto possui estrutura para Docker e Kubernetes, porém a entrega deve deixar claro qual ambiente será utilizado e comprovar seu funcionamento no estado final.

### 4.5 Documentação deve acompanhar o estado final

O README deve permanecer alinhado à versão final do sistema, principalmente quanto aos testes, funcionalidades e procedimentos de execução.

## 5. Próxima etapa de desenvolvimento

A próxima etapa será concentrada na estabilização e preparação do projeto para a entrega final:

1. Revisar o PR #2;
2. Integrar as melhorias aprovadas à `main`;
3. Executar os testes automatizados;
4. Corrigir eventuais falhas;
5. Testar o sistema completo pelo Docker;
6. Confirmar cadastro, entrada, saída, histórico e validações;
7. Confirmar a persistência no PostgreSQL;
8. Validar Kubernetes, se necessário;
9. Atualizar a documentação;
10. Finalizar o roteiro e realizar a gravação da apresentação.

## 6. Divisão das tarefas entre os integrantes

### Desenvolvimento e integração
- Revisar backend e regras de estoque;
- Executar e corrigir testes;
- Validar PostgreSQL;
- Verificar Docker e Kubernetes;
- Corrigir problemas técnicos;
- Realizar a integração final na `main`.

### Interface, documentação e apresentação
- Finalizar a interface;
- Validar responsividade, usabilidade e acessibilidade;
- Revisar o fluxo visual;
- Atualizar o README;
- Organizar o roteiro;
- Preparar a demonstração em vídeo;
- Conferir a coerência entre documentação e sistema.

### Atividades em conjunto
- Definição das próximas funcionalidades;
- Teste completo do sistema;
- Conferência do resultado final;
- Revisão antes da entrega;
- Validação da apresentação.

## 7. Conclusão

O projeto já possui a funcionalidade principal necessária para demonstrar um fluxo de entrada de dados, processamento e geração de resultado. O controle de estoque está integrado ao backend e ao PostgreSQL, com validações e rastreabilidade.

A prioridade desta etapa é concluir as melhorias pendentes, validar todas as funcionalidades de forma integrada, corrigir as inconsistências de documentação e preparar o projeto para a apresentação e entrega final.