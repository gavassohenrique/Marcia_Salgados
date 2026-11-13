ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS status VARCHAR(10) NOT NULL DEFAULT 'ATIVO'
  CHECK (status IN ('ATIVO', 'CANCELADO'));
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS versao INTEGER NOT NULL DEFAULT 1;
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS atualizado_em TIMESTAMPTZ;
ALTER TABLE pedido_itens ADD COLUMN IF NOT EXISTS ativo BOOLEAN NOT NULL DEFAULT TRUE;
-- Um item passa a ter várias movimentações: criação, deltas e devolução.
DROP INDEX IF EXISTS idx_movimentacoes_pedido_item;
CREATE INDEX IF NOT EXISTS idx_movimentacoes_item_historico ON movimentacoes(pedido_item_id);
CREATE TABLE IF NOT EXISTS pedido_eventos (
  id BIGSERIAL PRIMARY KEY,
  pedido_id INTEGER NOT NULL REFERENCES pedidos(id) ON DELETE RESTRICT,
  usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
  acao VARCHAR(15) NOT NULL CHECK (acao IN ('CRIACAO','EDICAO','CANCELAMENTO')),
  antes JSONB,
  depois JSONB NOT NULL,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
