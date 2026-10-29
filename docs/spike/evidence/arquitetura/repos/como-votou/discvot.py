"""Parsers for discvot.nsf ("Resultado das Sessões - Discursos e Votações")."""

from __future__ import annotations

import html as htmllib
import re
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup

from .spl import entry_values, iter_entries

ITEM_RE = re.compile(
    r"^(Projeto De Lei Complementar|Projeto De Lei|Projeto De Decreto Legislativo|"
    r"Projeto De Emenda À Lei Orgânica|Projeto De Resolução|Veto|Requerimento|Moção|Mensagem)\s+"
    r"(?:N[º°]\s*)?(\d+)(?:-([A-Z]))?/(\d{4})",
    re.I,
)
TIPO_MAP = {
    "projeto de lei complementar": "PLC",
    "projeto de lei": "PL",
    "projeto de decreto legislativo": "PDL",
    "projeto de emenda à lei orgânica": "PELOM",
    "projeto de resolução": "PR",
    "veto": "VETO",
    "requerimento": "REQ",
    "moção": "MOC",
    "mensagem": "MSG",
}
MONTHS = {
    m: i
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
        ],
        start=1,
    )
}


@dataclass(frozen=True)
class SessaoItem:
    unid: str
    data: str | None  # YYYY-MM-DD from the view categories
    sessao_tipo: str
    fase: str
    item: str
    autor: str
    num_sessao: str


def parse_view_items(doc: dict[str, Any], state: dict | None = None) -> list[SessaoItem]:
    """Expanded view: categories year > month(name) > 'dd/mm', then documents.

    Category rows are not repeated on later pages, so `state` carries them across pages.
    """
    state = state if state is not None else {}
    year, month, day = state.get("year"), state.get("month"), state.get("day")
    out: list[SessaoItem] = []
    for e in iter_entries(doc):
        v = entry_values(e)
        depth = e.get("@position", "").count(".")
        if "@unid" not in e:
            val = v[0].strip() if v else ""
            if depth == 0:
                year = re.sub(r"\D", "", val) or None
            elif depth == 1:
                month = MONTHS.get(val.lower())
            elif depth == 2:
                day = val
            continue
        data = None
        if year and day:
            m = re.match(r"(\d{1,2})/(\d{1,2})", day)
            if m:
                data = f"{year}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        v = (v + [""] * 7)[:7]
        out.append(
            SessaoItem(
                e["@unid"].upper(), data, v[0].strip(), v[1].strip(), v[3].strip(), v[5].strip(), v[6].strip()
            )
        )
    state.update(year=year, month=month, day=day)
    return out


def parse_search_unids(html: str) -> list[str]:
    return [
        u.upper()
        for u in dict.fromkeys(
            re.findall(r"/discvot\.nsf/[0-9a-f]{32}/([0-9a-f]{32})\?OpenDocument", html, re.I)
        )
    ]


@dataclass
class VotacaoNominal:
    sim: list[str] = field(default_factory=list)
    nao: list[str] = field(default_factory=list)
    abstencao: list[str] = field(default_factory=list)
    presentes_votando: int | None = None
    impresso: dict[str, int | None] = field(
        default_factory=dict
    )  # per-side counts as printed ("31 (trinta e um)")
    resultado: str | None = (
        None  # aprovado | rejeitado | mantido | derrubado | prejudicado | sem_quorum | None
    )
    objeto: str | None = None  # projeto | veto | emenda | substitutivo | destaque | redacao_final | None
    presidente: str | None = None  # name of the presiding officer as printed, e.g. "CARLO CAIADO"
    resultado_frase: str | None = None


@dataclass
class SessaoDoc:
    titulo: str
    item: str
    data: str | None
    hora: str | None
    texto: str
    votacoes: list[VotacaoNominal]
    presidente: str | None = None  # first presiding officer named in the document


