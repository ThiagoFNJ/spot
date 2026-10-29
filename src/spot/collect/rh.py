"""Coletor de Recursos Humanos (folha de gabinete) da CMS.

Fonte: https://www.cms.ba.gov.br/transparencia/recursos-humanos — HTML simples com uma aba por ano
(`div.tab-pane#<ano>`) e, em cada aba, seções `h3` ("Relações de Servidores", "Relação de
Aniversariantes", "Relações de Estagiários", "Tabelas de Referência") seguidas de `ul li a`.

Saída em data/bronze/rh/:
- `recursos-humanos_{YYYY-MM-DD}.html` — snapshot da página (via write_bronze, com manifest).
- `links_{YYYY-MM-DD}.json` — inventário de todos os links da página (ano, seção, rótulo, url,
  competência inferida) + resultado do download de cada um dos selecionados.
- `{tipo}_{YYYY-MM}.pdf` — tipo ∈ {servidores, estagiarios}. Imutável; se já existe, não refaz.

Fluxo HTTP plano (não é ScriptCase), mas reaproveita `spot.scriptcase.Client` pelo rate limit
(≤ 1 req/s), retries, timeout e User-Agent, e `write_bronze` pelo manifest.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urljoin

from lxml import html as lxml_html

from spot.config import BRONZE, CMS_SITE
from spot.scriptcase import Client, Response, write_bronze

log = logging.getLogger(__name__)

PAGE_URL = f"{CMS_SITE}/transparencia/recursos-humanos"
BRONZE_RH = BRONZE / "rh"

MESES = {
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}
SECAO_TIPO = {
    "relações de servidores": "servidores",
    "relacoes de servidores": "servidores",
    "relações de estagiários": "estagiarios",
    "relacoes de estagiarios": "estagiarios",
}
RE_LABEL = re.compile(r"([A-Za-zçÇãÃ]+)\s*/?\s*(\d{4})")


@dataclass
class Link:
    ano: int
    secao: str
    tipo: str | None  # servidores | estagiarios | None (aniversariantes, tabelas, ...)
    label: str
    href: str  # como está no HTML (pode ter espaços/acentos)
    url: str  # absoluta e percent-encoded
    competencia: str | None  # YYYY-MM inferida do rótulo
    file: str | None = None  # nome em bronze quando é um PDF mensal de interesse
    status: str | None = None  # ok | existente | 404 | nao-pdf | erro | pulado
    tentativas: list[str] | None = None


def encode_url(href: str) -> str:
    """URL absoluta, percent-encoded (nomes têm espaços e acentos). Idempotente para hrefs já codificados."""
    absolute = urljoin(CMS_SITE + "/", href.strip())
    return quote(unquote(absolute), safe="/:%?=&")


def competencia_from_label(label: str, ano: int) -> str | None:
    m = RE_LABEL.search(label)
    if not m:
        return None
    mes = MESES.get(m.group(1).lower())
    if mes is None:
        return None
    if int(m.group(2)) != ano:
        log.warning("rótulo %r na aba %d: ano divergente", label, ano)
    return f"{m.group(2)}-{mes:02d}"


def parse_links(page_html: str) -> list[Link]:
    """Inventário de todos os links das abas de ano da página de RH."""
    doc = lxml_html.fromstring(page_html)
    links: list[Link] = []
    for pane in doc.xpath('//div[contains(@class, "tab-pane")]'):
        pane_id = pane.get("id", "")
        if not pane_id.isdigit():
            continue
        ano = int(pane_id)
        secao = ""
        for el in pane.iter():
            if el.tag == "h3":
                secao = " ".join(el.text_content().split())
            elif el.tag == "a" and el.get("href"):
                href = el.get("href").strip()
                if "uploads/rh" not in href and not href.lower().endswith((".pdf", ".xlsm", ".xls", ".xlsx")):
                    continue
                label = " ".join(el.text_content().split())
                tipo = SECAO_TIPO.get(secao.lower())
                comp = competencia_from_label(label, ano) if tipo else None
                file = f"{tipo}_{comp}.pdf" if tipo and comp and href.lower().endswith(".pdf") else None
                links.append(Link(ano, secao, tipo, label, href, encode_url(href), comp, file))
    return links


def typo_variants(url: str) -> list[str]:
    """Variações para nomes com erro de digitação conhecido (ex.: `SETEBMRO` -> 404)."""
    out: list[str] = []
    for bad, good in (("SETEBMRO", "SETEMBRO"),):
        if bad in url:
            fixed = url.replace(bad, good)
            out.append(fixed)
            out.append(fixed.replace("ESTAGIARIOS", "ESTAGI%C3%81RIOS"))
    return out


def fetch_pdf(client: Client, link: Link) -> Response | None:
    """GET do PDF; tenta variantes de typo em 404. Devolve a resposta válida (PDF) ou None."""
    link.tentativas = []
    for url in [link.url, *typo_variants(link.url)]:
        link.tentativas.append(url)
        resp = client.request("GET", url)
        if resp.status == 404:
            log.warning("404: %s", url)
            link.status = "404"
            continue
        if resp.status != 200:
            log.warning("HTTP %d: %s", resp.status, url)
            link.status = f"http-{resp.status}"
            continue
        if not resp.content.startswith(b"%PDF"):
            log.warning("não é PDF (%d bytes, começa com %r): %s", len(resp.content), resp.content[:8], url)
            link.status = "nao-pdf"
            continue
        link.url = url
        link.status = "ok"
        return resp
    return None


def collect(anos: list[int], tipos: list[str], dir_: Path = BRONZE_RH) -> dict[str, Any]:
    dir_.mkdir(parents=True, exist_ok=True)
    today = time.strftime("%Y-%m-%d")
    t0 = time.monotonic()
    with Client(host=CMS_SITE) as client:
        page = client.request("GET", PAGE_URL)
        if page.status != 200:
            raise RuntimeError(f"página de RH devolveu HTTP {page.status}")
        write_bronze(dir_, f"recursos-humanos_{today}.html", page, {"fonte": "rh", "tipo": "pagina"})
        links = parse_links(page.content.decode("utf-8", "replace"))
        log.info("%d links na página; anos com aba: %s", len(links), sorted({l.ano for l in links}))
        for ano in anos:
            n = sum(1 for l in links if l.ano == ano and l.tipo in tipos and l.file)
            if n == 0:
                log.warning("ano %d: nenhum PDF mensal publicado (%s)", ano, "/".join(tipos))
        baixados = 0
        for link in links:
            if not link.file or link.ano not in anos or link.tipo not in tipos:
                link.status = "pulado"
                continue
            if (dir_ / link.file).exists():
                link.status = "existente"
                log.info("já existe: %s", link.file)
                continue
            resp = fetch_pdf(client, link)
            if resp is None:
                continue
            write_bronze(
                dir_,
                link.file,
                resp,
                {
                    "fonte": "rh",
                    "tipo": link.tipo,
                    "competencia": link.competencia,
                    "label": link.label,
                    "href": link.href,
                },
            )
            baixados += 1
        requests_made = client.requests_made
    elapsed = time.monotonic() - t0
    inventory = {
        "coletado_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "page_url": PAGE_URL,
        "anos_selecionados": anos,
        "tipos_selecionados": tipos,
        "requests": requests_made,
        "segundos": round(elapsed, 1),
        "baixados": baixados,
        "links": [asdict(l) for l in links],
    }
    (dir_ / f"links_{today}.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    status = {}
    for l in links:
        if l.status and l.status != "pulado":
            status[l.status] = status.get(l.status, 0) + 1
    log.info("fim: %d requests, %.1fs, %d baixados, status=%s", requests_made, elapsed, baixados, status)
    return inventory


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Coleta PDFs mensais de RH (servidores e estagiários) da CMS.")
    ap.add_argument(
        "--anos", nargs="+", type=int, default=[2025, 2026], help="anos a baixar (default: 2025 2026)"
    )
    ap.add_argument(
        "--tipos", nargs="+", choices=["servidores", "estagiarios"], default=["servidores", "estagiarios"]
    )
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.DEBUG if args.verbose else logging.WARNING)
    collect(args.anos, args.tipos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
