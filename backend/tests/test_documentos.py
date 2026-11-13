from datetime import datetime, timezone
from decimal import Decimal
import pytest
from documentos import moeda, gerar_txt, gerar_pdf, identificacao, aviso
from app import validar_edicao


def test_documento_calculo_exato_e_texto_seguro():
    pedido = {'id': 42, 'cliente': '<Cliente> & Márcia', 'referencia': 'Entrega\nTOTAL falso',
              'criado_em': datetime(2026, 11, 13, 15, tzinfo=timezone.utc),
              'status': 'ATIVO', 'itens': [
                  {'produto_nome': 'Pão & <queijo>', 'quantidade': 3, 'preco_unitario': Decimal('0.10')}]}
    txt = gerar_txt(pedido)
    assert 'R$ 0,30' in txt and '13/11/2026 12:00' in txt
    assert 'Entrega TOTAL falso' in txt
    assert moeda('1234567.89') == 'R$ 1.234.567,89'
    assert gerar_pdf(pedido).startswith(b'%PDF-')


@pytest.mark.parametrize('itens', [[], None, [True], [{'produto_id': 1, 'quantidade': True}],
                                 [{'produto_id': 1, 'quantidade': 1}]*2])
def test_validacao_edicao(itens):
    with pytest.raises(ValueError):
        validar_edicao({'versao': 1, 'cliente': 'Cliente', 'itens': itens})


def test_recuperacao_por_email_continua_removida():
    from app import app
    rotas = [r.rule.lower() for r in app.url_map.iter_rules()]
    assert not any(any(termo in rota for termo in ('recuper', 'forgot', 'reset-password')) for rota in rotas)


@pytest.mark.parametrize('tipo,status,titulo,conteudo', [
    ('ORCAMENTO', 'ATIVO', 'ORÇAMENTO', 'não reserva nem movimenta'),
    ('ORCAMENTO', 'CANCELADO', 'ORÇAMENTO', 'sem movimentação'),
    ('PEDIDO', 'ATIVO', 'PEDIDO', 'confirmado com baixa'),
    ('PEDIDO', 'CANCELADO', 'PEDIDO', 'estoque devolvido'),
])
def test_documento_distingue_orcamento_pedido_cancelamento(tipo, status, titulo, conteudo):
    pedido = {'tipo': tipo, 'status': status}
    assert identificacao(pedido) == titulo
    assert conteudo in aviso(pedido)
