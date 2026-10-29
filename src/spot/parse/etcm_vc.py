"""Parser dos processos de pagamento de Verba Compensatória publicados no e-TCM (bronze/etcm -> silver).

Cada PDF ``PP <n> - VC - <nome civil>.pdf`` é um processo de pagamento da CMS enviado ao TCM-BA
(~12 páginas digitalizadas com camada de texto OCR, acentos frequentemente corrompidos): capa do
processo, termo de abertura, declaração de responsabilidade, **resumo das despesas pagas** (tabela com
as 15 categorias I..XV do art. 14 da Lei 9.828/2025 e o valor pago em cada uma), autorização de pagamento
da Controladoria, despacho da Diretoria Financeira, Nota de Empenho, Liquidação, Ordem Bancária /
Preparação de Pagamento e despacho final. Ver ``docs/etcm.md``.

Saídas:
- ``data/silver/verba_processo.csv`` — uma linha por processo (cabeçalho: competência, total, NE, NL, OB...).
- ``data/silver/verba_processo_item.csv`` — uma linha por categoria com valor pago.

A tabela de categorias não é reconhecida por ``extract_tables``: usamos a posição das palavras. Os
valores são palavras ``R$ 9.999,99`` na coluna da direita (x0 ≈ 80 % da largura); cada categoria é um
bloco de texto que começa à esquerda com um numeral romano (o OCR produz ``ll_``, ``1V``, ``X1V``...),
e os 15 blocos aparecem em ordem — o valor pertence ao bloco cuja faixa vertical contém o seu ``top``.
Para textos já extraídos (fixtures, sem posições) há um caminho equivalente por linhas.

Sem rede. CPFs são mascarados em tudo que é gravado.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import unicodedata
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pdfplumber

from spot.config import BRONZE, SEEDS, SILVER
from spot.parse import etcm_vc_detalhamento as det
from spot.parse.vereadores import normalize_name

log = logging.getLogger(__name__)

BRONZE_ETCM = BRONZE / "etcm"
OUT_PROCESSO = SILVER / "verba_processo.csv"
OUT_ITEM = SILVER / "verba_processo_item.csv"
OUT_NF = SILVER / "verba_processo_nf.csv"
CATEGORIAS_CSV = SEEDS / "verba_categorias.csv"
DIM_CSV = SEEDS / "vereador_dim.csv"
ALIAS_CSV = SEEDS / "vereador_alias.csv"

PROCESSO_COLUMNS = [
    "arquivo",
    "pp_numero",
    "ano_processo",
    "requerente",
    "vereador_id",
    "competencia",
    "data_entrada",
    "total_declarado",
    "auditoria_numero",
    "empenho_numero",
    "liquidacao_numero",
    "ordem_bancaria",
    "pagamento_numero",
    "data_pagamento",
    "n_paginas",
    "mes_prestacao",
    "confianca",
    "layout",
]
ITEM_COLUMNS = [
    "pp_numero",
    "ano_processo",
    "competencia",
    "categoria_romano",
    "categoria_descricao",
    "valor",
]

# Uma linha por documento fiscal (só o formulário antigo, prestações de fev e mar/2025, traz esse nível).
NF_COLUMNS = [
    "pp_numero",
    "ano_processo",
    "competencia",
    "item",
    "inciso_fonte",
    "categoria_romano",
    "descricao",
    "documento_fiscal",
    "data_emissao",
    "valor_apresentado",
    "valor_glosa",
    "valor_compensado",
]
# Formato da página de categorias: ``resumo`` (tabela I..XV, jun/2025 em diante), ``detalhamento`` (formulário
# antigo, item a item) ou ``nenhum`` (abr e mai/2025: o processo só traz o total autorizado).
LAYOUT_RESUMO, LAYOUT_DETALHAMENTO, LAYOUT_NENHUM = "resumo", "detalhamento", "nenhum"

ROMANOS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV"]
N_CATEGORIAS = len(ROMANOS)

# CPF formatado (123.456.789-01) ou só dígitos (11 seguidos). Mascaramento agressivo: melhor perder um
# número de autenticação bancária do que gravar um CPF.
RE_CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
CPF_MASK = "***.***.***-**"
# Dados bancários do vereador (página "Dados bancários" e cabeçalho do formulário antigo): nunca gravar.
RE_BANCO = re.compile(
    r"((?:Ag(?:[êeé]ncia|\.)?|Conta(?: Corrente)?|C/?C|Op(?:era[çc][ãa]o)?)\s*:?\s*)(\d[\d.\-/ ]{1,}\d)", re.I
)

BANCO_MASK = "****"
# "Anexado via login e senha por Fulano, Cpf. 12345678901, Mat. 6074" — CPF de servidor, muitas vezes quebrado
# pelo OCR ("C,pf . 941120705, 7M8at") e por isso fora do alcance de RE_CPF.
RE_CPF_ROTULO = re.compile(r"(C,?\s*pf\s*\.?\s*:?\s*)(\d[\d.,\- ]{6,}\d)", re.I)

RE_PP_ARQUIVO = re.compile(r"\bPP\s*(\d+)\b", re.I)
RE_CAPA = re.compile(r"Capa do Processo:\s*\S*?(\d{3,6})\s*/\s*(\d{4})", re.I)
RE_PROCESSO_N = re.compile(r"Processo\s+n\S*\s*(\d{3,6})\s*/\s*(\d{4})", re.I)
RE_REQUERENTE_CAPA = re.compile(r"Requerente\s*:?\s*\n\s*(.+)")
RE_REQUERENTE_INLINE = re.compile(r"Requerente\s*:\s*(.+)")
RE_VEREADOR_LINHA = re.compile(r"Vereador[a]?\s*:\s*(.+)")
RE_DATA_ENTRADA = re.compile(r"Data de Entrada\s*:?\s*(\d{2}/\d{2}/\d{4})", re.I)
# "Competéncia n°: 08/2025" — acento e símbolo de ordinal vêm corrompidos do OCR.
RE_COMPETENCIA = re.compile(r"Compet\S*\s+n\S*\s*:?\s*(\d{2})\s*/\s*(\d{4})", re.I)
RE_MES_EXTENSO = re.compile(r"m[êeé]s de\s+([A-Za-zçÇ]+)\s+de\s+(\d{4})", re.I)
RE_TOTAL = re.compile(r"TOTAL DAS DESPESAS PAGAS\s*>*\s*R[S$5]?\s*(\d{1,3}(?:\.\d{3})*[.,]\d{1,2})", re.I)
RE_IMPORTANCIA = re.compile(r"import[âa]ncia de\s+R[S$5]?\s*(\d{1,3}(?:\.\d{3})*[.,]\d{1,2})", re.I)
RE_AUDITORIA = re.compile(r"Auditoria\s+n\S*\s*:?\s*\.?\s*((?:\d{1,2}\.){2,}\d{4})", re.I)
RE_NE = re.compile(r"\b(\d{4}NE\d{6})\b")
RE_NL = re.compile(r"\b(\d{4}NL\d{6})\b")
RE_OB = re.compile(r"\b(\d{4})[O0]B(\d{6})\b")
RE_PPAG = re.compile(r"\b(\d{4}PP\d{6})\b")
RE_DATA_PGTO_BANCO = re.compile(r"Pagamento Banco Data\s*(\d{2}/\d{2}/\d{4})", re.I)
RE_DATA_LANCAMENTO = re.compile(r"Data Lan\S+\s*(\d{2}/\d{2}/\d{4})", re.I)
# Valor como o OCR o devolve: com/sem "R$" grudado, com/sem centavos ("4.800"), ponto ou vírgula
# decimal. Um inteiro solto ("279", do carimbo lateral) não é valor.
RE_VALOR = re.compile(
    r"^(?:R[S$5])?(?:\d{1,3}(?:\.\d{3})+(?:[.,]\d{1,2})?|\d{1,3}(?:\.\d{3})*[.,]\d{1,2})$|^R[S$5]\d{1,6}$"
)
RE_VALOR_LINHA = re.compile(r"(?:R[S$5]\s*|\|\s*|\s)(\d{1,3}(?:\.\d{3})*,\d{1,2})(?=\s|$)")
# Numeral romano como o OCR o devolve: I/V/X e os sósias l, L, 1, |; sufixos _ - . : grudados.
RE_ROMANO_OCR = re.compile(r"^[IVXlL1|]{1,5}[_\-.:]*$")
RE_RESUMO = re.compile(r"RESUMO\s+DA[S]?\s+DESPESAS", re.I)
RE_VERBA = re.compile(r"verba\s+compensat", re.I)
# "Período Analisado: 01 a 28 DE FEVEREIRO 2025" (formulário antigo) e "DO MÊS DE FEVEREIRO," (empenho, sem ano).
RE_PERIODO = re.compile(
    r"Per[ií]odo Analisado\s*:?\s*\d{1,2}\s*a\s*\d{1,2}\s*(?:de\s+)?([A-Za-zçÇ]+)\s*(?:de\s+)?(\d{4})", re.I
)
RE_MES_SEM_ANO = re.compile(r"m[êeé]s de\s+([A-Za-zçÇ]{4,})\b", re.I)

MESES_PREFIXO = {
    "jan": 1,
    "fev": 2,
    "mar": 3,
    "abr": 4,
    "mai": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "set": 9,
    "out": 10,
    "nov": 11,
    "dez": 12,
}


class LayoutError(ValueError):
    """O PDF não tem a estrutura esperada de um processo de verba compensatória."""


# ---- utilidades --------------------------------------------------------------------------------------


def mascarar_cpf(texto: str) -> str:
    return RE_CPF.sub(CPF_MASK, texto)


def mascarar_sensiveis(texto: str) -> str:
    """CPF + agência/conta: tudo que sai do parser (CSV, fixtures, logs) passa por aqui."""
    texto = RE_CPF_ROTULO.sub(lambda m: m.group(1) + CPF_MASK, mascarar_cpf(texto))
    return RE_BANCO.sub(lambda m: m.group(1) + BANCO_MASK, texto)


def _clean(s: str) -> str:
    return mascarar_cpf(normalize_name(s)).strip(" .;:")


def _fold(s: str) -> str:
    """Chave de comparação de nomes: sem acentos (o OCR os perde), caixa baixa, whitespace normalizado."""
    nfkd = unicodedata.normalize("NFKD", normalize_name(s))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).casefold()


def iso_date(br: str) -> str:
    d, m, y = br.split("/")
    return f"{y}-{m}-{d}"


def normalizar_valor(s: str) -> str:
    """Limpa lixo de OCR em volta de um valor: `grei1.900.00` -> `1.900.00`, `10,000,00` -> `10.000,00`,
    `pg3900,00` -> `3900,00`. Devolve string ainda no formato brasileiro (para parse_valor)."""
    s = re.sub(r"^R[S$5]", "", s.strip())
    s = re.sub(r"^[^\d]+", "", s)  # prefixo não numérico
    s = re.sub(r"[^\d.,]+$", "", s)  # sufixo não numérico
    s = re.sub(r"[^\d.,]", "", s)
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+,\d{2}", s):  # vírgula usada como milhar
        s = s[:-3].replace(",", ".") + s[-3:]
    return s


def _valores_coluna(
    words: list[dict[str, Any]], x_min: float, x_max: float, top_min: float, top_max: float, tol: float = 3.0
) -> tuple[list[tuple[float, Decimal]], list[float]]:
    """Valores da coluna da direita, um por linha, juntando fragmentos que o OCR separou
    (`9` + `800,00` -> 9.800,00; `7` + `.000,00` -> 7.000,00). Devolve (valores, tops de linhas ilegíveis)."""
    col = sorted(
        (
            w
            for w in words
            if x_min < w["x0"] < x_max and top_min < w["top"] < top_max and re.search(r"\d", w["text"])
        ),
        key=lambda w: (w["top"], w["x0"]),
    )
    lines: list[tuple[float, list[dict[str, Any]]]] = []
    for w in col:
        if lines and abs(w["top"] - lines[-1][0]) <= tol:
            lines[-1][1].append(w)
        else:
            lines.append((w["top"], [w]))
    valores: list[tuple[float, Decimal]] = []
    ilegiveis: list[float] = []
    for top, ws in lines:
        txt = normalizar_valor(
            "".join(normalizar_valor(w["text"]) for w in sorted(ws, key=lambda w: w["x0"]))
        )
        v = parse_valor(txt) if RE_VALOR.match(txt) else None
        if v is not None and v > 0:
            valores.append((top, v))
        else:
            ilegiveis.append(top)
    return valores, ilegiveis


def parse_valor(s: str) -> Decimal | None:
    """`12.900,00` -> 12900.00. Tolera OCR: `36.550.79` (ponto como decimal) e `12.900,0` (casa perdida)."""
    s = re.sub(r"^R[S$5]\s*", "", s.strip())
    if "," not in s and re.fullmatch(r"\d{1,3}(?:\.\d{3})*\.\d{2}", s):
        s = s[:-3] + "," + s[-2:]  # ponto como separador decimal (OCR)
    if "," not in s and re.fullmatch(r"\d{1,3}(?:\.\d{3})+", s):
        s = s + ",00"  # sem centavos: "4.800" = 4.800,00
    try:
        v = Decimal(s.replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None
    if re.search(r",\d$", s):  # uma casa decimal: o OCR comeu o último dígito; assume zero
        v = v * 1  # Decimal já interpreta ",0" como décimos; mantém
    return v


def _fmt(v: Decimal | None) -> str:
    return "" if v is None else f"{v:.2f}"


def _first(regex: re.Pattern[str], pages: list[str]) -> re.Match[str] | None:
    for text in pages:
        if m := regex.search(text):
            return m
    return None


def _mode(regex: re.Pattern[str], pages: list[str]) -> str:
    """Ocorrência mais frequente no documento (números SIGEF repetem-se; o OCR erra um dígito às vezes)."""
    counts = Counter(m.group(1) for text in pages for m in regex.finditer(text))
    return counts.most_common(1)[0][0] if counts else ""


# ---- extração do PDF ---------------------------------------------------------------------------------


def extract_pdf(path: Path) -> tuple[list[str], list[list[dict[str, Any]]], list[float]]:
    """(texto por página, palavras por página, largura por página) — tudo que o parser precisa do PDF."""
    texts: list[str] = []
    words: list[list[dict[str, Any]]] = []
    widths: list[float] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            texts.append(page.extract_text() or "")
            words.append(
                [
                    {"text": w["text"], "x0": w["x0"], "x1": w["x1"], "top": w["top"], "bottom": w["bottom"]}
                    for w in page.extract_words(x_tolerance=2, y_tolerance=3)
                ]
            )
            widths.append(float(page.width))
    return texts, words, widths


def find_resumo_page(pages: list[str]) -> int | None:
    for i, text in enumerate(pages):
        if RE_RESUMO.search(text) and RE_TOTAL.search(text):
            return i
    for i, text in enumerate(pages):
        if RE_RESUMO.search(text):
            return i
    for i, text in enumerate(pages):  # título ilegível no OCR, mas a linha de total está lá
        if RE_TOTAL.search(text):
            return i
    return None


def detectar_layout(pages: list[str]) -> tuple[str, int | None]:
    """(formato da página de categorias, índice da página)."""
    if (i := find_resumo_page(pages)) is not None:
        return LAYOUT_RESUMO, i
    for i, text in enumerate(pages):
        if det.RE_TITULO.search(text):
            return LAYOUT_DETALHAMENTO, i
    return LAYOUT_NENHUM, None


# ---- tabela de categorias ----------------------------------------------------------------------------


def _is_romano(token: str) -> bool:
    return bool(RE_ROMANO_OCR.match(token))


# Cada inciso começa com um texto fixo no formulário; o OCR troca acentos/cedilhas, então as âncoras
# usam classes de caracteres frouxas. Ordem = I..XV.
ANCORAS = [
    re.compile(r"softwares|aplicativos", re.I),
    re.compile(r"Loca\S{1,3}o de m\S{1,2}veis|m\S{1,2}veis e equipamentos", re.I),
    re.compile(r"assinatura permanente|assinatura", re.I),
    re.compile(r"Telefonia", re.I),
    re.compile(r"C\S{1,2}pias|fotoc\S{1,2}pias", re.I),
    re.compile(r"Expedi\S{1,3}o de cartas|cartas, correspond", re.I),
    re.compile(r"filmagens", re.I),
    re.compile(r"gastos com viagens|viagens do parlamentar", re.I),
    re.compile(r"consultorias", re.I),
    re.compile(r"Edi\S{1,3}o de jornais|jornais, livros", re.I),
    re.compile(r"material de expediente|expediente e de consumo", re.I),
    re.compile(r"m\S{1,2}dia impressa|profissionais de m", re.I),
    re.compile(r"impulsionamento", re.I),
    re.compile(r"aquisi\S{1,4}o de combust|combust\S{1,3}vel\.?$|combust\S{1,3}vel;", re.I),
    re.compile(r"Loca\S{1,3}o de Ve|Ve\S{1,2}culos", re.I),
]


def _anchor_blocks(lines: list[tuple[float, str]]) -> list[tuple[int, float]]:
    """Linhas (top, texto) -> [(índice 0..14, top)] das linhas-âncora de cada inciso, ordenadas por `top`.

    Cada inciso é procurado de forma independente (primeira linha que casa a âncora): há gabinetes que
    usam um formulário condensado, só com os incisos utilizados e numeração própria, fora da ordem I..XV.
    """
    blocks: list[tuple[int, float]] = []
    claimed: set[int] = set()
    for idx, rx in enumerate(ANCORAS):
        for j, (top, text) in enumerate(lines):
            if j not in claimed and rx.search(text):
                blocks.append((idx, top))
                claimed.add(j)
                break
    return sorted(blocks, key=lambda b: b[1])


def _assign(blocks: list[tuple[int, float]], amounts: list[tuple[float, Decimal]]) -> dict[int, Decimal]:
    """Atribui cada valor (top, Decimal) ao bloco (índice 0..14, top) cuja faixa vertical o contém."""
    tol = 4.0
    out: dict[int, Decimal] = {}
    for top, valor in amounts:
        idx = None
        for k, (bi, btop) in enumerate(blocks):
            nxt = blocks[k + 1][1] if k + 1 < len(blocks) else float("inf")
            if btop - tol <= top < nxt - tol:
                idx = bi
                break
        if idx is None:
            log.warning("valor %s em top=%.1f fora de qualquer bloco de categoria", valor, top)
            continue
        out[idx] = out.get(idx, Decimal(0)) + valor
    return out


def _block_indices(tokens: list[str]) -> list[int] | None:
    """Índices 0..14 dos blocos. Se houver exatamente 15, pela ordem; senão tenta decodificar o OCR."""
    if len(tokens) == N_CATEGORIAS:
        return list(range(N_CATEGORIAS))
    log.warning("esperados %d blocos de categoria, encontrados %d: %s", N_CATEGORIAS, len(tokens), tokens)
    decoded: list[int] = []
    for tok in tokens:
        rom = (
            re.sub(r"[_\-.:]", "", tok)
            .replace("l", "I")
            .replace("L", "I")
            .replace("1", "I")
            .replace("|", "I")
        )
        if rom.upper() not in ROMANOS:
            return None
        decoded.append(ROMANOS.index(rom.upper()))
    return decoded if len(set(decoded)) == len(decoded) and decoded == sorted(decoded) else None


def _lines_from_words(words: list[dict[str, Any]], width: float, tol: float = 3.0) -> list[tuple[float, str]]:
    """Agrupa palavras da coluna de texto (x0 < 75% da largura) em linhas por `top`."""
    col = sorted((w for w in words if w["x0"] < width * 0.75), key=lambda w: w["top"])
    groups: list[tuple[float, list[dict[str, Any]]]] = []
    for w in col:
        if groups and abs(w["top"] - groups[-1][0]) <= tol:
            groups[-1][1].append(w)
        else:
            groups.append((w["top"], [w]))
    # A camada OCR devolve palavras da mesma linha fora de ordem; reordenar por x0 recompõe o texto.
    return [(top, " ".join(w["text"] for w in sorted(ws, key=lambda w: w["x0"]))) for top, ws in groups]


def parse_itens_words(words: list[dict[str, Any]], width: float) -> tuple[dict[str, Decimal], bool]:
    """Categoria -> valor a partir das posições das palavras da página do resumo. Devolve (itens, ok)."""
    itens, ok, _ = _itens_words(words, width)
    return itens, ok


def _itens_words(words: list[dict[str, Any]], width: float) -> tuple[dict[str, Decimal], bool, list[str]]:
    """Como parse_itens_words, mais a lista de incisos cujo valor o OCR quebrou em fragmentos ilegíveis.

    Os 15 incisos são localizados por palavras-chave do texto fixo do formulário (não pelo numeral
    romano, que o OCR corrompe); cada valor da coluna da direita vai para o inciso cuja faixa vertical
    o contém. `ok` = os 15 incisos foram encontrados.
    """
    right_min, right_max = width * 0.70, width * 0.92  # o carimbo lateral girado fica depois de 92%
    header_top = min((w["top"] for w in words if w["text"] in {"Detalhamento", "Pago"}), default=0.0) + 5
    total_tops = [w["top"] for w in words if re.match(r"^[^A-Z]*TOTAL", w["text"].upper())]
    total_top = (min(total_tops) if total_tops else float("inf")) - 5
    lines = [ln for ln in _lines_from_words(words, width) if header_top < ln[0] < total_top]
    blocks = _anchor_blocks(lines)
    if len(blocks) != N_CATEGORIAS:
        log.warning(
            "esperados %d incisos, encontrados %d: %s",
            N_CATEGORIAS,
            len(blocks),
            [ROMANOS[i] for i, _ in blocks],
        )
    if not blocks:
        return {}, False, []
    amounts, frag_tops_raw = _valores_coluna(words, right_min, right_max, header_top, total_top)
    assigned = _assign(blocks, amounts)
    # Fragmentos numéricos na coluna de valores que não formam um valor válido ("5", "650", "00"):
    # o OCR quebrou um número. Guardamos o inciso para que parse_processo possa imputar o resíduo.
    frag_tops = sorted({round(t) for t in frag_tops_raw})
    ilegiveis: list[str] = []
    for top in frag_tops:
        for k, (bi, btop) in enumerate(blocks):
            nxt = blocks[k + 1][1] if k + 1 < len(blocks) else float("inf")
            if btop - 4.0 <= top < nxt - 4.0 and bi not in assigned and ROMANOS[bi] not in ilegiveis:
                ilegiveis.append(ROMANOS[bi])
    return {ROMANOS[i]: v for i, v in sorted(assigned.items())}, len(blocks) == N_CATEGORIAS, ilegiveis


def parse_itens_text(text: str) -> tuple[dict[str, Decimal], bool]:
    """Mesma lógica sobre o texto extraído (sem posições): incisos ancorados por palavra-chave."""
    raw = text.splitlines()
    end = len(raw)
    for i, line in enumerate(raw):
        if RE_TOTAL.search(line) or line.upper().startswith("TOTAL DAS DESPESAS"):
            end = i
            break
    lines = [(float(i), ln) for i, ln in enumerate(raw[:end])]
    blocks = _anchor_blocks(lines)
    if not blocks:
        return {}, False
    out: dict[str, Decimal] = {}
    for k, (idx, line_i) in enumerate(blocks):
        stop = int(blocks[k + 1][1]) if k + 1 < len(blocks) else end
        block = "\n".join(raw[int(line_i) : stop])
        total = sum((parse_valor(m) or Decimal(0) for m in RE_VALOR_LINHA.findall(block)), Decimal(0))
        if total:
            out[ROMANOS[idx]] = total
    return out, len(blocks) == N_CATEGORIAS


# ---- cabeçalho do processo ---------------------------------------------------------------------------


def competencia(pages: list[str], ano_processo: str = "") -> str:
    """``YYYY-MM`` do mês das despesas: "Competência nº", "mês de <mês> de <ano>", "Período Analisado" ou, por
    último, "mês de <mês>" sem ano (ano do processo; a verba é paga no mês seguinte ou no outro)."""
    if m := _first(RE_COMPETENCIA, pages):
        return f"{m.group(2)}-{m.group(1)}"
    for rx in (RE_MES_EXTENSO, RE_PERIODO):
        if m := _first(rx, pages):
            mes = MESES_PREFIXO.get(_fold(m.group(1))[:3])
            if mes:
                return f"{m.group(2)}-{mes:02d}"
    if ano_processo and (m := _first(RE_MES_SEM_ANO, pages)):
        mes = MESES_PREFIXO.get(_fold(m.group(1))[:3])
        if mes:
            return f"{ano_processo}-{mes:02d}"
    return ""


def requerente(pages: list[str]) -> str:
    for regex in (RE_REQUERENTE_CAPA, RE_REQUERENTE_INLINE, RE_VEREADOR_LINHA):
        if m := _first(regex, pages):
            return _clean(m.group(1))
    return ""


RE_NOME_ARQUIVO = re.compile(r"\bVC\b\s*-?\s*(.+?)\s*(?:-\s*compressed)?$", re.I)


def nome_do_arquivo(arquivo: str) -> str:
    """``PP 907 - VC - Theofilo Virgilio de Senna-compressed.pdf`` -> ``Theofilo Virgilio de Senna``."""
    m = RE_NOME_ARQUIVO.search(Path(arquivo).stem)
    return normalize_name(m.group(1)) if m else ""


def numero_processo(arquivo: str, pages: list[str]) -> tuple[str, str]:
    """(pp_numero, ano): número do nome do arquivo (confirmado pela capa), ano da capa."""
    m_arq = RE_PP_ARQUIVO.search(Path(arquivo).stem)
    m_capa = _first(RE_CAPA, pages) or _first(RE_PROCESSO_N, pages)
    pp = m_arq.group(1) if m_arq else (m_capa.group(1) if m_capa else "")
    if m_arq and m_capa and m_arq.group(1) != m_capa.group(1):
        log.warning(
            "%s: número do arquivo (%s) difere da capa (%s)", arquivo, m_arq.group(1), m_capa.group(1)
        )
    ano = m_capa.group(2) if m_capa else ""
    if not ano:
        ne = _mode(RE_NE, pages)
        ano = ne[:4] if ne else ""
    return pp, ano


def ordem_bancaria(pages: list[str]) -> str:
    m = _first(RE_OB, pages)
    return f"{m.group(1)}OB{m.group(2)}" if m else ""


def data_pagamento(pages: list[str]) -> str:
    m = _first(RE_DATA_PGTO_BANCO, pages) or _first(RE_DATA_LANCAMENTO, pages)
    return iso_date(m.group(1)) if m else ""


# ---- resolução de vereador ---------------------------------------------------------------------------


def load_nome_index(dim_csv: Path = DIM_CSV, alias_csv: Path = ALIAS_CSV) -> dict[str, str]:
    """nome (folded) -> vereador_id: alias fonte=empenho/etcm, nome_civil e nome_parlamentar da dimensão."""
    index: dict[str, str] = {}
    if alias_csv.exists():
        with alias_csv.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["fonte"] in {"empenho", "etcm"}:
                    index.setdefault(_fold(row["alias"]), row["vereador_id"])
    if dim_csv.exists():
        with dim_csv.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                for col in ("nome_civil", "nome_parlamentar"):
                    if row.get(col):
                        index.setdefault(_fold(row[col]), row["vereador_id"])
    return index


def resolve_vereador(nomes: list[str], index: dict[str, str]) -> str:
    for nome in nomes:
        if nome and (vid := index.get(_fold(nome))):
            return vid
    return ""


def load_categorias(path: Path = CATEGORIAS_CSV) -> dict[str, str]:
    with path.open(encoding="utf-8") as f:
        return {r["categoria_romano"]: r["categoria_descricao"] for r in csv.DictReader(f)}


# ---- processo ----------------------------------------------------------------------------------------


def parse_processo(
    arquivo: str,
    pages: list[str],
    words: list[list[dict[str, Any]]] | None = None,
    widths: list[float] | None = None,
    nome_index: dict[str, str] | None = None,
    categorias: dict[str, str] | None = None,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Um processo -> (linha de verba_processo, linhas de verba_processo_item).

    ``pages`` são os textos por página (já podem estar mascarados). Com ``words``/``widths`` a tabela de
    categorias usa posições; sem eles, o caminho por linhas de texto.
    """
    if not pages:
        raise LayoutError(f"{arquivo}: PDF sem páginas")
    if not _first(RE_VERBA, pages):
        # O filtro "VC" do e-TCM pega homônimos (PP 2404/2025: contribuições previdenciárias de um servidor).
        raise LayoutError(f"{arquivo}: não é processo de verba compensatória")
    layout, resumo_i = detectar_layout(pages)

    ilegiveis: list[str] = []
    blocos_ok = False
    itens: dict[str, Decimal] = {}
    nfs: list[det.ItemNF] = []
    total_detalhamento: Decimal | None = None
    if layout == LAYOUT_RESUMO and resumo_i is not None:
        if words is not None and widths is not None:
            itens, blocos_ok, ilegiveis = _itens_words(words[resumo_i], widths[resumo_i])
        else:
            itens, blocos_ok = parse_itens_text(pages[resumo_i])
    elif layout == LAYOUT_DETALHAMENTO and resumo_i is not None:
        d = det.parse_paginas(pages, resumo_i)
        nfs = d.itens
        itens = det.agregar(nfs)
        blocos_ok = bool(nfs) and all(it.categoria for it in nfs)
        total_detalhamento = d.total_compensado
    else:
        log.info("%s: processo sem tabela de categorias (só o total autorizado)", arquivo)

    pp, ano = numero_processo(arquivo, pages)
    comp = competencia(pages, ano)
    req = requerente(pages)
    soma = sum(itens.values(), Decimal(0))
    # Total declarado: a linha "TOTAL DAS DESPESAS PAGAS" do resumo (ou "TOTAL >>" do detalhamento) e a
    # "importância de R$ ..." do parecer da Controladoria dizem o mesmo número; o OCR erra um ou outro
    # ("32,60" por "32.600,00"). Preferir o que fecha com a soma dos incisos; senão o maior (o erro típico é
    # perder dígitos).
    candidatos = [
        v
        for rx in (RE_TOTAL, RE_IMPORTANCIA)
        for m in [_first(rx, pages)]
        if m and (v := parse_valor(m.group(1))) is not None
    ]
    if total_detalhamento is not None:
        candidatos.append(total_detalhamento)
    total = next((c for c in candidatos if c == soma), max(candidatos) if candidatos else None)

    # A soma dos incisos fechar com o total declarado é a prova de que a tabela foi lida certa;
    # incisos não localizados sem valor não derrubam a confiança (só geram warning em parse_itens_*).
    confianca = "alta"
    imputado = ""
    if total is not None and soma != total and len(ilegiveis) == 1 and total - soma > 0:
        # Um único inciso com número ilegível: o resíduo é dele (documentado em `observacao`).
        itens[ilegiveis[0]] = total - soma
        imputado = ilegiveis[0]
        soma = total
        log.warning(
            "%s: valor do inciso %s ilegível no OCR; imputado o resíduo %s",
            arquivo,
            imputado,
            _fmt(total - sum((v for k, v in itens.items() if k != imputado), Decimal(0))),
        )
    if layout == LAYOUT_NENHUM:
        # Sem tabela não há o que conciliar: o total autorizado pela Controladoria vale, as categorias não existem.
        confianca = "media" if total is not None and comp and pp and ano and req else "baixa"
    elif total is None or soma != total:
        confianca = "baixa"
        log.warning(
            "%s: soma dos itens %s != total declarado %s (incisos_ok=%s)", arquivo, soma, total, blocos_ok
        )
    elif imputado or not (comp and pp and ano and req and blocos_ok):
        confianca = "media"

    index = nome_index if nome_index is not None else load_nome_index()
    m_ver = _first(RE_VEREADOR_LINHA, pages)
    vereador_id = resolve_vereador(
        [req, nome_do_arquivo(arquivo), _clean(m_ver.group(1)) if m_ver else ""], index
    )
    if not vereador_id:
        log.warning("%s: requerente %r sem vereador_id", arquivo, req)

    m_ent = _first(RE_DATA_ENTRADA, pages)
    m_aud = _first(RE_AUDITORIA, pages)
    row = {
        "arquivo": mascarar_cpf(Path(arquivo).name),
        "pp_numero": pp,
        "ano_processo": ano,
        "requerente": req,
        "vereador_id": vereador_id,
        "competencia": comp,
        "data_entrada": iso_date(m_ent.group(1)) if m_ent else "",
        "total_declarado": _fmt(total),
        "auditoria_numero": m_aud.group(1).strip(".") if m_aud else "",
        "empenho_numero": _mode(RE_NE, pages),
        "liquidacao_numero": _mode(RE_NL, pages),
        "ordem_bancaria": ordem_bancaria(pages),
        "pagamento_numero": _mode(RE_PPAG, pages),
        "data_pagamento": data_pagamento(pages),
        "n_paginas": str(len(pages)),
        "mes_prestacao": "",
        "confianca": confianca,
        "layout": layout,
    }
    row = {k: mascarar_sensiveis(v) for k, v in row.items()}

    desc = categorias if categorias is not None else load_categorias()
    item_rows = [
        {
            "pp_numero": pp,
            "ano_processo": ano,
            "competencia": comp,
            "categoria_romano": rom,
            "categoria_descricao": desc.get(rom, ""),
            "valor": _fmt(valor),
        }
        for rom, valor in itens.items()
    ]
    nf_rows = [
        {
            "pp_numero": pp,
            "ano_processo": ano,
            "competencia": comp,
            "item": it.item,
            "inciso_fonte": it.inciso_fonte,
            "categoria_romano": it.categoria,
            "descricao": mascarar_sensiveis(it.descricao),
            "documento_fiscal": mascarar_sensiveis(it.documento),
            "data_emissao": it.data_emissao,
            "valor_apresentado": _fmt(it.apresentado),
            "valor_glosa": _fmt(it.glosa),
            "valor_compensado": _fmt(it.compensado),
        }
        for it in nfs
    ]
    return row, item_rows, nf_rows


