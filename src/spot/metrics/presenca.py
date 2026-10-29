"""Presença bruta (spike §4.1) por vereador e ano sobre ``presenca_mvp``.

Definições (sessões ordinárias, ``tipo_sessao_codigo = 1``, sem sentinelas):
- ``sessoes_ordinarias_em_exercicio``: linhas da grade para o vereador no ano (Presente + Ausente + Licenciado);
- ``taxa_presenca = presentes / (presentes + ausentes)``: Licenciado fora do denominador (RI art. 17 §7 II);
- ``sem_dado`` quando ``presentes + ausentes < 10`` (como Campinas);
- alerta LOM art. 27: ``ausentes / ordinárias realizadas no ano >= 1/3`` (perda de mandato).

Grava a tabela ``metrica_presenca`` no DuckDB e o relatório ``docs/relatorios/presenca-2025-2026.md``.
CLI: ``uv run python -m spot.metrics.presenca [--db FILE] [--out FILE]``.
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
REPORT_DEFAULT = ROOT / "docs" / "relatorios" / "presenca-2025-2026.md"
MIN_BASE = 10
LIMIAR_LOM27 = 1 / 3
ANOS = (2025, 2026)

# Spike §2 — faltas em sessões ordinárias de 2025 (ano cheio), por apelido da grade de frequência.
IMPRENSA_2025: dict[str, dict[str, int]] = {
    "Panorama da Bahia (2025, ano cheio)": {
        "Débora Santana": 15,
        "Maurício Trindade": 9,
        "Alexandre Aleluia": 8,
        "Cris Correia": 7,
        "Ireuda Silva": 7,
        "Randerson Leal": 7,
        "Anderson Ninho": 6,
    },
    "dump do spike (16/10/2026)": {
        "Débora Santana": 16,
        "Alexandre Aleluia": 9,
        "Maurício Trindade": 8,
        "Anderson Ninho": 7,
        "Cris Correia": 7,
        "Randerson Leal": 6,
    },
}

SQL_METRICA = """
CREATE OR REPLACE TABLE metrica_presenca AS
WITH ord AS (
    SELECT * FROM presenca_mvp WHERE tipo_sessao_codigo = 1 AND NOT sentinela
),
ano_tot AS (
    SELECT ano, count(DISTINCT num_sessao) AS ordinarias_do_ano,
           max(num_sessao) AS ultima_ordinaria, max(data_sessao) AS data_ultima_ordinaria
    FROM ord GROUP BY ano
),
por_ver AS (
    SELECT
        vereador_id, ano,
        count(*)                                        AS sessoes_ordinarias_em_exercicio,
        sum(CASE WHEN status = 'Presente'   THEN 1 ELSE 0 END)::BIGINT AS presentes,
        sum(CASE WHEN status = 'Ausente'    THEN 1 ELSE 0 END)::BIGINT AS ausentes,
        sum(CASE WHEN status = 'Licenciado' THEN 1 ELSE 0 END)::BIGINT AS licenciado,
        min(num_sessao) AS primeira_sessao, max(num_sessao) AS ultima_sessao
    FROM ord GROUP BY vereador_id, ano
)
SELECT
    p.vereador_id, v.nome_parlamentar, v.partido, v.situacao, p.ano,
    p.sessoes_ordinarias_em_exercicio, p.presentes, p.ausentes, p.licenciado,
    (p.presentes + p.ausentes) AS base_taxa,
    CASE WHEN p.presentes + p.ausentes >= ? THEN round(p.presentes / (p.presentes + p.ausentes), 4) END AS taxa_presenca,
    (p.presentes + p.ausentes < ?) AS sem_dado,
    t.ordinarias_do_ano,
    round(p.ausentes / t.ordinarias_do_ano, 4) AS fracao_faltas_lom27,
    (p.ausentes / t.ordinarias_do_ano >= ?) AS alerta_lom27,
    p.primeira_sessao, p.ultima_sessao
