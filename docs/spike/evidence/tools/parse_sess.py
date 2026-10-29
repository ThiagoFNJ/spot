import sys, re, html, collections
from html.parser import HTMLParser

raw = open(sys.argv[1], "rb").read().decode("iso-8859-1", "replace")
raw = re.sub(r"(?is)<(script|style).*?</\1>", "", raw)


class P(HTMLParser):
    def __init__(s):
        super().__init__()
        s.rows = []
        s.cur = None
        s.cell = None

    def handle_starttag(s, t, a):
        a = dict(a)
        if t == "tr":
            s.cur = []
        if t in ("td", "th") and s.cur is not None:
            s.cell = []
        if t == "a" and s.cell is not None and a.get("href"):
            m = re.search(r"nm_gp_submit5\('([^']+)'", a["href"])
            if m:
                s.cell.append("{" + m.group(1) + "}")

    def handle_endtag(s, t):
        if t in ("td", "th") and s.cell is not None and s.cur is not None:
            s.cur.append(" ".join("".join(s.cell).split()))
            s.cell = None
        if t == "tr" and s.cur is not None:
            r = [c for c in s.cur if c]
            if r:
                s.rows.append(r)
            s.cur = None

    def handle_data(s, d):
        if s.cell is not None:
            s.cell.append(html.unescape(d))


p = P()
p.feed(raw)
out = []
for r in p.rows:
    if len(r) >= 3 and r[0].startswith("Sessão") and re.fullmatch(r"\d{2}/\d{2}/\d{4}", r[2]):
        files = re.findall(r"\{([^}]+)\}", " ".join(r[3:]))
        out.append((r[0], r[1], r[2], ";".join(files)))
print("sessions", len(out))
print("by type", collections.Counter(o[0] for o in out))
print("by year", sorted(collections.Counter(o[2][-4:] for o in out).items()))
print("with files", sum(1 for o in out if o[3]), "pdf", sum(1 for o in out if ".pdf" in o[3]))
print(
    "hosts",
    collections.Counter(re.sub(r"(https?://[^/]+).*", r"\1", f) for o in out for f in o[3].split(";") if f),
)
for o in out[-15:]:
    print(o[:3], o[3][:150])
with open(sys.argv[2], "w") as f:
    f.write("tipo\tnumero\tdata\tarquivos\n")
    for o in out:
        f.write("\t".join(o) + "\n")
