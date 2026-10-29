"""Testes offline da frequência: coletor (funções puras) e parser, sobre fixtures reais."""

from __future__ import annotations

import csv
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Self

import pytest

from spot.collect import frequencia as collect
from spot.parse import frequencia as parse
from spot.scriptcase import Response, ScriptCaseError, grid_total

FIX = Path(__file__).parent / "fixtures"
FIXTURE_CSV = FIX / "frequencia_2025-03_tipo1.csv"


def _latin1(name: str) -> str:
    return (FIX / name).read_bytes().decode("latin-1")


# ---- coletor: parsing das respostas ----------------------------------------------------------


def test_discover_months_from_root() -> None:
    root = _latin1("frequencia_root_snippet.html")
    assert collect.discover_months(root) == ["2025-01", "2025-02", "2026-09", "2026-10"]
    assert collect.discover_months(root, since="2018-01")[0] == "2018-05"
    assert collect.discover_months(root, until="2025-12") == ["2025-01", "2025-02"]
    assert grid_total(root) == 23516


def test_discover_months_fails_loudly_on_empty_root() -> None:
    with pytest.raises(ScriptCaseError, match="sem op"):
        collect.discover_months("<html><body>Fatal error</body></html>")
    # since/until que excluem tudo não é erro: a raiz listou meses, só não há alvo
    assert collect.discover_months(_latin1("frequencia_root_snippet.html"), since="2027-01") == []


def test_tipo_options_from_month_response() -> None:
    nav = _latin1("frequencia_nav_month_snippet.txt")
    assert collect.tipo_options(nav) == [(1, "Sessão Ordinária")]
    assert grid_total(nav) == 430


def test_tipo_options_decodes_js_unicode_escapes() -> None:
    txt = (
        r"nm_proc_int_search('link','nn','Tipo de Sessão','pre_tse_codigo','4##@@Sessão Extraordinária', 'x', '')"
        r" ... nm_proc_int_search('link','nn','Tipo de Sessão','pre_tse_codigo','1##@@Sessão Ordinária', 'x', '')"
    )
    assert collect.tipo_options(txt) == [(1, "Sessão Ordinária"), (4, "Sessão Extraordinária")]


def test_parms_match_handover_examples() -> None:
    assert (
        collect.month_parm("2025-04")
        == "pre_pre_data_presenca__DL__Mês e Ano__DL__dh__DL__2025-04##@@04/2025 __DL__S"
    )
    assert (
        collect.tipo_parm(1, "Sessão Ordinária")
        == "pre_tse_codigo__DL__Tipo de Sessão__DL__nn__DL__1##@@Sessão Ordinária__DL__S"
    )
    assert collect.bronze_name("2025-03", 1) == "2025-03_tipo1.csv"


def test_count_csv_rows_on_fixture() -> None:
    header, rows = collect.count_csv_rows(FIXTURE_CSV.read_bytes())
    assert header == collect.CSV_HEADER
    assert rows == 430


# ---- parser ----------------------------------------------------------------------------------


@pytest.fixture
def bronze_dir(tmp_path: Path) -> Path:
    d = tmp_path / "frequencia"
    d.mkdir()
    shutil.copy(FIXTURE_CSV, d / "2025-03_tipo1.csv")
    return d


def test_parse_fixture_counts(bronze_dir: Path) -> None:
    rows = parse.parse_file(bronze_dir / "2025-03_tipo1.csv")
    assert len(rows) == 430
    assert Counter(r["status"] for r in rows) == {"Presente": 377, "Licenciado": 37, "Ausente": 16}
    assert sorted({r["num_sessao"] for r in rows}) == list(range(9, 19))
    assert len({r["nome"] for r in rows}) == 43
    assert {r["ano"] for r in rows} == {2025}
    assert {r["mes_ref"] for r in rows} == {"2025-03"}
    assert {r["tipo_sessao_codigo"] for r in rows} == {1}
    assert {r["tipo_sessao"] for r in rows} == {"Sessão Ordinária"}
    assert not any(r["sentinela"] for r in rows)
    assert all(r["bronze_file"] == "2025-03_tipo1.csv" for r in rows)


