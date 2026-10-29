"""Faithful reproduction of HANDOVER.md section 2.3 (Scriptcase CSV export, LEG_SYS_frequencia).

Usage: run_faithful.py [YYYY-MM:TIPO ...] [full]
One httpx.Client (one PHPSESSID) for the whole run; <=1 request/second; hard cap of 40 requests.
Every raw response is saved under raw/ with a sequence number.
"""

import sys, re, time, json, os
import httpx

BASE = "http://45.4.247.157/leg/salvador/LEG_SYS_frequencia/"
HOST = "http://45.4.247.157"
OUT = os.environ.get("OUTDIR") or os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(OUT, "raw")
os.makedirs(RAW, exist_ok=True)
TIPOS = {1: "Sessão Ordinária", 2: "Sessão Especial", 3: "Sessão Solene", 4: "Sessão Extraordinária"}
MAX_REQ = 40
LOG = []
seq = 0
last_t = 0.0


def rate_limit():
    global last_t
    dt = time.time() - last_t
    if dt < 1.0:
        time.sleep(1.0 - dt)
    last_t = time.time()


def do(client, method, url, tag, data=None, timeout=60, ok_404=False):
    global seq
    if seq >= MAX_REQ:
        raise RuntimeError(f"request budget exhausted ({MAX_REQ})")
    rate_limit()
    seq += 1
    t0 = time.time()
    err = None
    try:
        r = client.request(method, url, data=data, timeout=timeout)
    except Exception as e:  # noqa
        err = repr(e)
        r = None
    el = round(time.time() - t0, 3)
    entry = {
        "seq": seq,
        "tag": tag,
        "method": method,
        "url": url,
        "body": data,
        "status": r.status_code if r else None,
        "bytes": len(r.content) if r else None,
        "elapsed_s": el,
        "error": err,
        "content_type": r.headers.get("content-type") if r else None,
    }
    fname = f"{seq:02d}_{tag}.bin"
    if r is not None:
        with open(os.path.join(RAW, fname), "wb") as f:
            f.write(r.content)
        entry["raw"] = fname
    LOG.append(entry)
    print(json.dumps(entry, ensure_ascii=False), flush=True)
    if err:
        raise RuntimeError(err)
    return r


def get_init(client):
    r = do(client, "GET", BASE, "step0_get_root")
    html = r.content.decode("latin-1")
    m = re.search(r'name="script_case_init"\s+value="(\d+)"', html)
    if not m:
        m = re.search(r'script_case_init["\']?\s*[:=]\s*["\']?(\d+)', html)
    if not m:
        raise RuntimeError("script_case_init not found in root HTML")
    return m.group(1)


def nav(client, init, parm, tag):
    # The page JS does + -> __NM_PLUS__, & -> __NM_AMP__, % -> __NM_PRC__ before url-encoding.
    parm = parm.replace("+", "__NM_PLUS__").replace("&", "__NM_AMP__").replace("%", "__NM_PRC__")
    body = {"nmgp_opcao": "ajax_navigate", "script_case_init": init, "opc": "interativ_search", "parm": parm}
    r = do(client, "POST", BASE + "index.php", tag, data=body)
    txt = r.content.decode("latin-1")
    m = re.search(r"\[\d+ a \d+ de (\d+)\]", txt)
    total = int(m.group(1)) if m else None
    fatal = "Fatal error" in txt
    print(f"   -> filter total = {total} fatal={fatal}", flush=True)
    return total, txt


