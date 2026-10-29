"""Cliente HTTP para os apps ScriptCase da CMS.

Cobre o fluxo validado em docs/HANDOVER.md §2.3 com as correções de
docs/HANDOVER-adendo-2026-10-27.md:

1. GET da raiz do app -> captura `script_case_init` (muda a cada GET; o estado de filtro
   fica indexado por ele dentro da sessão PHP, então nunca misturar inits).
2. POST index.php `nmgp_opcao=ajax_navigate&opc=interativ_search&parm=...` -> aplica um filtro
   (cumulativo). O corpo vai cru em UTF-8, como o JS da página faz.
3. POST <app>_export_ctrl.php com todos os campos do form Fexport e `SC_module_export=grid`
   (vazio reproduz o fatal error `Calc_resumo_sc_free_group_by`) -> `pbmd5`.
4. GET index.php?...&pbmd5= -> bloqueia até gerar; corpo vazio = sucesso, corpo não vazio = erro PHP.
5. GET /producao/tmp/sc_pb_<md5>.txt -> JSON com `link` e `complete`; polling com timeout.
6. GET do link -> CSV ISO-8859-1, `;`, aspas, CRLF.

Alternativa ao export: `dump_grid` (POST `muda_qt_linhas`) devolve o HTML da grade inteira.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx

from spot.config import LEG_SYS_BASE, LEG_SYS_HOST, MIN_GAP_SECONDS, USER_AGENT

log = logging.getLogger(__name__)

RE_INIT = re.compile(r'name="script_case_init"\s+value="(\d+)"')
RE_INIT_JS = re.compile(r"script_case_init=(\d+)")
# Rodapé `[1 a 43 de 23472]`; no prop_interna (sys.inf.br) os números vêm em <span>:
# `[1 a <span class='sm_counter_final'>20</span> de <span class='sm_counter_total'>31776</span>]`.
RE_TOTAL = re.compile(r"\[(\d+) a (?:<[^>]*>)?(\d+)(?:</[^>]*>)? de (?:<[^>]*>)?(\d+)(?:</[^>]*>)?\]")
RE_PBMD5 = re.compile(r"pbmd5=([0-9a-f]{32})")
# URL do arquivo de progresso dentro do JS de export_ctrl (`url: "/p/tmp/sc_pb_<md5>.txt"`);
# o diretório tmp varia por host (/producao/tmp no 45.4.247.157, /p/tmp no cmsalvador.sys.inf.br).
RE_PB_URL = re.compile(r'url:\s*"([^"]*sc_pb_[0-9a-f]{32}\.txt)"')
RE_IFRAME = re.compile(r'<iframe[^>]*src="([^"]+)"', re.I)
RE_FATAL = re.compile(r"Fatal error</b>:\s*(.*?)<br", re.S)


class ScriptCaseError(RuntimeError):
    pass


# Último request por host (netloc), compartilhado entre todas as instâncias de Client do processo.
_HOST_LAST: dict[str, float] = {}
_HOST_LOCK = threading.Lock()


@dataclass
class Response:
    url: str
    status: int
    content: bytes
    seconds: float
    method: str = "GET"
    body: str | None = None

    @property
    def text(self) -> str:
        return self.content.decode("latin-1")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    def fatal(self) -> str | None:
        m = RE_FATAL.search(self.text)
        return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def grid_total(text: str) -> int | None:
    """Total de linhas da grade a partir do rodapé `[a a b de N]`."""
    m = RE_TOTAL.search(text)
    return int(m.group(3)) if m else None


@dataclass
class Client:
    """Uma instância = uma sessão PHP (cookie jar próprio). Rate limit compartilhado por host."""

    host: str = LEG_SYS_HOST
    min_gap: float = MIN_GAP_SECONDS
    timeout: float = 120.0
    retries: int = 3
    _http: httpx.Client = field(init=False, repr=False)
    requests_made: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._http = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9"},
            follow_redirects=True,
            timeout=self.timeout,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _wait(self, url: str) -> None:
        """Garante `min_gap` entre requests ao mesmo host, mesmo entre instâncias distintas de Client."""
        host = urlsplit(url).netloc or self.host
        with _HOST_LOCK:
            gap = time.monotonic() - _HOST_LAST.get(host, 0.0)
            if gap < self.min_gap:
                time.sleep(self.min_gap - gap)
            _HOST_LAST[host] = time.monotonic()

    def request(
        self,
        method: str,
        url: str,
        *,
        content: bytes | None = None,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Response:
        last_exc: Exception | None = None
        for attempt in range(1, self.retries + 1):
            self._wait(url)
            t0 = time.monotonic()
            try:
                r = self._http.request(
                    method, url, content=content, data=data, headers=headers, timeout=timeout or self.timeout
                )
                self.requests_made += 1
                el = time.monotonic() - t0
                log.debug("%s %s -> %s %dB %.2fs", method, url, r.status_code, len(r.content), el)
                if r.status_code >= 500:
                    raise ScriptCaseError(f"HTTP {r.status_code} em {url}")
                body = content.decode("utf-8", "replace") if content else (urlencode(data) if data else None)
                return Response(url, r.status_code, r.content, el, method, body)
            except (httpx.HTTPError, ScriptCaseError) as exc:
                last_exc = exc
                log.warning("tentativa %d/%d falhou: %s %s: %s", attempt, self.retries, method, url, exc)
                time.sleep(2**attempt)
        raise ScriptCaseError(f"falhou após {self.retries} tentativas: {method} {url}") from last_exc

    # ---- fluxo ScriptCase -------------------------------------------------------------------

    def app_url(self, app: str, base: str = LEG_SYS_BASE) -> str:
        return f"{base}/{app}/"

    def open_app(self, app: str, base: str = LEG_SYS_BASE) -> tuple[str, Response]:
        """GET da raiz do app. Devolve (script_case_init, resposta)."""
        resp = self.request("GET", self.app_url(app, base))
        inits = set(RE_INIT.findall(resp.text)) or set(RE_INIT_JS.findall(resp.text))
        if len(inits) != 1:
            raise ScriptCaseError(f"script_case_init ambíguo ou ausente em {app}: {sorted(inits)}")
        init = inits.pop()
        log.info("%s aberto: init=%s total=%s", app, init, grid_total(resp.text))
        return init, resp

    def navigate(self, app: str, init: str, parm: str, base: str = LEG_SYS_BASE) -> Response:
        """Aplica um filtro da busca interativa (cumulativo dentro do mesmo init).

        `parm` no formato `{campo}__DL__{label}__DL__{tipo}__DL__{valor}##@@{exibido}__DL__S`.
        Ex.: `pre_pre_data_presenca__DL__Mês e Ano__DL__dh__DL__2025-03##@@03/2025 __DL__S`
        (atenção ao espaço após `03/2025`).
        """
        parm = parm.replace("+", "__NM_PLUS__").replace("&", "__NM_AMP__").replace("%", "__NM_PRC__")
        body = f"nmgp_opcao=ajax_navigate&script_case_init={init}&opc=interativ_search&parm={parm}"
        return self.request(
            "POST",
            self.app_url(app, base) + "index.php",
            content=body.encode("utf-8"),
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
            },
        )

    def filter_total(self, app: str, init: str, parm: str, base: str = LEG_SYS_BASE) -> int:
        resp = self.navigate(app, init, parm, base)
        total = grid_total(resp.text)
        if total is None:
            raise ScriptCaseError(f"filtro sem rodapé de total em {app}: {parm!r}")
        return total

    def export_csv(
        self,
        app: str,
        init: str,
        *,
        base: str = LEG_SYS_BASE,
        header: bool = True,
        poll_timeout: float = 120.0,
    ) -> tuple[Response, dict[str, Any]]:
        """Export CSV server-side do estado atual da grade. Devolve (resposta do CSV, json do progresso)."""
        fields = {
            "nmgp_opcao": "csv",
            "nmgp_tp_xls": "",
            "nmgp_tot_xls": "",
            "SC_module_export": "grid",  # vazio => fatal error Calc_resumo_sc_free_group_by
            "nm_delim_line": "1",
            "nm_delim_col": "1",
            "nm_delim_dados": "1",
            "nm_label_csv": "S" if header else "N",
            "nm_xml_tag": "",
            "nm_xml_label": "",
            "nm_json_format": "",
            "nm_json_label": "",
            "nmgp_password": "",
            "script_case_init": init,
        }
        url = self.app_url(app, base)
        ctrl = self.request("POST", url + f"{app}_export_ctrl.php", data=fields)
        m = RE_PBMD5.search(ctrl.text)
        if not m:
            raise ScriptCaseError(f"export_ctrl sem pbmd5 em {app}: {ctrl.fatal() or ctrl.text[:200]!r}")
        md5 = m.group(1)
        pb_m = RE_PB_URL.search(ctrl.text)
        pb_url = self.host + pb_m.group(1) if pb_m else f"{self.host}/producao/tmp/sc_pb_{md5}.txt"
        iframe = RE_IFRAME.search(ctrl.text)
        gen_url = (
            url + iframe.group(1)
            if iframe and "pbmd5" in iframe.group(1)
            else url + "index.php?" + urlencode({**fields, "pbmd5": md5})
        )
        gen = self.request("GET", gen_url, timeout=max(self.timeout, poll_timeout))
        if gen.content.strip():
            raise ScriptCaseError(f"geração do export falhou em {app}: {gen.fatal() or gen.text[:300]!r}")
        deadline = time.monotonic() + poll_timeout
        progress: dict[str, Any] = {}
        while time.monotonic() < deadline:
            pb = self.request("GET", pb_url, timeout=30)
            try:
                progress = json.loads(pb.text)
            except json.JSONDecodeError:
                progress = {}
            if progress.get("complete") and progress.get("link"):
                break
            time.sleep(1)
        else:
            raise ScriptCaseError(f"export não completou em {poll_timeout}s em {app}: {progress}")
        csv = self.request("GET", self.host + progress["link"])
        return csv, progress

    def dump_grid(self, app: str, init: str, rows: int = 30000, base: str = LEG_SYS_BASE) -> Response:
        """POST muda_qt_linhas: HTML da grade inteira (ou filtrada) numa página só."""
        body = f"script_case_init={init}&nmgp_opcao=muda_qt_linhas&nmgp_quant_linhas={rows}"
        return self.request(
            "POST",
            self.app_url(app, base) + "index.php",
            content=body.encode("ascii"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )


# ---- bronze helpers --------------------------------------------------------------------------


def write_bronze(dir_: Path, name: str, resp: Response, params: dict[str, Any] | None = None) -> Path:
    """Grava o bruto (imutável) e uma linha no manifest.jsonl. Devolve o caminho."""
    dir_.mkdir(parents=True, exist_ok=True)
    path = dir_ / name
    if path.exists():
        log.info("já existe, não sobrescrevo: %s", path)
        return path
    path.write_bytes(resp.content)
    entry = {
        "file": name,
        "url": resp.url,
        "method": resp.method,
        "body": resp.body,
        "params": params or {},
        "status": resp.status,
        "bytes": len(resp.content),
        "sha256": resp.sha256,
        "seconds": round(resp.seconds, 3),
        "coletado_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    with (dir_ / "manifest.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def bronze_exists(dir_: Path, name: str) -> bool:
    return (dir_ / name).exists()