def test_parse_normalizes_names_keeps_source(bronze_dir: Path) -> None:
    rows = parse.parse_file(bronze_dir / "2025-03_tipo1.csv")
    double = [r for r in rows if "  " in r["nome_fonte"]]
    assert double, "fixture deveria ter 'Randerson  Leal' com espaço duplo"
    assert all(r["nome"] == "Randerson Leal" for r in double)
    assert all("  " not in r["nome"] for r in rows)
    assert any(r["nome"] == "Téo Senna" for r in rows)  # acentos decodificados de latin-1


def test_parse_sentinel_and_sort_and_silver(tmp_path: Path, bronze_dir: Path) -> None:
    extra = bronze_dir / "2025-04_tipo3.csv"
    extra.write_bytes(
        (
            '"No. da Sessão";"Ano da Sessão";"Parlamentar";"Status"\r\n'
            '"999";"2025";"Beca";"Presente"\r\n'
            '"2";"2025";"Zé  Último";"Ausente"\r\n'
            '"888";"2025";"Aladilce";"Licenciado"\r\n'
            '"2";"2025";"Aladilce";"Presente"\r\n'
        ).encode("latin-1")
    )
    rows = parse.parse_dir(bronze_dir)
    assert len(rows) == 434
    assert rows == sorted(rows, key=parse.sort_key)
    tipo3 = [r for r in rows if r["tipo_sessao_codigo"] == 3]
    assert [(r["num_sessao"], r["nome"]) for r in tipo3] == [
        (2, "Aladilce"),
        (2, "Zé Último"),
        (888, "Aladilce"),
        (999, "Beca"),
    ]
    assert [r["sentinela"] for r in tipo3] == [False, False, True, True]
    assert tipo3[0]["tipo_sessao"] == "Sessão Solene"

    out = parse.write_silver(rows, tmp_path / "presenca.csv")
    raw = out.read_bytes()
    assert b"\r\n" not in raw
    with out.open(encoding="utf-8", newline="") as f:
        silver = list(csv.DictReader(f))
    assert list(silver[0].keys()) == parse.COLUMNS
    assert len(silver) == 434
    assert {r["sentinela"] for r in silver} == {"true", "false"}
    assert sum(r["sentinela"] == "true" for r in silver) == 2
    assert any(r["nome"] == "Zé Último" and r["nome_fonte"] == "Zé  Último" for r in silver)


def test_parse_rejects_bad_status_and_header(tmp_path: Path) -> None:
    bad = tmp_path / "2025-05_tipo1.csv"
    bad.write_bytes(
        b'"No. da Sess\xe3o";"Ano da Sess\xe3o";"Parlamentar";"Status"\r\n"1";"2025";"X";"Faltou"\r\n'
    )
    with pytest.raises(ValueError, match="status desconhecido"):
        parse.parse_file(bad)
    bad.write_bytes(b'"a";"b"\r\n"1";"2"\r\n')
    with pytest.raises(ValueError, match="cabe"):
        parse.parse_file(bad)
    with pytest.raises(ValueError, match="fora do padr"):
        parse.parse_file(tmp_path / "manifest.csv")


def test_summarize(bronze_dir: Path) -> None:
    s = parse.summarize(parse.parse_dir(bronze_dir))
    assert s == {
        "linhas": 430,
        "por_ano": {2025: 430},
        "status": {"Ausente": 16, "Licenciado": 37, "Presente": 377},
        "sentinelas": 0,
        "nomes": 43,
    }


# ---- coletor: idempotência / --force / validação, com cliente falso (sem rede) -------------------


