"""Testes de validação, permissões e API com banco simulado.

Execute: python -m pytest backend/tests -q
Integração real exige PostgreSQL e deve ser conferida separadamente.
"""
import pytest
import app as modulo
from app import (app, conferir_senha, hash_senha, inteiro,
                 preco_decimal, validar_produto, validar_usuario)

ADMIN = {"id": 1, "nome": "Admin", "email": "admin@exemplo.com",
         "perfil": "ADMIN", "ativo": True, "versao_sessao": 1}
FUNC = {**ADMIN, "id": 2, "nome": "Funcionária", "perfil": "FUNCIONARIO"}
CSRF = "token-para-teste"
HEADERS = {"X-CSRF-Token": CSRF}


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.sql = []
    def __enter__(self): return self
    def __exit__(self, *args): return None
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
    fake_pool = type("FakePool", (), {"putconn": lambda self, conn: None})()
    def set_rows(rows):
        conn = FakeConnection(rows)
        monkeypatch.setattr(modulo, "get_connection", lambda: conn)
        monkeypatch.setattr(modulo, "get_pool", lambda: fake_pool)
        return conn
    return set_rows


@pytest.fixture
def client(monkeypatch):
    app.config.update(TESTING=True, SECRET_KEY="chave-teste-nunca-publicar")
    monkeypatch.setattr(modulo, "consulta_usuario", lambda user_id: None)
    with app.test_client() as teste:
        yield teste


def autenticar(client, monkeypatch, usuario=ADMIN):
    monkeypatch.setattr(modulo, "consulta_usuario", lambda id: usuario if id == usuario["id"] else None)
    with client.session_transaction() as sess:
        sess["usuario_id"] = usuario["id"]
        sess["versao_sessao"] = usuario["versao_sessao"]
        sess["csrf"] = CSRF
    return HEADERS


def test_rota_inicial_sem_banco(client):
    assert client.get("/").json["linguagem"] == "Python/Flask"


def test_unauthorized(client):
    assert client.get("/produtos").status_code == 401
    assert client.post("/produtos", json={}).status_code == 401


def test_primeiro_acesso(client, fake_db):
    fake_db([(False,)])
    r = client.get("/auth/status")
    assert r.status_code == 200
    assert r.json["primeiro_acesso"] is True
    assert r.json["autenticado"] is False


def test_login_com_hash_e_email(client, fake_db, monkeypatch):
    usuario = {**ADMIN, "senha_hash": hash_senha("senha-segura-de-testes"),
               "tentativas_falhas": 0, "bloqueado_ate": None, "bloqueado": False}
    conn = fake_db([usuario])
    r = client.post("/auth/login", json={"email": "ADMIN@EXEMPLO.COM", "senha": "senha-segura-de-testes"})
    assert r.status_code == 200
    assert r.json["usuario"]["perfil"] == "ADMIN"
    assert r.json["csrf"]
    assert conn.commits == 1


def test_login_incorreto(client, fake_db):
    usuario = {**ADMIN, "senha_hash": hash_senha("senha-correta-de-testes"),
               "bloqueado": False}
    conn = fake_db([usuario])
    r = client.post("/auth/login", json={"email": ADMIN["email"], "senha": "errada"})
    assert r.status_code == 401
    assert conn.commits == 1
    assert any("tentativas_falhas" in sql for sql, _ in conn.cur.sql)


def test_login_sem_usuario(client, fake_db):
    fake_db([])
    r = client.post("/auth/login", json={"email": "nao@exemplo.com", "senha": "errada"})
    assert r.status_code == 401


def test_csrf_e_logout(client, monkeypatch, fake_db):
    autenticar(client, monkeypatch)
    assert client.post("/auth/logout").status_code == 403
    fake_db([(True,)])
    assert client.get("/auth/status").json["autenticado"] is True
    assert client.post("/auth/logout", headers=HEADERS).status_code == 200
    assert client.get("/produtos").status_code == 401


@pytest.mark.parametrize("valor", [True, False, 1.5, "1.5", None, -1, 2**31, "abc"])
def test_inteiro_rejeita_invalido(valor):
    with pytest.raises(ValueError): inteiro(valor)


@pytest.mark.parametrize("valor", ["NaN", "Infinity", -1, True, 0, "0.001", "100000000"])
def test_preco_rejeita_invalido(valor):
    with pytest.raises(ValueError): preco_decimal(valor)


def test_preco_brasileiro():
    assert str(preco_decimal("8,50")) == "8.50"


def test_argon2id_senha():
    senha = "um-segredo-grande-para-testar"
    hash_guardado = hash_senha(senha)
    assert hash_guardado.startswith("$argon2id$")
    assert senha not in hash_guardado
    assert conferir_senha(hash_guardado, senha)
    assert not conferir_senha(hash_guardado, "errada")


