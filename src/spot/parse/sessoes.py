"""Parser do catálogo de sessões: bronze (dump HTML de LEG_SYS_sessao_ata) -> data/silver/sessao.csv.

Sem rede. Lê o snapshot mais recente de ``data/bronze/sessoes/sessoes_catalogo_*.html``
(ou o arquivo passado em ``--bronze-file``) e escreve uma linha por sessão:

ano, tipo_sessao_codigo, tipo_sessao, num_sessao, data (ISO), ata_urls, pronunciamento_urls,
n_pdfs, sentinela (888/999 ou nº >= 500, fora da sequência anual), bronze_file.
Ordenado por (ano, tipo, nº, data). Chaves (ano, tipo, nº) duplicadas na fonte são mantidas e logadas.

Uso: ``uv run python -m spot.parse.sessoes [--bronze-file F] [--out data/silver/sessao.csv]``
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from lxml import html as lxml_html

from spot.config import BRONZE, SILVER, TIPOS_SESSAO
from spot.scriptcase import grid_total

log = logging.getLogger(__name__)

BRONZE_DIR = BRONZE / "sessoes"
OUT = SILVER / "sessao.csv"
SENTINELAS = {888, 999}
# Nº acima disto não cabe numa sequência anual (máx. observado ~120/ano): ex. "6.789" em 05/07/2024.
SENTINELA_MIN = 500
TIPO_CODIGO = {label: code for code, label in TIPOS_SESSAO.items()}

RE_LINK = re.compile(r"nm_gp_submit5\('([^']+)'")

COLUMNS = [
    "ano",
    "tipo_sessao_codigo",
    "tipo_sessao",
    "num_sessao",
    "data",
    "ata_urls",
    "pronunciamento_urls",
    "n_pdfs",
    "sentinela",
    "bronze_file",
]


@dataclass(frozen=True)
class Sessao:
    tipo_sessao: str
    num_sessao: int
    data: date
    ata_urls: tuple[str, ...]
    pronunciamento_urls: tuple[str, ...]

    @property
    def ano(self) -> int:
        return self.data.year

    @property
    def tipo_sessao_codigo(self) -> int | None:
        return TIPO_CODIGO.get(self.tipo_sessao)

    @property
    def n_pdfs(self) -> int:
        return sum(u.lower().endswith(".pdf") for u in self.ata_urls + self.pronunciamento_urls)

    @property
    def sentinela(self) -> bool:
        return self.num_sessao in SENTINELAS or self.num_sessao >= SENTINELA_MIN

    def row(self, bronze_file: str) -> dict[str, str]:
        return {
            "ano": str(self.ano),
            "tipo_sessao_codigo": "" if self.tipo_sessao_codigo is None else str(self.tipo_sessao_codigo),
            "tipo_sessao": self.tipo_sessao,
            "num_sessao": str(self.num_sessao),
            "data": self.data.isoformat(),
            "ata_urls": "|".join(self.ata_urls),
            "pronunciamento_urls": "|".join(self.pronunciamento_urls),
            "n_pdfs": str(self.n_pdfs),
            "sentinela": "true" if self.sentinela else "false",
            "bronze_file": bronze_file,
        }


def _cell_text(tr, field: str) -> str:
    cells = tr.xpath(f'.//td[contains(@class, "css_{field}_grid_line")]')
    return " ".join(cells[0].text_content().split()) if cells else ""


def _cell_links(tr, field: str) -> tuple[str, ...]:
    cells = tr.xpath(f'.//td[contains(@class, "css_{field}_grid_line")]')
    if not cells:
        return ()
    hrefs = cells[0].xpath(".//a/@href")
    return tuple(m.group(1).strip() for h in hrefs for m in [RE_LINK.search(h)] if m)


def parse_html(text: str) -> list[Sessao]:
    """Extrai as sessões das linhas de dados da grade (``<tr id="SC_ancorN">``)."""
    doc = lxml_html.fromstring(text)
    out: list[Sessao] = []
    for tr in doc.xpath('//tr[starts-with(@id, "SC_ancor")]'):
        tipo = _cell_text(tr, "ses_tse_codigo")
        numero = _cell_text(tr, "ses_ses_numero")
        data_txt = _cell_text(tr, "ses_ses_data")
        if not (tipo and numero and data_txt):
            log.warning("linha ignorada (campos vazios): tipo=%r num=%r data=%r", tipo, numero, data_txt)
            continue
        try:
            data = datetime.strptime(data_txt, "%d/%m/%Y").date()
            num = int(numero.replace(".", ""))  # a fonte tem "6.789" (separador de milhar)
        except ValueError:
            log.warning("linha ignorada (valores inválidos): tipo=%r num=%r data=%r", tipo, numero, data_txt)
            continue
        if tipo not in TIPO_CODIGO:
            log.warning("tipo de sessão desconhecido: %r (sessão %s de %s)", tipo, num, data_txt)
        out.append(Sessao(tipo, num, data, _cell_links(tr, "texto"), _cell_links(tr, "pronunciamento")))
    total = grid_total(text)
    if total is not None and total != len(out):
        log.warning("rodapé diz %d sessões, parser extraiu %d", total, len(out))
    return out


def sort_key(s: Sessao) -> tuple:
    return (s.ano, s.tipo_sessao_codigo or 99, s.num_sessao, s.data)


def latest_bronze(bronze_dir: Path = BRONZE_DIR) -> Path:
    files = sorted(bronze_dir.glob("sessoes_catalogo_*.html"))
    if not files:
        raise FileNotFoundError(f"nenhum sessoes_catalogo_*.html em {bronze_dir}")
    return files[-1]


def write_silver(sessoes: list[Sessao], bronze_file: str, out: Path = OUT) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        for s in sorted(sessoes, key=sort_key):
            w.writerow(s.row(bronze_file))
    return out


def summarize(sessoes: list[Sessao]) -> None:
    keys = Counter((s.ano, s.tipo_sessao_codigo, s.num_sessao) for s in sessoes)
    dups = {k: n for k, n in keys.items() if n > 1}
    if dups:
        log.warning("chaves (ano, tipo, nº) duplicadas: %s", dups)
    log.info("por tipo: %s", dict(Counter(s.tipo_sessao for s in sessoes)))
    log.info("por ano: %s", dict(sorted(Counter(s.ano for s in sessoes).items())))
    log.info("sentinelas: %s", [(s.ano, s.num_sessao, s.data.isoformat()) for s in sessoes if s.sentinela])
    recentes = [s for s in sessoes if s.ano >= 2025]
    log.info(
        "2025+: %d sessões, %d com ata, %d com pronunciamento, %d PDFs",
        len(recentes),
        sum(bool(s.ata_urls) for s in recentes),
        sum(bool(s.pronunciamento_urls) for s in recentes),
        sum(s.n_pdfs for s in recentes),
    )


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="bronze/sessoes -> silver/sessao.csv")
    ap.add_argument("--bronze-file", type=Path, help="dump HTML a usar (default: o snapshot mais recente)")
    ap.add_argument("--bronze-dir", type=Path, default=BRONZE_DIR)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    src = args.bronze_file or latest_bronze(args.bronze_dir)
    sessoes = parse_html(src.read_bytes().decode("latin-1"))
    summarize(sessoes)
    out = write_silver(sessoes, src.name, args.out)
    log.info("%d sessões -> %s", len(sessoes), out)


if __name__ == "__main__":
    main()
