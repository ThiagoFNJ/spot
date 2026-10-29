"""Testes offline do parser dos processos de Verba Compensatória do e-TCM.

Fixtures (gerados por `uv run python -m spot.parse.etcm_vc --dump-fixture <pdf> --out tests/fixtures/etcm_vc_pp2130.txt`
a partir de `PP 2130 - VC - Debora Santos de Santana.pdf`, com CPFs mascarados):
- tests/fixtures/etcm_vc_pp2130.txt — texto por página (12 páginas), separadas por `===== PAGE n =====`.
- tests/fixtures/etcm_vc_pp2130.words.json — palavras (texto + x0/x1/top/bottom) da página do resumo (p. 5),
  para exercitar a atribuição posicional dos valores às categorias.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from spot.parse import etcm_vc as m

FIX = Path(__file__).parent / "fixtures"
ARQUIVO = "PP 2130 - VC - Debora Santos de Santana.pdf"
ESPERADO_ITENS = {"IX": Decimal("13600.00"), "X": Decimal("17000.00"), "XII": Decimal("3400.00")}


@pytest.fixture(scope="module")
def pages() -> list[str]:
    return m.split_fixture((FIX / "etcm_vc_pp2130.txt").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def words_json() -> dict:
    return json.loads((FIX / "etcm_vc_pp2130.words.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def parsed(pages: list[str]) -> tuple[dict[str, str], list[dict[str, str]]]:
    return m.parse_processo(ARQUIVO, pages)


def test_fixture_sem_cpf(pages: list[str], words_json: dict) -> None:
    texto = "\n".join(pages) + " ".join(w["text"] for w in words_json["words"])
    assert not m.RE_CPF.search(texto)
    assert m.CPF_MASK in texto


def test_fixture_tem_12_paginas(pages: list[str]) -> None:
    assert len(pages) == 12
    assert m.find_resumo_page(pages) == 4


def test_cabecalho(parsed: tuple[dict[str, str], list[dict[str, str]]]) -> None:
    row, _, _ = parsed
    assert list(row) == m.PROCESSO_COLUMNS
    assert row["arquivo"] == ARQUIVO
    assert row["pp_numero"] == "2130"
    assert row["ano_processo"] == "2025"
    assert row["requerente"] == "Debora Santos de Santana"
    assert row["vereador_id"] == "debora-santana"
    assert row["competencia"] == "2025-08"
    assert row["data_entrada"] == "2025-09-11"
    assert row["total_declarado"] == "34000.00"
    assert "14.10.09.2025" in row["auditoria_numero"]
    assert row["empenho_numero"] == "2025NE000656"
    assert row["liquidacao_numero"] == "2025NL007402"
    assert row["ordem_bancaria"] == "2025OB000595"  # OCR lê "20250B000595"
    assert row["pagamento_numero"] == "2025PP003024"
    assert row["data_pagamento"] == "2025-09-12"
    assert row["n_paginas"] == "12"
    assert row["confianca"] == "alta"
    assert row["layout"] == m.LAYOUT_RESUMO


def test_itens_por_texto(parsed: tuple[dict[str, str], list[dict[str, str]]]) -> None:
    _, itens, _ = parsed
    assert [list(i) for i in itens] == [m.ITEM_COLUMNS] * len(itens)
    assert {i["categoria_romano"]: Decimal(i["valor"]) for i in itens} == ESPERADO_ITENS
    assert sum(Decimal(i["valor"]) for i in itens) == Decimal("34000.00")
    assert all(i["competencia"] == "2025-08" and i["pp_numero"] == "2130" for i in itens)
    assert itens[0]["categoria_descricao"].startswith("Consultorias")


def test_itens_por_posicao(words_json: dict) -> None:
    itens, ok = m.parse_itens_words(words_json["words"], words_json["width"])
    assert ok
    assert itens == ESPERADO_ITENS


def test_parse_com_palavras_igual_ao_texto(pages: list[str], words_json: dict, parsed) -> None:
    words: list[list[dict] | None] = [None] * len(pages)
    widths = [0.0] * len(pages)
    words[words_json["page"] - 1] = words_json["words"]
    widths[words_json["page"] - 1] = words_json["width"]
    assert m.parse_processo(ARQUIVO, pages, words, widths) == parsed  # type: ignore[arg-type]


def test_soma_diferente_rebaixa_confianca(pages: list[str], caplog: pytest.LogCaptureFixture) -> None:
    alterado = [p.replace("R$ 17.000,00", "R$ 17.100,00") for p in pages]
    row, itens, _ = m.parse_processo(ARQUIVO, alterado)
    assert row["confianca"] == "baixa"
    assert sum(Decimal(i["valor"]) for i in itens) == Decimal("34100.00")
    assert "soma dos itens" in caplog.text


def test_competencia_por_mes_extenso(pages: list[str]) -> None:
    sem_competencia = [p.replace("Competéncia n°: 08/2025", "") for p in pages]
    assert m.competencia(sem_competencia) == "2025-08"  # "mês de agosto de 2025" do termo de abertura


def test_sem_resumo_vira_layout_nenhum(pages: list[str]) -> None:
    # abr e mai/2025: o processo não traz tabela de categorias; fica o total autorizado, sem itens.
    row, itens, nfs = m.parse_processo(ARQUIVO, [p for i, p in enumerate(pages) if i != 4])
    assert row["layout"] == m.LAYOUT_NENHUM
    assert row["total_declarado"] == "34000.00"
    assert row["confianca"] == "media"
    assert itens == [] and nfs == []


def test_pdf_vazio_levanta_layout_error() -> None:
    with pytest.raises(m.LayoutError):
        m.parse_processo(ARQUIVO, [])


def test_vereador_nao_resolvido_fica_vazio(pages: list[str], caplog: pytest.LogCaptureFixture) -> None:
    row, _, _ = m.parse_processo("PP 1 - VC - Fulano.pdf", pages, nome_index={})
    assert row["vereador_id"] == ""
    assert "sem vereador_id" in caplog.text


@pytest.mark.parametrize(
    "tok, ok",
    [
        ("1", True),
        ("ll_-", True),
        ("III", True),
        ("1V", True),
        ("X1V", True),
        ("XV", True),
        ("Camara", False),
        ("a0", False),
    ],
)
def test_romano_ocr(tok: str, ok: bool) -> None:
    assert m._is_romano(tok) is ok


def test_block_indices_decodifica_quando_falta_bloco() -> None:
    toks = [
        "1",
        "ll_",
        "III",
        "1V",
        "V",
        "VI",
        "VII",
        "VIII",
        "IX",
        "X",
        "XI",
        "XII",
        "XIII",
        "X1V",
    ]  # sem XV
    assert m._block_indices(toks) == list(range(14))
    assert m._block_indices(["1", "zz"]) is None


def test_mascarar_cpf() -> None:
    assert m.mascarar_cpf("Cpf. 123.456.789-01, Mat. 1") == "Cpf. ***.***.***-**, Mat. 1"
    assert m.mascarar_cpf("12345678901 DEBORA") == "***.***.***-** DEBORA"
    assert m.mascarar_cpf("2025NE000656 34.000,00") == "2025NE000656 34.000,00"


def test_seed_categorias() -> None:
    cats = m.load_categorias()
    assert list(cats) == m.ROMANOS
    assert cats["XIV"] == "Combustível"


BRONZE_PDF = m.BRONZE_ETCM / ARQUIVO


@pytest.mark.skipif(not BRONZE_PDF.exists(), reason="PDF bruto do e-TCM não está no bronze local")
def test_pdf_real_igual_ao_fixture(parsed) -> None:
    assert m.parse_pdf(BRONZE_PDF) == parsed
