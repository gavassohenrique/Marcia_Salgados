-- Registros anteriores continuam pedidos, sem repetir a baixa já efetuada.
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS tipo VARCHAR(9) NOT NULL DEFAULT 'PEDIDO'
  CHECK (tipo IN ('ORCAMENTO', 'PEDIDO'));
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS confirmado_em TIMESTAMPTZ;
ALTER TABLE pedido_eventos DROP CONSTRAINT IF EXISTS pedido_eventos_acao_check;
ALTER TABLE pedido_eventos ADD CONSTRAINT pedido_eventos_acao_check
  CHECK (acao IN ('CRIACAO', 'EDICAO', 'CANCELAMENTO', 'CONFIRMACAO'));
