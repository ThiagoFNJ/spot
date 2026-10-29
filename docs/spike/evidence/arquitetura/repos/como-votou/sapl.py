"""Leitor genérico do SAPL 3 (Interlegis): um adaptador para todas as câmaras que o usam.

A API pública do SAPL 3 (Django REST Framework) expõe as tabelas do sistema em /api/<app>/<modelo>/,
paginadas (page_size até 100) e ordenáveis por ?o=<campo>. Este módulo lê:

  parlamentares/legislatura, parlamentar, mandato, filiacao, partido
  sessao/sessaoplenaria, sessaoplenariapresenca, registrovotacao, votoparlamentar, tiporesultadovotacao
  materia/materialegislativa (por ano, desde 2021), tipomaterialegislativa; base/autor, tipoautor

Educado: uma requisição por segundo por host, User-Agent com contato, três tentativas com espera.
Incremental: as tabelas grandes (votos, registros, presença, sessões) são lidas de trás para frente
(?o=-id) até a primeira página sem nada novo; as matérias, por ano, relendo só o ano corrente e o
anterior; as tabelas pequenas são relidas inteiras. Tudo fica em data/rjm/sapl/<slug>.json.

    python -m app.etl.sapl --slug petropolis --base https://sapl.petropolis.rj.leg.br
    python -m app.etl.sapl --all            # todas as câmaras com sistema sapl3 em backend/data/rj-camaras.csv

`merge_into(snapshot, tables)` converte as tabelas no formato de snapshot do resto do ETL
(vereadores, votações com votos, presença mensal, proposições) e liga os parlamentares do SAPL aos
vereadores do TSE por nome normalizado e partido.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import difflib
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

from .. import config
from ..names import norm

SAPL_DIR = config.DATA_DIR / "rjm" / "sapl"
SURVEY_CSV = config.BACKEND_DIR / "data" / "rj-camaras.csv"
FIRST_YEAR = 2021
PAGE = 100

# Campos guardados de cada tabela (o resto da resposta é descartado).
KEEP = {
    "parlamentares/legislatura": ("numero", "data_inicio", "data_fim"),
    "parlamentares/parlamentar": ("nome_completo", "nome_parlamentar", "ativo", "email", "fotografia"),
    "parlamentares/mandato": (
        "parlamentar",
        "legislatura",
        "data_inicio_mandato",
        "data_fim_mandato",
        "titular",
    ),
    "parlamentares/filiacao": ("parlamentar", "partido", "data", "data_desfiliacao"),
    "parlamentares/partido": ("sigla",),
    "sessao/tiporesultadovotacao": ("nome", "natureza"),
    "materia/tipomaterialegislativa": ("sigla", "descricao"),
    "base/tipoautor": ("descricao",),
    "base/autor": ("nome", "tipo", "object_id"),
    "sessao/sessaoplenaria": ("data_inicio", "numero", "tipo", "legislatura", "__str__"),
    "sessao/sessaoplenariapresenca": ("sessao_plenaria", "parlamentar"),
    "sessao/registrovotacao": (
        "numero_votos_sim",
        "numero_votos_nao",
        "numero_abstencoes",
        "tipo_resultado_votacao",
        "materia",
        "data_hora",
        "__str__",
        "ordem",
        "expediente",
    ),
    "sessao/votoparlamentar": ("votacao", "parlamentar", "voto"),
    "materia/materialegislativa": ("tipo", "numero", "ano", "ementa", "data_apresentacao", "autores"),
}
SMALL = (
    "parlamentares/legislatura",
    "parlamentares/parlamentar",
    "parlamentares/mandato",
    "parlamentares/filiacao",
    "parlamentares/partido",
    "sessao/tiporesultadovotacao",
    "materia/tipomaterialegislativa",
    "base/tipoautor",
    "base/autor",
)
APPEND = (
    "sessao/sessaoplenaria",
    "sessao/sessaoplenariapresenca",
    "sessao/registrovotacao",
    "sessao/votoparlamentar",
)


def log(slug: str, *a: object) -> None:
    print(f"[sapl {slug}]", *a, file=sys.stderr, flush=True)


class Sapl:
    def __init__(self, base: str, slug: str, delay_s: float = config.REQUEST_DELAY_S) -> None:
        self.base = base.rstrip("/")
        self.slug = slug
        self.delay_s = delay_s
        self.requests = 0
        self._last = 0.0
        self.verify = True
        self.total: int | None = None
        self.client = httpx.Client(
            headers={"User-Agent": config.USER_AGENT, "Accept": "application/json"},
            timeout=60,
            follow_redirects=True,
        )

    def get(self, path: str, params: dict, allow_404: bool = True) -> dict:
        url = f"{self.base}/api/{path}/"
        for attempt in range(3):
            wait = self.delay_s - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            self.requests += 1
            try:
                r = self.client.get(url, params=params)
                if r.status_code == 404 and allow_404:
                    return {"results": [], "pagination": {}}
                r.raise_for_status()
                return r.json()
            except httpx.ConnectError as exc:
                if "CERTIFICATE" in str(exc).upper() and self.verify:
                    self.verify = False
                    self.client = httpx.Client(
                        headers=self.client.headers, timeout=60, follow_redirects=True, verify=False
                    )
                    log(self.slug, "certificado TLS inválido; seguindo sem verificação")
                    continue
                if attempt == 2:
                    raise
            except (httpx.HTTPError, json.JSONDecodeError):
                if attempt == 2:
                    raise
            time.sleep(5 * (attempt + 1))
        raise RuntimeError("unreachable")

    def pages(self, path: str, params: dict | None = None):
        """Páginas de uma tabela; self.total guarda o total_entries anunciado na primeira."""
        page = 1
        while True:
            # um 404 no meio da paginação é falha do servidor, não fim da tabela
            data = self.get(path, {**(params or {}), "page_size": PAGE, "page": page}, allow_404=page == 1)
            if page == 1:
                self.total = (data.get("pagination") or {}).get("total_entries")
            yield data.get("results", [])
            nxt = (data.get("pagination") or {}).get("next_page")
            if not nxt:
                return
            page = nxt


def _slim(path: str, rec: dict) -> dict:
    return {k: rec.get(k) for k in KEEP[path]}


def collect(base: str, slug: str, *, full: bool = False) -> dict:
    """Lê (ou atualiza) as tabelas de uma câmara; devolve o dicionário salvo em data/rjm/sapl/<slug>.json."""
    path_out = SAPL_DIR / f"{slug}.json"
    old = json.loads(path_out.read_text(encoding="utf-8")) if path_out.exists() and not full else {}
    tables: dict[str, dict[str, dict]] = old.get("tables", {})
    s = Sapl(base, slug)
    started = time.monotonic()
    for path in SMALL:
        tables[path] = {str(r["id"]): _slim(path, r) for page in s.pages(path, {"o": "id"}) for r in page}
    for path in APPEND:
        have = tables.setdefault(path, {})
        new = 0
        for incremental in (True, False) if have else (False,):
            for page in s.pages(path, {"o": "-id"}):
                fresh = [r for r in page if str(r["id"]) not in have]
                for r in fresh:
                    have[str(r["id"])] = _slim(path, r)
                new += len(fresh)
                if incremental and not fresh:
                    break
            # registros apagados na câmara deixam o total menor que o guardado; um buraco o deixa maior
            if not s.total or len(have) >= s.total:
                break
            log(slug, f"{path}: {len(have)} guardados, {s.total} anunciados; relendo a tabela inteira")
        log(slug, f"{path}: {len(have)} ({new} novos)")
    mats = tables.setdefault("materia/materialegislativa", {})
    years_done = set(old.get("materia_anos", []))
    this_year = date.today().year
    for year in range(FIRST_YEAR, this_year + 1):
        if year in years_done and year < this_year - 1:
            continue
        for page in s.pages("materia/materialegislativa", {"ano": year, "o": "id"}):
            for r in page:
                mats[str(r["id"])] = _slim("materia/materialegislativa", r)
        years_done.add(year)
    # matérias votadas desde 2021 mas apresentadas antes: uma a uma
    missing = {
        str(r["materia"])
        for r in tables["sessao/registrovotacao"].values()
        if r.get("materia") and (r.get("data_hora") or "")[:4] >= str(FIRST_YEAR)
    } - set(mats)
    voted = {str(v["votacao"]) for v in tables["sessao/votoparlamentar"].values()}
    missing &= {str(r["materia"]) for k, r in tables["sessao/registrovotacao"].items() if k in voted}
    for mid in sorted(missing):
        rec = s.get(f"materia/materialegislativa/{mid}", {})
        if rec.get("id"):
            mats[mid] = _slim("materia/materialegislativa", rec)
    out = {
        "base": s.base,
        "slug": slug,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "first_fetched_at": old.get("first_fetched_at")
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "requests": s.requests,
        "seconds": round(time.monotonic() - started),
        "tls_verificado": s.verify,
        "materia_anos": sorted(years_done),
        "tables": tables,
    }
    SAPL_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path_out.with_suffix(".part")
    tmp.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path_out)
    log(slug, f"{s.requests} requisições em {out['seconds']} s")
    return out


# --- Conversão para o snapshot --------------------------------------------------------------------

VOTO_MAP = {
    "sim": "sim",
    "nao": "nao",
    "não": "nao",
    "abstencao": "abstencao",
    "abstenção": "abstencao",
    "nao votou": "ausente",
    "não votou": "ausente",
    "ausente": "ausente",
    "presidente": "presidindo",
}
# Tipos de matéria cujas votações nominais entram mesmo quando unânimes; as demais (indicações,
# requerimentos, moções) só quando alguém votou não ou se absteve.
BILL = re.compile(r"projeto|veto|emenda|lei|decreto|resolu|substitutivo|parecer|contas", re.I)
NOT_BILL = re.compile(r"indica|requer|mo[cç][aã]o|of[ií]cio|voto de", re.I)


def _d(s: str | None) -> str | None:
    return s[:10] if s else None


def _short(s: str | None, n: int = 240) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _match(tse: list[dict], nome: str, completo: str, partido: str | None) -> dict | None:
    keys = [(norm(completo), "nome"), (norm(nome), "nome_parlamentar")]
    for key, field in keys:
        if not key:
            continue
        hits = [v for v in tse if norm(v[field]) == key]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1 and partido:
            same = [v for v in hits if v.get("partido") == partido]
            if len(same) == 1:
                return same[0]
    # nome parecido (acentos que o TSE perde, abreviações): exige razão alta e, se houver, o mesmo partido
    best, score = None, 0.0
    for v in tse:
        for key, field in keys:
            if not key:
                continue
            r = difflib.SequenceMatcher(None, key, norm(v[field])).ratio()
            if r > score:
                best, score = v, r
    if best and (score >= 0.93 or (score >= 0.85 and partido and best.get("partido") == partido)):
        return best
    return None


def merge_into(snap: dict, raw: dict) -> None:
    """Acrescenta ao snapshot de um município (vereadores do TSE) o que o SAPL publica."""
    t = raw["tables"]
    base = raw["base"]
    today = date.today().isoformat()
    legs_all = sorted(t.get("parlamentares/legislatura", {}).values(), key=lambda l: l["data_inicio"] or "")
    legs = [
        {"numero": l["numero"], "inicio": l["data_inicio"], "fim": l["data_fim"]}
        for l in legs_all
        if l.get("data_fim") and l["data_fim"] >= f"{FIRST_YEAR}-01-01" and l.get("data_inicio")
    ]
    leg_by_id = {k: l["numero"] for k, l in t.get("parlamentares/legislatura", {}).items()}
    if legs:
        snap["legislatures"] = legs
    leg_of_year = {l["inicio"][:4]: l["numero"] for l in legs}

    partido_sigla = {k: p["sigla"] for k, p in t.get("parlamentares/partido", {}).items()}
    filiacoes: dict[str, list[dict]] = defaultdict(list)
    for f in t.get("parlamentares/filiacao", {}).values():
        filiacoes[str(f["parlamentar"])].append(f)

    def partido_em(pid: str, dia: str) -> str | None:
        rows = sorted(filiacoes.get(pid, []), key=lambda f: f["data"] or "")
        sigla = None
        for f in rows:
            if (f["data"] or "") <= dia and (not f.get("data_desfiliacao") or f["data_desfiliacao"] >= dia):
                sigla = partido_sigla.get(str(f["partido"]))
        return sigla

    mandatos: dict[str, list[dict]] = defaultdict(list)
    legs_by_num = {l["numero"]: l for l in legs}
    for m in t.get("parlamentares/mandato", {}).values():
        num = leg_by_id.get(str(m["legislatura"]))
        if num not in legs_by_num:
            continue
        lg = legs_by_num[num]
        mandatos[str(m["parlamentar"])].append(
            {
                "leg": num,
                "ini": m.get("data_inicio_mandato") or lg["inicio"],
                "fim": m.get("data_fim_mandato") or lg["fim"],
            }
        )

    # re-chave os partidos do TSE ("2021", "2025") pelos números de legislatura da câmara
    for v in snap["vereadores"]:
        v["partidos_por_legislatura"] = {
            str(leg_of_year.get(y, y)): p for y, p in v["partidos_por_legislatura"].items()
        }

    tse = snap["vereadores"]
    by_sapl: dict[str, str] = {}
    unmatched: list[str] = []
    cur_leg = legs[-1]["numero"] if legs else None
    for pid, p in t.get("parlamentares/parlamentar", {}).items():
        if pid not in mandatos:
            continue
        ultimo = max(mandatos[pid], key=lambda m: m["ini"])
        partido = partido_em(pid, min(ultimo["fim"], today))
        v = _match(tse, p["nome_parlamentar"] or "", p["nome_completo"] or "", partido)
        if v is None:
            v = {
                "id": f"sapl:{pid}",
                "nome": p["nome_completo"] or p["nome_parlamentar"],
                "nome_parlamentar": None,
                "partido": partido,
                "partidos_por_legislatura": {},
                "legislaturas": [],
                "situacao": "fora_de_exercicio",
                "foto": None,
                "eleicoes": {},
            }
            tse.append(v)
            unmatched.append(p["nome_parlamentar"] or p["nome_completo"])
        by_sapl[pid] = v["id"]
        v["sapl_id"] = int(pid)
        v["nome_parlamentar"] = p["nome_parlamentar"] or v.get("nome_parlamentar")
        v["perfil_url"] = f"{base}/parlamentar/{pid}"
        v["email"] = p.get("email") or None
        v["legislaturas"] = sorted({m["leg"] for m in mandatos[pid]})
        for m in mandatos[pid]:
            sig = partido_em(pid, min(m["fim"], today))
            if sig:
                v["partidos_por_legislatura"][str(m["leg"])] = sig
        if partido:
            v["partido"] = partido
        em_exercicio = any(m["leg"] == cur_leg and m["ini"] <= today <= m["fim"] for m in mandatos[pid])
        v["situacao"] = (
            "em_exercicio"
            if (em_exercicio and p.get("ativo") is not False)
            else (v["situacao"] if v["situacao"].startswith(("eleito", "suplente")) else "fora_de_exercicio")
        )
    # quem não está no SAPL fica com a situação do TSE; "em exercício" só vem do SAPL
    if not any(v["situacao"] == "em_exercicio" for v in tse):
        for v in tse:
            if v.get("eleicoes", {}).get("2024", {}).get("situacao") == "eleito":
                v["situacao"] = "eleito_2024"

    tipos = t.get("materia/tipomaterialegislativa", {})
    snap["tipo_labels"] = {tp["sigla"]: tp["descricao"] for tp in tipos.values() if tp.get("sigla")}
    tipo_autor_parl = {
        k for k, ta in t.get("base/tipoautor", {}).items() if norm(ta["descricao"]) == "parlamentar"
    }
    autor_nome = {k: a["nome"] for k, a in t.get("base/autor", {}).items()}
    autor_vid = {
        k: by_sapl.get(str(a["object_id"]))
        for k, a in t.get("base/autor", {}).items()
        if str(a.get("tipo")) in tipo_autor_parl and a.get("object_id") is not None
    }

    mats = t.get("materia/materialegislativa", {})

    def mat_ref(mid: str) -> dict:
        m = mats.get(mid)
        if not m:
            return {
                "id": "",
                "tipo": "",
                "numero": "",
                "ano": None,
                "ementa": "",
                "autores": [],
                "autores_ids": [],
            }
        sig = (tipos.get(str(m["tipo"])) or {}).get("sigla") or str(m["tipo"])
        autores = [str(a) for a in (m.get("autores") or [])]
        return {
            "id": f"{sig}-{m['numero']}/{m['ano']}",
            "tipo": sig,
            "numero": str(m["numero"]),
            "ano": m["ano"],
            "ementa": _short(m.get("ementa"), 600),
            "autores": [autor_nome.get(a, a) for a in autores],
            "autores_ids": [x for x in (autor_vid.get(a) for a in autores) if x],
        }

    # proposições: matérias desde 2021 com ao menos um parlamentar entre os autores
    props = []
    for mid, m in mats.items():
        if (m.get("ano") or 0) < FIRST_YEAR:
            continue
        ref = mat_ref(mid)
        if not ref["autores_ids"]:
            continue
        props.append({**ref, "ementa": _short(m.get("ementa")), "data": _d(m.get("data_apresentacao"))})
    snap["proposicoes"] = props

    # votações nominais
    res = t.get("sessao/tiporesultadovotacao", {})
    votos_by_reg: dict[str, dict[str, str]] = defaultdict(dict)
    for vp in t.get("sessao/votoparlamentar", {}).values():
        vid = by_sapl.get(str(vp["parlamentar"]))
        voto = VOTO_MAP.get((vp.get("voto") or "").strip().lower())
        if vid and voto:
            votos_by_reg[str(vp["votacao"])][vid] = voto
    votacoes, fora = [], Counter()
    for rid, r in t.get("sessao/registrovotacao", {}).items():
        votos = votos_by_reg.get(rid)
        dia = _d(r.get("data_hora"))
        if not votos or not dia or dia < f"{FIRST_YEAR}-01-01":
            continue
        ref = mat_ref(str(r.get("materia")))
        desc = (tipos.get(str((mats.get(str(r.get("materia"))) or {}).get("tipo"))) or {}).get(
            "descricao", ""
        )
        cont = Counter(votos.values())
        dividida = cont["nao"] > 0 or cont["abstencao"] > 0
        if not dividida and (NOT_BILL.search(desc) or not BILL.search(desc)):
            fora["unanimes_nao_projeto"] += 1
            continue
        tr = res.get(str(r.get("tipo_resultado_votacao"))) or {}
        natureza = (tr.get("natureza") or "").upper()
        nome_res = (tr.get("nome") or "").lower()
        resultado = (
            "aprovado"
            if natureza == "A" or nome_res.startswith("aprovad")
            else "rejeitado"
            if natureza == "R" or nome_res.startswith("rejeitad")
            else (nome_res or None)
        )
        sess = re.search(
            r"em (\d+ª Sessão [^-]+?)(?: da \d+ª Sessão Legislativa|$| -)", r.get("__str__") or ""
        )
        objeto = (
            "veto"
            if re.search(r"veto", desc, re.I)
            else "emenda"
            if re.search(r"^emenda", desc, re.I)
            else "requerimento"
            if re.search(r"requer", desc, re.I)
            else "projeto"
        )
        votacoes.append(
            {
                "id": f"sapl:{rid}",
                "data": dia,
                "hora": (r.get("data_hora") or "")[11:16] or None,
                "sessao": {"tipo": None, "numero": sess.group(1).strip() if sess else None, "fase": None},
                "proposicao": ref,
                "objeto": objeto,
                "resultado": resultado,
                "contagem": {
                    "sim": cont["sim"],
                    "nao": cont["nao"],
                    "abstencao": cont["abstencao"],
                    "presentes_votando": cont["sim"] + cont["nao"] + cont["abstencao"],
                },
                "impresso": {
                    "sim": r.get("numero_votos_sim"),
                    "nao": r.get("numero_votos_nao"),
                    "abstencao": r.get("numero_abstencoes"),
                },
                "votos": votos,
                "fonte": f"{base}/materia/{r.get('materia')}" if r.get("materia") else base,
                **({"titulo": desc} if not ref["id"] else {}),
            }
        )
    snap["votacoes"] = votacoes

    # presença: sessões com lista publicada; falta = mandato vigente no dia e fora da lista
    sessoes = {
        k: s
        for k, s in t.get("sessao/sessaoplenaria", {}).items()
        if s.get("data_inicio") and s["data_inicio"] >= f"{FIRST_YEAR}-01-01"
    }
    presentes: dict[str, set[str]] = defaultdict(set)
    for pr in t.get("sessao/sessaoplenariapresenca", {}).values():
        sid = str(pr["sessao_plenaria"])
        if sid in sessoes:
            presentes[sid].add(str(pr["parlamentar"]))
    falta_mes: dict[tuple[str, int, int], int] = Counter()
    meses_de: dict[str, set[tuple[int, int]]] = defaultdict(set)
    for sid, quem in presentes.items():
        dia = sessoes[sid]["data_inicio"]
        y, mth = int(dia[:4]), int(dia[5:7])
        for pid, ms in mandatos.items():
            if pid not in by_sapl or not any(m["ini"] <= dia <= m["fim"] for m in ms):
                continue
            vid = by_sapl[pid]
            meses_de[vid].add((y, mth))
            if pid not in quem:
                falta_mes[(vid, y, mth)] += 1
    snap["presencas"] = [
        {
            "vereador_id": vid,
            "ano": y,
            "mes": mth,
            "faltas": falta_mes[(vid, y, mth)],
            "faltas_abonadas": 0,
            "total_faltas": falta_mes[(vid, y, mth)],
        }
        for vid, ms in meses_de.items()
        for (y, mth) in sorted(ms)
    ]

    datas = sorted(v["data"] for v in votacoes)
    snap["stats"] = {
        "votacoes": {
            "total": len(votacoes),
            "fora_unanimes_nao_projeto": fora["unanimes_nao_projeto"],
            "primeira": datas[0] if datas else None,
            "ultima": datas[-1] if datas else None,
            "por_ano": {y: c for y, c in sorted(Counter(d[:4] for d in datas).items())},
        },
        "presenca": {"sessoes": len(presentes), "linhas": len(snap["presencas"])},
        "proposicoes": {"total": len(props)},
        "nomes_nao_casados": sorted(unmatched),
    }
    snap["sources"].append(
        {
            "name": f"SAPL da Câmara ({base.split('//')[1]})",
            "url": f"{base}/api/",
            "count": raw.get("requests"),
        }
    )


# --- CLI ------------------------------------------------------------------------------------------


def sapl_targets() -> list[tuple[str, str]]:
    with SURVEY_CSV.open(encoding="utf-8") as f:
        return [
            (r["slug"], r["sapl_url"])
            for r in csv.DictReader(f)
            if r.get("sistema") == "sapl3" and r.get("sapl_url") and r["slug"] != "rio-de-janeiro"
        ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug")
    ap.add_argument("--base")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--full", action="store_true", help="ignora o que já foi lido")
    ap.add_argument("--workers", type=int, default=4, help="câmaras em paralelo (cada uma a 1 req/s)")
    args = ap.parse_args(argv)
    targets = sapl_targets() if args.all else [(args.slug, args.base)]
    failed = []

    def run(t: tuple[str, str]) -> None:
        try:
            collect(t[1], t[0], full=args.full)
        except Exception as exc:  # uma câmara fora do ar não derruba as outras
            log(t[0], "falhou:", exc)
            failed.append(t[0])

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        list(pool.map(run, targets))
    if failed:
        print("falharam:", ", ".join(failed), file=sys.stderr)
    return 1 if failed and len(failed) == len(targets) else 0


if __name__ == "__main__":
    raise SystemExit(main())
