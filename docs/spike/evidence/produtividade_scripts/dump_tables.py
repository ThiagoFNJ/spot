import sys, re, html
from html.parser import HTMLParser


class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.cur = None
        self.cell = None
        self.skip = 0
        self.selects = {}
        self.cursel = None
        self.links = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style"):
            self.skip += 1
        if tag == "tr":
            self.cur = []
        if tag in ("td", "th") and self.cur is not None:
            self.cell = []
        if tag == "select":
            self.cursel = a.get("name") or a.get("id")
            self.selects[self.cursel] = []
        if tag == "option" and self.cursel:
            self.selects[self.cursel].append(a.get("value", ""))
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip -= 1
        if tag in ("td", "th") and self.cell is not None and self.cur is not None:
            t = re.sub(r"\s+", " ", "".join(self.cell)).strip()
            if t:
                self.cur.append(t)
            self.cell = None
        if tag == "tr" and self.cur is not None:
            if self.cur:
                self.rows.append(self.cur)
            self.cur = None
        if tag == "select":
            self.cursel = None

    def handle_data(self, d):
        if self.skip == 0 and self.cell is not None:
            self.cell.append(d)


enc = sys.argv[2] if len(sys.argv) > 2 else "utf-8"
raw = open(sys.argv[1], "rb").read().decode(enc, "replace")
p = P()
p.feed(raw)
print("ROWS:", len(p.rows))
seen = set()
for r in p.rows:
    k = " | ".join(r)
    if k in seen or len(k) < 3:
        continue
    seen.add(k)
    print(k[:400])
print("\nSELECTS:")
for k, v in p.selects.items():
    print(k, len(v), v[:15])
print("\nLINKS (unique, first 40):")
u = []
for l in p.links:
    if l not in u and not l.startswith("#") and "javascript" not in l:
        u.append(l)
for l in u[:40]:
    print(l)
