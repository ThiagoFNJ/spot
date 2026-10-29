"""Produtividade legislativa (spike §4.2) por vereador e ano sobre ``proposicao``.

Três eixos, nunca uma nota única:
1. *Volume bruto por tipo*: proposições em que o vereador é o **primeiro autor** (RI art. 179; ``autores``
   separado por ``|``, primeiro elemento), por (vereador, ano, tipo). Coautorias (demais posições) ficam
   em ``co_autorias``.
2. *Volume ponderado*: exclusões por regex sobre a ementa (logradouro, honraria, pesar — cada uma restrita
   aos tipos em que faz sentido) **antes** dos pesos de ``data/seeds/pesos_v0.csv``; normalizado por meses
   em exercício (``vol_ponderado / meses_exercicio * 12``). Meses em exercício vêm da grade de frequência
   (``presenca_mvp``): do primeiro ao último mês com linha no ano, estendido a janeiro / dezembro (ou ao mês
   corrente) quando o vereador aparece no primeiro / último mês com sessão do ano.
3. *Taxa de aprovação*: **não computável** sem a tramitação; publica-se só o snapshot de ``situacao``.

Tabelas gravadas no DuckDB: ``metrica_produtividade`` (larga), ``metrica_produtividade_tipo`` (longa),
``produtividade_outros_autores`` (Executivo, Mesa, comissões…), ``produtividade_situacao_snapshot`` e
``produtividade_reconciliacao`` (prop_interna × resumo oficial). Falha alto se um primeiro autor 2025+ não
tiver alias ``fonte = 'proposicao'`` nem for um autor institucional conhecido, ou se um tipo não tiver peso.

CLI: ``uv run python -m spot.metrics.produtividade [--db FILE] [--out FILE] [--pesos FILE]``.
"""

from __future__ import annotations

import argparse
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import duckdb

from spot.config import ROOT, SEEDS, SILVER

log = logging.getLogger(__name__)

DB_DEFAULT = SILVER / "spot.duckdb"
REPORT_DEFAULT = ROOT / "docs" / "relatorios" / "produtividade-2025-2026.md"
PESOS_DEFAULT = SEEDS / "pesos_v0.csv"
PESOS_TABLE = "pesos_v0"
ANO_INICIO = 2025
ANOS = (2025, 2026)
TIPOS_COLUNAS = ("PLE", "PLC", "PEL", "PDL", "PRE", "REP", "RUP", "PIN", "MOC")
TIPOS_PROJETO = ("PLE", "PLC", "PEL", "PDL", "PRE")

# Autores institucionais (não vereadores): ficam em ``produtividade_outros_autores``, nunca no ranking.
OUTROS_AUTORES = frozenset({"Executivo Municipal", "Mesa Executiva", "Diversos Vereadores"})
RE_OUTROS_AUTORES = re.compile(r"^(Comiss[aã]o\b|Coord\.|Mesa\b|Bancada\b|Frente\b)", re.IGNORECASE)

# Resumo oficial 2025 (BN / LEG_SYS_produtividade_parlamentar_proposicao) — critério de aceite do spike §4.2.
ACEITE_2025 = {"Aladilce": 148, "Felipe Santana": 144, "André Fraga": 124}
DELTAS_CONHECIDOS = {
    (
        2025,
        "Professor Hamilton",
    ): "SUB-1/2025 (substitutivo) existe em prop_interna mas o resumo não tem coluna SUB",
}


@dataclass(frozen=True)
class Exclusao:
    """Regex (RE2, aplicado a ``strip_accents(lower(ementa))``) que zera a proposição antes da ponderação."""

    nome: str
    regex: str
    tipos: tuple[str, ...]
    descricao: str


# Padrões conferidos contra as ementas 2025-26 (ver relatório): ``denomina`` solto pegava "campanha denominada
# Janeiro Branco"; ``diploma`` pegava "relações diplomáticas"; ``pesar`` sem \b pegaria "apesar" (0 casos, mas
# por segurança). Tipos fora do escopo de cada padrão nunca são excluídos por ele.
EXCLUSOES: tuple[Exclusao, ...] = (
    Exclusao(
        "logradouro",
        r"^denomina|passa a denominar|\bo nome de\b|denominacao d[aeo]s? |logradouro denominad|mudanca de nome"
        r"|seja denominad[oa] de|para denominar",
        ("PLE", "PLC", "PIN", "REP", "RUP"),
        "nome de rua / logradouro / equipamento público",
    ),
    Exclusao(
        "honraria",
        r"titulo de cidad|comenda|medalha|\bdiplomas?\b",
        ("PRE",),
        "Título de Cidadão, Medalha, Comenda, Diploma (RI arts. 203-208)",
    ),
    Exclusao(
        "pesar",
        r"\bpesar\b|falecimento|falecid[oa]s?\b|in memoriam|pela morte|condolencias|\bluto\b",
        ("MOC",),
        "moção de pesar / in memoriam",
    ),
)

