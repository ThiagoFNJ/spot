import sys, re

path, enc, names = sys.argv[1], sys.argv[2], sys.argv[3:]
raw = open(path, encoding=enc, errors="replace").read()
for n in names:
    m = re.search(r"function\s+" + re.escape(n) + r"\s*\(", raw)
    if not m:
        print("### %s: NOT FOUND" % n)
        continue
    i = raw.find("{", m.end())
    depth = 0
    j = i
    while j < len(raw):
        if raw[j] == "{":
            depth += 1
        elif raw[j] == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    body = raw[m.start() : j + 1]
    body = re.sub(r"\n\s*\n", "\n", body)
    print("### %s (%d chars)" % (n, len(body)))
    print(body[:2500])
    print()
