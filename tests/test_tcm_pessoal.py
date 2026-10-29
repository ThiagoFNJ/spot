"""Consulta de pessoal do TCM-BA exportada à mão (parse/tcm_pessoal.py) e a folha reconstruída de 2026 (metrics/custo.py)."""

from __future__ import annotations

import duckdb
import pytest

from spot.metrics import custo as c
from spot.parse import tcm_pessoal as m

HEAD = [
    (
        None,
        "Tribunal de Contas dos Municípios do Estado da Bahia",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    ),
    (
        "Câmara Municipal de SALVADORMARÇO/2026",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    ),
    list(m.HEADER),
]
LINHAS = [
    (
        "ABILIO BARBOSA FILHO",
        "14194",
        "Cargo Comissionado",
        "ASSESSOR PARLAMENTAR-G-13 CC10",
        "R$ 3.270,26",
        "R$ 4.326,41",
        "R$ 0,00",
        "R$ 0,00",
        "R$ 0,00",
        "44h",
        "Cargo Comissionado",
        "01/03/2022",
    ),
    (
        "ACLEIVA SANTOS",
        "353",
        "Cargo Comissionado",
        "ASSISTENCIA MILITAR SD PM",
        "R$ 2.402,76",
        "R$ 0,00",
        "R$ 2.402,76",
        "R$ 0,00",
        "R$ 0,00",
        "40h",
        "Cargo Comissionado",
        "Não informado",
    ),
    (
        "CARLOS DA SILVA MUNIZ",
        "900",
        "Agente Político",
        "AGENTE POLITICO",
        "R$ 17.170,23",
        "R$ 26.080,98",
        "R$ 0,00",
        "R$ 0,00",
        "R$ 0,00",
        "",
        "Agente Político",
        "01/01/2025",
    ),
    (
        "Receita Corrente Líquida de Março de 2025 até Março de 2026",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    ),
]


def test_parse_rows() -> None:
    rows = m.parse_rows(HEAD + LINHAS, "x.xlsx")
    assert [list(r) for r in rows] == [m.COLUMNS] * 3  # rodapé da RCL fora
    r = rows[0]
    assert (r["competencia"], r["matricula"], r["funcao"], r["grau"], r["simbolo"]) == (
        "2026-03",
        "14194",
        "ASSESSOR PARLAMENTAR",
        "G-13",
        "CC10",
    )
    assert (r["salario_base"], r["remuneracao_bruta"], r["salario_liquido"], r["admissao"]) == (
        "4326.41",
        "4326.41",
        "3270.26",
        "2022-03-01",
    )
    assert rows[1]["remuneracao_bruta"] == "2402.76" and rows[1]["admissao"] == "" and rows[1]["grau"] == ""


@pytest.mark.parametrize(
    "texto, comp",
    [
        ("Câmara Municipal de SALVADORMARÇO/2026", "2026-03"),
        ("SALVADORFEVEREIRO/2025", "2025-02"),
        ("sem mês", ""),
    ],
)
def test_competencia(texto: str, comp: str) -> None:
    assert m.competencia_do_cabecalho([(texto,)]) == comp


@pytest.mark.parametrize(
    "cargo, esperado",
    [
        ("ASSESSOR PARLAMENTAR-G-13 CC10 ", ("ASSESSOR PARLAMENTAR", "G-13", "CC10")),
        ("ASSESSOR PARLAMENTAR ESPECIAL-G-30 CC10", ("ASSESSOR PARLAMENTAR ESPECIAL", "G-30", "CC10")),
        ("ASSESSOR ESPECIAL DO GABINETE CC40", ("ASSESSOR ESPECIAL DO GABINETE", "", "CC40")),
        ("ANALISTA LEGISLATIVO MUNICIPAL", ("ANALISTA LEGISLATIVO MUNICIPAL", "", "")),
    ],
)
def test_split_cargo(cargo: str, esperado: tuple[str, str, str]) -> None:
    assert m.split_cargo(cargo) == esperado


def test_layout_error_sem_titulos() -> None:
    with pytest.raises(m.LayoutError):
        m.parse_rows([("Nada",), ("a", "b")], "x.xlsx")


# ---- folha reconstruída ---------------------------------------------------------------------------------------


