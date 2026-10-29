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
        if t == "tr":
            s.cur = []
        if t in ("td", "th") and s.cur is not None:
            s.cell = []

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
month = None
out = []
for r in p.rows:
    if len(r) >= 3 and r[0] == "Mês/Ano":
        month = r[-1]
        continue
    if len(r) == 4 and re.fullmatch(r"\d+", r[0]) and re.fullmatch(r"20\d\d", r[1]):
        out.append((month,) + tuple(r))
print("data rows", len(out))
print("STATUS", collections.Counter(o[4] for o in out))
print("rows per year", sorted(collections.Counter(o[2] for o in out).items()))
sess = collections.defaultdict(set)
for o in out:
    sess[o[2]].add(o[1])
print("distinct session numbers per year", {y: len(v) for y, v in sorted(sess.items())})
print("parlamentares total", len(set(o[3] for o in out)))
by = collections.defaultdict(collections.Counter)
for o in out:
    if o[2] == "2025":
        by[o[3]][o[4]] += 1
print("--- 2025 per parlamentar (Ausente desc) ---")
for n, c in sorted(by.items(), key=lambda x: -x[1]["Ausente"])[:12]:
    print(n, dict(c))
print("--- status x year ---")
sy = collections.defaultdict(collections.Counter)
for o in out:
    sy[o[2]][o[4]] += 1
for y in sorted(sy):
    print(y, dict(sy[y]))
with open(sys.argv[2], "w") as f:
    f.write("mes_ano\tnum_sessao\tano\tparlamentar\tstatus\n")
    for o in out:
        f.write("\t".join(o) + "\n")