FROM por_ver p
JOIN ano_tot t USING (ano)
LEFT JOIN vereador_dim v USING (vereador_id)
ORDER BY p.ano, p.ausentes DESC, taxa_presenca NULLS LAST, p.vereador_id
"""


def compute(con: duckdb.DuckDBPyConnection) -> int:
    """Cria ``metrica_presenca`` e devolve o nº de linhas (vereador × ano)."""
    con.execute(SQL_METRICA, [MIN_BASE, MIN_BASE, LIMIAR_LOM27])
    (n,) = con.execute("SELECT count(*) FROM metrica_presenca").fetchone()
    log.info("metrica_presenca: %d linhas (vereador x ano)", n)
    return n


def _rows(con: duckdb.DuckDBPyConnection, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    cur = con.execute(sql, list(params))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def _ranks(values: Sequence[float]) -> list[float]:
    """Postos (1 = maior) com empates em média, como o Spearman clássico."""
    order = sorted(range(len(values)), key=lambda i: -values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        mean_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = mean_rank
        i = j + 1
    return ranks


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Correlação de Spearman (Pearson sobre postos, empates em média). ``None`` com < 3 pares ou variância zero."""
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return None
    return sxy / (sxx * syy) ** 0.5


def ranking_faltas(con: duckdb.DuckDBPyConnection, ano: int, top: int | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM metrica_presenca WHERE ano = ? ORDER BY ausentes DESC, taxa_presenca NULLS LAST, vereador_id"
    if top:
        sql += f" LIMIT {int(top)}"
    return _rows(con, sql, [ano])


def faltas_por_apelido(con: duckdb.DuckDBPyConnection, ano: int) -> dict[str, dict[str, Any]]:
    """``{apelido da grade: linha da métrica}`` para comparar com a imprensa, que usa os apelidos."""
    rows = _rows(
        con,
        """
        SELECT a.alias, m.* FROM metrica_presenca m
        JOIN vereador_alias a ON a.fonte = 'frequencia' AND a.vereador_id = m.vereador_id
        WHERE m.ano = ?
        """,
        [ano],
    )
    return {r["alias"]: r for r in rows}


def comparar_imprensa(
    con: duckdb.DuckDBPyConnection, ano: int, imprensa: dict[str, int], top: int = 10
) -> dict[str, Any]:
    """Compara faltas do spot com uma lista da imprensa; Spearman sobre os nomes comuns dentro do top-N do spot ∪ lista."""
    nossos = faltas_por_apelido(con, ano)
    ranking = ranking_faltas(con, ano, top)
    top_ids = {r["vereador_id"] for r in ranking}
    top_aliases = {alias for alias, r in nossos.items() if r["vereador_id"] in top_ids}
    comuns = sorted(set(imprensa) & set(nossos))
    pares = [(nossos[a]["ausentes"], imprensa[a]) for a in comuns]
    deltas = {a: nossos[a]["ausentes"] - imprensa[a] for a in comuns}
    return {
        "nomes_imprensa": len(imprensa),
        "nomes_comuns": comuns,
        "nao_encontrados": sorted(set(imprensa) - set(nossos)),
        "top_spot_fora_da_imprensa": sorted(top_aliases - set(imprensa)),
        "spearman": spearman([p[0] for p in pares], [p[1] for p in pares]),
        "max_abs_delta": max((abs(d) for d in deltas.values()), default=None),
        "deltas": deltas,
        "linhas": [
            {
                "alias": a,
                "spot": nossos[a]["ausentes"],
                "imprensa": imprensa[a],
                "delta": deltas[a],
                "licenciado": nossos[a]["licenciado"],
                "em_exercicio": nossos[a]["sessoes_ordinarias_em_exercicio"],
            }
            for a in sorted(comuns, key=lambda a: (-imprensa[a], a))
        ],
    }


def _fmt_taxa(v: float | None) -> str:
    return "sem dado" if v is None else f"{100 * v:.1f}%"


def _tabela_ranking(rows: list[dict[str, Any]], ordinarias: int) -> list[str]:
    out = [
        "| # | vereador | partido | situação (27/10/2026) | em exercício | presentes | ausentes | licenciado | taxa | faltas/ordinárias | LOM 27 |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for i, r in enumerate(rows, 1):
        alerta = "**ALERTA**" if r["alerta_lom27"] else ""
        out.append(
            f"| {i} | {r['nome_parlamentar'] or r['vereador_id']} | {r['partido'] or ''} | {r['situacao'] or ''} | "
            f"{r['sessoes_ordinarias_em_exercicio']} | {r['presentes']} | {r['ausentes']} | {r['licenciado']} | "
            f"{_fmt_taxa(r['taxa_presenca'])} | {r['ausentes']}/{ordinarias} = {100 * r['fracao_faltas_lom27']:.1f}% | {alerta} |"
        )
    return out


def _frase_lideranca(con: duckdb.DuckDBPyConnection) -> str:
    """Diz se o 1º do ranking 2025 do spot coincide com o 1º de cada lista da imprensa (calculado, não fixo)."""
    top = ranking_faltas(con, 2025, 1)
    if not top:
        return "- Sem linhas de 2025 para comparar a liderança."
    nossos = faltas_por_apelido(con, 2025)
    lider_spot = next(
        (a for a, r in nossos.items() if r["vereador_id"] == top[0]["vereador_id"]), top[0]["vereador_id"]
    )
    lideres_imprensa = {fonte: max(lista, key=lista.get) for fonte, lista in IMPRENSA_2025.items()}
    iguais = all(lider == lider_spot for lider in lideres_imprensa.values())
    if iguais:
        return (
            f"- A divergência não inverte a conclusão: {lider_spot} lidera as faltas de 2025 no spot "
            f"({top[0]['ausentes']}) e em todas as listas da imprensa."
        )
    return (
        f"- Atenção: o 1º do spot em 2025 é {lider_spot} ({top[0]['ausentes']} faltas), mas a imprensa aponta "
        + "; ".join(f"{fonte}: {lider}" for fonte, lider in lideres_imprensa.items())
        + "."
    )


def _contexto(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    anos = _rows(
        con,
        """
        SELECT ano, count(DISTINCT num_sessao) AS ordinarias, max(num_sessao) AS ultima, max(data_sessao) AS data_ultima,
               count(*) AS linhas, count(DISTINCT vereador_id) AS vereadores
        FROM presenca_mvp WHERE tipo_sessao_codigo = 1 AND NOT sentinela GROUP BY ano ORDER BY ano
        """,
    )
    catalogo = _rows(
        con,
        """
        SELECT s.ano, s.num_sessao, s.data FROM sessao s
        WHERE s.tipo_sessao_codigo = 1 AND NOT s.sentinela AND s.ano >= 2025
          AND NOT EXISTS (SELECT 1 FROM presenca_mvp p WHERE p.ano = s.ano AND p.tipo_sessao_codigo = 1 AND p.num_sessao = s.num_sessao)
        ORDER BY 1, 2
        """,
    )
    incompletas = _rows(
        con,
        """
        SELECT ano, num_sessao, data_sessao, count(*) AS linhas FROM presenca_mvp
        WHERE tipo_sessao_codigo = 1 AND NOT sentinela GROUP BY 1, 2, 3 HAVING count(*) <> 43 ORDER BY 1, 2
        """,
    )
    (sentinelas,) = con.execute("SELECT count(*) FROM presenca WHERE ano >= 2025 AND sentinela").fetchone()
    (dups,) = con.execute("SELECT count(*) FROM presenca_mvp WHERE n_linhas_fonte > 1").fetchone()
    (sem_catalogo,) = con.execute(
        "SELECT count(DISTINCT (ano, tipo_sessao_codigo, num_sessao)) FROM presenca_mvp WHERE NOT no_catalogo"
    ).fetchone()
    (nomes,) = con.execute("SELECT count(DISTINCT nome) FROM presenca WHERE ano >= 2025").fetchone()
    (ids,) = con.execute("SELECT count(DISTINCT vereador_id) FROM presenca_mvp").fetchone()
    return {
        "anos": anos,
        "catalogo_sem_frequencia": catalogo,
        "sessoes_incompletas": incompletas,
        "sentinelas": sentinelas,
        "duplicatas": dups,
        "sem_catalogo": sem_catalogo,
        "nomes": nomes,
        "ids": ids,
    }


def render_report(con: duckdb.DuckDBPyConnection, hoje: date | None = None) -> str:
    hoje = hoje or date.today()
    ctx = _contexto(con)
    por_ano = {a["ano"]: a for a in ctx["anos"]}
    md: list[str] = [
        "# Presença bruta nas sessões ordinárias — 2025 e 2026 (parcial)",
        "",
        (
            f"Gerado em {hoje.isoformat()} por `uv run python -m spot.metrics.presenca` a partir de `data/silver/spot.duckdb` "
            "(tabela `metrica_presenca`). Fonte primária: grade `LEG_SYS_frequencia` (bronze `data/bronze/frequencia/`), "
            "sessões datadas pelo catálogo `LEG_SYS_sessao_ata`, nomes resolvidos por `data/seeds/vereador_alias.csv`."
        ),
        "",
        "## Método (spike §4.1, *presença bruta*)",
        "",
        "- Base: linhas da grade com `tipo_sessao_codigo = 1` (Sessão Ordinária), sentinelas (888/999) excluídas.",
        "- `em exercício` = nº de sessões ordinárias do ano em que o vereador tem linha na grade (Presente, Ausente ou Licenciado).",
        "- `taxa` = presentes / (presentes + ausentes); **Licenciado fica fora do denominador** (RI art. 17 §7 II).",
        f"- `sem dado` quando presentes + ausentes < {MIN_BASE} (critério de Campinas).",
        "- Alerta LOM art. 27: ausentes / ordinárias realizadas no ano ≥ 1/3. Para 2026 o denominador é parcial (ano em curso).",
        "- Esta é a presença **publicada pela CMS**; não é a 'falta descontável' (RI art. 17 §§6-7), que exige saber se a sessão foi deliberativa.",
        "",
    ]
    for ano in ANOS:
        info = por_ano.get(ano)
        if not info:
            md += [f"## {ano}", "", "Sem linhas na grade.", ""]
            continue
        parcial = " (YTD)" if ano == hoje.year else ""
        md += [
            f"## Ranking de faltas {ano}{parcial}",
            "",
            (
                f"{info['ordinarias']} sessões ordinárias (até a {info['ultima']}ª, em {info['data_ultima']}), "
                f"{info['linhas']} linhas da grade, {info['vereadores']} vereadores com pelo menos uma linha."
            ),
            "",
            *_tabela_ranking(ranking_faltas(con, ano), info["ordinarias"]),
            "",
        ]
    md += ["## Comparação com a imprensa (faltas 2025, sessões ordinárias)", ""]
    for fonte, lista in IMPRENSA_2025.items():
        cmp_ = comparar_imprensa(con, 2025, lista)
        rho = cmp_["spearman"]
        md += [
            f"### {fonte}",
            "",
            f"A fonte lista {cmp_['nomes_imprensa']} nomes; {len(cmp_['nomes_comuns'])} encontrados na grade"
            + (f" (não encontrados: {', '.join(cmp_['nao_encontrados'])})" if cmp_["nao_encontrados"] else "")
            + f". Spearman sobre os {len(cmp_['nomes_comuns'])} nomes comuns: "
            + ("n/d" if rho is None else f"**{rho:.2f}**")
            + f"; max |Δ| = **{cmp_['max_abs_delta']}**.",
            "",
            "| vereador | imprensa | spot | Δ (spot − imprensa) | licenciado (sessões) | em exercício |",
            "|---|---:|---:|---:|---:|---:|",
            *[
                f"| {r['alias']} | {r['imprensa']} | {r['spot']} | {r['delta']:+d} | {r['licenciado']} | {r['em_exercicio']} |"
                for r in cmp_["linhas"]
            ],
            "",
        ]
        if cmp_["top_spot_fora_da_imprensa"]:
            md += [
                f"Top-10 do spot ausentes da lista: {', '.join(cmp_['top_spot_fora_da_imprensa'])}.",
                "",
            ]
    md += [
        "### Leitura das divergências",
        "",
        "- A imprensa publica só a cabeça do ranking (6–7 nomes), então o Spearman é sobre esses nomes, não sobre um top-10 completo.",
        (
            "- Diferenças de ±1–2 faltas são compatíveis com (a) **correções retroativas de status** na grade da CMS "
            "(a errata da A Tarde em 2025 — Júlio Santos de 4 para 1 falta — mostra que o status muda depois de publicado; "
            "o próprio dump do spike de 16/10/2026 já difere do de 27/10/2026 em 1 falta para Anderson Ninho) e "
            "(b) **tratamento das licenças**: a imprensa aparentemente conta faltas em períodos que a grade hoje marca como `Licenciado` "
            "(Ireuda Silva: 7 na imprensa vs 5 ausentes + 25 licenciado aqui; Randerson Leal: 7 vs 6 + 13 licenciado)."
        ),
        _frase_lideranca(con),
        "",
        "## Ressalvas dos dados",
        "",
    ]
    ult = por_ano.get(hoje.year)
    if ult:
        md.append(
            f"- **2026 é parcial**: grade coletada até a {ult['ultima']}ª sessão ordinária ({ult['data_ultima']}); "
            f"o catálogo já lista {len(ctx['catalogo_sem_frequencia'])} sessão(ões) ordinária(s) 2025+ sem frequência publicada: "
            + (
                ", ".join(
                    f"{s['num_sessao']}/{s['ano']} ({s['data']})" for s in ctx["catalogo_sem_frequencia"]
                )
                or "nenhuma"
            )
            + "."
        )
    md += [
        f"- Sentinelas (sessões 888/999) excluídas: {ctx['sentinelas']} linha(s) em 2025–26 (nenhuma na prática).",
        (
            f"- Nomes da grade 2025+: {ctx['nomes']} apelidos → {ctx['ids']} `vereador_id` (50 nomes para 43 cadeiras: titulares licenciados e suplentes coexistem na grade). "
            "Nenhum nome ficou sem alias (o `build` falha se isso acontecer)."
        ),
        f"- Duplicatas exatas da fonte reduzidas a uma linha: {ctx['duplicatas']} chave(s) (sessão solene 3/2025, Kel Torres); não afeta as ordinárias.",
        f"- Sessões da grade sem data no catálogo: {ctx['sem_catalogo']}.",
    ]
    if ctx["sessoes_incompletas"]:
        md.append(
            "- Sessões ordinárias com nº de linhas ≠ 43 na grade (a fonte publica assim; quem não tem linha **não** conta como ausente nem como em exercício): "
            + "; ".join(
                f"{s['num_sessao']}/{s['ano']} ({s['data_sessao']}): {s['linhas']} linhas"
                for s in ctx["sessoes_incompletas"]
            )
            + "."
        )
    md += [
        (
            "- Suplentes e titulares afastados têm poucas sessões em exercício e aparecem como `sem dado` quando presentes + ausentes < 10; "
            "a situação (titular / licenciado / suplente) é a de 27/10/2026, não a da sessão."
        ),
        "- A grade não distingue sessão encerrada por falta de quórum (RI art. 25) nem falta justificada; só a ata diz isso (fase 2).",
        "- Status podem ser corrigidos retroativamente pela CMS; a recoleta mensal com `--force` e o diff entre snapshots do bronze são a forma de detectar.",
        "",
    ]
    return "\n".join(md)


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
    ap = argparse.ArgumentParser(description="metrica_presenca + relatório de presença bruta")
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
