const API = "/api";
const lista = document.getElementById("lista");
const statusElement = document.getElementById("status");
const form = document.getElementById("produtoForm");
const mensagem = document.getElementById("mensagem");
const buscaProduto = document.getElementById("buscaProduto");
const filtroEstoque = document.getElementById("filtroEstoque");
const editarDialog = document.getElementById("editarDialog");
const loginOverlay = document.getElementById("loginOverlay");
let csrfToken = "";
let usuarioAtual = null;
let resetUsuarioId = null;
let produtosCache = [];
let pedidosCache = [];
let historicoCache = [];
let editandoId = null;
let offsetHistorico = 0;
let carregandoHistorico = false;

function escapar(texto) {
  const div = document.createElement("div");
  div.textContent = String(texto ?? "");
  return div.innerHTML;
}

function formatarMoeda(valor) {
  return Number(valor).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function normalizarPreco(valor) {
  const texto = String(valor ?? "").trim().replace(/\s/g, "").replace(/R\$/i, "");
  if (!texto) return NaN;
  if (texto.includes(",") && texto.includes(".")) return Number(texto.replace(/\./g, "").replace(",", "."));
  return Number(texto.replace(",", "."));
}

function formatarData(valor) {
  const data = new Date(valor);
  if (!valor || Number.isNaN(data.getTime())) return "Data não informada";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit"
  }).format(data);
}

function mostrarLogin(mensagemErro = "") {
  loginOverlay.hidden = false;
  document.getElementById("sairBtn").hidden = true;
  document.getElementById("alterarSenhaBtn").hidden = true;
  document.getElementById("usuarioAtual").hidden = true;
  document.getElementById("loginMensagem").textContent = mensagemErro;
}
function ocultarLogin() {
  loginOverlay.hidden = true;
  document.getElementById("sairBtn").hidden = false;
  document.getElementById("alterarSenhaBtn").hidden = false;
  document.getElementById("loginMensagem").textContent = "";
}

function aplicarPerfil(usuario) {
  usuarioAtual = usuario;
  const administrador = usuario?.perfil === "ADMIN";
  document.querySelectorAll(".admin-only").forEach(el => { el.hidden = !administrador; });
  document.getElementById("usuariosNav").hidden = !administrador;
  document.getElementById("usuarios").hidden = !administrador;
  const texto = document.getElementById("usuarioAtual");
  texto.textContent = usuario ? `${usuario.nome} · ${administrador ? "Administrador" : "Funcionário"}` : "";
  texto.hidden = !usuario;
  if (!administrador) {
    document.getElementById("usuariosLista").textContent = "";
  }
}

async function apiFetch(caminho, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body) headers["Content-Type"] = "application/json";
  if (options.method && options.method.toUpperCase() !== "GET") headers["X-CSRF-Token"] = csrfToken;
  const response = await fetch(`${API}${caminho}`, { ...options, headers, credentials: "same-origin" });
  if (response.status === 401) mostrarLogin("Sua sessão expirou. Entre novamente.");
  return response;
}

async function obterJson(response) {
  const corpo = await response.text();
  let resultado;
  try { resultado = JSON.parse(corpo); }
  catch {
    const detalhe = response.status === 403 ? "Acesso bloqueado pelo servidor/proxy" : "Resposta inválida da API";
    throw new Error(`${detalhe} (HTTP ${response.status}). Acesse pelo Docker em http://localhost:8080, não pelo Live Server.`);
  }
  if (!response.ok) throw new Error(resultado?.erro || `Falha na solicitação (HTTP ${response.status}).`);
  return resultado;
}

function bloquearBotao(botao, bloqueado) {
  if (botao) botao.disabled = bloqueado;
}

async function verificarSaude() {
  const el = document.getElementById("systemStatus");
  const texto = document.getElementById("systemStatusText");
  try {
    const response = await fetch(`${API}/health`, { cache: "no-store" });
    const resultado = await response.json();
    if (!response.ok || resultado.status !== "ok") throw new Error();
    el.classList.remove("offline");
    texto.textContent = "Sistema ativo";
  } catch {
    el.classList.add("offline");
    texto.textContent = "Sistema indisponível";
  }
}

