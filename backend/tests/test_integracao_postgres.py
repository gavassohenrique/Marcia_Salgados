"""Teste real, limitado a um banco PostgreSQL descartável e isolado em CI.

Só executa com TEST_POSTGRES=1 e POSTGRES_DB começando com test_.
Não trunca nem altera dados reais do computador do usuário.
"""
import os
import pytest

pytestmark = pytest.mark.skipif(os.getenv("TEST_POSTGRES") != "1", reason="Requer PostgreSQL isolado no CI")


def test_flask_integrado_ao_postgresql_real():
    import psycopg2
    import app as modulo

    assert modulo.DB_CONFIG["dbname"].startswith("test_"), "Use somente um banco descartável test_*"
    assert modulo.app.config.get("SECRET_KEY"), "Defina FLASK_SECRET_KEY de teste"
    modulo.preparar_banco()
    with psycopg2.connect(**modulo.DB_CONFIG) as conn:
        with conn.cursor() as cur:
            # O CI possui banco exclusivo, recém-criado. Não limpe banco do usuário.
            cur.execute("SELECT COUNT(*) FROM usuarios")
            assert cur.fetchone()[0] == 0
            cur.execute("""INSERT INTO usuarios (nome, email, senha_hash, perfil)
                           VALUES ('Admin CI','admin@ci.example',%s,'ADMIN')""",
                        (modulo.hash_senha("senha-admin-exclusiva-de-ci"),))

    modulo.app.config["TESTING"] = True
    admin = modulo.app.test_client()
    status = admin.get('/auth/status')
    assert status.status_code == 200
    assert status.json['primeiro_acesso'] is False
    login = admin.post('/auth/login', json={"email": "admin@ci.example", "senha": "senha-admin-exclusiva-de-ci"})
    assert login.status_code == 200
    headers = {'X-CSRF-Token': login.json['csrf']}

    novo_usuario = admin.post('/usuarios', headers=headers, json={
        'nome': 'Funcionária CI', 'email': 'func@ci.example',
        'senha': 'Senha-funcionaria-de-ci!', 'perfil': 'FUNCIONARIO'
    })
    assert novo_usuario.status_code == 201
    func_id = novo_usuario.json['usuario']['id']

    novo_produto = admin.post('/produtos', headers=headers, json={
        'nome': 'Coxinha de teste CI', 'preco': '5.50', 'estoque': 12, 'estoque_minimo': 3
    })
    assert novo_produto.status_code == 201
    produto_id = novo_produto.json['produto']['id']

    func = modulo.app.test_client()
    login_func = func.post('/auth/login', json={'email':'func@ci.example','senha':'Senha-funcionaria-de-ci!'})
    assert login_func.status_code == 200
    h_func = {'X-CSRF-Token': login_func.json['csrf']}
    assert func.post('/produtos', headers=h_func, json={}).status_code == 403
    mov = func.post('/estoque/movimentacao', headers=h_func, json={
        'produto_id': produto_id, 'tipo': 'SAIDA', 'quantidade': 2,
        'motivo': 'Entrega CI'
    })
    assert mov.status_code == 201
    assert mov.json['estoque_atual'] == 10
    historico = func.get('/movimentacoes')
    assert historico.status_code == 200
    registro = next(m for m in historico.json if m['produto'] == 'Coxinha de teste CI')
    assert registro['usuario_nome'] == 'Funcionária CI'

    desativar = admin.patch(f'/usuarios/{func_id}', headers=headers, json={'ativo':False})
    assert desativar.status_code == 200
    assert func.get('/produtos').status_code == 401

    with psycopg2.connect(**modulo.DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT estoque FROM produtos WHERE id=%s', (produto_id,))
            assert cur.fetchone()[0] == 10
            cur.execute('''SELECT tipo,quantidade,usuario_id FROM movimentacoes
                           WHERE produto_id=%s ORDER BY id''', (produto_id,))
            assert cur.fetchall() == [('ENTRADA', 12, login.json['usuario']['id']), ('SAIDA', 2, func_id)]
