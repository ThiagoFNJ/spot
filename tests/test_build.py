"""Testes offline de ``spot.build`` e ``spot.metrics.presenca``.

Silver/seeds sintéticos pequenos escritos em ``tmp_path`` (sem rede, sem depender dos CSVs reais), mais um teste
de integração que roda o build real quando ``data/silver/presenca.csv`` existe.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import duckdb
import pytest

from spot.build import BuildError, build, csv_tables, unresolved_names
from spot.config import SEEDS, SILVER
from spot.metrics import presenca as mp

PRESENCA_COLS = [
    "mes_ref",
    "tipo_sessao_codigo",
    "tipo_sessao",
    "num_sessao",
    "ano",
    "nome_fonte",
    "nome",
    "status",
    "sentinela",
    "bronze_file",
]
SESSAO_COLS = [
    "ano",
    "tipo_sessao_codigo",
    "tipo_sessao",
    "num_sessao",
    "data",
    "ata_urls",
    "pronunciamento_urls",
    "n_pdfs",
    "sentinela",
    "bronze_file",
]
ALIAS_COLS = ["alias", "fonte", "vereador_id", "valido_de", "valido_ate", "confianca", "observacao"]
DIM_COLS = [
    "vereador_id",
    "nome_parlamentar",
    "nome_civil",
    "partido",
    "situacao",
    "gabinete_cc_codigo",
    "legislatura",
    "fonte_url",
    "confianca",
    "observacao",
]

# 12 sessões ordinárias de 2025 + 1 solene + 1 sentinela 999; 3 sessões ordinárias de 2026.
VEREADORES = {
    "Ana": ("ana", "Ana Silva", "PT"),
    "Beto  Lima": ("beto", "Beto Lima", "PP"),  # espaço duplo só em nome_fonte
    "Caio": ("caio", "Caio Souza", "PL"),
}


def _write(path: Path, cols: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def _presenca_rows() -> list[dict]:
    rows = []

    def add(
        ano: int, tipo: int, num: int, nome_fonte: str, status: str, mes: str, sentinela: bool = False
    ) -> None:
        rows.append(
            {
                "mes_ref": mes,
                "tipo_sessao_codigo": tipo,
                "tipo_sessao": {1: "Sessão Ordinária", 3: "Sessão Solene"}[tipo],
                "num_sessao": num,
                "ano": ano,
                "nome_fonte": nome_fonte,
                "nome": " ".join(nome_fonte.split()),
                "status": status,
                "sentinela": "true" if sentinela else "false",
                "bronze_file": f"{mes}_tipo{tipo}.csv",
            }
        )

    for n in range(1, 13):
        mes = f"2025-{(n - 1) // 4 + 2:02d}"
        # Ana: 12 em exercício, 3 ausências (sessões 1-3) -> taxa 9/12 = 0.75; 3/12 = 0.25 < 1/3
        add(2025, 1, n, "Ana", "Ausente" if n <= 3 else "Presente", mes)
        # Beto: 5 ausências (1-5), 4 licenciado (9-12), 3 presentes -> base 8 < 10 => sem_dado; 5/12 >= 1/3 => alerta
        status = "Ausente" if n <= 5 else ("Licenciado" if n >= 9 else "Presente")
        add(2025, 1, n, "Beto  Lima", status, mes)
        # Caio: só sessões 1-10, 10 presentes -> taxa 1.0, base 10 (limite inclusivo)
        if n <= 10:
            add(2025, 1, n, "Caio", "Presente", mes)
    # Solene 1/2025 com duplicata exata (como Kel Torres na 3/2025)
    add(2025, 3, 1, "Ana", "Presente", "2025-02")
    add(2025, 3, 1, "Ana", "Presente", "2025-02")
    # Sentinela 999 na grade
    add(2025, 1, 999, "Ana", "Ausente", "2025-04", sentinela=True)
    # 2026 YTD: 3 ordinárias, Ana 1 ausência (1/3 => alerta no limite), Caio 3 presentes
    for n in range(1, 4):
        add(2026, 1, n, "Ana", "Ausente" if n == 1 else "Presente", "2026-02")
        add(2026, 1, n, "Caio", "Presente", "2026-02")
    return rows


def _sessao_rows() -> list[dict]:
    rows = []
    for n in range(1, 13):
        rows.append(_sessao(2025, 1, n, f"2025-{(n - 1) // 4 + 2:02d}-{(n - 1) % 4 * 7 + 1:02d}"))
    rows.append(_sessao(2025, 3, 1, "2025-02-20"))
    rows.append(_sessao(2025, 1, 999, "2025-04-30", sentinela=True))
    for n in range(1, 4):
        rows.append(_sessao(2026, 1, n, f"2026-02-{n:02d}"))
    rows.append(_sessao(2026, 1, 4, "2026-03-01"))  # catálogo adiantado em relação à grade
    return rows


def _sessao(ano: int, tipo: int, num: int, data: str, sentinela: bool = False) -> dict:
    return {
        "ano": ano,
        "tipo_sessao_codigo": tipo,
        "tipo_sessao": {1: "Sessão Ordinária", 3: "Sessão Solene"}[tipo],
        "num_sessao": num,
        "data": data,
        "ata_urls": "",
        "pronunciamento_urls": "",
        "n_pdfs": 0,
        "sentinela": "true" if sentinela else "false",
        "bronze_file": "cat.html",
    }


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    silver, seeds = tmp_path / "silver", tmp_path / "seeds"
    silver.mkdir()
    seeds.mkdir()
    _write(silver / "presenca.csv", PRESENCA_COLS, _presenca_rows())
    _write(silver / "sessao.csv", SESSAO_COLS, _sessao_rows())
    _write(
        seeds / "vereador_alias.csv",
        ALIAS_COLS,
        [
            {
                "alias": " ".join(k.split()),
                "fonte": "frequencia",
                "vereador_id": v[0],
                "valido_de": "2025-01-01",
                "valido_ate": "",
                "confianca": "alta",
                "observacao": "",
            }
            for k, v in VEREADORES.items()
        ]
        + [
            {
                "alias": "Ana",
                "fonte": "comissao",
                "vereador_id": "ana",
                "valido_de": "",
                "valido_ate": "",
                "confianca": "alta",
                "observacao": "outra fonte, não entra no join",
            }
        ],
    )
    _write(
        seeds / "vereador_dim.csv",
        DIM_COLS,
        [
            {
                "vereador_id": v[0],
                "nome_parlamentar": v[1],
                "nome_civil": "",
                "partido": v[2],
                "situacao": "titular",
                "gabinete_cc_codigo": "",
                "legislatura": "2025-2028",
                "fonte_url": "",
                "confianca": "alta",
                "observacao": "",
            }
            for v in VEREADORES.values()
        ],
    )
    return silver, seeds


@pytest.fixture
def db(dirs: tuple[Path, Path]) -> Path:
    silver, seeds = dirs
    return build(silver, seeds)


def test_csv_tables_nomes_e_duplicata(dirs: tuple[Path, Path]) -> None:
    silver, seeds = dirs
    assert list(csv_tables(silver, seeds)) == ["presenca", "sessao", "vereador_alias", "vereador_dim"]
    (seeds / "presenca.csv").write_text("a\n1\n", encoding="utf-8")
    with pytest.raises(BuildError, match="duplicada"):
        csv_tables(silver, seeds)


def test_build_cria_tabelas_e_recria_do_zero(dirs: tuple[Path, Path]) -> None:
    silver, seeds = dirs
    db_path = build(silver, seeds)
    assert db_path == silver / "spot.duckdb"
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tabelas = {
            r[0]
            for r in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_catalog = 'spot' AND table_schema = 'main'"
            ).fetchall()
        }
        assert tabelas == {"presenca", "sessao", "vereador_alias", "vereador_dim", "presenca_mvp"}
        assert con.execute("SELECT count(*) FROM presenca").fetchone()[0] == len(_presenca_rows())
        assert (
            con.execute(
                "SELECT data_type FROM information_schema.columns WHERE table_name='sessao' AND column_name='data'"
            ).fetchone()[0]
            == "DATE"
        )
        assert (
            con.execute(
                "SELECT data_type FROM information_schema.columns WHERE table_name='presenca' AND column_name='sentinela'"
            ).fetchone()[0]
            == "BOOLEAN"
        )
    finally:
        con.close()
    # segunda execução recria do zero (sem erro de tabela existente, mesmo conteúdo)
    con2 = duckdb.connect(str(build(silver, seeds)), read_only=True)
    try:
        assert (
            con2.execute("SELECT count(*) FROM presenca_mvp").fetchone()[0] == len(_presenca_rows()) - 1
        )  # 1 duplicata removida
    finally:
        con2.close()


def test_presenca_mvp_join_dedupe_flags(db: Path) -> None:
    con = duckdb.connect(str(db), read_only=True)
    try:
        # alias resolve o nome normalizado; nome_fonte preserva o espaço duplo
        assert con.execute(
            "SELECT DISTINCT vereador_id FROM presenca_mvp WHERE nome_fonte = 'Beto  Lima'"
        ).fetchall() == [("beto",)]
        assert con.execute("SELECT count(*) FROM presenca_mvp WHERE vereador_id IS NULL").fetchone()[0] == 0
        # data da sessão vinda do catálogo
        assert con.execute(
            "SELECT data_sessao FROM presenca_mvp WHERE ano=2025 AND tipo_sessao_codigo=1 AND num_sessao=5 AND vereador_id='ana'"
        ).fetchone()[0] == date(2025, 3, 1)
        # duplicata exata da solene reduzida a 1 linha com n_linhas_fonte = 2
        assert con.execute(
            "SELECT count(*), max(n_linhas_fonte) FROM presenca_mvp WHERE tipo_sessao_codigo=3"
        ).fetchone() == (1, 2)
        # sentinela 999: mantida, marcada, fora de em_exercicio
        assert con.execute(
            "SELECT sentinela, em_exercicio FROM presenca_mvp WHERE num_sessao=999"
        ).fetchall() == [(True, False)]
        assert (
            con.execute("SELECT count(*) FROM presenca_mvp WHERE em_exercicio").fetchone()[0]
            == len(_presenca_rows()) - 2
        )
        assert con.execute("SELECT count(*) FROM presenca_mvp WHERE NOT no_catalogo").fetchone()[0] == 0
    finally:
        con.close()


def test_build_falha_com_nome_sem_alias(dirs: tuple[Path, Path]) -> None:
    silver, seeds = dirs
    rows = _presenca_rows()
    rows.append({**rows[0], "nome_fonte": "Zé Ninguém", "nome": "Zé Ninguém"})
    rows.append(
        {**rows[0], "nome_fonte": "Antigo", "nome": "Antigo", "ano": 2019, "mes_ref": "2019-03"}
    )  # pré-MVP: ignorado
    _write(silver / "presenca.csv", PRESENCA_COLS, rows)
    with pytest.raises(BuildError, match=r"1 nome\(s\).*Zé Ninguém"):
        build(silver, seeds)
    con = duckdb.connect()
    con.execute(f"CREATE TABLE presenca AS SELECT * FROM read_csv('{silver / 'presenca.csv'}', header=true)")
    con.execute(
        f"CREATE TABLE vereador_alias AS SELECT * FROM read_csv('{seeds / 'vereador_alias.csv'}', header=true)"
    )
    assert unresolved_names(con) == ["Zé Ninguém"]


def test_build_sem_csv(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    with pytest.raises(BuildError, match="nenhum CSV"):
        build(tmp_path / "a", tmp_path / "b")


def test_metrica_presenca(db: Path) -> None:
    con = duckdb.connect(str(db))
    try:
        assert mp.compute(con) == 5  # ana/beto/caio 2025 + ana/caio 2026
        m = {(r["vereador_id"], r["ano"]): r for r in mp._rows(con, "SELECT * FROM metrica_presenca")}
        ana = m[("ana", 2025)]
        assert (
            ana["sessoes_ordinarias_em_exercicio"],
            ana["presentes"],
            ana["ausentes"],
            ana["licenciado"],
        ) == (12, 9, 3, 0)
        assert ana["taxa_presenca"] == 0.75 and ana["sem_dado"] is False
        assert ana["ordinarias_do_ano"] == 12 and ana["alerta_lom27"] is False  # 3/12 < 1/3
        beto = m[("beto", 2025)]
        assert (beto["presentes"], beto["ausentes"], beto["licenciado"]) == (3, 5, 4)
        assert beto["sem_dado"] is True and beto["taxa_presenca"] is None  # base 8 < 10
        assert beto["alerta_lom27"] is True  # 5/12 >= 1/3 mesmo com sem_dado
        caio = m[("caio", 2025)]
        assert (
            caio["sem_dado"] is False
            and caio["taxa_presenca"] == 1.0
            and caio["sessoes_ordinarias_em_exercicio"] == 10
        )
        ana26 = m[("ana", 2026)]
        assert (
            ana26["ordinarias_do_ano"] == 3 and ana26["ausentes"] == 1 and ana26["alerta_lom27"] is True
        )  # 1/3 >= 1/3
        assert ana26["sem_dado"] is True
        # a sentinela 999 e a solene não entram
        assert all(r["sessoes_ordinarias_em_exercicio"] <= 12 for r in m.values())
        # ranking: mais faltas primeiro; empate desempata por taxa menor
        assert [r["vereador_id"] for r in mp.ranking_faltas(con, 2025)] == ["beto", "ana", "caio"]
        assert [r["vereador_id"] for r in mp.ranking_faltas(con, 2025, top=1)] == ["beto"]
    finally:
        con.close()


def test_spearman() -> None:
    assert mp.spearman([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)
    assert mp.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert mp.spearman([1, 2], [1, 2]) is None
    assert mp.spearman([1, 1, 1], [1, 2, 3]) is None
    assert mp.spearman([1, 2, 3], [1, 2]) is None
    # empates em média: ranks de [7, 7, 6] = [1.5, 1.5, 3]
    assert mp._ranks([7, 7, 6]) == [1.5, 1.5, 3.0]
    assert mp.spearman([16, 9, 8, 7, 7, 6], [15, 9, 8, 7, 7, 6]) == pytest.approx(1.0)


def test_comparar_imprensa_e_relatorio(db: Path) -> None:
    con = duckdb.connect(str(db))
    try:
        mp.compute(con)
        cmp_ = mp.comparar_imprensa(con, 2025, {"Beto Lima": 4, "Ana": 3, "Fulano": 2})
        assert cmp_["nomes_comuns"] == ["Ana", "Beto Lima"]
        assert cmp_["nao_encontrados"] == ["Fulano"]
        assert cmp_["deltas"] == {"Ana": 0, "Beto Lima": 1}
        assert cmp_["max_abs_delta"] == 1
        assert cmp_["spearman"] is None  # só 2 pares
        assert cmp_["top_spot_fora_da_imprensa"] == ["Caio"]
        texto = mp.render_report(con, hoje=date(2026, 10, 27))
        assert "## Ranking de faltas 2025" in texto and "## Ranking de faltas 2026 (YTD)" in texto
        assert (
            "| 1 | Beto Lima | PP | titular | 12 | 3 | 5 | 4 | sem dado | 5/12 = 41.7% | **ALERTA** |"
            in texto
        )
        assert "4/2026 (2026-03-01)" in texto  # catálogo adiantado listado nas ressalvas
        assert "Panorama da Bahia" in texto
    finally:
        con.close()


def test_run_grava_relatorio(db: Path, tmp_path: Path) -> None:
    out = mp.run(db, tmp_path / "rel" / "presenca.md", hoje=date(2026, 10, 27))
    assert out.exists() and out.read_text(encoding="utf-8").startswith("# Presença bruta")
    con = duckdb.connect(str(db), read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM metrica_presenca").fetchone()[0] == 5
    finally:
        con.close()


REAL = (
    SILVER / "presenca.csv",
    SILVER / "sessao.csv",
    SEEDS / "vereador_alias.csv",
    SEEDS / "vereador_dim.csv",
)


@pytest.mark.skipif(not all(p.exists() for p in REAL), reason="silver/seeds reais ausentes")
def test_build_real_em_tmp(tmp_path: Path) -> None:
    """Integração: o build real monta, resolve todos os nomes e reproduz os totais verificados pelos revisores."""
    db_path = build(SILVER, SEEDS, tmp_path / "spot.duckdb")
    con = duckdb.connect(str(db_path))
    try:
        assert con.execute("SELECT count(*) FROM presenca").fetchone()[0] == 5803
        assert (
            con.execute("SELECT count(*) FROM presenca_mvp").fetchone()[0] == 5802
        )  # Kel Torres 3/2025 solene
        assert (
            con.execute(
                "SELECT count(*) FROM presenca_mvp WHERE vereador_id IS NULL OR NOT no_catalogo"
            ).fetchone()[0]
            == 0
        )
        assert con.execute("SELECT count(DISTINCT vereador_id) FROM presenca_mvp").fetchone()[0] == 50
        mp.compute(con)
        deb = mp._rows(con, "SELECT * FROM metrica_presenca WHERE vereador_id='debora-santana' AND ano=2025")[
            0
        ]
        assert (deb["sessoes_ordinarias_em_exercicio"], deb["ausentes"], deb["ordinarias_do_ano"]) == (
            86,
            16,
            86,
        )
    finally:
        con.close()