async function inicializar() {
  await verificarSaude();
  try {
    const response = await fetch(`${API}/auth/status`, { cache: "no-store" });
    const estado = await obterJson(response);
    if (!estado.configurado) {
      mostrarLogin("Configure FLASK_SECRET_KEY no arquivo .env antes de iniciar.");
    } else if (estado.primeiro_acesso) {
      mostrarLogin("Ainda não existe administrador. No PowerShell, execute: docker compose exec backend python manage.py criar-admin");
    } else if (estado.autenticado) {
      csrfToken = estado.csrf;
      aplicarPerfil(estado.usuario);
      ocultarLogin();
      await atualizarDados();
    } else {
      mostrarLogin();
    }
  } catch (error) {
    mostrarLogin(error.message || "Não foi possível consultar o servidor. Verifique os containers.");
  }
}

async function atualizarDados() {
  await Promise.all([carregarProdutos(), carregarPedidos(), carregarHistorico(true),
    usuarioAtual?.perfil === "ADMIN" ? carregarUsuarios() : Promise.resolve()]);
  await verificarSaude();
}

document.getElementById("loginForm").addEventListener("submit", async event => {
  event.preventDefault();
  const botao = event.currentTarget.querySelector("button[type=submit]");
  bloquearBotao(botao, true);
  try {
    const response = await fetch(`${API}/auth/login`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ email: document.getElementById("loginEmail").value.trim(),
                             senha: document.getElementById("loginSenha").value })
    });
    const resultado = await obterJson(response);
    csrfToken = resultado.csrf;
    aplicarPerfil(resultado.usuario);
    document.getElementById("loginSenha").value = "";
    ocultarLogin();
    await atualizarDados();
  } catch (error) {
    document.getElementById("loginMensagem").textContent = error.message;
  } finally { bloquearBotao(botao, false); }
});

document.getElementById("sairBtn").addEventListener("click", async () => {
  try { await apiFetch("/auth/logout", { method: "POST" }); } catch { /* sessão local também termina */ }
  csrfToken = "";
  aplicarPerfil(null);
  produtosCache = [];
  pedidosCache = [];
  historicoCache = [];
  lista.innerHTML = "";
  document.getElementById("historicoLista").textContent = "";
  document.getElementById("pedidosLista").textContent = "";
  mostrarLogin();
});

async function carregarProdutos() {
  try {
    const produtos = await obterJson(await apiFetch("/produtos"));
    produtosCache = produtos;
    renderizarProdutos();
  } catch (error) {
    console.error(error);
    statusElement.textContent = "Não foi possível conectar com o backend.";
    lista.innerHTML = '<div class="empty-state"><strong>Não foi possível carregar os produtos.</strong><p>Confira os serviços e tente novamente.</p><button class="button outline" type="button" id="tentarNovamente">Tentar novamente</button></div>';
    document.getElementById("tentarNovamente")?.addEventListener("click", carregarProdutos);
  }
}

