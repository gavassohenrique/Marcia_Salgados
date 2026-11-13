"""API de estoque e rastreabilidade da Márcia Salgados."""
import hmac
import re
import os
import secrets
import time
import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path

import psycopg2
from flask import Flask, g, jsonify, request, session, Response
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from argon2 import PasswordHasher, exceptions as argon2_errors
from argon2.low_level import Type

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("FLASK_SECRET_KEY"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=16 * 1024,
)
PASSWORD_HASHER = PasswordHasher(time_cost=2, memory_cost=19456,
                                 parallelism=1, hash_len=32, salt_len=16,
                                 type=Type.ID)
PERFIS = ("ADMIN", "FUNCIONARIO")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MAX_INT = 2_147_483_647
MAX_PRECO = Decimal("99999999.99")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "postgres"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("POSTGRES_DB", os.getenv("DB_NAME", "appdb")),
    "user": os.getenv("POSTGRES_USER", os.getenv("DB_USER", "user")),
    "password": os.getenv("POSTGRES_PASSWORD", os.getenv("DB_PASSWORD", "")),
}
connection_pool = None


def get_pool():
    global connection_pool
    if connection_pool is None:
        connection_pool = pool.ThreadedConnectionPool(1, 10, **DB_CONFIG)
    return connection_pool


def get_connection():
    return get_pool().getconn()


def json_error(message, status=400):
    return jsonify({"erro": message}), status


def inteiro(valor, *, minimo=0):
    """Converte somente inteiros válidos; rejeita booleanos, frações e overflow SQL."""
    if isinstance(valor, bool) or valor is None:
        raise ValueError("Valor inteiro inválido")
    if isinstance(valor, int):
        resultado = valor
    elif isinstance(valor, str) and valor.strip().isdigit():
        resultado = int(valor.strip())
    else:
        raise ValueError("Valor inteiro inválido")
    if not minimo <= resultado <= MAX_INT:
        raise ValueError("Valor inteiro fora do intervalo")
    return resultado


def preco_decimal(valor):
    if isinstance(valor, bool) or valor is None:
        raise ValueError("Preço inválido")
    entrada = str(valor).strip().replace(",", ".")
    try:
        decimal = Decimal(entrada)
    except (InvalidOperation, ValueError):
        raise ValueError("Preço inválido") from None
    if not decimal.is_finite() or not Decimal("0.01") <= decimal <= MAX_PRECO:
        raise ValueError("Preço fora do intervalo")
    if decimal != decimal.quantize(Decimal("0.01")):
        raise ValueError("O preço aceita até duas casas decimais")
    return decimal


def validar_produto(data, *, edicao=False):
    if not isinstance(data, dict):
        return "Os dados enviados são inválidos."
    nome = data.get("nome")
    if not isinstance(nome, str) or not nome.strip():
        return "Informe o nome do produto."
    if len(nome.strip()) > 100:
        return "O nome do produto deve ter no máximo 100 caracteres."
    try:
        preco_decimal(data.get("preco"))
    except ValueError:
        return "Informe um preço válido entre R$ 0,01 e R$ 99.999.999,99, com até duas casas decimais."
    try:
        inteiro(data.get("estoque_minimo", 0))
        if not edicao:
            inteiro(data.get("estoque", 0))
    except ValueError:
        return "Estoque e estoque mínimo devem ser números inteiros não negativos."
    return None


def preparar_banco():
    """Migração idempotente: mantém produtos, pedidos e movimentações existentes."""
    sql = """
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
        ALTER TABLE produtos ADD COLUMN IF NOT EXISTS estoque_minimo INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE movimentacoes ADD COLUMN IF NOT EXISTS pedido_id INTEGER;
        CREATE INDEX IF NOT EXISTS idx_movimentacoes_criado_em
          ON movimentacoes (criado_em DESC, id DESC);
        CREATE TABLE IF NOT EXISTS usuarios (
          id SERIAL PRIMARY KEY,
          nome VARCHAR(100) NOT NULL,
          email VARCHAR(254) NOT NULL,
          senha_hash TEXT NOT NULL,
          perfil VARCHAR(11) NOT NULL CHECK (perfil IN ('ADMIN','FUNCIONARIO')),
          ativo BOOLEAN NOT NULL DEFAULT TRUE,
          versao_sessao INTEGER NOT NULL DEFAULT 1,
          tentativas_falhas INTEGER NOT NULL DEFAULT 0,
          bloqueado_ate TIMESTAMPTZ,
          criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_email_ci ON usuarios (LOWER(email));
        ALTER TABLE movimentacoes ADD COLUMN IF NOT EXISTS usuario_id INTEGER;
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'fk_movimentacoes_usuario'
              AND conrelid = 'movimentacoes'::regclass
          ) THEN
            ALTER TABLE movimentacoes ADD CONSTRAINT fk_movimentacoes_usuario
              FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL;
          END IF;
        END $$;
    """
    for tentativa in range(10):
        try:
            with psycopg2.connect(**DB_CONFIG) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute((Path(__file__).parent / "migrations" / "002_pedido_itens.sql").read_text(encoding="utf-8"))
                    cur.execute((Path(__file__).parent / "migrations" / "003_pedidos_edicao.sql").read_text(encoding="utf-8"))
                    cur.execute((Path(__file__).parent / "migrations" / "004_orcamentos_confirmacao.sql").read_text(encoding="utf-8"))
            return
        except psycopg2.Error:
            if tentativa == 9:
                raise
            time.sleep(2)


