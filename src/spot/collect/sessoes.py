"""Coletor do catálogo de sessões plenárias (app LEG_SYS_sessao_ata).

Captura, uma vez por dia, um snapshot do catálogo inteiro:

- ``sessoes_catalogo_{YYYY-MM-DD}.html`` — HTML da grade completa via ``dump_grid``
  (``muda_qt_linhas``); é a única forma de obter os links das atas/pronunciamentos
  (``http://177.21.11.131:8888/LEG/Upload/<GUID>.pdf``), que o export CSV não traz.
- ``sessoes_catalogo_{YYYY-MM-DD}.csv`` — export CSV server-side do mesmo estado, só para
  cruzar a contagem de linhas.

Os PDFs das atas NÃO são baixados aqui (fase 2); só as URLs ficam no HTML bronze.

Uso: ``uv run python -m spot.collect.sessoes [--date YYYY-MM-DD] [--rows 1000] [--no-csv]``
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import time
from datetime import date
from pathlib import Path

from spot.config import BRONZE
from spot.scriptcase import (
    RE_TOTAL,
    Client,
    Response,
    ScriptCaseError,
    bronze_exists,
    grid_total,
    write_bronze,
)

log = logging.getLogger(__name__)

APP = "LEG_SYS_sessao_ata"
BRONZE_DIR = BRONZE / "sessoes"
DEFAULT_ROWS = 1000

ROW_ID_MARK = 'id="id_sc_field_ses_ses_numero_'  # um por linha de dados da grade


def html_name(day: date) -> str:
    return f"sessoes_catalogo_{day.isoformat()}.html"


def csv_name(day: date) -> str:
    return f"sessoes_catalogo_{day.isoformat()}.csv"


def check_dump(resp: Response, expected_total: int | None) -> int:
    """Garante que o dump trouxe a grade inteira numa página só. Devolve o total."""
    m = RE_TOTAL.search(resp.text)
    if not m:
        raise ScriptCaseError(f"dump sem rodapé [a a b de N]: {resp.fatal() or resp.text[:200]!r}")
    first, last, total = (int(g) for g in m.groups())
    if first != 1 or last != total:
        raise ScriptCaseError(f"dump incompleto: [{first} a {last} de {total}] (aumente --rows)")
    if expected_total is not None and total != expected_total:
        raise ScriptCaseError(f"total do dump ({total}) difere do total da abertura ({expected_total})")
    n_rows = resp.text.count(ROW_ID_MARK)
    if n_rows != total:
        raise ScriptCaseError(f"dump com {n_rows} linhas de dados, rodapé diz {total}")
    return total


def csv_rows(resp: Response) -> int:
    """Linhas de dados do export (desconta o cabeçalho; campos com quebra de linha contam uma vez)."""
    rows = [r for r in csv.reader(io.StringIO(resp.text), delimiter=";") if r]
    return max(len(rows) - 1, 0)


def collect(
    day: date, *, rows: int = DEFAULT_ROWS, with_csv: bool = True, bronze_dir: Path = BRONZE_DIR
) -> dict:
    """Coleta o snapshot do dia. Idempotente: se os arquivos já existem, não faz request."""
    need_html = not bronze_exists(bronze_dir, html_name(day))
    need_csv = with_csv and not bronze_exists(bronze_dir, csv_name(day))
    summary = {
        "date": day.isoformat(),
        "html": None,
        "csv": None,
        "total": None,
        "csv_rows": None,
        "requests": 0,
    }
    if not need_html and not need_csv:
        log.info("snapshot de %s já existe em %s; nada a fazer", day, bronze_dir)
        return summary

    t0 = time.monotonic()
    with Client() as client:
        init, home = client.open_app(APP)
        total_home = grid_total(home.text)
        if need_html:
            dump = client.dump_grid(APP, init, rows=rows)
            total = check_dump(dump, total_home)
            path = write_bronze(
                bronze_dir, html_name(day), dump, {"app": APP, "init": init, "rows": rows, "total": total}
            )
            summary["html"], summary["total"] = str(path), total
            log.info("dump HTML: %d sessões, %d bytes -> %s", total, len(dump.content), path)
        if need_csv:
            csv, progress = client.export_csv(APP, init)
            n = csv_rows(csv)
            path = write_bronze(
                bronze_dir, csv_name(day), csv, {"app": APP, "init": init, "progress": progress, "rows": n}
            )
            summary["csv"], summary["csv_rows"] = str(path), n
            log.info("export CSV: %d linhas, %d bytes -> %s", n, len(csv.content), path)
            if summary["total"] is not None and n != summary["total"]:
                log.warning("CSV tem %d linhas, dump HTML tem %d: cruzamento falhou", n, summary["total"])
            elif total_home is not None and n != total_home:
                log.warning("CSV tem %d linhas, grade da abertura diz %d", n, total_home)
        summary["requests"] = client.requests_made
    summary["seconds"] = round(time.monotonic() - t0, 1)
    log.info("coleta concluída: %s", summary)
    return summary


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="Coleta o catálogo de sessões (LEG_SYS_sessao_ata) para o bronze."
    )
    ap.add_argument(
        "--date", type=date.fromisoformat, default=date.today(), help="data do snapshot (default: hoje)"
    )
    ap.add_argument("--rows", type=int, default=DEFAULT_ROWS, help="muda_qt_linhas (default: %(default)s)")
    ap.add_argument("--no-csv", action="store_true", help="não faz o export CSV de cruzamento")
    ap.add_argument("--bronze-dir", type=Path, default=BRONZE_DIR)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    collect(args.date, rows=args.rows, with_csv=not args.no_csv, bronze_dir=args.bronze_dir)


if __name__ == "__main__":
    main()