EMENTA_NORM = "strip_accents(lower(coalesce(ementa, '')))"


class ProdutividadeError(RuntimeError):
    """Inconsistência que impede calcular a métrica (autor sem alias, tipo sem peso…)."""


# ---- helpers -----------------------------------------------------------------------------------


def _rows(con: duckdb.DuckDBPyConnection, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    cur = con.execute(sql, list(params))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def _has_table(con: duckdb.DuckDBPyConnection, name: str) -> bool:
    (n,) = con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [name]
    ).fetchone()
    return n > 0


def is_outro_autor(nome: str) -> bool:
    """Autor institucional (Executivo, Mesa, comissão…) — não entra no ranking, mas não é descartado."""
    return nome in OUTROS_AUTORES or RE_OUTROS_AUTORES.match(nome) is not None


# ---- pesos -------------------------------------------------------------------------------------


def ensure_pesos(con: duckdb.DuckDBPyConnection, path: Path = PESOS_DEFAULT) -> None:
    """Garante a tabela ``pesos_v0`` (o ``build`` já a carrega dos seeds; aqui só para bancos antigos/testes)."""
    if _has_table(con, PESOS_TABLE):
        return
    if not path.exists():
        raise ProdutividadeError(f"tabela {PESOS_TABLE} ausente e seed {path} não existe")
    con.execute(
        f"CREATE TABLE {PESOS_TABLE} AS SELECT * FROM read_csv(?, header = true, encoding = 'utf-8')",
        [str(path)],
    )
    log.info("pesos carregados de %s", path)


def tipos_sem_peso(con: duckdb.DuckDBPyConnection, ano_inicio: int = ANO_INICIO) -> list[str]:
    rows = con.execute(
        f"""
        SELECT DISTINCT p.tipo FROM proposicao p
        LEFT JOIN {PESOS_TABLE} w ON w.tipo = p.tipo
        WHERE p.ano >= ? AND NOT p.sentinela AND w.tipo IS NULL ORDER BY 1
        """,
        [ano_inicio],
    ).fetchall()
    return [r[0] for r in rows]


# ---- autores -----------------------------------------------------------------------------------


def primeiros_autores(con: duckdb.DuckDBPyConnection, ano_inicio: int = ANO_INICIO) -> list[str]:
    rows = con.execute(
        "SELECT DISTINCT split_part(autores, '|', 1) FROM proposicao WHERE ano >= ? AND NOT sentinela ORDER BY 1",
        [ano_inicio],
    ).fetchall()
    return [r[0] for r in rows]


def autores_nao_resolvidos(con: duckdb.DuckDBPyConnection, ano_inicio: int = ANO_INICIO) -> list[str]:
    """Primeiros autores sem alias ``fonte='proposicao'`` que também não são autores institucionais."""
    com_alias = {
        r[0] for r in con.execute("SELECT alias FROM vereador_alias WHERE fonte = 'proposicao'").fetchall()
    }
    return [a for a in primeiros_autores(con, ano_inicio) if a not in com_alias and not is_outro_autor(a)]


# ---- base --------------------------------------------------------------------------------------


def _sql_exclusao(alias: str = "p") -> tuple[str, list[str]]:
    """``CASE`` que rotula a exclusão aplicável (ou NULL) — regexes como parâmetros, tipos como literais."""
    partes, params = [], []
    for e in EXCLUSOES:
        tipos = ", ".join("'" + t + "'" for t in e.tipos)
        partes.append(f"WHEN {alias}.tipo IN ({tipos}) AND regexp_matches({EMENTA_NORM}, ?) THEN '{e.nome}'")
        params.append(e.regex)
    return "CASE " + " ".join(partes) + " END", params


def build_base(con: duckdb.DuckDBPyConnection, ano_inicio: int = ANO_INICIO) -> int:
    """``produtividade_base``: uma linha por proposição 2025+ com 1º autor, vereador_id, exclusão e peso."""
    case_sql, params = _sql_exclusao()
    con.execute(
        f"""
        CREATE OR REPLACE TABLE produtividade_base AS
        SELECT
            p.codigo, p.tipo, p.numero, p.ano,
            split_part(p.autores, '|', 1) AS autor,
            p.autores,
            len(string_split(p.autores, '|')) - 1 AS n_coautores,
            a.vereador_id,
            p.ementa, p.situacao, p.movimentado,
            {case_sql} AS exclusao,
            w.peso
        FROM proposicao p
        LEFT JOIN vereador_alias a ON a.fonte = 'proposicao' AND a.alias = split_part(p.autores, '|', 1)
        LEFT JOIN {PESOS_TABLE} w ON w.tipo = p.tipo
        WHERE p.ano >= ? AND NOT p.sentinela
        """,
        [*params, ano_inicio],
    )
    (n,) = con.execute("SELECT count(*) FROM produtividade_base").fetchone()
    log.info("produtividade_base: %d proposições %d+", n, ano_inicio)
    return n


