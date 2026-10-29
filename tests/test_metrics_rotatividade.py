"""Rotatividade de assessores (b5) em ``spot.metrics.custo``: entradas/saídas por centro de custo sobre a série de
competências da folha, com DuckDB em memória.

Cenário (competências 2025-11, 2025-12, 2026-01, 2026-03 — 2026-02 não existe, como 2026-07 na folha real):
- CC 100 (ana): ANA em todos os meses; BIA só em 2025-11 (saída em nov); CAIO entra em 2025-12 e sai em 2026-01;
  DUDA aparece em 2025-11, falta em 2025-12 e volta em 2026-01 (saída em nov + entrada em jan, "mesmo centro de custo");
- CC 200 (bob): EVA em 2025-11..2026-01, listada duas vezes em 2025-12 (linha com proventos 0) → conta uma vez;
  em 2026-03 EVA está em outra função (não assessor) → saída em 2026-01 (último mês da série não gera saídas, mas
  2026-01 não é o último);
- CC 0 "LOTAÇÃO NÃO PUBLICADA" (2026, fonte tcm_pessoal): FABI entra em 2026-01 → vereador_id NULL, fonte 'nao_publicada';
- um estatutário no CC 900 (fora: não é assessor nem gabinete).
"""

from __future__ import annotations

import duckdb
import pytest

from spot.metrics import custo as c

ASSESSOR = "ASSESSOR PARLAMENTAR-G-10 CC10"
GAB_A = (100, "GAB. VER. ANA", "ANA")
GAB_B = (200, "GAB. VER. BOB", "BOB")
SEM = (0, c.CC_SEM_LOTACAO, None)
# (competencia, matricula, servidor, funcao, (cc, label, gabinete), proventos, fonte)
LINHAS = [
    ("2025-11", 1, "ANA", ASSESSOR, GAB_A, 3000.0, "rh_site"),
    ("2025-11", 2, "BIA", ASSESSOR, GAB_A, 3000.0, "rh_site"),
    ("2025-11", 4, "DUDA", ASSESSOR, GAB_A, 3000.0, "rh_site"),
    ("2025-11", 5, "EVA", ASSESSOR, GAB_B, 3000.0, "rh_site"),
    ("2025-12", 1, "ANA", ASSESSOR, GAB_A, 3000.0, "rh_site"),
    ("2025-12", 3, "CAIO", ASSESSOR, GAB_A, 3000.0, "rh_site"),
    ("2025-12", 5, "EVA", ASSESSOR, GAB_B, 0.0, "rh_site"),
    ("2025-12", 5, "EVA", ASSESSOR, GAB_B, 3000.0, "rh_site"),
    ("2026-01", 1, "ANA", ASSESSOR, GAB_A, 3100.0, "tcm_pessoal"),
    ("2026-01", 3, "CAIO", ASSESSOR, GAB_A, 3100.0, "tcm_pessoal"),
    ("2026-01", 4, "DUDA", ASSESSOR, GAB_A, 3100.0, "tcm_pessoal"),
    ("2026-01", 5, "EVA", ASSESSOR, GAB_B, 3100.0, "tcm_pessoal"),
    ("2026-01", 6, "FABI", ASSESSOR, SEM, 3100.0, "tcm_pessoal"),
    ("2026-03", 1, "ANA", ASSESSOR, GAB_A, 3100.0, "tcm_pessoal"),
    ("2026-03", 4, "DUDA", ASSESSOR, GAB_A, 3100.0, "tcm_pessoal"),
    ("2026-03", 5, "EVA", "SECRETARIO DE GABINETE CC-50", GAB_B, 4000.0, "tcm_pessoal"),
    ("2026-03", 6, "FABI", ASSESSOR, SEM, 3100.0, "tcm_pessoal"),
    ("2025-11", 9, "ZEL", "ANALISTA LEGISLATIVO MUNICIPAL", (900, "DIREL", None), 9000.0, "rh_site"),
]
OCUPANTE = {100: "ana", 200: "bob"}


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE folha (competencia VARCHAR, matricula BIGINT, servidor VARCHAR, funcao VARCHAR, "
        "centro_custo_codigo BIGINT, centro_custo_label VARCHAR, gabinete_vereador VARCHAR, proventos DOUBLE, fonte VARCHAR)"
    )
    con.executemany(
        "INSERT INTO folha VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (comp, mat, nome, fun, cc[0], cc[1], cc[2], prov, fonte)
            for comp, mat, nome, fun, cc, prov, fonte in LINHAS
        ],
    )
    con.execute(
        "CREATE TABLE metrica_custo_gabinete (centro_custo_codigo BIGINT, competencia VARCHAR, vereador_id VARCHAR)"
    )
    con.executemany(
        "INSERT INTO metrica_custo_gabinete VALUES (?, ?, ?)",
        [
            (cc, comp, v)
            for cc, v in OCUPANTE.items()
            for comp in ("2025-11", "2025-12", "2026-01", "2026-03")
        ],
    )
    c.computar_rotatividade(con)
    return con