def validar_configuracao():
    chave = app.config.get("SECRET_KEY")
    senha_db = DB_CONFIG["password"]
    if not isinstance(chave, str) or len(chave) < 32 or chave.startswith("SUBSTITUA_"):
        raise RuntimeError("Defina uma FLASK_SECRET_KEY aleatória com pelo menos 32 caracteres no .env.")
    if not senha_db or senha_db.startswith("SUBSTITUA_"):
        raise RuntimeError("Defina POSTGRES_PASSWORD com uma senha própria no .env.")


def validar_senha(senha):
    """Exige tamanho mínimo, letras maiúsculas/minúsculas e símbolo especial.

    Números são permitidos, mas não obrigatórios; espaços não contam como símbolo.
    A política vale para criação e troca, sem bloquear login de senhas já existentes.
    """
    if not isinstance(senha, str) or not 8 <= len(senha) <= 128:
        return "A senha deve ter de 8 a 128 caracteres."
    if not any(caractere.isupper() for caractere in senha):
        return "A senha precisa ter pelo menos uma letra maiúscula."
    if not any(caractere.islower() for caractere in senha):
        return "A senha precisa ter pelo menos uma letra minúscula."
    if not any(not caractere.isalnum() and not caractere.isspace() for caractere in senha):
        return "A senha precisa ter pelo menos um caractere especial (ex.: !, @, # ou _)."
    return None


def validar_usuario(data):
    if not isinstance(data, dict):
        return "Dados inválidos."
    nome, email, perfil = data.get("nome"), data.get("email"), data.get("perfil")
    if not isinstance(nome, str) or not 1 <= len(nome.strip()) <= 100:
        return "Informe um nome de até 100 caracteres."
    if not isinstance(email, str) or len(email.strip()) > 254 or not EMAIL_PATTERN.fullmatch(email.strip()):
        return "Informe um e-mail válido."
    if perfil not in PERFIS:
        return "Perfil inválido."
    return validar_senha(data.get("senha"))


def hash_senha(senha):
    return PASSWORD_HASHER.hash(senha)


def conferir_senha(hash_guardado, senha):
    try:
        return PASSWORD_HASHER.verify(hash_guardado, senha)
    except (argon2_errors.VerifyMismatchError, argon2_errors.VerificationError,
            argon2_errors.InvalidHashError, TypeError, ValueError):
        return False


