const API = "/api";

const lista = document.getElementById("lista");
const statusElement = document.getElementById("status");
const form = document.getElementById("produtoForm");
const mensagem = document.getElementById("mensagem");
const buscaProduto = document.getElementById("buscaProduto");
const filtroEstoque = document.getElementById("filtroEstoque");
let produtosCache = [];

function escapar(texto) {
  const div = document.createElement("div");
  div.textContent = String(texto ?? "");
  return div.innerHTML;
}

function formatarMoeda(valor) {
  return Number(valor).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL"
  });
}

function normalizarPreco(valor) {
  const texto = String(valor ?? "").trim().replace(/\s/g, "").replace(/R\$/i, "");
  if (!texto) return NaN;
  if (texto.includes(",") && texto.includes(".")) return Number(texto.replace(/\./g, "").replace(",", "."));
  return Number(texto.replace(",", "."));
}

function formatarData(valor) {
  if (!valor) return "Data não informada";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(valor));
}

async function movimentarEstoque(produtoId, formulario) {
  const retorno = formulario.querySelector(".movement-message");
  const dados = Object.fromEntries(new FormData(formulario));
  dados.produto_id = produtoId;
  dados.quantidade = Number(dados.quantidade);

  try {
    const response = await fetch(API + "/estoque/movimentacao", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(dados)
    });
    const resultado = await response.json();
    if (!response.ok) throw new Error(resultado.erro || "Erro ao movimentar estoque");

    retorno.textContent = `Movimentação concluída. Novo estoque: ${resultado.estoque_atual}.`;
    retorno.className = "movement-message success";
    formulario.reset();
    await Promise.all([carregarProdutos(), carregarHistorico()]);
  } catch (error) {
    retorno.textContent = error.message;
    retorno.className = "movement-message error";
  }
}

async function carregarProdutos() {
  try {
    const response = await fetch(`${API}/produtos`);
    if (!response.ok) throw new Error("Erro ao consultar API");

    const produtos = await response.json();
    produtosCache = produtos;
    renderizarProdutos();
  } catch (error) {
    console.error(error);
    statusElement.textContent = "Não foi possível conectar com o backend. Verifique se os serviços estão ativos.";
    lista.innerHTML = `<div class="empty-state"><strong>Não foi possível carregar os produtos</strong><p>Confira a conexão e tente novamente.</p><button class="button outline" type="button" id="tentarNovamente">Tentar novamente</button></div>`;
    document.getElementById("tentarNovamente")?.addEventListener("click", carregarProdutos);
  }
}

function renderizarProdutos() {
    lista.innerHTML = "";
    document.getElementById("totalProdutos").textContent = produtosCache.length;

    const estoqueTotal = produtosCache.reduce((total, produto) => total + Number(produto.estoque), 0);
    const estoqueBaixo = produtosCache.filter(produto => Number(produto.estoque) <= Number(produto.estoque_minimo));

    document.getElementById("estoqueTotal").textContent = estoqueTotal;
    document.getElementById("estoqueBaixo").textContent = estoqueBaixo.length;

    if (produtosCache.length === 0) {
      statusElement.textContent = "Nenhum produto cadastrado";
      lista.innerHTML = `
        <div class="empty-state">
          <span aria-hidden="true">+</span>
          <strong>Seu catálogo está vazio</strong>
          <p>Cadastre o primeiro produto para começar a controlar o estoque.</p>
          <a href="#cadastro" class="button primary">Cadastrar produto</a>
        </div>
      `;
      return;
    }

    const termo = (buscaProduto?.value || "").trim().toLocaleLowerCase("pt-BR");
    const filtro = filtroEstoque?.value || "todos";
    const filtrados = produtosCache.filter(produto => {
      const nomeCorresponde = produto.nome.toLocaleLowerCase("pt-BR").includes(termo);
      const baixo = Number(produto.estoque) <= Number(produto.estoque_minimo);
      return nomeCorresponde && (filtro === "todos" || (filtro === "baixo" && baixo) || (filtro === "disponivel" && !baixo));
    });
    statusElement.textContent = `${filtrados.length} de ${produtosCache.length} produto(s)`;
    if (filtrados.length === 0) {
      lista.innerHTML = `<div class="empty-state compact"><strong>Nenhum produto encontrado</strong><p>Altere a busca ou o filtro selecionado.</p></div>`;
      return;
    }

    filtrados.forEach(produto => {
      const estoqueBaixo = Number(produto.estoque) <= Number(produto.estoque_minimo);
      const card = document.createElement("article");
      card.className = "product";
      card.innerHTML = `
        <div class="product-content">
          <div class="product-topline">
            <h3>${escapar(produto.nome)}</h3>
            <span class="stock-badge ${estoqueBaixo ? "low" : ""}">${estoqueBaixo ? "Estoque baixo" : "Disponível"}</span>
          </div>
          <div class="price">${formatarMoeda(produto.preco)}</div>
          <button class="button outline edit-product" type="button">Editar produto</button>
          <div class="stock-info">
            <div><span>Em estoque</span><strong>${produto.estoque}</strong></div>
            <div><span>Mínimo</span><strong>${produto.estoque_minimo}</strong></div>
          </div>
        </div>
        <form class="movement-form">
          <label>Movimentar estoque</label>
          <div class="movement-grid">
            <select name="tipo" aria-label="Tipo de movimentação">
              <option value="ENTRADA">Entrada</option>
              <option value="SAIDA">Saída</option>
            </select>
            <input name="quantidade" type="number" min="1" value="1" required aria-label="Quantidade">
          </div>
          <input name="motivo" maxlength="200" placeholder="Motivo: venda, produção..." aria-label="Motivo da movimentação">
          <button class="button primary" type="submit">Confirmar movimentação</button>
          <p class="movement-message" aria-live="polite"></p>
        </form>
      `;

      card.querySelector(".edit-product").addEventListener("click", () => editarProduto(produto));
      card.querySelector(".movement-form").addEventListener("submit", event => {
        event.preventDefault();
        movimentarEstoque(produto.id, event.currentTarget);
      });
      lista.appendChild(card);
    });
}

