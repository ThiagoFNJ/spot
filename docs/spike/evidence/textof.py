import sys, re, html

t = open(sys.argv[1], encoding="utf-8", errors="ignore").read()
t = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", t, flags=re.S)
txt = html.unescape(re.sub(r"<[^>]+>", " ", t))
txt = re.sub(r"\s+", " ", txt)
if len(sys.argv) > 2:
    for m in re.finditer(sys.argv[2], txt, flags=re.I):
        print(
            "...",
            txt[
                max(0, m.start() - int(sys.argv[3]) if len(sys.argv) > 3 else m.start() - 200) : m.end()
                + (int(sys.argv[4]) if len(sys.argv) > 4 else 600)
            ],
            "\n",
        )
else:
    print(txt[: int(sys.argv[2]) if len(sys.argv) > 2 else 3000])
