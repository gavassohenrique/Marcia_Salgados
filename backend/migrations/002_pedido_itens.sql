ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS usuario_id INTEGER REFERENCES usuarios(id) ON DELETE RESTRICT;
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS estoque_processado BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE IF NOT EXISTS pedido_itens (
  id SERIAL PRIMARY KEY,
  pedido_id INTEGER NOT NULL REFERENCES pedidos(id) ON DELETE RESTRICT,
  produto_id INTEGER NOT NULL REFERENCES produtos(id) ON DELETE RESTRICT,
  produto_nome VARCHAR(100) NOT NULL,
  preco_unitario NUMERIC(10,2) NOT NULL CHECK (preco_unitario > 0),
  quantidade INTEGER NOT NULL CHECK (quantidade > 0),
  UNIQUE (pedido_id, produto_id)
);
ALTER TABLE movimentacoes ADD COLUMN IF NOT EXISTS pedido_item_id INTEGER
  REFERENCES pedido_itens(id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_movimentacoes_pedido_item
  ON movimentacoes(pedido_item_id) WHERE pedido_item_id IS NOT NULL;