class _FakeClient:
    """Imita spot.scriptcase.Client com as respostas das fixtures. 7 requests por combinação
    (open_app, mês, tipo, export_ctrl, geração, poll, csv), como o cliente real."""

    csv_bytes = FIXTURE_CSV.read_bytes()
    bad_export = False

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.requests_made = 0
        self.inits: list[str] = []

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        pass

    def _resp(self, text: str) -> Response:
        return Response("http://fake/", 200, text.encode("latin-1"), 0.0)

    def open_app(self, app: str) -> tuple[str, Response]:
        self.requests_made += 1
        init = str(1000 + self.requests_made)
        self.inits.append(init)
        return init, self._resp(_latin1("frequencia_root_snippet.html"))

    def navigate(self, app: str, init: str, parm: str) -> Response:
        assert init == self.inits[-1], "init misturado"
        self.requests_made += 1
        return self._resp(_latin1("frequencia_nav_month_snippet.txt"))

    def filter_total(self, app: str, init: str, parm: str) -> int:
        assert init == self.inits[-1], "init misturado"
        self.requests_made += 1
        return 430

    def export_csv(self, app: str, init: str) -> tuple[Response, dict]:
        assert init == self.inits[-1], "init misturado"
        self.requests_made += 4
        content = self.csv_bytes
        if self.bad_export:
            content = content.rsplit(b"\r\n", 2)[0] + b"\r\n"  # perde a última linha
        return Response("http://fake/x.csv", 200, content, 0.0), {"link": "/x.csv", "complete": True}


def _manifest(dir_: Path) -> list[dict]:
    return [
        json.loads(line) for line in (dir_ / "manifest.jsonl").read_text("utf-8").splitlines() if line.strip()
    ]


def test_collect_is_idempotent_and_force_recollects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collect, "Client", _FakeClient)
    d = tmp_path / "frequencia"

    s1 = collect.collect(since="2025-02", until="2025-02", dir_=d)
    assert s1["files"] == 1 and s1["skipped"] == 0 and s1["errors"] == []
    assert s1["requests"] == 1 + 7  # raiz (descoberta) + 7 da combinação
    assert s1["rows"] == 430 and s1["grid_total_sem_filtro"] == 23516
    assert (d / "2025-02_tipo1.csv").read_bytes() == FIXTURE_CSV.read_bytes()
    m = _manifest(d)
    assert len(m) == 1 and m[0]["file"] == "2025-02_tipo1.csv"
    assert m[0]["params"]["ym"] == "2025-02" and m[0]["params"]["tipo_codigo"] == 1
    assert m[0]["params"]["grid_total"] == m[0]["params"]["csv_rows"] == 430
    assert m[0]["params"]["tipos_disponiveis"] == [1] and m[0]["sha256"]

    # 2ª execução: só a raiz é pedida; o mês inteiro é pulado pelo manifest
    s2 = collect.collect(since="2025-02", until="2025-02", dir_=d)
    assert s2["files"] == 0 and s2["skipped"] == 1 and s2["requests"] == 1
    assert len(_manifest(d)) == 1

    # --force: refaz, substitui o arquivo e acrescenta uma linha ao manifest
    s3 = collect.collect(since="2025-02", until="2025-02", force=True, dir_=d)
    assert s3["files"] == 1 and s3["skipped"] == 0 and s3["requests"] == 8
    assert len(_manifest(d)) == 2 and (d / "2025-02_tipo1.csv").exists()


def test_collect_rejects_csv_shorter_than_grid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Bad(_FakeClient):
        bad_export = True

    monkeypatch.setattr(collect, "Client", Bad)
    d = tmp_path / "frequencia"
    s = collect.collect(since="2025-02", until="2025-02", dir_=d)
    assert s["files"] == 0 and len(s["errors"]) == 1 and "429 linhas != total da grade 430" in s["errors"][0]
    assert not (d / "2025-02_tipo1.csv").exists() and not (d / "manifest.jsonl").exists()
