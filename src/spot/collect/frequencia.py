"""Coletor da frequência (app LEG_SYS_frequencia): um CSV por mês × tipo de sessão.

Fluxo por combinação (docs/HANDOVER.md §2.3 + adendo 2026-10-27):
  GET raiz -> init -> filtro de mês -> (lista de tipos com dados vem nessa resposta)
  -> filtro de tipo -> total da grade -> export CSV -> linhas == total -> bronze.

Para cada tipo seguinte do mesmo mês recarrega-se a página (novo init), nunca se misturam inits.
Idempotente: combinação cujo arquivo já existe em data/bronze/frequencia/ é pulada (salvo --force).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from spot.config import BRONZE, MVP_START
from spot.scriptcase import Client, Response, ScriptCaseError, bronze_exists, grid_total, write_bronze

log = logging.getLogger(__name__)

APP = "LEG_SYS_frequencia"
BRONZE_DIR = BRONZE / "frequencia"
CSV_HEADER = ["No. da Sessão", "Ano da Sessão", "Parlamentar", "Status"]

RE_MONTH_OPTION = re.compile(r'value="(20\d\d-\d\d)##@@(\d\d/\d{4}) "')
RE_TIPO_LINK = re.compile(
    r"nm_proc_int_search\('link','nn','Tipo de Sessão','pre_tse_codigo','(\d+)##@@([^']*)'"
)
RE_JS_UNICODE = re.compile(r"\\u([0-9a-fA-F]{4})")


def bronze_name(ym: str, tipo: int) -> str:
    return f"{ym}_tipo{tipo}.csv"


def month_parm(ym: str) -> str:
    """`2025-03` -> parm do filtro "Mês e Ano" (com o espaço final do valor exibido)."""
    y, m = ym.split("-")
    return f"pre_pre_data_presenca__DL__Mês e Ano__DL__dh__DL__{ym}##@@{m}/{y} __DL__S"


def tipo_parm(code: int, label: str) -> str:
    return f"pre_tse_codigo__DL__Tipo de Sessão__DL__nn__DL__{code}##@@{label}__DL__S"


def discover_months(root_text: str, since: str = MVP_START, until: str | None = None) -> list[str]:
    """Meses com dados listados no filtro da raiz, `since <= ym <= until`, ascendentes."""
    found = {ym for ym, _ in RE_MONTH_OPTION.findall(root_text)}
    if not found:
        raise ScriptCaseError("raiz sem opções de 'Mês e Ano' (layout mudou ou página de erro)")
    return sorted(ym for ym in found if ym >= since and (until is None or ym <= until))


def tipo_options(nav_text: str) -> list[tuple[int, str]]:
    """Tipos de sessão com dados, lidos da resposta (JSON com `\\uXXXX`) do filtro de mês."""
    text = RE_JS_UNICODE.sub(lambda m: chr(int(m.group(1), 16)), nav_text)
    seen: dict[int, str] = {}
    for code, label in RE_TIPO_LINK.findall(text):
        seen.setdefault(int(code), label)
    return sorted(seen.items())


def count_csv_rows(content: bytes) -> tuple[list[str], int]:
    """(cabeçalho, nº de linhas de dados) de um export ISO-8859-1 `;`."""
    reader = csv.reader(io.StringIO(content.decode("latin-1"), newline=""), delimiter=";")
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        return [], 0
    return rows[0], len(rows) - 1


def _manifest_tipos(dir_: Path) -> dict[str, list[int]]:
    """ym -> tipos registrados como disponíveis na última coleta daquele mês (do manifest)."""
    path = dir_ / "manifest.jsonl"
    out: dict[str, list[int]] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        p = json.loads(line).get("params", {})
        if p.get("ym") and p.get("tipos_disponiveis") is not None:
            out[p["ym"]] = [int(t) for t in p["tipos_disponiveis"]]
    return out


def _export_combination(
    client: Client, init: str, ym: str, code: int, label: str
) -> tuple[Response, int, int, dict[str, Any]]:
    total = client.filter_total(APP, init, tipo_parm(code, label))
    if total <= 0:
        raise ScriptCaseError(f"{ym} tipo {code}: filtro de tipo devolveu total {total}")
    resp, progress = client.export_csv(APP, init)
    header, rows = count_csv_rows(resp.content)
    if header != CSV_HEADER:
        raise ScriptCaseError(f"{ym} tipo {code}: cabeçalho inesperado {header}")
    if rows != total:
        raise ScriptCaseError(f"{ym} tipo {code}: CSV com {rows} linhas != total da grade {total}")
    return resp, total, rows, progress


def collect(
    since: str = MVP_START,
    until: str | None = None,
    force: bool = False,
    dir_: Path = BRONZE_DIR,
) -> dict[str, Any]:
    t0 = time.monotonic()
    stats: dict[str, Any] = {"files": 0, "skipped": 0, "requests": 0, "rows": 0, "errors": []}
    # Um único Client (uma sessão PHP, como no HANDOVER §2.3): o rate limit de 1 req/s vale
    # também entre meses; cada combinação recarrega a raiz e ganha um init novo.
    with Client() as c:
        try:
            _, root = c.open_app(APP)
            total_dia = grid_total(root.text)
            months = discover_months(root.text, since, until)
            log.info("total sem filtro hoje: %s; meses alvo (%d): %s", total_dia, len(months), months)
            stats["grid_total_sem_filtro"] = total_dia
            stats["months"] = months

            known_tipos = {} if force else _manifest_tipos(dir_)
            for ym in months:
                if ym in known_tipos and all(
                    bronze_exists(dir_, bronze_name(ym, t)) for t in known_tipos[ym]
                ):
                    log.info("%s: todos os tipos (%s) já em bronze, pulo", ym, known_tipos[ym])
                    stats["skipped"] += len(known_tipos[ym])
                    continue
                try:
                    _collect_month(c, ym, force, dir_, total_dia, stats)
                except ScriptCaseError as exc:
                    log.error("%s: %s", ym, exc)
                    stats["errors"].append(f"{ym}: {exc}")
        finally:
            stats["requests"] = c.requests_made
    stats["seconds"] = round(time.monotonic() - t0, 1)
    log.info("fim: %s", stats)
    return stats


def _collect_month(
    c: Client, ym: str, force: bool, dir_: Path, total_dia: int | None, stats: dict[str, Any]
) -> None:
    init, _ = c.open_app(APP)
    nav = c.navigate(APP, init, month_parm(ym))
    total_mes = grid_total(nav.text)
    tipos = tipo_options(nav.text)
    log.info("%s: total do mês=%s tipos=%s", ym, total_mes, tipos)
    if not tipos:
        raise ScriptCaseError(f"{ym}: nenhum tipo de sessão listado (total do mês {total_mes})")
    fresh = True  # o init atual já tem o filtro de mês aplicado
    soma_tipos, pulou = 0, False
    for code, label in tipos:
        name = bronze_name(ym, code)
        existe = bronze_exists(dir_, name)
        if existe and not force:
            log.info("%s: já existe, pulo", name)
            stats["skipped"] += 1
            pulou = True
            continue
        if not fresh:
            init, _ = c.open_app(APP)
            c.navigate(APP, init, month_parm(ym))
        fresh = False
        try:
            resp, total, rows, progress = _export_combination(c, init, ym, code, label)
        except ScriptCaseError as exc:
            log.error("%s: %s", name, exc)
            stats["errors"].append(f"{name}: {exc}")
            pulou = True
            continue
        soma_tipos += total
        params = {
            "ym": ym,
            "tipo_codigo": code,
            "tipo_label": label,
            "grid_total": total,
            "csv_rows": rows,
            "grid_total_mes": total_mes,
            "grid_total_sem_filtro": total_dia,
            "tipos_disponiveis": [t for t, _ in tipos],
            "script_case_init": init,
            "export_link": progress.get("link"),
        }
        if existe:  # --force: só descarta o bronze antigo depois de o export novo ter validado
            (dir_ / name).unlink()
            log.warning("%s: --force, substituído", name)
        write_bronze(dir_, name, resp, params)
        stats["files"] += 1
        stats["rows"] += rows
        log.info("%s: %d linhas gravadas (%d requests até agora)", name, rows, c.requests_made)
    if not pulou and total_mes is not None and soma_tipos != total_mes:
        # só é comparável quando nenhum tipo do mês foi pulado/falhou nesta execução
        log.warning("%s: soma dos tipos %d != total do mês %d", ym, soma_tipos, total_mes)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Coleta a frequência (LEG_SYS_frequencia) para bronze.")
    ap.add_argument("--since", default=MVP_START, help="primeiro mês YYYY-MM (default: MVP_START)")
    ap.add_argument("--until", default=None, help="último mês YYYY-MM (default: o mais recente)")
    ap.add_argument("--force", action="store_true", help="refaz combinações já existentes em bronze")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    stats = collect(args.since, args.until, args.force)
    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