_NAMES_SPLIT = re.compile(r"\s*[,;]\s*|\s+e\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])")
_TRAIL_COUNT = re.compile(r"\s*(\w+)\s*\(([^)]*)\)\s*\.?\s*$")
_UNITS = {
    "zero": 0,
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "tres": 3,
    "três": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
    "onze": 11,
    "doze": 12,
    "treze": 13,
    "catorze": 14,
    "quatorze": 14,
    "quinze": 15,
    "dezesseis": 16,
    "dezessete": 17,
    "dezoito": 18,
    "dezenove": 19,
}
_TENS = {
    "vinte": 20,
    "trinta": 30,
    "quarenta": 40,
    "cinquenta": 50,
    "cinqüenta": 50,
    "sessenta": 60,
    "setenta": 70,
    "oitenta": 80,
    "noventa": 90,
}


def number_words(s: str) -> int | None:
    """'trinta e um' -> 31 (0..99); None if the words are not a number."""
    words = [w for w in re.split(r"[\s,]+", s.strip().lower()) if w and w != "e"]
    if not words or len(words) > 2:
        return None
    total = 0
    for w in words:
        if w in _TENS:
            total += _TENS[w]
        elif w in _UNITS:
            total += _UNITS[w]
        else:
            return None
    return total


_ROLL_CALL = re.compile(
    r"Conclu[ií]da a vota[çc][ãa]o nominal(.*?)(?:\)\.?\s*\n|\n\s*O SR\.|\n\s*A SRA\.|$)", re.S | re.I
)
_PRESIDENTE = re.compile(r"(?:O SR\.|A SRA\.)\s*PRESIDENTE\s*\(\s*([^)]+?)\s*\)", re.I)
_PRESIDENCIA = re.compile(
    r"Presid[êe]ncia d[oa]s? (?:Senhora?\s+|Sra?\.\s+)?Vereadora?\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ][^\n,.;(]{2,60})", re.I
)

# Outcome sentences, earliest match wins. Each pattern yields a base outcome; "veto" context flips
# rejeitado -> derrubado (the veto fell) and keeps mantido.
_RESULT_PATTERNS: list[tuple[re.Pattern[str], str | None]] = [
    (
        re.compile(
            r"\b(?:est[áa]|est[ãa]o|foi|foram|fica[m]?|considerad[oa]s?)\s+(aprovad|provad|rejeitad|mantid|derrubad|prejudicad)[oa]s?\b",
            re.I,
        ),
        None,
    ),
    # bare announcement on its own line: "Aprovado." / "Aprovada a Emenda nº 1." / "Rejeitado o bloco ..."
    (re.compile(r"(?:^|\n)\s*(?:[–-]\s*)?(aprovad|rejeitad|mantid|derrubad|prejudicad)[oa]s?\b", re.I), None),
    (re.compile(r"\bn[ãa]o h[áa] qu[óo]rum para deliberar", re.I), "sem_quorum"),
    (re.compile(r"\bfalta de qu[óo]rum\b", re.I), "sem_quorum"),
]
_BASE = {
    "aprovad": "aprovado",
    "provad": "aprovado",
    "rejeitad": "rejeitado",
    "mantid": "mantido",
    "derrubad": "derrubado",
    "prejudicad": "prejudicado",
}


def _printed_count(chunk: str) -> int | None:
    """The count printed after the names: '31 (trinta e um)'. The words win over the digits (typos like '2a6')."""
    chunk = re.split(r",?\s*n[ãa]o havendo\b", chunk.strip(), maxsplit=1, flags=re.I)[0]
    m = _TRAIL_COUNT.search(chunk.strip())
    if not m:
        return None
    by_words = number_words(m.group(2))
    if by_words is not None:
        return by_words
    return int(m.group(1)) if m.group(1).isdigit() else None


