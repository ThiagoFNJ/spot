"""Formulário antigo da verba compensatória (prestações de fev e mar/2025 no e-TCM):
``DETALHAMENTO / RESUMO - PROCESSO VERBA COMPENSATORIA``.

Uma linha por documento fiscal: item | referência ao inciso | histórico / tipo da despesa | nº do documento
fiscal | data de emissão | valor apresentado | glosa | saldo a compensar. A página nasceu digital, então o OCR
é bom e o parse é por linha de texto. A referência ao inciso foi preenchida por cada gabinete à sua maneira
(combustível aparece como VIII, XIV e XVI), por isso a categoria da lei (I..XV do art. 14 da Lei 9.828/2025) é
inferida do texto do tipo de despesa por palavras-chave; o inciso declarado fica em ``inciso_fonte``.

Linhas de valor sem número de item (vários cupons de combustível de um mesmo item, por exemplo) entram como
itens próprios com ``item`` vazio. Linhas só com ``R$ 0,00`` são ignoradas.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal

log = logging.getLogger(__name__)

RE_TITULO = re.compile(r"DETALHAMENTO\s*/?\s*(?:RESUMO)?\s*-?\s*PROCESSO\s+VERBA", re.I)
RE_ITEM = re.compile(r"^\s*[|{\[]?\s*[oO0]?(\d{1,2})\s+(?=\S)(.*)$")
RE_VALOR_RS = re.compile(
    r"R[S$5]\s*(\d{1,3}(?:[. ]\d{3})*,\d{2})"
)  # "R$ 21 441,55": OCR troca o ponto por espaço
RE_DATA = re.compile(r"\b(\d{1,2})[-/]([a-zç]{3})[-/](\d{2,4})\b|\b(\d{2})/(\d{2})/(\d{2,4})\b", re.I)
RE_TOTAL = re.compile(r"^[^A-Za-z]*TOTAL\b", re.I)
RE_DOC_NUM = re.compile(r"^\d{1,15}$")
RE_DOC_TXT = re.compile(
    r"((?:cupom\s*fiscal|cupom|recibo|nf\s*\d*|boleto|fatura)(?:\s+i?legivel|\s+llegivel)?|i?legivel|llegivel)\s*$",
    re.I,
)

RE_WRAP = re.compile(r"^[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ ]{1,40}$")

_MESES = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}  # fmt: skip

ROMANOS_LEI = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV"]

# (categoria, regex sobre o tipo de despesa + documento, sem acentos e em caixa baixa). A ordem importa:
# impulsionamento antes de mídia; gráfica/impressão antes de mídia/divulgação; mídia/comunicação antes de
# assessoria (``assessoria de imprensa`` é XII, ``assessoria jurídica`` é IX).
REGRAS_CATEGORIA: list[tuple[str, re.Pattern[str]]] = [
    (rom, re.compile(rx))
    for rom, rx in [
        ("XIII", r"impulsion|patrocin|boost|anuncio|\bads\b"),
        ("XIV", r"combust|cupom|gasolina|etanol|\bposto\b"),
        ("XV", r"loca\w*\s+(?:de\s+)?(?:auto|veic|carro)|automovel|veicul|\bcarro"),
        ("I", r"software|aplicativ|nuvem|armazenamento|licenca|sistema|\bapp\b"),
        ("II", r"tecnologia da informa|informatica|equipament|movei|manuten|internet|wi-?fi|\bti\b"),
        ("IV", r"telefon|celular"),
        ("V", r"\bcopia|digitaliza|xerox|reprograf"),
        ("VI", r"correio|postal|sedex|\bcartas?\b|mensage"),
        ("VII", r"filmag|fotograf|\bvideo|audiovisual"),
        ("VIII", r"viage|passage|hospedage|diaria"),
        (
            "X",
            r"grafic|impressao|impressoes|jornal|livro|revista|banner|panflet|folder|adesiv|editora|edicao",
        ),
        ("XII", r"midia|\bsocial|digital|divulga|comunica|imprensa|\bredes?\b|marketing|design|publicid"),
        ("IX", r"consultor|assessor|juridic|advoc|pesquisa|projeto|tecnic|contab"),
        ("III", r"assinatura|\bcurso|capacita|formacao|publicac"),
        ("XI", r"expediente|\bconsumo|material|papelaria"),
    ]
]


@dataclass
class ItemNF:
    item: str
    inciso_fonte: str
    categoria: str
    descricao: str
    documento: str
    data_emissao: str
    apresentado: Decimal
    glosa: Decimal
    compensado: Decimal


@dataclass
class Detalhamento:
    itens: list[ItemNF] = field(default_factory=list)
    total_apresentado: Decimal | None = None
    total_glosa: Decimal | None = None
    total_compensado: Decimal | None = None


def fold(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return re.sub(r"\s+", " ", "".join(c for c in nfkd if not unicodedata.combining(c))).casefold().strip()


def romano(token: str) -> str:
    """Normaliza o inciso como o OCR o devolve (``Il``, ``Vil``, ``1X``, ``XI!``, ``Iv``) -> ``II``, ``VII``..."""
    t = re.sub(r"[|!il1L]", "I", token.strip(" .:_-")).upper()
    if t and re.fullmatch(r"X{0,2}(?:IX|IV|V?I{0,3})", t):
        return t
    return ""


def categoria_por_texto(descricao: str, documento: str = "", inciso_fonte: str = "") -> str:
    """Categoria da lei pelo texto; cai no inciso declarado quando ele é válido e nenhuma regra casa."""
    alvo = fold(f"{descricao} {documento}")
    for rom, rx in REGRAS_CATEGORIA:
        if rx.search(alvo):
            return rom
    return inciso_fonte if inciso_fonte in ROMANOS_LEI else ""


def _decimal(s: str) -> Decimal:
    return Decimal(re.sub(r"[. ]", "", s).replace(",", "."))


def _data_iso(m: re.Match[str]) -> str:
    if m.group(1):
        d, mes, a = m.group(1), _MESES.get(fold(m.group(2))[:3]), m.group(3)
        if mes is None:
            return ""
    else:
        d, mes, a = m.group(4), int(m.group(5)), m.group(6)
    a = f"20{a}" if len(a) == 2 else a
    return f"{a}-{mes:02d}-{int(d):02d}"


def _split_descricao(pre: str) -> tuple[str, str, str]:
    """Texto entre o inciso e o primeiro valor -> (descrição, documento fiscal, data ISO)."""
    data = ""
    if m := RE_DATA.search(pre):
        data = _data_iso(m)
        pre = pre[: m.start()] + " " + pre[m.end() :]
    pre = re.sub(r"[|(){}\[\]\\/]", " ", pre)
    pre = re.sub(r"\s+", " ", pre).strip(" -")
    documento = ""
    tokens = pre.split(" ")
    if tokens and RE_DOC_NUM.match(tokens[-1]):
        documento, pre = tokens[-1], " ".join(tokens[:-1])
    elif m := RE_DOC_TXT.search(pre):
        documento, pre = m.group(1).strip(), pre[: m.start()]
    return pre.strip(" -"), documento, data


def _valores(line: str) -> list[Decimal]:
    return [_decimal(v) for v in RE_VALOR_RS.findall(line)]


def _montar(item: str, rest: str, vals: list[Decimal]) -> ItemNF | None:
    tokens = rest.split()
    inciso = ""
    if tokens and tokens[0] in {"|", "{", "[", "!", "\\", "/"}:
        tokens = tokens[1:]
    if tokens and (r := romano(tokens[0])):
        inciso = r
        tokens = tokens[1:]
    rest = " ".join(tokens)
    cut = RE_VALOR_RS.search(rest)
    pre = rest[: cut.start()] if cut else rest
    descricao, documento, data = _split_descricao(pre)
    # Colunas: apresentado | glosa | saldo a compensar. O OCR costuma destruir a última ("R$ zoe", "R$ 8.0000"),
    # então o saldo é recalculado como apresentado - glosa sempre que as duas primeiras existem.
    if len(vals) >= 3:
        apresentado, glosa = vals[0], vals[1]
        compensado = apresentado - glosa if 0 <= glosa <= apresentado else vals[2]
    elif len(vals) == 2:
        apresentado = vals[0]
        if vals[1] == 0 or vals[1] == apresentado:
            glosa, compensado = Decimal(0), apresentado  # (apresentado, glosa 0) ou (apresentado, saldo)
        else:
            compensado = vals[1]  # (apresentado, saldo): a glosa é a diferença
            glosa = apresentado - compensado if apresentado >= compensado else Decimal(0)
    elif len(vals) == 1:
        apresentado = compensado = vals[0]
        glosa = Decimal(0)
    else:
        return None
    if apresentado == 0 and compensado == 0:
        return None
    return ItemNF(
        item=item,
        inciso_fonte=inciso,
        categoria=categoria_por_texto(descricao, documento, inciso),
        descricao=descricao,
        documento=documento,
        data_emissao=data,
        apresentado=apresentado,
        glosa=glosa,
        compensado=compensado,
    )


def parse_pagina(text: str) -> Detalhamento:
    """Página ``DETALHAMENTO / RESUMO`` -> itens por documento fiscal e totais da linha ``TOTAL >>``."""
    out = Detalhamento()
    lines = text.splitlines()
    start = next((i + 1 for i, ln in enumerate(lines) if RE_TITULO.search(ln)), 0)
    for ln in lines[start:]:
        if RE_TOTAL.match(ln):
            vals = _valores(ln)
            if vals:
                out.total_apresentado = vals[0]
                out.total_compensado = vals[-1]
                out.total_glosa = vals[1] if len(vals) >= 3 else Decimal(0)
            break
        vals = _valores(ln)
        m = RE_ITEM.match(ln)
        if m and (vals or romano(m.group(2).split()[0]) if m.group(2).split() else False):
            if it := _montar(m.group(1).zfill(2), m.group(2), vals):
                out.itens.append(it)
        elif vals:
            if it := _montar("", ln, vals):
                out.itens.append(it)
        elif out.itens and RE_WRAP.match(ln.strip()) and not re.search(r"\d", ln):
            out.itens[-1].descricao = f"{out.itens[-1].descricao} {ln.strip()}".strip()
            out.itens[-1].categoria = categoria_por_texto(
                out.itens[-1].descricao, out.itens[-1].documento, out.itens[-1].inciso_fonte
            )
    sem_categoria = [it for it in out.itens if not it.categoria]
    if sem_categoria:
        log.warning("itens sem categoria inferida: %s", [(it.item, it.descricao) for it in sem_categoria])
    return out


def parse_paginas(pages: list[str], start: int, max_pages: int = 4) -> Detalhamento:
    """A tabela pode continuar nas páginas seguintes (Fábio Souza, fev/2025: 25 itens em 2 páginas): junta a página
    do título às próximas enquanto a linha ``TOTAL`` não aparecer e a página seguinte tiver linhas de item."""
    textos = [pages[start]]
    for text in pages[start + 1 : start + max_pages]:
        if any(RE_TOTAL.match(ln) and _valores(ln) for ln in textos[-1].splitlines()):
            break
        linhas = text.splitlines()
        if any(RE_ITEM.match(ln) and _valores(ln) for ln in linhas) or any(
            RE_TOTAL.match(ln) for ln in linhas
        ):
            textos.append(text)
        else:
            break
    return parse_pagina("\n".join(textos))


def agregar(itens: list[ItemNF]) -> dict[str, Decimal]:
    """Categoria -> soma do saldo a compensar (o que a Câmara efetivamente reembolsou)."""
    out: dict[str, Decimal] = {}
    for it in itens:
        if it.categoria:
            out[it.categoria] = out.get(it.categoria, Decimal(0)) + it.compensado
    return dict(sorted(out.items(), key=lambda kv: ROMANOS_LEI.index(kv[0])))
