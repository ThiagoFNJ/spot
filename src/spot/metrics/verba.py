"""Verba compensatória por categoria de despesa (incisos I..XV do art. 14 da Lei 9.828/2025), a partir dos
processos de pagamento publicados no e-TCM (``parse/etcm_vc.py`` → ``verba_processo`` + ``verba_processo_item``).

Definições:
- um processo = um pedido mensal de verba de um vereador (``pp_numero``/``ano_processo``); ``competencia`` é o mês
  da despesa (``YYYY-MM``) e ``ano`` o ano dessa competência. O mesmo PDF pode ter sido lido mais de uma vez
  (bronze antigo na raiz + subpasta ``<YYYY-MM>``): fica UMA linha por processo (``metrica_verba_processo``),
  preferindo a que tem ``mes_prestacao`` e a melhor ``confianca``;
- ``metrica_verba_vereador_categoria_mes`` (longa): vereador × competência × categoria → valor;
- ``metrica_verba_categoria``: vereador × ano × categoria → ``total``, ``n_meses`` (competências com valor na
  categoria), ``n_processos``, ``pct`` (fatia da categoria no total anual do vereador);
- ``metrica_verba_casa_categoria``: Casa × ano × categoria → total, nº de vereadores, ``pct``;
- conciliação (só log + colunas em ``metrica_verba_processo``): ``total_declarado`` do processo × verba empenhada
  para o mesmo vereador na mesma competência (``metrica_verba_vereador``, de ``metrics/custo.py``) e × valor do
  empenho de mesmo número (``empenho.numero = empenho_numero``). Soma dos incisos ≠ total declarado já vem marcada
  pelo parser (``confianca = 'baixa'``) e é reportada.

Grava as quatro tabelas no DuckDB e o relatório ``docs/relatorios/verba-categorias.md``.
CLI: ``uv run python -m spot.metrics.verba [--db FILE] [--out FILE]``.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import duckdb

from spot.config import ROOT, SILVER

log = logging.getLogger(__name__)

DB_DEFAULT = SILVER / "spot.duckdb"
REPORT_DEFAULT = ROOT / "docs" / "relatorios" / "verba-categorias.md"
TOLERANCIA = 0.01
TABELAS = (
    "metrica_verba_processo",
    "metrica_verba_vereador_categoria_mes",
    "metrica_verba_categoria",
    "metrica_verba_casa_categoria",
    "metrica_verba_nf",
)


class VerbaError(RuntimeError):
    """Tabelas de entrada ausentes."""


def _tables(con: duckdb.DuckDBPyConnection) -> set[str]:
    return {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}


def _columns(con: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    return {
        r[0]
        for r in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?", [table]
        ).fetchall()
    }


def _rows(con: duckdb.DuckDBPyConnection, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    cur = con.execute(sql, list(params))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def _require(con: duckdb.DuckDBPyConnection, *tables: str) -> None:
    missing = [t for t in tables if t not in _tables(con)]
    if missing:
        raise VerbaError(f"tabelas obrigatórias ausentes: {', '.join(missing)}")


# ---- SQL -----------------------------------------------------------------------------------------------------


def sql_processo(
    tem_mes_prestacao: bool, tem_verba_vereador: bool, tem_empenho: bool, tem_layout: bool = False
) -> str:
    """``metrica_verba_processo``: um processo por linha, com soma dos incisos e as colunas de conciliação.

    ``layout`` diz que página de categorias o processo traz: ``resumo`` (tabela I..XV, jun/2025 em diante),
    ``detalhamento`` (formulário antigo, item a item, prestações de fev–mar/2025) ou ``nenhum`` (abr–mai/2025:
    só o total autorizado — não entra nas tabelas por categoria)."""
    mes_prestacao = "p.mes_prestacao" if tem_mes_prestacao else "NULL::VARCHAR"
    layout = "d.layout" if tem_layout else "CASE WHEN it.n_itens > 0 THEN 'resumo' ELSE 'nenhum' END"
    verba_emp = (
        "(SELECT round(sum(mv.verba_compensatoria_observada), 2) FROM metrica_verba_vereador mv "
        " WHERE mv.vereador_id = d.vereador_id AND mv.competencia = d.competencia)"
        if tem_verba_vereador
        else "NULL::DOUBLE"
    )
    emp_num = (
        "(SELECT round(sum(CASE WHEN e.anulacao THEN -e.valor ELSE e.valor END), 2) FROM empenho e "
        " WHERE e.numero = d.empenho_numero)"
        if tem_empenho
        else "NULL::DOUBLE"
    )
    return f"""
    CREATE OR REPLACE TABLE metrica_verba_processo AS
    WITH p AS (
        SELECT p.*, {mes_prestacao} AS mes_prestacao_,
               row_number() OVER (
                   PARTITION BY p.pp_numero, p.ano_processo
                   ORDER BY ({mes_prestacao}) IS NULL,
                            CASE p.confianca WHEN 'alta' THEN 0 WHEN 'media' THEN 1 ELSE 2 END,
                            p.arquivo
               ) AS rn,
               count(*) OVER (PARTITION BY p.pp_numero, p.ano_processo) AS n_leituras
        FROM verba_processo p
    ),
    d AS (SELECT * FROM p WHERE rn = 1),
    it AS (
        SELECT pp_numero, ano_processo, round(sum(valor), 2) AS soma_itens, count(*) AS n_itens
        FROM (SELECT DISTINCT pp_numero, ano_processo, categoria_romano, valor FROM verba_processo_item)
        GROUP BY 1, 2
    )
    SELECT d.pp_numero, d.ano_processo, d.arquivo, d.mes_prestacao_ AS mes_prestacao, d.requerente, d.vereador_id,
           v.nome_parlamentar, d.competencia, left(d.competencia, 4)::INTEGER AS ano, d.data_entrada,
           d.total_declarado, coalesce(it.soma_itens, 0) AS soma_itens, coalesce(it.n_itens, 0) AS n_itens,
           round(d.total_declarado - coalesce(it.soma_itens, 0), 2) AS dif_itens,
           d.empenho_numero, d.liquidacao_numero, d.ordem_bancaria, d.data_pagamento, d.confianca, d.n_leituras,
           {layout} AS layout,
           {verba_emp} AS verba_empenhada_competencia,
           {emp_num} AS valor_empenho_numero,
           round(d.total_declarado - {verba_emp}, 2) AS dif_empenho_competencia,
           round(d.total_declarado - {emp_num}, 2) AS dif_empenho_numero
    FROM d
    LEFT JOIN it USING (pp_numero, ano_processo)
    LEFT JOIN vereador_dim v USING (vereador_id)
    ORDER BY d.competencia, d.vereador_id NULLS LAST, d.pp_numero
    """


SQL_MES = """
CREATE OR REPLACE TABLE metrica_verba_vereador_categoria_mes AS
WITH it AS (
    SELECT DISTINCT pp_numero, ano_processo, categoria_romano, valor FROM verba_processo_item
)
SELECT p.vereador_id, p.nome_parlamentar, p.competencia, p.ano, c.categoria_romano, c.categoria_ordem,
       c.categoria_descricao, round(sum(it.valor), 2) AS valor, p.pp_numero, p.ano_processo, p.confianca
