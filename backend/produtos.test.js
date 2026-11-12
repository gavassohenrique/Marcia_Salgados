const request = require("supertest");

const mockQuery = jest.fn();
jest.mock("pg", () => ({ Pool: jest.fn(() => ({ query: mockQuery })) }));

const { app } = require("./server");

describe("API Marcia Salgados", () => {
  beforeEach(() => mockQuery.mockReset());

  test("GET / retorna o estado da API", async () => {
    const response = await request(app).get("/");
    expect(response.statusCode).toBe(200);
    expect(response.body.projeto).toBe("Marcia Salgados");
  });

  test("GET /produtos retorna os produtos", async () => {
    mockQuery.mockResolvedValueOnce({ rows: [{ id: 1, nome: "Coxinha", preco: "5.00", estoque: 20 }] });
    const response = await request(app).get("/produtos");
    expect(response.statusCode).toBe(200);
    expect(response.body[0].nome).toBe("Coxinha");
  });

  test("POST /produtos cadastra todos os dados recebidos", async () => {
    mockQuery.mockResolvedValueOnce({ rows: [{ id: 1, nome: "Coxinha", preco: "5.00", estoque: 20, estoque_minimo: 5 }] });
    const response = await request(app).post("/produtos").send({ nome: "Coxinha", preco: 5, estoque: 20, estoque_minimo: 5 });
    expect(response.statusCode).toBe(201);
    expect(mockQuery).toHaveBeenCalledWith(expect.stringContaining("INSERT INTO produtos"), ["Coxinha", 5, 20, 5]);
  });

  test("POST /produtos rejeita preço inválido", async () => {
    const response = await request(app).post("/produtos").send({ nome: "Coxinha", preco: -1 });
    expect(response.statusCode).toBe(400);
  });

  test("entrada processa a quantidade e retorna o novo estoque", async () => {
    mockQuery
      .mockResolvedValueOnce({ rows: [{ id: 1, nome: "Coxinha", estoque: 25, estoque_anterior: 20 }] })
      .mockResolvedValueOnce({ rows: [{ id: 1, tipo: "ENTRADA", quantidade: 5 }] });
    const response = await request(app).post("/produtos/1/movimentacoes").send({ tipo: "ENTRADA", quantidade: 5, motivo: "Produção" });
    expect(response.statusCode).toBe(201);
    expect(response.body.produto.estoque).toBe(25);
    expect(response.body.mensagem).toBe("Entrada registrada");
  });

  test("saída maior que o estoque é recusada", async () => {
    mockQuery.mockResolvedValueOnce({ rows: [] }).mockResolvedValueOnce({ rows: [{ id: 1 }] });
    const response = await request(app).post("/produtos/1/movimentacoes").send({ tipo: "SAIDA", quantidade: 50 });
    expect(response.statusCode).toBe(409);
    expect(response.body.erro).toMatch(/insuficiente/i);
  });
});