async function editarProduto(produto) {
  const nome = prompt("Nome do produto:", produto.nome);
  if (nome === null) return;
  const precoTexto = prompt("Preço unitário (ex.: 8,50):", String(produto.preco).replace(".", ","));
  if (precoTexto === null) return;
  const estoqueMinimoTexto = prompt("Estoque mínimo:", String(produto.estoque_minimo));
  if (estoqueMinimoTexto === null) return;
  const preco = normalizarPreco(precoTexto);
  const estoque_minimo = Number(estoqueMinimoTexto);
  if (!nome.trim() || !Number.isFinite(preco) || preco <= 0 || !Number.isInteger(estoque_minimo) || estoque_minimo < 0) {
    alert("Dados inválidos. Confira nome, preço positivo e estoque mínimo inteiro não negativo.");
    return;
  }
  try {
    const response = await fetch(`${API}/produtos/${produto.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nome: nome.trim(), preco, estoque: produto.estoque, estoque_minimo })
    });
    const resultado = await response.json();
    if (!response.ok) throw new Error(resultado.erro || "Não foi possível atualizar o produto.");
    mensagem.textContent = resultado.mensagem;
    mensagem.className = "success";
    await carregarProdutos();
  } catch (error) {
    alert(error.message);
  }
}

async function carregarHistorico() {
  const container = document.getElementById("historicoLista");
  try {
    const response = await fetch(`${API}/movimentacoes`);
    if (!response.ok) throw new Error();

    const movimentacoes = await response.json();
    container.innerHTML = "";

    if (movimentacoes.length === 0) {
      container.innerHTML = `
        <div class="empty-state compact">
          <strong>Nenhuma movimentação registrada</strong>
          <p>As entradas e saídas aparecerão aqui.</p>
        </div>
      `;
      return;
    }

    movimentacoes.forEach(mov => {
      const div = document.createElement("div");
      div.className = "history-item";
      const entrada = mov.tipo === "ENTRADA";
      const tipoClasse = entrada ? "entry" : "exit";
      div.innerHTML = `
        <div class="history-product">
          <span class="history-symbol" aria-hidden="true">${entrada ? "+" : "−"}</span>
          <div>
            <strong>${escapar(mov.produto)}</strong>
            <p>${escapar(mov.motivo || "Sem motivo informado")}</p>
            <small>${formatarData(mov.criado_em)}${mov.pedido_id ? ` · Pedido #${mov.pedido_id}` : ""}</small>
          </div>
        </div>
        <div class="movement-summary ${tipoClasse}">
          <strong>${entrada ? "Entrada" : "Saída"} de ${mov.quantidade}</strong>
          <p>${mov.quantidade === 1 ? "unidade" : "unidades"}</p>
          <small>${mov.estoque_anterior} → ${mov.estoque_posterior}</small>
        </div>
      `;
      container.appendChild(div);
    });
  } catch (error) {
    container.textContent = "Erro ao carregar histórico.";
  }
}

form.addEventListener("submit", async event => {
  event.preventDefault();

  const dados = {
    nome: document.getElementById("nome").value,
    preco: normalizarPreco(document.getElementById("preco").value),
    estoque: Number(document.getElementById("estoque").value),
    estoque_minimo: Number(document.getElementById("estoque_minimo").value)
  };

  if (!dados.nome.trim() || !Number.isFinite(dados.preco) || dados.preco <= 0 || !Number.isInteger(dados.estoque) || dados.estoque < 0 || !Number.isInteger(dados.estoque_minimo) || dados.estoque_minimo < 0) {
    mensagem.textContent = "Confira os campos: nome obrigatório, preço positivo e estoques inteiros não negativos.";
    mensagem.className = "error";
    return;
  }

  try {
    const response = await fetch(`${API}/produtos`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(dados)
    });

    const resultado = await response.json();
    if (!response.ok) throw new Error(resultado.erro || "Erro ao cadastrar");

    mensagem.textContent = "Produto cadastrado com sucesso!";
    mensagem.className = "success";
    form.reset();
    await Promise.all([carregarProdutos(), carregarHistorico()]);
  } catch (error) {
    mensagem.textContent = error.message;
    mensagem.className = "error";
  }
});

carregarProdutos();
carregarHistorico();


buscaProduto?.addEventListener("input", renderizarProdutos);
filtroEstoque?.addEventListener("change", renderizarProdutos);


