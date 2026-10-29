import csv, re, collections, sys

rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
agg = collections.defaultdict(lambda: {"n": 0, "total": 0.0, "names": collections.Counter(), "mesa": ""})
for r in rows:
    cc = r["centro_custo"]
    code, _, desc = cc.partition(" - ")
    m = re.search(r"GAB\.?\s*VER\.?\s*(.+)$", desc)
    if not m:
        continue
    g = re.sub(r"\(SUP.*", "", m.group(1))
    g = re.sub(r"\s*-\s*\d[\d.]*\s*$", "", g).strip(" -")
    pref = desc[: m.start()].strip(" -")
    a = agg[code]
    a["n"] += 1
    a["total"] += float(r["total_proventos"].replace(".", "").replace(",", "."))
    a["names"][g] += 1
    if pref:
        a["mesa"] = pref
out = csv.writer(open(sys.argv[2], "w", newline=""))
out.writerow(["cc_code", "gabinete", "cargo_mesa", "n_servidores", "folha_mes_total"])
tot = 0
for code, a in sorted(agg.items(), key=lambda x: -x[1]["total"]):
    name = a["names"].most_common(1)[0][0]
    tot += a["total"]
    out.writerow([code, name, a["mesa"], a["n"], f"{a['total']:.2f}"])
    print(f"{code:>9} {name[:34]:34s} {a['mesa'][:28]:28s} n={a['n']:3d} folha={a['total']:>12,.2f}")
print(
    "gabinetes (cc codes):",
    len(agg),
    " servidores:",
    sum(a["n"] for a in agg.values()),
    "/",
    len(rows),
    " total:",
    f"{tot:,.2f}",
)
