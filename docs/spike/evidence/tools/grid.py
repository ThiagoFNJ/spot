import sys, re, html
from html.parser import HTMLParser

raw = open(sys.argv[1], "rb").read().decode("iso-8859-1", "replace")
raw = re.sub(r"(?is)<(script|style).*?</\1>", "", raw)


class P(HTMLParser):
    def __init__(s):
        super().__init__()
        s.rows = []
        s.cur = None
        s.cell = None
        s.links = []

    def handle_starttag(s, t, a):
        a = dict(a)
        if t == "tr":
            s.cur = []
        if t in ("td", "th") and s.cur is not None:
            s.cell = []
        if t == "a" and s.cell is not None and a.get("href"):
            s.cell.append("{" + a["href"][:160] + "}")

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
maxrows = int(sys.argv[2]) if len(sys.argv) > 2 else 80
for r in p.rows[:maxrows]:
    print(" | ".join(r)[:400])
print("TOTAL ROWS", len(p.rows))
