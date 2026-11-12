"""Testes para Flask. Execute com: python -m pytest backend/tests -q."""
import pytest
from app import app, inteiro, preco_decimal, validar_produto


@pytest.fixture
def client(monkeypatch):
    import app as modulo
    monkeypatch.setattr(modulo, "ADMIN_PASSWORD", "senha-de-teste")
    app.config.update(TESTING=True, SECRET_KEY="segredo-exclusivo-de-teste")
    with app.test_client() as client:
        yield client


def autenticar(client):
    response = client.post("/auth/login", json={"senha": "senha-de-teste"})
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json["csrf"]}


def test_rota_inicial_sem_banco(client):
    assert client.get("/").json["linguagem"] == "Python/Flask"


def test_unauthorized(client):
    assert client.get("/produtos").status_code == 401
    assert client.post("/produtos", json={}).status_code == 401


def test_login_incorreto(client):
    assert client.post("/auth/login", json={"senha": "errada"}).status_code == 401
    assert client.get("/auth/status").json["autenticado"] is False


def test_login_e_csrf(client):
    autenticar(client)
    assert client.get("/auth/status").json["autenticado"] is True
    assert client.post("/auth/logout").status_code == 403
    token = client.get("/auth/status").json["csrf"]
    assert client.post("/auth/logout", headers={"X-CSRF-Token": token}).status_code == 200
    assert client.get("/produtos").status_code == 401


@pytest.mark.parametrize("valor", [True, False, 1.5, "1.5", None, -1, -999, 2**31, "abc"])
def test_inteiro_rejeita_invalido(valor):
    with pytest.raises(ValueError):
        inteiro(valor)


@pytest.mark.parametrize("valor", ["NaN", "Infinity", -1, True, 0, "0.001", "100000000"])
def test_preco_rejeita_invalido(valor):
    with pytest.raises(ValueError):
        preco_decimal(valor)


def test_preco_brasileiro():
    assert str(preco_decimal("8,50")) == "8.50"


def test_valida_produto():
    base = {"nome": "Coxinha", "preco": "5,50", "estoque": 2, "estoque_minimo": 1}
    assert validar_produto(base) is None
    assert validar_produto({**base, "nome": None}) is not None
    assert validar_produto({**base, "estoque": 1.5}) is not None
    assert validar_produto({**base, "estoque": True}) is not None
    assert validar_produto({**base, "preco": "NaN"}) is not None
    assert validar_produto({"nome": "X", "preco": "5", "estoque_minimo": 0}, edicao=True) is None


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.sql = []
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, params=None): self.sql.append((sql, params))
    def fetchone(self): return self.rows.pop(0) if self.rows else None
    def fetchall(self): return self.rows


class FakeConnection:
    def __init__(self, rows=None):
        self.cur = FakeCursor(rows)
        self.commits = 0
        self.rollbacks = 0
    def cursor(self, **kwargs): return self.cur
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1


@pytest.fixture
def fake_db(monkeypatch):
    import app as modulo
    pool = type("FakePool", (), {"putconn": lambda self, conn: None})()
    def set_rows(rows):
        conn = FakeConnection(rows)
        monkeypatch.setattr(modulo, "get_connection", lambda: conn)
        monkeypatch.setattr(modulo, "get_pool", lambda: pool)
        return conn
    return set_rows


def test_cadastro_sem_csrf(client):
    autenticar(client)
    assert client.post("/produtos", json={}).status_code == 403


def test_cadastro_valida_sem_banco(client):
    headers = autenticar(client)
    resposta = client.post("/produtos", json={"nome": "X", "preco": "NaN"}, headers=headers)
    assert resposta.status_code == 400


def test_cadastro_sucesso_com_db_mock(client, fake_db):
    headers = autenticar(client)
    conn = fake_db([{"id": 8, "nome": "Pastel", "preco": "6.00", "estoque": 2, "estoque_minimo": 1}])
    r = client.post("/produtos", json={"nome": "Pastel", "preco": "6,00", "estoque": 2, "estoque_minimo": 1}, headers=headers)
    assert r.status_code == 201
    assert conn.commits == 1
    assert "INSERT INTO produtos" in conn.cur.sql[0][0]


def test_edicao_nao_altera_saldo(client, fake_db):
    headers = autenticar(client)
    conn = fake_db([{"id": 3, "nome": "Empada", "preco": "9.00", "estoque": 20, "estoque_minimo": 4}])
    r = client.put("/produtos/3", json={"nome": "Empada", "preco": "9.00", "estoque_minimo": 4}, headers=headers)
    assert r.status_code == 200
    assert "estoque=%s" not in conn.cur.sql[0][0]


def test_estoque_insuficiente_rollback(client, fake_db):
    headers = autenticar(client)
    conn = fake_db([{"estoque": 3, "estoque_minimo": 2}])
    r = client.post("/estoque/movimentacao", json={"produto_id": 5, "tipo": "SAIDA", "quantidade": 8}, headers=headers)
    assert r.status_code == 409
    assert conn.rollbacks == 1
    assert "FOR UPDATE" in conn.cur.sql[0][0]


def test_movimentacao_rejeita_fracao(client):
    headers = autenticar(client)
    r = client.post("/estoque/movimentacao", json={"produto_id": 2, "tipo": "SAIDA", "quantidade": 1.5}, headers=headers)
    assert r.status_code == 400


def test_movimentacao_com_pedido_inexistente(client, fake_db):
    headers = autenticar(client)
    conn = fake_db([])
    r = client.post("/estoque/movimentacao", json={"produto_id": 2, "tipo": "SAIDA", "quantidade": 1, "pedido_id": 40}, headers=headers)
    assert r.status_code == 404
    assert conn.rollbacks == 1


def test_pedido_valida_cliente(client):
    headers = autenticar(client)
    r = client.post("/pedidos", json={"cliente": ""}, headers=headers)
    assert r.status_code == 400


def test_historico_paginacao_invalida(client):
    autenticar(client)
    assert client.get("/movimentacoes?offset=-1").status_code == 400
