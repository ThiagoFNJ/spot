"""Testes offline do coletor (helpers) e do parser de empenhos sobre ``tests/fixtures/empenhos_sample.html``.

A fixture tem 30 registros reais do snapshot 2026-10-27: as 14 primeiras linhas da página 1 (out/2026) mais 16
casos escolhidos nas outras páginas (anulação com e sem referência, dois meses no objeto, mês sem ano, sem mês,
"VERBA PARLAMENTAR", "MÊS DEJULHO", número em minúsculas, tipo vazio, diária).
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from spot.collect import empenhos as ce
from spot.parse import empenhos as pe

FIXTURE = Path(__file__).parent / "fixtures" / "empenhos_sample.html"


@pytest.fixture(scope="module")
def rows() -> dict[str, dict[str, object]]:
    parsed = pe.parse_snapshot([FIXTURE])
    return {str(r["numero"]): r for r in parsed}


# ---- coletor ---------------------------------------------------------------------------------


def test_page_name_e_n_pages() -> None:
    assert ce.page_name(date(2026, 10, 27), 3) == "empenhos_2026-10-27_p003.html"
    assert ce.n_pages(3903) == 8 and ce.n_pages(500) == 1 and ce.n_pages(501) == 2 and ce.n_pages(0) == 1


def test_count_rows_fixture() -> None:
    assert ce.count_rows(FIXTURE.read_text("utf-8")) == 30


def test_ajax_page_html_concatena_fragmentos() -> None:
    payload = {
        "setVar": [
            {"var": "nm_gp_rec_ini", "value": 1},
            {"var": "nm_gp_rec_fim", "value": 1001},
            {"var": "x", "value": 0},
        ],
        "setValue": [
            {"field": "sc_grid_head", "value": "<table>"},
            {"field": "sc_grid_body", "value": '<TR class="scGridFieldOdd" id="SC_ancor1">Olá</TR>'},
            {"field": "sc_grid_toobar_bot", "value": "[501 a 1000 de 3903]"},
        ],
    }
    html, vars_ = ce.ajax_page_html(json.dumps(payload).encode("ascii"))
    assert "Olá" in html and html.index("<table>") < html.index("SC_ancor1") < html.index("[501 a")
    assert ce.count_rows(html) == 1
    assert vars_ == {"nm_gp_rec_ini": 1, "nm_gp_rec_fim": 1001}
    with pytest.raises(ce.ScriptCaseError, match="sc_grid_body"):
        ce.ajax_page_html(b'{"setValue": [{"field": "sc_grid_head", "value": ""}]}')
    with pytest.raises(ce.ScriptCaseError, match="JSON"):
        ce.ajax_page_html(b"<html>Fatal error")


def test_snapshot_complete(tmp_path: Path) -> None:
    d = date(2026, 10, 27)
    assert not ce.snapshot_complete(d, tmp_path)
    (tmp_path / ce.page_name(d, 1)).write_text(FIXTURE.read_text("utf-8"), "utf-8")  # rodapé [1 a 30 de 30]
    assert ce.snapshot_complete(d, tmp_path)
    (tmp_path / ce.page_name(d, 1)).write_text("[1 a 500 de 3903]", "utf-8")
    assert not ce.snapshot_complete(d, tmp_path)
    for p in range(2, 9):
        (tmp_path / ce.page_name(d, p)).write_text("", "utf-8")
    assert ce.snapshot_complete(d, tmp_path)


# ---- parser ----------------------------------------------------------------------------------


def test_parse_fixture_tamanho_e_colunas(rows: dict[str, dict[str, object]]) -> None:
    assert len(rows) == 30
    assert set(next(iter(rows.values()))) == set(pe.COLUMNS)
    assert all(r["bronze_file"] == FIXTURE.name for r in rows.values())


def test_campos_basicos(rows: dict[str, dict[str, object]]) -> None:
    r = rows["2026NE000755"]
    assert r["data"] == "2026-10-16" and r["ano"] == 2026
    assert r["valor"] == Decimal("37000.00") and r["tipo"] == "Original" and r["modalidade"] == "Ordinário"
    assert r["credor"] == "Debora Santos de Santana" and r["cnpj_cpf"] == ""  # CPF mascarado ``..-``
    assert r["categoria"] == "verba_compensatoria" and r["anulacao"] is False
    assert r["competencia_ref"] == "2026-09" and r["competencias"] == "2026-09"
    assert r["processo"] == "2267/2026" and r["auditoria"] == "14.16.10.20266"  # typo da fonte preservado
    assert str(r["objeto"]).startswith("DESPESAS REFERENTES A VERBA COMPENSATÓRIA")
    pj = rows["2026NE000770"]
    assert (
        pj["categoria"] == "outro"
        and pj["cnpj_cpf"] == "01.736.132/0001-49"
        and pj["valor"] == Decimal("5079.43")
    )
    assert pj["processo"] == "966/2026" and pj["competencia_ref"] == ""


def test_numero_minusculo_normalizado(rows: dict[str, dict[str, object]]) -> None:
    assert "2025NE000510" in rows and rows["2025NE000510"]["credor"] == "Isabela Sousa Santiago"


def test_categorias(rows: dict[str, dict[str, object]]) -> None:
    assert (
        rows["2025NE000540"]["categoria"] == "verba_compensatoria"
    )  # "VERBA PARLAMENTAR DO MÊS DE JUNHO/2025"
    assert rows["2024NE000214"]["categoria"] == "diaria"
    assert rows["2026NE000762"]["categoria"] == "outro"  # 13º salário
    assert pe.categoria("DESPESAS REF. ÀS VERBAS TRABALHISTAS DEVIDAS") == "outro"
    assert pe.categoria("VERBA DE ATIVIDADE PARLAMENTAR DO MÊS DE AGOSTO/2025") == "verba_compensatoria"


@pytest.mark.parametrize(
    ("objeto", "data", "esperado"),
    [
        ("... DO MÊS DE SETEMBRO/2026, CONFORME", "2026-10-16", ["2026-09"]),
        ("... DO MES DE MARÇO/2025, CONFORME", "2025-04-10", ["2025-03"]),
        ("... DO MÊS DE NOVEMBRO DE 2025, CONFORME", "2025-12-04", ["2025-11"]),
        ("... DO MÊS D MAIO/2025, CONFORME", "2025-06-10", ["2025-05"]),
        ("... DO MÊS DEJULHO/2026, CONFORME", "2026-08-07", ["2026-07"]),
        ("... PARLAMENTAR MÊS JANEIRO, CONFORME", "2025-03-11", ["2025-01"]),
        ("... DO MÊS DE MARÇO/, CONFORME", "2025-04-15", ["2025-03"]),
        ("... DO MÊS DE ABRIL, CONFORME", "2025-05-14", ["2025-04"]),
        (
            "... DO MÊS DE DEZEMBRO, CONFORME",
            "2026-01-08",
            ["2025-12"],
        ),  # sem ano e mês posterior → ano anterior
        ("... DOS MESES DE MARÇO E ABRIL/2025, CONFORME", "2025-05-13", ["2025-03", "2025-04"]),
        ("... DE MÊS DE MAIO E JUNHO/2025, CONFORME", "2025-07-11", ["2025-05", "2025-06"]),
        (
            "... DO MÊS DE JULHO/2026, COM UTILIZAÇÃO DE SALDO REMANESCENTE DO MÊS DE JUNHO/2026",
            "2026-08-28",
            ["2026-07"],
        ),
        ("... PARLAMENTAR , CONFORME DETALHAMENTO", "2025-02-26", []),
        ("... DO MÊS DE ABRIL, CONFORME", "", []),  # sem ano no objeto e sem data: não inventa
    ],
)
def test_competencias_regex(objeto: str, data: str, esperado: list[str]) -> None:
    assert pe.competencias(objeto, data) == esperado


def test_competencia_na_fixture(rows: dict[str, dict[str, object]]) -> None:
    assert rows["2025NE000369"]["competencia_ref"] == "2025-04"
    assert rows["2025NE000369"]["competencias"] == "2025-03|2025-04"
    assert rows["2025NE000176"]["competencia_ref"] == "2025-01"  # "MÊS JANEIRO," emitido em março
    assert rows["2025NE000298"]["competencia_ref"] == "2025-03"  # "MÊS DE MARÇO/" sem ano, emitido em abril
    assert rows["2025NE000162"]["competencia_ref"] == "" and rows["2025NE000162"]["data"] == "2025-02-26"
    assert rows["2025NE000955"]["competencia_ref"] == "2025-11"
    assert rows["2026NE000561"]["competencia_ref"] == "2026-07"


def test_anulacao_com_referencia_no_objeto(rows: dict[str, dict[str, object]]) -> None:
    a = rows["2026NE000423"]
    assert a["tipo"] == "Original" and a["anulacao"] is True  # tipo diz Original, objeto diz ANULAÇÃO TOTAL
    assert a["anula_numero"] == "2026NE000417" and a["anula_fonte"] == "objeto"
    # herda categoria e competência do empenho anulado (o próprio objeto não cita verba nem mês)
    assert a["categoria"] == "verba_compensatoria" and a["competencia_ref"] == "2026-05"
    assert rows["2026NE000417"]["anulacao"] is False and rows["2026NE000417"]["valor"] == a["valor"]


def test_anulacao_sem_referencia_por_credor_valor_data(rows: dict[str, dict[str, object]]) -> None:
    a = rows["2025NE000464"]  # objeto "ANULAÇÃO.", tipo Anulação Total, Anderson 43.100 em 17/06/2025
    assert (
        a["anulacao"] is True
        and a["anula_numero"] == "2025NE000453"
        and a["anula_fonte"] == "credor_valor_data"
    )
    assert a["categoria"] == "verba_compensatoria" and a["competencia_ref"] == "2025-05"
    # original (16/06) + anulação (17/06) + reemissão (18/06) do mesmo valor: líquido = 1 × 43.100 em mai/2025
    trio = [rows[n] for n in ("2025NE000453", "2025NE000464", "2025NE000473")]
    assert [r["anulacao"] for r in trio] == [False, True, False]
    liquido = sum(-r["valor"] if r["anulacao"] else r["valor"] for r in trio)
    assert liquido == Decimal("43100.00")


def test_anulacao_sem_alvo_fica_outro(rows: dict[str, dict[str, object]]) -> None:
    a = rows["2025NE000797"]  # anulação parcial de contrato cujo original não está na fixture
    assert a["anulacao"] is True and a["anula_numero"] == "" and a["categoria"] == "outro"
    assert a["processo"] == "1304/2024"


def test_tipo_vazio_e_art_22(rows: dict[str, dict[str, object]]) -> None:
    r = rows["2025NE000613"]
    assert r["tipo"] == "" and r["anulacao"] is False and r["competencia_ref"] == "2025-08"
    assert "ART. 22" in str(r["objeto"]) and r["cnpj_cpf"] == "***.***.***-**"


def test_parse_valor() -> None:
    assert pe.parse_valor("37.000,00") == Decimal("37000.00")
    assert pe.parse_valor("-1.234,56") == Decimal("-1234.56")
    assert pe.parse_valor("2.000.000,00") == Decimal("2000000.00")
    assert pe.parse_valor("") is None and pe.parse_valor("n/d") is None


def test_write_csv_e_build(tmp_path: Path) -> None:
    bronze = tmp_path / "bronze"
    bronze.mkdir()
    (bronze / "empenhos_2026-10-26_p001.html").write_text("<html>velho</html>", "utf-8")
    (bronze / "empenhos_2026-10-27_p001.html").write_bytes(FIXTURE.read_bytes())
    (bronze / "empenhos_2026-10-27_p002.html").write_bytes(FIXTURE.read_bytes())  # mesma página repetida
    out = tmp_path / "empenho.csv"
    assert pe.build(bronze, out) == 30  # dedupe por número entre páginas; snapshot mais recente
    text = out.read_text("utf-8").splitlines()
    assert text[0] == ",".join(pe.COLUMNS)
    assert len(text) == 31
    assert any(",true,2026NE000417,objeto,2026-05,2026-05," in line for line in text)
    assert any(line.startswith("2026NE000755,Original,Ordinário,2026-10-16,2026,37000.00,,") for line in text)


@pytest.mark.parametrize(
    ("objeto", "esperado"),
    [
        # diárias de viagem (objetos reais do snapshot 2026-10-27, encurtados)
        (
            "DIÁRIAS PARA FOZ DO IGUAÇU/PR, NOS DIAS 18, 19, 20 E 21 DE MARÇO DE 2024, A FIM DE PARTICIPAR DO "
            "19º CONGRESSO BRASILEIRO DE PREGOEIROS. SAÍDA - DIA 17/03/2024 ÀS 11:45H",
            "diaria",
        ),
        (
            "DIÁRIAS PARA O VEREADOR LUIZ CARLOS DE SOUZA , PARTICIPAR FORUM PANAMERICANO DE LIBERDADE",
            "diaria",
        ),
        (
            "DIÁRIAS PARA PARA PARTICIPAR DO 24º ENCONTRO NACIONAL DE TAQUIGRAFIA PARLAMENTAR E JUDICIÁRIA",
            "diaria",
        ),
        (
            "DIÁRIAS P/ PARTICIPAR DO XII SIMPÓSIO NACIONAL ONE CURSOS PREVIDÊNCIA DOS SERVIDORES PÚBLICOS",
            "diaria",
        ),
        ("CONCESSÃO DE 3 DIÁRIAS AO SERVIDOR FULANO DE TAL PARA CURSO EM BRASÍLIA", "diaria"),
        ("PAGAMENTO DE DIÁRIA DE VIAGEM, CONFORME PROCESSO Nº 1/2026", "diaria"),
        # assinaturas de jornal: "ENTREGA DIÁRIA" não é diária de viagem (14 empenhos, ~R$ 319 mil)
        (
            "FORNECIMENTO DE 60 (SESSENTA) ASSINATURAS IMPRESSAS, COM ENTREGA DIÁRIA E COM ACESSO DIGITAL "
            "DISPONÍVEL, DO JORNAL A TARDE, PELO PERÍODO DE 12 (DOZE) MESES PARA ESTA CASA LEGISLATIVA",
            "outro",
        ),
        (
            "ESTA NOTA DE EMPENHO COMPLEMENTA A DE Nº 48/2025. FORNECIMENTO DE 60 (SESSENTA) ASSINATURAS "
            "IMPRESSAS, COM ENTREGA DIÁRIA E COM ACESSO DIGITAL DISPONÍVEL, DO JORNAL A TARDE",
            "outro",
        ),
        (
            "FORNECIMENTO DE 60 (SESSENTA) ASSINATURAS IMPRESSAS, COM ENTREGA DIÁRIA DO JORNAL TRIBUNA DA BAHIA, "
            "INCLUINDO LOGIN E SENHA PARA ACESSO ONLINE, PELO PERÍODO DE 12 MESES P/ CMS",
            "outro",
        ),
        ("FORNECIMENTO DE 60 (SESSENTA) EXEMPLARES DIÁRIOS DO JORNAL TRIBUNA DA BAHIA, IMPRESSOS", "outro"),
        # "DIÁRIO OFICIAL" nunca foi diária; palavra solta sem contexto também não
        (
            "PAGAMENTO DE ABONO PARA OS SERVIDORES EFETIVOS DA CÂMARA MUNICIPAL DE SALVADOR, CONFORME ATO DA "
            "MESA DIRETORA Nº 565/2024, PUBLICADO NO DIÁRIO OFICIAL",
            "outro",
        ),
        ("DIÁRIA", "outro"),
        ("LIMPEZA DIÁRIA DAS DEPENDÊNCIAS DA CASA", "outro"),
    ],
)
def test_categoria_diaria_exige_contexto(objeto: str, esperado: str) -> None:
    assert pe.categoria(objeto) == esperado