def export_csv(client, init, tag):
    body = {
        "nmgp_opcao": "csv",
        "nm_delim_line": "1",
        "nm_delim_col": "1",
        "nm_delim_dados": "1",
        "nm_label_csv": "S",
        "nmgp_password": "",
        "SC_module_export": "grid",
        "script_case_init": init,
    }
    r = do(client, "POST", BASE + "LEG_SYS_frequencia_export_ctrl.php", tag + "_step2_export_ctrl", data=body)
    txt = r.content.decode("latin-1")
    if "Fatal error" in txt:
        raise RuntimeError("FATAL in export_ctrl: " + re.search(r"Fatal error[^<\n]*", txt).group(0))
    m = re.search(r"pbmd5=([0-9a-f]{32})", txt)
    if not m:
        raise RuntimeError("pbmd5 not found in export_ctrl response")
    pbmd5 = m.group(1)
    print(f"   -> pbmd5 = {pbmd5}", flush=True)
    url3 = (
        BASE + "index.php?nmgp_opcao=csv&nm_delim_line=1&nm_delim_col=1&nm_delim_dados=1"
        f"&nm_label_csv=S&nmgp_password=&SC_module_export=grid&script_case_init={init}&pbmd5={pbmd5}"
    )
    r3 = do(client, "GET", url3, tag + "_step3_generate", timeout=600)
    t3 = r3.content.decode("latin-1")
    if "Fatal error" in t3:
        raise RuntimeError("FATAL in step3: " + re.search(r"Fatal error[^<\n]*", t3).group(0))
    # step 4: poll
    pb = None
    for i in range(12):
        r4 = do(client, "GET", f"{HOST}/producao/tmp/sc_pb_{pbmd5}.txt", tag + f"_step4_poll{i}")
        if r4.status_code == 200:
            try:
                pb = json.loads(r4.content.decode("latin-1"))
            except Exception:
                pb = None
            if pb and pb.get("complete"):
                break
        time.sleep(0.5)
    if not pb or not pb.get("complete"):
        raise RuntimeError(f"progress never completed: {pb}")
    print(f"   -> progress = {pb}", flush=True)
    r5 = do(client, "GET", HOST + pb["link"], tag + "_step5_download", timeout=600)
    csv_text = r5.content.decode("latin-1")
    return csv_text, pb


def csv_stats(csv_text):
    lines = csv_text.splitlines()
    n = len(lines)
    header = lines[0] if lines else ""
    data = [l for l in lines[1:] if l.strip()]
    sessions = sorted(
        {(l.split(";")[0].strip('"'), l.split(";")[1].strip('"')) for l in data if l.count(";") >= 3}
    )
    # rows whose column count differs from header -> suspicious (group/subtotal rows)
    hc = header.count(";")
    odd = [l for l in lines[1:] if l.strip() and l.count(";") != hc]
    return {
        "total_lines": n,
        "header": header,
        "data_rows": len(data),
        "sessions": sessions,
        "odd_rows": odd[:20],
        "n_odd_rows": len(odd),
        "first3": lines[1:4],
        "last3": lines[-3:],
    }


def scenario(client, name, ym=None, tipo=None):
    res = {"scenario": name, "ok": False}
    try:
        init = get_init(client)
        res["script_case_init"] = init
        if ym:
            y, m = ym.split("-")
            parm_m = f"pre_pre_data_presenca__DL__Mês e Ano__DL__dh__DL__{ym}##@@{m}/{y} __DL__S"
            tot_m, _ = nav(client, init, parm_m, f"{name}_step1_month")
            res["total_after_month"] = tot_m
            parm_t = f"pre_tse_codigo__DL__Tipo de Sessão__DL__nn__DL__{tipo}##@@{TIPOS[tipo]}__DL__S"
            tot_t, _ = nav(client, init, parm_t, f"{name}_step1_type")
            res["total_after_type"] = tot_t
            if not tot_t:
                res["note"] = "empty combination (total 0/None) - export skipped"
                res["ok"] = True
                return res
        csv_text, pb = export_csv(client, init, name)
        res["progress"] = pb
        path = os.path.join(OUT, f"{name}.csv")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(csv_text)
        res["csv_path"] = path
        res["csv_bytes_latin1"] = len(csv_text.encode("latin-1", "replace"))
        res.update(csv_stats(csv_text))
        res["ok"] = True
    except Exception as e:
        res["error"] = repr(e)
        print("   !! " + repr(e), flush=True)
    return res


def main():
    args = sys.argv[1:] or ["2025-03:1", "2025-03:3", "2025-03:4", "full"]
    results = []
    with httpx.Client(
        timeout=60, headers={"User-Agent": "Mozilla/5.0 (handover-test faithful; contact: project spot)"}
    ) as c:
        for a in args:
            if a == "full":
                results.append(scenario(c, "full"))
            else:
                ym, t = a.split(":")
                results.append(scenario(c, f"{ym}_tipo{t}", ym, int(t)))
            print(json.dumps(results[-1], ensure_ascii=False, default=str)[:1500], flush=True)
        results.append({"cookies": dict(c.cookies)})
    with open(os.path.join(OUT, "results.json"), "w", encoding="utf-8") as f:
        json.dump({"requests": LOG, "results": results}, f, ensure_ascii=False, indent=1, default=str)
    print("TOTAL REQUESTS:", seq)


if __name__ == "__main__":
    main()
