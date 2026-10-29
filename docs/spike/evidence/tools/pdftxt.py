import sys, fitz

doc = fitz.open(sys.argv[1])
maxp = int(sys.argv[2]) if len(sys.argv) > 2 else len(doc)
out = []
for i, p in enumerate(doc):
    if i >= maxp:
        break
    out.append(f"\n=== PAGE {i + 1} ===\n" + p.get_text())
print(f"PAGES {len(doc)}")
print("".join(out))
