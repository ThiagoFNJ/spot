"""Bronze → silver dos empenhos (``gridRegistroEmpenho``). Sem rede.

Lê o snapshot mais recente ``data/bronze/empenhos/empenhos_{YYYY-MM-DD}_p{NNN}.html`` (página 1 = HTML
completo do ``muda_qt_linhas``; páginas 2+ = fragmentos ``setValue`` do ``ajax_navigate rec``; ambos UTF-8) e
grava ``data/silver/empenho.csv`` com uma linha por empenho (deduplicado por ``numero`` entre páginas: a grade é
viva e um empenho inserido durante a coleta desloca as páginas).

Cada registro da grade é um ``<TR class="scGridFieldOdd|Even" id="SC_ancorN">`` com os campos em
``<span id="id_sc_field_<campo>_N">Rótulo: valor</span>``. Campos usados: numero_empenho, modalidade_empenho,
tipo_empenho, data_emissao_empenho, valor_empenho, cnpjcpf, credor, objeto (as classificações
institucional/funcional/econômica vêm vazias na grade pública).

Colunas derivadas:
- ``categoria`` ∈ {verba_compensatoria, diaria, outro} por regex no objeto (``RE_VERBA`` cobre "VERBA
  COMPENSATÓRIA DE ATIVIDADE PARLAMENTAR", "VERBA DE ATIVIDADE PARLAMENTAR" e "VERBA PARLAMENTAR"; não casa
  "VERBAS TRABALHISTAS/RESCISÓRIAS"). ``RE_DIARIA`` = diária de viagem com contexto ("DIÁRIAS PARA/P/",
  "CONCESSÃO/PAGAMENTO DE DIÁRIA(S)", "DIÁRIA(S) DE VIAGEM", "DIÁRIA(S) ... SERVIDOR/VEREADOR") e sem veto de
  ``RE_NAO_DIARIA`` (assinatura de jornal com "ENTREGA DIÁRIA", periódicos): as 60 assinaturas do A Tarde/Correio/
  Tribuna (~R$ 319 mil) ficam em ``outro``.
- ``competencia_ref`` (YYYY-MM): primeira ocorrência de ``RE_COMPETENCIA`` no objeto — "MÊS (DE|D|DO) <mês>
  [E <mês>] [/|DE] [<ano>]" (tolera "MÊS JANEIRO,", "MÊS D MAIO/2025", "MÊS DEJULHO/2026", "MESES DE MARÇO E
  ABRIL/2025", "MÊS DE MARÇO/", "NOVEMBRO DE 2025"). Sem ano → ano da data de emissão, ou o anterior se o mês
  citado for posterior ao da emissão. Com dois meses ("MARÇO E ABRIL"), ``competencia_ref`` é o ÚLTIMO e
  ``competencias`` lista todos (``2025-03|2025-04``). Só a primeira frase conta: "COM UTILIZAÇÃO DE SALDO
  REMANESCENTE DO MÊS DE X" é origem do saldo, não competência. Vazio quando o objeto não cita mês (lote de
  26/02/2025) — a métrica cai no mês da emissão.
- ``anulacao`` (bool): tipo "Anulação*" OU objeto começando por "ANULAÇÃO" (há anulação com tipo "Original").
  ``anula_numero``: empenho anulado, por "NOTA DE EMPENHO Nº n/ano" no objeto ou, na falta, o empenho mais
  recente do mesmo credor com o mesmo valor emitido até a data da anulação (heurística, registrada em
  ``anula_fonte``). A anulação herda ``categoria``/``competencia_ref`` do empenho anulado quando o próprio objeto
  não os traz, para que a métrica possa descontá-la.
- ``processo`` ("PROCESSO Nº 2267/2026" → ``2267/2026``) e ``auditoria`` ("AUDITORIA DA CONTROLADORIA Nº
  14.16.10.2026" → ``14.16.10.2026``; tolera grafias "AUDITRORIA", "AUIТORIA", "Nª").

CLI: ``uv run python -m spot.parse.empenhos [--bronze DIR] [--out FILE]``.
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from html import unescape
from pathlib import Path

from spot.config import BRONZE, SILVER
from spot.scriptcase import RE_TOTAL

log = logging.getLogger(__name__)

BRONZE_DIR = BRONZE / "empenhos"
SILVER_OUT = SILVER / "empenho.csv"

COLUMNS = [
    "numero",
    "tipo",
    "modalidade",
    "data",
    "ano",
    "valor",
    "cnpj_cpf",
    "credor_fonte",
    "credor",
    "objeto",
    "processo",
    "auditoria",
    "categoria",
    "anulacao",
    "anula_numero",
    "anula_fonte",
    "competencia_ref",
    "competencias",
    "bronze_file",
]

RE_PAGE = re.compile(r"^empenhos_(\d{4}-\d{2}-\d{2})_p(\d{3})\.html$")
# Sem re.I de propósito: o registro é <TR ...>...</TR> em maiúsculas e contém tabelas aninhadas <tr>...</tr>
# em minúsculas; com re.I o fechamento casaria o primeiro </tr> interno e sobraria só o número do empenho.
RE_TR = re.compile(r'<TR\s+class="scGridField(?:Odd|Even)"[^>]*\bid="SC_ancor(\d+)"(.*?)</TR>', re.S)
RE_FIELD = re.compile(r'<span id="id_sc_field_(\w+?)_\d+">(.*?)</span>\s*</TD>', re.S)
RE_TAG = re.compile(r"<[^>]+>")
RE_WS = re.compile(r"\s+")
RE_DATA = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
RE_NUMERO = re.compile(r"^(\d{4})([A-Za-z]{2})(\d+)$")

RE_VERBA = re.compile(
    r"VERBA\s+(?:COMPENSAT\w*\s+)?(?:DE\s+ATIVIDADE\s+)?PARLAMENTAR|VERBA\s+COMPENSAT", re.I
)
# Diária de viagem exige contexto: "DIÁRIAS PARA/P/ ...", "CONCESSÃO/PAGAMENTO DE DIÁRIA(S)", "DIÁRIA(S) DE VIAGEM",
# "DIÁRIA(S) AO SERVIDOR/VEREADOR" (até 60 caracteres entre a palavra e o beneficiário). ``RE_NAO_DIARIA`` veta
# assinaturas de jornal ("ENTREGA DIÁRIA DO JORNAL A TARDE"), periódicos e "DIÁRIO OFICIAL" nunca casa (DIÁRIO ≠ DIÁRIA).
RE_DIARIA = re.compile(
    r"\bDI[ÁA]RIAS?\s+(?:PARA\b|P/|P\.)"
    r"|\b(?:CONCESS[ÃA]O|PAGAMENTO)\s+DE\s+(?:\d+\s+)?DI[ÁA]RIAS?\b"
    r"|\bDI[ÁA]RIAS?\s+DE\s+VIAGEM\b"
    r"|\bDI[ÁA]RIAS?\b[^.;]{0,60}?\b(?:SERVIDOR|VEREADOR)",
    re.I,
)
RE_NAO_DIARIA = re.compile(
    r"ENTREGA\s+DI[ÁA]RIA\b|\bASSINATURAS?\b|\bJORNA(?:L|IS)\b|\bPERI[ÓO]DICOS?\b", re.I
)
RE_ANULACAO = re.compile(r"^\W*ANULA[ÇC][ÃA]O", re.I)
RE_NOTA_REF = re.compile(r"NOTA\s+DE\s+EMPENHO\s+N[º°ªo.]*\s*(\d+)\s*/\s*(\d{4})", re.I)
RE_PROCESSO = re.compile(r"PROCESSO\s+N[º°ªo.]*\s*(\d[\d.]*\s*/\s*\d{4})", re.I)
RE_AUDITORIA = re.compile(r"AU[DI]I?T[OR]*RIA[^\d]{0,40}?N[º°ªo.]*\s*(\d[\d.]*\d)", re.I)

MESES = {
    "JANEIRO": 1,
    "FEVEREIRO": 2,
    "MARCO": 3,
    "MARÇO": 3,
    "ABRIL": 4,
    "MAIO": 5,
    "JUNHO": 6,
    "JULHO": 7,
    "AGOSTO": 8,
    "SETEMBRO": 9,
    "OUTUBRO": 10,
    "NOVEMBRO": 11,
    "DEZEMBRO": 12,
}
_MES = "(" + "|".join(sorted(MESES, key=len, reverse=True)) + ")"
RE_COMPETENCIA = re.compile(
    r"M[ÊE]S(?:ES)?\s+(?:D[EO]?\s*)?" + _MES + r"(?:\s*(?:E|,)\s*" + _MES + r")?\s*(?:/|DE\s+)?\s*(\d{4})?",
    re.I,
)


def clean(s: str) -> str:
    return RE_WS.sub(" ", unescape(RE_TAG.sub(" ", s)).replace("\xa0", " ")).strip()


def iso_date(s: str) -> str:
    m = RE_DATA.match(s)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def parse_valor(s: str) -> Decimal | None:
    """``37.000,00`` / ``-1.234,56`` → Decimal. None se não for número."""
    t = s.replace("R$", "").replace(".", "").replace(",", ".").replace(" ", "")
    try:
        return Decimal(t) if t else None
    except InvalidOperation:
        return None


RE_CPF = re.compile(r"^\d{3}\.?\d{3}\.?\d{3}-?\d{2}$")


def cnpj_cpf(s: str) -> str:
    """CPF de pessoa física vem mascarado (``..-`` ou ``../-``): vira vazio; CNPJ fica como está.

    A fonte expõe o CPF completo de alguns credores pessoa física; por LGPD o silver guarda só
    ``***.***.***-**`` nesses casos (o dado nunca é necessário para a métrica).
    """
    s = s.strip()
    if not s.strip("-./ "):
        return ""
    if RE_CPF.match(s):
        return "***.***.***-**"
    return s


RE_CPF_EM_TEXTO = re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}")


def mascarar_cpf(texto: str) -> str:
    """Remove CPFs citados em texto livre (objeto do empenho)."""
    return RE_CPF_EM_TEXTO.sub("***.***.***-**", texto)


def categoria(objeto: str) -> str:
    if RE_VERBA.search(objeto):
        return "verba_compensatoria"
    if RE_DIARIA.search(objeto) and not RE_NAO_DIARIA.search(objeto):
        return "diaria"
    return "outro"


def competencias(objeto: str, data_iso: str) -> list[str]:
    """Meses (YYYY-MM) da PRIMEIRA frase "MÊS DE ..." do objeto; [] se não houver."""
    m = RE_COMPETENCIA.search(objeto)
    if not m:
        return []
    meses = [MESES[g.upper()] for g in (m.group(1), m.group(2)) if g]
    ano = int(m.group(3)) if m.group(3) else None
    if ano is None:
        if not data_iso:
            return []
        ano = int(data_iso[:4])
        if meses[-1] > int(data_iso[5:7]):
            ano -= 1  # "MÊS DE DEZEMBRO" emitido em janeiro
    return [f"{ano}-{mes:02d}" for mes in meses]


def parse_page(raw: bytes, bronze_file: str) -> list[dict[str, object]]:
    """Linhas de uma página (sem resolução de anulações). Valida nº de linhas contra o rodapé ``[a a b de N]``."""
    html = raw.decode("utf-8")
    rows: list[dict[str, object]] = []
    for _, inner in RE_TR.findall(html):
        f: dict[str, str] = {}
        for name, val in RE_FIELD.findall(inner):
            txt = clean(val)
            if name != "objeto" and ": " in txt:
                txt = txt.split(": ", 1)[1]
            elif name != "objeto" and txt.endswith(":"):
                txt = ""
            f[name] = txt.strip()
        numero = f.get("numero_empenho", "").upper()
        if not numero:
            log.warning(
                "%s: registro sem número ignorado: %r", bronze_file, {k: v[:30] for k, v in f.items()}
            )
            continue
        data = iso_date(f.get("data_emissao_empenho", ""))
        mnum = RE_NUMERO.match(numero)
        ano = int(data[:4]) if data else (int(mnum.group(1)) if mnum else None)
        valor = parse_valor(f.get("valor_empenho", ""))
        if valor is None:
            log.warning("%s: %s sem valor numérico (%r)", bronze_file, numero, f.get("valor_empenho"))
        objeto = f.get("objeto", "")
        credor_fonte = f.get("credor", "")
        proc = RE_PROCESSO.search(objeto)
        aud = RE_AUDITORIA.search(objeto)
        comps = competencias(objeto, data)
        tipo = f.get("tipo_empenho", "")
        rows.append(
            {
                "numero": numero,
                "tipo": tipo,
                "modalidade": f.get("modalidade_empenho", ""),
                "data": data,
                "ano": ano,
                "valor": valor,
                "cnpj_cpf": cnpj_cpf(f.get("cnpjcpf", "")),
                "credor_fonte": credor_fonte,
                "credor": clean(credor_fonte),
                "objeto": mascarar_cpf(objeto),
                "processo": RE_WS.sub("", proc.group(1)) if proc else "",
                "auditoria": aud.group(1) if aud else "",
                "categoria": categoria(objeto),
                "anulacao": tipo.lower().startswith("anula") or bool(RE_ANULACAO.search(objeto)),
                "anula_numero": "",
                "anula_fonte": "",
                "competencia_ref": comps[-1] if comps else "",
                "competencias": "|".join(comps),
                "bronze_file": bronze_file,
            }
        )
    m = RE_TOTAL.search(html)
    if m:
        esperado = int(m.group(2)) - int(m.group(1)) + 1
        if esperado != len(rows):
            log.warning(
                "%s: %d linhas extraídas, rodapé diz %d (%s)", bronze_file, len(rows), esperado, m.group(0)
            )
    else:
        log.warning("%s: sem rodapé [a a b de N]; %d linhas extraídas sem validação", bronze_file, len(rows))
    return rows


def resolve_anulacoes(rows: list[dict[str, object]]) -> int:
    """Liga cada anulação ao empenho anulado e herda categoria/competência. Devolve nº resolvido."""
    by_num = {r["numero"]: r for r in rows}
    by_credor: dict[str, list[dict[str, object]]] = defaultdict(list)
    for r in rows:
        if not r["anulacao"]:
            by_credor[str(r["credor"])].append(r)
    n = 0
    for r in rows:
        if not r["anulacao"]:
            continue
        alvo: dict[str, object] | None = None
        m = RE_NOTA_REF.search(str(r["objeto"]))
        if m:
            alvo = by_num.get(f"{m.group(2)}NE{int(m.group(1)):06d}")
            fonte = "objeto"
        if alvo is None:
            cands = [
                c
                for c in by_credor.get(str(r["credor"]), [])
                if c["valor"] == r["valor"] and c["data"] and r["data"] and c["data"] <= r["data"]
            ]
            alvo = max(cands, key=lambda c: str(c["data"])) if cands else None
            fonte = "credor_valor_data"
        if alvo is None:
            continue
        n += 1
        r["anula_numero"] = alvo["numero"]
        r["anula_fonte"] = fonte
        if r["categoria"] == "outro":
            r["categoria"] = alvo["categoria"]
        if not r["competencia_ref"]:
            r["competencia_ref"] = alvo["competencia_ref"]
            r["competencias"] = alvo["competencias"]
    return n


def latest_snapshot(dir_: Path) -> list[Path]:
    """Páginas do snapshot mais recente, em ordem de página."""
    by_date: dict[str, list[Path]] = defaultdict(list)
    for p in dir_.glob("empenhos_*_p*.html"):
        m = RE_PAGE.match(p.name)
        if m:
            by_date[m.group(1)].append(p)
    if not by_date:
        return []
    return sorted(by_date[max(by_date)])


def parse_snapshot(pages: Iterable[Path]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    dup = 0
    for p in pages:
        for r in parse_page(p.read_bytes(), p.name):
            if r["numero"] in seen:
                dup += 1
                continue
            seen.add(str(r["numero"]))
            rows.append(r)
    if dup:
        log.warning(
            "%d empenho(s) repetidos entre páginas (grade deslocou durante a coleta); mantido o primeiro", dup
        )
    n_anul = resolve_anulacoes(rows)
    log.info("%d anulações, %d ligadas ao empenho anulado", sum(1 for r in rows if r["anulacao"]), n_anul)
    rows.sort(key=lambda r: (str(r["data"]), str(r["numero"])))
    return rows


def write_csv(path: Path, rows: Iterable[dict[str, object]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            out = dict(r)
            out["anulacao"] = "true" if r["anulacao"] else "false"
            out["valor"] = "" if r["valor"] is None else f"{r['valor']:.2f}"
            w.writerow(out)
            n += 1
    return n


def build(bronze_dir: Path = BRONZE_DIR, out: Path = SILVER_OUT) -> int:
    pages = latest_snapshot(bronze_dir)
    if not pages:
        log.warning("nenhum empenhos_*_p*.html em %s", bronze_dir)
        return 0
    rows = parse_snapshot(pages)
    n = write_csv(out, rows)
    cat = Counter(str(r["categoria"]) for r in rows)
    verba = [r for r in rows if r["categoria"] == "verba_compensatoria"]
    sem_comp = sum(1 for r in verba if not r["competencia_ref"])
    log.info(
        "%s: %d empenhos de %d páginas (%s); categorias %s; verba sem competência no objeto: %d",
        out,
        n,
        len(pages),
        pages[0].name,
        dict(cat),
        sem_comp,
    )
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="gridRegistroEmpenho (bronze) → silver/empenho.csv")
    ap.add_argument("--bronze", type=Path, default=BRONZE_DIR)
    ap.add_argument("--out", type=Path, default=SILVER_OUT)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    build(args.bronze, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
