const request = require("supertest");

jest.mock("pg", () => {
  const query = jest.fn();

  return {
    Pool: jest.fn(() => ({
      query,
      connect: jest.fn()
    }))
  };
});

const { Pool } = require("pg");
const { app } = require("./server");

const pool = new Pool();

describe("API Marcia Salgados", () => {

  beforeEach(() => {
    pool.query.mockReset();
  });

  test("GET / deve retornar API funcionando", async () => {

    const response = await request(app)
      .get("/");

    expect(response.statusCode).toBe(200);

    expect(response.body).toEqual({
      mensagem: "API funcionando",
      projeto: "Marcia Salgados"
    });
  });

  test("GET /produtos deve retornar produtos", async () => {

    pool.query.mockResolvedValueOnce({
      rows: [
        {
          id: 1,
          nome: "Coxinha",
          preco: "5.00",
          estoque: 20
        }
      ]
    });

    const response = await request(app)
      .get("/produtos");

    expect(response.statusCode).toBe(200);

    expect(response.body).toHaveLength(1);

    expect(response.body[0].nome)
      .toBe("Coxinha");
  });

  test("POST /produtos sem nome deve retornar 400", async () => {

    const response = await request(app)
      .post("/produtos")
      .send({
        preco: 5
      });

    expect(response.statusCode).toBe(400);

    expect(response.body.erro)
      .toBe("Nome e preço são obrigatórios");
  });

});