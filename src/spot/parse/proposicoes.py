"""Bronze → silver das proposições. Sem rede.

- `data/silver/proposicao.csv`: uma linha por proposição, a partir do snapshot mais recente de
  `prop_interna_{data}.csv` (todos os anos; barato). Ordenado por (ano, tipo, numero).
- `data/silver/produtividade_resumo.csv`: formato longo (ano, autor_fonte, tipo, quantidade) a partir
  do snapshot mais recente de cada `resumo_{ano}_{data}.html`. A coluna Total e as linhas de
  subtotal/total geral não viram linhas; são usadas só para validar a soma.
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import re
import sys
from collections import defaultdict
from collections.abc import Iterable
from html import unescape
from pathlib import Path

from spot.config import BRONZE, SILVER

log = logging.getLogger(__name__)

BRONZE_DIR = BRONZE / "proposicoes"
SILVER_PROP = SILVER / "proposicao.csv"
SILVER_RESUMO = SILVER / "produtividade_resumo.csv"

PROP_COLUMNS = [
    "codigo",
    "tipo",
    "numero",
    "ano",
    "autor_fonte",
    "autores",
    "ementa",
    "movimentado",
    "localizacao",
    "situacao",
    "outros_fonte",
    "sentinela",
    "bronze_file",
]
RESUMO_COLUMNS = ["ano", "autor_fonte", "tipo", "quantidade", "bronze_file"]

RE_CODIGO = re.compile(r"^\s*([A-Z]+)-(\d+)/(\d{4})\s*$")
RE_DATA = re.compile(r"^\s*(\d{2})/(\d{2})/(\d{4})\s*$")
RE_SNAPSHOT = re.compile(r"_(\d{4}-\d{2}-\d{2})\.\w+$")
RE_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
RE_TD = re.compile(r"<td([^>]*)>(.*?)</td>", re.DOTALL)
RE_TAG = re.compile(r"<[^>]+>")
RE_WS = re.compile(r"\s+")
# Separadores de coautoria no campo Autor (o campo normalmente traz um nome só).
RE_AUTOR_SEP = re.compile(r"\s*(?:\||;|\s/\s)\s*")
# Registro de teste do sistema (ex.: PLE-9999/2025 "Documento de teste - aba Legislativo", situação ".").
# Fica no bronze e no silver com `sentinela = true`; excluir das métricas (mesma regra das sessões 888/999).
RE_TESTE = re.compile(r"^\s*documento de teste\b", re.IGNORECASE)
NUMERO_TESTE = 9999


def is_sentinela(numero: int, ementa: str) -> bool:
    return numero >= NUMERO_TESTE or bool(RE_TESTE.match(ementa))


def decode(raw: bytes) -> str:
    """prop_interna (sys.inf.br) entrega UTF-8; os apps do 45.4.247.157 entregam ISO-8859-1."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def clean(s: str) -> str:
    return RE_WS.sub(" ", s).strip()


def iso_date(s: str) -> str:
    m = RE_DATA.match(s)
    if not m:
        return clean(s)
    d, mo, y = m.groups()
    return f"{y}-{mo}-{d}"


def latest_snapshot(dir_: Path, prefix: str) -> Path | None:
    """Arquivo mais recente `{prefix}_{YYYY-MM-DD}.*` (ordenação lexicográfica da data)."""
    files = sorted(p for p in dir_.glob(f"{prefix}_*") if RE_SNAPSHOT.search(p.name))
    return files[-1] if files else None


# ---- proposicao -----------------------------------------------------------------------------


def parse_prop_interna(raw: bytes, bronze_file: str) -> list[dict[str, object]]:
    text = decode(raw)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=";", quotechar='"')
    header = next(reader)
    idx = {clean(h): i for i, h in enumerate(header)}
    required = ["Proposição", "Autor", "Ementa", "Movimentado", "Localização", "Situação"]
    missing = [h for h in required if h not in idx]
    if missing:
        raise ValueError(f"{bronze_file}: colunas ausentes {missing}; cabeçalho={header}")
    outros_i = idx.get("Autor/Requerente/Vistas/Outros")
    rows: list[dict[str, object]] = []
    bad = 0
    short = 0
    for rec in reader:
        if not any(f.strip() for f in rec):
            continue
        if len(rec) < len(header):
            short += 1
            log.warning(
                "%s: registro com %d campos (cabeçalho tem %d), ignorado: %r",
                bronze_file,
                len(rec),
                len(header),
                rec[:2],
            )
            continue
        codigo = clean(rec[idx["Proposição"]])
        m = RE_CODIGO.match(codigo)
        if not m:
            bad += 1
            log.warning("%s: código fora do padrão, ignorado: %r", bronze_file, codigo)
            continue
        tipo, numero, ano = m.group(1), int(m.group(2)), int(m.group(3))
        autor_fonte = rec[idx["Autor"]]
        autores = "|".join(dict.fromkeys(clean(a) for a in RE_AUTOR_SEP.split(autor_fonte) if clean(a)))
        ementa = clean(rec[idx["Ementa"]])
        sentinela = is_sentinela(numero, ementa)
        if sentinela:
            log.info(
                "%s: registro de teste marcado como sentinela: %s (%s)", bronze_file, codigo, ementa[:60]
            )
        rows.append(
            {
                "codigo": codigo,
                "tipo": tipo,
                "numero": numero,
                "ano": ano,
                "autor_fonte": autor_fonte.strip(),
                "autores": autores,
                "ementa": ementa,
                "movimentado": iso_date(rec[idx["Movimentado"]]),
                "localizacao": clean(rec[idx["Localização"]]),
                "situacao": clean(rec[idx["Situação"]]),
                "outros_fonte": clean(rec[outros_i]) if outros_i is not None and outros_i < len(rec) else "",
                "sentinela": "true" if sentinela else "false",
                "bronze_file": bronze_file,
            }
        )
    if bad or short:
        log.warning(
            "%s: %d registros ignorados por código inválido, %d por campos a menos", bronze_file, bad, short
        )
    rows.sort(key=lambda r: (r["ano"], r["tipo"], r["numero"], r["codigo"]))
    dups = len(rows) - len({r["codigo"] for r in rows})
    if dups:
        log.warning("%s: %d códigos duplicados", bronze_file, dups)
    return rows


