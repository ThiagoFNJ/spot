"""Testes offline das proposições (fixtures em tests/fixtures/, sem rede)."""

from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path

import pytest

from spot.collect.proposicoes import csv_link, resumo_parm, summary_body
from spot.parse import proposicoes as parse
from spot.scriptcase import ScriptCaseError, grid_total

FIX = Path(__file__).parent / "fixtures"
PROP_FIXTURE = FIX / "proposicoes_prop_interna_head.csv"
RESUMO_2025 = FIX / "proposicoes_resumo_2025.html"
RESUMO_2026 = FIX / "proposicoes_resumo_2026.html"


# ---- collector helpers (sem rede) -----------------------------------------------------------


def test_csv_link_from_post_response():
    text = (FIX / "proposicoes_prop_interna_csv_post.html").read_text(encoding="utf-8")
    assert csv_link(text) == "/p/tmp/sc_csv_20261027182816_699_prop_interna.csv"
    assert csv_link("<html>Fatal error</html>") is None


def test_summary_body_extraction():
    html = RESUMO_2025.read_text(encoding="utf-8")
    raw = json.dumps(
        {
            "setDisplay": [],
            "setValue": [
                {"field": "id_resumo_search", "value": "x"},
                {"field": "summary_body", "value": html},
            ],
        }
    )
    assert summary_body(raw) == html
    with pytest.raises(ScriptCaseError):
        summary_body('{"setValue": []}')


def test_resumo_parm():
    assert resumo_parm(2025).endswith("__DL__YYYY__DL__2025")
    assert resumo_parm(2025).startswith(
        "TRA_TRA_DT_MOVIMENTACAO_SC_1__DL__TRA.TRA_DT_MOVIMENTACAO__DL__dth__DL__eql__DL__actual"
    )


def test_grid_total_with_spans():
    footer = "[1 a <span class='sm_counter_final'>20</span> de <span class='sm_counter_total'>31776</span>]"
    assert grid_total(footer) == 31776
    assert grid_total("[1 a 43 de 23472]") == 23472


# ---- parse prop_interna ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def prop_rows():
    return parse.parse_prop_interna(PROP_FIXTURE.read_bytes(), PROP_FIXTURE.name)


def test_prop_interna_rows(prop_rows):
    assert len(prop_rows) == 96  # 97 registros no fixture, menos o cabeçalho
    assert set(parse.PROP_COLUMNS) == set(prop_rows[0])
    assert all(r["bronze_file"] == PROP_FIXTURE.name for r in prop_rows)


def test_prop_interna_codigo_split(prop_rows):
    by_code = {r["codigo"]: r for r in prop_rows}
    r = by_code["PLE-287/2026"]
    assert (r["tipo"], r["numero"], r["ano"]) == ("PLE", 287, 2026)
    assert r["autor_fonte"] == "André Fraga"
    assert r["autores"] == "André Fraga"
    assert r["movimentado"] == "2026-10-16"
    assert r["localizacao"] == "Super. de Protocolo. Leg."
    assert r["situacao"] == "Aguardando Publicacao"
    assert "\n" not in r["ementa"] and r["ementa"].startswith("Estabelece diretrizes de transparência")


def test_prop_interna_sorted_and_unique(prop_rows):
    keys = [(r["ano"], r["tipo"], r["numero"]) for r in prop_rows]
    assert keys == sorted(keys)
    assert len({r["codigo"] for r in prop_rows}) == len(prop_rows)


def test_prop_interna_autores_whitespace(prop_rows):
    rand = [r for r in prop_rows if "Randerson" in r["autor_fonte"]]
    assert rand, "fixture deveria conter Randerson  Leal (espaço duplo)"
    assert all(r["autor_fonte"] == "Randerson  Leal" and r["autores"] == "Randerson Leal" for r in rand)


def test_prop_interna_latin1_fallback():
    """Os apps do 45.4.247.157 exportam ISO-8859-1; o parser tem que aceitar os dois encodings."""
    header = '"";"Proposição";"Autor";"Ementa";"Movimentado";"Localização";"Situação";"Autor/Requerente/Vistas/Outros"\r\n'
    row = '"";"PLE-1/2025";"José Antônio";"Ementa\r\ncom ção";"02/03/2025 ";"Super. de Protocolo. Leg.";"Protocolado";""\r\n'
    rows = parse.parse_prop_interna((header + row).encode("latin-1"), "x.csv")
    assert rows[0]["autor_fonte"] == "José Antônio" and rows[0]["ementa"] == "Ementa com ção"
    assert rows[0]["movimentado"] == "2025-03-02"


def test_prop_interna_bad_code_skipped(caplog):
    raw = PROP_FIXTURE.read_bytes() + b'"";"XYZ";"A";"e";"01/01/2025 ";"l";"s";""\r\n'
    rows = parse.parse_prop_interna(raw, "x.csv")
    assert len(rows) == 96
    assert "fora do padrão" in caplog.text


def test_prop_interna_sentinela_test_record(caplog):
    """PLE-9999/2025 é um registro de teste do sistema: fica no silver marcado, nunca descartado."""
    raw = PROP_FIXTURE.read_bytes() + (
        b'"";"PLE-9999/2025";"Jo\xc3\xa3o Marcelo";"Documento de teste - aba Legislativo";'
        b'"17/08/2026 ";"";".";""\r\n'
    )
    caplog.set_level(logging.INFO)
    rows = parse.parse_prop_interna(raw, "x.csv")
    assert len(rows) == 97
    by_code = {r["codigo"]: r for r in rows}
    assert by_code["PLE-9999/2025"]["sentinela"] == "true"
    assert by_code["PLE-9999/2025"]["autor_fonte"] == "João Marcelo"
    assert sum(1 for r in rows if r["sentinela"] == "true") == 1
    assert all(r["sentinela"] == "false" for r in rows if r["codigo"] != "PLE-9999/2025")
    assert "sentinela" in caplog.text
    # a regra não pega ementas legítimas que só mencionam "teste"
    assert not parse.is_sentinela(540, 'Dispõe sobre a realização do "Teste da Orelinha"')
    assert parse.is_sentinela(1, "documento de teste")


