"""Formulário antigo (fev–mar/2025) do e-TCM: itens por documento fiscal.

Fixture `tests/fixtures/etcm_vc_pp367.txt` = PP 367/2025 (Alexandre Aleluia, competência jan/2025), gerado por
`uv run python -m spot.parse.etcm_vc --dump-fixture <pdf> --out tests/fixtures/etcm_vc_pp367.txt`
(CPF, agência e conta mascarados pelo dump). Os trechos inline reproduzem linhas de outros processos do mesmo mês.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from spot.parse import etcm_vc as m
from spot.parse import etcm_vc_detalhamento as det

FIX = Path(__file__).parent / "fixtures"
ARQUIVO = "PP 367 - VC - Alexandre Aleluia Dantas Costa.pdf"


@pytest.fixture(scope="module")
def pages() -> list[str]:
    return m.split_fixture((FIX / "etcm_vc_pp367.txt").read_text(encoding="utf-8"))


def test_fixture_sem_dados_sensiveis(pages: list[str]) -> None:
    texto = "\n".join(pages)
    assert not m.RE_CPF.search(texto)
    assert "Agência: ****" in texto and "Conta: ****" in texto


def test_layout_detalhamento(pages: list[str]) -> None:
    assert m.detectar_layout(pages) == (m.LAYOUT_DETALHAMENTO, 1)


def test_processo_pp367(pages: list[str]) -> None:
    row, itens, nfs = m.parse_processo(ARQUIVO, pages)
    assert row["layout"] == m.LAYOUT_DETALHAMENTO
    assert row["pp_numero"] == "367" and row["ano_processo"] == "2025"
    assert row["competencia"] == "2025-01"
    assert row["vereador_id"] == "alexandre-aleluia"
    assert row["total_declarado"] == "14375.75"
    assert row["confianca"] == "alta"
    assert [list(n) for n in nfs] == [m.NF_COLUMNS] * 5
    assert [
        (n["item"], n["inciso_fonte"], n["categoria_romano"], n["documento_fiscal"], n["valor_compensado"])
        for n in nfs
    ] == [
        ("01", "XVI", "XIV", "87620", "202.95"),
        ("02", "XII", "XII", "28", "5800.00"),
        ("03", "X", "X", "134", "8250.00"),
        ("04", "", "I", "157896448169", "89.90"),
        ("05", "II", "II", "215905064779", "32.90"),
    ]
    assert nfs[0]["data_emissao"] == "2025-01-30"
    assert nfs[3]["descricao"] == "Locação Armazenamento nuvem software"  # linha quebrada em duas no PDF
    assert {i["categoria_romano"]: Decimal(i["valor"]) for i in itens} == {
        "I": Decimal("89.90"),
        "II": Decimal("32.90"),
        "X": Decimal("8250.00"),
        "XII": Decimal("5800.00"),
        "XIV": Decimal("202.95"),
    }


TINOCO = """DETALHAMENTO / RESUMO - PROCESSO VERBA COMPENSATORIA
Vereador Responsável: CLAUDIO TINOCO
Item | Referência ao $ Histórico / Tipo Despesa Documento Data Valor Valor Glosa Saldo a
do Art. 2º Fiscal nº | Emissão NF | Apresentado Compensar
01 Iv Telefonia Celular Recibo 13-jan-25 R$ 554,90 R$ 554,90
02 XIV Combustível cupom fiscal 17-jan-25 R$ 233,75 R$ 233,75
03 XIV Combustível cupom fiscal llegivel R$ 230,13 R$ 230,13 R$ 0,00
04 XIV Combustivel cupom fiscal | 29-jan-25 R$ 208,07 R$ 208,07
TOTAL >> R$ 1.579,75) R$230,13] R$1.349,62
Salvador, 11 de fevereiro de 2025
"""


def test_glosa_e_totais() -> None:
    d = det.parse_pagina(TINOCO)
    assert d.total_apresentado == Decimal("1579.75")
    assert d.total_glosa == Decimal("230.13")
    assert d.total_compensado == Decimal("1349.62")
    assert [(i.inciso_fonte, i.categoria, i.documento, i.glosa, i.compensado) for i in d.itens] == [
        ("IV", "IV", "Recibo", Decimal(0), Decimal("554.90")),
        ("XIV", "XIV", "cupom fiscal", Decimal(0), Decimal("233.75")),
        ("XIV", "XIV", "cupom fiscal llegivel", Decimal("230.13"), Decimal(0)),
        ("XIV", "XIV", "cupom fiscal", Decimal(0), Decimal("208.07")),
    ]
    assert det.agregar(d.itens) == {"IV": Decimal("554.90"), "XIV": Decimal("441.82")}


PAULO = """DETALHAMENTO / RESUMO - PROCESSO VERBA COMPENSATORIA
01 XII Midia Social 056 31-jan-25 R$ 6.800,00 R$ 6.800,00
02 X Impressão Digital Serviços Graficos 003 30-jan-25 R$ 8.500,00 R$ 8.500,00
03 1X Consultoria Juridica 087 31-jan-25 R$ 6.800,00 R$ 6.800,00
Cupom Fiscal 09-jan-25 R$ 187,92 R$ 187,92
" Cupom Fiscal | 17-jan-25 R$ 160,00 R$ 160,00
04 XIV Combustível Cupom Fiscal | 21-jan-25 R$ 317,32 R$ 317,32
Cupom Fiscal 22-jan-25 R$ 231,69 R$ 231,69
TOTAL >> R$ 22.996,93 R$ 0,00) R$ 22.996,93
"""


def test_cupons_sem_numero_de_item_vao_para_combustivel() -> None:
    d = det.parse_pagina(PAULO)
    assert [i.item for i in d.itens] == ["01", "02", "03", "", "", "04", ""]
    assert [i.categoria for i in d.itens] == ["XII", "X", "IX", "XIV", "XIV", "XIV", "XIV"]
    assert d.itens[2].inciso_fonte == "IX"  # OCR "1X"
    assert det.agregar(d.itens)["XIV"] == Decimal("896.93")
    assert sum((i.compensado for i in d.itens), Decimal(0)) == d.total_compensado


MARCELLE = """DETALHAMENTO / RESUMO - PROCESSO VERBA COMPENSATORIA
o1 X Impressão grafica divulgação 459 23-jan-25 R$ 8.500,00 R$ 8.500,00
parlamentar
02 XI Serviços Mídia assessoria imprensa 621 27-jan-25 R$ 6.800,00 R$ 6.800,00
03 VII Serviços Filmagem e Fotografia 01 28-jan-25 R$ 6.800,00 R$ 6.800,00
04 IX Consultoria Juridica 345 31-jan-25 R$ 6.800,00 R$ 6.800,00
05 XIV Combustivel cupom fiscal | 30-jan-25 R$ 50,00 R$ 50,00
06 Combustivel cupom fiscal | 30-jan-25 R$ 50,00 R$ 50,00
04 R$ 0,00
R$ 0,00
TOTAL >> R$ 29.000,00 R$ 0,00] R$ 29.000,00
"""


def test_linha_quebrada_ocr_o1_e_zeros() -> None:
    d = det.parse_pagina(MARCELLE)
    assert [i.item for i in d.itens] == ["01", "02", "03", "04", "05", "06"]
    assert d.itens[0].descricao == "Impressão grafica divulgação parlamentar"
    assert d.itens[0].categoria == "X"
    assert d.itens[1].categoria == "XII"  # "assessoria imprensa" é mídia, não consultoria
    assert d.itens[5].categoria == "XIV"  # sem inciso declarado: pelo texto
    assert d.itens[5].inciso_fonte == ""


@pytest.mark.parametrize(
    "tok, esperado",
    [
        ("Il", "II"),
        ("Vil", "VII"),
        ("Vill", "VIII"),
        ("1X", "IX"),
        ("XI!", "XII"),
        ("Iv", "IV"),
        ("XVI", "XVI"),
        ("Xl", "XI"),
        ("Combustivel", ""),
        ("|", "I"),
    ],
)
def test_romano_ocr(tok: str, esperado: str) -> None:
    assert det.romano(tok) == esperado


@pytest.mark.parametrize(
    "descricao, doc, inciso, esperado",
    [
        ("Gasto com combustivel", "cupom fiscal", "VIII", "XIV"),
        ("Divuigação midia impressa e digital", "43", "XII", "XII"),
        ("Serviços Graficos", "3169", "XI", "X"),
        ("Edição de Jornais, Livros, Revistas", "8722", "X", "X"),
        ("Consultoria elaboração projeto legislativo", "004", "IX", "IX"),
        ("Assessoria de comunicação", "229", "XI", "XII"),
        ("Locação software aplicativo", "5175", "", "I"),
        ("Serviços tecnologia da informação", "215905064779", "II", "II"),
        ("Mídia Digital e rede social", "02", "XI", "XII"),
        ("locação de automóvel", "067", "", "XV"),
        ("Impulsionamento de posts", "1", "XII", "XIII"),
        ("Coisa desconhecida", "", "XVI", ""),
        ("Coisa desconhecida", "", "III", "III"),
    ],
)
def test_categoria_por_texto(descricao: str, doc: str, inciso: str, esperado: str) -> None:
    assert det.categoria_por_texto(descricao, doc, inciso) == esperado


def test_mascarar_sensiveis() -> None:
    txt = "CPF: 123.456.789-01 Agência: 4682 Conta: 10818583 / Ag: 0235-6 / CC: 19341-0 Processo 367/2025"
    out = m.mascarar_sensiveis(txt)
    assert "4682" not in out and "10818583" not in out and "19341" not in out and "0235" not in out
    assert m.CPF_MASK in out and "367/2025" in out


def test_valor_com_espaco_e_saldo_ilegivel() -> None:
    # Clermilson, jan/2025: o OCR destrói a coluna do saldo ("R$ zoe", "R$ 8.0000") e troca o ponto do total por espaço.
    txt = """DETALHAMENTO / RESUMO - PROCESSO VERBA COMPENSATORIA
