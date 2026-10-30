"""Testes offline de ``spot.metrics.verba`` sobre um DuckDB em memória com processos sintéticos.

Cenário:
- ana: processos 2025-07 (PP 10: I 100 + XIV 50 = 150) e 2025-08 (PP 11: I 200 = 200), ambos batem com o empenho;
  PP 11 está lido duas vezes (raiz antiga sem mes_prestacao + subpasta) -> uma linha só;
- bob: PP 12 2025-08 total 300 mas incisos somam 250 (confianca baixa) e o empenho da competência é 280 -> divergência;
  o empenho de mesmo número vale 300 (bate pelo nº);
- PP 13 sem vereador_id (requerente desconhecido) 2026-01 -> aparece em cobertura/casa com vereador NULL, avisado;
- categoria XV sem itens -> não aparece;
- as categorias de cada processo somam o valor pago: os R$ 50 de bob sem inciso legível ficam na categoria "-".
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest

from spot.metrics import verba as mv

CATS = [("I", 1, "Softwares"), ("XIV", 14, "Combustível"), ("XV", 15, "Locação de veículos")]
DIM = [("ana", "Ana Silva"), ("bob", "Bob Lima")]
PROC_COLS = (
    "arquivo VARCHAR, pp_numero BIGINT, ano_processo BIGINT, requerente VARCHAR, vereador_id VARCHAR, "
    "competencia VARCHAR, data_entrada VARCHAR, total_declarado DOUBLE, auditoria_numero VARCHAR, "
    "empenho_numero VARCHAR, liquidacao_numero VARCHAR, ordem_bancaria VARCHAR, pagamento_numero VARCHAR, "
    "data_pagamento VARCHAR, n_paginas BIGINT, confianca VARCHAR, mes_prestacao VARCHAR"
)
PROCS = [
    (
        "2025-08/PP 10 - VC - Ana.pdf",
        10,
        2025,
        "Ana Silva",
        "ana",
        "2025-07",
        "2025-08-01",
        150.0,
        "NE1",
        "alta",
        "2025-08",
    ),
    (
        "PP 11 - VC - Ana.pdf",
        11,
        2025,
        "Ana Silva",
        "ana",
        "2025-08",
        "2025-09-01",
        200.0,
        "NE2",
        "baixa",
        None,
    ),
    (
        "2025-09/PP 11 - VC - Ana.pdf",
        11,
        2025,
        "Ana Silva",
        "ana",
        "2025-08",
        "2025-09-01",
        200.0,
        "NE2",
        "alta",
        "2025-09",
    ),
    (
        "2025-09/PP 12 - VC - Bob.pdf",
        12,
        2025,
        "Bob Lima",
        "bob",
        "2025-08",
        "2025-09-01",
        300.0,
        "NE3",
        "baixa",
        "2025-09",
    ),
    (
        "2026-02/PP 13 - VC - X.pdf",
        13,
        2026,
        "Fulano",
        None,
        "2026-01",
        "2026-02-01",
        40.0,
        "NE4",
        "media",
        "2026-02",
    ),
]
ITENS = [
    (10, 2025, "2025-07", "I", 100.0),
    (10, 2025, "2025-07", "XIV", 50.0),
    (11, 2025, "2025-08", "I", 200.0),
    (11, 2025, "2025-08", "I", 200.0),  # leitura duplicada do mesmo PDF
    (12, 2025, "2025-08", "I", 250.0),
    (13, 2026, "2026-01", "XIV", 40.0),
]
VERBA_VEREADOR = [("ana", "2025-07", 150.0), ("ana", "2025-08", 200.0), ("bob", "2025-08", 280.0)]
EMPENHOS = [("NE1", 150.0, False), ("NE2", 200.0, False), ("NE3", 300.0, False), ("NE3X", 20.0, True)]


def _load(con: duckdb.DuckDBPyConnection, com_mes_prestacao: bool = True, com_empenhos: bool = True) -> None:
    con.execute(
        "CREATE TABLE verba_categorias (categoria_romano VARCHAR, categoria_ordem INTEGER, categoria_descricao VARCHAR)"
    )
    con.executemany("INSERT INTO verba_categorias VALUES (?, ?, ?)", CATS)
    con.execute("CREATE TABLE vereador_dim (vereador_id VARCHAR, nome_parlamentar VARCHAR)")
    con.executemany("INSERT INTO vereador_dim VALUES (?, ?)", DIM)
    con.execute(f"CREATE TABLE verba_processo ({PROC_COLS})")
    for arq, pp, ano, req, vid, comp, ent, tot, ne, conf, mes in PROCS:
        con.execute(
            "INSERT INTO verba_processo VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'A', ?, 'NL', 'OB', 'PP', '2025-09-05', 12, ?, ?)",
            [arq, pp, ano, req, vid, comp, ent, tot, ne, conf, mes],
        )
    if not com_mes_prestacao:
        con.execute("ALTER TABLE verba_processo DROP COLUMN mes_prestacao")
    con.execute(
        "CREATE TABLE verba_processo_item (pp_numero BIGINT, ano_processo BIGINT, competencia VARCHAR, "
        "categoria_romano VARCHAR, categoria_descricao VARCHAR, valor DOUBLE)"
    )
    con.executemany("INSERT INTO verba_processo_item VALUES (?, ?, ?, ?, 'x', ?)", ITENS)
    if com_empenhos:
        con.execute(
            "CREATE TABLE metrica_verba_vereador (vereador_id VARCHAR, competencia VARCHAR, verba_compensatoria_observada DOUBLE)"
        )
        con.executemany("INSERT INTO metrica_verba_vereador VALUES (?, ?, ?)", VERBA_VEREADOR)
        con.execute("CREATE TABLE empenho (numero VARCHAR, valor DOUBLE, anulacao BOOLEAN)")
        con.executemany("INSERT INTO empenho VALUES (?, ?, ?)", EMPENHOS)


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect()
    _load(c)
    mv.compute(c)
    return c


def test_processo_dedup_e_colunas(con: duckdb.DuckDBPyConnection) -> None:
    rows = con.execute(
        "SELECT pp_numero, arquivo, mes_prestacao, n_leituras, soma_itens, dif_itens FROM metrica_verba_processo ORDER BY pp_numero"
    ).fetchall()
    assert [r[0] for r in rows] == [10, 11, 12, 13]
    pp11 = rows[1]
    assert pp11[1] == "2025-09/PP 11 - VC - Ana.pdf" and pp11[2] == "2025-09" and pp11[3] == 2
    assert pp11[4] == 200.0 and pp11[5] == 0.0
    assert rows[2][4] == 250.0 and rows[2][5] == 50.0


def test_metrica_verba_categoria(con: duckdb.DuckDBPyConnection) -> None:
    rows = con.execute(
        "SELECT vereador_id, ano, categoria_romano, categoria_descricao, total, n_meses, n_processos, pct "
        "FROM metrica_verba_categoria ORDER BY ano, vereador_id NULLS LAST, categoria_ordem"
    ).fetchall()
    assert rows == [
        ("ana", 2025, "I", "Softwares", 300.0, 2, 2, 85.7),
        ("ana", 2025, "XIV", "Combustível", 50.0, 1, 1, 14.3),
        ("bob", 2025, "I", "Softwares", 250.0, 1, 1, 83.3),
        # o que o pago (empenho NE3, 300) tem a mais que os incisos lidos (250) fica como não identificado
        ("bob", 2025, "-", "Não identificada no documento", 50.0, 1, 1, 16.7),
        (None, 2026, "XIV", "Combustível", 40.0, 1, 1, 100.0),
    ]


def test_tabela_longa(con: duckdb.DuckDBPyConnection) -> None:
    rows = con.execute(
        "SELECT vereador_id, competencia, categoria_romano, valor FROM metrica_verba_vereador_categoria_mes "
        "ORDER BY competencia, vereador_id, categoria_romano"
    ).fetchall()
    assert rows == [
        ("ana", "2025-07", "I", 100.0),
        ("ana", "2025-07", "XIV", 50.0),
        ("ana", "2025-08", "I", 200.0),
        ("bob", "2025-08", "-", 50.0),
        ("bob", "2025-08", "I", 250.0),
        (None, "2026-01", "XIV", 40.0),
    ]


def test_casa(con: duckdb.DuckDBPyConnection) -> None:
    rows = con.execute(
        "SELECT ano, categoria_romano, total, n_vereadores, n_processos, pct FROM metrica_verba_casa_categoria ORDER BY ano, categoria_ordem"
    ).fetchall()
    assert rows == [
        (2025, "I", 550.0, 2, 3, 84.6),
        (2025, "XIV", 50.0, 1, 1, 7.7),
        (2025, "-", 50.0, 1, 1, 7.7),
        (2026, "XIV", 40.0, 0, 1, 100.0),
    ]


def test_conciliacao(con: duckdb.DuckDBPyConnection) -> None:
    div = mv.divergencias_empenho(con)
    assert [d["pp_numero"] for d in div] == [12]
    assert div[0]["verba_empenhada_competencia"] == 280.0 and div[0]["dif_empenho_competencia"] == 20.0
    assert div[0]["valor_empenho_numero"] == 300.0 and div[0]["dif_empenho_numero"] == 0.0
    res = {r["ano"]: r for r in mv.conciliacao_resumo(con)}
    assert (
        res[2025]["processos"] == 3 and res[2025]["bate_competencia"] == 2 and res[2025]["bate_numero"] == 3
    )
    assert res[2025]["itens_fecham"] == 2
    assert res[2026]["com_empenho_competencia"] == 0
    avs = mv.avisos(con)
    assert any("lido 2x" in a and "11/2025" in a for a in avs)
    assert any("13/2026" in a and "sem vereador_id" in a for a in avs)
    assert any("12/2025" in a and "incisos somam" in a for a in avs)
    assert any("12/2025" in a and "dif R$ 20,00" in a for a in avs)


def test_cobertura(con: duckdb.DuckDBPyConnection) -> None:
    cob = {c["ano"]: c for c in mv.cobertura(con)}
    assert cob[2025]["n_processos"] == 3 and cob[2025]["n_vereadores"] == 2
    assert cob[2025]["meses_prestacao"] == "2025-08, 2025-09"
    assert cob[2026]["n_processos"] == 1 and cob[2026]["n_vereadores"] == 0


def test_sem_mes_prestacao_e_sem_empenhos() -> None:
    c = duckdb.connect()
    _load(c, com_mes_prestacao=False, com_empenhos=False)
    sizes = mv.compute(c)
    assert sizes["metrica_verba_processo"] == 4
    assert c.execute(
        "SELECT count(mes_prestacao), count(verba_empenhada_competencia) FROM metrica_verba_processo"
    ).fetchone() == (0, 0)
    assert mv.divergencias_empenho(c) == []


def test_tabelas_ausentes() -> None:
    with pytest.raises(mv.VerbaError, match="verba_processo"):
        mv.compute(duckdb.connect())


def test_run_grava_relatorio(tmp_path: Path) -> None:
    db = tmp_path / "t.duckdb"
    c = duckdb.connect(str(db))
    _load(c)
    c.close()
    out = mv.run(db, tmp_path / "rel.md", hoje=date(2026, 10, 28))
    text = out.read_text("utf-8")
    assert "# Verba compensatória por categoria" in text
    assert "### Casa — 2025" in text and "| I | Softwares | R$ 550,00 | 84.6 | 2 | 3 | 2 |" in text
    assert "| Ana Silva | 2 | 0.3 | 0.3 | 0.1 | · |" in text
    assert "processo 12/2025" in text
    assert "2026-10-28" in text


def test_categorias_somam_o_pago() -> None:
    # incisos acima do pago (o total lido como item, PP 1282/2025) e processo sem tabela: o processo inteiro vai
    # para "-"; o pago vem dos empenhos do processo (sem os descartados), não do total declarado
    c = duckdb.connect()
    _load(c)
    c.execute("INSERT INTO verba_processo_item VALUES (10, 2025, '2025-07', 'XV', 'x', 150.0)")
    c.execute(
        "CREATE TABLE metrica_verba_empenho (numero VARCHAR, processo VARCHAR, valor_liquido DOUBLE, descartado BOOLEAN)"
    )
    c.executemany(
        "INSERT INTO metrica_verba_empenho VALUES (?, ?, ?, ?)",
        [("NE1", "10/2025", 150.0, False), ("NE2", "11/2025", 190.0, False), ("NE9", "11/2025", 190.0, True)],
    )
    mv.compute(c)
    pago = dict(c.execute("SELECT pp_numero, valor_pago FROM metrica_verba_processo").fetchall())
    assert pago == {10: 150.0, 11: 190.0, 12: 300.0, 13: None}
    rows = c.execute(
        "SELECT pp_numero, categoria_romano, valor FROM metrica_verba_vereador_categoria_mes ORDER BY 1, 2"
    ).fetchall()
    assert rows == [
        (10, "-", 150.0),  # I 100 + XIV 50 + XV 150 = 300 > 150 pagos
        (11, "-", 190.0),  # I 200 > 190 pagos (glosa sem inciso identificado)
        (12, "-", 50.0),
        (12, "I", 250.0),
        (13, "XIV", 40.0),
    ]
    c.close()
