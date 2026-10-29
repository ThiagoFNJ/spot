"""Coletor de proposições (produtividade legislativa).

Duas fontes, dois hosts:

1. ``prop_interna`` em ``https://cmsalvador.sys.inf.br/cl/prop_interna/`` — grade de todas as
   proposições (2004→). O export CSV desse host NÃO segue o fluxo export_ctrl/pbmd5 de
   ``Client.export_csv``: o ``sc_pb_<md5>.txt`` fica em ``steps=0`` para sempre e o GET de geração
   devolve um HTML curto com ``window.location='/p/tmp/sc_csv_<ts>_prop_interna.csv'``. O caminho
   documentado em ``docs/spike/evidence/produtividade_verify/NOTAS_VERIFICACAO.md`` §1 (POST
   ``nmgp_opcao=csv`` na raiz do app, mesmo cookie jar) funciona em 3 requests e é o que está aqui.
   Snapshot diário: ``prop_interna_{YYYY-MM-DD}.csv``.

2. ``LEG_SYS_produtividade_parlamentar_proposicao`` em ``45.4.247.157`` — resumo oficial
   Ano × Autor × tipo. O GET só mostra 2018; cada ano sai por POST ``ajax_navigate&opc=resumo_search``
   (o ``export_ctrl`` desse app falha, ver spike §3.2). Guardamos o HTML da tabela (campo
   ``summary_body`` do JSON) como ``resumo_{ano}_{YYYY-MM-DD}.html``.

Ambos idempotentes: arquivo existente em bronze não é refeito.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import re
import sys
import time
from datetime import date
from pathlib import Path

from spot.config import BRONZE, LEG_SYS_HOST, SYSINF_HOST
from spot.scriptcase import Client, Response, ScriptCaseError, bronze_exists, grid_total, write_bronze

log = logging.getLogger(__name__)

BRONZE_DIR = BRONZE / "proposicoes"

PROP_APP = "prop_interna"
PROP_BASE = f"{SYSINF_HOST}/cl"
RESUMO_APP = "LEG_SYS_produtividade_parlamentar_proposicao"
RESUMO_YEARS = (2025, 2026)

RE_CSV_LINK = re.compile(r"window\.location\s*=\s*'([^']+\.csv)'")

# Campos do form de export do prop_interna (NOTAS_VERIFICACAO.md §1). SC_module_export=grid
# obrigatório, como nos outros apps.
PROP_EXPORT_FIELDS = {
    "nmgp_opcao": "csv",
    "nm_delim_line": "1",
    "nm_delim_col": "1",
    "nm_delim_dados": "1",
    "nm_label_csv": "S",
    "nmgp_password": "",
    "SC_module_export": "grid",
}


def csv_link(text: str) -> str | None:
    """Link do CSV gerado, lido do `window.location` da resposta do POST csv."""
    m = RE_CSV_LINK.search(text)
    return m.group(1) if m else None


def resumo_parm(year: int) -> str:
    return (
        "TRA_TRA_DT_MOVIMENTACAO_SC_1__DL__TRA.TRA_DT_MOVIMENTACAO__DL__dth__DL__eql__DL__actual"
        f"__DL__YYYY__DL__{year}"
    )


def summary_body(text: str) -> str:
    """Extrai o HTML da tabela (`setValue[field=summary_body]`) da resposta JSON do resumo_search."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ScriptCaseError(f"resposta do resumo_search não é JSON: {text[:200]!r}") from exc
    for item in data.get("setValue", []):
        if item.get("field") == "summary_body":
            return item["value"]
    raise ScriptCaseError(
        f"resumo_search sem summary_body: campos={[i.get('field') for i in data.get('setValue', [])]}"
    )


# ---- prop_interna ---------------------------------------------------------------------------


