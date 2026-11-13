"""Recuperação por SMTP TLS; tokens nunca são registrados em logs."""
import hashlib
import hmac
import os
import secrets
import smtplib
import ssl
import threading
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from urllib.parse import urlsplit

import psycopg2
from flask import jsonify, request, session

_sender = ThreadPoolExecutor(max_workers=2, thread_name_prefix='recovery-mail')
_mail_slots = threading.BoundedSemaphore(16)


def configuration():
    origin = os.environ.get('PUBLIC_APP_URL', '').rstrip('/')
    url = urlsplit(origin)
    if (url.scheme != 'https' or not url.hostname or url.username or url.password
            or url.query or url.fragment or url.path not in ('', '/')):
        raise ValueError('PUBLIC_APP_URL deve ser uma origem HTTPS.')
    for key in ('SMTP_HOST', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'SMTP_FROM'):
        if not os.environ.get(key):
            raise ValueError('SMTP não configurado.')
    if os.environ.get('SMTP_SECURITY', 'starttls') not in ('starttls', 'ssl'):
        raise ValueError('SMTP exige TLS.')
    return origin


def send_email(email, token):
    origin = configuration()
    message = EmailMessage()
    message['Subject'] = 'Redefinir sua senha — Márcia Salgados'
    message['From'] = os.environ['SMTP_FROM']
    message['To'] = email
    # Fragmento não chega aos logs HTTP nem ao Referer.
    message.set_content(f'Para redefinir sua senha, abra:\n{origin}/#redefinir-senha={token}\n\n'
                        'O link expira em 20 minutos e funciona uma única vez. '
                        'Se você não solicitou, ignore este e-mail.')
    implicit = os.environ.get('SMTP_SECURITY', 'starttls') == 'ssl'
    cls = smtplib.SMTP_SSL if implicit else smtplib.SMTP
    options = {'context': ssl.create_default_context()} if implicit else {}
    with cls(os.environ['SMTP_HOST'], int(os.environ.get('SMTP_PORT', '465' if implicit else '587')),
             timeout=10, **options) as smtp:
        if not implicit:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        smtp.login(os.environ['SMTP_USERNAME'], os.environ['SMTP_PASSWORD'])
        smtp.send_message(message)