def build_outros_autores(con: duckdb.DuckDBPyConnection) -> int:
    con.execute(
        """
        CREATE OR REPLACE TABLE produtividade_outros_autores AS
        SELECT autor AS autor_fonte, ano, count(*) AS n
        FROM produtividade_base WHERE vereador_id IS NULL
        GROUP BY 1, 2 ORDER BY ano, n DESC, autor
        """
    )
    (n,) = con.execute("SELECT coalesce(sum(n), 0) FROM produtividade_outros_autores").fetchone()
    log.info("produtividade_outros_autores: %d proposições de autores institucionais", n)
    return int(n)


# ---- meses em exercício ------------------------------------------------------------------------


def build_meses_exercicio(con: duckdb.DuckDBPyConnection, hoje: date) -> int:
    """``produtividade_meses``: meses em exercício por (vereador, ano) inferidos da grade de frequência.

    Intervalo [primeiro mês, último mês] com linha em ``presenca_mvp`` (qualquer tipo de sessão, sem sentinela),
    estendido a janeiro quando o primeiro mês é o primeiro mês com sessão do ano (recesso de janeiro) e a
    dezembro — ou ao mês corrente, no ano em curso — quando o último mês é o último com sessão no ano.
    Licenças dentro do intervalo não são descontadas (conservador).
    """
    con.execute(
        """
        CREATE OR REPLACE TABLE produtividade_meses AS
        WITH g AS (
            SELECT vereador_id, ano, min(month(data_sessao)) AS m_ini, max(month(data_sessao)) AS m_fim
            FROM presenca_mvp WHERE NOT sentinela AND data_sessao IS NOT NULL GROUP BY 1, 2
        ),
        y AS (
            SELECT ano, min(month(data_sessao)) AS y_ini, max(month(data_sessao)) AS y_fim
            FROM presenca_mvp WHERE NOT sentinela AND data_sessao IS NOT NULL GROUP BY 1
        ),
        r AS (
            SELECT g.vereador_id, g.ano,
                   CASE WHEN g.m_ini = y.y_ini THEN 1 ELSE g.m_ini END AS mes_ini,
                   CASE WHEN g.m_fim = y.y_fim THEN (CASE WHEN g.ano = ? THEN ? ELSE 12 END) ELSE g.m_fim END AS mes_fim
            FROM g JOIN y USING (ano)
        )
        SELECT vereador_id, ano, mes_ini, mes_fim, (mes_fim - mes_ini + 1) AS meses_exercicio FROM r
        ORDER BY ano, vereador_id
        """,
        [hoje.year, hoje.month],
    )
    (n,) = con.execute("SELECT count(*) FROM produtividade_meses").fetchone()
    return n


# ---- métricas ----------------------------------------------------------------------------------


def build_metrica_tipo(con: duckdb.DuckDBPyConnection) -> int:
    con.execute(
        """
        CREATE OR REPLACE TABLE metrica_produtividade_tipo AS
        SELECT vereador_id, ano, tipo, count(*) AS n,
               count(*) FILTER (WHERE exclusao IS NOT NULL) AS n_excluidas,
               max(peso) AS peso,
               max(peso) * (count(*) - count(*) FILTER (WHERE exclusao IS NOT NULL)) AS vol_ponderado
        FROM produtividade_base WHERE vereador_id IS NOT NULL
        GROUP BY 1, 2, 3 ORDER BY ano, vereador_id, tipo
        """
    )
    (n,) = con.execute("SELECT count(*) FROM metrica_produtividade_tipo").fetchone()
    return n


