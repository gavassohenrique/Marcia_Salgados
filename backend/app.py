"""API de estoque e rastreabilidade da Márcia Salgados."""
import hmac
import os
import secrets
import time
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

import psycopg2
from flask import Flask, jsonify, request, session
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("FLASK_SECRET_KEY"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=16 * 1024,
)
ADMIN_PASSWORD = os.getenv("APP_ADMIN_PASSWORD", "")
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
    # A mesma definição das tabelas está em database/init.sql, executada na primeira
    # criação do volume. CREATE IF NOT EXISTS mantém compatibilidade com volumes antigos.
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
        CREATE INDEX IF NOT EXISTS idx_movimentacoes_criado_em
          ON movimentacoes (criado_em DESC, id DESC);
    """
    for tentativa in range(10):
        try:
            with psycopg2.connect(**DB_CONFIG) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
            return
        except psycopg2.Error:
            if tentativa == 9:
                raise
            time.sleep(2)


def login_configurado():
    return bool(ADMIN_PASSWORD and app.config.get("SECRET_KEY"))


@app.before_request
def proteger_api():
    if request.path in ("/", "/health", "/auth/status", "/auth/login"):
        return None
    if not login_configurado():
        return json_error("Autenticação não configurada no servidor.", 503)
    if not session.get("autenticado"):
        return json_error("Faça login para continuar.", 401)
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
    autenticado = bool(session.get("autenticado") and login_configurado())
    return jsonify({
        "configurado": login_configurado(),
        "autenticado": autenticado,
        "csrf": session.get("csrf") if autenticado else None,
    })


@app.post("/auth/login")
def auth_login():
    if not login_configurado():
        return json_error("Configure APP_ADMIN_PASSWORD e FLASK_SECRET_KEY no servidor.", 503)
    data = request.get_json(silent=True)
    senha = data.get("senha") if isinstance(data, dict) else None
    if not isinstance(senha, str) or not hmac.compare_digest(senha, ADMIN_PASSWORD):
        return json_error("Senha incorreta.", 401)
    session.clear()
    session.permanent = True
    session["autenticado"] = True
    session["csrf"] = secrets.token_urlsafe(32)
    return jsonify({"mensagem": "Sessão iniciada.", "csrf": session["csrf"]})


@app.post("/auth/logout")
def auth_logout():
    session.clear()
    return jsonify({"mensagem": "Sessão encerrada."})


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
            cur.execute("SELECT id, cliente, referencia, criado_em FROM pedidos ORDER BY id DESC LIMIT 100")
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
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""INSERT INTO pedidos (cliente, referencia) VALUES (%s, %s)
                           RETURNING id, cliente, referencia, criado_em""", (cliente, referencia.strip() or None))
            pedido = cur.fetchone()
        conn.commit()
        return jsonify({"mensagem": "Pedido de referência criado.", "pedido": pedido}), 201
    except psycopg2.Error:
        if conn:
            conn.rollback()
        return json_error("Não foi possível cadastrar o pedido.", 503)
    finally:
        if conn:
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
                cur.execute("SELECT id FROM pedidos WHERE id=%s", (pedido_id,))
                if not cur.fetchone():
                    conn.rollback()
                    return json_error("Pedido não encontrado.", 404)
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
                           (produto_id, tipo, quantidade, estoque_anterior, estoque_posterior, motivo, pedido_id)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                        (produto_id, tipo, quantidade, anterior, novo, motivo.strip() or None, pedido_id))
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
                                m.estoque_posterior, m.motivo, m.pedido_id, m.criado_em,
                                p.nome AS produto, ped.cliente AS pedido_cliente
                           FROM movimentacoes m JOIN produtos p ON p.id=m.produto_id
                           LEFT JOIN pedidos ped ON ped.id=m.pedido_id
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
    if not login_configurado():
        raise RuntimeError("Configure APP_ADMIN_PASSWORD e FLASK_SECRET_KEY antes de executar a API.")
    preparar_banco()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "3000")), debug=False)
