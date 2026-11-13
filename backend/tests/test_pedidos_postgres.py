"""Pedidos completos em PostgreSQL exclusivo de teste, sem limpar dados existentes."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import psycopg2
import pytest
import app as modulo

pytestmark = pytest.mark.skipif(os.getenv("TEST_POSTGRES") != "1", reason="Requer PostgreSQL isolado")


@pytest.fixture
def banco():
    assert modulo.DB_CONFIG["dbname"].startswith("test_")
    modulo.preparar_banco()
    modulo.app.config["TESTING"] = True
    with psycopg2.connect(**modulo.DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO usuarios(nome,email,senha_hash,perfil)
                           VALUES ('Operador',%s,'hash-nao-usado','FUNCIONARIO') RETURNING id""",
                        (f"{uuid4()}@test.example",))
            usuario = cur.fetchone()[0]
            ids = []
            for nome in ('Coxinha', 'Pastel'):
                cur.execute("""INSERT INTO produtos(nome,preco,estoque) VALUES (%s,5.50,10)
                               RETURNING id""", (nome,))
                ids.append(cur.fetchone()[0])
    return usuario, ids


def cliente(usuario):
    client = modulo.app.test_client()
    with client.session_transaction() as sess:
        sess.update(usuario_id=usuario, versao_sessao=1, csrf="csrf-teste")
    return client


def enviar(client, ids, quantidades=(2, 3)):
    return client.post('/pedidos', headers={'X-CSRF-Token': 'csrf-teste'}, json={
        'cliente': 'Cliente teste', 'referencia': 'Entrega',
        'itens': [{'produto_id': p, 'quantidade': q} for p, q in zip(ids, quantidades)]})