def build_metrica(con: duckdb.DuckDBPyConnection) -> int:
    cols = ",\n".join(f"count(*) FILTER (WHERE tipo = '{t}') AS n_{t.lower()}" for t in TIPOS_COLUNAS)
    outros = ", ".join("'" + t + "'" for t in TIPOS_COLUNAS)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE metrica_produtividade AS
        WITH por_ver AS (
            SELECT vereador_id, ano,
                   count(*) AS n_total,
                   {cols},
                   count(*) FILTER (WHERE tipo NOT IN ({outros})) AS n_outros,
                   count(*) FILTER (WHERE exclusao IS NOT NULL) AS n_excluidas_regex,
                   sum(CASE WHEN exclusao IS NULL THEN peso ELSE 0 END) AS vol_ponderado
            FROM produtividade_base WHERE vereador_id IS NOT NULL GROUP BY 1, 2
        ),
        coaut AS (
            SELECT a.vereador_id, b.ano, count(*) AS co_autorias
            FROM produtividade_base b
            JOIN vereador_alias a
              ON a.fonte = 'proposicao' AND list_contains(string_split(b.autores, '|')[2:], a.alias)
            GROUP BY 1, 2
        )
        SELECT
            p.vereador_id, v.nome_parlamentar, v.partido, p.ano,
            m.meses_exercicio,
            p.n_total, p.n_ple, p.n_plc, p.n_pel, p.n_pdl, p.n_pre, p.n_rep, p.n_rup, p.n_pin, p.n_moc, p.n_outros,
            p.n_excluidas_regex,
            round(p.vol_ponderado, 2) AS vol_ponderado,
            round(p.vol_ponderado / m.meses_exercicio * 12, 2) AS vol_ponderado_12m,
            coalesce(c.co_autorias, 0) AS co_autorias
        FROM por_ver p
        LEFT JOIN vereador_dim v USING (vereador_id)
        LEFT JOIN produtividade_meses m USING (vereador_id, ano)
        LEFT JOIN coaut c USING (vereador_id, ano)
        ORDER BY p.ano, p.n_total DESC, p.vereador_id
        """
    )
    (n,) = con.execute("SELECT count(*) FROM metrica_produtividade").fetchone()
    sem_meses = [
        r[0] + f"/{r[1]}"
        for r in con.execute(
            "SELECT vereador_id, ano FROM metrica_produtividade WHERE meses_exercicio IS NULL"
        ).fetchall()
    ]
    if sem_meses:
        log.warning("sem meses em exercício na grade (vol_ponderado_12m = NULL): %s", ", ".join(sem_meses))
    log.info("metrica_produtividade: %d linhas (vereador x ano)", n)
    return n


def build_situacao_snapshot(con: duckdb.DuckDBPyConnection) -> int:
    con.execute(
        """
        CREATE OR REPLACE TABLE produtividade_situacao_snapshot AS
        SELECT vereador_id, ano, tipo, coalesce(situacao, '(vazio)') AS situacao, count(*) AS n
        FROM produtividade_base WHERE vereador_id IS NOT NULL
        GROUP BY 1, 2, 3, 4 ORDER BY ano, vereador_id, tipo, n DESC
        """
    )
    (n,) = con.execute("SELECT count(*) FROM produtividade_situacao_snapshot").fetchone()
    return n


def build_reconciliacao(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """prop_interna (1º autor, sem sentinela) × resumo oficial por (ano, autor); devolve só as divergências."""
    con.execute(
        """
        CREATE OR REPLACE TABLE produtividade_reconciliacao AS
        WITH p AS (SELECT ano, autor, count(*) AS n FROM produtividade_base GROUP BY 1, 2),
             r AS (SELECT ano, autor_fonte AS autor, sum(quantidade) AS n FROM produtividade_resumo GROUP BY 1, 2)
        SELECT coalesce(p.ano, r.ano) AS ano, coalesce(p.autor, r.autor) AS autor,
               coalesce(p.n, 0) AS n_prop_interna, coalesce(r.n, 0) AS n_resumo,
               coalesce(p.n, 0) - coalesce(r.n, 0) AS delta
        FROM p FULL JOIN r ON p.ano = r.ano AND p.autor = r.autor
        ORDER BY 1, abs(coalesce(p.n, 0) - coalesce(r.n, 0)) DESC, 2
        """
    )
    return _rows(con, "SELECT * FROM produtividade_reconciliacao WHERE delta <> 0")


def compute(con: duckdb.DuckDBPyConnection, hoje: date | None = None, pesos: Path = PESOS_DEFAULT) -> int:
    """Cria todas as tabelas de produtividade; devolve o nº de linhas de ``metrica_produtividade``."""
    hoje = hoje or date.today()
    ensure_pesos(con, pesos)
    faltam = tipos_sem_peso(con)
    if faltam:
        raise ProdutividadeError(f"tipo(s) de proposição sem peso em {PESOS_TABLE}: {', '.join(faltam)}")
    nao_resolvidos = autores_nao_resolvidos(con)
    if nao_resolvidos:
        raise ProdutividadeError(
            f"{len(nao_resolvidos)} primeiro(s) autor(es) {ANO_INICIO}+ sem alias (fonte=proposicao) e fora da lista "
            f"de autores institucionais: {', '.join(nao_resolvidos)}"
        )
    build_base(con)
    build_outros_autores(con)
    build_meses_exercicio(con, hoje)
    build_metrica_tipo(con)
    n = build_metrica(con)
    build_situacao_snapshot(con)
    divergencias = build_reconciliacao(con)
    for d in divergencias:
        log.warning(
            "reconciliação %d %s: prop_interna %d vs resumo %d (%s)",
            d["ano"],
            d["autor"],
            d["n_prop_interna"],
            d["n_resumo"],
            DELTAS_CONHECIDOS.get((d["ano"], d["autor"]), "sem explicação"),
        )
    return n


# ---- consultas para o relatório ----------------------------------------------------------------


def contagem_exclusoes(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Por padrão: linhas excluídas (no escopo de tipos) e quantas o regex pegaria fora do escopo (informativo)."""
    out = []
    for e in EXCLUSOES:
        tipos = ", ".join("'" + t + "'" for t in e.tipos)
        row = _rows(
            con,
            f"""
            SELECT count(*) FILTER (WHERE tipo IN ({tipos})) AS no_escopo,
                   count(*) FILTER (WHERE tipo NOT IN ({tipos})) AS fora_escopo,
                   count(*) FILTER (WHERE tipo IN ({tipos}) AND ano = 2025) AS no_escopo_2025,
                   count(*) FILTER (WHERE tipo IN ({tipos}) AND ano = 2026) AS no_escopo_2026
            FROM produtividade_base WHERE regexp_matches({EMENTA_NORM}, ?)
            """,
            [e.regex],
        )[0]
        por_tipo = _rows(
            con,
            "SELECT tipo, count(*) AS n FROM produtividade_base WHERE exclusao = ? GROUP BY 1 ORDER BY 2 DESC",
            [e.nome],
        )
        out.append({"exclusao": e, **row, "por_tipo": por_tipo})
    return out