def consulta_usuario(id_usuario):
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""SELECT id, nome, email, perfil, ativo, versao_sessao
                           FROM usuarios WHERE id=%s""", (id_usuario,))
            return cur.fetchone()
    finally:
        if conn:
            get_pool().putconn(conn)


def usuario_da_sessao():
    identificador = session.get("usuario_id")
    versao = session.get("versao_sessao")
    if type(identificador) is not int or type(versao) is not int:
        return None
    usuario = consulta_usuario(identificador)
    if not usuario or not usuario["ativo"] or usuario["versao_sessao"] != versao:
        return None
    return usuario


def usuario_publico(usuario):
    return {campo: usuario[campo] for campo in ("id", "nome", "email", "perfil")}


def exige_admin(func):
    @wraps(func)
    def protegido(*args, **kwargs):
        if g.usuario["perfil"] != "ADMIN":
            return json_error("Apenas administradores podem realizar essa operação.", 403)
        return func(*args, **kwargs)
    return protegido


@app.before_request
def proteger_api():
    if request.path in ("/", "/health", "/auth/status", "/auth/login"):
        return None
    if not app.config.get("SECRET_KEY"):
        return json_error("Chave de sessão não configurada no servidor.", 503)
    try:
        usuario = usuario_da_sessao()
    except psycopg2.Error:
        return json_error("Não foi possível verificar sua sessão no banco.", 503)
    if usuario is None:
        session.clear()
        return json_error("Faça login para continuar.", 401)
    g.usuario = usuario
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        enviado = request.headers.get("X-CSRF-Token", "")
        esperado = session.get("csrf", "")
        if not esperado or not hmac.compare_digest(enviado, esperado):
            return json_error("Sessão inválida. Atualize a página e entre novamente.", 403)
    return None


@app.get("/")
def home():
    return jsonify({"mensagem": "API Marcia Salgados funcionando", "linguagem": "Python/Flask"})


@app.get("/auth/status")
def auth_status():
    if not app.config.get("SECRET_KEY"):
        return jsonify({"configurado": False, "autenticado": False, "primeiro_acesso": False})
    try:
        usuario = usuario_da_sessao()
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT EXISTS (SELECT 1 FROM usuarios)")
                existem_usuarios = cur.fetchone()[0]
        finally:
            get_pool().putconn(conn)
    except psycopg2.Error:
        return json_error("Banco de dados indisponível.", 503)
    return jsonify({"configurado": True, "autenticado": bool(usuario),
                    "primeiro_acesso": not existem_usuarios,
                    "usuario": usuario_publico(usuario) if usuario else None,
                    "csrf": session.get("csrf") if usuario else None})


@app.post("/auth/login")
def auth_login():
    if not app.config.get("SECRET_KEY"):
        return json_error("Configure FLASK_SECRET_KEY no servidor.", 503)
    data = request.get_json(silent=True)
    email = data.get("email", "") if isinstance(data, dict) else ""
    senha = data.get("senha", "") if isinstance(data, dict) else ""
    if not isinstance(email, str) or not isinstance(senha, str) or len(email) > 254 or len(senha) > 128:
        return json_error("E-mail ou senha incorretos.", 401)
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""SELECT id, nome, email, senha_hash, perfil, ativo,
                                  versao_sessao, tentativas_falhas, bloqueado_ate,
                                  (bloqueado_ate IS NOT NULL AND bloqueado_ate > NOW()) AS bloqueado
                           FROM usuarios WHERE LOWER(email)=LOWER(%s) FOR UPDATE""", (email.strip(),))
            usuario = cur.fetchone()
            # Mensagem uniforme; a limitação de tentativas é vinculada à conta.
            if not usuario or not usuario["ativo"] or usuario["bloqueado"]:
                conn.rollback()
                return json_error("E-mail ou senha incorretos ou acesso temporariamente bloqueado.", 401)
            if not conferir_senha(usuario["senha_hash"], senha):
                cur.execute("""UPDATE usuarios SET tentativas_falhas=tentativas_falhas+1,
                           bloqueado_ate=CASE WHEN tentativas_falhas+1 >= 5
                             THEN NOW() + INTERVAL '15 minutes' ELSE bloqueado_ate END
                           WHERE id=%s""", (usuario["id"],))
                conn.commit()
                return json_error("E-mail ou senha incorretos ou acesso temporariamente bloqueado.", 401)
            cur.execute("""UPDATE usuarios SET tentativas_falhas=0, bloqueado_ate=NULL
                           WHERE id=%s""", (usuario["id"],))
        conn.commit()
    except psycopg2.Error:
        if conn:
            conn.rollback()
        return json_error("Não foi possível autenticar no momento.", 503)
    finally:
        if conn:
            get_pool().putconn(conn)
    session.clear()
    session.permanent = True
    session["usuario_id"] = usuario["id"]
    session["versao_sessao"] = usuario["versao_sessao"]
    session["csrf"] = secrets.token_urlsafe(32)
    return jsonify({"mensagem": "Sessão iniciada.", "csrf": session["csrf"],
                    "usuario": usuario_publico(usuario)})


@app.post("/auth/logout")
def auth_logout():
    session.clear()
    return jsonify({"mensagem": "Sessão encerrada."})


@app.post("/auth/alterar-senha")
def alterar_senha():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return json_error("Dados inválidos.")
    erro = validar_senha(data.get("nova_senha"))
    if erro:
        return json_error(erro)
    senha_atual = data.get("senha_atual")
    if not isinstance(senha_atual, str):
        return json_error("Senha atual incorreta.", 400)
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT senha_hash, versao_sessao FROM usuarios WHERE id=%s FOR UPDATE", (g.usuario["id"],))
            registrado = cur.fetchone()
            if not registrado or not conferir_senha(registrado["senha_hash"], senha_atual):
                conn.rollback()
                return json_error("Senha atual incorreta.", 400)
            if conferir_senha(registrado["senha_hash"], data["nova_senha"]):
                conn.rollback()
                return json_error("A nova senha deve ser diferente da anterior.")
            versao = registrado["versao_sessao"] + 1
            cur.execute("""UPDATE usuarios SET senha_hash=%s, versao_sessao=%s,
                           tentativas_falhas=0, bloqueado_ate=NULL, atualizado_em=NOW()
                           WHERE id=%s""", (hash_senha(data["nova_senha"]), versao, g.usuario["id"]))
        conn.commit()
        # Mantém a sessão atual; invalida todas as outras.
        session["versao_sessao"] = versao
        return jsonify({"mensagem": "Senha alterada. As outras sessões foram encerradas."})
    except psycopg2.Error:
        if conn:
            conn.rollback()
        return json_error("Não foi possível alterar a senha.", 503)
    finally:
        if conn:
            get_pool().putconn(conn)


