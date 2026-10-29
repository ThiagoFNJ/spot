import sys, pdfplumber

p = sys.argv[1]
pages = sys.argv[2] if len(sys.argv) > 2 else None
with pdfplumber.open(p) as pdf:
    print("PAGES", len(pdf.pages), file=sys.stderr)
    rng = range(len(pdf.pages))
    if pages:
        a, b = pages.split("-")
        rng = range(int(a) - 1, int(b))
    for i in rng:
        t = pdf.pages[i].extract_text() or ""
        print(f"=== PAGE {i + 1} ===")
        print(t)
