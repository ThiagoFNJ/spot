"""Consulta de pessoal do TCM-BA (Controle Social → Pessoal), exportada à mão em XLSX (bronze/tcm_pessoal -> silver).

A consulta pública fica atrás de reCAPTCHA e **não é automatizada** (ver `data/bronze/tcm_pessoal/README.md`). Uma pessoa
exporta a planilha por mês e grava em ``data/bronze/tcm_pessoal/<AAAA-MM>/``; ``ingest`` aceita os arquivos com nome
aleatório da pasta Downloads, descobre a competência no cabeçalho ("Câmara Municipal de SALVADORMARÇO/2026") e os
renomeia para ``pessoal_749_<AAAA-MM>.xlsx`` com ``manifest.jsonl``.

Planilha: 2 linhas de cabeçalho, linha de títulos ``Nome | Matrícula | Tipo Regime | Cargo | Salário Líquido | Salário
Base | Vantagens | Gratificação | 13º Salário | Carga H Semanal | Situação | Ingresso/Admissão`` e, no fim, uma linha
"Receita Corrente Líquida de ..." que não é servidor. **Não traz lotação**: a matrícula é a chave para cruzar com
``folha`` (RH do site, com centro de custo) e assim recuperar o gabinete de quem já estava lá em 2025.

Saída: ``data/silver/tcm_pessoal.csv``. Sem CPF na fonte; nomes são de agentes públicos.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
import shutil
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import openpyxl

from spot.config import BRONZE, SILVER
from spot.parse.etcm_vc import MESES_PREFIXO, _fold

log = logging.getLogger(__name__)

BRONZE_TCM = BRONZE / "tcm_pessoal"
OUT = SILVER / "tcm_pessoal.csv"
UNIDADE = "749"  # cdEntidade da Câmara Municipal de Salvador no TCM-BA

HEADER = (
    "Nome", "Matrícula", "Tipo Regime", "Cargo", "Salário Líquido", "Salário Base", "Vantagens", "Gratificação",
    "13º Salário", "Carga H Semanal", "Situação", "Ingresso/Admissão",
)  # fmt: skip
COLUMNS = [
    "competencia",
    "matricula",
    "servidor",
    "regime",
    "cargo",
    "funcao",
    "grau",
    "simbolo",
    "salario_liquido",
    "salario_base",
    "vantagens",
    "gratificacao",
    "decimo_terceiro",
    "remuneracao_bruta",
    "carga_horaria",
    "situacao",
    "admissao",
    "arquivo",
]
# "Câmara Municipal de SALVADORMARÇO/2026": o mês vem colado ao nome da unidade.
RE_COMPETENCIA = re.compile(
    r"(JANEIRO|FEVEREIRO|MAR[ÇC]O|ABRIL|MAIO|JUNHO|JULHO|AGOSTO|SETEMBRO|OUTUBRO|NOVEMBRO|DEZEMBRO)\s*/\s*(\d{4})",
    re.I,
)
# "ASSESSOR PARLAMENTAR-G-13 CC10" -> função, grau G-13, símbolo CC10.
RE_GRAU = re.compile(r"^(.*?)\s*-?\s*G\s*-?\s*(\d{1,2})\s*((?:CC|FC|FG)\s*-?\s*\d+)?\s*$", re.I)
RE_SIMBOLO = re.compile(r"^(.*?)\s+((?:CC|FC|FG)\s*-?\s*\d+)\s*$", re.I)


class LayoutError(ValueError):
    """Planilha fora do layout da consulta de pessoal do TCM-BA."""


def brl(s: Any) -> Decimal | None:
    if s is None:
        return None
    t = re.sub(r"[^\d,.-]", "", str(s)).replace(".", "").replace(",", ".")
    try:
        return Decimal(t) if t else None
    except InvalidOperation:
        return None


def _fmt(v: Decimal | None) -> str:
    return "" if v is None else f"{v:.2f}"


def iso(d: Any) -> str:
    if isinstance(d, datetime):
        return d.date().isoformat()
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", str(d or ""))
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def competencia_do_cabecalho(rows: list[tuple[Any, ...]]) -> str:
    for r in rows[:4]:
        for c in r:
            if c and (m := RE_COMPETENCIA.search(str(c))):
                mes = MESES_PREFIXO.get(_fold(m.group(1))[:3])
                if mes:
                    return f"{m.group(2)}-{mes:02d}"
    return ""


def split_cargo(cargo: str) -> tuple[str, str, str]:
    """``ASSESSOR PARLAMENTAR-G-13 CC10`` -> (``ASSESSOR PARLAMENTAR``, ``G-13``, ``CC10``)."""
    c = re.sub(r"\s+", " ", cargo or "").strip()
    if m := RE_GRAU.match(c):
        return (
            m.group(1).strip(" -"),
            f"G-{int(m.group(2)):02d}",
            re.sub(r"[\s-]", "", m.group(3) or "").upper(),
        )
    if m := RE_SIMBOLO.match(c):
        return m.group(1).strip(" -"), "", re.sub(r"[\s-]", "", m.group(2)).upper()
    return c, "", ""


def read_rows(path: Path) -> list[tuple[Any, ...]]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    return [tuple(r) for r in ws.iter_rows(values_only=True)]


def parse_rows(rows: list[tuple[Any, ...]], arquivo: str, competencia: str = "") -> list[dict[str, str]]:
    hdr_i = next((i for i, r in enumerate(rows) if r and str(r[0]).strip() == "Nome"), None)
    if hdr_i is None:
        raise LayoutError(f"{arquivo}: linha de títulos 'Nome | Matrícula | ...' não encontrada")
    titulos = tuple(str(c).strip() for c in rows[hdr_i][: len(HEADER)])
    if titulos != HEADER:
        raise LayoutError(f"{arquivo}: títulos inesperados {titulos}")
    comp = competencia or competencia_do_cabecalho(rows)
    if not comp:
        raise LayoutError(f"{arquivo}: competência não encontrada no cabeçalho")
    out: list[dict[str, str]] = []
    for r in rows[hdr_i + 1 :]:
        if not r or r[1] is None or not re.fullmatch(r"\d+", str(r[1]).strip()):
            continue  # rodapé "Receita Corrente Líquida ..." e linhas vazias
        funcao, grau, simbolo = split_cargo(str(r[3] or ""))
        base, vant, grat, dec = (brl(r[5]), brl(r[6]), brl(r[7]), brl(r[8]))
        bruta = sum((v for v in (base, vant, grat, dec) if v is not None), Decimal(0))
        out.append(
            {
                "competencia": comp,
                "matricula": str(r[1]).strip().lstrip("0") or "0",
                "servidor": re.sub(r"\s+", " ", str(r[0] or "")).strip(),
                "regime": re.sub(r"\s+", " ", str(r[2] or "")).strip(),
                "cargo": re.sub(r"\s+", " ", str(r[3] or "")).strip(),
                "funcao": funcao,
                "grau": grau,
                "simbolo": simbolo,
                "salario_liquido": _fmt(brl(r[4])),
                "salario_base": _fmt(base),
                "vantagens": _fmt(vant),
                "gratificacao": _fmt(grat),
                "decimo_terceiro": _fmt(dec),
                "remuneracao_bruta": _fmt(bruta),
                "carga_horaria": str(r[9] or "").strip(),
                "situacao": re.sub(r"\s+", " ", str(r[10] or "")).strip(),
                "admissao": iso(r[11]),
                "arquivo": arquivo,
            }
        )
    if not out:
        raise LayoutError(f"{arquivo}: nenhuma linha de servidor")
    return out


def parse_file(path: Path) -> list[dict[str, str]]:
    return parse_rows(read_rows(path), path.name)


# ---- ingestão manual ---------------------------------------------------------------------------------------


def ingest(origens: list[Path], bronze: Path = BRONZE_TCM) -> list[Path]:
    """Copia planilhas baixadas à mão para ``bronze/<AAAA-MM>/pessoal_749_<AAAA-MM>.xlsx`` e anota o manifest."""
    out: list[Path] = []
    for src in origens:
        rows = read_rows(src)
        comp = competencia_do_cabecalho(rows)
        if not comp:
            log.error("%s: competência não encontrada; ignorado", src.name)
            continue
        dest_dir = bronze / comp
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"pessoal_{UNIDADE}_{comp}.xlsx"
        sha = hashlib.sha256(src.read_bytes()).hexdigest()
        if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest() == sha:
            log.info("%s: já existe como %s", src.name, dest.name)
            out.append(dest)
            continue
        if dest.exists():
            # Nova exportação do mesmo mês (ex.: SIGA completou a carga): substitui; o manifest guarda o histórico.
            log.info("%s: substitui a exportação anterior de %s", src.name, comp)
        shutil.copy2(src, dest)
        with (dest_dir / "manifest.jsonl").open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "arquivo": dest.name,
                        "origem": src.name,
                        "competencia": comp,
                        "unidade": UNIDADE,
                        "fonte": "https://www.tcm.ba.gov.br/controle-social/pessoal/ (exportação manual, reCAPTCHA)",
                        "sha256": sha,
                        "bytes": dest.stat().st_size,
                        "ingerido_em": datetime.now(UTC).isoformat(timespec="seconds"),
                        "n_linhas": len(rows),
                        "substituiu_anterior": dest.exists(),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        log.info("%s -> %s (%d linhas)", src.name, dest, len(rows))
        out.append(dest)
    return out


def parse_dir(bronze: Path = BRONZE_TCM) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(bronze.rglob("*.xlsx")):
        try:
            r = parse_file(path)
        except LayoutError as e:
            log.error("%s", e)
            continue
        rows += r
        log.info("%s: %d servidores (%s)", path.name, len(r), r[0]["competencia"])
    rows.sort(key=lambda r: (r["competencia"], r["servidor"], r["matricula"]))
    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="TCM-BA pessoal (XLSX exportado à mão) -> silver/tcm_pessoal.csv"
    )
    ap.add_argument("--bronze", type=Path, default=BRONZE_TCM)
    ap.add_argument(
        "--ingest",
        type=Path,
        nargs="*",
        help="planilhas baixadas (ex.: ~/Downloads/*.xlsx) para copiar ao bronze",
    )
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if args.ingest:
        ingest([p for p in args.ingest if p.suffix.lower() == ".xlsx"], args.bronze)
    rows = parse_dir(args.bronze)
    if not rows:
        log.error("nenhuma planilha em %s", args.bronze)
        return 1
    write_csv(OUT, rows)
    log.info("%d linhas -> %s", len(rows), OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
