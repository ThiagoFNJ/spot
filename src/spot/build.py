"""Monta ``data/silver/spot.duckdb`` a partir dos CSVs silver + seeds curados.

Regras:
- recria o banco do zero a cada execução (nada incremental);
- uma tabela por CSV, com o nome do arquivo (``presenca.csv`` -> ``presenca``);
- tabelas derivadas: ``presenca_mvp`` (presença 2025+ resolvida para ``vereador_id`` e datada pela
  sessão do catálogo, com flags ``sentinela`` e ``em_exercicio``);
- falha alto se algum nome da grade de frequência 2025+ não tiver alias em ``vereador_alias``.

Sem rede. CLI: ``uv run python -m spot.build [--silver DIR] [--seeds DIR] [--db FILE]``.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import duckdb

from spot.config import SEEDS, SILVER

log = logging.getLogger(__name__)

DB_NAME = "spot.duckdb"
MVP_ANO_INICIO = 2025


class BuildError(RuntimeError):
    """Inconsistência que impede montar o banco (ex.: nome sem alias)."""


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def csv_tables(*dirs: Path) -> dict[str, Path]:
    """``{nome_da_tabela: caminho}`` para todo ``*.csv`` dos diretórios (ordem alfabética, sem repetir nome)."""
    tables: dict[str, Path] = {}
    for d in dirs:
        for path in sorted(d.glob("*.csv")):
            name = path.stem
            if name in tables:
                raise BuildError(f"tabela duplicada: {name} em {tables[name]} e {path}")
            tables[name] = path
    return tables


def load_csv(con: duckdb.DuckDBPyConnection, name: str, path: Path) -> int:
    """Cria ``name`` a partir do CSV (UTF-8, header, tipos inferidos sobre o arquivo inteiro). Devolve nº de linhas."""
    con.execute(
        f"CREATE OR REPLACE TABLE {_ident(name)} AS "
        f"SELECT * FROM read_csv({_lit(str(path))}, header = true, sample_size = -1, encoding = 'utf-8')"
    )
    (n,) = con.execute(f"SELECT count(*) FROM {_ident(name)}").fetchone()
    log.info("tabela %-22s %8d linhas  <- %s", name, n, path.name)
    return n


def _require(con: duckdb.DuckDBPyConnection, *tables: str) -> None:
    have = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    missing = [t for t in tables if t not in have]
    if missing:
        raise BuildError(f"tabelas obrigatórias ausentes: {', '.join(missing)}")


def unresolved_names(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Nomes de ``presenca`` (ano >= MVP) sem alias ``fonte = 'frequencia'``."""
    rows = con.execute(
        """
        SELECT DISTINCT p.nome
        FROM presenca p
        LEFT JOIN vereador_alias a ON a.fonte = 'frequencia' AND a.alias = p.nome
        WHERE p.ano >= ? AND a.vereador_id IS NULL
        ORDER BY p.nome
        """,
        [MVP_ANO_INICIO],
    ).fetchall()
    return [r[0] for r in rows]