@app.get("/usuarios")
@exige_admin
def listar_usuarios():
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""SELECT id, nome, email, perfil, ativo, criado_em
                           FROM usuarios ORDER BY id ASC""")
            return jsonify(cur.fetchall())
    except psycopg2.Error:
        return json_error("Não foi possível consultar os usuários.", 503)
    finally:
        if conn:
            get_pool().putconn(conn)


@app.post("/usuarios")
@exige_admin
def criar_usuario():
    data = request.get_json(silent=True)
    erro = validar_usuario(data)
    if erro:
        return json_error(erro)
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""INSERT INTO usuarios (nome, email, senha_hash, perfil)
                           VALUES (%s,%s,%s,%s)
                           RETURNING id, nome, email, perfil, ativo, criado_em""",
                        (data["nome"].strip(), data["email"].strip().lower(),
                         hash_senha(data["senha"]), data["perfil"]))
            usuario = cur.fetchone()
        conn.commit()
        return jsonify({"mensagem": "Usuário cadastrado.", "usuario": usuario}), 201
    except psycopg2.IntegrityError:
        if conn:
            conn.rollback()
        return json_error("Este e-mail já está cadastrado.", 409)
    except psycopg2.Error:
        if conn:
            conn.rollback()
        return json_error("Não foi possível cadastrar o usuário.", 503)
    finally:
        if conn:
            get_pool().putconn(conn)


@app.patch("/usuarios/<int:usuario_id>")
@exige_admin
def editar_usuario(usuario_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data or set(data) - {"perfil", "ativo"}:
        return json_error("Informe perfil ou status ativo válido.")
    perfil = data.get("perfil")
    ativo = data.get("ativo")
    if perfil is not None and perfil not in PERFIS:
        return json_error("Perfil inválido.")
    if ativo is not None and type(ativo) is not bool:
        return json_error("Status ativo deve ser verdadeiro ou falso.")
    if usuario_id == g.usuario["id"] and (perfil == "FUNCIONARIO" or ativo is False):
        return json_error("Você não pode desativar ou retirar seu próprio acesso administrativo.", 409)
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""UPDATE usuarios SET perfil=COALESCE(%s,perfil),
                           ativo=COALESCE(%s,ativo), versao_sessao=versao_sessao+1,
                           atualizado_em=NOW() WHERE id=%s
                           RETURNING id, nome, email, perfil, ativo""", (perfil, ativo, usuario_id))
            usuario = cur.fetchone()
        if not usuario:
            conn.rollback()
            return json_error("Usuário não encontrado.", 404)
        conn.commit()
        return jsonify({"usuario": usuario})
    except psycopg2.Error:
        if conn:
            conn.rollback()
        return json_error("Não foi possível atualizar o usuário.", 503)
    finally:
        if conn:
            get_pool().putconn(conn)


@app.post("/usuarios/<int:usuario_id>/redefinir-senha")
@exige_admin
def redefinir_senha(usuario_id):
    data = request.get_json(silent=True)
    erro = validar_senha(data.get("nova_senha") if isinstance(data, dict) else None)
    if erro:
        return json_error(erro)
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""UPDATE usuarios SET senha_hash=%s, versao_sessao=versao_sessao+1,
                           tentativas_falhas=0, bloqueado_ate=NULL, atualizado_em=NOW()
                           WHERE id=%s RETURNING id""", (hash_senha(data["nova_senha"]), usuario_id))
            usuario = cur.fetchone()
        if not usuario:
            conn.rollback()
            return json_error("Usuário não encontrado.", 404)
        conn.commit()
        # Inclusive a própria sessão é invalidada se redefinir a própria senha.
        if usuario_id == g.usuario["id"]:
            session.clear()
        return jsonify({"mensagem": "Senha redefinida. Sessões anteriores foram invalidadas."})
    except psycopg2.Error:
        if conn:
            conn.rollback()
        return json_error("Não foi possível redefinir a senha.", 503)
    finally:
        if conn:
            get_pool().putconn(conn)


@app.get("/health")
def health():
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return jsonify({"status": "ok", "banco": "conectado"})
    except Exception:
        return jsonify({"status": "erro", "banco": "indisponível"}), 503
    finally:
        if conn:
            get_pool().putconn(conn)


@app.get("/produtos")
def listar_produtos():
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, nome, preco, estoque, estoque_minimo,
                       (estoque <= estoque_minimo) AS estoque_baixo
                FROM produtos ORDER BY id DESC
            """)
            return jsonify(cur.fetchall())
    except psycopg2.Error:
        return json_error("Não foi possível acessar o banco de dados.", 503)
    finally:
        if conn:
            get_pool().putconn(conn)


@app.post("/produtos")
@exige_admin
def cadastrar_produto():
    data = request.get_json(silent=True)
    erro = validar_produto(data)
    if erro:
        return json_error(erro)
    valores = (data["nome"].strip(), preco_decimal(data["preco"]),
               inteiro(data.get("estoque", 0)), inteiro(data.get("estoque_minimo", 0)))
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""INSERT INTO produtos (nome, preco, estoque, estoque_minimo)
                        VALUES (%s,%s,%s,%s)
                        RETURNING id, nome, preco, estoque, estoque_minimo""", valores)
            produto = cur.fetchone()
        conn.commit()
        return jsonify({"mensagem": "Produto cadastrado com sucesso.", "produto": produto}), 201
    except psycopg2.Error:
        if conn:
            conn.rollback()
        return json_error("Não foi possível cadastrar o produto.", 503)
    finally:
        if conn:
            get_pool().putconn(conn)