def parse_pdf(path: Path, **kw: Any) -> tuple[dict[str, str], list[dict[str, str]], list[dict[str, str]]]:
    texts, words, widths = extract_pdf(path)
    return parse_processo(path.name, texts, words, widths, **kw)


def dump_fixture(path: Path, out_txt: Path, out_words: Path | None = None) -> None:
    """Texto por página com CPFs mascarados (e, opcionalmente, as palavras da página do resumo) para testes."""
    texts, words, widths = extract_pdf(path)
    sep = "\n\n===== PAGE {n} =====\n"
    out_txt.write_text(
        "".join(sep.format(n=i) + mascarar_sensiveis(t) for i, t in enumerate(texts, 1)).lstrip("\n") + "\n",
        encoding="utf-8",
    )
    if out_words is not None:
        _, i = detectar_layout(texts)
        if i is None:
            raise LayoutError(f"{path.name}: sem página de resumo")
        page_words = [
            {k: (mascarar_sensiveis(v) if k == "text" else round(v, 2)) for k, v in w.items()}
            for w in words[i]
        ]
        payload = {"page": i + 1, "width": round(widths[i], 2), "words": page_words}
        out_words.write_text(json.dumps(payload, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")


def split_fixture(text: str) -> list[str]:
    """Inverso de ``dump_fixture``: texto do fixture -> lista de páginas."""
    parts = re.split(r"^===== PAGE \d+ =====\n", text, flags=re.M)
    return [p.strip("\n") for p in parts if p.strip()]


# ---- CLI ---------------------------------------------------------------------------------------------


def write_csv(path: Path, rows: list[dict[str, str]], cols: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def parse_dir(
    bronze: Path = BRONZE_ETCM,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    index = load_nome_index()
    desc = load_categorias()
    processos: list[dict[str, str]] = []
    itens: list[dict[str, str]] = []
    nfs: list[dict[str, str]] = []
    for pdf in sorted(bronze.rglob("*VC*.pdf")):
        try:
            row, item_rows, nf_rows = parse_pdf(pdf, nome_index=index, categorias=desc)
        except LayoutError as e:
            log.error("%s", e)
            continue
        if re.fullmatch(r"\d{4}-\d{2}", pdf.parent.name):
            row["mes_prestacao"] = pdf.parent.name
        processos.append(row)
        itens.extend(item_rows)
        nfs.extend(nf_rows)
        log.info(
            "%s: pp=%s comp=%s total=%s itens=%d nfs=%d layout=%s confianca=%s",
            pdf.name,
            row["pp_numero"],
            row["competencia"],
            row["total_declarado"],
            len(item_rows),
            len(nf_rows),
            row["layout"],
            row["confianca"],
        )
    processos.sort(key=lambda r: (r["ano_processo"], int(r["pp_numero"] or 0)))
    itens.sort(
        key=lambda r: (r["ano_processo"], int(r["pp_numero"] or 0), ROMANOS.index(r["categoria_romano"]))
    )
    nfs.sort(
        key=lambda r: (r["ano_processo"], int(r["pp_numero"] or 0), r["item"] or "99", r["data_emissao"])
    )
    return processos, itens, nfs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="PDFs 'PP <n> - VC - <nome>.pdf' do e-TCM -> silver/verba_processo*.csv"
    )
    ap.add_argument("--bronze", type=Path, default=BRONZE_ETCM)
    ap.add_argument(
        "--dump-fixture", type=Path, help="PDF -> texto mascarado por página (para tests/fixtures)"
    )
    ap.add_argument(
        "--out", type=Path, help="destino do --dump-fixture (.txt); .json das palavras vai ao lado"
    )
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.dump_fixture:
        out = args.out or Path(args.dump_fixture.stem + ".txt")
        dump_fixture(args.dump_fixture, out, out.with_suffix(".words.json"))
        log.info("fixture gravado em %s", out)
        return 0

    processos, itens, nfs = parse_dir(args.bronze)
    if not processos:
        log.error("nenhum PDF '*VC*.pdf' processado em %s", args.bronze)
        return 1
    write_csv(OUT_PROCESSO, processos, PROCESSO_COLUMNS)
    write_csv(OUT_ITEM, itens, ITEM_COLUMNS)
    write_csv(OUT_NF, nfs, NF_COLUMNS)
    log.info(
        "%d processo(s), %d item(ns), %d nota(s) -> %s, %s, %s",
        len(processos),
        len(itens),
        len(nfs),
        OUT_PROCESSO,
        OUT_ITEM,
        OUT_NF,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