def build_presenca_mvp(con: duckdb.DuckDBPyConnection) -> int:
    """``presenca_mvp``: presença 2025+ -> vereador_id (alias) -> data da sessão (catálogo).

    - ``sentinela`` = sentinela na grade OU no catálogo (sessões 888/999 etc.);
    - ``em_exercicio`` = a linha existe na grade para o par (vereador, sessão) e não é sentinela
      (spike §4.1: "existe linha em LEG_SYS_frequencia"). ``Licenciado`` continua em exercício
      para este flag; a exclusão do denominador é feita pelo ``status`` na métrica;
    - duplicatas exatas da fonte em (ano, tipo, nº, nome) são reduzidas a uma linha (``n_linhas_fonte`` guarda quantas).
    """
    _require(con, "presenca", "vereador_alias", "vereador_dim", "sessao")
    missing = unresolved_names(con)
    if missing:
        raise BuildError(
            f"{len(missing)} nome(s) da grade de frequência {MVP_ANO_INICIO}+ sem alias em vereador_alias "
            f"(fonte=frequencia): {', '.join(missing)}"
        )
    con.execute(
        """
        CREATE OR REPLACE TABLE presenca_mvp AS
        WITH dedup AS (
            SELECT
                p.ano, p.tipo_sessao_codigo, p.tipo_sessao, p.num_sessao, p.mes_ref,
                p.nome_fonte, p.nome, p.status, p.sentinela AS sentinela_grade, p.bronze_file,
                count(*) OVER (PARTITION BY p.ano, p.tipo_sessao_codigo, p.num_sessao, p.nome) AS n_linhas_fonte,
                row_number() OVER (
                    PARTITION BY p.ano, p.tipo_sessao_codigo, p.num_sessao, p.nome ORDER BY p.status, p.mes_ref
                ) AS rn
            FROM presenca p
            WHERE p.ano >= ?
        ),
        cat AS (
            SELECT ano, tipo_sessao_codigo, num_sessao, min(data) AS data_sessao,
                   bool_or(sentinela) AS sentinela_catalogo, count(*) AS n_catalogo
            FROM sessao
            GROUP BY 1, 2, 3
        )
        SELECT
            d.ano, d.tipo_sessao_codigo, d.tipo_sessao, d.num_sessao, c.data_sessao, d.mes_ref,
            a.vereador_id, v.nome_parlamentar, v.partido,
            d.nome_fonte, d.nome, d.status,
            (d.sentinela_grade OR coalesce(c.sentinela_catalogo, false)) AS sentinela,
            (NOT (d.sentinela_grade OR coalesce(c.sentinela_catalogo, false))) AS em_exercicio,
            (c.data_sessao IS NOT NULL) AS no_catalogo,
            d.n_linhas_fonte, d.bronze_file
        FROM dedup d
        JOIN vereador_alias a ON a.fonte = 'frequencia' AND a.alias = d.nome
        LEFT JOIN vereador_dim v ON v.vereador_id = a.vereador_id
        LEFT JOIN cat c
          ON c.ano = d.ano AND c.tipo_sessao_codigo = d.tipo_sessao_codigo AND c.num_sessao = d.num_sessao
        WHERE d.rn = 1
        ORDER BY d.ano, d.tipo_sessao_codigo, d.num_sessao, a.vereador_id
        """,
        [MVP_ANO_INICIO],
    )
    (n, dups, sem_data, sent) = con.execute(
        """
        SELECT count(*), sum(CASE WHEN n_linhas_fonte > 1 THEN 1 ELSE 0 END),
               sum(CASE WHEN NOT no_catalogo THEN 1 ELSE 0 END), sum(CASE WHEN sentinela THEN 1 ELSE 0 END)
        FROM presenca_mvp
        """
    ).fetchone()
    log.info(
        "presenca_mvp: %d linhas (%d chaves com duplicata na fonte, %d sem sessão no catálogo, %d sentinela)",
        n,
        dups,
        sem_data,
        sent,
    )
    if sem_data:
        faltam = con.execute(
            "SELECT DISTINCT ano, tipo_sessao_codigo, num_sessao FROM presenca_mvp WHERE NOT no_catalogo ORDER BY 1,2,3"
        ).fetchall()
        log.warning("sessões da grade ausentes do catálogo (sem data): %s", faltam)
    return n


def build(silver: Path = SILVER, seeds: Path = SEEDS, db_path: Path | None = None) -> Path:
    """Recria o DuckDB a partir dos CSVs e devolve o caminho do banco."""
    db_path = db_path or silver / DB_NAME
    for p in (db_path, db_path.with_name(db_path.name + ".wal")):
        if p.exists():
            p.unlink()
    tables = csv_tables(silver, seeds)
    if not tables:
        raise BuildError(f"nenhum CSV em {silver} ou {seeds}")
    con = duckdb.connect(str(db_path))
    try:
        for name, path in tables.items():
            load_csv(con, name, path)
        build_presenca_mvp(con)
    finally:
        con.close()
    log.info("banco gravado em %s (%d tabelas base)", db_path, len(tables))
    return db_path


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="silver/*.csv + seeds/*.csv -> silver/spot.duckdb")
    ap.add_argument("--silver", type=Path, default=SILVER)
    ap.add_argument("--seeds", type=Path, default=SEEDS)
    ap.add_argument("--db", type=Path, default=None, help=f"padrão: <silver>/{DB_NAME}")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    build(args.silver, args.seeds, args.db)


if __name__ == "__main__":
    main()
