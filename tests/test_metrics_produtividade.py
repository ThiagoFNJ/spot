"""Testes offline de ``spot.metrics.produtividade`` sobre um DuckDB em memória com linhas sintéticas."""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from spot.config import SEEDS
from spot.metrics import produtividade as mp

HOJE = date(2026, 10, 27)

DIM = [
    ("ana", "Ana Silva", "PT"),
    ("beto", "Beto Lima", "PP"),
    ("caio", "Caio Souza", "PL"),
]
ALIAS = [("Ana", "ana"), ("Beto", "beto"), ("Caio", "caio")]

# (codigo, autores, ementa, situacao)
PROPOSICOES_2025 = [
    ("PLE-1/2025", "Ana", "Institui a Política Municipal de Saúde Mental.", "Designado Relator"),
    ("PLE-2/2025", "Ana", "Denomina Rua João das Neves a via sem nome no bairro X.", "Encaminhado"),
    ("PLE-3/2025", "Ana", "Institui a Campanha denominada Janeiro Branco.", "Encaminhado"),
    (
        "PLE-4/2025",
        "Ana|Beto",
        "Dispõe sobre a transcrição em braile nas medalhas e diplomas.",
        "Ordem do Dia",
    ),
    (
        "REP-1/2025",
        "Ana",
        "Requer a realização de Sessão Solene para entrega da Medalha Thomé de Souza.",
        "Armazenado",
    ),
    ("PIN-1/2025", "Ana", "Indica ao Prefeito a pavimentação da Rua A.", "Encaminhado"),
    (
        "PIN-2/2025",
        "Ana",
        "Indica ao Prefeito que seja atribuído o nome de Maria à UBS do bairro.",
        "Encaminhado",
    ),
    ("MOC-1/2025", "Ana", "Aplausos à escola X pelos 50 anos.", "Armazenado"),
    ("MOC-2/2025", "Ana", "Pesar pelo falecimento de Fulano.", "Armazenado"),
    ("MOC-3/2025", "Ana", "Aplausos pelos 200 anos das relações diplomáticas Brasil-Santa Sé.", "Armazenado"),
    ("PRE-1/2025", "Ana", "Concede o Título de Cidadão Soteropolitano a Beltrano.", "Encaminhado"),
    ("PRE-2/2025", "Ana", "Revoga a Resolução nº 1/2020.", "Encaminhado"),
    ("PLE-5/2025", "Beto", "Cria o programa Y.", "Encaminhado"),
    ("PLE-6/2025", "Beto", "Cria o programa Z.", "Arquivado"),
    ("PLE-7/2025", "Executivo Municipal", "Altera a Lei nº 1.", "Aguardando Deliberação"),
    ("VTO-1/2025", "Executivo Municipal", "Veto parcial ao PL 1/2024.", "Encaminhado"),
    ("PRE-3/2025", "Mesa Executiva", "Dispõe sobre a estrutura administrativa.", "Encaminhado"),
    ("PLE-9999/2025", "João Marcelo", "Documento de teste - aba Legislativo", "."),  # sentinela
]
PROPOSICOES_2026 = [
    ("PLE-1/2026", "Caio", "Institui o programa W.", "Encaminhado"),
    ("PIN-1/2026", "Caio", "Indica ao Prefeito a poda das árvores da Rua B.", "Encaminhado"),
]


def _load_pesos(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        f"CREATE TABLE {mp.PESOS_TABLE} AS SELECT * FROM read_csv(?, header = true, encoding = 'utf-8')",
        [str(SEEDS / "pesos_v0.csv")],
    )


def _presenca(con: duckdb.DuckDBPyConnection, rows: list[tuple[str, int, str]]) -> None:
    """``presenca_mvp`` mínima: (vereador_id, ano, data_sessao); 1 linha por sessão, sem sentinela."""
    con.execute(
        "CREATE TABLE presenca_mvp (vereador_id VARCHAR, ano BIGINT, data_sessao DATE, sentinela BOOLEAN)"
    )
    con.executemany("INSERT INTO presenca_mvp VALUES (?, ?, ?, false)", rows)