def _names(chunk: str) -> list[str]:
    chunk = re.split(r",?\s*n[ãa]o havendo\b", chunk.strip(), maxsplit=1, flags=re.I)[0]
    chunk = _TRAIL_COUNT.sub("", chunk.strip())
    chunk = re.sub(
        r"^(?:[oa]s?\s+)?(?:Senhor(?:es|as?)?|Sr\.?s?|Sras?\.?)\s+Vereador(?:es|as?)?\s*",
        "",
        chunk,
        flags=re.I,
    )
    chunk = re.sub(r"^(?:[oa]s?\s+)?Vereador(?:es|as?)?\s*", "", chunk, flags=re.I)
    names = [re.sub(r"\s+\d+\w*$", "", n.strip(" .")) for n in _NAMES_SPLIT.split(chunk)]
    return [n for n in names if n and not re.fullmatch(r"\d+", n) and not re.match(r"(?i)n[ãa]o havendo", n)]


def _clean_name(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" \n–-")


def detect_resultado(after: str, objeto_hint: str | None = None) -> tuple[str | None, str | None]:
    """Earliest outcome sentence in the text that follows a roll call. Returns (resultado, sentence)."""
    best: tuple[int, str, str] | None = None
    for pat, fixed in _RESULT_PATTERNS:
        m = pat.search(after)
        if not m:
            continue
        res = fixed or _BASE[m.group(1).lower()]
        if best is None or m.start() < best[0]:
            best = (m.start(), res, m.group(0))
    if best is None:
        return None, None
    pos, res, _ = best
    s0 = after.rfind("\n", 0, pos) + 1
    s1 = after.find("\n", pos)
    sentence = _clean_name(after[s0 : s1 if s1 > 0 else None])
    context = after[max(0, pos - 200) : pos + 80]
    if res == "rejeitado" and (objeto_hint == "veto" or re.search(r"\bvetos?\b", context, re.I)):
        res = "derrubado"  # the veto was rejected, i.e. overridden
    return res, sentence


def _classify_objeto(p: str) -> str | None:
    p = p.lower()
    if re.search(r"\bvetos?\b", p):
        return "veto"
    if "subemenda" in p or "emenda" in p:
        return "emenda"
    if "substitutivo" in p:
        return "substitutivo"
    if "destaque" in p:
        return "destaque"
    if "redação final" in p or "redacao final" in p:
        return "redacao_final"
    if "projeto" in p or "matéria" in p or "materia" in p:
        return "projeto"
    return None


def detect_objeto(before: str, sentence: str | None) -> str | None:
    """What was voted, in order of confidence: the last 'Em votação <object>' line before the roll
    call; an upper-case VETO in the agenda reading (vetos are read as 'VETO PARCIAL ...', 'REJEIÇÃO AO
    VETO'); the outcome sentence; other upper-case tokens of the reading (EMENDA, SUBSTITUTIVO)."""
    ev = re.findall(r"Em vota[çc][ãa]o\b([^\n]{0,120})", before, re.I)
    line = ev[-1].strip(" .:;,") if ev else ""
    if line:
        c = _classify_objeto(line)
        if c:
            return c
    reading = before[-1500:]
    if re.search(r"\bVETOS?\b", reading):
        return "veto"
    if sentence:
        c = _classify_objeto(sentence)
        if c:
            return c
    tokens = " ".join(re.findall(r"\b(EMENDAS?|SUBEMENDAS?|SUBSTITUTIVO|DESTAQUE|REDAÇÃO FINAL)\b", reading))
    c = _classify_objeto(tokens) if tokens else None
    return c or ("projeto" if ev else None)


