import sys, re

t = open(sys.argv[1], encoding="utf-8", errors="ignore").read()
for h, txt in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', t, flags=re.S):
    txt = re.sub(r"<[^>]+>", "", txt).strip()
    if re.search(sys.argv[2], h + " " + txt, flags=re.I):
        print(h, "|", txt[:80])