@app.put("/produtos/<int:produto_id>")
@exige_admin
def editar_produto(produto_id):
    data = request.get_json(silent=True)
    erro = validar_produto(data, edicao=True)
    if erro:
        return json_error(erro)
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""UPDATE produtos SET nome=%s, preco=%s, estoque_minimo=%s
                           WHERE id=%s RETURNING id, nome, preco, estoque, estoque_minimo""",
                        (data["nome"].strip(), preco_decimal(data["preco"]),
                         inteiro(data.get("estoque_minimo", 0)), produto_id))
            produto = cur.fetchone()
        if not produto:
            conn.rollback()
            return json_error("Produto não encontrado.", 404)
        conn.commit()
        return jsonify({"mensagem": "Produto atualizado com sucesso.", "produto": produto})
    except psycopg2.Error:
        if conn:
            conn.rollback()
        return json_error("Não foi possível atualizar o produto.", 503)
    finally:
        if conn:
            get_pool().putconn(conn)


@app.get("/pedidos")
def listar_pedidos():
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""SELECT p.id, p.cliente, p.referencia, p.criado_em,
                                  p.usuario_id, p.estoque_processado, p.status, p.tipo, p.confirmado_em, p.versao, u.nome AS usuario_nome,
                                  COALESCE((SELECT json_agg(json_build_object(
                                    'id', i.id, 'produto_id', i.produto_id,
                                    'produto_nome', i.produto_nome, 'quantidade', i.quantidade,
                                    'preco_unitario', i.preco_unitario) ORDER BY i.id)
                                    FROM pedido_itens i WHERE i.pedido_id=p.id AND i.ativo), '[]'::json) AS itens
                           FROM pedidos p LEFT JOIN usuarios u ON u.id=p.usuario_id
                           ORDER BY p.id DESC LIMIT 100""")
            return jsonify(cur.fetchall())
    except psycopg2.Error:
        return json_error("Não foi possível consultar os pedidos.", 503)
    finally:
        if conn:
            get_pool().putconn(conn)


@app.post("/pedidos")
def cadastrar_pedido():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("cliente"), str):
        return json_error("Informe o cliente do pedido.")
    cliente = data["cliente"].strip()
    referencia = data.get("referencia", "")
    if not cliente or len(cliente) > 150 or not isinstance(referencia, str) or len(referencia) > 80:
        return json_error("Confira o nome do cliente (até 150 caracteres) e a referência (até 80).")
    itens = data.get("itens")
    if not isinstance(itens, list) or not 1 <= len(itens) <= 100:
        return json_error("Informe de 1 a 100 itens no pedido.")
    quantidades = {}
    try:
        for item in itens:
            if not isinstance(item, dict):
                raise ValueError()
            produto_id = inteiro(item.get("produto_id"), minimo=1)
            quantidade = inteiro(item.get("quantidade"), minimo=1)
            if produto_id in quantidades:
                return json_error("Selecione cada produto apenas uma vez e ajuste sua quantidade.")
            quantidades[produto_id] = quantidade
    except ValueError:
        return json_error("Produtos e quantidades devem ser inteiros positivos dentro do limite permitido.")
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Ordem fixa de bloqueio evita deadlock entre pedidos concorrentes.
            cur.execute("""SELECT id, nome, preco, estoque FROM produtos
                           WHERE id = ANY(%s) ORDER BY id FOR UPDATE""", (sorted(quantidades),))
            produtos = cur.fetchall()
            if len(produtos) != len(quantidades):
                conn.rollback()
                return json_error("Um dos produtos selecionados não existe.", 404)
            cur.execute("""INSERT INTO pedidos (cliente, referencia, usuario_id, estoque_processado, tipo)
                           VALUES (%s, %s, %s, FALSE, 'ORCAMENTO')
                           RETURNING id, cliente, referencia, criado_em, usuario_id, estoque_processado, status, tipo, versao""",
                        (cliente, referencia.strip() or None, g.usuario["id"]))
            pedido = cur.fetchone()
            pedido["itens"] = []
            for produto in produtos:
                quantidade = quantidades[produto["id"]]
                cur.execute("""INSERT INTO pedido_itens
                               (pedido_id, produto_id, produto_nome, preco_unitario, quantidade)
                               VALUES (%s,%s,%s,%s,%s) RETURNING id""",
                            (pedido["id"], produto["id"], produto["nome"], produto["preco"], quantidade))
                item_id = cur.fetchone()["id"]
                pedido["itens"].append({"id": item_id, "produto_id": produto["id"],
                                        "produto_nome": produto["nome"], "quantidade": quantidade,
                                        "preco_unitario": produto["preco"]})
            registrar_evento(cur, pedido["id"], "CRIACAO", None, pedido)
        conn.commit()
        return jsonify({"mensagem": "Orçamento salvo, sem movimentar ou reservar estoque. Confirme para gerar o pedido.", "pedido": pedido}), 201
    except psycopg2.Error:
        if conn:
            conn.rollback()
        return json_error("Não foi possível cadastrar o pedido.", 503)
    finally:
        if conn:
            get_pool().putconn(conn)


