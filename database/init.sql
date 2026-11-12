CREATE TABLE IF NOT EXISTS produtos (
  id SERIAL PRIMARY KEY,
  nome VARCHAR(100) NOT NULL,
  preco NUMERIC(10,2) NOT NULL CHECK (preco > 0),
  estoque INTEGER NOT NULL DEFAULT 0 CHECK (estoque >= 0),
  estoque_minimo INTEGER NOT NULL DEFAULT 0 CHECK (estoque_minimo >= 0),
  criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS movimentacoes (
  id SERIAL PRIMARY KEY,
  produto_id INTEGER NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
  tipo VARCHAR(7) NOT NULL CHECK (tipo IN ('ENTRADA', 'SAIDA')),
  quantidade INTEGER NOT NULL CHECK (quantidade > 0),
  estoque_anterior INTEGER NOT NULL,
  estoque_posterior INTEGER NOT NULL,
  motivo VARCHAR(200),
  pedido_id INTEGER,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO produtos (nome, preco, estoque, estoque_minimo)
SELECT 'Coxinha', 5.00, 20, 5
WHERE NOT EXISTS (SELECT 1 FROM produtos WHERE nome = 'Coxinha');

INSERT INTO produtos (nome, preco, estoque, estoque_minimo)
SELECT 'Pastel', 6.00, 15, 5
WHERE NOT EXISTS (SELECT 1 FROM produtos WHERE nome = 'Pastel');