FROM it
JOIN metrica_verba_processo p USING (pp_numero, ano_processo)
JOIN verba_categorias c USING (categoria_romano)
GROUP BY ALL
ORDER BY p.competencia, p.vereador_id NULLS LAST, c.categoria_ordem
"""

SQL_CATEGORIA = """
CREATE OR REPLACE TABLE metrica_verba_categoria AS
WITH a AS (
    SELECT vereador_id, any_value(nome_parlamentar) AS nome_parlamentar, ano, categoria_romano, categoria_ordem,
           categoria_descricao, round(sum(valor), 2) AS total, count(DISTINCT competencia) AS n_meses,
           count(DISTINCT (pp_numero, ano_processo)) AS n_processos
    FROM metrica_verba_vereador_categoria_mes
    GROUP BY vereador_id, ano, categoria_romano, categoria_ordem, categoria_descricao
),
t AS (SELECT vereador_id, ano, sum(total) AS total_ano FROM a GROUP BY 1, 2)
SELECT a.*, round(100 * a.total / nullif(t.total_ano, 0), 1) AS pct
FROM a JOIN t ON t.vereador_id IS NOT DISTINCT FROM a.vereador_id AND t.ano = a.ano
ORDER BY a.ano, a.vereador_id NULLS LAST, a.categoria_ordem
"""

# Uma linha por documento fiscal declarado (só os processos com `layout = 'detalhamento'`, competências
# jan–fev/2025): o único nível em que a Câmara publicou número e data da nota.
SQL_NF = """
CREATE OR REPLACE TABLE metrica_verba_nf AS
SELECT p.vereador_id, p.nome_parlamentar, p.competencia, p.ano, p.pp_numero, p.ano_processo,
       n.item, n.inciso_fonte, n.categoria_romano, c.categoria_ordem, c.categoria_descricao, n.descricao,
       n.documento_fiscal, n.data_emissao, n.valor_apresentado, n.valor_glosa, n.valor_compensado
