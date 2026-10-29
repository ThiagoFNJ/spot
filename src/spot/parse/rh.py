"""Parser dos PDFs mensais de RH da CMS (bronze/rh -> silver/folha.csv e silver/estagiarios.csv).

Layout "SIGP" (JasperReports/iText, todos os meses de 2025, servidores e estagiários): cada página
repete o cabeçalho institucional, a linha `Filtros : Mês : X, Ano : Y` e a linha de colunas
`Matrícula Servidor Regime Função Exercicida Admissão Centro de Custo Total de Proventos`.
Células longas (nome, função, centro de custo) quebram em linhas de continuação sem matrícula.
A última página termina com `Total de Registros : N`.

Estratégia: pdfplumber `extract_words` e atribuição de cada palavra a uma coluna pela posição x,
usando os x0 da linha de colunas da própria página como fronteiras. Uma linha com número na coluna
Matrícula abre um registro; linhas sem matrícula são continuação do registro anterior.
Validação de schema por registro e contagem contra `Total de Registros`; qualquer desvio levanta
`LayoutError` (falha alta, sem silêncio).

Sem rede. Entrada: data/bronze/rh/{servidores,estagiarios}_{YYYY-MM}.pdf.
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pdfplumber

from spot.config import BRONZE, SILVER

log = logging.getLogger(__name__)

BRONZE_RH = BRONZE / "rh"

COLUMNS = ("matricula", "servidor", "regime", "funcao", "admissao", "centro_custo", "proventos")
HEADER_WORDS = ("Matrícula", "Servidor", "Regime", "Função", "Admissão", "Centro", "Total")

SILVER_COLUMNS = [
    "competencia",
    "matricula",
    "servidor",
    "regime",
    "funcao_codigo",
    "funcao",
    "simbolo",
    "grau",
    "admissao",
    "centro_custo_codigo",
    "centro_custo_label",
    "gabinete_vereador",
    "suplente_vereador",
    "proventos",
    "bronze_file",
]

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

RE_FILE = re.compile(r"^(servidores|estagiarios)_(\d{4}-\d{2})\.pdf$")
RE_FILTROS = re.compile(r"Filtros\s*:\s*Mês\s*:\s*([^,]+?),\s*Ano\s*:\s*(\d{4})")
RE_TOTAL = re.compile(r"Total de Registros\s*:\s*(\d+)")
RE_CODE_LABEL = re.compile(r"^(\d+)\s*-\s*(.+)$", re.DOTALL)
RE_DATE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
RE_MONEY = re.compile(r"^-?(?:\d{1,3}(?:\.\d{3})*|\d+),\d{2}$")
RE_SIMBOLO = re.compile(r"\b([A-Z]{2,3})-?(\d{2})\s*$")
RE_GRAU = re.compile(r"\b(G-\d{2})\b")
RE_GAB = re.compile(r"GAB\.?\s*VER\.?\s*(.+)$")
# "(SUP. X)", "(SUP. VER. X)" e "(SUPLENTE X)" — o rótulo de ORLANDO PALHINHA usa a forma por extenso.
RE_SUP = re.compile(r"\(\s*SUP(?:LENTE|\.)?\s*(?:VER\.?\s*)?(.+?)\s*\)")
RE_TRAIL_CODE = re.compile(r"\s*-\s*[\d.]+\s*$")


class LayoutError(RuntimeError):
    """O PDF não segue o layout esperado (drift) ou falhou a validação de schema."""


@dataclass
class Record:
    page: int
    cells: dict[str, list[str]]

    def text(self, col: str) -> str:
        return " ".join(" ".join(self.cells[col]).split())


# ---- extração posicional ---------------------------------------------------------------------


def _group_lines(words: list[dict[str, Any]], tol: float = 3.0) -> list[list[dict[str, Any]]]:
    """Agrupa palavras em linhas pela coordenada `top` (tolerância em pt), ordenadas por x0."""
    lines: list[list[dict[str, Any]]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(w["top"] - lines[-1][0]["top"]) <= tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(l, key=lambda w: w["x0"]) for l in lines]


def _column_bounds(header: list[dict[str, Any]]) -> list[float]:
    """x0 de cada título da linha de colunas -> fronteiras esquerdas das 7 colunas."""
    starts: list[float] = []
    for name in HEADER_WORDS:
        hit = [w for w in header if w["text"] == name]
        if not hit:
            raise LayoutError(f"linha de colunas sem {name!r}: {' '.join(w['text'] for w in header)!r}")
        starts.append(hit[0]["x0"])
    if starts != sorted(starts):
        raise LayoutError(f"linha de colunas fora de ordem: {starts}")
    return [s - 2.0 for s in starts]


def _column_of(x0: float, bounds: list[float]) -> str:
    idx = 0
    for i, b in enumerate(bounds):
        if x0 >= b:
            idx = i
    return COLUMNS[idx]


def extract_records(pdf_path: Path) -> tuple[list[Record], str | None, int | None]:
    """Devolve (registros, competência declarada nos filtros como YYYY-MM, Total de Registros)."""
    records: list[Record] = []
    competencia: str | None = None
    total: int | None = None
    current: Record | None = None  # persiste entre páginas: um registro pode quebrar no fim da página
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(x_tolerance=1.5, y_tolerance=2)
            lines = _group_lines(words)
            header_idx = next(
                (
                    i
                    for i, l in enumerate(lines)
                    if {"Matrícula", "Servidor", "Proventos"} <= {w["text"] for w in l}
                ),
                None,
            )
            if header_idx is None:
                raise LayoutError(f"{pdf_path.name} p.{pno}: linha de colunas não encontrada (layout novo?)")
            bounds = _column_bounds(lines[header_idx])
            for l in lines[:header_idx]:
                m = RE_FILTROS.search(" ".join(w["text"] for w in l))
                if m and competencia is None:
                    competencia = _competencia(m.group(1), m.group(2))
            for l in lines[header_idx + 1 :]:
                text = " ".join(w["text"] for w in l)
                m = RE_TOTAL.search(text)
                if m:
                    total = int(m.group(1))
                    break
                if text.startswith("Sistema Integrado de Gestão de Pessoas"):
                    continue
                first = l[0]
                is_new = _column_of(first["x0"], bounds) == "matricula" and first["text"].isdigit()
                if is_new:
                    current = Record(pno, {c: [] for c in COLUMNS})
                    records.append(current)
                elif current is None:
                    raise LayoutError(f"{pdf_path.name} p.{pno}: continuação sem registro: {text!r}")
                elif _column_of(first["x0"], bounds) == "matricula":
                    raise LayoutError(f"{pdf_path.name} p.{pno}: matrícula não numérica: {text!r}")
                for w in l:
                    current.cells[_column_of(w["x0"], bounds)].append(w["text"])
    return records, competencia, total


def _competencia(mes: str, ano: str) -> str:
    mes = mes.strip().lower()
    n = int(mes) if mes.isdigit() else MESES.get(mes)
    if not n or not 1 <= n <= 12:
        raise LayoutError(f"mês desconhecido nos filtros: {mes!r}")
    return f"{ano}-{n:02d}"


# ---- transformação e validação ---------------------------------------------------------------


def money_to_decimal(s: str) -> Decimal:
    if not RE_MONEY.match(s):
        raise ValueError(f"valor monetário inválido: {s!r}")
    try:
        return Decimal(s.replace(".", "").replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError(f"valor monetário inválido: {s!r}") from exc


def date_to_iso(s: str) -> str:
    m = RE_DATE.match(s)
    if not m:
        raise ValueError(f"data inválida: {s!r}")
    d, mo, y = (int(g) for g in m.groups())
    if not (1 <= mo <= 12 and 1 <= d <= 31 and 1900 <= y <= 2100):
        raise ValueError(f"data inválida: {s!r}")
    return f"{y:04d}-{mo:02d}-{d:02d}"


def split_code(s: str) -> tuple[int, str]:
    m = RE_CODE_LABEL.match(s)
    if not m:
        raise ValueError(f"esperado '<código> - <rótulo>': {s!r}")
    return int(m.group(1)), " ".join(m.group(2).split())


def gabinete_from_label(label: str) -> tuple[str, str]:
    """(vereador titular, suplente) a partir do rótulo do centro de custo; vazios se não é gabinete."""
    m = RE_GAB.search(label)
    if not m:
        return "", ""
    rest = m.group(1)
    sup = RE_SUP.search(rest)
    suplente = " ".join(sup.group(1).split()) if sup else ""
    titular = RE_SUP.sub("", rest)
    titular = RE_TRAIL_CODE.sub("", titular).strip(" -")
    return " ".join(titular.split()), suplente


def to_row(rec: Record, competencia: str, bronze_file: str) -> dict[str, str]:
    try:
        matricula = rec.text("matricula")
        if not matricula.isdigit():
            raise ValueError(f"matrícula não numérica: {matricula!r}")
        servidor = rec.text("servidor")
        if not servidor:
            raise ValueError("servidor vazio")
        regime_codigo, regime_label = split_code(rec.text("regime"))
        funcao_codigo, funcao = split_code(rec.text("funcao"))
        admissao = date_to_iso(rec.text("admissao"))
        cc_codigo, cc_label = split_code(rec.text("centro_custo"))
        proventos = money_to_decimal(rec.text("proventos"))
    except ValueError as exc:
        raise LayoutError(
            f"{bronze_file} p.{rec.page}: {exc}; células={ {c: rec.text(c) for c in COLUMNS} }"
        ) from exc
    simbolo = RE_SIMBOLO.search(funcao)
    grau = RE_GRAU.search(funcao)
    titular, suplente = gabinete_from_label(cc_label)
    return {
        "competencia": competencia,
        "matricula": matricula,
        "servidor": servidor,
        "regime": f"{regime_codigo} - {regime_label}",
        "funcao_codigo": str(funcao_codigo),
        "funcao": funcao,
        "simbolo": simbolo.group(1) + simbolo.group(2) if simbolo else "",
        "grau": grau.group(1) if grau else "",
        "admissao": admissao,
        "centro_custo_codigo": str(cc_codigo),
        "centro_custo_label": cc_label,
        "gabinete_vereador": titular,
        "suplente_vereador": suplente,
        "proventos": f"{proventos:.2f}",
        "bronze_file": bronze_file,
    }


def parse_pdf(pdf_path: Path, competencia: str | None = None) -> list[dict[str, str]]:
    """Parseia um PDF mensal. `competencia` (YYYY-MM) vem do nome do arquivo quando não informada."""
    name = pdf_path.name
    if competencia is None:
        m = RE_FILE.match(name)
        if not m:
            raise ValueError(f"nome fora do padrão {{tipo}}_{{YYYY-MM}}.pdf: {name}")
        competencia = m.group(2)
    records, comp_pdf, total = extract_records(pdf_path)
    if comp_pdf is None:
        raise LayoutError(f"{name}: linha 'Filtros : Mês : ..., Ano : ...' não encontrada")
    if comp_pdf != competencia:
        log.warning(
            "%s: competência do nome (%s) difere dos filtros do PDF (%s); mantendo a do nome",
            name,
            competencia,
            comp_pdf,
        )
    if total is None:
        raise LayoutError(f"{name}: 'Total de Registros' não encontrado")
    if len(records) != total:
        raise LayoutError(f"{name}: {len(records)} registros extraídos, PDF declara {total}")
    rows = [to_row(r, competencia, name) for r in records]
    log.info(
        "%s: %d registros, %d matrículas, soma proventos %s",
        name,
        len(rows),
        len({r["matricula"] for r in rows}),
        sum(Decimal(r["proventos"]) for r in rows),
    )
    return rows


# ---- silver --------------------------------------------------------------------------------------


def sort_key(r: dict[str, str]) -> tuple:
    return (
        r["competencia"],
        int(r["matricula"]),
        int(r["centro_custo_codigo"]),
        int(r["funcao_codigo"]),
        r["servidor"],
    )


def write_silver(rows: list[dict[str, str]], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=sort_key)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SILVER_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    log.info("%s: %d linhas", out, len(rows))


def parse_all(
    bronze_dir: Path = BRONZE_RH,
    silver_dir: Path = SILVER,
    tipos: tuple[str, ...] = ("servidores", "estagiarios"),
) -> dict[str, int]:
    outputs = {"servidores": silver_dir / "folha.csv", "estagiarios": silver_dir / "estagiarios.csv"}
    counts: dict[str, int] = {}
    for tipo in tipos:
        files = sorted(bronze_dir.glob(f"{tipo}_????-??.pdf"))
        if not files:
            log.warning("nenhum PDF %s_* em %s", tipo, bronze_dir)
        rows: list[dict[str, str]] = []
        for f in files:
            rows.extend(parse_pdf(f))
        write_silver(rows, outputs[tipo])
        counts[tipo] = len(rows)
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="bronze/rh -> silver/folha.csv + silver/estagiarios.csv")
    ap.add_argument("--bronze", type=Path, default=BRONZE_RH)
    ap.add_argument("--silver", type=Path, default=SILVER)
    ap.add_argument(
        "--tipos", nargs="+", choices=["servidores", "estagiarios"], default=["servidores", "estagiarios"]
    )
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("pdfminer").setLevel(logging.WARNING)
    parse_all(args.bronze, args.silver, tuple(args.tipos))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
