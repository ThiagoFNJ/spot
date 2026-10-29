import httpx, re, time, json, html

BASE = "http://45.4.247.157/leg/salvador/LEG_SYS_sessao_ata/"
c = httpx.Client(timeout=60, headers={"User-Agent": "Mozilla/5.0 (handover-test faithful)"})
log = []


def req(tag, method, url, data=None):
    t0 = time.time()
    r = c.request(method, url, data=data)
    el = round(time.time() - t0, 2)
    open(f"{tag}.bin", "wb").write(r.content)
    e = {
        "tag": tag,
        "method": method,
        "url": url,
        "body": data,
        "status": r.status_code,
        "bytes": len(r.content),
        "elapsed_s": el,
    }
    log.append(e)
    print(json.dumps(e, ensure_ascii=False))
    time.sleep(1)
    return r


r = req("e02_root", "GET", BASE)
h = r.content.decode("latin-1")
init = re.search(r'name="script_case_init"\s+value="(\d+)"', h).group(1)
print("init", init)


def nav(tag, parm):
    r = req(
        tag,
        "POST",
        BASE + "index.php",
        {"nmgp_opcao": "ajax_navigate", "script_case_init": init, "opc": "interativ_search", "parm": parm},
    )
    t = r.content.decode("latin-1")
    tot = re.findall(r"\[\d+ a \d+ de (\d+)\]", t)
    print("  total", tot, "fatal" if "Fatal error" in t else "")
    try:
        j = json.loads(t)
        body = [v["value"] for v in j["setValue"] if v["field"] == "sc_grid_body"][0]
        s = html.unescape(re.sub(r"<[^>]+>", "|", body))
        s = re.sub(r"(\|\s*)+", "|", s)
        return s
    except Exception as e:
        print("  parse err", e)
        return t[:800]


s1 = nav(
    "e03_type1",
    "pre_tse_codigo__DL__Tipo de Sessão__DL__nn__DL__1##@@Sessão Ordinária__DL__S".replace(
        "pre_tse_codigo", "ses_tse_codigo"
    ),
)
print(s1[:300])
s2 = nav("e04_mes_2025-03", "mes__DL__MES__DL__dh__DL__2025-03##@@03/2025 __DL__S")
print(s2[:1500])
print("dates:", re.findall(r"(\d\d/\d\d/\d{4})", s2))
json.dump(log, open("probe2_log.json", "w"), ensure_ascii=False, indent=1)
