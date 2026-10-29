"""Parser da frequência: data/bronze/frequencia/*.csv -> data/silver/presenca.csv (UTF-8). Sem rede.

Cada bronze é um export ISO-8859-1 (`;`, aspas, CRLF) de um mês × tipo, com 4 colunas:
No. da Sessão; Ano da Sessão; Parlamentar; Status. Mês e tipo vêm do nome do arquivo
`{YYYY-MM}_tipo{N}.csv`. A ordem das linhas do export não é estável: o silver é ordenado.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
from pathlib import Path
from typing import Any

from spot.config import BRONZE, SILVER, TIPOS_SESSAO

log = logging.getLogger(__name__)

BRONZE_DIR = BRONZE / "frequencia"
SILVER_FILE = SILVER / "presenca.csv"
RE_BRONZE_NAME = re.compile(r"^(\d{4}-\d{2})_tipo(\d+)\.csv$")
STATUS_OK = {"Presente", "Ausente", "Licenciado"}
SENTINELAS = {888, 999}
COLUMNS = [
    "mes_ref",
    "tipo_sessao_codigo",
    "tipo_sessao",
    "num_sessao",
    "ano",
    "nome_fonte",
    "nome",
    "status",
    "sentinela",
    "bronze_file",
]


def normalize_name(name: str) -> str:
    return " ".join(name.split())


def _manifest_labels(dir_: Path) -> dict[str, str]:
    """bronze_file -> tipo_label registrado no manifest (se houver)."""
    path = dir_ / "manifest.jsonl"
    out: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entry = json.loads(line)
                label = entry.get("params", {}).get("tipo_label")
                if label:
                    out[entry["file"]] = label
    return out


def parse_file(path: Path, tipo_label: str | None = None) -> list[dict[str, Any]]:
    """Linhas de um bronze. Levanta ValueError em cabeçalho/status/número inesperado."""
    m = RE_BRONZE_NAME.match(path.name)
    if not m:
        raise ValueError(f"nome de bronze fora do padrão: {path.name}")
    mes_ref, tipo = m.group(1), int(m.group(2))
    label = tipo_label or TIPOS_SESSAO.get(tipo) or f"tipo {tipo}"
    with path.open(encoding="latin-1", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows or rows[0][:4] != ["No. da Sessão", "Ano da Sessão", "Parlamentar", "Status"]:
        raise ValueError(f"{path.name}: cabeçalho inesperado {rows[0] if rows else None}")
    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows[1:], start=2):
        if len(r) != 4:
            raise ValueError(f"{path.name}:{i}: {len(r)} colunas")
        num, ano, nome_fonte, status = r
        if status not in STATUS_OK:
            raise ValueError(f"{path.name}:{i}: status desconhecido {status!r}")
        num_i, ano_i = int(num), int(ano)
        out.append(
            {
                "mes_ref": mes_ref,
                "tipo_sessao_codigo": tipo,
                "tipo_sessao": label,
                "num_sessao": num_i,
                "ano": ano_i,
                "nome_fonte": nome_fonte,
                "nome": normalize_name(nome_fonte),
                "status": status,
                "sentinela": num_i in SENTINELAS,
                "bronze_file": path.name,
            }
        )
    return out


def sort_key(row: dict[str, Any]) -> tuple:
    return (
        row["ano"],
        row["tipo_sessao_codigo"],
        row["num_sessao"],
        row["nome"],
        row["mes_ref"],
        row["status"],
    )


def parse_dir(dir_: Path = BRONZE_DIR) -> list[dict[str, Any]]:
    labels = _manifest_labels(dir_)
    rows: list[dict[str, Any]] = []
    files = sorted(p for p in dir_.glob("*.csv") if RE_BRONZE_NAME.match(p.name))
    for p in files:
        part = parse_file(p, labels.get(p.name))
        log.info("%s: %d linhas", p.name, len(part))
        rows.extend(part)
    rows.sort(key=sort_key)
    log.info("%d arquivos, %d linhas", len(files), len(rows))
    return rows


def write_silver(rows: list[dict[str, Any]], path: Path = SILVER_FILE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "sentinela": "true" if r["sentinela"] else "false"})
    return path


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    por_ano: dict[int, int] = {}
    status: dict[str, int] = {}
    for r in rows:
        por_ano[r["ano"]] = por_ano.get(r["ano"], 0) + 1
        status[r["status"]] = status.get(r["status"], 0) + 1
    return {
        "linhas": len(rows),
        "por_ano": dict(sorted(por_ano.items())),
        "status": dict(sorted(status.items())),
        "sentinelas": sum(r["sentinela"] for r in rows),
        "nomes": len({r["nome"] for r in rows}),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="bronze/frequencia -> silver/presenca.csv")
    ap.add_argument("--bronze", type=Path, default=BRONZE_DIR)
    ap.add_argument("--out", type=Path, default=SILVER_FILE)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    rows = parse_dir(args.bronze)
    out = write_silver(rows, args.out)
    log.info("gravado %s: %s", out, summarize(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