def registrar_evento(cur, pedido_id, acao, antes, depois):
    cur.execute("""INSERT INTO pedido_eventos(pedido_id,usuario_id,acao,antes,depois)
                   VALUES (%s,%s,%s,%s::jsonb,%s::jsonb)""",
                (pedido_id, g.usuario["id"], acao,
                 json.dumps(antes, default=str) if antes is not None else None,
                 json.dumps(depois, default=str)))


def ler_pedido(cur, pedido_id, bloqueio="FOR UPDATE"):
    # Apenas constantes internas são usadas no sufixo SQL.
    cur.execute("SELECT * FROM pedidos WHERE id=%s " + bloqueio, (pedido_id,))
    pedido = cur.fetchone()
    if pedido:
        cur.execute("SELECT * FROM pedido_itens WHERE pedido_id=%s AND ativo ORDER BY id", (pedido_id,))
        pedido["itens"] = cur.fetchall()
    return pedido


def validar_edicao(data):
    if not isinstance(data, dict):
        raise ValueError("Dados inválidos.")
    versao = inteiro(data.get("versao"), minimo=1)
    cliente, referencia = data.get("cliente"), data.get("referencia", "")
    if not isinstance(cliente, str) or not 1 <= len(cliente.strip()) <= 150:
        raise ValueError("Informe um cliente de até 150 caracteres.")
    if not isinstance(referencia, str) or len(referencia) > 80:
        raise ValueError("Informe uma referência de até 80 caracteres.")
    itens = data.get("itens")
    if not isinstance(itens, list) or not 1 <= len(itens) <= 100:
        raise ValueError("Informe de 1 a 100 itens.")
    quantidades = {}
    for item in itens:
        if not isinstance(item, dict):
            raise ValueError("Item inválido.")
        pid = inteiro(item.get("produto_id"), minimo=1)
        if pid in quantidades:
            raise ValueError("Selecione cada produto apenas uma vez.")
        quantidades[pid] = inteiro(item.get("quantidade"), minimo=1)
    return versao, cliente.strip(), referencia.strip() or None, quantidades


