"""Gerenciamento local do primeiro administrador. Não grava senhas em arquivos."""
import argparse
import getpass
from app import DB_CONFIG, hash_senha, preparar_banco, validar_usuario, validar_configuracao
import psycopg2


def criar_primeiro_admin():
    validar_configuracao()
    preparar_banco()
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM usuarios")
            if cur.fetchone()[0] != 0:
                raise SystemExit("Já existem usuários. Cadastre outros pelo painel com acesso de administrador.")
            print("Criação do primeiro administrador (senha não aparece no terminal).")
            nome = input("Nome: ").strip()
            email = input("E-mail: ").strip().lower()
            senha = getpass.getpass("Senha (mín. 8 caracteres, maiúscula, minúscula e símbolo): ")
            confirmacao = getpass.getpass("Repita a senha: ")
            if senha != confirmacao:
                raise SystemExit("As senhas não coincidem; nada foi gravado.")
            data = {"nome": nome, "email": email, "senha": senha, "perfil": "ADMIN"}
            erro = validar_usuario(data)
            if erro:
                raise SystemExit(erro)
            cur.execute("""INSERT INTO usuarios (nome,email,senha_hash,perfil)
                           VALUES (%s,%s,%s,'ADMIN')""", (nome,email,hash_senha(senha)))
    print("Administrador cadastrado. Abra http://localhost:8080 e entre com seu e-mail.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Configuração local do sistema")
    parser.add_argument("comando", choices=["criar-admin"])
    args = parser.parse_args()
    if args.comando == "criar-admin":
        criar_primeiro_admin()