def make_db(
    props: list[tuple[str, str, str, str]] | None = None,
    alias: list[tuple[str, str]] = ALIAS,
    presenca: list[tuple[str, int, str]] | None = None,
) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute(
        "CREATE TABLE proposicao (codigo VARCHAR, tipo VARCHAR, numero BIGINT, ano BIGINT, autor_fonte VARCHAR, "
        "autores VARCHAR, ementa VARCHAR, movimentado DATE, localizacao VARCHAR, situacao VARCHAR, "
        "outros_fonte VARCHAR, sentinela BOOLEAN, bronze_file VARCHAR)"
    )
    for codigo, autores, ementa, situacao in (
        props if props is not None else PROPOSICOES_2025 + PROPOSICOES_2026
    ):
        tipo, resto = codigo.split("-")
        numero, ano = resto.split("/")
        con.execute(
            "INSERT INTO proposicao VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL, ?, 'x.csv')",
            [codigo, tipo, int(numero), int(ano), autores, autores, ementa, situacao, int(numero) == 9999],
        )
    con.execute("CREATE TABLE vereador_dim (vereador_id VARCHAR, nome_parlamentar VARCHAR, partido VARCHAR)")
    con.executemany("INSERT INTO vereador_dim VALUES (?, ?, ?)", DIM)
    con.execute("CREATE TABLE vereador_alias (alias VARCHAR, fonte VARCHAR, vereador_id VARCHAR)")
    con.executemany("INSERT INTO vereador_alias VALUES (?, 'proposicao', ?)", alias)
    con.execute(
        "CREATE TABLE produtividade_resumo (ano BIGINT, autor_fonte VARCHAR, tipo VARCHAR, quantidade BIGINT)"
    )
    con.executemany(
        "INSERT INTO produtividade_resumo VALUES (?, ?, ?, ?)",
        [
            (2025, "Ana", "PLE", 4), (2025, "Ana", "REP", 1), (2025, "Ana", "PIN", 2), (2025, "Ana", "MOC", 3),
            (2025, "Ana", "PRE", 2), (2025, "Beto", "PLE", 1),  # Beto: resumo 1 vs prop_interna 2 (divergência)
            (2025, "Executivo Municipal", "PLE", 1), (2025, "Executivo Municipal", "VTO", 1),
            (2025, "Mesa Executiva", "PRE", 1), (2026, "Caio", "PLE", 1), (2026, "Caio", "PIN", 1),
        ],
    )  # fmt: skip
    _load_pesos(con)
    if presenca is None:
        # 2025: sessões de jan a dez (Ana, Caio); Beto só até fevereiro. 2026: fev a out (Ana, Caio), Beto a partir de ago.
        presenca = []
        for m in range(1, 13):
            presenca += [("ana", 2025, f"2025-{m:02d}-05"), ("caio", 2025, f"2025-{m:02d}-05")]
            if m <= 2:
                presenca.append(("beto", 2025, f"2025-{m:02d}-05"))
        for m in range(2, 11):
            presenca += [("ana", 2026, f"2026-{m:02d}-05"), ("caio", 2026, f"2026-{m:02d}-05")]
            if m >= 8:
                presenca.append(("beto", 2026, f"2026-{m:02d}-05"))
    _presenca(con, presenca)
    return con


def _metrica(con: duckdb.DuckDBPyConnection, vereador_id: str, ano: int) -> dict:
    rows = mp._rows(
        con, "SELECT * FROM metrica_produtividade WHERE vereador_id = ? AND ano = ?", [vereador_id, ano]
    )
    assert len(rows) == 1, rows
    return rows[0]


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    c = make_db()
    mp.compute(c, HOJE)
    return c


# ---- exclusões por regex ------------------------------------------------------------------------


def test_exclusao_regex_por_tipo(con):
    excl = dict(con.execute("SELECT codigo, exclusao FROM produtividade_base").fetchall())
    assert excl["PLE-2/2025"] == "logradouro"  # "Denomina Rua ..."
    assert excl["PIN-2/2025"] == "logradouro"  # "o nome de"
    assert excl["PLE-3/2025"] is None  # "campanha denominada" não é logradouro
    assert excl["MOC-2/2025"] == "pesar"
    assert excl["PRE-1/2025"] == "honraria"
    assert excl["PRE-2/2025"] is None  # PRE não honorífico vale
    assert excl["PLE-4/2025"] is None  # honraria só se aplica a PRE
    assert excl["REP-1/2025"] is None
    assert excl["MOC-3/2025"] is None  # "diplomáticas" não é diploma (e MOC não está no escopo)
    assert excl["MOC-1/2025"] is None


def test_contagem_exclusoes_total(con):
    ana = _metrica(con, "ana", 2025)
    assert ana["n_excluidas_regex"] == 4  # PLE-2, PIN-2, MOC-2, PRE-1
    por_tipo = {
        r[0]: r[1]
        for r in con.execute(
            "SELECT tipo, n_excluidas FROM metrica_produtividade_tipo WHERE vereador_id = 'ana' AND ano = 2025"
        ).fetchall()
    }
    assert por_tipo == {"PLE": 1, "REP": 0, "PIN": 1, "MOC": 1, "PRE": 1}


# ---- pesos e volume ponderado -------------------------------------------------------------------


def test_volume_bruto_por_tipo_e_total(con):
    ana = _metrica(con, "ana", 2025)
    assert ana["n_total"] == 12
    assert (ana["n_ple"], ana["n_rep"], ana["n_pin"], ana["n_moc"], ana["n_pre"]) == (4, 1, 2, 3, 2)
    assert ana["n_outros"] == 0


def test_volume_ponderado_aplica_pesos_apos_exclusao(con):
    ana = _metrica(con, "ana", 2025)
    # PLE 3 válidos × 3 + REP 1 × 1 + PIN 1 × 0.5 + MOC 2 × 0.25 + PRE 1 × 1 = 9 + 1 + 0.5 + 0.5 + 1
    assert ana["vol_ponderado"] == pytest.approx(12.0)
    assert ana["meses_exercicio"] == 12
    assert ana["vol_ponderado_12m"] == pytest.approx(12.0)


