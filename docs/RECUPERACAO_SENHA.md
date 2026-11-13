# Recuperação segura de conta

Configure no `.env` ignorado pelo Git ou no gerenciador de segredos do servidor:

- `PUBLIC_APP_URL`: origem HTTPS real, por exemplo `https://estoque.seudominio.com`.
- `SMTP_HOST`, `SMTP_PORT`: servidor do provedor; normalmente 587 com `SMTP_SECURITY=starttls`, ou 465 com `SMTP_SECURITY=ssl`.
- `SMTP_USERNAME`, `SMTP_PASSWORD`: credencial exclusiva de envio ou senha de aplicativo, nunca a senha pessoal do usuário. Não cole em issues, commits, logs ou imagens Docker.
- `SMTP_FROM`: remetente autorizado no provedor.

Valide domínio/remetente e configure SPF, DKIM e DMARC conforme o provedor. Use privilégio mínimo, rotação de credenciais e restrinja a leitura do `.env`. Nunca desative validação de certificado TLS. Recrie o backend após alterar ambiente. Ambos os arquivos Compose repassam essas variáveis. Em Kubernetes, forneça as credenciais por Secret externo; não versione um Secret preenchido.

A recuperação fica indisponível com erro 503 enquanto a configuração estiver incompleta. Falhas de entrega são registradas sem endereço, token ou segredo; a mensagem pública é condicional e uniforme e não garante entrega. Monitore erros SMTP e a atividade no painel do provedor. Verifique entrega real com uma conta de teste antes de liberar o recurso; os testes automatizados não comprovam entrega em uma caixa postal externa.

O link usa somente a origem configurada, nunca o cabeçalho Host. Exige HTTPS público e abre a tela de redefinição pelo fragmento, removido imediatamente da barra de endereço. Não registra o token no servidor web. Evite ferramentas de analytics que capturem URLs/campos de senha. Não publique o serviço por HTTP; mantenha COOKIE_SECURE=true no servidor público.

A migração `003_recuperacao_senha.sql` é aditiva, idempotente e executada por `preparar_banco()`. Não remova volumes nem recrie o banco. Faça backup antes da atualização. Mantém dados e sessões existentes até sua invalidação normal. Tokens duram 20 minutos, são armazenados apenas como SHA-256 e consumidos em transação com bloqueio do usuário. Redefinir invalida todos os links anteriores e todas as sessões. Trocas administrativas ou alteração normal da senha também invalidam links pela versão de sessão.

Limites compartilhados entre workers: até 3 solicitações por endereço e 20 por origem de rede em janela de 15 minutos; redefinição permite 20 tentativas por origem. Chaves de limite são HMAC, sem e-mail/IP em claro. A aplicação usa o endereço direto da conexão: atrás do Nginx o limite por origem é conservador e compartilhado por todos os clientes. Não confie em X-Forwarded-For enviado pelo público. Para limites individuais de IP, configure no proxy de borda confiável; não ative ProxyFix indiscriminadamente. O limite por e-mail continua individual e compartilhado.

Manutenção periódica recomendada, com SQL parametrizado operacional: remover tokens expirados há mais de um dia e limites com `inicio < NOW() - INTERVAL '1 day'`. Nenhuma tabela de negócio é removida. Retenção precisa ser ajustada à operação.

O envio real ocorre fora da resposta HTTP, em fila limitada em memória (2 envios simultâneos, 16 pendentes por processo), evitando que a latência SMTP revele se uma conta existe. Não há promessa de entrega: reiniciar o worker pode perder e-mails pendentes; o usuário pode solicitar novamente após a janela de limite. Para operações que exijam garantia de entrega, substituir por fila durável com proteção criptográfica dos tokens e gestão de chaves. A fila nunca grava o token em claro em disco. Falhas e saturação geram alertas no log, sem dados sensíveis.

## Verificação desta implementação

Em 13/11/2026: 66 testes Flask/PostgreSQL 15 em banco descartável e 9 testes de frontend passaram; sintaxe JavaScript e ambos os arquivos Compose foram validados. Incluem concorrência/uso único, expiração, versão de sessão, política e confirmação de senha, limite compartilhado e sequência SMTP com TLS em adaptador de teste. Integra as correções de `audit/correcoes-2026-11-13` (`4e3ff8b`) e as mudanças anteriores de pedidos/responsividade.

A política do navegador bloqueou a prévia de arquivo local: a revisão visual em larguras de celular e desktop permanece pendente. Os testes de frontend exercitam handlers e atributos, não o layout de um navegador real. Entrega externa SMTP não foi validada por falta de credenciais/domínio; não houve envio real para caixa postal externa nem acesso à base de produção.
