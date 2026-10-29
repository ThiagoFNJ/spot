import re, sys, html

f = sys.argv[1]
h = open(f, encoding="utf-8", errors="replace").read()
print("#####", f, len(h))
print("title:", re.findall(r"<title>(.*?)</title>", h, re.S)[:1])
for m in re.finditer(r"<form[^>]*>", h):
    print("form:", m.group(0)[:200])
print("inputs:", sorted(set(re.findall(r'<(?:input|select|textarea)[^>]*name="([^"]+)"', h)))[:40])
ths = re.findall(r"<th[^>]*>(.*?)</th>", h, re.S)
print("th:", [re.sub(r"<[^>]+>|\s+", " ", t).strip()[:40] for t in ths][:30])
rows = re.findall(r"<tr[^>]*>(.*?)</tr>", h, re.S)
print("n_tr:", len(rows))
for r in rows[1:6]:
    cells = [re.sub(r"<[^>]+>|\s+", " ", c).strip()[:50] for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
    if cells:
        print("  row:", cells)
for kw in [
    "VEREADOR",
    "VERBA COMPENSAT",
    "INDENIZA",
    "RESSARC",
    "credor",
    "Credor",
    "favorecido",
    "Favorecido",
    "ajax",
    "json",
    "\.php",
    "csv",
    "xls",
    "exportar",
    "pagina",
    "page=",
    "limit",
]:
    n = len(re.findall(kw, h))
    if n:
        i = h.find(kw)
        print(f"kw {kw!r}: {n} -> ", re.sub(r"\s+", " ", h[max(0, i - 100) : i + 160]))
print(
    "urls:",
    sorted(
        set(
            re.findall(
                r'(?:href|src|action|url)=?["\']?(https?://cmsalvador\.sys\.inf\.br[^"\'\s>]+|/ca/[^"\'\s>]+)',
                h,
            )
        )
    )[:40],
)
