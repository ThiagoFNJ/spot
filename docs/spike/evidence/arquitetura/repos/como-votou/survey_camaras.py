"""Survey of the Câmaras Municipais of the 92 municipalities of Rio de Janeiro -> data/rj-camaras.csv

    cd backend && .venv/bin/python -m app.etl.survey_camaras            # uses the cache
    cd backend && .venv/bin/python -m app.etl.survey_camaras --refresh  # refetch everything

For each municipality (IBGE list) it looks for the Câmara's site among the usual hosts
(Interlegis *.rj.leg.br first, then cm<x>.rj.gov.br and variants, then OVERRIDES found by hand),
detects the system behind it from HTML signatures, and for SAPL 3 hosts reads the DRF API
(page_size=1) to count what is published. Responses are cached under data/raw/survey/.
Politeness: one request per second per host, 15 s timeouts, a fixed User-Agent.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import threading
import time
import unicodedata
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

import socket

import httpx

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "data" / "raw" / "survey"
OUT = ROOT / "backend" / "data" / "rj-camaras.csv"
UA = "tomoyo-g0v-research (contact: g0v@tomoyo.systems)"
TIMEOUT = 15.0
API_TIMEOUT = 40.0  # counting big tables (votoparlamentar) on the shared Interlegis hosts is slow
IBGE_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/33/municipios"

# Sites found by web search or by DNS-probing abbreviations (2026-10-16) when no standard host answers.
# slug -> homepage url.
OVERRIDES: dict[str, str] = {
    "araruama": "https://www.cmararuama.rj.gov.br",
    "bom-jesus-do-itabapoana": "https://www.cmbji.rj.gov.br",
    "duque-de-caxias": "https://www.cmdc.rj.gov.br",
    "rio-claro": "https://www.cmrc.rj.gov.br",
    "rio-de-janeiro": "https://www.camara.rio",
    "sao-francisco-de-itabapoana": "https://camarasfi.rj.gov.br",
    "sao-joao-da-barra": "https://camarasjb.rj.gov.br",
    "sao-jose-de-uba": "https://www.cmsjuba.rj.gov.br",
    "sao-pedro-da-aldeia": "https://www.cmspa.rj.gov.br",
    "sapucaia": "https://cms.rj.gov.br",
    "tres-rios": "https://cvtr.rj.gov.br",
    "campos-dos-goytacazes": "https://www.camaracampos.rj.gov.br/site/",
    "itatiaia": "https://www.cmi.rj.gov.br",
    "cardoso-moreira": "https://cardosomoreira.rj.leg.br",  # listed by Interlegis; connect timeout 2026-10-16
}
# Known SAPL hosts that are not linked from the homepage nor at sapl.<x>.rj.leg.br. slug -> base url.
SAPL_OVERRIDES: dict[str, str] = {}

COLUMNS = [
    "ibge",
    "municipio",
    "slug",
    "url_camara",
    "sistema",
    "sapl_url",
    "parlamentares",
    "sessoes",
    "presencas",
    "votos_nominais",
    "registros_votacao",
    "materias",
    "autorias",
    "ultima_sessao",
    "ultimo_voto",
    "publica",
    "tls",
    "nota",
    "checado_em",
]

# ---------------------------------------------------------------- dns
# The local resolver answers NXDOMAIN for some live *.rj.leg.br names (seen 2026-10-16), so a failed
# system lookup falls back to DNS-over-HTTPS (Cloudflare, then Google), cached per process.

_sys_getaddrinfo = socket.getaddrinfo
_doh_cache: dict[str, list[str]] = {}
_doh_lock = threading.Lock()


def doh_resolve(host: str) -> list[str]:
    with _doh_lock:
        if host in _doh_cache:
            return _doh_cache[host]
    ips: list[str] = []
    for ep in ("https://cloudflare-dns.com/dns-query", "https://dns.google/resolve"):
        try:
            r = httpx.get(
                ep, params={"name": host, "type": "A"}, headers={"accept": "application/dns-json"}, timeout=10
            )
            j = r.json()
            ips = [a["data"] for a in j.get("Answer", []) if a.get("type") == 1]
            if j.get("Status") in (0, 3):
                break
        except Exception:  # noqa: BLE001
            continue
    with _doh_lock:
        _doh_cache[host] = ips
    return ips


def _getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    try:
        return _sys_getaddrinfo(host, port, family, type, proto, flags)
    except socket.gaierror:
        if not isinstance(host, str) or host.endswith(("cloudflare-dns.com", "dns.google")):
            raise
        ips = doh_resolve(host)
        if not ips:
            raise
        out = []
        for ip in ips:
            out += _sys_getaddrinfo(ip, port, socket.AF_INET, type, proto, flags)
        return out


socket.getaddrinfo = _getaddrinfo

# ---------------------------------------------------------------- http


class Fetcher:
    def __init__(self, refresh: bool = False, retry_errors: bool = False):
        self.refresh = refresh
        self.retry_errors = retry_errors
        self.locks: dict[str, threading.Lock] = {}
        self.last: dict[str, float] = {}
        self.glock = threading.Lock()
        self.insecure_hosts: set[str] = set()
        self.dead_hosts: dict[str, str] = {}
        self.requests = 0
        CACHE.mkdir(parents=True, exist_ok=True)
        warnings.filterwarnings("ignore")

    def _host_lock(self, host: str) -> threading.Lock:
        with self.glock:
            return self.locks.setdefault(host, threading.Lock())

    def get(self, url: str, max_bytes: int = 600_000, timeout: float = TIMEOUT) -> dict:
        """Returns {url, status, final_url, headers, text, insecure, error}. Cached by url."""
        key = hashlib.sha1(url.encode()).hexdigest()
        path = CACHE / f"{key}.json"
        if path.exists() and not self.refresh:
            r = json.loads(path.read_text())
            if self.retry_errors and r["error"]:
                path.unlink()
                return self.get(url, max_bytes, timeout)
            if r.get("insecure"):
                self.insecure_hosts.add(urlparse(url).hostname or "")
            return r
        host = urlparse(url).hostname or ""
        if host in self.dead_hosts:
            return {
                "url": url,
                "status": None,
                "final_url": None,
                "headers": {},
                "text": "",
                "insecure": False,
                "error": self.dead_hosts[host],
            }
        r = self._fetch(
            url, host, verify=host not in self.insecure_hosts, max_bytes=max_bytes, timeout=timeout
        )
        if r["error"] and r["error"].startswith("tls") and host not in self.insecure_hosts:
            r = self._fetch(url, host, verify=False, max_bytes=max_bytes, timeout=timeout)
            if not r["error"] or not r["error"].startswith(("dns", "connect", "tls")):
                self.insecure_hosts.add(host)
        if r["error"] and r["error"].startswith("dns"):
            self.dead_hosts[host] = r["error"]
        if not (r["error"] or "").startswith(
            "dns"
        ):  # NXDOMAIN is cheap to recheck, and the resolver is flaky
            path.write_text(json.dumps(r, ensure_ascii=False))
        return r

    def _fetch(self, url: str, host: str, verify: bool, max_bytes: int, timeout: float) -> dict:
        lock = self._host_lock(host)
        with lock:
            wait = self.last.get(host, 0) + 1.0 - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            res = {
                "url": url,
                "status": None,
                "final_url": None,
                "headers": {},
                "text": "",
                "insecure": not verify,
                "error": None,
            }
            try:
                self.requests += 1
                with httpx.Client(
                    verify=verify,
                    timeout=timeout,
                    follow_redirects=True,
                    headers={"User-Agent": UA, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"},
                ) as c:
                    with c.stream("GET", url) as resp:
                        buf = b""
                        for chunk in resp.iter_bytes():
                            buf += chunk
                            if len(buf) > max_bytes:
                                break
                        res["status"] = resp.status_code
                        res["final_url"] = str(resp.url)
                        res["headers"] = {
                            k.lower(): v
                            for k, v in resp.headers.items()
                            if k.lower()
                            in (
                                "server",
                                "x-powered-by",
                                "content-type",
                                "via",
                                "x-generator",
                                "set-cookie",
                                "x-frame-options",
                            )
                        }
                        enc = resp.encoding or "utf-8"
                        try:
                            res["text"] = buf.decode(enc, errors="replace")
                        except LookupError:
                            res["text"] = buf.decode("utf-8", errors="replace")
            except httpx.ConnectError as e:
                msg = str(e)
                low = msg.lower()
                if "certificate" in low or "ssl" in low or "tls" in low or "handshake" in low:
                    res["error"] = "tls: " + msg[:200]
                elif (
                    "name or service" in low
                    or "nodename" in low
                    or "name resolution" in low
                    or "errno -2" in low
                    or "errno -5" in low
                    or "no address" in low
                ):
                    res["error"] = "dns: " + msg[:200]
                else:
                    res["error"] = "connect: " + msg[:200]
            except httpx.TimeoutException as e:
                res["error"] = "timeout: " + str(e)[:200]
            except Exception as e:  # noqa: BLE001 - survey: record anything
                msg = f"{type(e).__name__}: {e}"
                low = msg.lower()
                res["error"] = ("tls: " if ("ssl" in low or "certificate" in low) else "other: ") + msg[:200]
            finally:
                self.last[host] = time.monotonic()
            return res


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


# ---------------------------------------------------------------- discovery

PARKED = re.compile(
    r"(domain (is )?for sale|parked|registro\.br/.*dominio|este dom[ií]nio|hostgator.*default|"
    r"index of /|it works!|apache2 (ubuntu|debian) default|welcome to nginx)",
    re.I,
)


def candidate_hosts(slug: str) -> list[str]:
    x = slug.replace("-", "")
    return [
        f"https://{x}.rj.leg.br",
        f"https://www.{x}.rj.leg.br",
        f"https://www.cm{x}.rj.gov.br",
        f"https://cm{x}.rj.gov.br",
        f"https://www.camara{x}.rj.gov.br",
        f"https://camara{x}.rj.gov.br",
        f"https://www.camarade{x}.rj.gov.br",
        f"https://camarade{x}.rj.gov.br",
        f"https://www.camara{x}.com.br",
        f"https://{x}.camarasempapel.com.br",
    ]


JS_REDIRECT = re.compile(
    r"""(?:window\.location(?:\.href)?\s*=\s*|location\.replace\(\s*|"""
    r"""http-equiv=["']?refresh["']?[^>]*url=)["']?([^"'>;)\s]+)""",
    re.I,
)


def page_ok(r: dict) -> bool:
    if r["error"] or r["status"] is None or r["status"] >= 400:
        return False
    t = r["text"]
    if len(t) < 300 or PARKED.search(t[:5000]):
        return False
    return True


def follow_soft_redirect(f: Fetcher, r: dict) -> dict:
    """Small pages that only redirect by script or meta refresh."""
    for _ in range(2):
        if r["error"] or r["status"] != 200 or len(r["text"]) > 3000:
            return r
        m = JS_REDIRECT.search(r["text"])
        if not m:
            return r
        r = f.get(urljoin(r["final_url"] or r["url"], m.group(1)))
    return r


def find_site(f: Fetcher, slug: str) -> tuple[str | None, dict | None, list[str]]:
    """First candidate that serves a real page; failing that, one that answers but blocks us
    (403 / redirect loop), returned with r["blocked"] set."""
    tried = []
    urls = [OVERRIDES[slug]] if slug in OVERRIDES else []
    urls += candidate_hosts(slug)
    blocked = None
    for u in urls:
        r = follow_soft_redirect(f, f.get(u + ("/" if urlparse(u).path == "" else "")))
        tried.append(f"{u}:{r['status'] or (r['error'] or '')[:12]}")
        if page_ok(r):
            return u, r, tried
        if r["error"] and r["error"].startswith(("connect", "timeout", "tls")) and u.startswith("https://"):
            r2 = follow_soft_redirect(
                f, f.get("http://" + u[len("https://") :] + ("/" if urlparse(u).path == "" else ""))
            )
            if page_ok(r2):
                return "http://" + u[len("https://") :], r2, tried
        if blocked is None and (
            r["status"] in (401, 403, 429, 503) or "TooManyRedirects" in (r["error"] or "")
        ):
            blocked = (u, dict(r, blocked=r["status"] or "redirect loop"))
    if blocked:
        return blocked[0], blocked[1], tried
    return None, None, tried


# ---------------------------------------------------------------- detection

# Legislative-process systems, recognised by text or by the hosts the homepage links to.
LEGIS_SIGNATURES = [
    ("camara-sem-papel", re.compile(r"c[aâ]mara\s*sem\s*papel|camarasempapel|//sempapel\.", re.I)),
    ("siscam", re.compile(r"siscam", re.I)),
    ("jcsoftwares", re.compile(r"jcsoftwares|jc\s*softwares", re.I)),
    ("ip-camara", re.compile(r"ipcamara|instarsistemas|//[a-z0-9.\-]*instar\.", re.I)),
    ("betha", re.compile(r"betha[^\"'<>\s]*/(?:processo|legisla|sapl)|legislativo\.betha", re.I)),
    (
        "processo-legislativo-eletronico",
        re.compile(r"//spl\.[a-z0-9.\-]+|processo\s+legislativo\s+eletr[oô]nico", re.I),
    ),
]
# Website platforms / vendors.
SITE_SIGNATURES = [
    ("npi-brasil", re.compile(r'name="author"\s+content="NPI Brasil"', re.I)),
    ("mtw-portalgov", re.compile(r'ng-app="portalgovApp"|name="author"\s+content="MTW"', re.I)),
]
# Transparency portals: recorded in the note only.
TRANSP = re.compile(
    r"//([a-z0-9.\-]*(?:portaltp\.com\.br|betha\.cloud|transpgp\.com\.br|portaldatransparencia\.com\.br|"
    r"amazonsistemas\.com\.br|primaxonline\.com\.br|oppcloud\.com\.br|govbr\.cloud))",
    re.I,
)

VENDOR_HINT = re.compile(
    r"(?:desenvolvid[oa]\s+por|developed\s+by|powered\s+by|criad[oa]\s+por)\s*:?\s*"
    r"(?:<[^>]+>\s*)*([A-Za-zÀ-ú][^<\n\"]{2,40})",
    re.I,
)


def detect_vendor(html: str, headers: dict) -> tuple[str, str]:
    """Returns (sistema, note). Legislative system first, website platform otherwise."""
    low = html.lower()
    gens = re.findall(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)', html, re.I)
    gen_s = next(
        (g for g in gens if re.search(r"wordpress|joomla|drupal|plone|wix", g, re.I)), gens[0] if gens else ""
    )
    gen_s = gen_s.strip()[:40]
    visible = re.sub(
        r"<script.*?</script>|<style.*?</style>|<meta[^>]*>|<link[^>]*>", " ", html, flags=re.S | re.I
    )
    hint = VENDOR_HINT.search(visible)
    hint_s = re.sub(r"\s+", " ", hint.group(1)).strip() if hint else ""
    transp = sorted({m.lower() for m in TRANSP.findall(html)})
    notes = [
        f"generator={gen_s}" if gen_s else "",
        f"credito={hint_s}" if hint_s else "",
        f"transparência={','.join(transp[:2])}" if transp else "",
    ]
    for name, rx in LEGIS_SIGNATURES:
        m = rx.search(html)
        if m:
            notes.append(f"legis={m.group(0).lstrip('/')[:40]}")
            return name, "; ".join(x for x in notes if x)
    note = "; ".join(x for x in notes if x)
    if "portalmodelo" in low or ("interlegis" in low and ("plone" in low or "portal-column" in low)):
        return "portal-modelo", note
    if "plone" in gen_s.lower():
        return "plone", note
    for name, rx in SITE_SIGNATURES:
        if rx.search(html):
            return name, note
    if "joomla" in " ".join(gens).lower() or "/media/jui/" in low:
        return "joomla", note
    if "wp-content" in low or "wordpress" in gen_s.lower():
        return "wordpress", note
    if "drupal" in gen_s.lower() or "drupal.settings" in low:
        return "drupal", note
    if "wix.com" in low or "wixstatic" in low:
        return "wix", note
    if len(html) < 4000 and re.search(r'<script[^>]+type="module"|id="(?:root|app)"', html):
        return "spa", note
    return "outro", note


SAPL_LINK = re.compile(r"https?://[a-z0-9.\-]*sapl[a-z0-9.\-]*(?::\d+)?(?:/sapl)?", re.I)


def sapl_candidates(slug: str, home_url: str | None, html: str) -> list[str]:
    x = slug.replace("-", "")
    c = []
    if slug in SAPL_OVERRIDES:
        c.append(SAPL_OVERRIDES[slug])
    for m in SAPL_LINK.findall(html or ""):
        u = m.rstrip("/")
        if u.endswith("/sapl"):
            u = u[:-5]
        if u not in c:
            c.append(u)
    for u in (f"https://sapl.{x}.rj.leg.br",):
        if u not in c:
            c.append(u)
    if home_url:
        base = f"{urlparse(home_url).scheme}://{urlparse(home_url).netloc}"
        if base not in c:
            c.append(base)
    return c


def jload(r: dict):
    if r["error"] or r["status"] != 200:
        return None
    try:
        return json.loads(r["text"])
    except Exception:  # noqa: BLE001
        return None


def total_of(j) -> int | None:
    if not isinstance(j, dict):
        return None
    p = j.get("pagination")
    if isinstance(p, dict):
        for k in ("total_entries", "count", "total"):
            if k in p:
                return p[k]
    if "count" in j:
        return j["count"]
    return None


def results_of(j) -> list:
    if isinstance(j, dict):
        return j.get("results") or []
    return []


ENDPOINTS = {
    "parlamentares": ["/api/parlamentares/parlamentar/"],
    "sessoes": ["/api/sessao/sessaoplenaria/"],
    "presencas": [
        "/api/sessao/sessaoplenariapresenca/",
        "/api/sessao/presencasessao/",
        "/api/sessao/sessaopresenca/",
    ],
    "votos_nominais": ["/api/sessao/votoparlamentar/"],
    "registros_votacao": ["/api/sessao/registrovotacao/"],
    "materias": ["/api/materia/materialegislativa/"],
    "autorias": ["/api/materia/autoria/"],
}


def probe_sapl3(f: Fetcher, base: str) -> dict | None:
    j = jload(f.get(base + "/api/parlamentares/parlamentar/?page_size=1", timeout=API_TIMEOUT))
    if total_of(j) is None:
        return None
    out = {"sapl_url": base, "parlamentares": total_of(j), "paths": []}
    for col, paths in ENDPOINTS.items():
        if col == "parlamentares":
            continue
        out[col] = None
        for p in paths:
            r = f.get(base + p + "?page_size=1", timeout=API_TIMEOUT)
            t = total_of(jload(r))
            if t is not None:
                out[col] = t
                if p != paths[0]:
                    out["paths"].append(p)
                break
            out.setdefault("http_" + col, r["status"] or (r["error"] or "")[:20])
    # django-filter's OrderingFilter takes "o", not DRF's "ordering" (ignored silently).
    # Sessions can be scheduled ahead, so take the latest one not after today.
    if out.get("sessoes"):
        j = jload(
            f.get(base + "/api/sessao/sessaoplenaria/?page_size=20&o=-data_inicio", timeout=API_TIMEOUT)
        )
        datas = sorted((x.get("data_inicio") or "" for x in results_of(j)), reverse=True)
        today = date.today().isoformat()
        past = [d for d in datas if d and d <= today]
        if past:
            out["ultima_sessao"] = past[0]
        if datas and datas[0] > today:
            out["sessao_agendada"] = datas[0]
    # data_hora of a vote is when it was recorded in the panel; rows migrated from SAPL 2.5 carry the
    # migration timestamp instead.
    if out.get("votos_nominais"):
        j = jload(f.get(base + "/api/sessao/votoparlamentar/?page_size=1&o=-id", timeout=API_TIMEOUT))
        res = results_of(j)
        if res and res[0].get("data_hora"):
            out["ultimo_voto"] = res[0]["data_hora"][:10]
    return out


def probe_sapl25(f: Fetcher, base: str, home_html: str) -> bool:
    """SAPL 2.5 lives on Zope under /sapl/. Catch-all SPAs answer 200 to any path, so require Zope or
    SAPL 2.5 markup that the homepage itself does not have."""
    for p in ("/sapl/consultas/parlamentar/parlamentar_index_html", "/sapl/"):
        r = f.get(base + p)
        if r["status"] != 200 or r["text"][:2000] == home_html[:2000]:
            continue
        zope = "zope" in json.dumps(r["headers"]).lower()
        if zope or re.search(r"sapl_documentos|consultas/parlamentar|generico/", r["text"]):
            return True
    return False


LEVEL_WORDS = [
    (
        "votos",
        re.compile(
            r"vota[cç][aã]o\s+nominal|votos?\s+nominai?s|votos?\s+dos\s+vereadores|painel\s+de\s+vota|"
            r"resultado\s+(das?\s+)?vota",
            re.I,
        ),
    ),
    (
        "presenca",
        re.compile(
            r"presen[cç]as?\s+(dos\s+vereadores|em\s+plen|nas\s+sess)|lista\s+de\s+presen|"
            r"frequ[eê]ncia\s+(dos\s+)?vereadores|controle\s+de\s+presen",
            re.I,
        ),
    ),
    (
        "proposicoes",
        re.compile(
            r"proposi[cç][oõ]es|projetos?\s+de\s+lei|mat[eé]rias?\s+legislativ|"
            r"processo\s+legislativo|indica[cç][oõ]es|requerimentos",
            re.I,
        ),
    ),
    ("pdf", re.compile(r"\.pdf\b|atas?\s+(das\s+)?sess|pautas?", re.I)),
]


def level_from_html(html: str) -> str:
    for lvl, rx in LEVEL_WORDS:
        if rx.search(html):
            return lvl
    return "nada"


# ---------------------------------------------------------------- per municipality


def survey_one(f: Fetcher, m: dict, today: str) -> dict:
    nome = m["nome"]
    slug = slugify(nome)
    row = {c: "" for c in COLUMNS}
    row.update(ibge=m["id"], municipio=nome, slug=slug, checado_em=today)
    notes = []
    url, home, tried = find_site(f, slug)
    html = home["text"] if home else ""
    if url:
        final = home.get("final_url") or url
        row["url_camara"] = url if ("acl_users" in final or "login" in final or slug in OVERRIDES) else final
        if re.search(r"<title>\s*Bot Verification|cf-chl|Just a moment", html[:3000]):
            notes.append("home atrás de verificação anti-robô")
        if "hostgator" in html.lower() and home.get("blocked"):
            notes.append("página padrão da hospedagem")
        sistema, vnote = detect_vendor(html, home["headers"])
        if home.get("blocked") or "anti-robô" in " ".join(notes):
            sistema = "inacessivel"
        if vnote:
            notes.append(vnote)
        if home.get("blocked"):
            notes.append(f"home responde {home['blocked']} ao robô")
            if "cloudflare" in html.lower() or "cf-chl" in html:
                notes.append("cloudflare")
        if slug in OVERRIDES:
            notes.append("url por busca manual")
    elif slug in OVERRIDES:
        row["url_camara"] = OVERRIDES[slug]
        sistema = "inacessivel"
        notes.append("site conhecido não respondeu: " + tried[0].split(":", 2)[-1])
    else:
        sistema = "nenhum"
        notes.append("sem site nos hosts padrão")

    # SAPL 3
    sapl = None
    empty = []
    for base in sapl_candidates(slug, row["url_camara"] or None, html):
        sapl = probe_sapl3(f, base)
        if sapl and not sapl.get("parlamentares") and not sapl.get("materias"):
            empty.append(base)
            sapl = None
        if sapl:
            break
    if empty:
        notes.append("SAPL 3 vazio em " + ",".join(urlparse(e).hostname for e in empty))
    if sapl:
        sistema_site = sistema
        sistema = "sapl3"
        if (
            sistema_site not in ("nenhum", "outro")
            and urlparse(sapl["sapl_url"]).netloc != urlparse(row["url_camara"]).netloc
        ):
            notes.append(f"site={sistema_site}")
        if not row["url_camara"]:
            row["url_camara"] = sapl["sapl_url"]
        for col in (
            "sapl_url",
            "parlamentares",
            "sessoes",
            "presencas",
            "votos_nominais",
            "registros_votacao",
            "materias",
            "autorias",
            "ultima_sessao",
            "ultimo_voto",
        ):
            v = sapl.get(col)
            row[col] = "" if v is None else v
        if sapl["paths"]:
            notes.append("paths=" + ",".join(sapl["paths"]))
        miss = [k[5:] + "=" + str(v) for k, v in sapl.items() if k.startswith("http_")]
        if miss:
            notes.append("falhou " + " ".join(miss))
        if sapl.get("sessao_agendada"):
            notes.append(f"sessão agendada {sapl['sessao_agendada']}")
        if (sapl.get("votos_nominais") or 0) > 0:
            row["publica"] = "votos"
        elif (sapl.get("presencas") or 0) > 0:
            row["publica"] = "presenca"
        elif (sapl.get("materias") or 0) > 0:
            row["publica"] = "proposicoes"
        else:
            row["publica"] = "nada"
    else:
        base = row["url_camara"]
        if base:
            b = f"{urlparse(base).scheme}://{urlparse(base).netloc}"
            if probe_sapl25(f, b, html):
                notes.append(f"site={sistema}")
                sistema = "sapl25"
                row["sapl_url"] = b + "/sapl"
        if sistema in ("inacessivel", "nenhum"):
            row["publica"] = "desconhecido"
        else:
            row["publica"] = level_from_html(html)
            if row["publica"] == "votos":  # a link to a voting panel is not a machine-readable vote record
                notes.append("home menciona votação")
                row["publica"] = level_from_html(LEVEL_WORDS[0][1].sub(" ", html))
            if row["publica"] == "nada":
                row["publica"] = "desconhecido"
            notes.append("publica estimada pela home")

    hosts = {urlparse(x).hostname for x in (row["url_camara"], row["sapl_url"]) if x}
    if sistema in ("inacessivel", "nenhum") and not row["sapl_url"]:
        hosts = set()
    row["tls"] = (
        ""
        if not hosts
        else "inválido"
        if hosts & f.insecure_hosts
        else (
            "ok"
            if any(str(x).startswith("https") for x in (row["url_camara"], row["sapl_url"]))
            else ("http" if url else "")
        )
    )
    if slug == "rio-de-janeiro":
        notes.insert(0, "capital, adaptador próprio")
        row["publica"] = "votos"  # nominal votes and presence are already ingested by the Rio adapter
        notes.append(f"site={sistema}")
        sistema = "proprio (Domino)"
    row["sistema"] = sistema
    row["nota"] = "; ".join(n.replace("\n", " ") for n in notes)[:400]
    print(f"{slug:32} {sistema:18} {row['publica']:12} {row['url_camara']}", flush=True)
    return row


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--retry-errors", action="store_true", help="refetch cached responses that were errors")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--workers", type=int, default=12)
    a = ap.parse_args(argv)
    t0 = time.time()
    f = Fetcher(refresh=a.refresh, retry_errors=a.retry_errors)
    r = f.get(IBGE_URL, max_bytes=5_000_000)
    munis = json.loads(r["text"])
    munis = [{"id": str(m["id"]), "nome": m["nome"]} for m in munis]
    assert len(munis) == 92, len(munis)
    if a.only:
        munis = [m for m in munis if slugify(m["nome"]) in a.only]
    today = date.today().isoformat()
    with ThreadPoolExecutor(a.workers) as ex:
        rows = list(ex.map(lambda m: survey_one(f, m, today), munis))
    rows.sort(key=lambda r: r["municipio"])
    if not a.only:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {OUT}", file=sys.stderr)
    print(f"{len(rows)} municípios, {f.requests} requests, {time.time() - t0:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
