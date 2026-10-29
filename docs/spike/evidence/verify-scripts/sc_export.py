import re, sys, json, time, urllib.request, urllib.parse, http.cookiejar, os

OUT = sys.argv[1]
H = "http://45.4.247.157"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
for app, opc in [("LEG_SYS_produtividade_parlamentar_proposicao", "csv_res"), ("LEG_SYS_frequencia", "csv")]:
    print("##########", app, flush=True)
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", UA)]
    s = op.open(f"{H}/leg/salvador/{app}/", timeout=90).read().decode("iso-8859-1")
    init = re.search(r'name="script_case_init" value="(\d+)"', s).group(1)
    print("init", init, flush=True)
    data = urllib.parse.urlencode(
        {
            "nmgp_opcao": opc,
            "nm_delim_line": "1",
            "nm_delim_col": "1",
            "nm_delim_dados": "1",
            "nm_label_csv": "S",
            "SC_module_export": "",
            "nmgp_password": "",
            "script_case_init": init,
        }
    ).encode()
    e = (
        op.open(f"{H}/leg/salvador/{app}/{app}_export_ctrl.php", data=data, timeout=120)
        .read()
        .decode("iso-8859-1")
    )
    gen = re.search(r'index\.php\?nmgp_opcao=csv[^"\']*', e).group(0)
    md5 = gen.split("pbmd5=")[1]
    print("gen", gen, flush=True)
    import threading

    res = {}

    def trigger():
        try:
            r = op.open(f"{H}/leg/salvador/{app}/{gen}", timeout=600).read()
            res["gen"] = len(r)
        except Exception as ex:
            res["gen"] = repr(ex)

    t = threading.Thread(target=trigger)
    t.start()
    pb = None
    for i in range(120):
        time.sleep(3)
        try:
            pb = json.loads(
                op.open(f"{H}/producao/tmp/sc_pb_{md5}.txt", timeout=30).read().decode("utf-8", "replace")
            )
            if pb.get("complete"):
                print("complete after", (i + 1) * 3, "s", flush=True)
                break
        except Exception as ex:
            pb = {"err": repr(ex)}
    t.join(timeout=5)
    print("gen result", res, "| pb", json.dumps(pb)[:400], flush=True)
    if pb and pb.get("md5"):
        q = urllib.parse.urlencode({"script_case_init": init, "nm_tit_doc": app, "nm_name_doc": pb["md5"]})
        r = op.open(f"{H}/leg/salvador/{app}/{app}_download.php?{q}", timeout=600)
        body = r.read()
        print(
            "download",
            r.status,
            r.headers.get("Content-Type"),
            r.headers.get("Content-Disposition"),
            len(body),
            flush=True,
        )
        open(os.path.join(OUT, f"csv_{app}.bin"), "wb").write(body)
        if pb.get("link"):
            try:
                r2 = op.open(f"{H}{pb['link']}" if pb["link"].startswith("/") else pb["link"], timeout=600)
                b2 = r2.read()
                print("link fetch", r2.status, r2.headers.get("Content-Type"), len(b2), flush=True)
                open(os.path.join(OUT, f"csv_{app}_link.bin"), "wb").write(b2)
            except Exception as ex:
                print("link fetch err", repr(ex))
