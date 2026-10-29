"""Parser da dimensão de vereadores: bronze (HTML do site da CMS) -> silver + checagem dos seeds.

Entradas (sem rede):
- data/bronze/vereadores/vereadores.html   índice com as abas "Vereadores" e "Ex-vereadores e licenciados"
- data/bronze/vereadores/<slug>.html       perfil (nome, partido, nascimento, gabinete, biografia, nota de licença)

Saída: data/silver/vereadores.csv (UTF-8, ordenado por vereador_id).

Seeds curados (data/seeds/vereador_dim.csv, vereador_alias.csv) são lidos e validados aqui
(`validate_seeds`) e usados pelo `--check` para apontar nomes da presença sem alias.
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
from pathlib import Path
from typing import Any

from lxml import html as lhtml

from spot.config import BRONZE, CMS_SITE, SEEDS, SILVER

log = logging.getLogger(__name__)

BRONZE_DIR = BRONZE / "vereadores"
INDEX_NAME = "vereadores.html"
SILVER_CSV = SILVER / "vereadores.csv"
DIM_CSV = SEEDS / "vereador_dim.csv"
ALIAS_CSV = SEEDS / "vereador_alias.csv"

SITUACOES = {"titular", "suplente", "licenciado", "ex"}
FONTES = {"frequencia", "comissao", "centro_custo", "empenho", "etcm", "ata", "proposicao"}
CONFIANCAS = {"alta", "media", "baixa"}
DIM_COLS = [
    "vereador_id",
    "nome_parlamentar",
    "nome_civil",
    "partido",
    "situacao",
    "gabinete_cc_codigo",
    "legislatura",
    "fonte_url",
    "confianca",
    "observacao",
]
ALIAS_COLS = ["alias", "fonte", "vereador_id", "valido_de", "valido_ate", "confianca", "observacao"]
SILVER_COLS = [
    "vereador_id",
    "nome",
    "partido",
    "grupo",
    "nascimento",
    "legislatura",
    "gabinete_numero",
    "gabinete_endereco",
    "email",
    "telefones",
    "licenca_data",
    "licenca_dias",
    "suplente_nome",
    "suplente_partido",
    "licenca_texto",
    "fonte_url",
    "foto_url",
    "bio",
    "no_indice",
    "perfil_no_bronze",
]
RE_FOTO = re.compile(r"background-image:\s*url\('?\"?([^'\")]+)")

RE_SLUG = re.compile(r"getUrl\('/vereadores/([a-z0-9-]+)'")
# `Gabinete 34`, `Gab. 34`, `gabinete nº 6`, `gabinete n° 5`, `Gabinete. 27`
RE_GAB_NUM = re.compile(r"Gab(?:inete|\.)\.?\s*(?:n[ºo°]?\.?\s*)?(\d+)", re.I)
RE_DATE_BR = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
RE_LICENCA = re.compile(r"licenciou-se", re.I)
RE_DATA_PT = re.compile(r"(?:(\d{1,2})º?\s+de\s+)?([a-zç]+)\s+de\s+(\d{4})", re.I)
RE_DIAS = re.compile(r"(\d+)\s+dias", re.I)
RE_SUPLENTE = re.compile(
    r"suplente(?:\s+do\s+partido)?\s+([A-ZÀ-Ý][^,()]*?[a-zà-ÿA-ZÀ-Ý])\s*\(([^)]+)\)", re.S
)
MESES = {
    m: i + 1
    for i, m in enumerate(
        [
            "janeiro",
            "fevereiro",
            "março",
            "abril",
            "maio",
            "junho",
            "julho",
            "agosto",
            "setembro",
            "outubro",
            "novembro",
            "dezembro",
        ]
    )
}


def normalize_name(s: str) -> str:
    """Normalização mínima de nome de fonte: whitespace (há `Randerson  Leal` com espaço duplo)."""
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def _text(el: Any) -> str:
    return normalize_name(el.text_content()) if el is not None else ""


# ---- índice ----------------------------------------------------------------------------------


def parse_index(html: str) -> list[dict[str, str]]:
    """Cartões do índice: vereador_id (slug), nome, partido, grupo (titular|ex_licenciado)."""
    doc = lhtml.fromstring(html)
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for card in doc.xpath("//div[contains(@class,'avatar-container')][@onclick]"):
        m = RE_SLUG.search(card.get("onclick", ""))
        if not m or m.group(1) in seen:
            continue
        slug = m.group(1)
        seen.add(slug)
        tab = card.xpath("ancestor::div[contains(@class,'tab-pane')][1]/@id")
        grupo = (
            "ex_licenciado" if tab and tab[0].lower().startswith("ex") else "titular"
        )  # id=exvereadores_licenciados
        name = card.xpath(".//div[@class='name']/p")
        partido = card.xpath(".//div[@class='partido']/p")
        out.append(
            {
                "vereador_id": slug,
                "nome": _text(name[0]) if name else "",
                "partido": _text(partido[0]) if partido else "",
                "grupo": grupo,
            }
        )
    return out


# ---- perfil ----------------------------------------------------------------------------------


def parse_profile(html: str, slug: str) -> dict[str, str]:
    """Campos do perfil /vereadores/<slug>. Campos ausentes ficam vazios."""
    doc = lhtml.fromstring(html)
    rec: dict[str, str] = {k: "" for k in SILVER_COLS}
    rec["vereador_id"] = slug
    rec["fonte_url"] = f"{CMS_SITE}/vereadores/{slug}"
    info = doc.xpath("//div[@class='info']")
    if not info:
        log.warning("%s: perfil sem div.info", slug)
        return rec
    info = info[0]
    h4 = info.xpath("./h4")
    rec["nome"] = _text(h4[0]) if h4 else ""
    partido = info.xpath("./p[contains(@class,'partido')]")
    rec["partido"] = _text(partido[0]) if partido else ""
    telefones: list[str] = []
    for p in info.xpath("./p[contains(@class,'extra')]"):
        t = _text(p)
        key, _, val = t.partition(":")
        key, val = key.strip().lower(), val.strip()
        if key.startswith("nascimento"):
            m = RE_DATE_BR.search(val)
            rec["nascimento"] = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else val
        elif key.startswith("telefone"):
            if val:
                telefones.append(val)
        elif key.startswith("e-mail") or key.startswith("email"):
            rec["email"] = val
        elif key.startswith("legislatura"):
            rec["legislatura"] = val
        elif key.startswith("endere"):
            rec["gabinete_endereco"] = val
            m = RE_GAB_NUM.search(val)
            rec["gabinete_numero"] = m.group(1) if m else ""
    rec["telefones"] = " | ".join(telefones)
    bio_el = doc.xpath("//div[@id='fade-content']")
    bio = _text(bio_el[0]) if bio_el else ""
    rec["bio"] = re.sub(r"\s+", " ", bio).strip()
    foto = doc.xpath("//div[contains(@class,'photo')]/@style")
    m = RE_FOTO.search(foto[0]) if foto else None
    rec["foto_url"] = (
        (CMS_SITE + m.group(1)) if m and m.group(1).startswith("/") else (m.group(1) if m else "")
    )
    rec.update(parse_licenca(bio))
    return rec


def parse_licenca(bio: str) -> dict[str, str]:
    """Nota de licença do próprio vereador na biografia (a última `licenciou-se` cujo sujeito não é
    outro vereador, i.e. não precedida de `que`). Heurística: data e dias vêm da mesma frase;
    o suplente, da frase ou das ~300 letras seguintes (`suplente [do partido] Nome (Partido)`)."""
    out = {
        "licenca_data": "",
        "licenca_dias": "",
        "suplente_nome": "",
        "suplente_partido": "",
        "licenca_texto": "",
    }
    hits = [
        m
        for m in RE_LICENCA.finditer(bio)
        if not re.search(r"\bque\s*$", bio[max(0, m.start() - 6) : m.start()])
    ]
    if not hits:
        return out
    m = hits[-1]
    start = bio.rfind(". ", 0, m.start())
    start = 0 if start == -1 else start + 2
    end = bio.find(". ", m.end())
    sent = bio[start : end + 1 if end != -1 else None].strip()
    md = RE_DATA_PT.search(sent)
    if md and md.group(2).lower() in MESES:
        mes = MESES[md.group(2).lower()]
        out["licenca_data"] = (
            f"{md.group(3)}-{mes:02d}-{int(md.group(1)):02d}" if md.group(1) else f"{md.group(3)}-{mes:02d}"
        )
    elif mbr := RE_DATE_BR.search(sent):  # `no dia 09/07/2014`
        out["licenca_data"] = f"{mbr.group(3)}-{int(mbr.group(2)):02d}-{int(mbr.group(1)):02d}"
    mdias = RE_DIAS.search(sent)
    out["licenca_dias"] = mdias.group(1) if mdias else ""
    ms = RE_SUPLENTE.search(bio, m.start(), min(len(bio), m.end() + 300))
    if ms:
        out["suplente_nome"] = normalize_name(ms.group(1))
        out["suplente_partido"] = ms.group(2).strip()
        sent_end = bio.find(". ", ms.end())
        sent = bio[start : sent_end + 1 if sent_end != -1 else None].strip()
    out["licenca_texto"] = sent
    return out


# ---- silver ----------------------------------------------------------------------------------


def build_silver(bronze_dir: Path = BRONZE_DIR) -> list[dict[str, str]]:
    index_path = bronze_dir / INDEX_NAME
    if not index_path.exists():
        raise FileNotFoundError(f"bronze sem índice: {index_path}")
    cards = {
        c["vereador_id"]: c for c in parse_index(index_path.read_text(encoding="utf-8", errors="replace"))
    }
    rows: list[dict[str, str]] = []
    for slug, card in cards.items():
        path = bronze_dir / f"{slug}.html"
        if path.exists():
            rec = parse_profile(path.read_text(encoding="utf-8", errors="replace"), slug)
            rec["perfil_no_bronze"] = "true"
            if rec["nome"] != card["nome"]:
                log.debug("%s: nome do índice %r != perfil %r", slug, card["nome"], rec["nome"])
            rec["nome"] = rec["nome"] or card["nome"]
            rec["partido"] = rec["partido"] or card["partido"]
        else:
            log.warning("%s: perfil ausente no bronze, uso só o índice", slug)
            rec = {k: "" for k in SILVER_COLS}
            rec.update(vereador_id=slug, nome=card["nome"], partido=card["partido"], perfil_no_bronze="false")
            rec["fonte_url"] = f"{CMS_SITE}/vereadores/{slug}"
        rec["grupo"] = card["grupo"]
        rec["no_indice"] = "true"
        rows.append(rec)
    rows.sort(key=lambda r: r["vereador_id"])
    return rows


def write_csv(path: Path, rows: list[dict[str, str]], cols: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


# ---- seeds -----------------------------------------------------------------------------------


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_dim(path: Path = DIM_CSV) -> list[dict[str, str]]:
    return read_csv(path)


def load_alias(path: Path = ALIAS_CSV) -> list[dict[str, str]]:
    return read_csv(path)


def validate_seeds(dim: list[dict[str, str]], alias: list[dict[str, str]]) -> list[str]:
    """Integridade dos seeds. Lista vazia = ok."""
    problems: list[str] = []
    ids = [d["vereador_id"] for d in dim]
    if len(ids) != len(set(ids)):
        problems.append("vereador_dim: vereador_id duplicado")
    for d in dim:
        if list(d.keys()) != DIM_COLS:
            problems.append(f"vereador_dim: colunas {list(d.keys())}")
            break
        if d["situacao"] not in SITUACOES:
            problems.append(f"vereador_dim: situacao inválida {d['situacao']!r} em {d['vereador_id']}")
        if d["confianca"] not in CONFIANCAS:
            problems.append(f"vereador_dim: confianca inválida em {d['vereador_id']}")
        if d["gabinete_cc_codigo"] and not d["gabinete_cc_codigo"].isdigit():
            problems.append(f"vereador_dim: gabinete_cc_codigo não numérico em {d['vereador_id']}")
        if not re.fullmatch(r"[a-z0-9-]+", d["vereador_id"]):
            problems.append(f"vereador_dim: id não é slug: {d['vereador_id']!r}")
    idset = set(ids)
    keys: set[tuple[str, str]] = set()
    for a in alias:
        if list(a.keys()) != ALIAS_COLS:
            problems.append(f"vereador_alias: colunas {list(a.keys())}")
            break
        k = (a["alias"], a["fonte"])
        if k in keys:
            problems.append(f"vereador_alias: (alias, fonte) duplicado {k}")
        keys.add(k)
        if a["fonte"] not in FONTES:
            problems.append(f"vereador_alias: fonte inválida {a['fonte']!r} em {a['alias']!r}")
        if a["vereador_id"] not in idset:
            problems.append(
                f"vereador_alias: vereador_id {a['vereador_id']!r} não existe na dim ({a['alias']!r})"
            )
        if a["alias"] != normalize_name(a["alias"]):
            problems.append(f"vereador_alias: alias não normalizado {a['alias']!r}")
        for col in ("valido_de", "valido_ate"):
            if a[col] and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a[col]):
                problems.append(f"vereador_alias: {col} inválido {a[col]!r} em {a['alias']!r}")
        if a["confianca"] not in CONFIANCAS:
            problems.append(f"vereador_alias: confianca inválida em {a['alias']!r}")
    return problems


def alias_lookup(alias: list[dict[str, str]], fonte: str) -> dict[str, str]:
    """alias normalizado -> vereador_id para uma fonte (ignora vigência)."""
    return {normalize_name(a["alias"]): a["vereador_id"] for a in alias if a["fonte"] == fonte}


NAME_COLS = ("nome_fonte", "parlamentar", "nome_parlamentar", "nome")


def check_presenca(presenca_csv: Path, alias: list[dict[str, str]]) -> dict[str, int]:
    """Nomes de data/silver/presenca.csv sem alias de frequência. Devolve {nome: ocorrências}."""
    rows = read_csv(presenca_csv)
    if not rows:
        return {}
    col = next((c for c in NAME_COLS if c in rows[0]), None)
    if col is None:
        raise KeyError(f"{presenca_csv}: nenhuma coluna de nome entre {NAME_COLS}; colunas = {list(rows[0])}")
    lookup = alias_lookup(alias, "frequencia")
    missing: dict[str, int] = {}
    for r in rows:
        n = normalize_name(r[col])
        if n and n not in lookup:
            missing[n] = missing.get(n, 0) + 1
    return dict(sorted(missing.items()))


# ---- CLI -------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="bronze/vereadores -> silver/vereadores.csv; checagem dos seeds."
    )
    ap.add_argument("--bronze-dir", type=Path, default=BRONZE_DIR)
    ap.add_argument("--out", type=Path, default=SILVER_CSV)
    ap.add_argument(
        "--check", action="store_true", help="só valida seeds e reporta nomes de presenca.csv sem alias"
    )
    ap.add_argument("--presenca", type=Path, default=SILVER / "presenca.csv")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    if args.check:
        dim, alias = load_dim(), load_alias()
        problems = validate_seeds(dim, alias)
        for p in problems:
            log.error(p)
        log.info("seeds: %d vereadores, %d aliases, %d problemas", len(dim), len(alias), len(problems))
        if not args.presenca.exists():
            log.info("%s não existe ainda; nada a checar", args.presenca)
            return 1 if problems else 0
        missing = check_presenca(args.presenca, alias)
        for name, n in missing.items():
            log.error("sem alias (frequencia): %r (%d linhas)", name, n)
        log.info("presenca: %d nomes sem alias", len(missing))
        return 1 if problems or missing else 0

    rows = build_silver(args.bronze_dir)
    write_csv(args.out, rows, SILVER_COLS)
    n_tit = sum(r["grupo"] == "titular" for r in rows)
    n_lic = sum(bool(r["licenca_data"]) for r in rows)
    log.info(
        "silver: %d vereadores (%d titulares, %d ex/licenciados), %d com nota de licença -> %s",
        len(rows),
        n_tit,
        len(rows) - n_tit,
        n_lic,
        args.out,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
