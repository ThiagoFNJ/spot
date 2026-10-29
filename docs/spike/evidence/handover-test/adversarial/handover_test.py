#!/usr/bin/env python3
"""Adversarial reproduction of HANDOVER.md 2.3-2.4 (LEG_SYS_frequencia, Scriptcase 9).

Builds requests the way the page's own JS does (ajax_navigate raw body, Fexport hidden
fields), logs every request (method, url, body, status, size, timing) to log.jsonl and
saves every raw response under ./responses/NN_<name>.<ext>.
Rate limit: >= 1.0 s between request starts, hard cap on total requests.
"""

import json, os, re, sys, time, collections
import httpx

OUT = os.path.dirname(os.path.abspath(__file__))
RESP = os.path.join(OUT, "responses")
os.makedirs(RESP, exist_ok=True)
HOST = "http://45.4.247.157"
APP = "LEG_SYS_frequencia"
BASE = f"{HOST}/leg/salvador/{APP}/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
MAX_REQ = 44
MIN_GAP = 1.0

TIPOS = {1: "Sessão Ordinária", 2: "Sessão Especial", 3: "Sessão Solene", 4: "Sessão Extraordinária"}
RE_TOTAL = re.compile(r"\[(\d+) a (\d+) de (\d+)\]")
RE_INIT = re.compile(r'name="script_case_init" value="(\d+)"')
RE_PB = re.compile(r"pbmd5=([0-9a-f]{32})")
RE_FATAL = re.compile(r"Fatal error</b>:\s*(.*?)<br", re.S)

_n = 0
_last = 0.0
LOG = open(os.path.join(OUT, "log.jsonl"), "a")
RESULTS = {}


def _wait():
    global _last
    d = time.monotonic() - _last
    if d < MIN_GAP:
        time.sleep(MIN_GAP - d)
    _last = time.monotonic()


def req(c, method, url, name, ext="html", content=None, data=None, headers=None, timeout=600):
    global _n
    if _n >= MAX_REQ:
        raise RuntimeError(f"request budget exhausted ({MAX_REQ})")
    _n += 1
    _wait()
    t0 = time.monotonic()
    body_sent = content if content is not None else (data if data is not None else None)
    try:
        r = c.request(method, url, content=content, data=data, headers=headers, timeout=timeout)
        el = time.monotonic() - t0
        raw = r.content
        fn = f"{_n:02d}_{name}.{ext}"
        with open(os.path.join(RESP, fn), "wb") as f:
            f.write(raw)
        txt = raw.decode("latin-1")
        fatal = RE_FATAL.search(txt)
        entry = {
            "n": _n,
            "t": time.strftime("%H:%M:%S"),
            "method": method,
            "url": url,
            "body": (body_sent.decode("utf-8", "replace") if isinstance(body_sent, bytes) else body_sent),
            "status": r.status_code,
            "bytes": len(raw),
            "secs": round(el, 3),
            "file": fn,
            "content_type": r.headers.get("content-type"),
            "fatal": (fatal.group(1).strip()[:200] if fatal else None),
            "cookies": dict(c.cookies),
        }
        print(
            f"[{_n:02d}] {method} {url.replace(HOST, '')} -> {r.status_code} {len(raw)}B {el:.2f}s"
            + (f" FATAL: {entry['fatal'][:100]}" if fatal else ""),
            flush=True,
        )
    except Exception as e:
        el = time.monotonic() - t0
        entry = {
            "n": _n,
            "t": time.strftime("%H:%M:%S"),
            "method": method,
            "url": url,
            "body": (body_sent.decode("utf-8", "replace") if isinstance(body_sent, bytes) else body_sent),
            "error": repr(e),
            "secs": round(el, 3),
        }
        print(f"[{_n:02d}] {method} {url.replace(HOST, '')} -> ERROR {e!r} {el:.2f}s", flush=True)
        LOG.write(json.dumps(entry, ensure_ascii=False) + "\n")
        LOG.flush()
        raise
    LOG.write(json.dumps(entry, ensure_ascii=False) + "\n")
    LOG.flush()
    return r, txt, entry


def new_client():
    return httpx.Client(
        headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"}, follow_redirects=True
    )


def get_init(c, name="get_root"):
    r, txt, e = req(c, "GET", BASE, name)
    inits = set(RE_INIT.findall(txt))
    tot = RE_TOTAL.findall(txt)
    e2 = {"inits": sorted(inits), "total": tot[0] if tot else None}
    print("     script_case_init:", inits, "grid total:", tot[:1], flush=True)
    if len(inits) != 1:
        raise RuntimeError(f"unexpected script_case_init set {inits}")
    return inits.pop(), e2