01 XIV Combustivel 649479 21-jan-25 R$ 209,56| R$ 0,00 R$ zoe
05 XI Marketing redes sociais, criação de 24 30-jan-25 R$ 6.000,00] R$ 0,00) R$ 6.000,
07 X Serviços Graficos 3170 31jan-25 R$ 8.000,00] R$ 0,00] R$ 8.0000
TOTAL >> R$ 14.209,56| R$ 0,00] R$ 14 209,56
"""
    d = det.parse_pagina(txt)
    assert [i.compensado for i in d.itens] == [Decimal("209.56"), Decimal("6000.00"), Decimal("8000.00")]
    assert d.total_compensado == Decimal("14209.56")
    assert d.itens[1].categoria == "XII"


def test_tabela_em_duas_paginas() -> None:
    p1 = """DETALHAMENTO / RESUMO - PROCESSO VERBA COMPENSATORIA
02 XIV Combustível 1300247 14-fev-25 R$ 200,00 R$ 200,00
03 XIV Combustível 1300881 15-fev-25 R$ 200,00 R$ 200,00
Arquivo com Id. 433946 Anexado via login e senha
"""
    p2 = """23 1X Serviços jurídicos 9 28-fev-25 | R$10.000,00 R$ 10.000,00
TOTAL >> R$ 10.400,00 R$00,00] R$ 10.400,00
"""
    p3 = "LEGISLACAO\nLeis nº 9.828/2025"
    d = det.parse_paginas(["capa", p1, p2, p3], 1)
    assert [i.item for i in d.itens] == ["02", "03", "23"]
    assert d.total_compensado == Decimal("10400.00") == sum((i.compensado for i in d.itens), Decimal(0))
    assert d.itens[2].documento == "9" and d.itens[2].categoria == "IX"


def test_processo_que_nao_e_de_verba_e_rejeitado() -> None:
    with pytest.raises(m.LayoutError, match="não é processo de verba"):
        m.parse_processo(
            "PP 2404 - VC - Fulano.pdf", ["Capa do Processo: PRO-2404/2025\ncontribuições previdenciárias"]
        )


@pytest.mark.parametrize(
    "arquivo, nome",
    [
        ("PP 907 - VC - Theofilo Virgilio de Senna-compressed.pdf", "Theofilo Virgilio de Senna"),
        ("PP 1548-VC- Theofilo Virgilio de Senna.pdf", "Theofilo Virgilio de Senna"),
        ("PP 372 VC - Eliete Paraguassu da Conceição.pdf", "Eliete Paraguassu da Conceição"),
        ("PP 1001 - VC- Orlando Palhinha.pdf", "Orlando Palhinha"),
        ("outro.pdf", ""),
    ],
)
def test_nome_do_arquivo(arquivo: str, nome: str) -> None:
    assert m.nome_do_arquivo(arquivo) == nome


def test_competencia_por_periodo_e_por_mes_sem_ano() -> None:
    assert m.competencia(["Período Analisado: 01 a 28 DE FEVEREIRO 2025"]) == "2025-02"
    assert (
        m.competencia(["VERBA COMPENSATÓRIA DE ATIVIDADE PARLAMENTAR DO MÊS DE FEVEREIRO,"], "2025")
        == "2025-02"
    )
    assert m.competencia(["VERBA COMPENSATÓRIA DO MÊS DE FEVEREIRO,"]) == ""


def test_mascara_cpf_de_servidor_quebrado_pelo_ocr() -> None:
    out = m.mascarar_sensiveis("Anexado via login e senhpaor Cid Santos, C,pf . 941120705, 7M8at . 6074")
    assert "941120705" not in out
