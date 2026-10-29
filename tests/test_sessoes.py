"""Testes offline do catálogo de sessões (LEG_SYS_sessao_ata).

Fixture: ``tests/fixtures/sessoes_sample.html`` = recorte de 60 linhas (23/10/2024 → 16/06/2025) do dump
real ``sessoes_catalogo_2026-10-27.html`` (scripts removidos, rodapé ajustado para ``[1 a 60 de 60]``).
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import ClassVar, Self

import pytest

from spot.collect.sessoes import check_dump, collect, csv_name, csv_rows, html_name
from spot.parse.sessoes import COLUMNS, Sessao, latest_bronze, parse_html, write_silver
from spot.scriptcase import Response, ScriptCaseError

FIXTURE = Path(__file__).parent / "fixtures" / "sessoes_sample.html"
UPLOAD = "http://177.21.11.131:8888/LEG/Upload"


@pytest.fixture(scope="module")
def html_text() -> str:
    return FIXTURE.read_bytes().decode("latin-1")


@pytest.fixture(scope="module")
def sessoes(html_text: str) -> list[Sessao]:
    return parse_html(html_text)


def _row(tipo: str, num: str, data: str, ata: str = "", pron: str = "", i: int = 1) -> str:
    link = lambda u, c: (
        f"<a href=\"javascript:nm_gp_submit5('{u}', '/leg/salvador/LEG_SYS_sessao_ata/', 'x', '_blank', '', '', '')\">"
        "<img/></a>"
        if u
        else "<img/>"
    )
    return (
        f'<TR class="scGridFieldOdd" id="SC_ancor{i}">'
        f'<TD class="scGridFieldOddFont css_ses_tse_codigo_grid_line"><span id="id_sc_field_ses_tse_codigo_{i}">{tipo}</span></TD>'
        f'<TD class="scGridFieldOddFont css_ses_ses_numero_grid_line"><span id="id_sc_field_ses_ses_numero_{i}">{num}</span></TD>'
        f'<TD class="scGridFieldOddFont css_ses_ses_data_grid_line"><span id="id_sc_field_ses_ses_data_{i}">{data}</span></TD>'
        f'<TD class="scGridFieldOddFont css_texto_grid_line">{link(ata, "texto")}</TD>'
        f'<TD class="scGridFieldOddFont css_audio_grid_line"><img/></TD>'
        f'<TD class="scGridFieldOddFont css_video_grid_line"><img/></TD>'
        f'<TD class="scGridFieldOddFont css_pronunciamento_grid_line">{link(pron, "pronunciamento")}</TD>'
        "</TR>"
    )


def _page(rows: list[str]) -> str:
    return f"<html><body><table>{''.join(rows)}</table><span>[1 a {len(rows)} de {len(rows)}]</span></body></html>"


# ---- parser ------------------------------------------------------------------------------------


def test_fixture_counts(sessoes: list[Sessao]) -> None:
    assert len(sessoes) == 60
    assert Counter(s.tipo_sessao for s in sessoes) == {
        "Sessão Ordinária": 58,
        "Sessão Especial": 1,
        "Sessão Solene": 1,
    }
    assert Counter(s.ano for s in sessoes) == {2024: 18, 2025: 42}
    assert Counter(s.tipo_sessao_codigo for s in sessoes) == {1: 58, 2: 1, 3: 1}
    # a fonte tem uma linha "6.789" (05/07/2024): nº com separador de milhar, fora da sequência -> sentinela
    assert [(s.num_sessao, s.data) for s in sessoes if s.sentinela] == [(6789, date(2024, 7, 5))]


def test_2025_03_ordinarias_sao_10_a_18(sessoes: list[Sessao]) -> None:
    """Adendo item 10: março/2025 no catálogo = sessões 10–18 em 9 dias distintos (a 9 fica em fevereiro)."""
    marco = sorted(
        (s for s in sessoes if s.tipo_sessao_codigo == 1 and s.data.year == 2025 and s.data.month == 3),
        key=lambda s: s.num_sessao,
    )
    assert [s.num_sessao for s in marco] == list(range(10, 19))
    assert [s.data.day for s in marco] == [10, 11, 12, 17, 18, 19, 24, 26, 31]
    assert len({s.data for s in marco}) == 9
    nove = [s for s in sessoes if s.tipo_sessao_codigo == 1 and s.ano == 2025 and s.num_sessao == 9]
    assert len(nove) == 1 and nove[0].data == date(2025, 2, 25)


def test_links_das_atas(sessoes: list[Sessao]) -> None:
    assert sum(s.n_pdfs for s in sessoes) == 117
    assert sum(bool(s.ata_urls) for s in sessoes) == 59
    assert sum(bool(s.pronunciamento_urls) for s in sessoes) == 58
    primeira = next(s for s in sessoes if s.ano == 2024 and s.num_sessao == 52)
    assert primeira.ata_urls == (f"{UPLOAD}/7E12AF76-F7DA-462F-8A87-AC2DA664A5A5.pdf",)
    assert primeira.pronunciamento_urls == (f"{UPLOAD}/3C950C09-CB84-420B-8A7E-F62B55C1FA40.pdf",)
    assert all(u.startswith(UPLOAD + "/") and u.endswith(".pdf") for s in sessoes for u in s.ata_urls)


def test_sentinelas_e_numero_com_milhar() -> None:
    page = _page(
        [
            _row("Sessão Ordinária", "888", "27/03/2019", i=1),
            _row("Sessão Ordinária", "999", "23/10/2023", i=2),
            _row("Sessão Ordinária", "6.789", "05/07/2024", i=3),
            _row("Sessão Solene", "12", "05/07/2024", ata=f"{UPLOAD}/A.pdf", pron=f"{UPLOAD}/B.pdf", i=4),
            _row("Sessão Ordinária", "49", "05/09/2018", ata="http://177.21.11.131:8888/LEG/aaa", i=5),
        ]
    )
    s = parse_html(page)
    assert [x.num_sessao for x in s] == [888, 999, 6789, 12, 49]
    assert [x.sentinela for x in s] == [True, True, True, False, False]
    assert s[3].tipo_sessao_codigo == 3 and s[3].n_pdfs == 2
    assert s[4].ata_urls == ("http://177.21.11.131:8888/LEG/aaa",) and s[4].n_pdfs == 0


def test_linhas_invalidas_sao_ignoradas_com_aviso(caplog: pytest.LogCaptureFixture) -> None:
    page = _page(
        [_row("Sessão Ordinária", "", "01/01/2025", i=1), _row("Sessão Ordinária", "x", "2025-01-01", i=2)]
    )
    with caplog.at_level("WARNING"):
        assert parse_html(page) == []
    assert sum("linha ignorada" in r.message for r in caplog.records) == 2


def test_write_silver_sorted_utf8(sessoes: list[Sessao], tmp_path: Path) -> None:
    out = write_silver(list(reversed(sessoes)), "sessoes_catalogo_2026-10-27.html", tmp_path / "sessao.csv")
    with out.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == COLUMNS
    assert len(rows) == 60
    keys = [(int(r["ano"]), int(r["tipo_sessao_codigo"]), int(r["num_sessao"]), r["data"]) for r in rows]
    assert keys == sorted(keys)
    assert rows[0] == {
        "ano": "2024",
        "tipo_sessao_codigo": "1",
        "tipo_sessao": "Sessão Ordinária",
        "num_sessao": "52",
        "data": "2024-10-23",
        "ata_urls": f"{UPLOAD}/7E12AF76-F7DA-462F-8A87-AC2DA664A5A5.pdf",
        "pronunciamento_urls": f"{UPLOAD}/3C950C09-CB84-420B-8A7E-F62B55C1FA40.pdf",
        "n_pdfs": "2",
        "sentinela": "false",
        "bronze_file": "sessoes_catalogo_2026-10-27.html",
    }
    assert "Sessão Ordinária" in out.read_text(encoding="utf-8")


# ---- collector (sem rede) ----------------------------------------------------------------------


def _resp(text: str) -> Response:
    return Response("http://x/", 200, text.encode("latin-1"), 0.1, "POST")


def test_check_dump_aceita_grade_completa(html_text: str) -> None:
    assert check_dump(_resp(html_text), 60) == 60
    assert check_dump(_resp(html_text), None) == 60


def test_check_dump_rejeita_incompleto_ou_divergente(html_text: str) -> None:
    with pytest.raises(ScriptCaseError, match="difere"):
        check_dump(_resp(html_text), 556)
    with pytest.raises(ScriptCaseError, match="incompleto"):
        check_dump(_resp(html_text.replace("[1 a 60 de 60]", "[1 a 20 de 60]")), 60)
    with pytest.raises(ScriptCaseError, match="rodapé"):
        check_dump(_resp("<html>Fatal error</b>: boom<br></html>"), None)
    with pytest.raises(ScriptCaseError, match="linhas de dados"):
        check_dump(_resp(html_text.replace("[1 a 60 de 60]", "[1 a 61 de 61]")), None)


def test_csv_rows_desconta_cabecalho() -> None:
    assert csv_rows(_resp('"Tipo";"No."\r\n"Sessão Ordinária";"1"\r\n"Sessão Solene";"2"\r\n')) == 2
    assert (
        csv_rows(_resp('"Tipo";"No."\r\n"Sessão\r\nOrdinária";"1"\r\n')) == 1
    )  # quebra de linha dentro das aspas
    assert csv_rows(_resp("")) == 0


def test_latest_bronze_escolhe_snapshot_mais_recente(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        latest_bronze(tmp_path)
    for d in ("2026-10-27", "2026-11-02", "2026-10-30"):
        (tmp_path / f"sessoes_catalogo_{d}.html").write_bytes(b"")
    (tmp_path / "sessoes_catalogo_2026-12-01.csv").write_bytes(b"")
    assert latest_bronze(tmp_path).name == "sessoes_catalogo_2026-11-02.html"


def test_collect_idempotente_nao_usa_rede(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    day = date(2026, 10, 27)
    (tmp_path / html_name(day)).write_bytes(b"<html/>")
    (tmp_path / csv_name(day)).write_bytes(b"")

    def boom(*a, **k):
        raise AssertionError("não deveria abrir cliente HTTP")

    monkeypatch.setattr("spot.collect.sessoes.Client", boom)
    summary = collect(day, bronze_dir=tmp_path)
    assert summary["requests"] == 0 and summary["html"] is None
    assert html_name(day) == "sessoes_catalogo_2026-10-27.html"


class _FakeClient:
    """Simula o Client do ScriptCase: registra os inits recebidos e nunca toca a rede."""

    calls: ClassVar[list[tuple[str, str]]] = []

    def __init__(self, html_text: str) -> None:
        self._html = html_text
        self.requests_made = 0

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        pass

    def open_app(self, app: str) -> tuple[str, Response]:
        self.requests_made += 1
        return "4242", _resp("<html>[1 a 20 de 60]</html>")

    def dump_grid(self, app: str, init: str, rows: int = 30000) -> Response:
        self.requests_made += 1
        self.calls.append(("dump", init))
        return _resp(self._html)

    def export_csv(self, app: str, init: str) -> tuple[Response, dict]:
        self.requests_made += 5
        self.calls.append(("export", init))
        body = '"Tipo";"No."\r\n' + '"Sessão Ordinária";"1"\r\n' * 60
        return _resp(body), {"complete": True, "link": "/producao/tmp/x.csv"}


def test_collect_reusa_init_e_escreve_manifest(
    html_text: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adendo item 4: um único script_case_init para dump e export; dois brutos + manifest com 2 linhas."""
    _FakeClient.calls = []
    monkeypatch.setattr("spot.collect.sessoes.Client", lambda: _FakeClient(html_text))
    day = date(2026, 10, 27)

    summary = collect(day, bronze_dir=tmp_path)

    assert _FakeClient.calls == [("dump", "4242"), ("export", "4242")]
    assert summary["total"] == 60 and summary["csv_rows"] == 60 and summary["requests"] == 7
    assert (tmp_path / html_name(day)).read_bytes() == html_text.encode("latin-1")
    manifest = [
        json.loads(line) for line in (tmp_path / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [m["file"] for m in manifest] == [html_name(day), csv_name(day)]
    assert {m["params"]["init"] for m in manifest} == {"4242"}
    assert manifest[0]["params"]["total"] == 60 and manifest[1]["params"]["rows"] == 60
    assert all(m["sha256"] and m["bytes"] > 0 and m["coletado_em"] for m in manifest)

    # segunda rodada: nada a fazer, nenhum request, manifest intacto
    _FakeClient.calls = []
    again = collect(day, bronze_dir=tmp_path)
    assert again["requests"] == 0 and _FakeClient.calls == []
    assert len((tmp_path / "manifest.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_collect_rejeita_dump_divergente(
    html_text: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Se o dump não bate com o total da abertura, nada é gravado no bronze."""

    class _Divergente(_FakeClient):
        def open_app(self, app: str) -> tuple[str, Response]:
            return "1", _resp("<html>[1 a 20 de 556]</html>")

    monkeypatch.setattr("spot.collect.sessoes.Client", lambda: _Divergente(html_text))
    with pytest.raises(ScriptCaseError, match="difere"):
        collect(date(2026, 10, 27), bronze_dir=tmp_path)
    assert not list(tmp_path.iterdir())