def collect_prop_interna(snapshot: date, dir_: Path = BRONZE_DIR) -> Path | None:
    """Export completo da grade prop_interna → `prop_interna_{snapshot}.csv`. None se já existia."""
    name = f"prop_interna_{snapshot.isoformat()}.csv"
    if bronze_exists(dir_, name):
        log.info("prop_interna: %s já existe, pulando", name)
        return None
    t0 = time.monotonic()
    with Client(host=SYSINF_HOST) as c:
        init, root = c.open_app(PROP_APP, PROP_BASE)
        total = grid_total(root.text)
        gen = c.request(
            "POST",
            c.app_url(PROP_APP, PROP_BASE),
            data={"script_case_init": init, **PROP_EXPORT_FIELDS},
            timeout=300,
        )
        link = csv_link(gen.text)
        if not link:
            raise ScriptCaseError(f"prop_interna: POST csv sem link: {gen.fatal() or gen.text[:300]!r}")
        resp = c.request("GET", SYSINF_HOST + link, timeout=300)
        if not resp.content.startswith(b'""') and b";" not in resp.content[:200]:
            raise ScriptCaseError(f"prop_interna: corpo do CSV inesperado: {resp.content[:200]!r}")
        n_rows = csv_records(resp.content)
        path = write_bronze(
            dir_,
            name,
            resp,
            {
                "app": PROP_APP,
                "init": init,
                "grid_total": total,
                "csv_records": n_rows,
                "snapshot": snapshot.isoformat(),
                "export_post": {"url": c.app_url(PROP_APP, PROP_BASE), "fields": PROP_EXPORT_FIELDS},
            },
        )
        log.info(
            "prop_interna: %s %d bytes, %d registros (rodapé da grade: %s), %d requests, %.1fs",
            path.name,
            len(resp.content),
            n_rows,
            total,
            c.requests_made,
            time.monotonic() - t0,
        )
        if total is not None and n_rows != total:
            log.warning("prop_interna: CSV com %d registros mas grade diz %d", n_rows, total)
        return path


def csv_records(raw: bytes) -> int:
    """Registros de dados do CSV (ementas têm quebras de linha internas; contar linhas não serve)."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    return sum(1 for _ in csv.reader(io.StringIO(text, newline=""), delimiter=";", quotechar='"')) - 1


# ---- resumo oficial -------------------------------------------------------------------------


def fetch_resumo(c: Client, init: str, year: int) -> Response:
    """POST resumo_search do ano. Devolve uma Response cujo content é o HTML da tabela (UTF-8)."""
    body = f"nmgp_opcao=ajax_navigate&script_case_init={init}&opc=resumo_search&parm={resumo_parm(year)}"
    raw = c.request(
        "POST",
        c.app_url(RESUMO_APP) + "index.php",
        content=body.encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    if raw.fatal():
        raise ScriptCaseError(f"resumo {year}: {raw.fatal()}")
    # O JSON vem com \uXXXX (latin-1 seria seguro), mas o host declara UTF-8: decodificar como UTF-8
    # com fallback para não gravar mojibake no bronze se um dia vierem bytes multibyte crus.
    try:
        json_text = raw.content.decode("utf-8")
    except UnicodeDecodeError:
        json_text = raw.text
    html = summary_body(json_text)
    if f">{year}<" not in html:
        raise ScriptCaseError(f"resumo {year}: tabela não contém o ano pedido (filtro não aplicou?)")
    return Response(raw.url, raw.status, html.encode("utf-8"), raw.seconds, raw.method, raw.body)


def collect_resumo(years: tuple[int, ...], snapshot: date, dir_: Path = BRONZE_DIR) -> list[Path]:
    pending = [y for y in years if not bronze_exists(dir_, f"resumo_{y}_{snapshot.isoformat()}.html")]
    for y in set(years) - set(pending):
        log.info("resumo %d: snapshot %s já existe, pulando", y, snapshot.isoformat())
    if not pending:
        return []
    t0 = time.monotonic()
    written: list[Path] = []
    with Client(host=LEG_SYS_HOST) as c:
        init, _ = c.open_app(RESUMO_APP)
        for y in pending:
            resp = fetch_resumo(c, init, y)
            name = f"resumo_{y}_{snapshot.isoformat()}.html"
            written.append(write_bronze(dir_, name, resp, {"app": RESUMO_APP, "init": init, "ano": y}))
            log.info("resumo %d: %s %d bytes", y, name, len(resp.content))
        log.info("resumo: %d anos, %d requests, %.1fs", len(pending), c.requests_made, time.monotonic() - t0)
    return written


# ---- CLI ------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Coleta prop_interna (CSV completo) e resumos oficiais por ano.")
    ap.add_argument("--snapshot", default=date.today().isoformat(), help="data do snapshot (YYYY-MM-DD)")
    ap.add_argument("--years", type=int, nargs="*", default=list(RESUMO_YEARS), help="anos do resumo")
    ap.add_argument("--skip-prop", action="store_true", help="não exportar o prop_interna")
    ap.add_argument("--skip-resumo", action="store_true", help="não buscar os resumos")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    snapshot = date.fromisoformat(args.snapshot)
    if not args.skip_prop:
        collect_prop_interna(snapshot)
    if not args.skip_resumo:
        collect_resumo(tuple(args.years), snapshot)
    return 0


if __name__ == "__main__":
    sys.exit(main())
