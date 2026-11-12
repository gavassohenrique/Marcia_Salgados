-- Executado apenas na criação inicial do volume PostgreSQL.
-- Volumes existentes mantêm seus dados; o backend cria tabelas ausentes.
CREATE TABLE IF NOT EXISTS produtos (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    preco NUMERIC(10,2) NOT NULL CHECK (preco > 0),
    estoque INTEGER NOT NULL DEFAULT 0 CHECK (estoque >= 0),
    estoque_minimo INTEGER NOT NULL DEFAULT 0 CHECK (estoque_minimo >= 0),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pedidos (
    id SERIAL PRIMARY KEY,
    cliente VARCHAR(150) NOT NULL,
    referencia VARCHAR(80),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS movimentacoes (
    id SERIAL PRIMARY KEY,
    produto_id INTEGER NOT NULL REFERENCES produtos(id) ON DELETE RESTRICT,
    tipo VARCHAR(7) NOT NULL CHECK (tipo IN ('ENTRADA', 'SAIDA')),
    quantidade INTEGER NOT NULL CHECK (quantidade > 0),
    estoque_anterior INTEGER NOT NULL,
    estoque_posterior INTEGER NOT NULL,
    motivo VARCHAR(200),
    pedido_id INTEGER,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_movimentacoes_criado_em
    ON movimentacoes (criado_em DESC, id DESC);

-- Autenticação persistente e auditoria de movimentações (compatível com volumes antigos).
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(254) NOT NULL,
    senha_hash TEXT NOT NULL,
    perfil VARCHAR(11) NOT NULL CHECK (perfil IN ('ADMIN', 'FUNCIONARIO')),
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    versao_sessao INTEGER NOT NULL DEFAULT 1,
    tentativas_falhas INTEGER NOT NULL DEFAULT 0,
    bloqueado_ate TIMESTAMPTZ,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_email_ci ON usuarios (LOWER(email));
ALTER TABLE movimentacoes ADD COLUMN IF NOT EXISTS usuario_id INTEGER;
ALTER TABLE movimentacoes ADD COLUMN IF NOT EXISTS pedido_id INTEGER;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_movimentacoes_usuario'
      AND conrelid = 'movimentacoes'::regclass
  ) THEN
    ALTER TABLE movimentacoes ADD CONSTRAINT fk_movimentacoes_usuario
      FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL;
  END IF;
END $$;

INSERT INTO produtos (nome, preco, estoque, estoque_minimo)
SELECT 'Coxinha', 5.00, 20, 5
WHERE NOT EXISTS (SELECT 1 FROM produtos WHERE nome = 'Coxinha');

INSERT INTO produtos (nome, preco, estoque, estoque_minimo)
SELECT 'Pastel', 6.00, 15, 5
WHERE NOT EXISTS (SELECT 1 FROM produtos WHERE nome = 'Pastel');