FROM verba_processo_nf n
JOIN metrica_verba_processo p USING (pp_numero, ano_processo)
LEFT JOIN verba_categorias c USING (categoria_romano)
ORDER BY p.competencia, p.vereador_id NULLS LAST, p.pp_numero, n.item, n.data_emissao
"""
SQL_NF_VAZIA = """
CREATE OR REPLACE TABLE metrica_verba_nf (
    vereador_id VARCHAR, nome_parlamentar VARCHAR, competencia VARCHAR, ano INTEGER, pp_numero VARCHAR,
    ano_processo VARCHAR, item VARCHAR, inciso_fonte VARCHAR, categoria_romano VARCHAR, categoria_ordem INTEGER,
    categoria_descricao VARCHAR, descricao VARCHAR, documento_fiscal VARCHAR, data_emissao VARCHAR,
    valor_apresentado DOUBLE, valor_glosa DOUBLE, valor_compensado DOUBLE
)
"""

SQL_CASA = """
CREATE OR REPLACE TABLE metrica_verba_casa_categoria AS
WITH a AS (
    SELECT ano, categoria_romano, categoria_ordem, categoria_descricao, round(sum(valor), 2) AS total,
           count(DISTINCT vereador_id) AS n_vereadores, count(DISTINCT (pp_numero, ano_processo)) AS n_processos,
           count(DISTINCT competencia) AS n_meses
    FROM metrica_verba_vereador_categoria_mes GROUP BY 1, 2, 3, 4
),
t AS (SELECT ano, sum(total) AS total_ano FROM a GROUP BY 1)
SELECT a.*, round(100 * a.total / nullif(t.total_ano, 0), 1) AS pct
FROM a JOIN t USING (ano) ORDER BY a.ano, a.categoria_ordem
"""


# ---- cálculo -------------------------------------------------------------------------------------------------


def compute(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    _require(con, "verba_processo", "verba_processo_item", "verba_categorias", "vereador_dim")
    tabelas = _tables(con)
    tem_mes = "mes_prestacao" in _columns(con, "verba_processo")
    if not tem_mes:
        log.warning("verba_processo sem coluna mes_prestacao (parser antigo): fica NULL")
    tem_vv = "metrica_verba_vereador" in tabelas
    tem_emp = "empenho" in tabelas
    if not tem_vv:
        log.warning(
            "metrica_verba_vereador ausente (rode spot.metrics.custo antes): sem conciliação por competência"
        )
    tem_layout = "layout" in _columns(con, "verba_processo")
    con.execute(sql_processo(tem_mes, tem_vv, tem_emp, tem_layout))
    con.execute(SQL_MES)
    con.execute(SQL_CATEGORIA)
    con.execute(SQL_CASA)
    tem_nf = (
        "verba_processo_nf" in tabelas and con.execute("SELECT count(*) FROM verba_processo_nf").fetchone()[0]
    )
    con.execute(SQL_NF if tem_nf else SQL_NF_VAZIA)
    for w in avisos(con):
        log.warning("%s", w)
    sizes = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABELAS}
    log.info("tabelas de verba por categoria: %s", sizes)
    return sizes


def duplicados(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    return _rows(
        con,
        "SELECT pp_numero, ano_processo, arquivo, n_leituras FROM metrica_verba_processo WHERE n_leituras > 1 ORDER BY 1, 2",
    )


def sem_vereador(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    return _rows(
        con,
        "SELECT pp_numero, ano_processo, arquivo, requerente, competencia FROM metrica_verba_processo "
        "WHERE vereador_id IS NULL ORDER BY competencia, pp_numero",
    )


def itens_nao_fecham(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    return _rows(
        con,
        f"""
        SELECT pp_numero, ano_processo, arquivo, vereador_id, competencia, total_declarado, soma_itens, dif_itens,
               n_itens, confianca
        FROM metrica_verba_processo
        WHERE layout <> 'nenhum' AND (abs(dif_itens) > {TOLERANCIA} OR n_itens = 0)
        ORDER BY competencia, pp_numero
        """,
    )


def divergencias_empenho(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Processos cujo total declarado difere da verba empenhada ao vereador na competência (quando há empenho)."""
    return _rows(
        con,
        f"""
        SELECT pp_numero, ano_processo, arquivo, vereador_id, competencia, total_declarado,
               verba_empenhada_competencia, dif_empenho_competencia, empenho_numero, valor_empenho_numero,
               dif_empenho_numero
        FROM metrica_verba_processo
        WHERE (verba_empenhada_competencia IS NOT NULL AND abs(dif_empenho_competencia) > {TOLERANCIA})
           OR (valor_empenho_numero IS NOT NULL AND abs(dif_empenho_numero) > {TOLERANCIA})
        ORDER BY competencia, pp_numero
        """,
    )


