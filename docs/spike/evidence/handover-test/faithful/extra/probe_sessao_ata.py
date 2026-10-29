import httpx, re, time, json, sys, html

BASE = "http://45.4.247.157/leg/salvador/LEG_SYS_sessao_ata/"
c = httpx.Client(timeout=60, headers={"User-Agent": "Mozilla/5.0 (handover-test faithful)"})
t0 = time.time()
r = c.get(BASE)
print("GET root", r.status_code, len(r.content), round(time.time() - t0, 2))
open("e01_sessao_ata_root.bin", "wb").write(r.content)
h = r.content.decode("latin-1")
m = re.search(r'name="script_case_init"\s+value="(\d+)"', h) or re.search(
    r'script_case_init["\']?\s*[:=]\s*["\']?(\d+)', h
)
init = m.group(1) if m else None
print("init", init)
print("int_search fields:", sorted(set(re.findall(r'name="int_search_([a-zA-Z_]+)\[\]"', h))))
print("month opts sample:", sorted(set(re.findall(r'value="(2025-0[23]##@@[^"]*)"', h))))
print("labels:", sorted(set(re.findall(r"nm_expand_int_search\(\'([^\']+)\'", h))))
print("totals:", re.findall(r"\[\d+ a \d+ de \d+\]", h))
json.dump({"init": init}, open("probe_state.json", "w"))
# pass filter parm on argv to try one POST
if len(sys.argv) > 1:
    time.sleep(1)
    parm = sys.argv[1]
    t0 = time.time()
    r2 = c.post(
        BASE + "index.php",
        data={
            "nmgp_opcao": "ajax_navigate",
            "script_case_init": init,
            "opc": "interativ_search",
            "parm": parm,
        },
    )
    print("POST", r2.status_code, len(r2.content), round(time.time() - t0, 2))
    open("e02_sessao_ata_filter.bin", "wb").write(r2.content)
    t = r2.content.decode("latin-1")
    print("totals:", re.findall(r"\[\d+ a \d+ de \d+\]", t))
    try:
        j = json.loads(t)
        body = [v["value"] for v in j["setValue"] if v["field"] == "sc_grid_body"][0]
        s = html.unescape(re.sub(r"<[^>]+>", "|", body))
        s = re.sub(r"(\|\s*)+", "|", s)
        print(s[:3000])
    except Exception as e:
        print("parse err", e)
        print(t[:1500])