def consultar(sql, params=()):
    with psycopg2.connect(**modulo.DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def test_itens_persistencia_auditoria_e_bloqueio_baixa_duplicada(banco):
    usuario, ids = banco
    client = cliente(usuario)
    response = enviar(client, ids)
    assert response.status_code == 201
    pedido = response.json['pedido']
    assert len(pedido['itens']) == 2
    assert consultar('SELECT estoque FROM produtos WHERE id=ANY(%s) ORDER BY id', (ids,)) == [(8,), (7,)]
    assert consultar('''SELECT quantidade,estoque_anterior,estoque_posterior,usuario_id,
                        pedido_item_id IS NOT NULL FROM movimentacoes WHERE pedido_id=%s ORDER BY id''',
                     (pedido['id'],)) == [(2, 10, 8, usuario, True), (3, 10, 7, usuario, True)]
    with psycopg2.connect(**modulo.DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE produtos SET nome='Renomeado',preco=9 WHERE id=ANY(%s)", (ids,))
    salvo = next(p for p in client.get('/pedidos').json if p['id'] == pedido['id'])
    assert salvo['itens'][0]['produto_nome'] == 'Coxinha'
    assert float(salvo['itens'][0]['preco_unitario']) == 5.5
    assert salvo['usuario_nome'] == 'Operador'
    assert client.post('/estoque/movimentacao', headers={'X-CSRF-Token': 'csrf-teste'}, json={
        'produto_id': ids[0], 'quantidade': 1, 'tipo': 'SAIDA', 'pedido_id': pedido['id']
    }).status_code == 409
    assert consultar('SELECT estoque FROM produtos WHERE id=%s', (ids[0],)) == [(8,)]


@pytest.mark.parametrize('quantidade', [0, -1, True, 1.5, '1.5', None, 2147483648])
def test_quantidades_invalidas_sem_efeito(banco, quantidade):
    usuario, ids = banco
    assert enviar(cliente(usuario), ids, (2, quantidade)).status_code == 400
    assert consultar('SELECT estoque FROM produtos WHERE id=ANY(%s) ORDER BY id', (ids,)) == [(10,), (10,)]
    assert consultar('SELECT id FROM movimentacoes WHERE produto_id=ANY(%s)', (ids,)) == []


def test_falhas_nao_persistem_parcialmente(banco):
    usuario, ids = banco
    client = cliente(usuario)
    assert enviar(client, ids, (2, 11)).status_code == 409
    assert enviar(client, [ids[0], 2147483647]).status_code == 404
    assert enviar(client, [ids[0], ids[0]]).status_code == 400
    assert enviar(client, []).status_code == 400
    assert client.post('/pedidos', json={}, headers={}).status_code == 403
    assert modulo.app.test_client().get('/pedidos').status_code == 401
    assert consultar('SELECT id FROM pedidos WHERE usuario_id=%s', (usuario,)) == []
    assert consultar('SELECT estoque FROM produtos WHERE id=ANY(%s) ORDER BY id', (ids,)) == [(10,), (10,)]


def test_erro_sql_reverte_pedido_itens_e_saldo(banco):
    usuario, ids = banco
    # Trigger exclusivo para este produto simula falha após inserir item e atualizar saldo.
    with psycopg2.connect(**modulo.DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(f"""CREATE FUNCTION falha_pedido_teste() RETURNS trigger LANGUAGE plpgsql AS $$
                            BEGIN IF NEW.produto_id={ids[1]} THEN RAISE EXCEPTION 'falha teste'; END IF;
                            RETURN NEW; END $$;
                            CREATE TRIGGER falha_pedido_teste BEFORE INSERT ON movimentacoes
                            FOR EACH ROW EXECUTE FUNCTION falha_pedido_teste()""")
    try:
        assert enviar(cliente(usuario), ids).status_code == 503
        assert consultar('SELECT id FROM pedidos WHERE usuario_id=%s', (usuario,)) == []
        assert consultar('SELECT id FROM pedido_itens WHERE produto_id=ANY(%s)', (ids,)) == []
        assert consultar('SELECT id FROM movimentacoes WHERE produto_id=ANY(%s)', (ids,)) == []
        assert consultar('SELECT estoque FROM produtos WHERE id=ANY(%s) ORDER BY id', (ids,)) == [(10,), (10,)]
    finally:
        with psycopg2.connect(**modulo.DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute('DROP TRIGGER falha_pedido_teste ON movimentacoes; DROP FUNCTION falha_pedido_teste()')


def test_pedidos_concorrentes_nao_vendem_mesmo_saldo(banco):
    usuario, ids = banco
    barreira = Barrier(2)
    def pedir(ordem):
        client = cliente(usuario)
        barreira.wait(timeout=10)
        return enviar(client, ordem, (7, 7)).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        resultados = list(executor.map(pedir, [ids, ids[::-1]]))
    assert sorted(resultados) == [201, 409]
    assert consultar('SELECT estoque FROM produtos WHERE id=ANY(%s) ORDER BY id', (ids,)) == [(3,), (3,)]
    assert len(consultar('SELECT id FROM pedidos WHERE usuario_id=%s', (usuario,))) == 1


def test_migracao_aditiva_preserva_schema_antigo(monkeypatch):
    assert modulo.DB_CONFIG['dbname'].startswith('test_')
    schema = 'test_migracao_' + uuid4().hex
    config = dict(modulo.DB_CONFIG)
    with psycopg2.connect(**config) as conn:
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA {schema}')
    config['options'] = f'-c search_path={schema}'
    monkeypatch.setattr(modulo, 'DB_CONFIG', config)
    with psycopg2.connect(**config) as conn:
        with conn.cursor() as cur:
            cur.execute('''CREATE TABLE pedidos (id SERIAL PRIMARY KEY, cliente VARCHAR(150) NOT NULL,
                           referencia VARCHAR(80), criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW());
                           INSERT INTO pedidos(cliente) VALUES ('Cliente preservado');
                           CREATE TABLE produtos (id SERIAL PRIMARY KEY,nome VARCHAR(100) NOT NULL,
                             preco NUMERIC(10,2) NOT NULL,estoque INTEGER NOT NULL,
                             criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW());
                           INSERT INTO produtos(nome,preco,estoque) VALUES ('Produto preservado',4.50,7);
                           CREATE TABLE movimentacoes (id SERIAL PRIMARY KEY,
                             produto_id INTEGER NOT NULL REFERENCES produtos(id),tipo VARCHAR(7) NOT NULL,
                             quantidade INTEGER NOT NULL,estoque_anterior INTEGER NOT NULL,
                             estoque_posterior INTEGER NOT NULL,motivo VARCHAR(200),pedido_id INTEGER,
                             criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW());
                           INSERT INTO movimentacoes(produto_id,tipo,quantidade,estoque_anterior,
                             estoque_posterior,motivo,pedido_id) VALUES (1,'SAIDA',3,10,7,'Antigo',1)''')
    modulo.preparar_banco()
    modulo.preparar_banco()
    assert consultar('SELECT cliente,estoque_processado,usuario_id FROM pedidos') == [('Cliente preservado', False, None)]
    assert consultar('SELECT * FROM pedido_itens') == []
    assert consultar('SELECT nome,preco,estoque FROM produtos') == [('Produto preservado', modulo.Decimal('4.50'), 7)]
    assert consultar('SELECT quantidade,estoque_anterior,estoque_posterior,motivo,pedido_id FROM movimentacoes') == [(3, 10, 7, 'Antigo', 1)]


def test_saida_manual_ainda_aceita_pedido_antigo(banco):
    usuario, ids = banco
    with psycopg2.connect(**modulo.DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO pedidos(cliente) VALUES ('Legado') RETURNING id")
            pedido = cur.fetchone()[0]
    client = cliente(usuario)
    response = client.post('/estoque/movimentacao', headers={'X-CSRF-Token': 'csrf-teste'}, json={
        'produto_id': ids[0], 'quantidade': 1, 'tipo': 'SAIDA', 'pedido_id': pedido})
    assert response.status_code == 201
    assert response.json['estoque_atual'] == 9


@pytest.mark.parametrize('saldo', [0, 12])
def test_cadastro_de_produto_audita_somente_saldo_inicial_positivo(banco, saldo):
    usuario, _ = banco
    with psycopg2.connect(**modulo.DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE usuarios SET perfil='ADMIN' WHERE id=%s", (usuario,))
    response = cliente(usuario).post('/produtos', headers={'X-CSRF-Token': 'csrf-teste'}, json={
        'nome': 'Produto auditado', 'preco': '4.50', 'estoque': saldo})
    assert response.status_code == 201
    produto = response.json['produto']['id']
    movimentos = consultar('''SELECT tipo,quantidade,estoque_anterior,estoque_posterior,
                               usuario_id,motivo FROM movimentacoes WHERE produto_id=%s''', (produto,))
    assert movimentos == ([('ENTRADA', saldo, 0, saldo, usuario, 'Estoque inicial')] if saldo else [])


def test_troca_e_reset_de_senha_revogam_sessoes_reais(banco):
    usuario, _ = banco
    email, senha = f'{uuid4()}@test.example', 'SenhaAnterior!'
    with psycopg2.connect(**modulo.DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE usuarios SET email=%s,senha_hash=%s,perfil='ADMIN' WHERE id=%s",
                        (email, modulo.hash_senha(senha), usuario))
    a, b = modulo.app.test_client(), modulo.app.test_client()
    ha = {'X-CSRF-Token': a.post('/auth/login', json={'email': email, 'senha': senha}).json['csrf']}
    assert b.post('/auth/login', json={'email': email, 'senha': senha}).status_code == 200
    assert a.post('/auth/alterar-senha', headers=ha, json={
        'senha_atual': senha, 'nova_senha': 'NovaSenhaTeste!'}).status_code == 200
    assert a.get('/produtos').status_code == 200
    assert b.get('/produtos').status_code == 401
    assert b.post('/auth/login', json={'email': email, 'senha': senha}).status_code == 401
    assert b.post('/auth/login', json={'email': email, 'senha': 'NovaSenhaTeste!'}).status_code == 200
    assert a.post(f'/usuarios/{usuario}/redefinir-senha', headers=ha,
                  json={'nova_senha': 'SenhaRedefinida!'}).status_code == 200
    assert a.get('/produtos').status_code == b.get('/produtos').status_code == 401
    assert a.post('/auth/login', json={'email': email, 'senha': 'SenhaRedefinida!'}).status_code == 200


def test_bloqueio_apos_cinco_falhas_e_liberacao_apos_prazo(banco):
    usuario, _ = banco
    email, senha = f'{uuid4()}@test.example', 'SenhaTeste!'
    with psycopg2.connect(**modulo.DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute('UPDATE usuarios SET email=%s,senha_hash=%s WHERE id=%s',
                        (email, modulo.hash_senha(senha), usuario))
    client = modulo.app.test_client()
    for _ in range(5):
        assert client.post('/auth/login', json={'email': email, 'senha': 'errada'}).status_code == 401
    assert client.post('/auth/login', json={'email': email, 'senha': senha}).status_code == 401
    with psycopg2.connect(**modulo.DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE usuarios SET bloqueado_ate=NOW()-INTERVAL '1 second' WHERE id=%s", (usuario,))
    assert client.post('/auth/login', json={'email': email, 'senha': senha}).status_code == 200
    assert consultar('SELECT tentativas_falhas,bloqueado_ate FROM usuarios WHERE id=%s', (usuario,)) == [(0, None)]
