"""Bronze do DOL → ``data/silver/proposicao_dol.csv``. Sem rede.

Uma linha por proposição com bronze coletado (``data/bronze/dol/<codigo>[__variante].json`` +
``manifest.jsonl``), escolhendo a variante que vale pela mesma regra do coletor
(:func:`spot.collect.dol.escolher`): ``frase`` com 1..10 edições ≥ ``ano-01-01`` > ``termos`` idem >
``numero`` com ≥ 1 edição. A edição linkada é a MAIS ANTIGA no intervalo (a íntegra sai logo após o
protocolo); ``ultima_dol_data`` e ``n_edicoes`` alimentam "citada em N edições".

``confianca``: ``alta`` = variante ``frase`` com 1..3 edições e a mais antiga no ano da proposição ou no
seguinte; ``media`` = ``frase`` nos outros casos; ``baixa`` = veio de variante afrouxada (``termos`` ou
``numero`` — esta última acha a pauta, não a íntegra). Sem edição aceitável: campos do DOL vazios,
``n_edicoes = 0`` e ``confianca`` vazia (a ``query`` registrada é a última tentada).
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from spot.collect.dol import (
    VARIANTES,
    codigo_de_nome,
    em_intervalo,
    escolher,
    itens,
    query_da_url,
    split_codigo,
)
from spot.config import BRONZE, SILVER

log = logging.getLogger(__name__)

BRONZE_DIR = BRONZE / "dol"
SILVER_OUT = SILVER / "proposicao_dol.csv"

COLUMNS = [
    "codigo",
    "tipo",
    "ano",
    "variante",
    "query",
    "n_edicoes",
    "dol_numero",
    "dol_data",
    "pdf_url",
    "dol_id",
    "ultima_dol_data",
    "confianca",
    "bronze_file",
]


def ler_manifest(dir_: Path) -> dict[str, dict[str, Any]]:
    """``{arquivo: entrada}`` do manifest.jsonl (a última entrada de cada arquivo vence)."""
    path = dir_ / "manifest.jsonl"
    out: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                e = json.loads(line)
                out[e["file"]] = e
    return out


def query_do_manifest(entry: dict[str, Any] | None) -> str:
    if not entry:
        return ""
    return entry.get("params", {}).get("query") or query_da_url(entry.get("url", "")) or ""


def variante_do_nome(nome: str) -> str:
    stem = nome.removesuffix(".json")
    return stem.split("__", 1)[1] if "__" in stem else "frase"


def confianca(variante: str, edicoes: list[dict[str, Any]], ano: int) -> str:
    if variante != "frase":
        return "baixa"
    primeira = int(edicoes[0]["data_publicacao"][:4])
    return "alta" if 1 <= len(edicoes) <= 3 and primeira in (ano, ano + 1) else "media"


def agrupar(dir_: Path) -> dict[str, dict[str, Path]]:
    """``{codigo: {variante: arquivo}}`` para todo ``*.json`` do bronze (menos progress.json)."""
    grupos: dict[str, dict[str, Path]] = {}
    for f in sorted(dir_.glob("*.json")):
        if f.name == "progress.json":
            continue
        v = variante_do_nome(f.name)
        if v not in VARIANTES:
            log.warning("arquivo com variante desconhecida ignorado: %s", f.name)
            continue
        grupos.setdefault(codigo_de_nome(f.stem), {})[v] = f
    return grupos


def linha(codigo: str, arquivos: dict[str, Path], manifest: dict[str, dict[str, Any]]) -> dict[str, object]:
    tipo, _, ano = split_codigo(codigo)
    resultados = {v: em_intervalo(itens(f.read_bytes()), ano) for v, f in arquivos.items()}
    escolha = escolher(resultados)
    ultima = next(v for v in reversed(VARIANTES) if v in arquivos)  # última variante tentada
    base: dict[str, object] = {
        "codigo": codigo,
        "tipo": tipo,
        "ano": ano,
        "variante": "",
        "query": query_do_manifest(manifest.get(arquivos[ultima].name)),
        "n_edicoes": 0,
        "dol_numero": "",
        "dol_data": "",
        "pdf_url": "",
        "dol_id": "",
        "ultima_dol_data": "",
        "confianca": "",
        "bronze_file": arquivos[ultima].name,
    }
    if escolha is None:
        return base
    variante, edicoes = escolha
    primeira = edicoes[0]
    return {
        **base,
        "variante": variante,
        "query": query_do_manifest(manifest.get(arquivos[variante].name)),
        "n_edicoes": len(edicoes),
        "dol_numero": primeira.get("numero") or "",
        "dol_data": primeira["data_publicacao"],
        "pdf_url": primeira.get("pdf_url", ""),
        "dol_id": primeira.get("id", ""),
        "ultima_dol_data": edicoes[-1]["data_publicacao"],
        "confianca": confianca(variante, edicoes, ano),
        "bronze_file": arquivos[variante].name,
    }


def parse_dir(dir_: Path) -> list[dict[str, object]]:
    manifest = ler_manifest(dir_)
    linhas = [linha(c, arqs, manifest) for c, arqs in agrupar(dir_).items()]
    linhas.sort(key=lambda r: (r["ano"], r["tipo"], split_codigo(str(r["codigo"]))[1]))
    return linhas


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


def build(bronze_dir: Path = BRONZE_DIR, out: Path = SILVER_OUT) -> int:
    if not bronze_dir.exists():
        log.warning("sem bronze em %s", bronze_dir)
        return 0
    rows = parse_dir(bronze_dir)
    n = write_csv(out, COLUMNS, rows)
    com_link = sum(1 for r in rows if r["dol_numero"])
    por_conf: dict[str, int] = {}
    for r in rows:
        por_conf[str(r["confianca"]) or "sem_link"] = por_conf.get(str(r["confianca"]) or "sem_link", 0) + 1
    log.info("%s: %d proposições, %d com edição (%s)", out, n, com_link, dict(sorted(por_conf.items())))
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="bronze/dol → silver/proposicao_dol.csv")
    ap.add_argument("--bronze-dir", type=Path, default=BRONZE_DIR)
    ap.add_argument("--out", type=Path, default=SILVER_OUT)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    build(args.bronze_dir, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