def nav(c, init, parm, name, encode="raw"):
    """ajax_navigate exactly like LEG_SYS_frequencia_jquery.js: plain string body, no url-encoding."""
    parm = (
        parm.replace("+", "__NM_PLUS__")
        .replace("&amp;", "__NM_AMP__")
        .replace("&", "__NM_AMP__")
        .replace("%", "__NM_PRC__")
    )
    body = f"nmgp_opcao=ajax_navigate&script_case_init={init}&opc=interativ_search&parm={parm}"
    if encode == "raw":  # what jQuery $.ajax(data: "string") sends: raw string, UTF-8
        content = body.encode("utf-8")
    elif encode == "latin1":  # what the spike doc claims ("latin-1 de ...")
        content = body.encode("latin-1")
    elif encode == "urlencoded":  # what HANDOVER claims ("url-encoded normalmente")
        from urllib.parse import quote

        content = (
            "nmgp_opcao=ajax_navigate&script_case_init=%s&opc=interativ_search&parm=%s"
            % (init, quote(parm, safe=""))
        ).encode("ascii")
    r, txt, e = req(
        c,
        "POST",
        BASE + "index.php",
        name,
        ext="json",
        content=content,
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    tot = RE_TOTAL.findall(txt)
    total = int(tot[0][2]) if tot else None
    starts_brace = txt.strip().startswith("{")
    print(f"     starts with '{{': {starts_brace}; total regex: {tot[:2]} -> {total}", flush=True)
    return total, txt


def fexport_fields(init, opcao="csv", label="N", module="grid", **over):
    """All hidden inputs of form Fexport, as the browser submits them for nm_gp_csv_conf(...)."""
    d = collections.OrderedDict(
        [
            ("nmgp_opcao", opcao),
            ("nmgp_tp_xls", ""),
            ("nmgp_tot_xls", ""),
            ("SC_module_export", module),
            ("nm_delim_line", "1"),
            ("nm_delim_col", "1"),
            ("nm_delim_dados", "1"),
            ("nm_label_csv", label),
            ("nm_xml_tag", ""),
            ("nm_xml_label", ""),
            ("nm_json_format", ""),
            ("nm_json_label", ""),
            ("nmgp_password", ""),
            ("script_case_init", init),
        ]
    )
    d.update(over)
    return d


def export(c, init, name, fields=None, poll_max=6, download=True, **kw):
    """Steps 2-5 of HANDOVER: export_ctrl -> pbmd5 -> gen (blocking) -> poll -> download."""
    fields = fields or fexport_fields(init, **kw)
    res = {"fields": dict(fields)}
    r, txt, e = req(c, "POST", BASE + f"{APP}_export_ctrl.php", f"{name}_ctrl", data=fields)
    res["ctrl"] = {"status": r.status_code, "bytes": len(txt), "fatal": e.get("fatal")}
    m = RE_PB.search(txt)
    src = re.search(r'<iframe[^>]*src="([^"]+)"', txt, re.I)
    if not m:
        res["error"] = "no pbmd5 in export_ctrl response"
        snippet = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", txt))[:400]
        res["ctrl_snippet"] = snippet
        print("     NO pbmd5; snippet:", snippet[:300], flush=True)
        return res
    md5 = m.group(1)
    res["pbmd5"] = md5
    gen_url = BASE + (
        src.group(1)
        if src and "pbmd5" in src.group(1)
        else f"index.php?{'&'.join(f'{k}={v}' for k, v in fields.items())}&pbmd5={md5}"
    )
    res["gen_url"] = gen_url
    print("     iframe src:", src.group(1) if src else None, flush=True)
    r, txt, e = req(c, "GET", gen_url, f"{name}_gen")
    res["gen"] = {"status": r.status_code, "bytes": len(txt), "secs": e["secs"], "fatal": e.get("fatal")}
    pb = None
    for i in range(poll_max):
        r, txt, e = req(
            c, "GET", f"{HOST}/producao/tmp/sc_pb_{md5}.txt", f"{name}_pb{i}", ext="txt", timeout=60
        )
        try:
            pb = json.loads(txt)
        except Exception:
            pb = {"raw": txt[:300], "status": r.status_code}
        print("     pb:", json.dumps(pb, ensure_ascii=False)[:300], flush=True)
        if pb.get("complete"):
            break
    res["pb"] = pb
    if download and pb and pb.get("link"):
        r, txt, e = req(c, "GET", HOST + pb["link"], f"{name}_csv", ext="csv")
        res["download"] = {"status": r.status_code, "bytes": len(txt), "secs": e["secs"], "file": e["file"]}
        res["csv"] = analyze_csv(txt)
        print("     csv:", json.dumps(res["csv"], ensure_ascii=False)[:600], flush=True)
    return res


RE_DATA = re.compile(r'^"(\d+)";"(\d{4})";"(.*)";"(Presente|Ausente|Licenciado)"$')


def analyze_csv(txt):
    lines = txt.split("\r\n") if "\r\n" in txt else txt.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    data = [l for l in lines if RE_DATA.match(l)]
    other = [l for l in lines if not RE_DATA.match(l)]
    rows = [RE_DATA.match(l).groups() for l in data]
    sess = sorted({(r[1], r[0]) for r in rows})
    st = collections.Counter(r[3] for r in rows)
    return {
        "lines": len(lines),
        "data_rows": len(data),
        "other_rows": len(other),
        "other_sample": other[:12],
        "crlf": "\r\n" in txt,
        "first": lines[:2],
        "last": lines[-1:],
        "sessions": [f"{a}/{n}" for a, n in sess] if len(sess) <= 60 else f"{len(sess)} sessions",
        "status": dict(st),
        "distinct_parl": len({r[2] for r in rows}),
        "rows_per_session": dict(collections.Counter(f"{r[1]}/{r[0]}" for r in rows))
        if len(sess) <= 60
        else None,
    }


RE_TR = re.compile(r"<TR class=\"scGridField(?:Odd|Even)\".*?</TR>", re.S)
RE_SPAN = re.compile(
    r'id="id_sc_field_(pre_ses_numero|pre_ses_ano|cad_cad_nome_abreviado|pre_pre_presente)_\d+">(.*?)</span>',
    re.S,
)


def parse_grid_rows(txt):
    out = []
    for tr in RE_TR.findall(txt):
        d = dict(RE_SPAN.findall(tr))
        if len(d) == 4:
            out.append(
                (
                    d["pre_ses_numero"].strip(),
                    d["pre_ses_ano"].strip(),
                    d["cad_cad_nome_abreviado"].strip(),
                    d["pre_pre_presente"].strip(),
                )
            )
    return out


def dump_html(c, init, name, qt=30000):
    body = f"script_case_init={init}&nmgp_opcao=muda_qt_linhas&nmgp_quant_linhas={qt}"
    r, txt, e = req(
        c,
        "POST",
        BASE + "index.php",
        name,
        content=body.encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    tot = RE_TOTAL.findall(txt)
    rows = parse_grid_rows(txt)
    groups = re.findall(r'class="scGridLabelGroup[^"]*"[^>]*>(.*?)</', txt, re.S)
    print(
        f"     dump total regex {tot[:1]}, parsed rows {len(rows)}, group-break cells {len(groups)}",
        flush=True,
    )
    return {
        "status": r.status_code,
        "bytes": len(txt),
        "secs": e["secs"],
        "total": tot[0] if tot else None,
        "rows": rows,
        "file": e["file"],
    }


def csv_rows(path):
    txt = open(path, "rb").read().decode("latin-1")
    lines = txt.split("\r\n") if "\r\n" in txt else txt.split("\n")
    return [RE_DATA.match(l).groups() for l in lines if RE_DATA.match(l)]


def month_parm(ym):
    y, m = ym.split("-")
    return f"pre_pre_data_presenca__DL__Mês e Ano__DL__dh__DL__{ym}##@@{m}/{y} __DL__S"


def tipo_parm(code):
    return f"pre_tse_codigo__DL__Tipo de Sessão__DL__nn__DL__{code}##@@{TIPOS[code]}__DL__S"


def save_results():
    with open(os.path.join(OUT, "results.json"), "w") as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=1, default=str)


def main():
    stages = sys.argv[1:] or ["A", "B", "C", "D", "E"]
    # ---------------- Scenario A: 2025-03 x tipo 1, page-faithful ----------------
    if "A" in stages:
        c = new_client()
        RESULTS["A"] = A = {}
        try:
            init, meta = get_init(c, "A_get_root")
            A["init"] = init
            A["unfiltered_total"] = meta["total"]
            A["month_total"], _ = nav(c, init, month_parm("2025-03"), "A_nav_month")
            A["tipo1_total"], _ = nav(c, init, tipo_parm(1), "A_nav_tipo1")
            A["export_N"] = export(c, init, "A_csvN", label="N")
            A["export_S"] = export(c, init, "A_csvS", label="S")
            A["dump"] = dump_html(c, init, "A_dump30000")
            # compare sets
            rows_csv = (
                csv_rows(os.path.join(RESP, A["export_N"]["download"]["file"]))
                if A["export_N"].get("download")
                else []
            )
            set_csv = collections.Counter((r[0], r[1], r[2], r[3]) for r in rows_csv)
            set_dump = collections.Counter(A["dump"]["rows"])
            A["compare_csv_vs_dump"] = {
                "csv_rows": sum(set_csv.values()),
                "dump_rows": sum(set_dump.values()),
                "only_in_csv": list((set_csv - set_dump).elements())[:20],
                "only_in_dump": list((set_dump - set_csv).elements())[:20],
                "equal_multiset": set_csv == set_dump,
            }
            print("     compare:", json.dumps(A["compare_csv_vs_dump"], ensure_ascii=False)[:500], flush=True)
            A["dump"].pop("rows", None)
            # filter persistence across a new GET on the same PHPSESSID
            init2, meta2 = get_init(c, "A_get_root_again")
            A["init2"] = init2
            A["total_after_reget"] = meta2["total"]
            # stale script_case_init: export with the OLD init after the page was reloaded
            A["export_stale_init"] = export(c, init, "A_csvN_staleinit", label="N", poll_max=1)
        except Exception as e:
            A["error"] = repr(e)
            print("A ERROR", repr(e), flush=True)
        finally:
            c.close()
            save_results()
    # ---------------- Scenario B: 2025-03 x tipo 3 / tipo 4 (fresh sessions) ----------------
    if "B" in stages:
        for code in (3, 4):
            c = new_client()
            RESULTS[f"B_tipo{code}"] = B = {}
            try:
                init, meta = get_init(c, f"B{code}_get_root")
                B["init"] = init
                B["unfiltered_total"] = meta["total"]
                B["month_total"], _ = nav(c, init, month_parm("2025-03"), f"B{code}_nav_month")
                B["tipo_total"], _ = nav(c, init, tipo_parm(code), f"B{code}_nav_tipo{code}")
                if B["tipo_total"] and not any(RESULTS.get(f"B_tipo{k}", {}).get("export_N") for k in (3, 4)):
                    B["export_N"] = export(c, init, f"B{code}_csvN", label="N", poll_max=3)
            except Exception as e:
                B["error"] = repr(e)
                print("B ERROR", repr(e), flush=True)
            finally:
                c.close()
                save_results()
    # ---------------- Scenario D: full export, no filter (HANDOVER params, label S) ----------------
    if "D" in stages:
        c = new_client()
        RESULTS["D"] = D = {}
        try:
            init, meta = get_init(c, "D_get_root")
            D["init"] = init
            D["unfiltered_total"] = meta["total"]
            D["export_S_full"] = export(c, init, "D_csvS_full", label="S", poll_max=8)
            # ---------------- Scenario E: try to trigger the fatal error, same session ----------------
            if "E" in stages:
                RESULTS["E"] = E = {}
                # E1: XML export via export_ctrl, as the page's XML button does (nm_gp_xml_conf('attribute','N','grid',''))
                E["xml"] = export(
                    c,
                    init,
                    "E_xml",
                    fields=fexport_fields(
                        init, opcao="xml", module="grid", nm_xml_tag="attribute", nm_xml_label="N"
                    ),
                    poll_max=1,
                    download=False,
                )
                # E2: CSV with SC_module_export=resumo (summary module)
                E["csv_resumo"] = export(
                    c, init, "E_csv_resumo", label="N", module="resumo", poll_max=1, download=False
                )
                # E3: CSV with SC_module_export empty (what verify-scripts/sc_export.py sent)
                E["csv_module_empty"] = export(
                    c, init, "E_csv_moduleempty", label="S", module="", poll_max=1, download=False
                )
        except Exception as e:
            D["error"] = repr(e)
            print("D/E ERROR", repr(e), flush=True)
        finally:
            c.close()
            save_results()
    RESULTS["_requests_total"] = _n
    save_results()
    print("DONE, requests:", _n)


if __name__ == "__main__":
    main()
