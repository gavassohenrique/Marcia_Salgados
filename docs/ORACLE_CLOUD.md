# Hospedar Marcia Salgados na Oracle Cloud Always Free

Este documento é um roteiro para uma **implantação de estudo** em VM Ubuntu ARM64 na Oracle Cloud. A execução local continua usando `docker-compose.yaml`, sem alterações. Na VM use **somente `compose.oracle.yaml`**.

> **Aviso de custo e confiabilidade:** escolha explicitamente recursos "Always Free-eligible", mantenha-se dentro das cotas e **não faça upgrade automático para Pay As You Go**. Capacidade gratuita pode estar indisponível; instâncias inativas podem ser recuperadas pela Oracle. Tenha um backup fora da VM. O plano não garante disponibilidade 24x7.

## 1. Abrir conta e criar VM Ubuntu

1. Acesse https://signup.oraclecloud.com/ e preencha seus dados **somente no site oficial**. Verificação de cartão pode exigir uma autorização temporária; não compartilhe dados de pagamento.
2. Selecione a **Home Region** com cuidado. Computação Always Free é criada na região principal. Compare a proximidade ao Brasil e a disponibilidade; a região principal não deve ser escolhida por tentativa.
3. Na console: **Compute → Instances → Create instance**.
4. Nome sugerido: `marcia-salgados`. Em **Image and shape**, escolha **Ubuntu 24.04 LTS ARM64** e **VM.Standard.A1.Flex** marcada Always Free-eligible, com até **2 OCPUs e 12 GB de RAM** totais (para uma VM, 2/12). Se indisponível, **não selecione uma shape paga** sem verificar custos. O disco inicial de aproximadamente 50 GB entra na cota gratuita de 200 GB.
5. Em networking, use VCN com sub-rede pública e **IPv4 público**; o servidor precisa receber conexões HTTPS.
6. Para SSH, gere uma chave no seu Windows PowerShell e cole **apenas a chave pública** no cadastro da VM:
   ```powershell
   ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\oracle-marcia" -C "marcia-salgados"
   Get-Content "$env:USERPROFILE\.ssh\oracle-marcia.pub"
   ```
   Guarde o arquivo `oracle-marcia` (sem `.pub`) em local seguro. Nunca envie a chave privada para ninguém nem para o GitHub.

Na VCN (Security List ou Network Security Group associado à VM), permita **ingress TCP 80 e TCP 443 a partir de 0.0.0.0/0**. Permita **TCP 22 somente do seu IP público (/32)** quando possível. **Não abra TCP 3000 ou 5432**. Firewalls no Ubuntu são uma segunda camada: se portas 80/443 não responderem, examine também `sudo iptables -S` e regras UFW, **sem apagar regras existentes**.

## 2. Conectar do Windows via SSH

Copie o IPv4 público da VM na console. No PowerShell do seu Windows:

```powershell
ssh -i "$env:USERPROFILE\.ssh\oracle-marcia" ubuntu@SEU_IP_PUBLICO
```

O próximo conjunto de comandos é executado **dentro da VM Ubuntu** (não no PowerShell Windows).

## 3. Instalar Docker Engine e Git na VM

Conforme https://docs.docker.com/engine/install/ubuntu/ :

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker compose version
```

Use `sudo docker` em vez de colocar o usuário no grupo `docker` (esse grupo dá acesso equivalente a root).

## 4. Baixar repositório e criar .env

```bash
git clone https://github.com/gavassohenrique/Marcia_Salgados.git
cd Marcia_Salgados
umask 077
cp .env.example .env
nano .env
```

Exemplo sem segredos reais:

```dotenv
POSTGRES_USER=user
POSTGRES_DB=appdb
POSTGRES_PASSWORD=ESCOLHA_SENHA_FORTE_E_UNICA_DO_BANCO
FLASK_SECRET_KEY=COLE_CHAVE_GERADA_ALEATORIAMENTE
PUBLIC_DOMAIN=SEU_IPV4_COM_HIFENS.sslip.io
```

- Gere o segredo Flask com `openssl rand -hex 32` e cole os 64 caracteres no `.env`.
- Crie uma senha separada e longa para `POSTGRES_PASSWORD`. **A senha do login do painel não fica aqui.**
- Para um endereço gratuito sem comprar domínio, se o IP da VM fosse `203.0.113.10` (exemplo **não utilizável**), `PUBLIC_DOMAIN` seria `203-0-113-10.sslip.io`. Troque pelo seu **IP público verdadeiro**. O sslip.io resolve DNS automaticamente a partir do IP no nome. Um domínio `*.duckdns.org` seu também funciona se apontar para o IPv4 público.
- Não escreva `https://` em `PUBLIC_DOMAIN`: use apenas o nome.
- Certifique-se de que 80 e 443 estejam acessíveis da Internet antes de esperar que Caddy emita o certificado.

