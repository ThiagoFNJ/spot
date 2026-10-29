"""Folhas de pagamento sintéticas da CMS publicadas no e-TCM (bronze/etcm -> silver/folha_sintetica*.csv).

Toda prestação mensal da Câmara ao TCM-BA traz, nas classes ``PCMGE035`` (folha de pagamento) e ``PCMGE048``
(subsídios dos vereadores), um processo de pagamento por folha: ``PP <n> Fl. Pagamento - Cargo em Comissão -
Fl. Sintética.pdf`` etc. Dentro, a página **"Resumo - Geral"** do sistema de RH: cabeçalho (Mês, Ano, Tipo da
Folha, Nº da Folha, Grupo de regime) e uma tabela com uma linha por rubrica — ``código - descrição | Qtd. Serv. |
REMUNERAÇÃO | DESCONTOS`` — fechada por ``Total da Remuneração``, ``Total de Descontos``, ``Total Geral de
Servidores`` e ``Liquido``. É a única fonte pública da folha da Câmara em 2026 (a página de RH do site parou em
dez/2025); é agregada por grupo de regime, sem servidor nem gabinete.

Colunas pela posição x das palavras (a página é digital, OCR limpo): descrição à esquerda, quantidade no
meio, valor em REMUNERAÇÃO (x < 450) ou DESCONTOS (x >= 450). Carimbos laterais (x < 30 e x > 550) ignorados.

Saídas:
- ``folha_sintetica.csv``: uma linha por rubrica (``natureza`` = remuneracao | desconto).
- ``folha_sintetica_resumo.csv``: uma linha por folha (totais declarados, somas lidas, ``confianca``).
Sem rede. Nada de CPF/conta é gravado (a tabela não tem pessoas).
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import pdfplumber

from spot.config import BRONZE, SILVER
from spot.parse.etcm_vc import MESES_PREFIXO, _fold, normalizar_valor, parse_valor

log = logging.getLogger(__name__)

BRONZE_ETCM = BRONZE / "etcm"
OUT_RUBRICAS = SILVER / "folha_sintetica.csv"
OUT_RESUMO = SILVER / "folha_sintetica_resumo.csv"
CLASSES = ("PCMGE035", "PCMGE048")
RE_NOME_FOLHA = re.compile(r"(?i)sint[eé]tica|folha de pgto|fl\.? ?(?:de )?pagamento|pessoal civil")

RUBRICA_COLUMNS = [
    "mes_prestacao",
    "pp_numero",
    "arquivo",
    "folha_id",
    "competencia",
    "tipo_folha",
    "numero_folha",
    "grupo_regime",
    "rubrica_codigo",
    "rubrica",
    "qtd",
    "valor",
    "natureza",
]
RESUMO_COLUMNS = [
    "mes_prestacao",
    "pp_numero",
    "arquivo",
    "folha_id",
    "competencia",
    "tipo_folha",
    "numero_folha",
    "grupo_regime",
    "total_servidores",
    "total_remuneracao",
    "total_descontos",
    "liquido",
    "soma_remuneracao",
    "soma_descontos",
    "n_rubricas",
    "confianca",
]

# Fronteiras de coluna (página de 587 pt; o layout é fixo, só o OCR varia).
X_MARGEM_ESQ, X_DESCRICAO_MAX, X_QTD_MAX, X_DESCONTO_MIN, X_MARGEM_DIR = 30.0, 228.0, 300.0, 450.0, 552.0
RE_NUM = re.compile(r"^\d{1,4}$")
RE_CODIGO = re.compile(r"^(\d{1,5})-?$")


class LayoutError(ValueError):
    """PDF sem página 'Resumo - Geral' reconhecível."""


@dataclass
class Rubrica:
    codigo: str
    descricao: str
    qtd: int | None
    valor: Decimal
    natureza: str  # remuneracao | desconto


@dataclass
class Folha:
    folha_id: str = ""
    competencia: str = ""
    tipo_folha: str = ""
    numero_folha: str = ""
    grupo_regime: str = ""
    rubricas: list[Rubrica] = field(default_factory=list)
    total_servidores: int | None = None
    total_remuneracao: Decimal | None = None
    total_descontos: Decimal | None = None
    liquido: Decimal | None = None

    @property
    def soma(self) -> tuple[Decimal, Decimal]:
        rem = sum((r.valor for r in self.rubricas if r.natureza == "remuneracao"), Decimal(0))
        des = sum((r.valor for r in self.rubricas if r.natureza == "desconto"), Decimal(0))
        return rem, des

    @property
    def confianca(self) -> str:
        rem, des = self.soma
        fecha = self.total_remuneracao is not None and rem == self.total_remuneracao
        fecha_d = self.total_descontos is None or des == self.total_descontos
        if fecha and fecha_d and self.competencia and self.grupo_regime:
            return "alta"
        if fecha and self.competencia:
            return "media"
        return "baixa"


# ---- utilidades --------------------------------------------------------------------------------------------


def _lines(words: list[dict[str, Any]], tol: float = 3.0) -> list[list[dict[str, Any]]]:
    """Agrupa palavras por linha (top) e ordena por x; descarta carimbos laterais."""
    body = [w for w in words if X_MARGEM_ESQ <= w["x0"] < X_MARGEM_DIR]
    body.sort(key=lambda w: (w["top"], w["x0"]))
    out: list[list[dict[str, Any]]] = []
    for w in body:
        if out and abs(w["top"] - out[-1][0]["top"]) <= tol:
            out[-1].append(w)
        else:
            out.append([w])
    return [sorted(ln, key=lambda w: w["x0"]) for ln in out]


def _texto(ws: list[dict[str, Any]]) -> str:
    return " ".join(w["text"] for w in ws)


def _valor(tok: str) -> Decimal | None:
    s = normalizar_valor(tok)
    if not re.search(r"\d", s):
        return None
    return parse_valor(s)


def _qtd(tok: str) -> int | None:
    t = tok.replace(".", "")
    return int(t) if RE_NUM.match(t) else None


def _competencia(mes: str, ano: str) -> str:
    m = MESES_PREFIXO.get(_fold(mes)[:3])
    return f"{ano}-{m:02d}" if m and re.fullmatch(r"\d{4}", ano) else ""


# Rótulos canônicos (o OCR alterna acentos: "Cargo Em Comissao"/"CARGO EM COMISSÃO", "Estagiario").
REGIMES = [
    ("comiss", "Cargo em comissão"),
    ("estatut", "Estatutário"),
    ("agente", "Agente político"),
    ("estagi", "Estagiário"),
    ("militar", "Assistência militar"),
    ("celet", "Celetista"),
    ("tempor", "Temporário"),
]
TIPOS_FOLHA = [
    ("normal", "Normal"),
    ("complement", "Complementar"),
    ("f", "Férias"),
    ("resc", "Rescisão"),
    ("adiant", "Adiantamento 13º"),
    ("13", "13º salário"),
]


def grupo_regime_canonico(raw: str) -> str:
    f = _fold(raw)
    for chave, rotulo in REGIMES:
        if chave in f:
            return rotulo
    return re.sub(r"\s+", " ", raw).strip().title()


def tipo_folha_canonico(raw: str) -> str:
    f = _fold(raw).strip(".:")
    for chave, rotulo in TIPOS_FOLHA:
        if f.startswith(chave):
            return rotulo
    return raw


# ---- página ------------------------------------------------------------------------------------------------


def is_resumo_page(words: list[dict[str, Any]]) -> bool:
    txt = _texto(sorted(words, key=lambda w: (w["top"], w["x0"])))
    return "Resumo" in txt and "Geral" in txt and "Grupo" in txt and "regime" in txt


def _cabecalho(lines: list[list[dict[str, Any]]], folha: Folha) -> None:
    for ws in lines:
        t = _texto(ws)
        if m := re.search(r"FOLHA\s+n\.?\s*(\d+)", t):
            folha.folha_id = m.group(1)
        if m := re.search(r"M[êeé]s:\s*([A-Za-zçÇ]+)", t):
            folha.competencia = _competencia(m.group(1), folha.competencia or "")
            folha.__dict__["_mes"] = m.group(1)
        if m := re.search(r"Ano:\s*(\d{4})", t):
            folha.competencia = _competencia(folha.__dict__.get("_mes", ""), m.group(1))
        if re.search(r"Ti[a-z]*\s*da|Tidap", t) and (m := re.search(r"Fol?o?ha:\s*(\S+)", t)):
            folha.tipo_folha = tipo_folha_canonico(m.group(1))
        if m := re.search(r"da\s*Folha:\s*(\d+)", t):
            folha.numero_folha = m.group(1)
        if m := re.search(r"regime:\s*(.+)$", t):
            folha.grupo_regime = grupo_regime_canonico(m.group(1))


def _rubrica(ws: list[dict[str, Any]]) -> Rubrica | None:
    desc = [w for w in ws if w["x0"] < X_DESCRICAO_MAX]
    qtd_ws = [w for w in ws if X_DESCRICAO_MAX <= w["x0"] < X_QTD_MAX]
    rem_ws = [w for w in ws if X_QTD_MAX <= w["x0"] < X_DESCONTO_MIN]
    des_ws = [w for w in ws if w["x0"] >= X_DESCONTO_MIN]
    if not desc or not (rem_ws or des_ws):
        return None
    valor_ws, natureza = (rem_ws, "remuneracao") if rem_ws else (des_ws, "desconto")
    valor = _valor("".join(w["text"] for w in valor_ws))
    if valor is None:
        return None
    toks = [w["text"] for w in desc]
    codigo = ""
    if toks and (m := RE_CODIGO.match(toks[0])):
        codigo = m.group(1)
        toks = toks[1:]
        if toks and toks[0] == "-":
            toks = toks[1:]
    elif toks and RE_CODIGO.match(toks[0].rstrip("-")) and toks[0].endswith("-"):
        codigo = toks[0].rstrip("-")
        toks = toks[1:]
    descricao = re.sub(r"\s+", " ", " ".join(toks)).strip(" -")
    if not descricao:
        return None
    qtd = _qtd("".join(w["text"] for w in qtd_ws)) if qtd_ws else None
    return Rubrica(codigo, descricao, qtd, valor, natureza)


def parse_pagina(words: list[dict[str, Any]], folha: Folha | None = None) -> tuple[Folha, bool]:
    """Uma página 'Resumo - Geral' -> Folha (ou continua ``folha``). Devolve (folha, fechou com totais)."""
    folha = folha or Folha()
    lines = _lines(words)
    _cabecalho(lines, folha)
    em_tabela = False
    fechou = False
    for ws in lines:
        t = _texto(ws)
        if re.search(r"DESCRI[ÇC][ÃA]O", t) and re.search(r"Qtd", t):
            em_tabela = True
            continue
        if not em_tabela:
            continue
        if re.search(r"Total\s+da\s+Remunera", t):
            rem = [w for w in ws if X_QTD_MAX <= w["x0"] < X_DESCONTO_MIN and re.search(r"\d", w["text"])]
            des = [w for w in ws if w["x0"] >= X_DESCONTO_MIN and re.search(r"\d", w["text"])]
            folha.total_remuneracao = _valor("".join(w["text"] for w in rem)) if rem else None
            folha.total_descontos = _valor("".join(w["text"] for w in des)) if des else None
            continue
        if re.search(r"Total\s+Geral\s+de\s+Servidores", t):
            nums = [w for w in ws if X_QTD_MAX <= w["x0"] < X_DESCONTO_MIN and re.search(r"\d", w["text"])]
            liq = [w for w in ws if w["x0"] >= X_DESCONTO_MIN and re.search(r"\d", w["text"])]
            folha.total_servidores = _qtd("".join(w["text"] for w in nums)) if nums else None
            folha.liquido = _valor("".join(w["text"] for w in liq)) if liq else None
            fechou = True
            break
        if t.startswith("Total:"):
            fechou = True
            break
        if r := _rubrica(ws):
            folha.rubricas.append(r)
    return folha, fechou


# ---- PDF ---------------------------------------------------------------------------------------------------


def grupo_por_contexto(folha: Folha, arquivo: str) -> str:
    """Algumas folhas trazem "Grupo de regime: (Todos)": o grupo vem do nome do processo ou das rubricas."""
    if folha.grupo_regime and folha.grupo_regime.lower() not in ("(todos)", "todos"):
        return folha.grupo_regime
    nome = _fold(Path(arquivo).stem)
    for chave, rotulo in REGIMES:
        if chave in nome or (chave == "agente" and "agentes" in nome):
            return rotulo
    rubs = " ".join(_fold(r.descricao) for r in folha.rubricas)
    if "subsidio" in rubs:
        return "Agente político"
    if "estagio" in rubs:
        return "Estagiário"
    return folha.grupo_regime


def parse_pdf(path: Path) -> list[Folha]:
    folhas: list[Folha] = []
    aberta: Folha | None = None
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=2, y_tolerance=3)
            if not is_resumo_page(words):
                continue
            folha, fechou = parse_pagina(words, aberta)
            if fechou:
                folhas.append(folha)
                aberta = None
            else:
                aberta = folha
    if aberta is not None and aberta.rubricas:
        folhas.append(aberta)
    if not folhas:
        raise LayoutError(f"{path.name}: nenhuma página 'Resumo - Geral'")
    for f in folhas:
        f.grupo_regime = grupo_por_contexto(f, path.name)
    return folhas


def pp_numero(arquivo: str) -> str:
    m = re.search(r"\bPP\s*(\d+)", arquivo, re.I)
    return m.group(1) if m else ""


def arquivos_de_folha(mes_dir: Path) -> list[Path]:
    """PDFs das classes de folha segundo o manifest (ou pelo nome, se o manifest não os tiver)."""
    manifest = mes_dir / "manifest.jsonl"
    nomes: set[str] = set()
    if manifest.exists():
        for line in manifest.read_text("utf-8").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if any(str(e.get("classificacao", "")).startswith(c) for c in CLASSES):
                nomes.add(e["arquivo"])
    out = [
        p for p in mes_dir.glob("*.pdf") if p.name in nomes or (not nomes and RE_NOME_FOLHA.search(p.name))
    ]
    return sorted(p for p in out if " VC " not in f" {p.stem} " and "- VC" not in p.stem)


def rows_de(
    folhas: list[Folha], mes_prestacao: str, arquivo: str
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    pp = pp_numero(arquivo)
    rubs: list[dict[str, str]] = []
    res: list[dict[str, str]] = []
    for f in folhas:
        if not f.competencia:  # "Mês:" ilegível no OCR: a prestação mensal é do próprio mês da folha
            f.competencia = mes_prestacao
            log.warning("%s: competência não lida; assumido o mês da prestação (%s)", arquivo, mes_prestacao)
        base = {
            "mes_prestacao": mes_prestacao,
            "pp_numero": pp,
            "arquivo": arquivo,
            "folha_id": f.folha_id,
            "competencia": f.competencia,
            "tipo_folha": f.tipo_folha,
            "numero_folha": f.numero_folha,
            "grupo_regime": f.grupo_regime,
        }
        for r in f.rubricas:
            rubs.append(
                base
                | {
                    "rubrica_codigo": r.codigo,
                    "rubrica": r.descricao,
                    "qtd": "" if r.qtd is None else str(r.qtd),
                    "valor": f"{r.valor:.2f}",
                    "natureza": r.natureza,
                }
            )
        rem, des = f.soma
        res.append(
            base
            | {
                "total_servidores": "" if f.total_servidores is None else str(f.total_servidores),
                "total_remuneracao": "" if f.total_remuneracao is None else f"{f.total_remuneracao:.2f}",
                "total_descontos": "" if f.total_descontos is None else f"{f.total_descontos:.2f}",
                "liquido": "" if f.liquido is None else f"{f.liquido:.2f}",
                "soma_remuneracao": f"{rem:.2f}",
                "soma_descontos": f"{des:.2f}",
                "n_rubricas": str(len(f.rubricas)),
                "confianca": f.confianca,
            }
        )
    return rubs, res


def parse_dir(bronze: Path = BRONZE_ETCM) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    rubs: list[dict[str, str]] = []
    res: list[dict[str, str]] = []
    for mes_dir in sorted(p for p in bronze.iterdir() if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}", p.name)):
        for pdf in arquivos_de_folha(mes_dir):
            try:
                folhas = parse_pdf(pdf)
            except LayoutError as e:
                log.error("%s", e)
                continue
            r, s = rows_de(folhas, mes_dir.name, pdf.name)
            rubs += r
            res += s
            for f in folhas:
                if f.confianca != "alta":
                    log.warning(
                        "%s: folha %s %s %s: soma %s/%s vs total %s/%s (confianca=%s)",
                        pdf.name, f.folha_id, f.competencia, f.grupo_regime, *f.soma,
                        f.total_remuneracao, f.total_descontos, f.confianca,
                    )  # fmt: skip
            log.info(
                "%s: %d folha(s) %s",
                pdf.name,
                len(folhas),
                [(f.competencia, f.grupo_regime, f.tipo_folha) for f in folhas],
            )
    return rubs, res


def write_csv(path: Path, rows: list[dict[str, str]], cols: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="folhas sintéticas do e-TCM (PCMGE035/048) -> silver/folha_sintetica*.csv"
    )
    ap.add_argument("--bronze", type=Path, default=BRONZE_ETCM)
    ap.add_argument("--out-dir", type=Path, default=SILVER)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    rubs, res = parse_dir(args.bronze)
    if not res:
        log.error("nenhuma folha sintética em %s", args.bronze)
        return 1
    write_csv(args.out_dir / OUT_RUBRICAS.name, rubs, RUBRICA_COLUMNS)
    write_csv(args.out_dir / OUT_RESUMO.name, res, RESUMO_COLUMNS)
    log.info("%d rubrica(s), %d folha(s) -> %s", len(rubs), len(res), args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
