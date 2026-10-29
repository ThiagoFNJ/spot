import pdfplumber, sys

src = sys.argv[1]
first = int(sys.argv[2]) if len(sys.argv) > 2 else 1
last = int(sys.argv[3]) if len(sys.argv) > 3 else None
with pdfplumber.open(src) as pdf:
    n = len(pdf.pages)
    last = last or n
    sys.stderr.write(f"pages={n}\n")
    for i in range(first - 1, min(last, n)):
        t = pdf.pages[i].extract_text() or ""
        print(f"\n===== PAGE {i + 1} =====\n" + t)