@app.put("/pedidos/<int:pedido_id>")
@app.delete("/pedidos/<int:pedido_id>")
@app.post("/pedidos/<int:pedido_id>/confirmar")
def alterar_pedido(pedido_id):
    cancelar = request.method == "DELETE"
    confirmar = request.method == "POST"
    data = request.get_json(silent=True)
    try:
        if cancelar or confirmar:
            versao = inteiro(data.get("versao") if isinstance(data, dict) else None, minimo=1)
        else:
            versao, cliente, referencia, quantidades = validar_edicao(data)
    except ValueError as exc:
        return json_error(str(exc))
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            antes = ler_pedido(cur, pedido_id)
            if not antes:
                conn.rollback()
                return json_error("Pedido não encontrado.", 404)
            if antes["status"] == "CANCELADO" or antes["versao"] != versao:
                conn.rollback()
                return json_error("Pedido cancelado ou alterado por outra pessoa. Atualize a lista.", 409)
            orcamento = antes["tipo"] == "ORCAMENTO"
            if confirmar and (not orcamento or antes["estoque_processado"]):
                conn.rollback()
                return json_error("Este registro já é um pedido. A confirmação não pode ser repetida.", 409)
            if not antes["itens"] or (not orcamento and not antes["estoque_processado"]):
                conn.rollback()
                return json_error("Pedido antigo sem itens detalhados. Consulte o histórico e reconcilie o estoque antes de ajustar.", 409)
            if cancelar:
                quantidades = {}
            elif confirmar:
                quantidades = {i["produto_id"]: i["quantidade"] for i in antes["itens"]}
            antigos = {i["produto_id"]: i for i in antes["itens"]}
            ids = sorted(set(antigos) | set(quantidades))
            # Sempre pedido primeiro, depois produtos em ID crescente; mesma ordem da criação.
            cur.execute("SELECT id,nome,preco,estoque FROM produtos WHERE id=ANY(%s) ORDER BY id FOR UPDATE", (ids,))
            produtos = cur.fetchall()
            if len(produtos) != len(ids):
                conn.rollback()
                return json_error("Produto não encontrado.", 404)
            for produto in produtos:
                pid = produto["id"]
                if confirmar:
                    delta = quantidades[pid]
                elif orcamento:
                    delta = 0
                else:
                    delta = quantidades.get(pid, 0) - antigos.get(pid, {}).get("quantidade", 0)
                saldo = produto["estoque"] - delta
                if not 0 <= saldo <= MAX_INT:
                    conn.rollback()
                    return json_error(f"Saldo inválido para {produto['nome']}. Disponível: {produto['estoque']}.", 409)
                item = antigos.get(pid)
                if pid in quantidades:
                    # Reativação conserva preço/nome já registrados; produto novo usa catálogo atual.
                    cur.execute("""INSERT INTO pedido_itens(pedido_id,produto_id,produto_nome,preco_unitario,quantidade)
                                   VALUES (%s,%s,%s,%s,%s)
                                   ON CONFLICT (pedido_id,produto_id) DO UPDATE
                                   SET quantidade=EXCLUDED.quantidade, ativo=TRUE RETURNING id""",
                                (pedido_id, pid, produto["nome"], produto["preco"], quantidades[pid]))
                    item_id = cur.fetchone()["id"]
                else:
                    item_id = item["id"]
                    cur.execute("UPDATE pedido_itens SET ativo=FALSE WHERE id=%s", (item_id,))
                if delta:
                    cur.execute("UPDATE produtos SET estoque=%s WHERE id=%s", (saldo, pid))
                    cur.execute("""INSERT INTO movimentacoes(produto_id,tipo,quantidade,estoque_anterior,
                                   estoque_posterior,motivo,pedido_id,usuario_id,pedido_item_id)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                                (pid, "SAIDA" if delta > 0 else "ENTRADA", abs(delta), produto["estoque"], saldo,
                                 "Confirmação de orçamento" if confirmar else ("Cancelamento de pedido" if cancelar else "Edição de pedido"),
                                 pedido_id, g.usuario["id"], item_id))
            if cancelar:
                # Itens permanecem visíveis no documento cancelado e no histórico.
                cur.execute("UPDATE pedido_itens SET ativo=TRUE WHERE id=ANY(%s)", ([i["id"] for i in antes["itens"]],))
                cur.execute("UPDATE pedidos SET status='CANCELADO',versao=versao+1,atualizado_em=NOW() WHERE id=%s", (pedido_id,))
            elif confirmar:
                cur.execute("""UPDATE pedidos SET tipo='PEDIDO',estoque_processado=TRUE,
                               confirmado_em=NOW(),versao=versao+1,atualizado_em=NOW() WHERE id=%s""", (pedido_id,))
            else:
                cur.execute("UPDATE pedidos SET cliente=%s,referencia=%s,versao=versao+1,atualizado_em=NOW() WHERE id=%s",
                            (cliente, referencia, pedido_id))
            depois = ler_pedido(cur, pedido_id)
            registrar_evento(cur, pedido_id, "CONFIRMACAO" if confirmar else ("CANCELAMENTO" if cancelar else "EDICAO"), antes, depois)
        conn.commit()
        if confirmar:
            mensagem = "Pedido confirmado; saída de estoque registrada uma única vez."
        elif cancelar:
            mensagem = "Orçamento cancelado, sem movimentar estoque." if orcamento else "Pedido cancelado; estoque devolvido."
        else:
            mensagem = "Orçamento atualizado, sem movimentar estoque." if orcamento else "Pedido atualizado; diferenças de estoque registradas."
        return jsonify({"mensagem": mensagem, "pedido": depois})
    except psycopg2.Error:
        if conn:
            conn.rollback()
        return json_error("Não foi possível atualizar o pedido. Nenhuma alteração foi salva.", 503)
    finally:
        if conn:
            get_pool().putconn(conn)


@app.get("/pedidos/<int:pedido_id>")
@app.get("/pedidos/<int:pedido_id>/documento.<formato>")
def consultar_pedido(pedido_id, formato=None):
    if formato not in (None, "pdf", "txt"):
        return json_error("Formato inválido.", 400)
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            pedido = ler_pedido(cur, pedido_id, "FOR SHARE")
            if not pedido:
                return json_error("Pedido não encontrado.", 404)
            if formato:
                if not pedido["itens"]:
                    return json_error("Pedido antigo sem itens: não é possível calcular um documento sem inventar valores.", 409)
                from documentos import gerar_pdf, gerar_txt
                conteudo = gerar_pdf(pedido) if formato == "pdf" else gerar_txt(pedido).encode("utf-8")
                disposicao = "inline" if request.args.get("visualizar") == "1" else "attachment"
                nome_documento = "orcamento" if pedido["tipo"] == "ORCAMENTO" else "pedido"
                return Response(conteudo, content_type="application/pdf" if formato == "pdf" else "text/plain; charset=utf-8",
                                headers={"Content-Disposition": f'{disposicao}; filename="{nome_documento}-{pedido_id}.{formato}"',
                                         "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
            cur.execute("""SELECT acao,antes,depois,criado_em,usuario_id FROM pedido_eventos
                           WHERE pedido_id=%s ORDER BY id""", (pedido_id,))
            pedido["historico"] = cur.fetchall()
            return jsonify(pedido)
    except psycopg2.Error:
        return json_error("Não foi possível consultar o pedido.", 503)
    finally:
        if conn:
            conn.rollback()
            get_pool().putconn(conn)


@app.post("/estoque/movimentacao")
def movimentar_estoque():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return json_error("Dados inválidos.")
    try:
        produto_id = inteiro(data.get("produto_id"), minimo=1)
        quantidade = inteiro(data.get("quantidade"), minimo=1)
        pedido_id = (inteiro(data["pedido_id"], minimo=1)
                     if data.get("pedido_id") not in (None, "") else None)
    except ValueError:
        return json_error("Produto, quantidade e pedido devem ser números inteiros válidos.")
    tipo = data.get("tipo")
    motivo = data.get("motivo", "")
    if tipo not in ("ENTRADA", "SAIDA"):
        return json_error("O tipo deve ser ENTRADA ou SAIDA.")
    if not isinstance(motivo, str) or len(motivo.strip()) > 200:
        return json_error("O motivo deve ter no máximo 200 caracteres.")
    if pedido_id is not None and tipo != "SAIDA":
        return json_error("Pedidos podem ser vinculados apenas a saídas de estoque.")
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if pedido_id is not None:
                cur.execute("SELECT id, estoque_processado, status, tipo FROM pedidos WHERE id=%s FOR UPDATE", (pedido_id,))
                pedido = cur.fetchone()
                if not pedido:
                    conn.rollback()
                    return json_error("Pedido não encontrado.", 404)
                if pedido["estoque_processado"] or pedido["status"] == "CANCELADO" or pedido["tipo"] == "ORCAMENTO":
                    conn.rollback()
                    return json_error("Registro cancelado, orçamento ainda não confirmado ou pedido já baixado. Use as ações da lista.", 409)
            cur.execute("SELECT estoque, estoque_minimo FROM produtos WHERE id=%s FOR UPDATE", (produto_id,))
            produto = cur.fetchone()
            if not produto:
                conn.rollback()
                return json_error("Produto não encontrado.", 404)
            anterior = produto["estoque"]
            novo = anterior + quantidade if tipo == "ENTRADA" else anterior - quantidade
            if novo < 0:
                conn.rollback()
                return json_error(f"Estoque insuficiente. Disponível: {anterior}.", 409)
            if novo > MAX_INT:
                conn.rollback()
                return json_error("O estoque ultrapassaria o limite permitido.")
            cur.execute("UPDATE produtos SET estoque=%s WHERE id=%s", (novo, produto_id))
            cur.execute("""INSERT INTO movimentacoes
                           (produto_id, tipo, quantidade, estoque_anterior, estoque_posterior, motivo, pedido_id, usuario_id)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (produto_id, tipo, quantidade, anterior, novo, motivo.strip() or None, pedido_id, g.usuario["id"]))
        conn.commit()
        return jsonify({"mensagem": "Movimentação registrada com sucesso.",
                        "estoque_anterior": anterior, "estoque_atual": novo,
                        "estoque_baixo": novo <= produto["estoque_minimo"]}), 201
    except psycopg2.Error:
        if conn:
            conn.rollback()
        return json_error("Erro ao atualizar o banco de dados.", 503)
    finally:
        if conn:
            get_pool().putconn(conn)