```bash
chmod 600 .env
sudo docker compose -f compose.oracle.yaml config --quiet
```

**Atenção:** `docker compose config` *sem* `--quiet` pode imprimir suas senhas no terminal. Não envie esse resultado nem capturas contendo segredos.

## 5. Subir serviços com HTTPS

```bash
sudo docker compose -f compose.oracle.yaml up -d --build
sudo docker compose -f compose.oracle.yaml ps
sudo docker compose -f compose.oracle.yaml logs --tail=80 caddy
sudo docker compose -f compose.oracle.yaml logs --tail=80 backend
```

Diferenças da configuração local:

- Caddy abre somente as portas **80 e 443** e cria/renova HTTPS automaticamente.
- Nginx, Flask/Gunicorn e PostgreSQL não publicam portas diretamente na VM.
- O backend roda sob **Gunicorn**; antes de iniciar, verifica segredos e executa migrações **aditivas** do schema.
- `COOKIE_SECURE=true` impede envio de cookies de sessão via HTTP.

Acesse **https://SEU_DOMINIO/** e **https://SEU_DOMINIO/api/health**. O resultado do health deve incluir `"status":"ok"` e `"banco":"conectado"`.

Se der erro de certificado, verifique DNS e abertura das portas 80 e 443 no OCI **e** na VM. Nunca aceite certificado inválido para digitar senha.

## 6. Criar o primeiro administrador

Depois que o backend estiver saudável:

```bash
sudo docker compose -f compose.oracle.yaml exec backend python manage.py criar-admin
```

Informe seu nome, e-mail e **uma senha inédita** com pelo menos 8 caracteres, letra maiúscula, minúscula e símbolo especial (recomendamos 16 ou mais). A senha não aparece durante a digitação e o banco armazena apenas hash Argon2id. Se usuários já existirem, **não apague o banco**: o comando impede recriar o primeiro admin.

## 7. Atualizar, verificar e fazer backup

Para atualizar o código e recriar containers:

```bash
cd ~/Marcia_Salgados
git pull --ff-only origin main
sudo docker compose -f compose.oracle.yaml up -d --build
sudo docker compose -f compose.oracle.yaml ps
```

Um backup do banco para arquivo no próprio servidor (copie depois para outro lugar seguro):

```bash
umask 077
sudo docker compose -f compose.oracle.yaml exec -T postgres sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "marcia-$(date +%Y%m%d-%H%M).dump"
```

Depois copie esse backup para fora da VM de maneira segura e teste restauração em **banco separado**. Uma cópia no mesmo disco **não é backup suficiente**. As permissões de `/var/run/docker.sock` e o acesso SSH também são críticos.

**Nunca use** `docker compose down -v` — isso remove volumes e pode apagar dados.

## 8. Limites e responsabilidades

Esta configuração é uma **base de deploy**, não comprovação de produção validada na Oracle. Antes de armazenar dados reais da empresa, faça testes com a VM, configure backups automáticos fora dela, monitoramento, correções de segurança e endurecimento de autenticação e infraestrutura. O Always Free não garante continuidade 24/7.

Referências oficiais:
- Oracle Always Free: https://docs.oracle.com/pt-br/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- Criar VM: https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/launchinginstance.htm
- Docker Ubuntu: https://docs.docker.com/engine/install/ubuntu/
- Caddy HTTPS: https://caddyserver.com/docs/automatic-https
- DNS gratuito sslip.io: https://sslip.io/
