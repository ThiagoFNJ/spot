"""Testes offline do coletor (inventário de links) e do parser de RH, contra fixtures reais.

Fixtures:
- tests/fixtures/recursos-humanos_2026-10-27.html — snapshot da página de RH (177 links, 2026 vazio).
- tests/fixtures/servidores_2025-09.pdf — set/2025 (999 registros; layout SIGP, mês por extenso).
- tests/fixtures/servidores_2025-12.pdf — dez/2025 (1000 registros; `Mês : 12` numérico).
- tests/fixtures/estagiarios_2025-10.pdf — out/2025 (154 estagiários).
- tests/fixtures/rh_layout_drift_sample.pdf — PDF com outro layout (Relação dos Cargos da Mesa) para o teste de drift.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

import pytest
from pdfplumber.utils.exceptions import PdfminerException

from spot.collect.rh import competencia_from_label, encode_url, parse_links, typo_variants
from spot.parse.rh import (
    SILVER_COLUMNS,
    LayoutError,
    date_to_iso,
    gabinete_from_label,
    money_to_decimal,
    parse_all,
    parse_pdf,
    split_code,
)

FIX = Path(__file__).parent / "fixtures"


# ---- coletor: inventário --------------------------------------------------------------------------


def test_parse_links_inventory() -> None:
    links = parse_links((FIX / "recursos-humanos_2026-10-27.html").read_text(encoding="utf-8"))
    assert len(links) == 177
    anos = {l.ano for l in links}
    assert 2026 not in anos  # aba 2026 existe mas está vazia
    srv_2025 = [l for l in links if l.ano == 2025 and l.tipo == "servidores"]
    est_2025 = [l for l in links if l.ano == 2025 and l.tipo == "estagiarios"]
    assert [l.competencia for l in srv_2025] == [f"2025-{m:02d}" for m in range(1, 13)]
    assert [l.file for l in srv_2025][:4] == [
        "servidores_2025-01.pdf",
        "servidores_2025-02.pdf",
        "servidores_2025-03.pdf",
        "servidores_2025-04.pdf",
    ]
    assert [l.competencia for l in est_2025] == [f"2025-{m:02d}" for m in range(4, 13)]
    assert all(l.tipo is None for l in links if "aniversariantes" in l.secao.lower())


def test_encode_url_spaces_and_accents() -> None:
    url = encode_url("https://www.cms.ba.gov.br/uploads/rh/EFETIVOS E CARGOS EM COMISSÃO ABRIL 2025.pdf")
    assert (
        url
        == "https://www.cms.ba.gov.br/uploads/rh/EFETIVOS%20E%20CARGOS%20EM%20COMISS%C3%83O%20ABRIL%202025.pdf"
    )
    assert encode_url(url) == url  # idempotente
    assert encode_url("/uploads/rh/abc_123.pdf") == "https://www.cms.ba.gov.br/uploads/rh/abc_123.pdf"


def test_competencia_from_label() -> None:
    assert competencia_from_label("Março 2025", 2025) == "2025-03"
    assert competencia_from_label("Janeiro /2022", 2022) == "2022-01"
    assert competencia_from_label("Tabela de cargos", 2025) is None


def test_typo_variants() -> None:
    v = typo_variants("https://www.cms.ba.gov.br/uploads/rh/ESTAGIARIOS%20SETEBMRO%202025.pdf")
    assert v[0] == "https://www.cms.ba.gov.br/uploads/rh/ESTAGIARIOS%20SETEMBRO%202025.pdf"
    assert typo_variants("https://x/y.pdf") == []


# ---- parser: helpers ------------------------------------------------------------------------------


def test_helpers() -> None:
    assert money_to_decimal("4.326,41") == Decimal("4326.41")
    assert money_to_decimal("623,20") == Decimal("623.20")
    with pytest.raises(ValueError):
        money_to_decimal("4326.41")
    assert date_to_iso("01/02/2019") == "2019-02-01"
    with pytest.raises(ValueError):
        date_to_iso("2019-02-01")
    assert split_code("367370 - ASSESSOR PARLAMENTAR-G-13 CC10") == (367370, "ASSESSOR PARLAMENTAR-G-13 CC10")
    with pytest.raises(ValueError):
        split_code("ASSESSOR SEM CODIGO")


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("GAB. VER. ANDRE FRAGA", ("ANDRE FRAGA", "")),
        ("GAB. VER. SILVIO HUMBERTO - 0124", ("SILVIO HUMBERTO", "")),
        ("1ª SECRETARIA - GAB. VER. CLAUDIO TINOCO", ("CLAUDIO TINOCO", "")),
        (
            "GAB. VER. EVERALDO LOPES BECA (SUP. LUIZ CARLOS DE SOUZA)",
            ("EVERALDO LOPES BECA", "LUIZ CARLOS DE SOUZA"),
        ),
        (
            "GAB. VER. HELIO FERREIRA (SUP. VER. AUGUSTO VASCONCELOS)",
            ("HELIO FERREIRA", "AUGUSTO VASCONCELOS"),
        ),
        ("GAB. VER. ORLANDO PALHINHA (SUPLENTE ALBERTO BRAGA)", ("ORLANDO PALHINHA", "ALBERTO BRAGA")),
        ("DIRETORIA DA ESCOLA DO LEGISLATIVO - GAB. VER. MARTA RODRIGUES", ("MARTA RODRIGUES", "")),
        ("GABINETE DA PRESIDENCIA - 00831", ("", "")),
        ("DIRETORIA FINANCEIRA", ("", "")),
    ],
)
def test_gabinete_from_label(label: str, expected: tuple[str, str]) -> None:
    assert gabinete_from_label(label) == expected


# ---- parser: PDFs reais ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def set2025() -> list[dict[str, str]]:
    return parse_pdf(FIX / "servidores_2025-09.pdf")


@pytest.fixture(scope="module")
def dez2025() -> list[dict[str, str]]:
    return parse_pdf(FIX / "servidores_2025-12.pdf")


def test_set2025_schema_and_totals(set2025: list[dict[str, str]]) -> None:
    rows = set2025
    assert len(rows) == 999  # "Total de Registros : 999"
    assert len({r["matricula"] for r in rows}) == 999
    assert all(set(r) == set(SILVER_COLUMNS) for r in rows)
    assert all(r["competencia"] == "2025-09" for r in rows)
    assert all(r["matricula"].isdigit() for r in rows)
    assert all(Decimal(r["proventos"]) > 0 for r in rows)
    assert all(len(r["admissao"]) == 10 and r["admissao"][4] == "-" for r in rows)
    assert sum(Decimal(r["proventos"]) for r in rows) == Decimal("8974966.34")
    gab = [r for r in rows if r["gabinete_vereador"]]
    # O spike (parser por linha) achou 42 gabinetes / 716 / R$ 4.633.426,74: perdia o gabinete
    # 10017183 (MARTA RODRIGUES), cujo rótulo quebra em linha de continuação.
    assert len({r["centro_custo_codigo"] for r in gab}) == 43
    assert len(gab) == 733
    assert sum(Decimal(r["proventos"]) for r in gab) == Decimal("4757228.61")
    assert sum(Decimal(r["proventos"]) for r in gab if r["centro_custo_codigo"] != "10017183") == Decimal(
        "4633426.74"
    )


def test_set2025_sample_rows(set2025: list[dict[str, str]]) -> None:
    by = {r["matricula"]: r for r in set2025}
    r = by["14194"]
    assert r["servidor"] == "ABILIO BARBOSA FILHO"
    assert r["regime"] == "3 - CARGO EM COMISSÃO"
    assert (r["funcao_codigo"], r["funcao"], r["simbolo"], r["grau"]) == (
        "367370",
        "ASSESSOR PARLAMENTAR-G-13 CC10",
        "CC10",
        "G-13",
    )
    assert r["admissao"] == "2013-01-01"
    assert (r["centro_custo_codigo"], r["centro_custo_label"]) == (
        "367171",
        "GAB. VER. SILVIO HUMBERTO - 0124",
    )
    assert r["gabinete_vereador"] == "SILVIO HUMBERTO"
    assert r["proventos"] == "4326.41"
    assert r["bronze_file"] == "servidores_2025-09.pdf"
    # célula de função quebrada em duas linhas (continuação vai para a coluna certa)
    r = by["21049"]
    assert r["funcao"] == "ASSESSOR ESPECIAL DO GABINETE DA PRESIDENCIA CC80"
    assert r["simbolo"] == "CC80"
    assert r["centro_custo_label"] == "GABINETE DA PRESIDENCIA - 00831"
    assert r["gabinete_vereador"] == ""
    # centro de custo quebrado em duas linhas
    r = by["21304"]
    assert r["centro_custo_label"] == "CORRREGEDORIA - GAB. VER. ALEXANDRE ALELUIA"
    assert r["gabinete_vereador"] == "ALEXANDRE ALELUIA"
    # suplente por extenso "(SUPLENTE ...)" — regex antiga devolvia "LENTE ALBERTO BRAGA"
    assert {
        (r["gabinete_vereador"], r["suplente_vereador"])
        for r in set2025
        if r["centro_custo_codigo"] == "10680016"
    } == {("ORLANDO PALHINHA", "ALBERTO BRAGA")}
    assert {r["suplente_vereador"] for r in set2025 if r["suplente_vereador"]} == {
        "ALBERTO BRAGA",
        "AUGUSTO VASCONCELOS",
        "LUIZ CARLOS DE SOUZA",
    }
    # símbolo com hífen
    assert {r["simbolo"] for r in set2025 if r["funcao"].endswith("CC-50")} == {"CC50"}


def test_dez2025_new_month_format(dez2025: list[dict[str, str]]) -> None:
    assert len(dez2025) == 1000
    assert all(r["competencia"] == "2025-12" for r in dez2025)
    by = {r["matricula"]: r for r in dez2025}
    assert by["21524"]["centro_custo_label"] == "4ª SECRETARIA - GAB. VER. KEL TORRES"
    assert by["21524"]["gabinete_vereador"] == "KEL TORRES"


def test_set_vs_dez_no_13o(set2025: list[dict[str, str]], dez2025: list[dict[str, str]]) -> None:
    """Dezembro NÃO traz 13º: sem salto ~2x por matrícula e total do mês igual ao de setembro (±2%)."""
    s = {r["matricula"]: Decimal(r["proventos"]) for r in set2025}
    d = {r["matricula"]: Decimal(r["proventos"]) for r in dez2025}
    common = s.keys() & d.keys()
    assert len(common) > 900
    same = sum(1 for m in common if s[m] == d[m])
    assert same / len(common) > 0.8  # observado: 845/970
    doubled = sum(1 for m in common if d[m] / s[m] > Decimal("1.5"))
    assert doubled / len(common) < 0.01  # observado: 1 (mudança de cargo), não 13º
    tot_s, tot_d = sum(s.values()), sum(d.values())
    assert abs(tot_d - tot_s) / tot_s < Decimal("0.02")
    # tabela CC10 idêntica nos dois meses
    g16 = {
        r["proventos"]
        for rows in (set2025, dez2025)
        for r in rows
        if r["grau"] == "G-16" and r["simbolo"] == "CC10"
    }
    assert g16 == {"5324.80"}


def test_estagiarios() -> None:
    rows = parse_pdf(FIX / "estagiarios_2025-10.pdf")
    assert len(rows) == 154
    assert {r["proventos"] for r in rows} == {"623.20", "923.20"}
    assert all(r["regime"] == "5 - ESTAGIARIO" for r in rows)
    by = {r["matricula"]: r for r in rows}
    assert by["30049"]["servidor"] == "AMANDA BEATRIZ ALENCAR SANTANA DOS SANTOS"  # nome quebrado em 2 linhas
    assert by["30095"]["gabinete_vereador"] == "EVERALDO LOPES BECA"
    assert by["30095"]["suplente_vereador"] == "LUIZ CARLOS DE SOUZA"


def test_bad_filename() -> None:
    with pytest.raises(ValueError):
        parse_pdf(FIX / "frequencia_2025-03_tipo1.csv")


def test_layout_drift_fails_loudly(tmp_path: Path) -> None:
    # PDF real com outro layout (Relação dos Cargos da Mesa): sem linha de colunas -> LayoutError
    with pytest.raises(LayoutError, match="linha de colunas"):
        parse_pdf(FIX / "rh_layout_drift_sample.pdf", competencia="2025-01")
    # bytes que não são um PDF: a exceção do pdfplumber sobe, nunca silêncio
    (tmp_path / "servidores_2025-01.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    with pytest.raises(PdfminerException):
        parse_pdf(tmp_path / "servidores_2025-01.pdf")


def test_parse_all_writes_sorted_utf8_csv(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    bronze.mkdir()
    for name in ("servidores_2025-12.pdf", "servidores_2025-09.pdf", "estagiarios_2025-10.pdf"):
        (bronze / name).write_bytes((FIX / name).read_bytes())
    silver = tmp_path / "silver"
    counts = parse_all(bronze, silver)
    assert counts == {"servidores": 1999, "estagiarios": 154}
    with (silver / "folha.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == SILVER_COLUMNS
    keys = [(r["competencia"], int(r["matricula"])) for r in rows]
    assert keys == sorted(keys)
    assert rows[0]["competencia"] == "2025-09" and rows[-1]["competencia"] == "2025-12"
    assert "COMISSÃO" in (silver / "folha.csv").read_text(encoding="utf-8")


def test_layout_error_is_runtime_error() -> None:
    assert issubclass(LayoutError, RuntimeError)