def _db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(
        """CREATE TABLE folha AS SELECT * FROM (VALUES
        ('2025-11', 100::BIGINT, 'ANA', '3 - CARGO EM COMISSÃO', 1::BIGINT, 'ASSESSOR PARLAMENTAR-G-10 CC10', 'CC10', 'G-10', DATE '2025-02-01', 367171::BIGINT, 'GAB. VER. SILVIO HUMBERTO - 0124', 'SILVIO HUMBERTO', NULL, 3000.0, 'servidores_2025-11.pdf'),
        ('2025-12', 100::BIGINT, 'ANA', '3 - CARGO EM COMISSÃO', 1::BIGINT, 'ASSESSOR PARLAMENTAR-G-10 CC10', 'CC10', 'G-10', DATE '2025-02-01', 367172::BIGINT, 'GAB. VER. CARLOS MUNIZ', 'CARLOS MUNIZ', NULL, 3000.0, 'servidores_2025-12.pdf'),
        ('2025-12', 200::BIGINT, 'BIA', '1 - Estatutário', 2::BIGINT, 'ANALISTA LEGISLATIVO MUNICIPAL', '', '', DATE '2010-01-01', 367029::BIGINT, 'DIREL - COORDENAÇÃO', NULL, NULL, 9000.0, 'servidores_2025-12.pdf')
        ) t(competencia, matricula, servidor, regime, funcao_codigo, funcao, simbolo, grau, admissao, centro_custo_codigo, centro_custo_label, gabinete_vereador, suplente_vereador, proventos, bronze_file)"""
    )
    cols = "competencia VARCHAR, matricula BIGINT, servidor VARCHAR, regime VARCHAR, cargo VARCHAR, funcao VARCHAR, grau VARCHAR, simbolo VARCHAR, salario_liquido DOUBLE, salario_base DOUBLE, vantagens DOUBLE, gratificacao DOUBLE, decimo_terceiro DOUBLE, remuneracao_bruta DOUBLE, carga_horaria VARCHAR, situacao VARCHAR, admissao VARCHAR, arquivo VARCHAR"
    vals = []
    for comp in ("2026-01", "2026-02", "2026-03", "2026-07"):
        vals += [
            f"('{comp}', 100, 'ANA', 'Cargo Comissionado', 'ASSESSOR PARLAMENTAR-G-10 CC10', 'ASSESSOR PARLAMENTAR', 'G-10', 'CC10', 2500.0, 3100.0, 0.0, 0.0, 0.0, 3100.0, '44h', 'Cargo Comissionado', '2025-02-01', 'p.xlsx')",
            f"('{comp}', 200, 'BIA', 'Cargo Efetivo/ Estatutário', 'ANALISTA LEGISLATIVO MUNICIPAL', 'ANALISTA LEGISLATIVO MUNICIPAL', '', '', 7000.0, 8000.0, 1000.0, 0.0, 0.0, 9000.0, '40h', 'Cargo Efetivo/ Estatutário', '2010-01-01', 'p.xlsx')",
            f"('{comp}', 900, 'VER', 'Agente Político', 'AGENTE POLITICO', 'AGENTE POLITICO', '', '', 17000.0, 26080.98, 0.0, 0.0, 0.0, 26080.98, '', 'Agente Político', '', 'p.xlsx')",
        ]
        if comp != "2026-07":  # julho incompleto: só 1 linha além do agente → fica fora
            vals += [
                f"('{comp}', 300, 'CAIO', 'Cargo Comissionado', 'ASSESSOR PARLAMENTAR-G-05 CC10', 'ASSESSOR PARLAMENTAR', 'G-05', 'CC10', 1500.0, 1664.0, 0.0, 0.0, 0.0, 1664.0, '44h', 'Cargo Comissionado', '', 'p.xlsx')",
                f"('{comp}', 353, 'MIL', 'Cargo Comissionado', 'ASSISTENCIA MILITAR SD PM', 'ASSISTENCIA MILITAR SD PM', '', '', 2402.76, 0.0, 2402.76, 0.0, 0.0, 2402.76, '40h', 'Cargo Comissionado', '', 'p.xlsx')",
            ]
        else:
            vals = vals[:-2]  # julho: ANA só (incompleto)
    con.execute(f"CREATE TABLE tcm_pessoal ({cols}) ")
    con.execute(f"INSERT INTO tcm_pessoal SELECT * FROM (VALUES {', '.join(vals)})")
    return con


def test_reconstrucao_mapeia_ultima_lotacao_e_exclui_mes_incompleto() -> None:
    con = _db()
    n = c.reconstruir_folha(con)
    rows = con.execute(
        "SELECT competencia, matricula, centro_custo_label, gabinete_vereador, proventos, lotacao_conhecida, fonte FROM folha_reconstruida ORDER BY 1, 2"
    ).fetchall()
    assert n == 12 and {r[0] for r in rows} == {
        "2026-01",
        "2026-02",
        "2026-03",
    }  # agente fora; julho incompleto fora
    ana = next(r for r in rows if r[1] == 100 and r[0] == "2026-03")
    assert ana[2:] == (
        "GAB. VER. CARLOS MUNIZ",
        "CARLOS MUNIZ",
        3100.0,
        True,
        "tcm_pessoal",
    )  # última lotação (dez/2025), remuneração do TCM
    caio = next(r for r in rows if r[1] == 300)
    assert caio[2] == c.CC_SEM_LOTACAO and caio[3] is None and caio[5] is False
    mil = next(r for r in rows if r[1] == 353)
    assert mil[2] == c.CC_MILITAR and mil[5] is True
    # inseridas em folha com fonte
    assert con.execute("SELECT count(*) FROM folha WHERE fonte = 'tcm_pessoal'").fetchone()[0] == 12
    assert con.execute("SELECT count(*) FROM folha WHERE fonte = 'rh_site'").fetchone()[0] == 3
    cob = {
        r[0]: r
        for r in con.execute(
            "SELECT competencia, n_servidores, n_sem_lotacao, n_assessores_sem_lotacao FROM metrica_lotacao_cobertura"
        ).fetchall()
    }
    assert cob["2026-03"][1:] == (4, 1, 1)


def test_sem_tcm_pessoal_nao_quebra() -> None:
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE folha (competencia VARCHAR, matricula BIGINT, servidor VARCHAR, regime VARCHAR, funcao_codigo BIGINT, funcao VARCHAR, simbolo VARCHAR, grau VARCHAR, admissao DATE, centro_custo_codigo BIGINT, centro_custo_label VARCHAR, gabinete_vereador VARCHAR, suplente_vereador VARCHAR, proventos DOUBLE, bronze_file VARCHAR)"
    )
    assert c.reconstruir_folha(con) == 0
    assert con.execute("SELECT count(*) FROM metrica_lotacao_cobertura").fetchone()[0] == 0
