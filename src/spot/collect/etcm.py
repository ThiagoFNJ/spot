"""Coletor dos processos de pagamento da CMS na consulta pública do e-TCM (TCM-BA).

Fonte: <https://e.tcm.ba.gov.br/epp/ConsultaPublica/listView.seam> (ver ``docs/etcm.md``). É um formulário
JSF/RichFaces com estado no servidor e filtros encadeados por AJAX; a navegação é feita com um Chromium headless
(Playwright) em vez de reproduzir os POSTs: Mensal → ano → mês → SALVADOR → "Camara Municipal de SALVADOR" →
Gestão → Pesquisar → abre a prestação → filtra "Nome do Documento" (padrão ``VC`` = verba compensatória) →
pagina a tabela de documentos e baixa cada PDF pelo link ``downloadDocBinario``.

Bronze: ``data/bronze/etcm/<YYYY-MM>/<nome original do documento>`` (o nome traz o nº do processo e o nome civil
do vereador; é preservado, só ``/`` e ``\\`` são trocados), ``manifest.jsonl`` por mês (nome, classificacao,
bytes, sha256, coletado_em, mes_prestacao, url, filtro) e ``_lista_<filtro>.json`` com TODOS os documentos
listados para o filtro, baixados ou não (inventário para conferir completude: ~43 processos VC por mês).

Regras: um contexto de navegador por mês; idempotente (arquivo existente não é baixado de novo); ≤ 1 download/s;
download que falha é tentado uma segunda vez; mês sem prestação publicada → log + código de saída 2.
``playwright`` é importado só quando o navegador é aberto, para o resto do pacote não depender dele.

CLI: ``uv run python -m spot.collect.etcm --ano 2025 --mes 09 [--filtro VC] [--max N] [--todos-meses]``.
``--todos-meses`` percorre de ``MVP_START`` (2025-01) até o mês corrente; meses sem prestação só logam.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from spot.config import BRONZE, MIN_GAP_SECONDS, MVP_START, USER_AGENT

if TYPE_CHECKING:  # pragma: no cover - só para tipos; o import real é tardio
    from playwright.sync_api import Browser, Page

log = logging.getLogger(__name__)

OUT_DEFAULT = BRONZE / "etcm"
URL = "https://e.tcm.ba.gov.br/epp/ConsultaPublica/listView.seam"
FILTRO_DEFAULT = "VC"
EXIT_SEM_PRESTACAO = 2

# Ids dos componentes JSF (estáveis entre sessões; o ``:`` precisa de escape nos seletores CSS).
_FORM = "consultaPublicaTabPanel\\:consultaPublicaPCSearchForm"
_SEARCH_BUTTON = f"#{_FORM}\\:searchButton"
_RESULT_ROWS = "tbody[id='consultaPublicaTabPanel:consultaPublicaDataTable:tb'] tr"
_FILTRO_INPUT = "input[id='consultaPublicaTabPanel:formFiltros:nomeDocumento']"
_FILTRO_BUTTON = "#consultaPublicaTabPanel\\:formFiltros\\:btnFiltrar"
_DOC_ROWS = "tbody[id='consultaPublicaTabPanel:tabelaDocumentos_data'] tr"
_DOC_NEXT = "#consultaPublicaTabPanel\\:tabelaDocumentos_paginator_bottom .ui-paginator-next"
_DOWNLOAD_LINK = "a[id$='downloadDocBinario']"
_RX_VAZIA = re.compile(r"no records found|nenhum registro", re.I)

# O servidor devolve páginas de erro para UAs que não parecem navegador; o token do spot vai no fim.
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    f"Chrome/124.0 Safari/537.36 {USER_AGENT}"
)
_WAIT_AJAX_MS = 1500
_PICK_TRIES = 20
_SHADE = "#modalStatus_shade"  # véu do RichFaces que bloqueia cliques enquanto o servidor responde
_SHADE_TIMEOUT_MS = 90_000
_MES_TRIES = 2  # tentativas por mês antes de desistir (servidor instável à noite)
_WAIT_TABLE_MS = 4000
_WAIT_PAGE_MS = 3000
_DOWNLOAD_TIMEOUT_MS = 60_000


class SemPrestacao(RuntimeError):
    """A unidade ainda não enviou a prestação de contas do mês pedido."""


@dataclass
class Documento:
    nome: str
    classificacao: str


@dataclass
class ResultadoMes:
    mes_prestacao: str
    filtro: str
    listados: list[Documento] = field(default_factory=list)
    baixados: list[str] = field(default_factory=list)
    existentes: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)
    prestacao: str = ""


# ---- helpers puros (testáveis sem navegador) --------------------------------------------------------------


def sanitize_filename(nome: str) -> str:
    """Nome do documento → nome de arquivo: troca separadores de caminho por ``_``, normaliza espaços e tira
    pontos/espaços nas pontas. O resto do nome original é preservado (o parser lê o nº do processo dele)."""
    s = re.sub(r"[/\\\x00]", "_", nome)
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s or "_sem_nome"


def iter_meses(inicio: str, fim: str) -> Iterator[str]:
    """``YYYY-MM`` de ``inicio`` a ``fim`` (inclusive), em ordem crescente."""
    y, m = (int(x) for x in inicio.split("-"))
    fy, fm = (int(x) for x in fim.split("-"))
    while (y, m) <= (fy, fm):
        yield f"{y:04d}-{m:02d}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def mes_corrente(hoje: date | None = None) -> str:
    hoje = hoje or date.today()
    return f"{hoje.year:04d}-{hoje.month:02d}"


def mes_dir(out: Path, mes_prestacao: str) -> Path:
    return out / mes_prestacao


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_entry(path: Path, doc: Documento, mes_prestacao: str, filtro: str) -> dict[str, Any]:
    return {
        "arquivo": path.name,
        "nome": doc.nome,
        "classificacao": doc.classificacao,
        "bytes": path.stat().st_size,
        "sha256": sha256_of(path),
        "coletado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "mes_prestacao": mes_prestacao,
        "url": URL,
        "filtro": filtro,
    }


def append_manifest(manifest: Path, entry: dict[str, Any]) -> None:
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_manifest(manifest: Path) -> list[dict[str, Any]]:
    if not manifest.exists():
        return []
    return [json.loads(line) for line in manifest.read_text("utf-8").splitlines() if line.strip()]


def write_lista(dirpath: Path, resultado: ResultadoMes) -> Path:
    """``_lista_<filtro>.json``: inventário de tudo que a consulta listou para o filtro (baixado ou não)."""
    dirpath.mkdir(parents=True, exist_ok=True)
    path = dirpath / f"_lista_{sanitize_filename(resultado.filtro) if resultado.filtro else 'todos'}.json"
    payload = {
        "mes_prestacao": resultado.mes_prestacao,
        "filtro": resultado.filtro,
        "prestacao": resultado.prestacao,
        "url": URL,
        "gerado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "n_listados": len(resultado.listados),
        "docs": [asdict(d) for d in sorted(resultado.listados, key=lambda d: d.nome)],
        "baixados": sorted(resultado.baixados),
        "existentes": sorted(resultado.existentes),
        "erros": sorted(resultado.erros),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), "utf-8")
    return path


# ---- navegação ----------------------------------------------------------------------------------------------


def _launch(playwright: Any) -> Browser:
    return playwright.chromium.launch(headless=True)


def _esperar_veu(page: Page) -> None:
    """Espera o véu modal do RichFaces sumir; sem ele os cliques são interceptados e o Playwright fica em loop."""
    shade = page.locator(_SHADE)
    if shade.count() and shade.first.is_visible():
        shade.first.wait_for(state="hidden", timeout=_SHADE_TIMEOUT_MS)


def _opcoes(page: Page, comp: str) -> list[str]:
    """Abre o selectOneMenu ``comp`` e devolve o texto das opções (sem o placeholder)."""
    panel = page.locator(f"#{_FORM}\\:{comp}_panel")
    _esperar_veu(page)
    if not panel.is_visible():
        page.click(f"#{_FORM}\\:{comp} .ui-selectonemenu-trigger")
        panel.wait_for(state="visible", timeout=10_000)
    items = page.locator(f"#{_FORM}\\:{comp}_items li")
    return [items.nth(i).inner_text().strip() for i in range(items.count())]


def _pick(page: Page, comp: str, rx: str) -> str:
    """Clica no item de ``comp`` cujo texto casa com ``rx``. As opções chegam por AJAX depois do filtro anterior,
    então reabre o menu até aparecerem (até ``_PICK_TRIES`` vezes, ~20 s)."""
    textos: list[str] = []
    for tentativa in range(_PICK_TRIES):
        textos = _opcoes(page, comp)
        reais = [t for t in textos if t and not t.lower().startswith("clique")]
        if reais:
            break
        page.keyboard.press("Escape")
        page.wait_for_timeout(_WAIT_AJAX_MS)
        log.debug("%s: opções ainda não carregadas (tentativa %d)", comp, tentativa + 1)
    items = page.locator(f"#{_FORM}\\:{comp}_items li")
    for i, t in enumerate(textos):
        if re.search(rx, t, re.I):
            items.nth(i).click()
            page.wait_for_timeout(_WAIT_AJAX_MS)
            return t
    page.keyboard.press("Escape")
    raise RuntimeError(f"{comp}: nenhum item casa com {rx!r} (opções: {textos})")


def abrir_prestacao(page: Page, ano: int, mes: int) -> str:
    """Preenche os filtros encadeados, pesquisa e abre a prestação do mês. Devolve o rótulo da linha."""
    page.goto(URL, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(_WAIT_AJAX_MS)
    _pick(page, "PeriodicidadePC", r"^Mensal$")
    try:
        _pick(page, "competenciaPCAno", rf"^{ano}$")
        _pick(page, "competenciaPCMes", rf"^{mes:02d}/{ano}$")
    except RuntimeError as e:
        raise SemPrestacao(f"{ano}-{mes:02d}: período não oferecido pela consulta ({e})") from e
    _pick(page, "municipio", r"^SALVADOR$")
    _pick(page, "unidadeJurisdicionada", r"^Camara Municipal de SALVADOR$")
    _pick(page, "tipoPC", r"Gest")
    _esperar_veu(page)
    page.click(_SEARCH_BUTTON)
    page.wait_for_timeout(_WAIT_TABLE_MS)
    _esperar_veu(page)
    rows = page.locator(_RESULT_ROWS)
    if rows.count() == 0 or "encontrados" in rows.first.inner_text():
        raise SemPrestacao(f"{ano}-{mes:02d}: nenhuma prestação da Câmara publicada")
    rotulo = re.sub(r"\s+", " ", rows.first.inner_text()).strip()
    rows.first.locator("a").first.click()
    page.wait_for_timeout(_WAIT_TABLE_MS)
    _esperar_veu(page)
    return rotulo


def filtrar_documentos(page: Page, filtro: str) -> None:
    page.fill(_FILTRO_INPUT, filtro)
    _esperar_veu(page)
    page.click(_FILTRO_BUTTON)
    page.wait_for_timeout(_WAIT_TABLE_MS)
    _esperar_veu(page)


def _tabela_vazia(tr: Any) -> bool:
    """A tabela sem resultados tem uma linha única de mensagem ("No records found." / "Nenhum registro")."""
    return tr.locator("td").count() < 3 or _RX_VAZIA.search(tr.inner_text()) is not None


def _doc_da_linha(tr: Any) -> Documento:
    tds = tr.locator("td")
    if tds.count() >= 3:
        return Documento(nome=tds.nth(2).inner_text().strip(), classificacao=tds.nth(1).inner_text().strip())
    return Documento(nome=tr.inner_text().strip(), classificacao="")


def _proxima_pagina(page: Page) -> bool:
    nxt = page.locator(_DOC_NEXT)
    if nxt.count() == 0 or "ui-state-disabled" in (nxt.first.get_attribute("class") or ""):
        return False
    _esperar_veu(page)
    nxt.first.click()
    page.wait_for_timeout(_WAIT_PAGE_MS)
    _esperar_veu(page)
    return True


def _baixar(page: Page, tr: Any, dest: Path) -> int:
    """Clica no link de download da linha e grava em ``dest``. Devolve o tamanho em bytes."""
    _esperar_veu(page)
    with page.expect_download(timeout=_DOWNLOAD_TIMEOUT_MS) as dl:
        tr.locator(_DOWNLOAD_LINK).click()
    _esperar_veu(page)
    dl.value.save_as(dest)
    size = dest.stat().st_size
    if size == 0:
        dest.unlink(missing_ok=True)
        raise RuntimeError("download vazio")
    return size


def _baixar_com_retry(page: Page, tr: Any, dest: Path) -> int:
    try:
        return _baixar(page, tr, dest)
    except Exception as e:  # noqa: BLE001 - qualquer falha de rede/timeout do Playwright
        log.warning("  falha no download de %s (%s); tentando de novo", dest.name, repr(e)[:120])
        time.sleep(MIN_GAP_SECONDS)
        return _baixar(page, tr, dest)


def coletar_mes(
    browser: Browser,
    ano: int,
    mes: int,
    filtro: str = FILTRO_DEFAULT,
    max_downloads: int | None = None,
    out: Path = OUT_DEFAULT,
    classes: tuple[str, ...] = (),
) -> ResultadoMes:
    """Um contexto de navegador para a prestação ``ano``/``mes``: lista e baixa os documentos do filtro.

    ``classes``: prefixos de classificação (ex.: ``PCMGE035``) — com ela, só baixa documentos dessas classes
    (a listagem continua completa e vai para ``_lista_*.json``)."""
    mes_prestacao = f"{ano:04d}-{mes:02d}"
    res = ResultadoMes(mes_prestacao=mes_prestacao, filtro=filtro)
    dirpath = mes_dir(out, mes_prestacao)
    manifest = dirpath / "manifest.jsonl"
    limite = max_downloads if max_downloads is not None else sys.maxsize
    ctx = browser.new_context(user_agent=_BROWSER_UA, accept_downloads=True)
    try:
        page = ctx.new_page()
        page.set_default_timeout(60_000)
        res.prestacao = abrir_prestacao(page, ano, mes)
        log.info("%s: prestação %s", mes_prestacao, res.prestacao[:100])
        filtrar_documentos(page, filtro)
        no_manifest = {e["arquivo"] for e in read_manifest(manifest)}
        vistos: set[str] = set()
        pagina = 1
        while True:
            trs = page.locator(_DOC_ROWS)
            n = trs.count()
            log.debug("%s: página %d com %d linhas", mes_prestacao, pagina, n)
            if n == 0 or _tabela_vazia(trs.first):
                break
            for i in range(n):
                tr = trs.nth(i)
                doc = _doc_da_linha(tr)
                if not doc.nome or doc.nome in vistos:
                    continue
                vistos.add(doc.nome)
                res.listados.append(doc)
                if classes and not any(doc.classificacao.startswith(c) for c in classes):
                    continue
                dest = dirpath / sanitize_filename(doc.nome)
                if dest.exists() and dest.stat().st_size > 0:
                    res.existentes.append(doc.nome)
                    if dest.name not in no_manifest:  # baixado fora do coletor: completa o manifesto
                        append_manifest(manifest, manifest_entry(dest, doc, mes_prestacao, filtro))
                        no_manifest.add(dest.name)
                    continue
                if len(res.baixados) >= limite:
                    continue
                dirpath.mkdir(parents=True, exist_ok=True)
                try:
                    size = _baixar_com_retry(page, tr, dest)
                except Exception as e:  # noqa: BLE001
                    log.error("  ERRO %s: %s", doc.nome, repr(e)[:160])
                    res.erros.append(doc.nome)
                    continue
                append_manifest(manifest, manifest_entry(dest, doc, mes_prestacao, filtro))
                no_manifest.add(dest.name)
                res.baixados.append(doc.nome)
                log.info("  baixado %s (%d B) [%s]", doc.nome, size, doc.classificacao[:40])
                time.sleep(MIN_GAP_SECONDS)
            if not _proxima_pagina(page):
                break
            pagina += 1
    finally:
        ctx.close()
    write_lista(dirpath, res)
    log.info(
        "%s: %d documento(s) '%s' listados; %d baixados, %d já existiam, %d erro(s)",
        mes_prestacao,
        len(res.listados),
        filtro,
        len(res.baixados),
        len(res.existentes),
        len(res.erros),
    )
    return res


def coletar(
    meses: list[str],
    filtro: str = FILTRO_DEFAULT,
    max_downloads: int | None = None,
    out: Path = OUT_DEFAULT,
    classes: tuple[str, ...] = (),
) -> tuple[list[ResultadoMes], list[str]]:
    """Abre um navegador e percorre ``meses`` (``YYYY-MM``). Devolve (resultados, meses sem prestação)."""
    from playwright.sync_api import sync_playwright  # import tardio: o resto do pacote não precisa dele

    resultados: list[ResultadoMes] = []
    sem_prestacao: list[str] = []
    with sync_playwright() as pw:
        browser = _launch(pw)
        try:
            for m in meses:
                ano, mes = (int(x) for x in m.split("-"))
                for tentativa in range(1, _MES_TRIES + 1):
                    try:
                        resultados.append(coletar_mes(browser, ano, mes, filtro, max_downloads, out, classes))
                        break
                    except SemPrestacao as e:
                        # as opções do mês chegam por AJAX e às vezes não carregam: só aceita "sem prestação"
                        # depois de repetir o mês (a coleta é idempotente, repetir não custa downloads)
                        if tentativa < _MES_TRIES:
                            log.warning("%s: %s; repetindo o mês", m, e)
                            time.sleep(10)
                            continue
                        log.warning("%s: sem prestação (%s)", m, e)
                        sem_prestacao.append(m)
                    except Exception as e:  # noqa: BLE001 - timeout/queda do e-TCM não deve matar os outros meses
                        if tentativa < _MES_TRIES:
                            log.warning("%s: falha (%s); repetindo o mês", m, repr(e)[:160])
                            time.sleep(30)
                            continue
                        log.error("%s: desistindo após %d tentativas (%s)", m, _MES_TRIES, repr(e)[:160])
        finally:
            browser.close()
    return resultados, sem_prestacao


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="e-TCM: processos de pagamento da CMS (PDFs) -> data/bronze/etcm"
    )
    ap.add_argument("--ano", type=int, help="ano da prestação (ex.: 2025)")
    ap.add_argument("--mes", type=int, help="mês da prestação (1-12)")
    ap.add_argument(
        "--filtro", default=FILTRO_DEFAULT, help="texto do filtro 'Nome do Documento' (padrão VC)"
    )
    ap.add_argument("--max", type=int, default=None, help="máximo de downloads por mês (teste)")
    ap.add_argument(
        "--classes",
        default="",
        help="só baixa documentos cuja classificação começa por um destes prefixos, separados por vírgula "
        "(ex.: PCMGE035,PCMGE048 = folhas sintéticas); combine com --filtro ''",
    )
    ap.add_argument("--todos-meses", action="store_true", help=f"percorre de {MVP_START} até o mês corrente")
    ap.add_argument("--desde", default=MVP_START, help="primeiro mês com --todos-meses (YYYY-MM)")
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.todos_meses:
        meses = list(iter_meses(args.desde, mes_corrente()))
    elif args.ano and args.mes:
        meses = [f"{args.ano:04d}-{args.mes:02d}"]
    else:
        ap.error("informe --ano e --mes, ou --todos-meses")
    classes = tuple(c.strip() for c in args.classes.split(",") if c.strip())
    resultados, sem = coletar(meses, args.filtro, args.max, args.out, classes)
    for r in resultados:
        log.info(
            "%s: listados=%d baixados=%d existentes=%d erros=%d",
            r.mes_prestacao,
            len(r.listados),
            len(r.baixados),
            len(r.existentes),
            len(r.erros),
        )
    if sem:
        log.info("meses sem prestação: %s", ", ".join(sem))
    if not resultados:
        return EXIT_SEM_PRESTACAO
    return 1 if any(r.erros for r in resultados) else 0


if __name__ == "__main__":
    sys.exit(main())
