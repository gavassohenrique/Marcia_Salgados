import pytest

from app import app, validar_produto

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_rota_inicial(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.get_json()["linguagem"] == "Python/Flask"


def test_produto_sem_nome_e_invalido():
    assert validar_produto({"nome": "", "preco": 5}) == "Informe o nome do produto."


def test_produto_com_preco_negativo_e_invalido():
    assert validar_produto({"nome": "Coxinha", "preco": -1}) == "O preço deve ser maior que zero."


def test_produto_valido():
    assert validar_produto({"nome": "Coxinha", "preco": 5, "estoque": 10, "estoque_minimo": 3}) is None
