// Exercita os handlers reais, incluindo a expiração de Event.currentTarget
// ao sair do despacho síncrono do evento no navegador.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');

function pagina() {
  const elements = new Map();
  class Element {
    constructor() {
      this.value = ''; this.textContent = ''; this.hidden = false;
      this.children = []; this.handlers = {}; this.resets = 0;
      this.classList = { add() {}, remove() {} };
    }
    focus() { this.focused = true; }
    setAttribute(key, value) { this[key] = value; }
    addEventListener(type, handler) { this.handlers[type] = handler; }
    querySelector(selector) { return get(selector); }
    querySelectorAll() { return []; }
    appendChild(el) { this.children.push(el); }
    replaceChildren() { this.children = []; }
    reset() { this.resets++; }
    close() { this.closed = true; }
    showModal() { this.closed = false; }
  }
  function get(id) {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  }
  const requests = [];
  const alerts = [];
  let logoutFails = false;
  const context = vm.createContext({
    document: {
      getElementById: get, createElement: () => new Element(),
      querySelector: get, querySelectorAll: selector => {
        if (selector === '[data-password]') {
          const button = get('toggleSenha');
          button.dataset = {password: 'loginSenha'};
          get('loginSenha').type = 'password';
          return [button];
        }
        return [];
      },
    },
    FormData: class { constructor() { return Object.entries({
      nome: 'Operador teste', email: 'teste@example.test',
      senha: 'SenhaTeste!', perfil: 'FUNCIONARIO',
    }); } },
    fetch: async (url, options = {}) => {
      requests.push({ url, options });
      if (url.endsWith('/auth/logout') && logoutFails) throw new Error('offline');
      let body = { mensagem: 'Operação concluída.', usuario: { id: 2 } };
      if (url.endsWith('/health')) body = { status: 'ok' };
      if (url.endsWith('/auth/status')) body = { configurado: true, autenticado: false };
      if (url.endsWith('/usuarios') && !options.method) body = [];
      if (url.endsWith('/produtos') && !options.method) body = [];
      if (url.includes('/movimentacoes?')) body = [];
      return { status: 200, ok: true, json: async () => body, text: async () => JSON.stringify(body) };
    },
    location: {hash: "", pathname: "/", search: ""}, history: {replaceState() {}},
    console, alert: text => alerts.push(text), setTimeout,
  });
  vm.runInContext(readFileSync(join(__dirname, '../script.js'), 'utf8'), context);
  async function submit(id) {
    const event = { currentTarget: get(id), preventDefault() {} };
    const pending = get(id).handlers.submit(event);
    event.currentTarget = null;
    await pending;
  }
  return { get, submit, requests, alerts, context, failLogout() { logoutFails = true; } };
}

test('cadastro confirmado limpa formulário e atualiza lista sem falso erro', async () => {
  const p = pagina();
  await p.submit('usuarioForm');
  assert.equal(p.get('usuarioForm').resets, 1);
  assert.match(p.get('usuarioMensagem').textContent, /Usuário criado/);
  assert.equal(p.get('button[type="submit"]').disabled, false);
});

test('troca da própria senha conclui após aguardar API', async () => {
  const p = pagina();
  p.get('senhaAtual').value = 'AnteriorTeste!';
  p.get('senhaNova').value = p.get('senhaConfirmacao').value = 'NovaSenhaTeste!';
  await p.submit('alterarSenhaForm');
  assert.equal(p.get('alterarSenhaForm').resets, 1);
  assert.equal(p.get('alterarSenhaDialog').closed, true);
  assert.deepEqual(p.alerts, ['Operação concluída.']);
  assert.equal(p.get('alterarSenhaMensagem').textContent, '');
});

test('redefinição da própria senha volta ao login após resposta', async () => {
  const p = pagina();
  vm.runInContext('aplicarPerfil({id: 2, nome: "Teste", perfil: "ADMIN"}); resetUsuarioId = 2;', p.context);
  p.get('resetSenha').value = 'NovaSenhaTeste!';
  await p.submit('resetSenhaForm');
  assert.equal(p.get('resetSenhaForm').resets, 1);
  assert.equal(p.get('resetSenhaDialog').closed, true);
  assert.equal(p.get('loginOverlay').hidden, false);
  assert.match(p.get('loginMensagem').textContent, /nova senha/);
});

test('falha de rede no logout não anuncia encerramento inexistente', async () => {
  const p = pagina();
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext('ocultarLogin();', p.context);
  p.failLogout();
  await p.get('sairBtn').handlers.click();
  assert.equal(p.get('loginOverlay').hidden, true);
  assert.match(p.alerts[0], /Não foi possível encerrar/);
});

test('cadastro de produto atualiza também o histórico de entrada inicial', async () => {
  const p = pagina();
  p.get('nome').value = 'Produto teste';
  p.get('preco').value = '6,50';
  p.get('estoque').value = '20';
  p.get('estoque_minimo').value = '5';
  await p.submit('produtoForm');
  assert.equal(p.get('produtoForm').resets, 1);
  assert.match(p.get('mensagem').textContent, /Produto cadastrado com sucesso/);
  assert.ok(p.requests.some(r => r.url.includes('/movimentacoes?')));
});

test('filtro disponível inclui saldo positivo abaixo do mínimo e exclui saldo zero', () => {
  const p = pagina();
  p.get('filtroEstoque').value = 'disponivel';
  vm.runInContext(`produtosCache = [
    {id:1,nome:'Baixo',preco:5,estoque:2,estoque_minimo:5},
    {id:2,nome:'Normal',preco:5,estoque:10,estoque_minimo:5},
    {id:3,nome:'Zerado',preco:5,estoque:0,estoque_minimo:0}
  ]; renderizarProdutos();`, p.context);
  assert.equal(p.get('lista').children.length, 2);
  assert.equal(p.get('status').textContent, '2 de 3 produto(s)');
});

test('mostrar senha alterna tipo e rótulo acessível sem enviar o login', () => {
  const p = pagina();
  p.get('loginSenha').value = 'SenhaTeste!';
  const before = p.requests.filter(r => r.url.endsWith('/auth/login')).length;
  p.get('toggleSenha').handlers.click();
  assert.equal(p.get('loginSenha').type, 'text');
  assert.equal(p.get('toggleSenha')['aria-label'], 'Ocultar senha');
  assert.equal(p.get('toggleSenha')['aria-pressed'], 'true');
  p.get('toggleSenha').handlers.click();
  assert.equal(p.get('loginSenha').type, 'password');
  assert.equal(p.get('loginSenha').value, 'SenhaTeste!');
  assert.equal(p.requests.filter(r => r.url.endsWith('/auth/login')).length, before);
});

test('solicitação por e-mail usa formulário público e mostra confirmação', async () => {
  const p = pagina();
  p.get('recuperarEmail').value = 'teste@example.com';
  await p.submit('recuperarForm');
  const r = p.requests.find(r => r.url.endsWith('/auth/recuperar-senha'));
  assert.deepEqual(JSON.parse(r.options.body), {email:'teste@example.com'});
  assert.equal(p.get('recuperarMensagem').textContent, 'Operação concluída.');
});

test('confirmação divergente impede envio da nova senha', async () => {
  const p = pagina();
  p.get('novaSenhaRecuperacao').value = 'SenhaNova!';
  p.get('confirmarSenhaRecuperacao').value = 'OutraSenha!';
  await p.submit('redefinirForm');
  assert.equal(p.requests.some(r => r.url.endsWith('/auth/redefinir-senha')), false);
  assert.equal(p.get('confirmarSenhaRecuperacao').focused, true);
});
