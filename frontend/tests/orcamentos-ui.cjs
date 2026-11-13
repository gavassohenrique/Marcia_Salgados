// Teste de interação com API simulada; transações reais são testadas no pytest.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const produtos = [{ id: 1, nome: 'PRODUTO DE TESTE', preco: '5.50', estoque: 10, estoque_minimo: 0 }];
let registro = null, confirmacoes = 0;
const server = http.createServer((req, res) => {
  const pathname = new URL(req.url, 'http://localhost').pathname;
  const file = path.join(root, pathname === '/' ? 'index.html' : pathname);
  res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : file.endsWith('.jpg') ? 'image/jpeg' : 'text/html');
  fs.createReadStream(file).on('error', () => res.end()).pipe(res);
});

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route('**/api/**', async route => {
      const req = route.request();
      const url = new URL(req.url()).pathname.replace('/api', '');
      let body = [];
      if (url === '/auth/status') body = { configurado: true, autenticado: true, csrf: 'teste', usuario: { id: 1, nome: 'OPERADOR DE TESTE', perfil: 'FUNCIONARIO' } };
      if (url === '/health') body = { status: 'ok', banco: 'conectado' };
      if (url === '/produtos') body = produtos;
      if (url === '/pedidos') {
        if (req.method() === 'POST') {
          const data = req.postDataJSON();
          registro = { ...data, id: 1, tipo: 'ORCAMENTO', status: 'ATIVO', estoque_processado: false, versao: 1, criado_em: '2026-11-13T15:00:00Z', itens: data.itens.map(i => ({ ...i, produto_nome: produtos[0].nome, preco_unitario: '5.50' })) };
          body = { pedido: registro, mensagem: 'Orçamento salvo, sem movimentar estoque.' };
        } else body = registro ? [registro] : [];
      }
      if (url === '/pedidos/1') {
        if (req.method() === 'PUT') {
          const data = req.postDataJSON();
          assert.equal(data.versao, registro.versao);
          registro = { ...registro, cliente: data.cliente, referencia: data.referencia, versao: registro.versao + 1, itens: data.itens.map(i => ({ ...i, produto_nome: produtos[0].nome, preco_unitario: '5.50' })) };
          body = { pedido: registro, mensagem: 'Orçamento atualizado, sem movimentar estoque.' };
        } else if (req.method() === 'DELETE') {
          assert.equal(req.postDataJSON().versao, registro.versao);
          registro = { ...registro, status: 'CANCELADO', versao: registro.versao + 1 };
          body = { pedido: registro, mensagem: 'Pedido cancelado; estoque devolvido.' };
        } else body = registro;
      }
      if (url === '/pedidos/1/confirmar') {
        assert.equal(req.postDataJSON().versao, registro.versao);
        assert.equal(registro.tipo, 'ORCAMENTO');
        confirmacoes++;
        registro = { ...registro, tipo: 'PEDIDO', estoque_processado: true, versao: registro.versao + 1 };
        body = { pedido: registro, mensagem: 'Pedido confirmado; saída de estoque registrada uma única vez.' };
      }
      if (url.includes('documento.')) return route.fulfill({ status: 200, contentType: 'text/plain', headers: { 'Content-Disposition': `attachment; filename="${registro.tipo === 'ORCAMENTO' ? 'orcamento' : 'pedido'}-1.txt"` }, body: 'DOCUMENTO SOMENTE TESTE' });
      await route.fulfill({ status: req.method() === 'POST' && url === '/pedidos' ? 201 : 200, contentType: 'application/json', body: JSON.stringify(body) });
    });
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.locator('#loginOverlay').waitFor({ state: 'hidden' });
    await page.locator('#pedidoCliente').fill('CLIENTE DE TESTE');
    await page.locator('.order-product').selectOption('1');
    await page.locator('.order-quantity').fill('2');
    await page.getByRole('button', { name: 'Salvar orçamento', exact: true }).click();
    await page.getByRole('button', { name: 'Confirmar e gerar pedido' }).waitFor();
    assert.equal(confirmacoes, 0);
    assert.equal(registro.tipo, 'ORCAMENTO');
    assert.match(await page.locator('#pedidosLista').innerText(), /AGUARDANDO CONFIRMAÇÃO/);
    await page.getByRole('button', { name: 'Editar', exact: true }).click();
    await page.getByRole('button', { name: 'Salvar alterações: orçamento #1' }).waitFor();
    await page.locator('.order-quantity').fill('3');
    await page.getByRole('button', { name: 'Salvar alterações: orçamento #1' }).click();
    await page.waitForFunction(() => document.getElementById('pedidoMensagem').textContent.includes('atualizado'));
    assert.equal(confirmacoes, 0);
    assert.equal(registro.itens[0].quantidade, 3);
    fs.mkdirSync('work/ui-screenshots', { recursive: true });
    for (const [width, height] of [[1920, 1080], [768, 1024], [390, 844]]) {
      await page.setViewportSize({ width, height });
      await page.locator('#pedidosLista').scrollIntoViewIfNeeded();
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `overflow ${width}`);
      await page.screenshot({ path: `work/ui-screenshots/orcamento-${width}.png` });
    }
    const download = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Baixar TXT' }).click();
    assert.equal((await download).suggestedFilename(), 'orcamento-1.txt');
    page.once('dialog', d => d.dismiss());
    await page.getByRole('button', { name: 'Confirmar e gerar pedido' }).click();
    assert.equal(confirmacoes, 0);
    page.once('dialog', d => d.accept());
    await page.getByRole('button', { name: 'Confirmar e gerar pedido' }).click();
    await page.waitForFunction(() => document.getElementById('pedidosLista').textContent.includes('CONFIRMADO'));
    assert.equal(confirmacoes, 1);
    assert.equal(await page.getByRole('button', { name: 'Confirmar e gerar pedido' }).count(), 0);
    await page.locator('#pedidosLista').scrollIntoViewIfNeeded();
    await page.screenshot({ path: 'work/ui-screenshots/pedido-confirmado-390.png' });
    page.once('dialog', d => d.accept());
    await page.getByRole('button', { name: 'Cancelar pedido', exact: true }).click();
    await page.locator('.order-cancelled').waitFor();
    assert.equal(await page.getByRole('button', { name: 'Editar', exact: true }).count(), 0);
    assert.deepEqual(errors, []);
    console.log('Interface OK: orçamento, edição sem confirmar, TXT, confirmação explícita, cancelamento e 3 larguras.');
  } finally {
    await browser.close();
    server.close();
  }
})().catch(error => { console.error(error); server.close(); process.exitCode = 1; });