@app.get("/movimentacoes")
def listar_movimentacoes():
    try:
        limite = inteiro(request.args.get("limite", "50"), minimo=1)
        offset = inteiro(request.args.get("offset", "0"))
    except ValueError:
        return json_error("Paginação inválida.")
    limite = min(limite, 100)
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""SELECT m.id, m.tipo, m.quantidade, m.estoque_anterior,
                                m.estoque_posterior, m.motivo, m.pedido_id, m.pedido_item_id, m.criado_em,
                                p.nome AS produto, ped.cliente AS pedido_cliente,
                                u.nome AS usuario_nome
                           FROM movimentacoes m JOIN produtos p ON p.id=m.produto_id
                           LEFT JOIN pedidos ped ON ped.id=m.pedido_id
                           LEFT JOIN usuarios u ON u.id=m.usuario_id
                           ORDER BY m.criado_em DESC, m.id DESC LIMIT %s OFFSET %s""", (limite, offset))
            return jsonify(cur.fetchall())
    except psycopg2.Error:
        return json_error("Não foi possível consultar o histórico.", 503)
    finally:
        if conn:
            get_pool().putconn(conn)


@app.errorhandler(404)
def rota_nao_encontrada(_):
    return json_error("Rota não encontrada.", 404)


@app.errorhandler(405)
def metodo_nao_permitido(_):
    return json_error("Método HTTP não permitido para esta rota.", 405)


if __name__ == "__main__":
    validar_configuracao()
    preparar_banco()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "3000")), debug=False)