def _mes(con: duckdb.DuckDBPyConnection) -> dict[tuple[str, int], tuple]:
    return {
        (r[0], r[1]): r[2:]
        for r in con.execute(
            "SELECT competencia, centro_custo_codigo, vereador_id, entradas, saidas, n_assessores, fonte_lotacao "
            "FROM metrica_rotatividade_mes"
        ).fetchall()
    }


def test_entradas_saidas_por_mes(con: duckdb.DuckDBPyConnection) -> None:
    m = _mes(con)
    # primeiro mês da série: nunca gera entradas; BIA e DUDA somem em dez → 2 saídas
    assert m["2025-11", 100] == ("ana", 0, 2, 3, "rh_site")
    # CAIO entra em dez; ninguém de dez falta em jan
    assert m["2025-12", 100] == ("ana", 1, 0, 2, "rh_site")
    # DUDA volta (entrada, mesmo CC); CAIO sai (ausente em 2026-03, o mês seguinte da série, pulando 2026-02)
    assert m["2026-01", 100] == ("ana", 1, 1, 3, "tcm_reconstruida")
    # último mês da série: nunca gera saídas
    assert m["2026-03", 100] == ("ana", 0, 0, 2, "tcm_reconstruida")
    # EVA duplicada em dez conta uma vez; vira CC-50 em março → saída em jan; o CC 200 não tem linha em 2026-03
    assert m["2025-12", 200] == ("bob", 0, 0, 1, "rh_site")
    assert m["2026-01", 200] == ("bob", 0, 1, 1, "tcm_reconstruida")
    assert ("2026-03", 200) not in m
    # centro fictício de 2026: sem vereador, fonte própria, entrada registrada
    assert m["2026-01", 0] == (None, 1, 0, 1, "nao_publicada")
    assert m["2026-03", 0] == (None, 0, 0, 1, "nao_publicada")
    assert all(cc != 900 for _, cc in m)


def test_anual_pessoas_vagas_razao_permanencia(con: duckdb.DuckDBPyConnection) -> None:
    rows = {
        (r[0], r[1], r[2]): r[3:]
        for r in con.execute(
            "SELECT vereador_id, centro_custo_codigo, ano, meses, pessoas_distintas, vagas_medias, razao, entradas, saidas, "
            "permanencia_media_meses, fonte_lotacao FROM metrica_rotatividade_gabinete"
        ).fetchall()
    }
    # 2025 CC 100: ANA, BIA, DUDA, CAIO = 4 pessoas; (3 + 2) / 2 meses = 2,5 vagas; 4 / 2,5 = 1,6
    # permanência (série inteira): ANA 4, BIA 1, DUDA 3, CAIO 2 → 2,5
    assert rows["ana", 100, 2025] == (2, 4, 2.5, 1.6, 1, 2, 2.5, "rh_site")
    # 2026 CC 100: ANA, CAIO, DUDA = 3 pessoas; (3 + 2) / 2 = 2,5 vagas; 3 / 2,5 = 1,2
    assert rows["ana", 100, 2026] == (2, 3, 2.5, 1.2, 1, 1, 3.0, "tcm_reconstruida")
    assert rows["bob", 200, 2025][:3] == (2, 1, 1.0)
    # vereador NULL preservado (join com IS NOT DISTINCT FROM)
    assert rows[None, 0, 2026] == (2, 1, 1.0, 1.0, 1, 0, 2.0, "nao_publicada")


def test_casa(con: duckdb.DuckDBPyConnection) -> None:
    casa = {
        r[0]: r[1:]
        for r in con.execute(
            "SELECT ano, meses, pessoas_distintas, pessoas_sem_lotacao, vagas_medias, razao, entradas, saidas, "
            "permanencia_media_meses FROM metrica_rotatividade_casa"
        ).fetchall()
    }
    # 2025: ANA BIA DUDA CAIO EVA = 5 pessoas; (4 + 3) / 2 = 3,5 vagas; 1 entrada (CAIO), 2 saídas (BIA, DUDA)
    assert casa[2025] == (2, 5, 0, 3.5, 1.43, 1, 2, 2.6)
    # 2026: ANA CAIO DUDA EVA FABI = 5; (5 + 3) / 2 = 4; entradas DUDA + FABI; saídas CAIO + EVA; FABI só sem lotação
    assert casa[2026] == (2, 5, 1, 4.0, 1.25, 2, 2, 2.8)


def test_base_uma_linha_por_matricula_mes(con: duckdb.DuckDBPyConnection) -> None:
    (n,) = con.execute(
        "SELECT count(*) FROM rotatividade_assessor_mes WHERE competencia = '2025-12' AND centro_custo_codigo = 200"
    ).fetchone()
    assert n == 1
