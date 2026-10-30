"""Testes offline de ``spot.metrics.custo`` sobre um DuckDB em memória com linhas sintéticas.

Cenário (competências 2025-01..03):
- CC 100 ``1ª SECRETARIA - GAB. VER. ANA`` (ana): 2 assessores CC10 + 1 CC50 -> split mandato/estrutura;
- CC 200 ``GAB. VER. BOB (SUP. VER. TOM)``: tom (licenciado) e bob (suplente) compartilham o código;
  grade: jan só tom, fev bob > tom, mar sem sessão -> herda bob;
- CC 300 ``GAB. VER. CARLA``: sem alias, mas único em ``vereador_dim`` -> resolvido pelo código;
- CC 400 ``GAB. VER. DESCONHECIDO``: sem alias e sem dim -> vereador_id NULL (sinalizado, não descartado);
- CC 900 ``PROJUR``: institucional (folha + 1 estagiário);
- estagiários publicados só em 2025-02; subsídio sintético (1000) vigente a partir de 2025-02-01; teto 50/60;
- empenhos (fixture ``con_verba``): verba de ana em 2025-02 (original + anulação + reemissão = 100), carla 80 em
  2025-02, bob 70 sem mês no objeto (cai no mês da emissão, 2025-03), tom 30 em 2025-03 (não é o ocupante do
  gabinete nesse mês), ``Zé Ninguém`` 55 sem alias, e um empenho ``outro`` de ana que não entra.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest

from spot.build import build
from spot.config import SEEDS, SILVER
from spot.metrics import custo as mc

PARAMS_CSV = """parametro,valor,unidade,tipo,vigencia_de,vigencia_ate,fonte,fonte_url,observacao
subsidio_vereador,1000.00,BRL/mes,valor_legal,2025-02-01,2028-12-31,Lei X,http://x,
verba_compensatoria_teto,50.00,BRL/mes,teto,2025-01-01,2025-12-29,Lei Y,http://y,
verba_compensatoria_teto,60.00,BRL/mes,teto,2025-12-30,,Lei Z,http://z,
"""

MESES = ("2025-01", "2025-02", "2025-03")
CC10 = "3 - CARGO EM COMISSÃO"
EST = "1 - Estatutário"

# (matricula, regime, funcao, proventos, cc_codigo, cc_label, gabinete_vereador)
FOLHA = [
    (1, CC10, "ASSESSOR PARLAMENTAR-G-29 CC10", 9651.25, 100, "1ª SECRETARIA - GAB. VER. ANA", "ANA"),
    (
        2,
        CC10,
        "ASSESSOR PARLAMENTAR ESPECIAL-G-30 CC10",
        14975.91,
        100,
        "1ª SECRETARIA - GAB. VER. ANA",
        "ANA",
    ),
    (3, CC10, "SECRETARIO DE GABINETE CC-50", 4552.07, 100, "1ª SECRETARIA - GAB. VER. ANA", "ANA"),
    (4, CC10, "ASSESSOR PARLAMENTAR-G-10 CC10", 3000.00, 200, "GAB. VER. BOB (SUP. VER. TOM)", "BOB"),
    (5, CC10, "ASSESSOR PARLAMENTAR-G-10 CC10", 3000.00, 300, "GAB. VER. CARLA", "CARLA"),
    (6, CC10, "ASSESSOR PARLAMENTAR-G-10 CC10", 2000.00, 400, "GAB. VER. DESCONHECIDO", "DESCONHECIDO"),
    (7, EST, "PROCURADOR JURIDICO", 29105.19, 900, "PROJUR - COORDENAÇÃO DE PROCURADORIA", None),
    (8, EST, "ASSISTENTE LEGISLATIVO MUNICIPAL", 12000.00, 900, "PROJUR - COORDENAÇÃO DE PROCURADORIA", ""),
]
ESTAGIARIOS = [
    (20, "5 - ESTAGIARIO", "ESTAGIARIO - NIVEL MEDIO", 623.20, 100, "1ª SECRETARIA - GAB. VER. ANA", "ANA"),
    (
        21,
        "5 - ESTAGIARIO",
        "ESTAGIARIO - NIVEL SUPERIOR",
        923.20,
        900,
        "PROJUR - COORDENAÇÃO DE PROCURADORIA",
        None,
    ),
]
ALIAS = [
    ("100 - 1ª SECRETARIA - GAB. VER. ANA", "centro_custo", "ana"),
    ("200 - GAB. VER. BOB (SUP. VER. TOM)", "centro_custo", "bob"),
    ("Ana", "frequencia", "ana"),  # outra fonte: não entra no join
]
DIM = [
    ("ana", "Ana Silva", "PT", "titular", 100),
    ("tom", "Tom Souza", "PP", "licenciado", 200),
    ("bob", "Bob Lima", "PP", "suplente", 200),
    ("carla", "Carla Reis", "PL", "titular", 300),
]
# (vereador_id, data_sessao): jan só tom; fev tom 1 × bob 4; mar sem sessão
GRADE = [
    ("tom", "2025-01-02"),
    ("tom", "2025-01-09"),
    ("tom", "2025-02-03"),
    ("bob", "2025-02-10"),
    ("bob", "2025-02-12"),
    ("bob", "2025-02-17"),
    ("bob", "2025-02-19"),
    ("ana", "2025-01-02"),
    ("ana", "2025-02-03"),
]


# (numero, tipo, data, ano, valor, credor, categoria, anulacao, competencia_ref)
EMPENHOS = [
    (
        "2025NE000001",
        "Original",
        "2025-03-10",
        2025,
        100.0,
        "Ana Silva Civil",
        "verba_compensatoria",
        False,
        "2025-02",
    ),
    (
        "2025NE000002",
        "Anulação Total",
        "2025-03-11",
        2025,
        100.0,
        "Ana Silva Civil",
        "verba_compensatoria",
        True,
        "2025-02",
    ),
    (
        "2025NE000003",
        "Original",
        "2025-03-12",
        2025,
        100.0,
        "Ana Silva Civil",
        "verba_compensatoria",
        False,
        "2025-02",
    ),
    (
        "2025NE000004",
        "Original",
        "2025-03-20",
        2025,
        70.0,
        "Bob Lima Civil",
        "verba_compensatoria",
        False,
        "",
    ),
    (
        "2025NE000005",
        "Original",
        "2025-03-21",
        2025,
        30.0,
        "Tom Souza Civil",
        "verba_compensatoria",
        False,
        "2025-03",
    ),
    (
        "2025NE000006",
        "Original",
        "2025-03-22",
        2025,
        55.0,
        "Zé Ninguém",
        "verba_compensatoria",
        False,
        "2025-03",
    ),
    ("2025NE000007", "Original", "2025-03-23", 2025, 999.0, "Ana Silva Civil", "outro", False, "2025-03"),
    (
        "2025NE000008",
        "Original",
        "2025-02-05",
        2025,
        80.0,
        "Carla Reis",
        "verba_compensatoria",
        False,
        "2025-02",
    ),
]
ALIAS_EMPENHO = [
    ("Ana Silva Civil", "empenho", "ana"),
    ("Bob Lima Civil", "empenho", "bob"),
    ("Tom Souza Civil", "empenho", "tom"),
    ("Carla Reis", "empenho", "carla"),
]


def _add_empenhos(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"CREATE TABLE empenho ({mc.EMPENHO_COLS})")
    con.executemany(
        "INSERT INTO empenho (numero, tipo, data, ano, valor, credor, categoria, anulacao, competencia_ref) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        EMPENHOS,
    )
    con.executemany("INSERT INTO vereador_alias VALUES (?, ?, ?)", ALIAS_EMPENHO)


def _con(tmp_path: Path) -> tuple[duckdb.DuckDBPyConnection, Path]:
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE folha (competencia VARCHAR, matricula BIGINT, regime VARCHAR, funcao VARCHAR, proventos DOUBLE, "
        "centro_custo_codigo BIGINT, centro_custo_label VARCHAR, gabinete_vereador VARCHAR)"
    )
    con.execute("CREATE TABLE estagiarios AS SELECT * FROM folha WHERE false")
    con.executemany(
        "INSERT INTO folha VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [(m, *row) for m in MESES for row in FOLHA]
    )
    con.executemany(
        "INSERT INTO estagiarios VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [("2025-02", *r) for r in ESTAGIARIOS]
    )
    con.execute("CREATE TABLE vereador_alias (alias VARCHAR, fonte VARCHAR, vereador_id VARCHAR)")
    con.executemany("INSERT INTO vereador_alias VALUES (?, ?, ?)", ALIAS)
    con.execute(
        "CREATE TABLE vereador_dim (vereador_id VARCHAR, nome_parlamentar VARCHAR, partido VARCHAR, situacao VARCHAR, "
        "gabinete_cc_codigo BIGINT)"
    )
    con.executemany("INSERT INTO vereador_dim VALUES (?, ?, ?, ?, ?)", DIM)
    con.execute("CREATE TABLE presenca_mvp (vereador_id VARCHAR, data_sessao DATE, em_exercicio BOOLEAN)")
    con.executemany("INSERT INTO presenca_mvp VALUES (?, ?::DATE, true)", GRADE)
    params = tmp_path / "parametros_custo.csv"
    params.write_text(PARAMS_CSV, encoding="utf-8")
    return con, params


@pytest.fixture
def con(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    con, params = _con(tmp_path)
    mc.compute(con, params)
    yield con
    con.close()


@pytest.fixture
def con_verba(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    con, params = _con(tmp_path)
    _add_empenhos(con)
    mc.compute(con, params)
    yield con
    con.close()


def _one(con: duckdb.DuckDBPyConnection, sql: str, *params: object) -> dict:
    rows = mc._rows(con, sql, params)
    assert len(rows) == 1, rows
    return rows[0]


def test_compute_tamanhos(con: duckdb.DuckDBPyConnection) -> None:
    sizes = {
        t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        for t in (
            "custo_gabinete_ocupante",
            "metrica_custo_gabinete",
            "metrica_custo_anual",
            "custo_institucional",
        )
    }
    assert sizes["custo_gabinete_ocupante"] == 4 * 3 == sizes["metrica_custo_gabinete"]
    # ana, tom, bob, carla, NULL (cc 400)
    assert sizes["metrica_custo_anual"] == 5
    # PROJUR: 3 meses de folha + 1 mês de estagiário
    assert sizes["custo_institucional"] == 4


def test_split_assessor_vs_institucional(con: duckdb.DuckDBPyConnection) -> None:
    r = _one(
        con,
        "SELECT * FROM metrica_custo_gabinete WHERE centro_custo_codigo = 100 AND competencia = '2025-02'",
    )
    assert (r["n_servidores"], r["n_assessores_parlamentares"]) == (3, 2)
    assert r["folha_assessores"] == pytest.approx(9651.25 + 14975.91)
    assert r["folha_outros"] == pytest.approx(4552.07)
    assert (r["n_estagiarios"], r["bolsas_estagiarios"]) == (1, pytest.approx(623.20))
    assert r["subsidio"] == 1000.0 and r["verba_compensatoria_teto"] == 50.0
    assert r["custo_observado"] == pytest.approx(1000 + 9651.25 + 14975.91 + 4552.07 + 623.20)
    assert r["custo_com_teto_verba"] == pytest.approx(r["custo_observado"] + 50)
    assert r["verba_compensatoria_observada"] is None and r["diarias"] is None
    assert r["componentes_faltantes"] == "verba_compensatoria, diarias"
    assert (r["vereador_id"], r["nome_parlamentar"], r["ocupante_fonte"]) == ("ana", "Ana Silva", "rotulo")


def test_subsidio_e_estagiarios_sem_vigencia_ou_sem_pdf(con: duckdb.DuckDBPyConnection) -> None:
    jan = _one(
        con,
        "SELECT * FROM metrica_custo_gabinete WHERE centro_custo_codigo = 100 AND competencia = '2025-01'",
    )
    assert jan["subsidio"] is None and jan["n_estagiarios"] is None and jan["bolsas_estagiarios"] is None
    assert jan["custo_observado"] == pytest.approx(9651.25 + 14975.91 + 4552.07)
    assert jan["componentes_faltantes"] == "subsidio, estagiarios, verba_compensatoria, diarias"
    mar = _one(
        con,
        "SELECT * FROM metrica_custo_gabinete WHERE centro_custo_codigo = 100 AND competencia = '2025-03'",
    )
    assert mar["subsidio"] == 1000.0 and mar["n_estagiarios"] is None  # fev publicado, mar não
    # Σ subsídio do mês = um por gabinete ocupado (4 gabinetes, inclusive o sem vereador)
    assert con.execute(
        "SELECT count(subsidio), sum(subsidio) FROM metrica_custo_gabinete WHERE competencia = '2025-02'"
    ).fetchone() == (4, 4000.0)


def test_suplente_atribuido_pela_grade(con: duckdb.DuckDBPyConnection) -> None:
    rows = mc._rows(
        con,
        "SELECT competencia, vereador_id, ocupante_fonte, vereador_id_rotulo, n_candidatos "
        "FROM custo_gabinete_ocupante WHERE centro_custo_codigo = 200 ORDER BY competencia",
    )
    assert [(r["competencia"], r["vereador_id"], r["ocupante_fonte"]) for r in rows] == [
        ("2025-01", "tom", "grade"),
        ("2025-02", "bob", "grade"),
        ("2025-03", "bob", "grade_mes_anterior"),
    ]
    assert all(r["vereador_id_rotulo"] == "bob" and r["n_candidatos"] == 2 for r in rows)
    # o subsídio segue o ocupante
    assert con.execute(
        "SELECT vereador_id, subsidio FROM metrica_custo_gabinete WHERE centro_custo_codigo = 200 ORDER BY competencia"
    ).fetchall() == [("tom", None), ("bob", 1000.0), ("bob", 1000.0)]
    anual = {
        r["vereador_id"]: r
        for r in mc._rows(con, "SELECT * FROM metrica_custo_anual WHERE centro_custo_codigo = 200")
    }
    assert anual["tom"]["meses_com_folha"] == 1 and anual["bob"]["meses_com_folha"] == 2
    assert anual["bob"]["meses_com_subsidio"] == 2 and anual["bob"]["subsidio"] == 2000.0
    assert anual["bob"]["media_mensal_custo_observado"] == pytest.approx(3000 + 1000)
    assert anual["bob"]["situacao"] == "suplente" and anual["tom"]["situacao"] == "licenciado"


def test_gabinete_sem_alias_detectado_nao_descartado(con: duckdb.DuckDBPyConnection) -> None:
    sem = {g["centro_custo_codigo"]: g for g in mc.gabinetes_sem_alias(con)}
    assert set(sem) == {300, 400}
    assert sem[300]["vereador_id_resolvido"] == "carla" and sem[300]["meses"] == 3
    assert sem[400]["vereador_id_resolvido"] is None
    assert con.execute(
        "SELECT DISTINCT ocupante_fonte FROM custo_gabinete_ocupante WHERE centro_custo_codigo = 300"
    ).fetchall() == [("dim_codigo",)]
    # o gabinete 400 continua na métrica (com vereador_id NULL) e no ranking anual
    assert con.execute(
        "SELECT count(*), count(vereador_id) FROM metrica_custo_gabinete WHERE centro_custo_codigo = 400"
    ).fetchone() == (3, 0)
    assert (
        con.execute("SELECT count(*) FROM metrica_custo_anual WHERE vereador_id IS NULL").fetchone()[0] == 1
    )


def test_custo_institucional_nao_descartado(con: duckdb.DuckDBPyConnection) -> None:
    rows = mc._rows(con, "SELECT * FROM custo_institucional ORDER BY competencia, fonte")
    assert [(r["competencia"], r["fonte"], r["n"]) for r in rows] == [
        ("2025-01", "folha", 2),
        ("2025-02", "estagiarios", 1),
        ("2025-02", "folha", 2),
        ("2025-03", "folha", 2),
    ]
    assert all(r["centro_custo_codigo"] == 900 and r["centro_custo_label"].startswith("PROJUR") for r in rows)
    assert rows[0]["total"] == pytest.approx(29105.19 + 12000.00)
    # gabinetes + institucional = folha, mês a mês (a reconciliação já rodou em compute; forçar uma quebra)
    con.execute("DELETE FROM custo_institucional WHERE competencia = '2025-03'")
    with pytest.raises(mc.CustoError, match="folha"):
        mc.reconciliar(con, "folha")


def test_ranking_e_relatorio(con: duckdb.DuckDBPyConnection) -> None:
    rank = mc.ranking_gabinetes(con)
    assert [r["centro_custo_codigo"] for r in rank] == [100, 200, 300, 400]
    assert rank[1]["ocupantes"] == "Tom Souza (1m) → Bob Lima (2m)"
    mesa = mc.mesa_split(con)
    assert (
        len(mesa) == 1
        and mesa[0]["cargo"] == "1ª SECRETARIA"
        and mesa[0]["folha_outros"] == pytest.approx(3 * 4552.07)
    )
    texto = mc.render_report(con, hoje=date(2026, 10, 27))
    assert "# Custo dos gabinetes — 2025" in texto
    assert "| 1 | 100 · 1ª SECRETARIA - GAB. VER. ANA | Ana Silva (3m) | PT | 3 |" in texto
    assert "| 400 | GAB. VER. DESCONHECIDO | 2025-01..2025-03 (3) | **não resolvido** |" in texto
    assert "| 300 | GAB. VER. CARLA | 2025-01..2025-03 (3) | carla |" in texto
    assert "01: Tom Souza (grade); 02: Bob Lima (grade); 03: Bob Lima (grade_mes_anterior)" in texto
    assert "**DIVERGE**" in texto  # sanidade set/2025 não se aplica ao sintético


def test_run_grava_relatorio(tmp_path: Path) -> None:
    con, params = _con(tmp_path)
    con.close()
    db = tmp_path / "t.duckdb"
    con2, _ = _con(tmp_path)
    con2.execute(f"ATTACH '{db}' AS d")
    for t in ("folha", "estagiarios", "vereador_alias", "vereador_dim", "presenca_mvp"):
        con2.execute(f"CREATE TABLE d.{t} AS SELECT * FROM {t}")
    con2.close()
    out = mc.run(db, tmp_path / "rel" / "custo.md", params, hoje=date(2026, 10, 27))
    assert out.exists() and out.read_text(encoding="utf-8").startswith("# Custo dos gabinetes")
    con3 = duckdb.connect(str(db), read_only=True)
    try:
        assert con3.execute("SELECT count(*) FROM metrica_custo_gabinete").fetchone()[0] == 12
        assert con3.execute("SELECT count(*) FROM parametros_custo").fetchone()[0] == 3
    finally:
        con3.close()


def test_parametros_reais_e_sobreposicao(tmp_path: Path) -> None:
    con = duckdb.connect()
    mc.ensure_parametros(con, mc.PARAMS_DEFAULT)
    rows = mc._rows(con, "SELECT * FROM parametros_custo ORDER BY parametro, vigencia_de")
    assert [(r["parametro"], r["valor"]) for r in rows] == [
        ("subsidio_vereador", 26080.98),
        ("verba_compensatoria_teto", 34000.0),
        ("verba_compensatoria_teto", 39000.0),
    ]
    assert all(r["fonte_url"].startswith("http") and r["tipo"] in ("teto", "valor_legal") for r in rows)
    con.close()
    bad = tmp_path / "bad.csv"
    bad.write_text(
        PARAMS_CSV.replace("2025-12-29", "2025-12-31"), encoding="utf-8"
    )  # 34k até 31/12 e 39k desde 30/12 -> sobreposição
    con = duckdb.connect()
    with pytest.raises(mc.CustoError, match="sobrepostas"):
        mc.ensure_parametros(con, bad)
    con.close()


def test_analise_13_sintetica(con: duckdb.DuckDBPyConnection) -> None:
    a = mc.analise_13(con)
    assert a["comuns"] == 0 and a["g29"] == []  # sem nov/dez no sintético: não quebra
    assert [m["competencia"] for m in a["por_mes"]] == ["2025-02", "2025-03"]
    assert all(m["iguais"] == 8 for m in a["por_mes"])


# ---- verba compensatória (empenhos) ----


def test_sem_tabela_empenho_verba_fica_null(con: duckdb.DuckDBPyConnection) -> None:
    assert con.execute("SELECT count(*) FROM metrica_verba_vereador").fetchone()[0] == 0
    assert (
        con.execute(
            "SELECT count(*) FROM metrica_custo_gabinete WHERE verba_compensatoria_observada IS NOT NULL"
        ).fetchone()[0]
        == 0
    )
    assert all(
        "verba_compensatoria" in r[0]
        for r in con.execute("SELECT componentes_faltantes FROM metrica_custo_gabinete").fetchall()
    )


def test_metrica_verba_vereador(con_verba: duckdb.DuckDBPyConnection) -> None:
    rows = {
        (r["vereador_id"], r["competencia"]): r
        for r in mc._rows(con_verba, "SELECT * FROM metrica_verba_vereador")
    }
    assert set(rows) == {
        ("ana", "2025-02"),
        ("carla", "2025-02"),
        ("bob", "2025-03"),
        ("tom", "2025-03"),
        (None, "2025-03"),
    }
    ana = rows[("ana", "2025-02")]
    # original + anulação + reemissão: líquido 100; o empenho ``outro`` de ana não entra
    assert (ana["n_empenhos"], ana["n_anulacoes"], ana["verba_compensatoria_observada"]) == (3, 1, 100.0)
    assert ana["verba_compensatoria_teto"] == 50.0 and ana["nome_parlamentar"] == "Ana Silva"
    assert ana["empenhos"] == "2025NE000001|2025NE000002|2025NE000003"
    bob = rows[("bob", "2025-03")]  # sem competência no objeto → mês da emissão
    assert (bob["n_fallback_mes_emissao"], bob["verba_compensatoria_observada"]) == (1, 70.0)
    assert rows[(None, "2025-03")]["credor"] == "Zé Ninguém"
    assert mc.verba_nao_mapeada(con_verba) == [
        {"credor": "Zé Ninguém", "n_empenhos": 1, "competencias": "2025-03", "total": 55.0}
    ]


def test_verba_entra_no_custo_do_ocupante(con_verba: duckdb.DuckDBPyConnection) -> None:
    fev = _one(
        con_verba,
        "SELECT * FROM metrica_custo_gabinete WHERE centro_custo_codigo = 100 AND competencia = '2025-02'",
    )
    assert fev["verba_compensatoria_observada"] == 100.0 and fev["n_empenhos_verba"] == 3
    assert fev["custo_observado"] == pytest.approx(1000 + 9651.25 + 14975.91 + 4552.07 + 623.20 + 100)
    assert fev["custo_com_teto_verba"] == pytest.approx(1000 + 9651.25 + 14975.91 + 4552.07 + 623.20 + 50)
    assert fev["componentes_faltantes"] == "diarias"
    jan = _one(
        con_verba,
        "SELECT * FROM metrica_custo_gabinete WHERE centro_custo_codigo = 100 AND competencia = '2025-01'",
    )
    # janeiro não tem nenhum empenho de verba na fonte: NULL (não 0) e listado como faltante
    assert jan["verba_compensatoria_observada"] is None and jan["n_empenhos_verba"] is None
    assert jan["componentes_faltantes"] == "subsidio, estagiarios, verba_compensatoria, diarias"
    mar = _one(
        con_verba,
        "SELECT * FROM metrica_custo_gabinete WHERE centro_custo_codigo = 100 AND competencia = '2025-03'",
    )
    # março tem empenhos na fonte (de outros), ana não recebeu: 0, e verba deixa de ser componente faltante
    assert (
        mar["verba_compensatoria_observada"] == 0.0 and mar["componentes_faltantes"] == "estagiarios, diarias"
    )
    carla = _one(
        con_verba,
        "SELECT * FROM metrica_custo_gabinete WHERE centro_custo_codigo = 300 AND competencia = '2025-02'",
    )
    assert (
        carla["verba_compensatoria_observada"] == 80.0
    )  # alias empenho = nome parlamentar, gabinete via dim_codigo


def test_verba_fallback_mes_emissao_segue_ocupante(con_verba: duckdb.DuckDBPyConnection) -> None:
    cc200 = {
        r["competencia"]: r
        for r in mc._rows(con_verba, "SELECT * FROM metrica_custo_gabinete WHERE centro_custo_codigo = 200")
    }
    # bob (ocupante de março pela grade do mês anterior) recebe os 70 do empenho sem mês; tom (30) não é o ocupante
    assert (cc200["2025-03"]["vereador_id"], cc200["2025-03"]["verba_compensatoria_observada"]) == (
        "bob",
        70.0,
    )
    assert cc200["2025-02"]["verba_compensatoria_observada"] == 0.0
    assert cc200["2025-03"]["custo_observado"] == pytest.approx(1000 + 3000 + 70)
    diff = mc.reconciliar_verba(con_verba)
    assert diff == [{"competencia": "2025-03", "mapeada": 100.0, "gabinetes": 70.0, "fora_do_gabinete": 30.0}]


def test_verba_anual_e_ranking(con_verba: duckdb.DuckDBPyConnection) -> None:
    anual = {r["vereador_id"]: r for r in mc._rows(con_verba, "SELECT * FROM metrica_custo_anual")}
    assert (anual["ana"]["meses_com_verba"], anual["ana"]["verba_compensatoria_observada"]) == (2, 100.0)
    assert (
        anual["bob"]["verba_compensatoria_observada"] == 70.0
        and anual["tom"]["verba_compensatoria_observada"] is None
    )
    assert anual["ana"]["custo_observado"] == pytest.approx(
        2 * 1000 + 3 * (9651.25 + 14975.91 + 4552.07) + 623.20 + 100
    )
    assert anual["ana"]["media_mensal_custo_observado"] == pytest.approx(anual["ana"]["custo_observado"] / 3)
    rank = mc.ranking_gabinetes(con_verba)
    # a verba muda o ranking: carla (80) passa à frente de bob (70) na média mensal
    assert [r["centro_custo_codigo"] for r in rank] == [100, 300, 200, 400]
    assert [r["verba_observada"] for r in rank] == [100.0, 80.0, 70.0, 0.0]
    tot = {t["competencia"]: t for t in mc.totais_mensais(con_verba)}
    assert (tot["2025-02"]["com_verba"], tot["2025-02"]["verba_observada"]) == (4, 180.0)
    assert tot["2025-01"]["com_verba"] == 0 and tot["2025-01"]["verba_observada"] is None


def test_siga_check_e_relatorio_verba(con_verba: duckdb.DuckDBPyConnection) -> None:
    siga = mc.siga_check(con_verba)
    assert [s["competencia"] for s in siga] == sorted(mc.SIGA_INDENIZACOES)
    assert all(
        s["por_emissao"] == 0 and s["razao_competencia"] == 0 for s in siga
    )  # sintético não cobre 06/11
    texto = mc.render_report(con_verba, hoje=date(2026, 10, 27))
    assert "## Verba compensatória observada (empenhos)" in texto
    # ana (100) e carla (80) acima do teto sintético de 50
    assert "| 2025-02 | 4 | 1 | 2 | 0 | R$ 180,00 | R$ 80,00 | R$ 100,00 | R$ 50,00 | 2 | 0 |" in texto
    assert "| 2025-03 | 3 | 0 | 2 | 1 | R$ 155,00 |" in texto
    assert "`Zé Ninguém` (1 empenho(s), 2025-03, R$ 55,00)" in texto
    assert "Conciliação SIGA 2025-11" in texto
    assert "| 1 | 100 · 1ª SECRETARIA - GAB. VER. ANA | Ana Silva (3m) | PT | 3 |" in texto


REAL = (
    SILVER / "folha.csv",
    SILVER / "estagiarios.csv",
    SILVER / "presenca.csv",
    SEEDS / "vereador_alias.csv",
)


@pytest.mark.skipif(not all(p.exists() for p in REAL), reason="silver/seeds reais ausentes")
def test_custo_real_em_tmp(tmp_path: Path) -> None:
    """Integração: reproduz os totais de set/2025 do revisor de RH e o Σ subsídio = 43 × 26.080,98 (fev–dez)."""
    db = build(SILVER, SEEDS, tmp_path / "spot.duckdb")
    con = duckdb.connect(str(db))
    try:
        mc.compute(con)
        san = mc.sanity(con)
        assert san["ok"], san
        assert (san["gabinetes"], san["servidores"], san["folha"]) == (43, 733, 4757228.61)
        subs = {s["competencia"]: s for s in san["subsidios"]}
        assert subs["2025-01"]["n_subsidios"] == 0
        assert all(subs[f"2025-{m:02d}"]["n_subsidios"] == 43 for m in range(2, 13))
        assert subs["2025-06"]["total"] == pytest.approx(43 * 26080.98)
        assert mc.gabinetes_sem_alias(con) == []
        assert (
            con.execute("SELECT count(*) FROM metrica_custo_gabinete WHERE vereador_id IS NULL").fetchone()[0]
            == 0
        )
        occ = dict(
            con.execute(
                "SELECT competencia, vereador_id FROM custo_gabinete_ocupante WHERE centro_custo_codigo = 10679962"
            ).fetchall()
        )
        assert occ["2025-02"] == "augusto-vasconcelos" and occ["2025-03"] == "helio-ferreira"
        assert occ["2025-07"] == "helio-ferreira"
        a = mc.analise_13(con)
        assert a["comuns"] > 900 and a["razao_2x"] <= 1 and a["mediana_razao"] == 1.0
        if (SILVER / "empenho.csv").exists():
            # verba: todos os 43 gabinetes com valor em jun/2025 (não NULL), Σ do ano na ordem de 43 × 12 × ~30 mil
            (n, nulos, total) = con.execute(
                "SELECT count(*), count(*) - count(verba_compensatoria_observada), sum(verba_compensatoria_observada) "
                "FROM metrica_custo_gabinete WHERE competencia = '2025-06'"
            ).fetchone()
            assert (n, nulos) == (43, 0) and 1_000_000 < total < 1_600_000
            (ano_total,) = con.execute(
                "SELECT sum(verba_compensatoria_observada) FROM metrica_verba_vereador WHERE competencia LIKE '2025-%'"
            ).fetchone()
            assert 12_000_000 < ano_total < 17_000_000
            # credores sem alias ficam visíveis em metrica_verba_vereador (vereador_id NULL), nunca somem
            assert all(u["n_empenhos"] >= 1 for u in mc.verba_nao_mapeada(con))
    finally:
        con.close()


def test_verba_empenho_duplicado_e_competencia_do_processo(tmp_path: Path) -> None:
    # PP 780/2025: três empenhos originais para o mesmo processo, sem anulação publicada; o e-TCM cita só o 302.
    # PP 367/2025: empenho sem mês no objeto, emitido em fevereiro; o processo do e-TCM é de janeiro.
    # PP 1279/2025: dois originais, mas o que o e-TCM não cita foi anulado por inteiro: nada a descartar.
    con, params = _con(tmp_path)
    cols = (
        "numero, tipo, data, ano, valor, credor, categoria, anulacao, competencia_ref, processo, anula_numero"
    )
    con.execute(f"CREATE TABLE empenho ({mc.EMPENHO_COLS})")
    con.executemany(
        f"INSERT INTO empenho ({cols}) VALUES (?, 'Original', ?, 2025, ?, 'Ana Silva Civil', 'verba_compensatoria', ?, ?, ?, ?)",
        [
            ("2025NE000157", "2025-02-26", 14375.75, False, None, "367/2025", None),
            ("2025NE000289", "2025-04-01", 33889.12, False, "2025-03", "780/2025", None),
            ("2025NE000302", "2025-04-02", 33309.12, False, "2025-03", "780/2025", None),
            ("2025NE000303", "2025-04-02", 33889.12, False, "2025-03", "780/2025", None),
            ("2025NE000400", "2025-04-03", 100.0, True, None, None, "2025NE000303"),
            ("2025NE000453", "2025-06-01", 43100.0, False, "2025-05", "1279/2025", None),
            ("2025NE000464", "2025-06-02", 43100.0, True, "2025-05", None, "2025NE000453"),
            ("2025NE000473", "2025-06-03", 43100.0, False, "2025-05", "1279/2025", None),
        ],
    )
    con.executemany("INSERT INTO vereador_alias VALUES (?, ?, ?)", ALIAS_EMPENHO)
    con.execute(
        "CREATE TABLE verba_processo (pp_numero BIGINT, ano_processo BIGINT, empenho_numero VARCHAR, competencia VARCHAR)"
    )
    con.executemany(
        "INSERT INTO verba_processo VALUES (?, 2025, ?, ?)",
        [
            (367, "2025NE000157", "2025-01"),
            (780, "2025NE000302", "2025-03"),
            (780, "2025NE000302", "2025-03"),
            (1279, "2025NE000473", "2025-05"),
        ],
    )
    mc.compute(con, params)
    rows = {
        r["competencia"]: r
        for r in mc._rows(con, "SELECT * FROM metrica_verba_vereador WHERE vereador_id = 'ana'")
    }
    assert set(rows) == {"2025-01", "2025-03", "2025-05"}
    assert rows["2025-05"]["verba_compensatoria_observada"] == 43100.0
    assert rows["2025-05"]["empenhos_descartados"] is None
    assert rows["2025-01"]["verba_compensatoria_observada"] == 14375.75
    assert (rows["2025-01"]["n_competencia_processo"], rows["2025-01"]["n_fallback_mes_emissao"]) == (1, 0)
    mar = rows["2025-03"]
    assert mar["verba_compensatoria_observada"] == 33309.12 and mar["empenhos"] == "2025NE000302"
    # a anulação (parcial) de um empenho descartado sai junto com ele
    assert mar["empenhos_descartados"] == "2025NE000289|2025NE000303|2025NE000400"
    assert [(d["numero"], d["empenho_citado"]) for d in mc.empenhos_descartados(con)] == [
        ("2025NE000289", "2025NE000302"),
        ("2025NE000303", "2025NE000302"),
    ]
    con.close()
