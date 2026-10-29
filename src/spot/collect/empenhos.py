"""Coletor de empenhos do portal financeiro (``https://cmsalvador.sys.inf.br/ca/gridRegistroEmpenho/``).

Grade ScriptCase 9 com TODOS os empenhos da CMS (verba compensatória dos vereadores, diárias, contratos…).
Fluxo validado em 2026-10-27 (spike §3.3 + esta coleta):

1. GET da raiz -> cookie jar + ``script_case_init`` (só no JS; ``Client.open_app`` cobre);
2. POST ``index.php`` ``script_case_init=<n>&nmgp_opcao=muda_qt_linhas&nmgp_quant_linhas=500`` -> HTML completo
   (~5 MB) com os 500 primeiros registros e o rodapé ``[1 a 500 de N]`` -> página 1;
3. paginação: o link "2" da barra chama ``nm_gp_submit_rec(501)`` -> ``ajax_navigate('rec', 501)``, ou seja
   POST ``nmgp_opcao=ajax_navigate&script_case_init=<n>&opc=rec&parm=<primeiro registro>`` com
   ``X-Requested-With``. A resposta é JSON ASCII (``\\uXXXX``) com ``setValue`` = [sc_grid_head,
   sc_grid_toobar_top, NM_Grid_Search, sc_grid_body, sc_grid_toobar_bot] e ``setVar`` (``nm_gp_rec_ini``,
   ``nm_gp_rec_fim``, ``scQtReg``). O tamanho de página (500) fica na sessão PHP indexada pelo init.
   O POST de formulário ``nmgp_opcao=rec&nmgp_parms=501`` NÃO pagina (devolve a página 1 de novo).
   Guardamos os fragmentos HTML do JSON concatenados (UTF-8), como o coletor de proposições faz com
   ``summary_body`` -> páginas 2..N.

Bronze: ``data/bronze/empenhos/empenhos_{YYYY-MM-DD}_p{NNN}.html`` (um arquivo por página por dia; se o
snapshot do dia já está completo, nada é refeito) + ``manifest.jsonl``. Validação: Σ linhas das páginas ==
total do rodapé (grade viva: um empenho inserido durante a coleta desloca as páginas; o aviso fica no log e
o parser deduplica por número).

``gridRegistroDespesa`` (liquidação/pagamento, ~92 mil linhas) NÃO é coletada aqui; ver nota no fim do módulo.

CLI: ``uv run python -m spot.collect.empenhos [--date YYYY-MM-DD] [--max-pages N] [--rows 500]``.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import date
from pathlib import Path

from spot.config import BRONZE, SYSINF_HOST
from spot.scriptcase import Client, Response, ScriptCaseError, grid_total, write_bronze

log = logging.getLogger(__name__)

BRONZE_DIR = BRONZE / "empenhos"
APP = "gridRegistroEmpenho"
BASE = f"{SYSINF_HOST}/ca"
PAGE_ROWS = 500

# Cada registro da grade é um <TR class="scGridFieldOdd|Even" ... id="SC_ancorN">.
RE_ANCOR = re.compile(r'<TR\s+class="scGridField(?:Odd|Even)"[^>]*\bid="SC_ancor\d+"', re.I)
RE_PAGE = re.compile(r"^empenhos_(\d{4}-\d{2}-\d{2})_p(\d{3})\.html$")


def page_name(snapshot: date, page: int) -> str:
    return f"empenhos_{snapshot.isoformat()}_p{page:03d}.html"


def count_rows(html: str) -> int:
    return len(RE_ANCOR.findall(html))


def n_pages(total: int, rows: int = PAGE_ROWS) -> int:
    return max(1, -(-total // rows))


def ajax_page_html(raw: bytes) -> tuple[str, dict[str, object]]:
    """JSON do ``ajax_navigate`` -> (HTML dos fragmentos concatenados, setVar relevantes)."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScriptCaseError(f"resposta do ajax_navigate não é JSON: {raw[:200]!r}") from exc
    values = data.get("setValue", [])
    fields = [v.get("field") for v in values]
    if "sc_grid_body" not in fields:
        raise ScriptCaseError(f"ajax_navigate sem sc_grid_body (campos: {fields})")
    html = "\n".join(f"<!-- setValue[{v.get('field')}] -->\n{v.get('value', '')}" for v in values)
    vars_ = {
        v["var"]: v["value"]
        for v in data.get("setVar", [])
        if v.get("var") in ("nm_gp_ini", "nm_gp_rec_ini", "nm_gp_rec_fim", "nm_gp_fim", "scQtReg")
    }
    return html, vars_