# ---- resumo ---------------------------------------------------------------------------------


def _cells(tr: str) -> list[tuple[str, str]]:
    """[(classe, texto)] de cada <td> de uma linha."""
    out = []
    for attrs, inner in RE_TD.findall(tr):
        cls = re.search(r'class="([^"]*)"', attrs)
        txt = clean(unescape(RE_TAG.sub(" ", inner)).replace("\xa0", " "))
        out.append((cls.group(1) if cls else "", txt))
    return out


def _int(s: str) -> int:
    return int(s.replace(".", "")) if s else 0


def parse_resumo(raw: bytes, bronze_file: str) -> list[dict[str, object]]:
    """Tabela Ano × Autor × tipo do resumo oficial → linhas longas. Valida contra Total/subtotal."""
    html = decode(raw)
    header: list[str] | None = None
    rows: list[dict[str, object]] = []
    totals: dict[tuple[int, str], int] = {}
    subtotal: dict[int, int] = {}
    year_sum: dict[int, int] = defaultdict(int)
    for tr_attrs_inner in re.finditer(r"<tr([^>]*)>(.*?)</tr>", html, re.DOTALL):
        attrs, inner = tr_attrs_inner.groups()
        cells = _cells(inner)
        if "sc-ui-summary-header-row" in attrs:
            labels = [t for _, t in cells]
            if labels and labels[0] == "Ano" and header is None:
                header = labels
            continue
        if "scGridSummaryLine" not in attrs or header is None or not cells:
            continue
        classes = [c for c, _ in cells]
        texts = [t for _, t in cells]
        if texts and texts[0] == "Total Geral":
            continue
        if "scGridSummarySubtotal" in classes[0]:
            subtotal[int(texts[0])] = _int(texts[-1])
            continue
        if len(texts) != len(header):
            log.warning(
                "%s: linha com %d células, cabeçalho com %d: %r",
                bronze_file,
                len(texts),
                len(header),
                texts[:3],
            )
            continue
        ano, autor = int(texts[0]), texts[1]
        total = _int(texts[-1])
        soma = 0
        for tipo, q in zip(header[2:-1], texts[2:-1], strict=True):
            if not q:
                continue
            n = _int(q)
            soma += n
            rows.append(
                {"ano": ano, "autor_fonte": autor, "tipo": tipo, "quantidade": n, "bronze_file": bronze_file}
            )
        if soma != total:
            log.warning("%s: %d/%s soma %d != Total %d", bronze_file, ano, autor, soma, total)
        totals[(ano, autor)] = total
        year_sum[ano] += soma
    if header is None:
        raise ValueError(f"{bronze_file}: cabeçalho do resumo não encontrado")
    for ano, s in year_sum.items():
        n_autores = sum(1 for a in totals if a[0] == ano)
        if ano not in subtotal:
            log.warning(
                "%s: %d: %d proposições, %d autores; linha de subtotal ausente, soma não validada",
                bronze_file,
                ano,
                s,
                n_autores,
            )
        elif subtotal[ano] != s:
            log.warning("%s: soma dos autores de %d = %d != subtotal %d", bronze_file, ano, s, subtotal[ano])
        else:
            log.info("%s: %d: %d proposições, %d autores (bate com subtotal)", bronze_file, ano, s, n_autores)
    rows.sort(key=lambda r: (r["ano"], r["autor_fonte"], r["tipo"]))
    return rows


# ---- escrita --------------------------------------------------------------------------------


def write_csv(path: Path, columns: list[str], rows: Iterable[dict[str, object]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)
            n += 1
    return n


def build_proposicao(bronze_dir: Path = BRONZE_DIR, out: Path = SILVER_PROP) -> int:
    src = latest_snapshot(bronze_dir, "prop_interna")
    if src is None:
        log.warning("nenhum prop_interna_*.csv em %s", bronze_dir)
        return 0
    rows = parse_prop_interna(src.read_bytes(), src.name)
    n = write_csv(out, PROP_COLUMNS, rows)
    por_ano = defaultdict(int)
    for r in rows:
        por_ano[r["ano"]] += 1
    log.info(
        "%s: %d proposições de %s; últimos anos: %s", out, n, src.name, dict(sorted(por_ano.items())[-3:])
    )
    return n


def build_resumo(bronze_dir: Path = BRONZE_DIR, out: Path = SILVER_RESUMO) -> int:
    by_year: dict[int, Path] = {}
    for p in sorted(bronze_dir.glob("resumo_*.html")):
        m = re.match(r"resumo_(\d{4})_", p.name)
        if m:
            by_year[int(m.group(1))] = p  # ordenado: o último snapshot de cada ano vence
    if not by_year:
        log.warning("nenhum resumo_*.html em %s", bronze_dir)
        return 0
    rows: list[dict[str, object]] = []
    for _, p in sorted(by_year.items()):
        rows.extend(parse_resumo(p.read_bytes(), p.name))
    n = write_csv(out, RESUMO_COLUMNS, rows)
    log.info("%s: %d linhas (anos %s)", out, n, sorted(by_year))
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="prop_interna + resumos → silver")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    build_proposicao()
    build_resumo()
    return 0


if __name__ == "__main__":
    sys.exit(main())
