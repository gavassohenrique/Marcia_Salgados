"""Documentos comerciais calculados exclusivamente com os itens persistidos."""
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo


def moeda(valor):
    numero = f"{Decimal(str(valor)):,.2f}"
    return "R$ " + numero.replace(",", "X").replace(".", ",").replace("X", ".")


def texto(valor):
    # Remove controles que poderiam injetar linhas no TXT ou marcação no PDF.
    return " ".join(str(valor or "").split())


def data_local(valor):
    if isinstance(valor, str):
        valor = datetime.fromisoformat(valor)
    return valor.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M")


def subtotal(item):
    return Decimal(str(item["preco_unitario"])) * item["quantidade"]


def identificacao(pedido):
    return "ORÇAMENTO" if pedido.get("tipo") == "ORCAMENTO" else "PEDIDO"


def aviso(pedido):
    if pedido.get("status") == "CANCELADO":
        return ("ORÇAMENTO CANCELADO - sem movimentação de estoque. Valores apenas para histórico."
                if pedido.get("tipo") == "ORCAMENTO" else
                "PEDIDO CANCELADO - estoque devolvido. Valores apenas para histórico.")
    if pedido.get("tipo") == "ORCAMENTO":
        return "Aguardando confirmação. Este orçamento não reserva nem movimenta estoque."
    return "Pedido confirmado com baixa de estoque."


def gerar_txt(pedido):
    linhas = ["MÁRCIA SALGADOS", identificacao(pedido), f"Número: {pedido['id']:06d}",
              f"Data: {data_local(pedido['criado_em'])} (Brasília)",
              f"Status: {pedido.get('status', 'ATIVO')}",
              f"Cliente: {texto(pedido['cliente'])}", f"Referência: {texto(pedido['referencia']) or 'Não informada'}", "", "ITENS"]
    for item in pedido["itens"]:
        linhas += [texto(item['produto_nome']),
                   f"  {item['quantidade']} un. x {moeda(item['preco_unitario'])} = {moeda(subtotal(item))}"]
    linhas += ["", f"TOTAL: {moeda(sum((subtotal(i) for i in pedido['itens']), Decimal(0)))}",
               "", "Documento comercial. Não é documento fiscal.",
               aviso(pedido)]
    if pedido.get("confirmado_em"):
        linhas += [f"Confirmado em: {data_local(pedido['confirmado_em'])} (Brasília)"]
    return "\n".join(linhas) + "\n"


def gerar_pdf(pedido):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    saida = BytesIO()
    estilos = getSampleStyleSheet()
    normal = ParagraphStyle("corpo", parent=estilos["Normal"], fontSize=10, leading=15, wordWrap="CJK")
    direita = ParagraphStyle("direita", parent=normal, alignment=TA_RIGHT, fontSize=9)
    def p(valor, estilo=normal):
        return Paragraph(escape(texto(valor)), estilo)
    doc = SimpleDocTemplate(saida, pagesize=A4, rightMargin=40, leftMargin=40,
                            topMargin=42, bottomMargin=48, title=f"Márcia Salgados - {identificacao(pedido)} {pedido['id']}",
                            author="Márcia Salgados")
    elementos = [p("Márcia Salgados", estilos["Title"]), p(identificacao(pedido), estilos["Heading2"]),
                 p(f"Nº {pedido['id']:06d} | {data_local(pedido['criado_em'])} (Brasília) | {pedido.get('status', 'ATIVO')}"),
                 Spacer(1, 16), p(f"Cliente: {pedido['cliente']}"),
                 p(f"Referência: {pedido['referencia'] or 'Não informada'}"), Spacer(1, 18)]
    if pedido.get("status") == "CANCELADO":
        elementos += [p(aviso(pedido), estilos["Heading3"])]
    dados = [[p("Produto"), p("Qtd."), p("Unitário"), p("Subtotal")]]
    for item in pedido["itens"]:
        dados.append([p(item["produto_nome"]), p(item["quantidade"], direita),
                      p(moeda(item["preco_unitario"]), direita), p(moeda(subtotal(item)), direita)])
    tabela = Table(dados, colWidths=[175, 75, 95, A4[0]-425], repeatRows=1, hAlign="LEFT")
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3d9b9")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#b56b25"))]))
    elementos += [tabela, Spacer(1, 18), p(f"TOTAL: {moeda(sum((subtotal(i) for i in pedido['itens']), Decimal(0)))}", estilos["Heading2"]),
                  Spacer(1, 12), p("Documento comercial. Não é documento fiscal."),
                  p(aviso(pedido))]
    if pedido.get("confirmado_em"):
        elementos += [p(f"Confirmado em: {data_local(pedido['confirmado_em'])} (Brasília)")]
    def rodape(canvas, documento):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(40, 25, f"Márcia Salgados | {identificacao(pedido)} {pedido['id']:06d} | {pedido.get('status', 'ATIVO')}")
        canvas.drawRightString(A4[0]-40, 25, f"Página {documento.page}")
    doc.build(elementos, onFirstPage=rodape, onLaterPages=rodape)
    return saida.getvalue()