def fetch_rec(c: Client, init: str, first: int) -> tuple[Response, dict[str, object]]:
    """POST ``ajax_navigate`` ``opc=rec`` a partir do registro ``first`` (1-based). Devolve HTML em UTF-8."""
    body = f"nmgp_opcao=ajax_navigate&script_case_init={init}&opc=rec&parm={first}"
    raw = c.request(
        "POST",
        c.app_url(APP, BASE) + "index.php",
        content=body.encode("ascii"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=300,
    )
    if raw.fatal():
        raise ScriptCaseError(f"rec {first}: {raw.fatal()}")
    html, vars_ = ajax_page_html(raw.content)
    return Response(raw.url, raw.status, html.encode("utf-8"), raw.seconds, raw.method, raw.body), vars_


def snapshot_complete(snapshot: date, dir_: Path, rows: int = PAGE_ROWS) -> bool:
    """True se a página 1 do dia existe e todas as páginas que o seu rodapé implica também existem."""
    p1 = dir_ / page_name(snapshot, 1)
    if not p1.exists():
        return False
    total = grid_total(p1.read_text("utf-8", errors="replace"))
    if total is None:
        return False
    return all((dir_ / page_name(snapshot, p)).exists() for p in range(1, n_pages(total, rows) + 1))


def collect(
    snapshot: date,
    max_pages: int | None = None,
    rows: int = PAGE_ROWS,
    dir_: Path = BRONZE_DIR,
) -> dict[str, object]:
    """Baixa as páginas do dia que ainda não existem. Devolve estatísticas (total da grade, linhas, páginas)."""
    if max_pages is None and snapshot_complete(snapshot, dir_, rows):
        log.info("empenhos: snapshot %s já completo em %s, nada a fazer", snapshot, dir_)
        return {"snapshot": snapshot.isoformat(), "skipped": True}
    t0 = time.monotonic()
    written: list[Path] = []
    n_rows = 0
    with Client(host=SYSINF_HOST) as c:
        init, root = c.open_app(APP, BASE)
        total_get = grid_total(root.text)
        p1 = c.dump_grid(APP, init, rows=rows, base=BASE)
        if p1.fatal():
            raise ScriptCaseError(f"muda_qt_linhas: {p1.fatal()}")
        total = grid_total(p1.text)
        if total is None:
            raise ScriptCaseError("página 1 sem rodapé [a a b de N]")
        if total_get is not None and total_get != total:
            log.warning("total da grade mudou entre o GET (%d) e a página 1 (%d)", total_get, total)
        pages = n_pages(total, rows)
        if max_pages is not None:
            pages = min(pages, max_pages)
        n1 = count_rows(p1.text)
        n_rows += n1
        written.append(
            write_bronze(
                dir_,
                page_name(snapshot, 1),
                p1,
                {
                    "app": APP,
                    "init": init,
                    "page": 1,
                    "rows": rows,
                    "grid_total": total,
                    "n_rows": n1,
                    "via": "muda_qt_linhas",
                },
            )
        )
        log.info(
            "empenhos p001: %d linhas, %d bytes, total da grade %d (%d páginas)",
            n1,
            len(p1.content),
            total,
            pages,
        )
        for page in range(2, pages + 1):
            first = (page - 1) * rows + 1
            name = page_name(snapshot, page)
            resp, vars_ = fetch_rec(c, init, first)
            n = count_rows(resp.text)
            n_rows += n
            written.append(
                write_bronze(
                    dir_,
                    name,
                    resp,
                    {
                        "app": APP,
                        "init": init,
                        "page": page,
                        "rows": rows,
                        "first": first,
                        "grid_total": total,
                        "n_rows": n,
                        "via": "ajax_navigate rec (fragmentos HTML do JSON)",
                        "setVar": vars_,
                    },
                )
            )
            log.info("empenhos p%03d: registros %d.., %d linhas, %d bytes", page, first, n, len(resp.content))
            if n == 0:
                log.warning("página %d vazia: parando", page)
                break
        esperado = total if max_pages is None else min(total, pages * rows)
        if n_rows != esperado:
            log.warning(
                "empenhos: %d linhas coletadas em %d páginas, mas a grade diz %d (esperado %d) — grade viva ou página incompleta",
                n_rows,
                len(written),
                total,
                esperado,
            )
        else:
            log.info(
                "empenhos: %d linhas em %d páginas == total da grade (%d) ✔", n_rows, len(written), esperado
            )
        log.info("empenhos: %d requests, %.1fs", c.requests_made, time.monotonic() - t0)
    return {
        "snapshot": snapshot.isoformat(),
        "grid_total": total,
        "pages": len(written),
        "n_rows": n_rows,
        "files": [p.name for p in written],
        "skipped": False,
    }


# ``gridRegistroDespesa`` (https://cmsalvador.sys.inf.br/ca/gridRegistroDespesa/, ~92 mil linhas = fases
# liquidação/pagamento) tem o mesmo protocolo (GET -> init; muda_qt_linhas; ajax_navigate rec) e expõe o número
# do empenho (``2026NE000755``) em cada linha: o join futuro é ``empenho.numero = despesa.numero_empenho``,
# agregando por fase (liquidado/pago) para comparar empenhado x pago. Não coletar antes de filtrar por
# período (185 páginas de 500) — fica para a fase 2.


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Coleta todas as páginas do gridRegistroEmpenho (snapshot diário)."
    )
    ap.add_argument("--date", default=date.today().isoformat(), help="data do snapshot (YYYY-MM-DD)")
    ap.add_argument("--max-pages", type=int, default=None, help="limitar páginas (teste)")
    ap.add_argument("--rows", type=int, default=PAGE_ROWS, help="linhas por página (padrão 500)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    stats = collect(date.fromisoformat(args.date), args.max_pages, args.rows)
    log.info("%s", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