def register_recovery(app, db):
    generic = {'mensagem': 'Se houver uma conta ativa com esse e-mail, você receberá instruções. '
               'Verifique também o spam e aguarde alguns minutos antes de tentar novamente.'}

    def deliver(email, token):
        try:
            send_email(email, token)
        except (smtplib.SMTPException, OSError, ValueError):
            app.logger.error('Falha na entrega SMTP de recuperação; verifique o provedor.')
        finally:
            _mail_slots.release()

    def digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    def limited(cur, scope, value, maximum):
        key = hmac.new(app.secret_key.encode(), f'{scope}:{value}'.encode(), hashlib.sha256).hexdigest()
        cur.execute('''INSERT INTO recuperacao_limites(chave) VALUES (%s)
            ON CONFLICT(chave) DO UPDATE SET
            tentativas=CASE WHEN recuperacao_limites.inicio < NOW()-INTERVAL '15 minutes'
                THEN 1 ELSE recuperacao_limites.tentativas+1 END,
            inicio=CASE WHEN recuperacao_limites.inicio < NOW()-INTERVAL '15 minutes'
                THEN NOW() ELSE recuperacao_limites.inicio END RETURNING tentativas''', (key,))
        return cur.fetchone()[0] > maximum

    @app.after_request
    def recovery_headers(response):
        if request.path.startswith('/auth/'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.before_request
    def recovery_configured():
        if request.path in ('/auth/recuperar-senha', '/auth/redefinir-senha') and not app.secret_key:
            return db.json_error('Serviço de recuperação indisponível.', 503)

    @app.post('/auth/recuperar-senha')
    def request_reset():
        try:
            configuration()
        except ValueError:
            return db.json_error('Recuperação por e-mail indisponível. Contate o administrador.', 503)
        data = request.get_json(silent=True)
        email = data.get('email') if isinstance(data, dict) else None
        if not isinstance(email, str) or len(email) > 254 or not db.EMAIL_PATTERN.fullmatch(email.strip()):
            return db.json_error('Informe um e-mail válido.')
        email = email.strip().lower()
        conn = None
        try:
            conn = db.get_connection()
            with conn.cursor() as cur:
                ip_limit = limited(cur, 'request-ip', request.remote_addr or '', 20)
                if ip_limit:
                    conn.commit()
                    return jsonify(generic)
                account_limit = limited(cur, 'request-email', email, 3)
                conn.commit()
                if ip_limit or account_limit:
                    return jsonify(generic)
                cur.execute('SELECT id, email, versao_sessao FROM usuarios WHERE LOWER(email)=%s AND ativo FOR UPDATE', (email,))
                user = cur.fetchone()
                if user:
                    token = secrets.token_urlsafe(32)
                    cur.execute('''INSERT INTO recuperacao_senha(token_hash,usuario_id,versao_sessao,expira_em)
                        VALUES (%s,%s,%s,NOW()+INTERVAL '20 minutes')''', (digest(token), user[0], user[2]))
                conn.commit()
                # SMTP fora da resposta HTTP evita revelar contas pelo tempo do provedor.
                # Fila limitada em memória: nunca persiste tokens em claro.
                if user and _mail_slots.acquire(blocking=False):
                    try:
                        _sender.submit(deliver, user[1], token)
                    except RuntimeError:
                        _mail_slots.release()
                        app.logger.error('Fila SMTP indisponível.')
                elif user:
                    app.logger.error('Fila SMTP cheia; solicitação não entregue.')
            return jsonify(generic)
        except psycopg2.Error:
            if conn:
                conn.rollback()
            return db.json_error('Serviço temporariamente indisponível. Tente mais tarde.', 503)
        except (smtplib.SMTPException, OSError, ValueError):
            if conn:
                conn.rollback()
            app.logger.error('Falha na entrega SMTP de recuperação; verifique o provedor.')
            # Resposta igual para não revelar existência de conta durante falha do provedor.
            return jsonify(generic)
        finally:
            if conn:
                db.get_pool().putconn(conn)

    @app.post('/auth/redefinir-senha')
    def reset_password():
        data = request.get_json(silent=True)
        data = data if isinstance(data, dict) else {}
        conn = None
        try:
            conn = db.get_connection()
            with conn.cursor() as cur:
                blocked = limited(cur, 'reset-ip', request.remote_addr or '', 20)
                conn.commit()
                if blocked:
                    return db.json_error('Muitas tentativas. Aguarde 15 minutos.', 429)
                token = data.get('token')
                if not isinstance(token, str) or not 40 <= len(token) <= 128:
                    return db.json_error('Link inválido ou expirado. Solicite outro.')
                error = db.validar_senha(data.get('nova_senha'))
                if error:
                    return db.json_error(error)
                if data.get('nova_senha') != data.get('confirmacao'):
                    return db.json_error('As senhas não coincidem.')
                # Bloqueio do usuário serializa consumo de todos os seus tokens.
                cur.execute('''SELECT u.id FROM usuarios u JOIN recuperacao_senha r ON r.usuario_id=u.id
                    WHERE r.token_hash=%s FOR UPDATE OF u''', (digest(token),))
                user = cur.fetchone()
                cur.execute('''SELECT r.usuario_id FROM recuperacao_senha r JOIN usuarios u ON u.id=r.usuario_id
                    WHERE r.token_hash=%s AND r.usado_em IS NULL AND r.expira_em>NOW()
                    AND u.ativo AND r.versao_sessao=u.versao_sessao''', (digest(token),))
                if not user or not cur.fetchone():
                    conn.rollback()
                    return db.json_error('Link inválido ou expirado. Solicite outro.')
                cur.execute('''UPDATE usuarios SET senha_hash=%s, versao_sessao=versao_sessao+1,
                    tentativas_falhas=0,bloqueado_ate=NULL,atualizado_em=NOW() WHERE id=%s''',
                            (db.hash_senha(data['nova_senha']), user[0]))
                cur.execute('UPDATE recuperacao_senha SET usado_em=NOW() WHERE usuario_id=%s AND usado_em IS NULL', (user[0],))
            conn.commit()
            session.clear()
            return jsonify({'mensagem': 'Senha redefinida. Entre com sua nova senha. Todas as sessões anteriores foram encerradas.'})
        except psycopg2.Error:
            if conn:
                conn.rollback()
            return db.json_error('Não foi possível redefinir a senha. Tente mais tarde.', 503)
        finally:
            if conn:
                db.get_pool().putconn(conn)