def ranking(con: duckdb.DuckDBPyConnection, ano: int) -> list[dict[str, Any]]:
    """Linhas de ``metrica_produtividade`` do ano com postos por volume bruto e por volume ponderado/12m."""
    return _rows(
        con,
        """
        SELECT *,
               rank() OVER (ORDER BY n_total DESC) AS posto_bruto,
               rank() OVER (ORDER BY vol_ponderado_12m DESC NULLS LAST) AS posto_ponderado
        FROM metrica_produtividade WHERE ano = ?
        ORDER BY posto_bruto, vereador_id
        """,
        [ano],
    )


def situacao_wide(
    con: duckdb.DuckDBPyConnection, ano: int, tipos: Sequence[str] = TIPOS_PROJETO
) -> list[dict[str, Any]]:
    tipos_sql = ", ".join("'" + t + "'" for t in tipos)
    return _rows(
        con,
        f"""
        SELECT v.nome_parlamentar, s.vereador_id,
               sum(n) AS total,
               sum(n) FILTER (WHERE s.situacao = 'Encaminhado') AS encaminhado,
               sum(n) FILTER (WHERE s.situacao = 'Armazenado') AS armazenado,
               sum(n) FILTER (WHERE s.situacao IN ('Designado Relator', 'Aguardando Designacao do Relator',
                                                 'Redistribuido', 'Aguardando Parecer', 'Diligência')) AS em_comissao,
               sum(n) FILTER (WHERE s.situacao IN ('Ordem do Dia', 'Pauta', 'Aguardando Deliberação')) AS plenario,
               sum(n) FILTER (WHERE s.situacao IN ('Anexado Redacao Final', 'Aguardando Sancao/Promulgacao',
                                                 'Aguardando Publicacao', 'Aprovado', 'Sancionado', 'Promulgado')) AS pos_aprovacao,
               sum(n) FILTER (WHERE s.situacao = 'Arquivado') AS arquivado
        FROM produtividade_situacao_snapshot s
        LEFT JOIN vereador_dim v USING (vereador_id)
        WHERE s.ano = ? AND s.tipo IN ({tipos_sql})
        GROUP BY 1, 2 ORDER BY total DESC, 1
        """,
        [ano],
    )


def _fmt(v: Any) -> str:
    if v is None:
        return "n/d"
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v)