def test_prop_interna_short_record_skipped(caplog):
    """Registro truncado (menos campos que o cabeçalho) não pode derrubar o parser."""
    raw = PROP_FIXTURE.read_bytes() + b'"";"PLE-9999/2025";"A"\r\n'
    rows = parse.parse_prop_interna(raw, "x.csv")
    assert len(rows) == 96
    assert "campos a menos" in caplog.text


# ---- parse resumo ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def resumo_2025():
    return parse.parse_resumo(RESUMO_2025.read_bytes(), RESUMO_2025.name)


def test_resumo_2025_totals(resumo_2025):
    assert all(r["ano"] == 2025 for r in resumo_2025)
    assert sum(r["quantidade"] for r in resumo_2025) == 2037
    por_autor = {}
    for r in resumo_2025:
        por_autor[r["autor_fonte"]] = por_autor.get(r["autor_fonte"], 0) + r["quantidade"]
    assert por_autor["Aladilce"] == 148
    assert por_autor["Felipe Santana"] == 144
    assert por_autor["André Fraga"] == 124
    assert len(por_autor) == 47
    assert "Total Geral" not in por_autor


def test_resumo_2025_tipos(resumo_2025):
    tipos = {r["tipo"] for r in resumo_2025}
    assert tipos == {"MOC", "PDL", "PEL", "PIN", "PLC", "PLE", "PRE", "REP", "RUP", "VTO"}
    assert "Total" not in tipos
    alad = {r["tipo"]: r["quantidade"] for r in resumo_2025 if r["autor_fonte"] == "Aladilce"}
    assert alad == {"MOC": 62, "PIN": 12, "PLE": 15, "PRE": 3, "REP": 52, "RUP": 4}
    por_tipo = {}
    for r in resumo_2025:
        por_tipo[r["tipo"]] = por_tipo.get(r["tipo"], 0) + r["quantidade"]
    assert por_tipo["PLE"] == 580 and por_tipo["PIN"] == 609 and por_tipo["VTO"] == 7


def test_resumo_2026_header_differs():
    """2026 não tem as colunas PEL e VTO: o parser tem que ler o cabeçalho, não assumir colunas fixas."""
    rows = parse.parse_resumo(RESUMO_2026.read_bytes(), RESUMO_2026.name)
    assert {r["tipo"] for r in rows} == {"MOC", "PDL", "PIN", "PLC", "PLE", "PRE", "REP", "RUP"}
    assert sum(r["quantidade"] for r in rows) == 1550
    alad = sum(r["quantidade"] for r in rows if r["autor_fonte"] == "Aladilce")
    assert alad == 75


def test_resumo_missing_subtotal_warns(caplog):
    """Sem a linha de subtotal, o parser não pode dizer que a soma 'bate'."""
    html = RESUMO_2025.read_text(encoding="utf-8")
    stripped = re.sub(
        r"<tr[^>]*>(?:(?!</tr>).)*scGridSummarySubtotal(?:(?!</tr>).)*</tr>", "", html, flags=re.DOTALL
    )
    assert 'class="scGridSummarySubtotal' in html and 'class="scGridSummarySubtotal' not in stripped
    caplog.set_level(logging.INFO)
    rows = parse.parse_resumo(stripped.encode("utf-8"), "x.html")
    assert sum(r["quantidade"] for r in rows) == 2037
    assert "subtotal ausente" in caplog.text
    assert "bate com subtotal" not in caplog.text


def test_resumo_sorted(resumo_2025):
    keys = [(r["ano"], r["autor_fonte"], r["tipo"]) for r in resumo_2025]
    assert keys == sorted(keys)


# ---- build end to end em tmp_path -----------------------------------------------------------


def test_build_silver(tmp_path):
    bronze = tmp_path / "bronze"
    bronze.mkdir()
    (bronze / "prop_interna_2026-10-01.csv").write_bytes(
        b'"";"Proposi\xc3\xa7\xc3\xa3o";"Autor";"Ementa";"Movimentado";"Localiza\xc3\xa7\xc3\xa3o";"Situa\xc3\xa7\xc3\xa3o";"Autor/Requerente/Vistas/Outros"\r\n'
    )
    (bronze / "prop_interna_2026-10-27.csv").write_bytes(PROP_FIXTURE.read_bytes())
    (bronze / "resumo_2025_2026-10-27.html").write_bytes(RESUMO_2025.read_bytes())
    (bronze / "resumo_2026_2026-10-27.html").write_bytes(RESUMO_2026.read_bytes())
    out_prop = tmp_path / "silver" / "proposicao.csv"
    out_res = tmp_path / "silver" / "produtividade_resumo.csv"
    assert parse.build_proposicao(bronze, out_prop) == 96  # usa o snapshot mais recente
    n = parse.build_resumo(bronze, out_res)
    with out_prop.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 96 and list(rows[0]) == parse.PROP_COLUMNS
    assert rows[0]["bronze_file"] == "prop_interna_2026-10-27.csv"
    with out_res.open(encoding="utf-8", newline="") as f:
        rrows = list(csv.DictReader(f))
    assert len(rrows) == n and list(rrows[0]) == parse.RESUMO_COLUMNS
    assert sum(int(r["quantidade"]) for r in rrows if r["ano"] == "2025") == 2037
    assert sum(int(r["quantidade"]) for r in rrows if r["ano"] == "2026") == 1550