function renderizarProdutos() {
  lista.innerHTML = "";
  document.getElementById("totalProdutos").textContent = produtosCache.length;
  document.getElementById("estoqueTotal").textContent = produtosCache.reduce((soma, item) => soma + Number(item.estoque), 0);
  document.getElementById("estoqueBaixo").textContent = produtosCache.filter(item => item.estoque <= item.estoque_minimo).length;

  const termo = (buscaProduto?.value || "").trim().toLocaleLowerCase("pt-BR");
  const filtro = filtroEstoque?.value || "todos";
  const filtrados = produtosCache.filter(item => {
    const baixo = Number(item.estoque) <= Number(item.estoque_minimo);
    return item.nome.toLocaleLowerCase("pt-BR").includes(termo) &&
      (filtro === "todos" || (filtro === "baixo" && baixo) || (filtro === "disponivel" && !baixo));
  });
  statusElement.textContent = `${filtrados.length} de ${produtosCache.length} produto(s)`;
  if (!filtrados.length) {
    lista.innerHTML = `<div class="empty-state compact"><strong>${produtosCache.length ? "Nenhum produto encontrado" : "Seu catálogo está vazio"}</strong><p>${produtosCache.length ? "Altere a busca ou o filtro." : "Cadastre o primeiro produto para começar."}</p></div>`;
    return;
  }

  filtrados.forEach(produto => {
    const baixo = Number(produto.estoque) <= Number(produto.estoque_minimo);
    const card = document.createElement("article");
    card.className = "product";
    card.innerHTML = `
      <div class="product-content">
        <div class="product-topline"><h3>${escapar(produto.nome)}</h3><span class="stock-badge ${baixo ? "low" : ""}">${baixo ? "Estoque baixo" : "Disponível"}</span></div>
        <div class="price">${formatarMoeda(produto.preco)}</div>
        ${usuarioAtual?.perfil === "ADMIN" ? '<button class="button outline edit-product" type="button">Editar produto</button>' : ""}
        <div class="stock-info"><div><span>Em estoque</span><strong>${produto.estoque}</strong></div><div><span>Mínimo</span><strong>${produto.estoque_minimo}</strong></div></div>
      </div>
      <form class="movement-form">
        <label>Movimentar estoque</label>
        <div class="movement-grid"><select name="tipo" aria-label="Tipo de movimentação"><option value="ENTRADA">Entrada</option><option value="SAIDA">Saída</option></select><input name="quantidade" type="number" min="1" step="1" value="1" required aria-label="Quantidade"></div>
        <input name="motivo" maxlength="200" placeholder="Motivo: venda, produção..." aria-label="Motivo da movimentação">
        <select name="pedido_id" class="order-select" aria-label="Pedido vinculado" disabled><option value="">Sem pedido vinculado</option>${pedidosCache.map(p => `<option value="${p.id}">#${p.id} — ${escapar(p.cliente)}</option>`).join("")}</select>
        <button class="button primary" type="submit">Confirmar movimentação</button><p class="movement-message" aria-live="polite"></p>
      </form>`;
    card.querySelector(".edit-product")?.addEventListener("click", () => abrirEdicao(produto));
    const movement = card.querySelector(".movement-form");
    const tipo = movement.querySelector('[name="tipo"]');
    const pedido = movement.querySelector('[name="pedido_id"]');
    tipo.addEventListener("change", () => { pedido.disabled = tipo.value !== "SAIDA"; });
    movement.addEventListener("submit", event => { event.preventDefault(); movimentarEstoque(produto.id, movement); });
    lista.appendChild(card);
  });
}

async function movimentarEstoque(produtoId, formulario) {
  const retorno = formulario.querySelector(".movement-message");
  const botao = formulario.querySelector("button[type=submit]");
  const dados = Object.fromEntries(new FormData(formulario));
  dados.produto_id = produtoId;
  dados.quantidade = Number(dados.quantidade);
  if (!Number.isInteger(dados.quantidade) || dados.quantidade <= 0) {
    retorno.textContent = "Informe uma quantidade inteira maior que zero.";
    retorno.className = "movement-message error";
    return;
  }
  if (!dados.pedido_id) delete dados.pedido_id;
  bloquearBotao(botao, true);
  try {
    const resultado = await obterJson(await apiFetch("/estoque/movimentacao", { method: "POST", body: JSON.stringify(dados) }));
    retorno.textContent = `Movimentação concluída. Novo estoque: ${resultado.estoque_atual}.`;
    retorno.className = "movement-message success";
    formulario.reset();
    await Promise.all([carregarProdutos(), carregarHistorico(true)]);
  } catch (error) {
    retorno.textContent = error.message;
    retorno.className = "movement-message error";
  } finally { bloquearBotao(botao, false); }
}

function abrirEdicao(produto) {
  editandoId = produto.id;
  document.getElementById("editarNome").value = produto.nome;
  document.getElementById("editarPreco").value = String(produto.preco).replace(".", ",");
  document.getElementById("editarMinimo").value = produto.estoque_minimo;
  document.getElementById("editarMensagem").textContent = "";
  editarDialog.showModal();
}
document.getElementById("fecharEdicao").addEventListener("click", () => editarDialog.close());
document.getElementById("cancelarEdicao").addEventListener("click", () => editarDialog.close());
document.getElementById("editarForm").addEventListener("submit", async event => {
  event.preventDefault();
  const nome = document.getElementById("editarNome").value.trim();
  const preco = normalizarPreco(document.getElementById("editarPreco").value);
  const estoque_minimo = Number(document.getElementById("editarMinimo").value);
  const erro = document.getElementById("editarMensagem");
  if (!nome || !(preco > 0) || !Number.isFinite(preco) || !Number.isInteger(estoque_minimo) || estoque_minimo < 0) {
    erro.textContent = "Confira nome, preço positivo e estoque mínimo inteiro.";
    return;
  }
  const botao = event.currentTarget.querySelector('button[type="submit"]');
  bloquearBotao(botao, true);
  try {
    await obterJson(await apiFetch(`/produtos/${editandoId}`, { method: "PUT", body: JSON.stringify({ nome, preco, estoque_minimo }) }));
    editarDialog.close();
    await carregarProdutos();
  } catch (e) { erro.textContent = e.message; }
  finally { bloquearBotao(botao, false); }
});

form.addEventListener("submit", async event => {
  event.preventDefault();
  const dados = {
    nome: document.getElementById("nome").value.trim(),
    preco: normalizarPreco(document.getElementById("preco").value),
    estoque: Number(document.getElementById("estoque").value),
    estoque_minimo: Number(document.getElementById("estoque_minimo").value)
  };
  if (!dados.nome || !Number.isFinite(dados.preco) || dados.preco <= 0 ||
      !Number.isInteger(dados.estoque) || dados.estoque < 0 ||
      !Number.isInteger(dados.estoque_minimo) || dados.estoque_minimo < 0) {
    mensagem.textContent = "Confira os campos: nome obrigatório, preço positivo e estoques inteiros não negativos.";
    mensagem.className = "error";
    return;
  }
  const botao = form.querySelector('button[type="submit"]');
  bloquearBotao(botao, true);
  try {
    await obterJson(await apiFetch("/produtos", { method: "POST", body: JSON.stringify(dados) }));
    mensagem.textContent = "Produto cadastrado com sucesso!";
    mensagem.className = "success";
    form.reset();
    await carregarProdutos();
  } catch (error) {
    mensagem.textContent = error.message;
    mensagem.className = "error";
  } finally { bloquearBotao(botao, false); }
});

async function carregarPedidos() {
  try {
    pedidosCache = await obterJson(await apiFetch("/pedidos"));
    document.getElementById("pedidosLista").innerHTML = pedidosCache.length
      ? pedidosCache.map(p => `<article class="order-item"><strong>#${p.id} — ${escapar(p.cliente)}</strong><small>${escapar(p.referencia || "Sem referência")} · ${formatarData(p.criado_em)}</small></article>`).join("")
      : '<p>Nenhum pedido registrado. Cadastre um para relacioná-lo a uma saída de estoque.</p>';
    renderizarProdutos();
  } catch {
    document.getElementById("pedidosLista").textContent = "Não foi possível carregar pedidos.";
  }
}

document.getElementById("pedidoForm").addEventListener("submit", async event => {
  event.preventDefault();
  const formPedido = event.currentTarget;
  const botao = formPedido.querySelector('button[type="submit"]');
  bloquearBotao(botao, true);
  try {
    const dados = Object.fromEntries(new FormData(formPedido));
    const resultado = await obterJson(await apiFetch("/pedidos", { method: "POST", body: JSON.stringify(dados) }));
    document.getElementById("pedidoMensagem").textContent = `Pedido #${resultado.pedido.id} cadastrado.`;
    formPedido.reset();
    await carregarPedidos();
  } catch (error) { document.getElementById("pedidoMensagem").textContent = error.message; }
  finally { bloquearBotao(botao, false); }
});

async function carregarHistorico(reiniciar = false) {
  if (carregandoHistorico) return;
  if (reiniciar) { offsetHistorico = 0; historicoCache = []; }
  carregandoHistorico = true;
  const maisBtn = document.getElementById("maisHistorico");
  bloquearBotao(maisBtn, true);
  try {
    const novos = await obterJson(await apiFetch(`/movimentacoes?limite=50&offset=${offsetHistorico}`));
    historicoCache.push(...novos);
    offsetHistorico += novos.length;
    maisBtn.hidden = novos.length < 50;
    renderizarHistorico();
  } catch (error) {
    document.getElementById("historicoLista").textContent = "Erro ao carregar histórico: " + error.message;
  } finally { carregandoHistorico = false; bloquearBotao(maisBtn, false); }
}

function renderizarHistorico() {
  const container = document.getElementById("historicoLista");
  if (!historicoCache.length) {
    container.innerHTML = '<div class="empty-state compact"><strong>Nenhuma movimentação registrada</strong><p>As entradas e saídas aparecerão aqui.</p></div>';
    return;
  }
  container.innerHTML = historicoCache.map(mov => {
    const entrada = mov.tipo === "ENTRADA";
    return `<div class="history-item">
      <div class="history-product"><span class="history-symbol" aria-hidden="true">${entrada ? "+" : "−"}</span>
      <div><strong>${escapar(mov.produto)}</strong><p>${escapar(mov.motivo || "Sem motivo informado")}</p>
      <small>${formatarData(mov.criado_em)}${mov.pedido_id ? ` · Pedido #${mov.pedido_id} ${escapar(mov.pedido_cliente || "")}` : ""}${mov.usuario_nome ? ` · Por ${escapar(mov.usuario_nome)}` : " · Registro anterior à auditoria"}</small></div></div>
      <div class="movement-summary ${entrada ? "entry" : "exit"}"><strong>${entrada ? "Entrada" : "Saída"} de ${mov.quantidade}</strong>
      <p>${mov.quantidade === 1 ? "unidade" : "unidades"}</p><small>${mov.estoque_anterior} → ${mov.estoque_posterior}</small></div></div>`;
  }).join("");
}

document.getElementById("maisHistorico").addEventListener("click", () => carregarHistorico());
document.getElementById("exportarCsv").addEventListener("click", () => {
  if (!historicoCache.length) return;
  const campos = ["id", "produto", "tipo", "quantidade", "estoque_anterior", "estoque_posterior", "motivo", "pedido_id", "usuario_nome", "criado_em"];
  const campoCsv = valor => {
    let texto = String(valor ?? "");
    // Evita execução de fórmulas ao abrir CSV em planilhas.
    if (/^[\s]*[=+\-@]/.test(texto)) texto = "'" + texto;
    return '"' + texto.replace(/"/g, '""') + '"';
  };
  const conteudo = [campos.join(";"), ...historicoCache.map(mov => campos.map(campo => campoCsv(mov[campo])).join(";"))].join("\r\n");
  const url = URL.createObjectURL(new Blob(["\uFEFF", conteudo], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url; link.download = "movimentacoes-marcia-salgados.csv";
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

buscaProduto.addEventListener("input", renderizarProdutos);
filtroEstoque.addEventListener("change", renderizarProdutos);
// Administração de usuários: controles ocultos para funcionário e autorização no servidor.
async function carregarUsuarios() {
  if (usuarioAtual?.perfil !== "ADMIN") return;
  const container = document.getElementById("usuariosLista");
  try {
    const usuarios = await obterJson(await apiFetch("/usuarios"));
    container.innerHTML = usuarios.map(u => `
      <article class="user-item">
        <div><strong>${escapar(u.nome)}</strong><small>${escapar(u.email)} · ${u.perfil === "ADMIN" ? "Administrador" : "Funcionário"} · ${u.ativo ? "Ativo" : "Inativo"}</small></div>
        <div class="user-actions">
          <button class="button outline" data-action="reset" data-id="${u.id}" type="button">Redefinir senha</button>
          <button class="button outline" data-action="perfil" data-id="${u.id}" data-perfil="${u.perfil}" type="button" ${u.id === usuarioAtual.id ? "disabled" : ""}>${u.perfil === "ADMIN" ? "Tornar funcionário" : "Tornar administrador"}</button>
          <button class="button outline" data-action="ativo" data-id="${u.id}" data-ativo="${u.ativo}" type="button" ${u.id === usuarioAtual.id ? "disabled" : ""}>${u.ativo ? "Desativar" : "Reativar"}</button>
        </div>
      </article>`).join("") || "Nenhum usuário cadastrado.";
    container.querySelectorAll("button[data-action]").forEach(btn => btn.addEventListener("click", async () => {
      const id = Number(btn.dataset.id);
      if (btn.dataset.action === "reset") {
        resetUsuarioId = id;
        document.getElementById("resetUsuarioNome").textContent = usuarios.find(u => u.id === id)?.nome || "Usuário";
        document.getElementById("resetMensagem").textContent = "";
        document.getElementById("resetSenha").value = "";
        document.getElementById("resetSenhaDialog").showModal();
        return;
      }
      const dados = btn.dataset.action === "perfil"
        ? { perfil: btn.dataset.perfil === "ADMIN" ? "FUNCIONARIO" : "ADMIN" }
        : { ativo: btn.dataset.ativo !== "true" };
      if (!confirm("Confirma a alteração de acesso deste usuário?")) return;
      bloquearBotao(btn, true);
      try {
        await obterJson(await apiFetch(`/usuarios/${id}`, { method: "PATCH", body: JSON.stringify(dados) }));
        await carregarUsuarios();
      } catch (error) { alert(error.message); bloquearBotao(btn, false); }
    }));
  } catch (error) { container.textContent = "Não foi possível carregar usuários: " + error.message; }
}

document.getElementById("usuarioForm").addEventListener("submit", async event => {
  event.preventDefault();
  const botao = event.currentTarget.querySelector('button[type="submit"]');
  const aviso = document.getElementById("usuarioMensagem");
  const dados = Object.fromEntries(new FormData(event.currentTarget));
  bloquearBotao(botao, true);
  try {
    await obterJson(await apiFetch("/usuarios", { method: "POST", body: JSON.stringify(dados) }));
    event.currentTarget.reset();
    aviso.textContent = "Usuário criado. Ele já pode entrar com seu e-mail e senha.";
    aviso.className = "success";
    await carregarUsuarios();
  } catch (error) { aviso.textContent = error.message; aviso.className = "error"; }
  finally { bloquearBotao(botao, false); }
});

document.getElementById("alterarSenhaBtn").addEventListener("click", () => {
  document.getElementById("alterarSenhaForm").reset();
  document.getElementById("alterarSenhaMensagem").textContent = "";
  document.getElementById("alterarSenhaDialog").showModal();
});
document.getElementById("fecharSenhaDialog").addEventListener("click", () => document.getElementById("alterarSenhaDialog").close());
document.getElementById("alterarSenhaForm").addEventListener("submit", async event => {
  event.preventDefault();
  const aviso = document.getElementById("alterarSenhaMensagem");
  const senha_atual = document.getElementById("senhaAtual").value;
  const nova_senha = document.getElementById("senhaNova").value;
  if (nova_senha !== document.getElementById("senhaConfirmacao").value) { aviso.textContent = "As senhas não coincidem."; return; }
  const botao = event.currentTarget.querySelector('button[type="submit"]');
  bloquearBotao(botao, true);
  try {
    const resultado = await obterJson(await apiFetch("/auth/alterar-senha", { method: "POST", body: JSON.stringify({ senha_atual, nova_senha }) }));
    document.getElementById("alterarSenhaDialog").close();
    event.currentTarget.reset();
    alert(resultado.mensagem);
  } catch (error) { aviso.textContent = error.message; }
  finally { bloquearBotao(botao, false); }
});
document.getElementById("fecharResetDialog").addEventListener("click", () => document.getElementById("resetSenhaDialog").close());
document.getElementById("resetSenhaForm").addEventListener("submit", async event => {
  event.preventDefault();
  const botao = event.currentTarget.querySelector('button[type="submit"]');
  bloquearBotao(botao, true);
  try {
    await obterJson(await apiFetch(`/usuarios/${resetUsuarioId}/redefinir-senha`, { method: "POST",
      body: JSON.stringify({ nova_senha: document.getElementById("resetSenha").value }) }));
    document.getElementById("resetSenhaDialog").close();
    event.currentTarget.reset();
    if (resetUsuarioId === usuarioAtual?.id) { aplicarPerfil(null); mostrarLogin("Entre novamente com a nova senha."); }
    else await carregarUsuarios();
  } catch (error) { document.getElementById("resetMensagem").textContent = error.message; }
  finally { bloquearBotao(botao, false); }
});

inicializar();