def parse_roll_calls(texto: str) -> list[VotacaoNominal]:
    """Extract '(Concluída a votação nominal, ... votaram SIM ... votaram NÃO ... ABSTENÇÃO ...)' blocks."""
    out: list[VotacaoNominal] = []
    spans: list[tuple[int, int]] = []
    for m in _ROLL_CALL.finditer(texto):
        block = m.group(1)
        vn = VotacaoNominal()
        # end of one side's list: ". E que votaram NÃO", "; e que votou NÃO", ". Votaram NÃO", ". Abstiveram-se",
        # ". Presentes", ". Houve abstenção", or the closing parenthesis
        # transcripts contain typos ("voltaram NÃO", "Abteve-se", "E que NÃO os Senhores"); tolerate them
        vot = r"(?:vo[lt]?t(?:aram|ou))"
        stop = (
            r"(?=(?:[.;,]\s*(?:E\s+)?que\s+(?:"
            + vot
            + r"\s+)?(?:SIM|N[ÃA]O)|[.;]\s*(?:E\s+)?"
            + vot
            + r"\s+(?:SIM|N[ÃA]O)|"
            r"[.;]\s*Abs?t|[.;]\s*Presentes|[.;]\s*Votando|[.;]\s*Houve|\)\s*$|$))"
        )
        for kind, key in (
            (vot + r"\s*SIM", "sim"),
            (r"(?:" + vot + r"|que)\s*N[ÃA]O", "nao"),
            (r"(?:(?:" + vot + r"|houve)\s*)?ABSTEN[ÇC][ÃA]O(?:\s+d[eo]s?)?", "abstencao"),
            (r"abs?t(?:eve|iveram)(?:-se)?(?:\s+de\s+votar)?", "abstencao"),
        ):
            mm = re.search(kind + r"\s*(?:[:,-]\s*)?(.*?)" + stop, block, re.S | re.I)
            if mm and not getattr(vn, key):
                setattr(vn, key, _names(mm.group(1)))
                vn.impresso[key] = _printed_count(mm.group(1))
        mm = re.search(r"Presentes e votando\s+(\d+)", block)
        if mm:
            vn.presentes_votando = int(mm.group(1))
        if vn.sim or vn.nao or vn.abstencao:
            out.append(vn)
            spans.append((m.start(), m.end()))
    for i, (vn, (start, end)) in enumerate(zip(out, spans)):
        next_start = spans[i + 1][0] if i + 1 < len(spans) else len(texto)
        after = texto[end : min(end + 1500, next_start)]
        prev_end = spans[i - 1][1] if i > 0 else 0
        before = texto[max(prev_end, start - 2500) : start]
        _, frase = detect_resultado(after)
        vn.objeto = detect_objeto(before, frase)
        vn.resultado, vn.resultado_frase = detect_resultado(after, vn.objeto)
        pm = _PRESIDENTE.search(after) or (list(_PRESIDENTE.finditer(texto[:start])) or [None])[-1]
        if pm is None:
            hm = _PRESIDENCIA.search(texto[: min(len(texto), 4000)])
            vn.presidente = _clean_name(hm.group(1)) if hm else None
        else:
            vn.presidente = _clean_name(pm.group(1))
    return out


def parse_session_doc(html: str) -> SessaoDoc:
    soup = BeautifulSoup(html, "lxml")
    for s in soup(["script", "style"]):
        s.decompose()
    texto = soup.get_text("\n")
    texto = htmllib.unescape(texto)
    texto = re.sub(r"[ \t\xa0]+", " ", texto)
    texto = re.sub(r"\n\s*\n+", "\n", texto).strip()
    lines = [l.strip() for l in texto.split("\n") if l.strip()]
    titulo = lines[0] if lines else ""
    item = next((l for l in lines[:5] if ITEM_RE.match(l)), lines[1] if len(lines) > 1 else "")
    m = re.search(r"Data da Sessão:\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*Hora:\s*([\d:]+\s*[AP]M)?", texto)
    data = f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}" if m else None  # shown as MM/DD/YYYY
    hora = m.group(4) if m and m.group(4) else None
    pm = _PRESIDENTE.search(texto) or _PRESIDENCIA.search(texto[:4000])
    return SessaoDoc(
        titulo, item, data, hora, texto, parse_roll_calls(texto), _clean_name(pm.group(1)) if pm else None
    )


def parse_item(item: str) -> tuple[str, str, int] | None:
    m = ITEM_RE.match(item.strip())
    if not m:
        return None
    tipo = TIPO_MAP[m.group(1).lower()]
    numero = str(int(m.group(2))) + (f"-{m.group(3)}" if m.group(3) else "")
    return tipo, numero, int(m.group(4))
