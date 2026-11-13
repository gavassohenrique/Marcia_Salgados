CREATE TABLE IF NOT EXISTS recuperacao_senha (
  token_hash CHAR(64) PRIMARY KEY,
  usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  versao_sessao INTEGER NOT NULL,
  expira_em TIMESTAMPTZ NOT NULL,
  usado_em TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_recuperacao_usuario ON recuperacao_senha(usuario_id);
CREATE TABLE IF NOT EXISTS recuperacao_limites (
  chave CHAR(64) PRIMARY KEY,
  inicio TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  tentativas INTEGER NOT NULL DEFAULT 1
);