def _tabela_ranking(rows: list[dict[str, Any]]) -> list[str]:
    out = [
        "| # bruto | # pond. | Δ posto | vereador | partido | meses | total | PLE | PLC+PEL+PDL | PRE | REP+RUP | PIN | MOC | outros | excl. regex | vol. pond. | vol. pond./12m | coaut. |",
        "|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        delta = r["posto_bruto"] - r["posto_ponderado"]
        out.append(
            f"| {r['posto_bruto']} | {r['posto_ponderado']} | {delta:+d} | {r['nome_parlamentar'] or r['vereador_id']} | "
            f"{r['partido'] or ''} | {_fmt(r['meses_exercicio'])} | {r['n_total']} | {r['n_ple']} | "
            f"{r['n_plc'] + r['n_pel'] + r['n_pdl']} | {r['n_pre']} | {r['n_rep'] + r['n_rup']} | {r['n_pin']} | "
            f"{r['n_moc']} | {r['n_outros']} | {r['n_excluidas_regex']} | {_fmt(r['vol_ponderado'])} | "
            f"{_fmt(r['vol_ponderado_12m'])} | {r['co_autorias']} |"
        )
    return out


def _top(rows: list[dict[str, Any]], chave: str, n: int = 5) -> str:
    ordem = sorted(rows, key=lambda r: (-(r[chave] or 0), r["vereador_id"]))[:n]
    return "; ".join(f"{r['nome_parlamentar']} ({_fmt(r[chave])})" for r in ordem)


def _secao_metodo(con: duckdb.DuckDBPyConnection) -> list[str]:
    pesos = _rows(con, f"SELECT * FROM {PESOS_TABLE} ORDER BY peso DESC, tipo")
    presentes = {
        r[0]: r[1] for r in con.execute("SELECT tipo, count(*) FROM produtividade_base GROUP BY 1").fetchall()
    }
    md = [
        "## Método (spike §4.2)",
        "",
        "- **Autor** = primeiro signatário (RI art. 179): primeiro elemento de `autores` (campo *Autor* do grid, separado por `|`). "
        "Nomes resolvidos por `vereador_alias` (`fonte = proposicao`, strings idênticas às da grade de frequência). "
        "Autores institucionais (Executivo, Mesa, comissões) ficam em `produtividade_outros_autores`.",
        "- **Volume bruto** `n_total` = proposições 2025+ por (vereador, ano), sem sentinelas (`PLE-9999/2025` é registro de teste).",
        "- **Exclusões** por regex (RE2, sobre `strip_accents(lower(ementa))`) aplicadas **antes** da ponderação, cada uma só nos tipos indicados; "
        "a proposição excluída continua em `n_total` e em `n_<tipo>` mas vale 0 no volume ponderado.",
        "- **Volume ponderado** `vol_ponderado = Σ_tipo peso_tipo × (n_tipo − n_excluídas_tipo)`; "
        "`vol_ponderado_12m = vol_ponderado / meses_exercicio × 12`.",
        "- **Meses em exercício**: inferidos da grade de frequência (`presenca_mvp`): do primeiro ao último mês do ano em que o vereador tem linha, "
        "estendido a janeiro quando aparece no primeiro mês com sessão do ano (janeiro é recesso) e a dezembro — ou ao mês corrente, em 2026 — "
        "quando aparece no último. Licenças no meio do intervalo não são descontadas.",
        "- **Taxa de aprovação**: não computável neste snapshot (exige o crawl de `prop_interna_tram`); ver §Situação (snapshot).",
        "",
        "### Pesos v0 (`data/seeds/pesos_v0.csv`, parâmetro versionado)",
        "",
        "| tipo | peso | proposições 2025-26 | observação |",
        "|---|---:|---:|---|",
        *[
            f"| {p['tipo']} | {p['peso']} | {presentes.get(p['tipo'], 0)} | {p['observacao']} |"
            for p in pesos
        ],
        "",
        "### Exclusões por regex (contagens sobre 2025-26, todos os autores)",
        "",
        "| exclusão | tipos em que se aplica | regex | excluídas (2025 / 2026) | por tipo | acertos fora do escopo (ignorados) |",
        "|---|---|---|---:|---|---:|",
    ]
    for c in contagem_exclusoes(con):
        e: Exclusao = c["exclusao"]
        por_tipo = ", ".join(f"{t['tipo']} {t['n']}" for t in c["por_tipo"]) or "—"
        md.append(
            f"| {e.nome} — {e.descricao} | {', '.join(e.tipos)} | `{e.regex.replace('|', '\\|')}` | "
            f"{c['no_escopo']} ({c['no_escopo_2025']} / {c['no_escopo_2026']}) | {por_tipo} | {c['fora_escopo']} |"
        )
    md += [
        "",
        "Conferência manual dos padrões nas ementas reais (27/10/2026): `denomina` solto pegava campanhas/programas "
        '"denominados" (Janeiro Branco, Agosto Dourado, Sala Lilás) e a "PEC denominada Blindagem" — daí o padrão ancorado '
        "(`^denomina`, `denominacao d[aeo]`, `o nome de`, `logradouro denominad`, `mudanca de nome`); restam como falsos "
        "positivos conhecidos 2–3 PLE que *regulam* denominação (veda denominação de vias; cessão onerosa do direito à denominação; "
        'denominação de nomes de vereadores falecidos). `diploma` pegava "relações diplomáticas" (MOC) — `\\bdiplomas?\\b`. '
        "`pesar` foi ampliado para `falecid[oa]`, `in memoriam`, `pela morte`, pois há aplausos *in memoriam* e um "
        '"Repúdio pela morte"; só vale para MOC — o PLE sobre mães atípicas "após o falecimento de filhos" e a PIN sobre abono de '
        "faltas não são excluídos. Honraria só em PRE: os 4 REP de sessão solene para entrega de medalha e o PLE do braile em "
        "medalhas continuam valendo.",
        "",
    ]
    return md


def _secao_reconciliacao(con: duckdb.DuckDBPyConnection) -> list[str]:
    tot = _rows(
        con,
        "SELECT ano, sum(n_prop_interna) AS prop, sum(n_resumo) AS resumo, count(*) FILTER (WHERE delta <> 0) AS n_div "
        "FROM produtividade_reconciliacao GROUP BY 1 ORDER BY 1",
    )
    aceite = _rows(
        con,
        "SELECT autor, n_prop_interna, n_resumo FROM produtividade_reconciliacao "
        "WHERE ano = 2025 AND list_contains(?, autor) ORDER BY n_resumo DESC",
        [list(ACEITE_2025)],
    )
    div = _rows(
        con, "SELECT * FROM produtividade_reconciliacao WHERE delta <> 0 ORDER BY ano, abs(delta) DESC, autor"
    )
    md = [
        "## Reconciliação com o resumo oficial (`LEG_SYS_produtividade_parlamentar_proposicao`)",
        "",
        "Volume bruto por primeiro autor em `prop_interna` (sem sentinelas) × soma por autor do resumo oficial (mesmo sistema; "
        "o resumo não tem coluna SUB).",
        "",
        "| ano | prop_interna | resumo | autores divergentes |",
        "|---:|---:|---:|---:|",
        *[f"| {t['ano']} | {t['prop']} | {t['resumo']} | {t['n_div']} |" for t in tot],
        "",
        "Critério de aceite do spike (2025, volume bruto antes de exclusões e pesos):",
        "",
        "| autor | esperado (BN 2025) | prop_interna | resumo | ok |",
        "|---|---:|---:|---:|:---:|",
    ]
    for a in aceite:
        esperado = ACEITE_2025[a["autor"]]
        ok = a["n_prop_interna"] == esperado == a["n_resumo"]
        md.append(
            f"| {a['autor']} | {esperado} | {a['n_prop_interna']} | {a['n_resumo']} | {'sim' if ok else '**NÃO**'} |"
        )
    md += ["", "Autores com contagem diferente entre as duas fontes:", ""]
    if not div:
        md.append("Nenhum.")
    else:
        md += ["| ano | autor | prop_interna | resumo | Δ | explicação |", "|---:|---|---:|---:|---:|---|"]
        for d in div:
            md.append(
                f"| {d['ano']} | {d['autor']} | {d['n_prop_interna']} | {d['n_resumo']} | {d['delta']:+d} | "
                f"{DELTAS_CONHECIDOS.get((d['ano'], d['autor']), 'sem explicação')} |"
            )
    md += [
        "",
        "`João Marcelo` aparece em `prop_interna` só como autor do registro de teste `PLE-9999/2025` (`sentinela = true`) e, "
        "por isso, em nenhuma tabela desta métrica.",
        "",
    ]
    return md


def _secao_outros(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = _rows(
        con,
        """
        SELECT o.autor_fonte, o.ano, o.n, string_agg(t.tipo || ' ' || t.n, ', ' ORDER BY t.n DESC) AS tipos
        FROM produtividade_outros_autores o
        JOIN (SELECT autor, ano, tipo, count(*) AS n FROM produtividade_base WHERE vereador_id IS NULL GROUP BY 1, 2, 3) t
          ON t.autor = o.autor_fonte AND t.ano = o.ano
        GROUP BY 1, 2, 3 ORDER BY o.ano, o.n DESC, o.autor_fonte
        """,
    )
    return [
        "## Outros autores (fora do ranking de vereadores)",
        "",
        "| autor | ano | proposições | por tipo |",
        "|---|---:|---:|---|",
        *[f"| {r['autor_fonte']} | {r['ano']} | {r['n']} | {r['tipos']} |" for r in rows],
        "",
    ]


def _secao_situacao(con: duckdb.DuckDBPyConnection, ano: int) -> list[str]:
    geral = _rows(
        con,
        "SELECT situacao, sum(n) AS n FROM produtividade_situacao_snapshot WHERE ano = ? GROUP BY 1 ORDER BY 2 DESC",
        [ano],
    )
    total = sum(r["n"] for r in geral) or 1
    rows = situacao_wide(con, ano)
    md = [
        f"## Situação das proposições de {ano} — **snapshot** de 27/10/2026, não é taxa de aprovação",
        "",
        "O campo `Situação` do grid é só o estado atual do processo; o desfecho (Aprovado / Sancionado / lei) está na tramitação "
        "(`prop_interna_tram`), ainda não coletada. Distribuição geral das proposições de vereadores do ano:",
        "",
        "| situação | n | % |",
        "|---|---:|---:|",
        *[f"| {r['situacao']} | {r['n']} | {100 * r['n'] / total:.1f}% |" for r in geral],
        "",
        f"Por vereador, só projetos ({', '.join(TIPOS_PROJETO)} — os que tramitam em comissão e Plenário; indicações e moções "
        "vão para `Encaminhado`/`Armazenado` por construção):",
        "",
        "| vereador | projetos | Encaminhado | Armazenado | em comissão | Plenário | pós-aprovação | Arquivado |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        *[
            f"| {r['nome_parlamentar'] or r['vereador_id']} | {r['total']} | {r['encaminhado'] or 0} | {r['armazenado'] or 0} | "
            f"{r['em_comissao'] or 0} | {r['plenario'] or 0} | {r['pos_aprovacao'] or 0} | {r['arquivado'] or 0} |"
            for r in rows
        ],
        "",
        "`em comissão` = Designado Relator, Aguardando Designação do Relator, Redistribuído, Aguardando Parecer, Diligência; "
        "`Plenário` = Ordem do Dia, Pauta, Aguardando Deliberação; `pós-aprovação` = Redação Final, Aguardando Sanção/Promulgação, "
        "Aguardando Publicação, Aprovado, Sancionado, Promulgado.",
        "",
    ]
    return md


def render_report(con: duckdb.DuckDBPyConnection, hoje: date | None = None) -> str:
    hoje = hoje or date.today()
    md: list[str] = [
        "# Produtividade legislativa — 2025 e 2026 (parcial)",
        "",
        (
            f"Gerado em {hoje.isoformat()} por `uv run python -m spot.metrics.produtividade` a partir de `data/silver/spot.duckdb` "
            "(tabelas `metrica_produtividade`, `metrica_produtividade_tipo`, `produtividade_outros_autores`, "
            "`produtividade_situacao_snapshot`, `produtividade_reconciliacao`). Fonte primária: export CSV de "
            "`cmsalvador.sys.inf.br/cl/prop_interna` (bronze `data/bronze/proposicoes/`), resumo oficial "
            "`LEG_SYS_produtividade_parlamentar_proposicao` para reconciliação, meses em exercício pela grade de frequência."
        ),
        "",
        *_secao_metodo(con),
        *_secao_reconciliacao(con),
    ]
    for ano in ANOS:
        rows = ranking(con, ano)
        if not rows:
            md += [f"## {ano}", "", "Sem proposições.", ""]
            continue
        parcial = f" (YTD, até {hoje.isoformat()})" if ano == hoje.year else ""
        n_tot = sum(r["n_total"] for r in rows)
        n_exc = sum(r["n_excluidas_regex"] for r in rows)
        md += [
            f"## Ranking {ano}{parcial}",
            "",
            f"{len(rows)} vereadores com pelo menos uma proposição como 1º autor; {n_tot} proposições, {n_exc} excluídas por regex.",
            "",
            f"- Top-5 por **volume bruto**: {_top(rows, 'n_total')}.",
            f"- Top-5 por **volume ponderado / 12 meses**: {_top(rows, 'vol_ponderado_12m')}.",
            "",
            "`Δ posto` = posto bruto − posto ponderado (positivo = sobe quando indicações/moções/honrarias são descontadas). "
            "Ordenado pelo volume bruto.",
            "",
            *_tabela_ranking(rows),
            "",
        ]
    md += [*_secao_outros(con), *_secao_situacao(con, 2025)]
    md += [
        "## Ressalvas",
        "",
        "- **Primeiro autor** (RI art. 179): o campo *Autor* do grid traz um nome só em 100% das proposições 2025-26 "
        "(nenhum `|`), logo `co_autorias` é 0 para todos — a coautoria, quando existe, não é publicada no grid; a coluna "
        "`Autor/Requerente/Vistas/Outros` (`outros_fonte`) registra pedidos de vista/relatoria (Alexandre Aleluia 315), não coautoria.",
        "- **Indicações e moções inflam** (spike §4.2): PIN + MOC são mais da metade do volume bruto; por isso a leitura deve ser sempre "
        "pelos dois rankings lado a lado, e os pesos v0 são hipótese versionada, não verdade.",
        "- **Exclusões por regex** têm falsos positivos/negativos conhecidos (ver §Método) e só olham a ementa; indicações de "
        "nome de logradouro que não usam 'denomina'/'nome de' não são capturadas.",
        "- **PRE não honorífico** vale 1 (hipótese v0: só 4 casos em 2025-26); PRE de honraria vale 0 pela exclusão.",
        "- **2026 é parcial**: proposições até 27/10/2026 e meses em exercício até outubro; `vol_ponderado_12m` anualiza, "
        "mas o fim de ano legislativo (dez.) costuma concentrar protocolos.",
        "- **Meses em exercício** vêm da grade de frequência coletada (até a 44ª ordinária de 2026); suplentes com poucos meses têm "
        "`vol_ponderado_12m` muito sensível (Carlos Kleber, Dr. José Antônio, Tiago Queiroz, Sandro Bahiense). Vereador com "
        "proposição mas sem linha na grade no ano fica com `n/d`.",
        "- **Taxa de aprovação não é mensurável** neste snapshot; `Situação` é estado atual, não desfecho. Fase seguinte: "
        "crawl de `prop_interna_tram` por coorte de ano (spike §3.2).",
        "- A data `movimentado` é a da última movimentação, não a do protocolo; o ano da coorte é o do código (`-/2025`).",
        "",
    ]
    return "\n".join(md)


def run(
    db_path: Path = DB_DEFAULT,
    out: Path = REPORT_DEFAULT,
    pesos: Path = PESOS_DEFAULT,
    hoje: date | None = None,
) -> Path:
    con = duckdb.connect(str(db_path))
    try:
        compute(con, hoje, pesos)
        text = render_report(con, hoje)
    finally:
        con.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    log.info("relatório gravado em %s (%d bytes)", out, len(text.encode("utf-8")))
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="metrica_produtividade + relatório de produtividade legislativa")
    ap.add_argument("--db", type=Path, default=DB_DEFAULT)
    ap.add_argument("--out", type=Path, default=REPORT_DEFAULT)
    ap.add_argument("--pesos", type=Path, default=PESOS_DEFAULT)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run(args.db, args.out, args.pesos)


if __name__ == "__main__":
    main()
