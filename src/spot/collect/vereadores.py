"""Coletor da dimensão de vereadores: site institucional da CMS.

Fonte: https://www.cms.ba.gov.br/vereadores (abas "Vereadores" e "Ex-vereadores e vereadores
licenciados") e cada perfil /vereadores/<slug>. HTML puro, sem ScriptCase; reaproveita o
`spot.scriptcase.Client` só pelo rate limit (≤ 1 req/s), retry e User-Agent.

Bronze (imutável, idempotente): data/bronze/vereadores/vereadores.html (índice) e
data/bronze/vereadores/<slug>.html (perfis). manifest.jsonl via `write_bronze`.
"""

from __future__ import annotations

import argparse
import logging
import re
import time
from pathlib import Path

from spot.config import BRONZE, CMS_SITE
from spot.scriptcase import Client, ScriptCaseError, bronze_exists, write_bronze

log = logging.getLogger(__name__)

BRONZE_DIR = BRONZE / "vereadores"
INDEX_NAME = "vereadores.html"
INDEX_URL = f"{CMS_SITE}/vereadores"
RE_SLUG = re.compile(r"getUrl\('/vereadores/([a-z0-9-]+)'")


def slugs_from_index(html: str) -> list[str]:
    """Slugs dos perfis citados no índice, na ordem da página, sem repetição."""
    seen: dict[str, None] = {}
    for slug in RE_SLUG.findall(html):
        seen.setdefault(slug, None)
    return list(seen)


def profile_url(slug: str) -> str:
    return f"{CMS_SITE}/vereadores/{slug}"


def collect(
    bronze_dir: Path = BRONZE_DIR, *, only: list[str] | None = None, min_gap: float = 1.0
) -> dict[str, int]:
    """Baixa índice + perfis que ainda não estão no bronze. Devolve contadores."""
    stats = {"requests": 0, "written": 0, "skipped": 0, "failed": 0}
    t0 = time.monotonic()
    with Client(host=CMS_SITE, min_gap=min_gap, timeout=60.0) as client:
        index_path = bronze_dir / INDEX_NAME
        if bronze_exists(bronze_dir, INDEX_NAME):
            log.info("índice já no bronze: %s", index_path)
            stats["skipped"] += 1
        else:
            resp = client.request("GET", INDEX_URL)
            if resp.status != 200:
                raise ScriptCaseError(f"índice HTTP {resp.status}")
            write_bronze(bronze_dir, INDEX_NAME, resp, {"tipo": "indice"})
            stats["written"] += 1
        html = index_path.read_text(encoding="utf-8", errors="replace")
        slugs = slugs_from_index(html)
        if not slugs:
            raise ScriptCaseError("índice sem nenhum getUrl('/vereadores/<slug>')")
        if only:
            slugs = [s for s in slugs if s in set(only)]
        log.info("%d perfis no índice", len(slugs))
        for slug in slugs:
            name = f"{slug}.html"
            if bronze_exists(bronze_dir, name):
                stats["skipped"] += 1
                continue
            try:
                resp = client.request("GET", profile_url(slug))
            except ScriptCaseError as exc:
                log.error("perfil %s falhou: %s", slug, exc)
                stats["failed"] += 1
                continue
            if resp.status != 200:
                log.error("perfil %s HTTP %d, não gravo", slug, resp.status)
                stats["failed"] += 1
                continue
            write_bronze(bronze_dir, name, resp, {"tipo": "perfil", "slug": slug})
            stats["written"] += 1
        stats["requests"] = client.requests_made
    stats["seconds"] = round(time.monotonic() - t0)
    log.info("coleta: %s", stats)
    return stats


FOTOS_DIR = BRONZE_DIR / "fotos"


def fotos(
    slugs: list[str], bronze_dir: Path = BRONZE_DIR, site_dir: Path | None = None, min_gap: float = 1.0
) -> dict[str, str]:
    """Baixa a foto oficial de cada perfil (``div.photo`` → ``/uploads/vereadores/<hash>.jpg``) para
    ``bronze/vereadores/fotos/<slug>.jpg`` (idempotente) e, se ``site_dir`` for dado, copia para ``site/fotos/``.
    Devolve ``{slug: caminho relativo no site}``. Fotos de agentes públicos publicadas pela própria Câmara."""
    import shutil
    import time

    import httpx

    from spot.parse.vereadores import RE_FOTO

    out: dict[str, str] = {}
    FOTOS_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.Client(
        timeout=30, headers={"User-Agent": "spot-cms-monitor/0.1 (+github)"}, follow_redirects=True
    ) as c:
        for slug in slugs:
            html_path = bronze_dir / f"{slug}.html"
            if not html_path.exists():
                continue
            m = RE_FOTO.search(html_path.read_text(encoding="utf-8", errors="replace"))
            if not m:
                log.warning("%s: perfil sem foto", slug)
                continue
            url = m.group(1)
            url = CMS_SITE + url if url.startswith("/") else url
            dest = FOTOS_DIR / f"{slug}.jpg"
            if not dest.exists():
                try:
                    r = c.get(url)
                    r.raise_for_status()
                    dest.write_bytes(r.content)
                    log.info("%s: foto %d bytes", slug, len(r.content))
                except httpx.HTTPError as e:
                    log.warning("%s: falha ao baixar foto %s (%s)", slug, url, e)
                    continue
                time.sleep(min_gap)
            if site_dir is not None:
                (site_dir / "fotos").mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, site_dir / "fotos" / dest.name)
            out[slug] = f"fotos/{slug}.jpg"
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Coleta /vereadores e perfis da CMS para o bronze.")
    ap.add_argument("--bronze-dir", type=Path, default=BRONZE_DIR)
    ap.add_argument(
        "--fotos",
        action="store_true",
        help="baixa as fotos dos 50 vereadores de vereador_dim para bronze e site/fotos",
    )
    ap.add_argument("--only", nargs="*", help="limita a estes slugs (depois de baixar o índice)")
    ap.add_argument("--min-gap", type=float, default=1.0, help="segundos entre requests (>= 1)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    if args.fotos:
        import csv

        from spot.config import ROOT, SEEDS

        with (SEEDS / "vereador_dim.csv").open(encoding="utf-8") as f:
            slugs = [r["vereador_id"] for r in csv.DictReader(f)]
        got = fotos(slugs, args.bronze_dir, site_dir=ROOT / "site", min_gap=max(args.min_gap, 1.0))
        log.info("fotos: %d de %d vereadores", len(got), len(slugs))
        return 0
    stats = collect(args.bronze_dir, only=args.only, min_gap=max(args.min_gap, 1.0))
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
