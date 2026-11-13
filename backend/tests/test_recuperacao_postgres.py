"""Recuperação integrada com PostgreSQL descartável; transporte SMTP isolado nos testes."""
import hashlib
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest

pytestmark = pytest.mark.skipif(os.getenv('TEST_POSTGRES') != '1', reason='Requer PostgreSQL isolado')


def test_recuperacao_postgres(monkeypatch):
    import app as db
    import recovery
    import psycopg2
    assert db.DB_CONFIG['dbname'].startswith('test_')
    db.preparar_banco()
    db.preparar_banco()  # migração aditiva idempotente
    for key, value in dict(PUBLIC_APP_URL='https://estoque.example', SMTP_HOST='smtp.example',
                           SMTP_USERNAME='teste', SMTP_PASSWORD='somente-teste', SMTP_FROM='teste@example.com').items():
        monkeypatch.setenv(key, value)
    email = f'{uuid.uuid4().hex}@example.com'
    password = 'SenhaAntiga!'
    with psycopg2.connect(**db.DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO usuarios(nome,email,senha_hash,perfil) VALUES ('Recuperacao',%s,%s,'FUNCIONARIO') RETURNING id", (email, db.hash_senha(password)))
            uid = cur.fetchone()[0]
    client = db.app.test_client()
    assert client.post('/auth/login', json={'email':email,'senha':password}).status_code == 200
    delivered = []
    event = threading.Event()
    def capture(address, token):
        delivered.append((address, token))
        event.set()
    monkeypatch.setattr(recovery, 'send_email', capture)
    public = db.app.test_client()
    result = public.post('/auth/recuperar-senha', json={'email':email})
    assert result.status_code == 200
    assert event.wait(5)
    token = delivered[0][1]
    assert public.post('/auth/recuperar-senha', json={'email':'ausente@example.com'}).json == result.json
    assert public.post('/auth/recuperar-senha', json={'email':[]}).status_code == 400
    with psycopg2.connect(**db.DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT token_hash, expira_em>NOW() FROM recuperacao_senha WHERE usuario_id=%s', (uid,))
            row = cur.fetchone()
            assert row == (hashlib.sha256(token.encode()).hexdigest(), True)
    def reset(value=token, senha='NovaSenha!', confirmacao='NovaSenha!'):
        return public.post('/auth/redefinir-senha', json={'token':value,'nova_senha':senha,'confirmacao':confirmacao})
    assert reset(senha='fraca', confirmacao='fraca').status_code == 400
    assert reset(confirmacao='Diferente!').status_code == 400
    assert reset('x'*43).status_code == 400
    assert reset().status_code == 200
    assert reset().status_code == 400
    assert client.get('/produtos').status_code == 401
    assert client.post('/auth/login', json={'email':email,'senha':password}).status_code == 401
    assert client.post('/auth/login', json={'email':email,'senha':'NovaSenha!'}).status_code == 200
    # Expiração e invalidação por versão, inclusive para tokens ainda não consumidos.
    def insert_token(raw, expired=False, version_delta=0):
        with psycopg2.connect(**db.DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO recuperacao_senha(token_hash,usuario_id,versao_sessao,expira_em) SELECT %s,id,versao_sessao+%s,NOW()+(%s * INTERVAL '1 minute') FROM usuarios WHERE id=%s", (hashlib.sha256(raw.encode()).hexdigest(),version_delta,-1 if expired else 20,uid))
    expired = 'e'*43
    insert_token(expired, expired=True)
    assert reset(expired).status_code == 400
    stale = 's'*43
    insert_token(stale, version_delta=-1)
    assert reset(stale).status_code == 400
    racing = 'r'*43
    insert_token(racing)
    def race(_):
        with db.app.test_client() as c:
            return c.post('/auth/redefinir-senha', json={'token':racing,'nova_senha':'OutraSenha!','confirmacao':'OutraSenha!'}).status_code
    with ThreadPoolExecutor(2) as workers:
        assert sorted(workers.map(race, range(2))) == [200,400]
    # Limites reais no banco compartilhados por clientes diferentes.
    for _ in range(4):
        assert public.post('/auth/recuperar-senha', json={'email':email}).json == result.json
    with psycopg2.connect(**db.DB_CONFIG) as conn:
        with conn.cursor() as cur:
            key = __import__('hmac').new(db.app.secret_key.encode(), f'request-email:{email}'.encode(), hashlib.sha256).hexdigest()
            cur.execute('SELECT tentativas FROM recuperacao_limites WHERE chave=%s', (key,))
            assert cur.fetchone()[0] == 5
    for _ in range(25):
        response = reset('i'*43)
    assert response.status_code == 429
    monkeypatch.setenv('PUBLIC_APP_URL','http://public.example')
    assert public.post('/auth/recuperar-senha',json={'email':email}).status_code == 503


def test_smtp_tls_real_adapter(monkeypatch):
    """Testa protocolo do adaptador, sem alegar entrega externa."""
    import recovery
    monkeypatch.setenv('PUBLIC_APP_URL','https://estoque.example')
    for key in ('SMTP_HOST','SMTP_USERNAME','SMTP_PASSWORD','SMTP_FROM'):
        monkeypatch.setenv(key,'teste@example.com')
    actions = []
    class SMTP:
        def __init__(self, *args, **kwargs): actions.append('connect')
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def ehlo(self): actions.append('ehlo')
        def starttls(self, **kwargs):
            assert kwargs['context'].check_hostname
            actions.append('tls')
        def login(self,*args): actions.append('login')
        def send_message(self,msg):
            assert 'https://estoque.example/#redefinir-senha=' in msg.get_content()
            actions.append('send')
    monkeypatch.setattr(recovery.smtplib,'SMTP',SMTP)
    recovery.send_email('destino@example.com','token-de-teste')
    assert actions == ['connect','ehlo','tls','ehlo','login','send']
