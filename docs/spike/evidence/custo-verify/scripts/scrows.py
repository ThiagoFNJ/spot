import re, sys, html, collections

f = sys.argv[1]
kw = sys.argv[2] if len(sys.argv) > 2 else None
h = open(f, encoding="utf-8", errors="replace").read()
fields = collections.OrderedDict()
for m in re.finditer(r'id="id_sc_field_([a-zA-Z0-9_]+?)_(\d+)"[^>]*>(.*?)</span>', h, re.S):
    name, idx, val = (
        m.group(1),
        int(m.group(2)),
        re.sub(r"<[^>]+>|\s+", " ", html.unescape(m.group(3))).strip(),
    )
    fields.setdefault(idx, {})[name] = val
print("n rows", len(fields))
if fields:
    print("columns:", list(next(iter(fields.values())).keys()))
for idx, row in fields.items():
    s = " | ".join(f"{k}={v[:70]}" for k, v in row.items())
    if kw is None or kw.lower() in s.lower():
        print(idx, ":", s[:400])