def conciliacao_resumo(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    return _rows(
        con,
        f"""
        SELECT ano, count(*) AS processos, count(vereador_id) AS com_vereador,
               count(verba_empenhada_competencia) AS com_empenho_competencia,
               sum(CASE WHEN abs(dif_empenho_competencia) <= {TOLERANCIA} THEN 1 ELSE 0 END)::BIGINT AS bate_competencia,
               count(valor_empenho_numero) AS com_empenho_numero,
               sum(CASE WHEN abs(dif_empenho_numero) <= {TOLERANCIA} THEN 1 ELSE 0 END)::BIGINT AS bate_numero,
               sum(CASE WHEN abs(dif_itens) <= {TOLERANCIA} AND n_itens > 0 THEN 1 ELSE 0 END)::BIGINT AS itens_fecham,
               round(sum(total_declarado), 2) AS total_declarado,
               round(sum(verba_empenhada_competencia), 2) AS total_empenhado_competencia
        FROM metrica_verba_processo GROUP BY 1 ORDER BY 1
        """,
    )


def cobertura(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    return _rows(
        con,
        """
        SELECT ano, count(*) AS n_processos, count(DISTINCT vereador_id) AS n_vereadores,
               count(DISTINCT competencia) AS n_competencias, min(competencia) AS de, max(competencia) AS ate,
               string_agg(DISTINCT mes_prestacao, ', ' ORDER BY mes_prestacao) AS meses_prestacao,
               sum(CASE WHEN confianca = 'alta' THEN 1 ELSE 0 END)::BIGINT AS alta,
               sum(CASE WHEN confianca = 'media' THEN 1 ELSE 0 END)::BIGINT AS media,
               sum(CASE WHEN confianca = 'baixa' THEN 1 ELSE 0 END)::BIGINT AS baixa,
               sum(CASE WHEN layout = 'resumo' THEN 1 ELSE 0 END)::BIGINT AS resumo,
               sum(CASE WHEN layout = 'detalhamento' THEN 1 ELSE 0 END)::BIGINT AS detalhamento,
               sum(CASE WHEN layout = 'nenhum' THEN 1 ELSE 0 END)::BIGINT AS nenhum,
               round(sum(total_declarado), 2) AS total_declarado
        FROM metrica_verba_processo GROUP BY 1 ORDER BY 1
        """,
    )


def cobertura_mensal(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    return _rows(
        con,
        """
        SELECT competencia, count(*) AS n_processos, count(DISTINCT vereador_id) AS n_vereadores,
               round(sum(total_declarado), 2) AS total_declarado, round(sum(soma_itens), 2) AS soma_itens,
               sum(CASE WHEN confianca = 'baixa' THEN 1 ELSE 0 END)::BIGINT AS baixa,
               string_agg(DISTINCT layout, '/' ORDER BY layout) AS layouts
        FROM metrica_verba_processo GROUP BY 1 ORDER BY 1
        """,
    )


def avisos(con: duckdb.DuckDBPyConnection) -> list[str]:
    out = [
        f"processo {d['pp_numero']}/{d['ano_processo']} lido {d['n_leituras']}x no bronze; mantido {d['arquivo']}"
        for d in duplicados(con)
    ]
    out += [
        f"processo {s['pp_numero']}/{s['ano_processo']} ({s['arquivo']}) sem vereador_id: requerente {s['requerente']!r}"
        for s in sem_vereador(con)
    ]
    out += [
        f"processo {i['pp_numero']}/{i['ano_processo']} {i['competencia']}: incisos somam {_brl(i['soma_itens'])} "
        f"({i['n_itens']} itens) vs total declarado {_brl(i['total_declarado'])} (confianca={i['confianca']})"
        for i in itens_nao_fecham(con)
    ]
    for d in divergencias_empenho(con):
        partes = []
        if d["verba_empenhada_competencia"] is not None and abs(d["dif_empenho_competencia"]) > TOLERANCIA:
            partes.append(
                f"empenhado ao vereador na competência {_brl(d['verba_empenhada_competencia'])} "
                f"(dif {_brl(d['dif_empenho_competencia'])})"
            )
        if d["valor_empenho_numero"] is not None and abs(d["dif_empenho_numero"]) > TOLERANCIA:
            partes.append(
                f"empenho {d['empenho_numero']} vale {_brl(d['valor_empenho_numero'])} (dif {_brl(d['dif_empenho_numero'])})"
            )
        out.append(
            f"processo {d['pp_numero']}/{d['ano_processo']} {d['competencia']} {d['vereador_id']}: total declarado "
            f"{_brl(d['total_declarado'])} × {'; '.join(partes)}"
        )
    return out


# ---- relatório -----------------------------------------------------------------------------------------------


def _brl(v: float | None) -> str:
    if v is None:
        return "n/d"
    s = f"{v:,.2f}".replace(",", "\u0000").replace(".", ",").replace("\u0000", ".")
    return f"R$ {s}"


def _casa_md(con: duckdb.DuckDBPyConnection, ano: int) -> list[str]:
    rows = _rows(
        con, "SELECT * FROM metrica_verba_casa_categoria WHERE ano = ? ORDER BY categoria_ordem", [ano]
    )
    if not rows:
        return [f"_Sem processos com competência em {ano}._", ""]
    out = [
        f"### Casa — {ano}",
        "",
        "| inciso | categoria | total | % | vereadores | processos | meses |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    out += [
        f"| {r['categoria_romano']} | {r['categoria_descricao']} | {_brl(r['total'])} | {r['pct']} | {r['n_vereadores']} | "
        f"{r['n_processos']} | {r['n_meses']} |"
        for r in rows
    ]
    out += ["", f"Σ {ano}: {_brl(sum(r['total'] for r in rows))}.", ""]
    return out


def _vereador_md(con: duckdb.DuckDBPyConnection, ano: int) -> list[str]:
    cats = _rows(con, "SELECT categoria_romano FROM verba_categorias ORDER BY categoria_ordem")
    romanos = [c["categoria_romano"] for c in cats]
    rows = _rows(
        con,
        """
        SELECT coalesce(nome_parlamentar, vereador_id, '?') AS nome, vereador_id, max(n_meses) AS meses,
               round(sum(total), 2) AS total_ano,
               map_from_entries(list((categoria_romano, total))) AS por_cat
        FROM metrica_verba_categoria WHERE ano = ? GROUP BY vereador_id, nome_parlamentar ORDER BY total_ano DESC
        """,
        [ano],
    )
    if not rows:
        return []
    out = [
        f"### Por vereador — {ano} (valores em R$ mil; `meses` = competências com processo lido)",
        "",
        "| vereador | meses | total | " + " | ".join(romanos) + " |",
        "|---|---:|---:|" + "---:|" * len(romanos),
    ]
    for r in rows:
        cells = [f"{r['por_cat'].get(c, 0) / 1000:.1f}" if r["por_cat"].get(c) else "·" for c in romanos]
        out.append(
            f"| {r['nome']} | {r['meses']} | {r['total_ano'] / 1000:.1f} | " + " | ".join(cells) + " |"
        )
    return out + [""]


def render_report(con: duckdb.DuckDBPyConnection, hoje: date | None = None) -> str:
    hoje = hoje or date.today()
    cob = cobertura(con)
    anos = [c["ano"] for c in cob]
    out = [
        "# Verba compensatória por categoria de despesa (e-TCM)",
        "",
        f"Gerado em {hoje.isoformat()} por `spot.metrics.verba` a partir de `verba_processo`/`verba_processo_item` "
        "(PDFs `PP <n> - VC - <nome>.pdf` da consulta pública do e-TCM; ver `docs/etcm.md`). Categorias = incisos "
        "I..XV do art. 14 da Lei 9.828/2025 (`data/seeds/verba_categorias.csv`).",
        "",
        "## Cobertura",
        "",
        "| ano (competência) | processos | vereadores | competências | de | até | prestações lidas | alta | média | baixa | resumo | detalhamento | sem tabela | Σ declarado |",
        "|---|---:|---:|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    out += [
        f"| {c['ano']} | {c['n_processos']} | {c['n_vereadores']} | {c['n_competencias']} | {c['de']} | {c['ate']} | "
        f"{c['meses_prestacao'] or 'n/d'} | {c['alta']} | {c['media']} | {c['baixa']} | {c['resumo']} | "
        f"{c['detalhamento']} | {c['nenhum']} | {_brl(c['total_declarado'])} |"
        for c in cob
    ] or ["| — | 0 | | | | | | | | | | | | |"]
    out += [
        "",
        "| competência | processos | vereadores | Σ declarado | Σ incisos | confiança baixa | página de categorias |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    out += [
        f"| {m['competencia']} | {m['n_processos']} | {m['n_vereadores']} | {_brl(m['total_declarado'])} | "
        f"{_brl(m['soma_itens'])} | {m['baixa']} | {m['layouts']} |"
        for m in cobertura_mensal(con)
    ]
    out += [
        "",
        "A Câmara tem 43 cadeiras: um mês com menos processos que isso tem PDFs ainda não baixados/lidos ou vereadores sem pedido.",
        "Página de categorias: `resumo` = tabela dos 15 incisos (prestações de jun/2025 em diante); `detalhamento` = "
        "formulário antigo com uma linha por documento fiscal (nº e data da nota, glosa; prestações de fev–mar/2025); "
        "`nenhum` = o processo só traz o total autorizado pela Controladoria (prestações de abr–mai/2025) e não entra "
        "nas tabelas por categoria.",
        "",
    ]
    nf = _rows(
        con,
        """
        SELECT competencia, count(*) AS notas, count(DISTINCT vereador_id) AS vereadores,
               sum(CASE WHEN documento_fiscal ~ '^[0-9]+$' THEN 1 ELSE 0 END)::BIGINT AS com_numero,
               sum(CASE WHEN valor_glosa > 0 THEN 1 ELSE 0 END)::BIGINT AS glosadas,
               round(sum(valor_glosa), 2) AS glosa, round(sum(valor_compensado), 2) AS compensado
        FROM metrica_verba_nf GROUP BY 1 ORDER BY 1
        """,
    )
    if nf:
        out += [
            "### Notas fiscais declaradas (formulário antigo)",
            "",
            "| competência | notas | vereadores | com nº de documento | glosadas | Σ glosa | Σ compensado |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        out += [
            f"| {r['competencia']} | {r['notas']} | {r['vereadores']} | {r['com_numero']} | {r['glosadas']} | "
            f"{_brl(r['glosa'])} | {_brl(r['compensado'])} |"
            for r in nf
        ]
        out += ["", "Tabela completa em `metrica_verba_nf` (sem fornecedor: o formulário não o traz).", ""]
    out += ["## Por categoria", ""]
    for ano in anos:
        out += _casa_md(con, ano)
        out += _vereador_md(con, ano)
    out += ["## Conciliação com os empenhos", ""]
    res = conciliacao_resumo(con)
    if res:
        out += [
            "| ano | processos | c/ vereador | c/ empenho na competência | batem | c/ empenho pelo nº | batem | incisos fecham | Σ declarado | Σ empenhado (competência) |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        out += [
            f"| {r['ano']} | {r['processos']} | {r['com_vereador']} | {r['com_empenho_competencia']} | {r['bate_competencia']} | "
            f"{r['com_empenho_numero']} | {r['bate_numero']} | {r['itens_fecham']} | {_brl(r['total_declarado'])} | "
            f"{_brl(r['total_empenhado_competencia'])} |"
            for r in res
        ]
        out.append("")
    avs = avisos(con)
    if avs:
        out += ["Divergências e avisos (também no log):", ""] + [f"- {a}" for a in avs] + [""]
    else:
        out += [
            "Nenhuma divergência: todo processo lido bate com o empenho da competência e os incisos fecham.",
            "",
        ]
    return "\n".join(out)


def run(db_path: Path = DB_DEFAULT, out: Path = REPORT_DEFAULT, hoje: date | None = None) -> Path:
    con = duckdb.connect(str(db_path))
    try:
        compute(con)
        text = render_report(con, hoje)
    finally:
        con.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    log.info("relatório gravado em %s (%d bytes)", out, len(text.encode("utf-8")))
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="verba compensatória por categoria (e-TCM) + relatório")
    ap.add_argument("--db", type=Path, default=DB_DEFAULT)
    ap.add_argument("--out", type=Path, default=REPORT_DEFAULT)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run(args.db, args.out)


if __name__ == "__main__":
    main()
