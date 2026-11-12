import os
import time
from decimal import Decimal, InvalidOperation
from flask import Flask, jsonify, request
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "postgres"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("POSTGRES_DB", os.getenv("DB_NAME", "appdb")),
    "user": os.getenv("POSTGRES_USER", os.getenv("DB_USER", "user")),
    "password": os.getenv("POSTGRES_PASSWORD", os.getenv("DB_PASSWORD", "password")),
}

connection_pool = None

def get_pool():
    global connection_pool
    if connection_pool is None:
        connection_pool = pool.SimpleConnectionPool(1, 10, **DB_CONFIG)
    return connection_pool

def get_connection():
    return get_pool().getconn()

def json_error(message, status=400):
    return jsonify({"erro": message}), status

def validar_produto(data):
    if not isinstance(data, dict):
        return "Os dados enviados são inválidos."
    nome = str(data.get("nome", "")).strip()
    if not nome:
        return "Informe o nome do produto."
    if len(nome) > 100:
        return "O nome do produto deve ter no máximo 100 caracteres."
    try:
        preco = Decimal(str(data.get("preco", ""))).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return "Informe um preço válido."
    if preco <= 0:
        return "O preço deve ser maior que zero."
    try:
        estoque = int(data.get("estoque", 0))
        estoque_minimo = int(data.get("estoque_minimo", 0))
    except (TypeError, ValueError):
        return "Estoque e estoque mínimo devem ser números inteiros."
    if estoque < 0 or estoque_minimo < 0:
        return "Estoque e estoque mínimo não podem ser negativos."
    return None

def preparar_banco():
    sql = """
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
    """
    for tentativa in range(10):
        conn = None
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
            conn.close()
            return
        except psycopg2.Error:
            if conn:
                conn.close()
            if tentativa == 9:
                raise
            time.sleep(2)

@app.get("/")
def home():
    return jsonify({"mensagem": "API Marcia Salgados funcionando", "linguagem": "Python/Flask"})

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
        return json_error(erro, 400)
    nome = str(data["nome"]).strip()
    preco = Decimal(str(data["preco"]))
    estoque = int(data.get("estoque", 0))
    estoque_minimo = int(data.get("estoque_minimo", 0))
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """INSERT INTO produtos (nome, preco, estoque, estoque_minimo)
                   VALUES (%s, %s, %s, %s)
                   RETURNING id, nome, preco, estoque, estoque_minimo""",
                (nome, preco, estoque, estoque_minimo),
            )
            produto = cur.fetchone()
        conn.commit()
        return jsonify({"mensagem": "Produto cadastrado com sucesso.", "produto": produto}), 201
    except psycopg2.Error:
        if conn:
            conn.rollback()
        return json_error("Não foi possível cadastrar o produto no banco de dados.", 503)
    finally:
        if conn:
            get_pool().putconn(conn)


@app.put("/produtos/<int:produto_id>")
def editar_produto(produto_id):
    data = request.get_json(silent=True)
    erro = validar_produto(data)
    if erro:
        return json_error(erro, 400)

    nome = str(data["nome"]).strip()
    preco = Decimal(str(data["preco"])).quantize(Decimal("0.01"))
    estoque_minimo = int(data.get("estoque_minimo", 0))
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """UPDATE produtos
                   SET nome = %s, preco = %s, estoque_minimo = %s
                   WHERE id = %s
                   RETURNING id, nome, preco, estoque, estoque_minimo""",
                (nome, preco, estoque_minimo, produto_id),
            )
            produto = cur.fetchone()
        if not produto:
            conn.rollback()
            return json_error("Produto não encontrado.", 404)
        conn.commit()
        return jsonify({"mensagem": "Produto atualizado com sucesso.", "produto": produto})
    except psycopg2.Error:
        if conn:
            conn.rollback()
        return json_error("Não foi possível atualizar o produto no banco de dados.", 503)
    finally:
        if conn:
            get_pool().putconn(conn)

@app.put("/produtos/<int:produto_id>")
def editar_produto(produto_id):
    data = request.get_json(silent=True)
    erro = validar_produto(data)
    if erro:
        return json_error(erro, 400)

    nome = str(data["nome"]).strip()
    preco = Decimal(str(data["preco"])).quantize(Decimal("0.01"))
    estoque_minimo = int(data.get("estoque_minimo", 0))
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """UPDATE produtos
                   SET nome = %s, preco = %s, estoque_minimo = %s
                   WHERE id = %s
                   RETURNING id, nome, preco, estoque, estoque_minimo""",
                (nome, preco, estoque_minimo, produto_id),
            )
            produto = cur.fetchone()
        if not produto:
            conn.rollback()
            return json_error("Produto não encontrado.", 404)
        conn.commit()
        return jsonify({"mensagem": "Produto atualizado com sucesso.", "produto": produto})
    except psycopg2.Error:
        if conn:
            conn.rollback()
        return json_error("Não foi possível atualizar o produto no banco de dados.", 503)
    finally:
        if conn:
            get_pool().putconn(conn)


@app.post("/estoque/movimentacao")
def movimentar_estoque():
    data = request.get_json(silent=True) or {}
    try:
        produto_id = int(data.get("produto_id"))
        quantidade = int(data.get("quantidade"))
    except (TypeError, ValueError):
        return json_error("Produto e quantidade devem ser informados corretamente.")
    tipo = str(data.get("tipo", "")).upper().strip()
    motivo = str(data.get("motivo", "")).strip()
    pedido_id = data.get("pedido_id")
    if tipo not in ("ENTRADA", "SAIDA"):
        return json_error("O tipo deve ser ENTRADA ou SAIDA.")
    if quantidade <= 0:
        return json_error("A quantidade deve ser maior que zero.")
    if len(motivo) > 200:
        return json_error("O motivo deve ter no máximo 200 caracteres.")
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM produtos WHERE id = %s FOR UPDATE", (produto_id,))
            produto = cur.fetchone()
            if not produto:
                conn.rollback()
                return json_error("Produto não encontrado.", 404)
            anterior = produto["estoque"]
            novo = anterior + quantidade if tipo == "ENTRADA" else anterior - quantidade
            if novo < 0:
                conn.rollback()
                return json_error(f"Estoque insuficiente. Disponível: {anterior}.", 409)
            cur.execute("UPDATE produtos SET estoque = %s WHERE id = %s", (novo, produto_id))
            cur.execute(
                """INSERT INTO movimentacoes
                   (produto_id, tipo, quantidade, estoque_anterior, estoque_posterior, motivo, pedido_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (produto_id, tipo, quantidade, anterior, novo, motivo or None, pedido_id),
            )
        conn.commit()
        return jsonify({
            "mensagem": "Movimentação registrada com sucesso.",
            "estoque_anterior": anterior,
            "estoque_atual": novo,
            "estoque_baixo": novo <= produto["estoque_minimo"],
        }), 201
    except psycopg2.Error:
        if conn:
            conn.rollback()
        return json_error("Erro ao acessar ou atualizar o banco de dados.", 503)
    finally:
        if conn:
            get_pool().putconn(conn)

@app.get("/movimentacoes")
def listar_movimentacoes():
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT m.id, m.tipo, m.quantidade, m.estoque_anterior,
                       m.estoque_posterior, m.motivo, m.pedido_id, m.criado_em,
                       p.nome AS produto
                FROM movimentacoes m
                JOIN produtos p ON p.id = m.produto_id
                ORDER BY m.criado_em DESC, m.id DESC
                LIMIT 50
            """)
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
    preparar_banco()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "3000")), debug=False)