def test_tipo_sem_peso_falha_alto():
    c = make_db(props=[("XYZ-1/2025", "Ana", "Coisa nova.", "Encaminhado")])
    with pytest.raises(mp.ProdutividadeError, match="XYZ"):
        mp.compute(c, HOJE)


def test_pesos_cobrem_todos_os_tipos_do_seed():
    c = make_db()
    tipos = {r[0] for r in c.execute(f"SELECT tipo FROM {mp.PESOS_TABLE}").fetchall()}
    assert set(mp.TIPOS_COLUNAS) <= tipos
    assert {"VTO", "SUB", "RUU", "RAD"} <= tipos


# ---- meses em exercício -------------------------------------------------------------------------


def test_meses_exercicio_normaliza_12m(con):
    beto = _metrica(con, "beto", 2025)
    assert beto["meses_exercicio"] == 2  # jan–fev na grade
    assert beto["vol_ponderado"] == pytest.approx(6.0)  # 2 PLE × 3
    assert beto["vol_ponderado_12m"] == pytest.approx(36.0)
    meses = dict(
        con.execute(
            "SELECT vereador_id, meses_exercicio FROM produtividade_meses WHERE ano = 2026"
        ).fetchall()
    )
    # 2026 (ano corrente, hoje = out): quem aparece no 1º mês com sessão (fev) conta desde jan; até out = 10.
    assert meses["ana"] == 10
    assert meses["beto"] == 3  # ago–out


def test_vereador_sem_grade_fica_sem_normalizacao():
    c = make_db(presenca=[("ana", 2025, "2025-03-05")])
    mp.compute(c, HOJE)
    caio = _metrica(c, "caio", 2026)
    assert caio["meses_exercicio"] is None
    assert caio["vol_ponderado_12m"] is None
    assert caio["vol_ponderado"] == pytest.approx(3.5)


# ---- regra do primeiro autor e coautoria --------------------------------------------------------


def test_primeiro_autor_e_coautoria(con):
    # PLE-4/2025 "Ana|Beto": conta para Ana; Beto ganha 1 coautoria e não ganha volume.
    ana, beto = _metrica(con, "ana", 2025), _metrica(con, "beto", 2025)
    assert ana["n_ple"] == 4 and beto["n_ple"] == 2
    assert ana["co_autorias"] == 0 and beto["co_autorias"] == 1
    (n,) = con.execute("SELECT n_coautores FROM produtividade_base WHERE codigo = 'PLE-4/2025'").fetchone()
    assert n == 1


# ---- autores não resolvidos e institucionais ----------------------------------------------------


def test_autor_sem_alias_falha_listando_nome():
    c = make_db(alias=[("Ana", "ana"), ("Caio", "caio")])  # Beto sem alias
    with pytest.raises(mp.ProdutividadeError, match="Beto"):
        mp.compute(c, HOJE)


def test_outros_autores_nao_sao_descartados(con):
    rows = con.execute(
        "SELECT autor_fonte, ano, n FROM produtividade_outros_autores ORDER BY autor_fonte"
    ).fetchall()
    assert rows == [("Executivo Municipal", 2025, 2), ("Mesa Executiva", 2025, 1)]
    assert "Executivo Municipal" not in {
        r[0] for r in con.execute("SELECT vereador_id FROM metrica_produtividade").fetchall()
    }


def test_is_outro_autor():
    assert mp.is_outro_autor("Executivo Municipal")
    assert mp.is_outro_autor("Comissão de Legislação Participativa")
    assert mp.is_outro_autor("Diversos Vereadores")
    assert not mp.is_outro_autor("Professor Hamilton")


def test_sentinela_excluida(con):
    (n,) = con.execute("SELECT count(*) FROM produtividade_base WHERE codigo = 'PLE-9999/2025'").fetchone()
    assert n == 0


# ---- reconciliação e relatório ------------------------------------------------------------------


def test_reconciliacao_lista_divergencias(con):
    div = mp._rows(con, "SELECT * FROM produtividade_reconciliacao WHERE delta <> 0")
    assert [(d["ano"], d["autor"], d["n_prop_interna"], d["n_resumo"], d["delta"]) for d in div] == [
        (2025, "Beto", 2, 1, 1)
    ]
    (n_ana,) = con.execute(
        "SELECT delta FROM produtividade_reconciliacao WHERE autor = 'Ana' AND ano = 2025"
    ).fetchone()
    assert n_ana == 0


def test_ranking_e_relatorio(con):
    r2025 = mp.ranking(con, 2025)
    assert [r["vereador_id"] for r in r2025] == ["ana", "beto"]
    assert r2025[1]["posto_ponderado"] == 1  # Beto: 36/12m > Ana: 12/12m
    text = mp.render_report(con, HOJE)
    assert "## Ranking 2025" in text and "## Ranking 2026 (YTD" in text
    assert "Executivo Municipal" in text
    assert "Ana Silva" in text
    assert "\\|" in text  # regex com '|' escapado dentro da tabela markdown