def test_validacoes():
    base = {"nome": "Coxinha", "preco": "5,50", "estoque": 2, "estoque_minimo": 1}
    assert validar_produto(base) is None
    assert validar_produto({**base, "estoque": 1.5}) is not None
    assert validar_produto({**base, "preco": "NaN"}) is not None
    assert validar_usuario({"nome": "Márcia", "email": "marcia@exemplo.com",
                            "senha": "minha-senha-segura", "perfil": "FUNCIONARIO"}) is None
    assert validar_usuario({"nome": "Márcia", "email": "incorreto", "senha": "curta",
                            "perfil": "ADMIN"}) is not None


def test_funcionario_nao_administra_usuarios(client, monkeypatch):
    autenticar(client, monkeypatch, FUNC)
    assert client.get("/usuarios").status_code == 403
    assert client.post("/usuarios", json={}, headers=HEADERS).status_code == 403
    assert client.post("/produtos", json={}, headers=HEADERS).status_code == 403
    assert client.patch("/usuarios/1", json={"ativo": False}, headers=HEADERS).status_code == 403


def test_admin_cadastro_usuario(client, monkeypatch, fake_db):
    autenticar(client, monkeypatch)
    conn = fake_db([{"id": 4, "nome": "Funcionário", "email": "fun@exemplo.com",
                     "perfil": "FUNCIONARIO", "ativo": True}])
    r = client.post("/usuarios", json={"nome": "Funcionário", "email": "fun@exemplo.com",
                  "senha": "senha-muito-segura", "perfil": "FUNCIONARIO"}, headers=HEADERS)
    assert r.status_code == 201
    assert conn.commits == 1
    assert any("INSERT INTO usuarios" in sql for sql, _ in conn.cur.sql)


def test_admin_nao_desativa_propria_conta(client, monkeypatch):
    autenticar(client, monkeypatch)
    assert client.patch("/usuarios/1", json={"ativo": False}, headers=HEADERS).status_code == 409
    assert client.patch("/usuarios/1", json={"perfil": "FUNCIONARIO"}, headers=HEADERS).status_code == 409


def test_admin_desativa_funcionario_e_revoga_sessao(client, monkeypatch, fake_db):
    autenticar(client, monkeypatch)
    conn = fake_db([{"id": 2, "nome": "Func", "email": "func@exemplo.com",
                     "perfil": "FUNCIONARIO", "ativo": False}])
    r = client.patch("/usuarios/2", json={"ativo": False}, headers=HEADERS)
    assert r.status_code == 200
    assert "versao_sessao=versao_sessao+1" in conn.cur.sql[0][0]


def test_sessao_revogada_por_versao(client, monkeypatch):
    autenticar(client, monkeypatch)
    monkeypatch.setattr(modulo, "consulta_usuario", lambda id: {**ADMIN, "versao_sessao": 2})
    assert client.get("/produtos").status_code == 401


def test_cadastro_produto_csrf_e_validacao(client, monkeypatch):
    autenticar(client, monkeypatch)
    assert client.post("/produtos", json={}).status_code == 403
    r = client.post("/produtos", json={"nome": "X", "preco": "NaN"}, headers=HEADERS)
    assert r.status_code == 400


def test_cadastro_sucesso_com_db_mock(client, monkeypatch, fake_db):
    autenticar(client, monkeypatch)
    conn = fake_db([{"id": 8, "nome": "Pastel", "preco": "6.00", "estoque": 2, "estoque_minimo": 1}])
    r = client.post("/produtos", json={"nome": "Pastel", "preco": "6,00", "estoque": 2,
                      "estoque_minimo": 1}, headers=HEADERS)
    assert r.status_code == 201
    assert conn.commits == 1


def test_estoque_insuficiente_rollback(client, monkeypatch, fake_db):
    autenticar(client, monkeypatch)
    conn = fake_db([{"estoque": 3, "estoque_minimo": 2}])
    r = client.post("/estoque/movimentacao", json={"produto_id": 5, "tipo": "SAIDA",
                    "quantidade": 8}, headers=HEADERS)
    assert r.status_code == 409
    assert conn.rollbacks == 1
    assert "FOR UPDATE" in conn.cur.sql[0][0]


def test_estoque_movimentado_guarda_usuario(client, monkeypatch, fake_db):
    autenticar(client, monkeypatch, FUNC)
    conn = fake_db([{"estoque": 8, "estoque_minimo": 2}])
    r = client.post("/estoque/movimentacao", json={"produto_id": 5, "tipo": "SAIDA",
                    "quantidade": 2}, headers=HEADERS)
    assert r.status_code == 201
    assert conn.cur.sql[-1][1][-1] == FUNC["id"]
    assert conn.commits == 1


def test_historico_paginacao_invalida(client, monkeypatch):
    autenticar(client, monkeypatch)
    assert client.get("/movimentacoes?offset=-1").status_code == 400
