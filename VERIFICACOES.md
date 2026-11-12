# Verificações da revisão — 12/11/2026

Este registro diferencia testes efetivamente executados de verificações pendentes, sem presumir resultados.

## Executadas neste ambiente

- Verificação sintática de `backend/app.py` e dos arquivos de teste Python (`py_compile`).
- Verificação sintática de `frontend/script.js` (`node --check`).
- Leitura e validação sintática de `docker-compose.yaml` e dos manifests de Kubernetes pelo parser YAML Python (não substitui `docker compose config`/`kubectl`).
- Navegador Chromium automatizado com **API simulada**: login, saúde visual, catálogo, métricas, busca, filtro, cadastro com vírgula decimal, modal de edição, pedido de referência, saída vinculada, erro de estoque insuficiente, navegação móvel e ausência de rolagem horizontal nas duas resoluções examinadas. **Nenhum backend real foi utilizado nesse teste.**
- Integridade de ambos os PDFs corrigidos (abertura e renderização) e do JPEG.
- Verificação estática de rotas duplicadas e revisão do SQL.

## Pendentes (exigem ambiente com dependências ou Docker)

- Executar Flask/Pytest reais: `python -m pip install -r backend/requirements.txt` e `python -m pytest backend/tests -q`.
- Validar `docker compose config`, construir containers, inicializar PostgreSQL com volume existente e volume novo, login, CRUD e persistência após reinício.
- Testar concorrência real de duas movimentações simultâneas em PostgreSQL (a implementação usa `SELECT ... FOR UPDATE`).
- Implantar e verificar Kubernetes; a configuração exige armazenamento e secret TLS do cluster.
- Revisão final de conformidade ABNT/A4 de acordo com a orientação da instituição; PDFs históricos permaneceram no tamanho Letter para preservar a diagramação e só tiveram numeração/sumário corrigidos.

## Recomendações antes de apresentar

1. No Windows, configure `.env` com segredos próprios sem publicar credenciais.
2. Rode `docker compose config` e `docker compose up -d --build`.
3. Confira `http://localhost:3000/health`, login e cada fluxo do roteiro.
4. Execute `python -m pytest backend/tests -q`.
5. Não afirme ter realizado testes de integração ou implantação enquanto não houver evidências desses testes.
