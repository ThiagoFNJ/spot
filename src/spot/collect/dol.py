"""Coletor do Diário Oficial do Legislativo (DOL) para as proposições de vereadores (2025+).

Objetivo: achar a edição do DOL que publicou a íntegra de cada proposição, para o dashboard linkar
"íntegra" ao PDF. Fonte: API pública ``GET https://portal-api.dioly.com.br/api/diarios/?tipo=DOL&q=``
(``q`` é full-text sobre o conteúdo do PDF; resposta ``{items, total, page, per_page, total_pages}``).

Calibração de 2026-10-27 (≈75 requests, ver docs no relatório da coleta):

- A busca é por palavras: entre aspas = frase (palavras adjacentes), sem aspas = E de palavras.
  Case-insensitive. ``Nº`` do PDF vira a palavra ``no`` no índice (``"Portaria No 158/2026"`` acha;
  ``"Portaria Nº 158/2026"`` e ``"Portaria N 158/2026"`` não). ``N/AA`` é uma palavra só.
- O DOL cita uma proposição de três jeitos: (a) íntegra, com cabeçalho ``PROJETO DE LEI Nº 367/2025``
  (ano com 4 dígitos) seguido da ementa e do texto; (b) pauta/Ordem do Dia, ``PROJETO DE LEI Nº 232/25
  .......ementa`` (2 dígitos); (c) ata, ``Projeto de Lei n. 232/25`` ou em lista ``Projetos de Lei n.s
  274/26 do vereador ...``. O cabeçalho da íntegra sai embaralhado na extração do PDF
  (``PROJETO DE LEINº 367/ 2025``, ``Nº 3 7/ 2/2025``) e **não é encontrável** pelo número; a pauta é.
- A ementa (que o LEG_SYS copia do documento) está na íntegra e na pauta. Uma frase de 6 palavras da
  ementa acha a íntegra (PLE-1/2025 → DOL 6882 de 05/02/2025; PLE-232/2025 → DOL 6971 de 12/06/2025,
  enquanto o número só acha a pauta de 14/10/2025). Frase que atravessa quebra de linha do PDF em duas
  colunas falha; por isso há variantes.

Estratégia por proposição, parando na primeira variante com 1..``MAX_EDICOES`` edições ≥ ``ano-01-01``:

1. ``frase``: janela de 6 palavras consecutivas da ementa, única no corpus e com maior IDF, entre aspas.
2. ``termos`` (só se ``frase`` deu 0): as 5 palavras mais raras da ementa, sem aspas (E de palavras).
3. ``numero``: ``"<Nome do tipo> no N/AA"`` — forma da pauta; acha a citação, não a íntegra.

Bronze: um arquivo por query, ``data/bronze/dol/<codigo>.json`` (frase), ``<codigo>__termos.json``,
``<codigo>__numero.json`` com a resposta bruta da API; ``manifest.jsonl`` guarda url, query, variante,
sha256. Idempotente: arquivo existente não é refeito (resume implícito). ``progress.json`` tem
done/total/started/eta. Rate limit: 1 request/s por host, duro.

CLI: ``uv run python -m spot.collect.dol [--since-ano 2025] [--limit N] [--only-tipo PLE,PLC] [-v]``.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import re
import sys
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from spot.config import BRONZE, DIOLY_API, MIN_GAP_SECONDS, SEEDS, SILVER, USER_AGENT
from spot.scriptcase import Response, write_bronze

log = logging.getLogger(__name__)

BRONZE_DIR = BRONZE / "dol"
API_URL = f"{DIOLY_API}/diarios/"
PER_PAGE = 100
# A API devolve 406 sem UA de navegador (spike §6); mantemos o identificador do projeto no fim.
BROWSER_UA = f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 {USER_AGENT}"
TIMEOUT = 60.0
RETRIES = 3

JANELA = 6  # palavras por frase
N_TERMOS = 5
MAX_EDICOES = 10  # acima disso a query é genérica demais para confiar na edição mais antiga
MIN_PALAVRAS = 3
VARIANTES = ("frase", "termos", "numero")

# Nome por extenso como o DOL escreve na pauta (calibração 2026-10-27 + Regimento Interno).
TIPO_NOME = {
    "PLE": "Projeto de Lei",
    "PLC": "Projeto de Lei Complementar",
    "PEL": "Projeto de Emenda à Lei Orgânica",
    "PDL": "Projeto de Decreto Legislativo",
    "PRE": "Projeto de Resolução",
    "REP": "Requerimento",
    "RUP": "Requerimento de Utilidade Pública",
    "RUU": "Requerimento de Urgência",
    "PIN": "Projeto de Indicação",
    "MOC": "Moção",
    "VTO": "Veto",
    "SUB": "Substitutivo",
    "RAD": "Requerimento de Adiamento",
}
# Ordem da coleta: os links mais valiosos primeiro.
TIPO_PRIORIDADE = ["PLE", "PLC", "PEL", "PDL", "PRE", "MOC", "REP", "RUP", "RUU", "PIN"]

RE_CODIGO = re.compile(r"^([A-Z]+)-(\d+)/(\d{4})$")
RE_ASPAS = re.compile(r'["“”„«»]')
RE_WS = re.compile(r"\s+")
RE_PALAVRA = re.compile(r"[^\W\d_]+")  # só letras (unicode)
RE_ALNUM = re.compile(r"\w")
RE_SUJO = re.compile(r"[\d§/()]")


# ---- texto ----------------------------------------------------------------------------------


def normalizar(texto: str) -> str:
    """Como o índice do DOL vê o texto: ``º``/``°`` -> ``o``, sem aspas, whitespace simples."""
    t = unicodedata.normalize("NFC", texto).replace("º", "o").replace("°", "o").replace("ª", "a")
    t = RE_ASPAS.sub(" ", t)
    palavras = [p for p in RE_WS.split(t.strip()) if RE_ALNUM.search(p)]  # travessões soltos caem
    return " ".join(palavras)


def tokens(texto: str) -> list[str]:
    return [t.lower() for t in RE_PALAVRA.findall(texto)]


def chave(palavras: list[str]) -> str:
    return " ".join(tokens(" ".join(palavras)))


@dataclass
class Corpus:
    """Frequências sobre todas as ementas do silver: IDF por palavra e repetição de janelas."""

    n_docs: int = 0
    df: Counter[str] = field(default_factory=Counter)
    janelas: Counter[str] = field(default_factory=Counter)

    @classmethod
    def das_ementas(cls, ementas: list[str]) -> Corpus:
        c = cls(n_docs=len(ementas))
        for e in ementas:
            norm = normalizar(e)
            c.df.update(set(tokens(norm)))
            palavras = norm.split(" ")
            for i in range(max(1, len(palavras) - JANELA + 1)):
                c.janelas[chave(palavras[i : i + JANELA])] += 1
        return c

    def idf(self, token: str) -> float:
        return math.log((self.n_docs + 1) / (1 + self.df[token]))

    def score(self, palavras: list[str]) -> float:
        s = sum(self.idf(t) for t in tokens(" ".join(palavras)))
        return s - 4.0 if RE_SUJO.search(" ".join(palavras)) else s


def query_frase(ementa: str, corpus: Corpus) -> str | None:
    """Janela de JANELA palavras da ementa, única no corpus e com maior IDF, entre aspas."""
    palavras = normalizar(ementa).split(" ")
    if len(palavras) < MIN_PALAVRAS or not palavras[0]:
        return None
    if len(palavras) <= JANELA:
        return '"' + " ".join(palavras).strip(" .,;:") + '"'
    janelas = [palavras[i : i + JANELA] for i in range(len(palavras) - JANELA + 1)]
    unicas = [j for j in janelas if corpus.janelas[chave(j)] <= 1] or janelas
    melhor = max(unicas, key=corpus.score)
    return '"' + " ".join(melhor).strip(" .,;:") + '"'


def query_termos(ementa: str, corpus: Corpus, n: int = N_TERMOS) -> str | None:
    """As ``n`` palavras mais raras da ementa (≥ 4 letras), sem aspas: E de palavras, imune a quebras."""
    vistos: dict[str, int] = {}
    for pos, t in enumerate(tokens(normalizar(ementa))):
        if len(t) >= 4 and t not in vistos:
            vistos[t] = pos
    if len(vistos) < MIN_PALAVRAS:
        return None
    raras = sorted(vistos, key=lambda t: (-corpus.idf(t), vistos[t]))[:n]
    return " ".join(sorted(raras, key=vistos.__getitem__))


def query_numero(tipo: str, numero: int, ano: int) -> str | None:
    """Forma da pauta/Ordem do Dia: ``"Projeto de Lei no 232/25"`` (``Nº`` vira ``no`` no índice)."""
    nome = TIPO_NOME.get(tipo)
    return f'"{nome} no {numero}/{ano % 100:02d}"' if nome else None


# ---- proposições de entrada -----------------------------------------------------------------


@dataclass(frozen=True)
class Proposicao:
    codigo: str
    tipo: str
    numero: int
    ano: int
    ementa: str

    @property
    def nome_bronze(self) -> str:
        return sanitizar(self.codigo)


def sanitizar(codigo: str) -> str:
    return codigo.replace("/", "_")


def codigo_de_nome(nome: str) -> str:
    """``PLE-232_2025`` (ou ``PLE-232_2025__termos``) -> ``PLE-232/2025``."""
    base = nome.split("__", 1)[0]
    cabeca, _, ano = base.rpartition("_")
    return f"{cabeca}/{ano}"


def split_codigo(codigo: str) -> tuple[str, int, int]:
    m = RE_CODIGO.match(codigo)
    if not m:
        raise ValueError(f"código fora do padrão: {codigo!r}")
    return m.group(1), int(m.group(2)), int(m.group(3))


def bronze_nome(codigo: str, variante: str) -> str:
    base = sanitizar(codigo)
    return f"{base}.json" if variante == "frase" else f"{base}__{variante}.json"


def prioridade(p: Proposicao) -> tuple[int, int, int]:
    idx = TIPO_PRIORIDADE.index(p.tipo) if p.tipo in TIPO_PRIORIDADE else len(TIPO_PRIORIDADE)
    return (-p.ano, idx, p.numero)


def ler_aliases(path: Path = SEEDS / "vereador_alias.csv") -> set[str]:
    with path.open(encoding="utf-8", newline="") as f:
        return {r["alias"] for r in csv.DictReader(f) if r["fonte"] == "proposicao"}


def ler_proposicoes(
    path: Path = SILVER / "proposicao.csv",
    aliases: set[str] | None = None,
    since_ano: int = 2025,
    tipos: set[str] | None = None,
) -> tuple[list[Proposicao], Corpus]:
    """Proposições-alvo (ano ≥ since_ano, não sentinela, 1º autor vereador) + corpus de TODAS as ementas."""
    aliases = ler_aliases() if aliases is None else aliases
    alvo: list[Proposicao] = []
    ementas: list[str] = []
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            ementas.append(r["ementa"])
            if int(r["ano"]) < since_ano or r["sentinela"] == "true":
                continue
            if tipos and r["tipo"] not in tipos:
                continue
            if r["autores"].split("|")[0] not in aliases:
                continue
            alvo.append(Proposicao(r["codigo"], r["tipo"], int(r["numero"]), int(r["ano"]), r["ementa"]))
    alvo.sort(key=prioridade)
    return alvo, Corpus.das_ementas(ementas)


def queries(p: Proposicao, corpus: Corpus) -> dict[str, str | None]:
    return {
        "frase": query_frase(p.ementa, corpus),
        "termos": query_termos(p.ementa, corpus),
        "numero": query_numero(p.tipo, p.numero, p.ano),
    }


# ---- resposta da API e decisão --------------------------------------------------------------


def itens(raw: bytes | str | dict[str, Any]) -> list[dict[str, Any]]:
    """Lista ``items`` da resposta bruta (vazia se não for a resposta esperada)."""
    data = json.loads(raw) if not isinstance(raw, dict) else raw
    return data.get("items", []) if isinstance(data, dict) else []


def em_intervalo(items: list[dict[str, Any]], ano: int) -> list[dict[str, Any]]:
    """Edições com ``data_publicacao >= ano-01-01``, da mais antiga para a mais nova."""
    piso = f"{ano}-01-01"
    ok = [i for i in items if (i.get("data_publicacao") or "") >= piso]
    return sorted(ok, key=lambda i: (i["data_publicacao"], i.get("numero") or 0))


def aceitavel(n: int) -> bool:
    return 1 <= n <= MAX_EDICOES


def proxima_variante(resultados: dict[str, int], qs: dict[str, str | None]) -> str | None:
    """Próxima query a fazer dado ``{variante: nº de edições no intervalo}`` já coletadas; None = acabou.

    frase aceitável -> fim; frase == 0 -> termos; frase genérica (> MAX) -> numero; termos aceitável -> fim;
    senão numero. Variantes sem query (ementa curta, tipo sem nome) são puladas.
    """
    if "frase" not in resultados:
        if qs.get("frase"):
            return "frase"
        resultados = {**resultados, "frase": 0}
    if aceitavel(resultados["frase"]):
        return None
    if resultados["frase"] == 0 and "termos" not in resultados:
        if qs.get("termos"):
            return "termos"
        resultados = {**resultados, "termos": 0}
    if resultados["frase"] == 0 and aceitavel(resultados.get("termos", 0)):
        return None
    if "numero" not in resultados and qs.get("numero"):
        return "numero"
    return None


def escolher(resultados: dict[str, list[dict[str, Any]]]) -> tuple[str, list[dict[str, Any]]] | None:
    """Variante que vale: frase aceitável > termos aceitável > numero com ≥ 1 edição. None = sem link."""
    for v in ("frase", "termos"):
        if aceitavel(len(resultados.get(v, []))):
            return v, resultados[v]
    if resultados.get("numero"):
        return "numero", resultados["numero"]
    return None


# ---- HTTP -----------------------------------------------------------------------------------


_ULTIMO: dict[str, float] = {}


def _esperar(url: str, gap: float = MIN_GAP_SECONDS) -> None:
    host = urlsplit(url).netloc
    delta = time.monotonic() - _ULTIMO.get(host, 0.0)
    if delta < gap:
        time.sleep(gap - delta)
    _ULTIMO[host] = time.monotonic()


def novo_cliente() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": BROWSER_UA, "Accept": "application/json", "Accept-Language": "pt-BR,pt;q=0.9"},
        timeout=TIMEOUT,
        follow_redirects=True,
    )


class DolError(RuntimeError):
    pass


def buscar(http: httpx.Client, q: str) -> Response:
    """GET /api/diarios/?tipo=DOL&q=...&per_page=100 com rate limit, 3 tentativas e backoff."""
    url = API_URL + "?" + urlencode({"tipo": "DOL", "q": q, "per_page": PER_PAGE})
    ultimo: Exception | None = None
    for tentativa in range(1, RETRIES + 1):
        _esperar(url)
        t0 = time.monotonic()
        try:
            r = http.get(url)
            el = time.monotonic() - t0
            if r.status_code >= 500:
                raise DolError(f"HTTP {r.status_code}")
            if r.status_code != 200:
                raise DolError(f"HTTP {r.status_code}: {r.text[:200]!r}")
            json.loads(r.content)  # garante que o bronze é JSON
            return Response(url, r.status_code, r.content, el, "GET")
        except (httpx.HTTPError, DolError, json.JSONDecodeError) as exc:
            ultimo = exc
            log.warning("tentativa %d/%d falhou (%s): %s", tentativa, RETRIES, q, exc)
            if isinstance(exc, DolError) and exc.args[0].startswith("HTTP 4"):
                break  # 4xx não melhora repetindo
            time.sleep(2**tentativa)
    raise DolError(f"falhou: {q!r}") from ultimo


# ---- coleta ---------------------------------------------------------------------------------


def resultados_locais(dir_: Path, p: Proposicao) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for v in VARIANTES:
        f = dir_ / bronze_nome(p.codigo, v)
        if f.exists():
            out[v] = em_intervalo(itens(f.read_bytes()), p.ano)
    return out


def coletar_proposicao(http: httpx.Client, p: Proposicao, qs: dict[str, str | None], dir_: Path) -> int:
    """Faz as queries que faltam para ``p``. Devolve o nº de requests feitos."""
    res = resultados_locais(dir_, p)
    feitos = 0
    while (v := proxima_variante({k: len(x) for k, x in res.items()}, qs)) is not None:
        q = qs[v]
        assert q is not None
        resp = buscar(http, q)
        feitos += 1
        total = json.loads(resp.content).get("total")
        write_bronze(
            dir_,
            bronze_nome(p.codigo, v),
            resp,
            {"codigo": p.codigo, "tipo": p.tipo, "ano": p.ano, "variante": v, "query": q, "total": total},
        )
        res[v] = em_intervalo(itens(resp.content), p.ano)
        log.debug("%s %s %r -> total=%s no_intervalo=%d", p.codigo, v, q, total, len(res[v]))
    return feitos


def escrever_progresso(path: Path, done: int, total: int, started: datetime, requests: int) -> None:
    agora = datetime.now().astimezone()
    elapsed = (agora - started).total_seconds()
    restante = (elapsed / done) * (total - done) if done else None
    path.write_text(
        json.dumps(
            {
                "done": done,
                "total": total,
                "requests": requests,
                "started": started.isoformat(timespec="seconds"),
                "updated": agora.isoformat(timespec="seconds"),
                "eta_seconds": round(restante) if restante is not None else None,
                "eta": (agora + timedelta(seconds=restante)).isoformat(timespec="seconds")
                if restante
                else None,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )


def coletar(
    alvo: list[Proposicao],
    corpus: Corpus,
    dir_: Path = BRONZE_DIR,
    limit: int | None = None,
) -> tuple[int, int]:
    """Coleta todas as proposições (ou as ``limit`` primeiras). Devolve (proposições, requests)."""
    dir_.mkdir(parents=True, exist_ok=True)
    plano = alvo[:limit] if limit else alvo
    started = datetime.now().astimezone()
    t0 = time.monotonic()
    requests = 0
    progresso = dir_ / "progress.json"
    log.info("dol: %d proposições (de %d), bronze em %s", len(plano), len(alvo), dir_)
    with novo_cliente() as http:
        for i, p in enumerate(plano, 1):
            try:
                requests += coletar_proposicao(http, p, queries(p, corpus), dir_)
            except DolError as exc:
                log.error("%s: %s (segue para a próxima)", p.codigo, exc)
            if i % 10 == 0 or i == len(plano):
                escrever_progresso(progresso, i, len(plano), started, requests)
            if i % 100 == 0:
                log.info(
                    "dol: %d/%d proposições, %d requests, %.0fs",
                    i,
                    len(plano),
                    requests,
                    time.monotonic() - t0,
                )
    log.info("dol: fim, %d proposições, %d requests", len(plano), requests)
    return len(plano), requests


def query_da_url(url: str) -> str | None:
    """``q`` da URL do manifest (fallback quando ``params.query`` faltar)."""
    return (parse_qs(urlsplit(url).query).get("q") or [None])[0]


# ---- CLI ------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Busca no DOL (API dioly) as edições que citam cada proposição.")
    ap.add_argument("--since-ano", type=int, default=2025)
    ap.add_argument("--limit", type=int, default=None, help="só as N primeiras proposições do plano")
    ap.add_argument("--only-tipo", default=None, help="tipos separados por vírgula (ex.: PLE,PLC)")
    ap.add_argument("--input", type=Path, default=SILVER / "proposicao.csv")
    ap.add_argument("--bronze-dir", type=Path, default=BRONZE_DIR)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    tipos = {t.strip().upper() for t in args.only_tipo.split(",")} if args.only_tipo else None
    alvo, corpus = ler_proposicoes(args.input, since_ano=args.since_ano, tipos=tipos)
    coletar(alvo, corpus, args.bronze_dir, args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
