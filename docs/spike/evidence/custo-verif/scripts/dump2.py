import sys, pdfplumber

p = sys.argv[1]
a, b = map(int, sys.argv[2].split("-"))
with pdfplumber.open(p) as pdf:
    print("PAGES", len(pdf.pages))
    for i in range(a - 1, b):
        print(f"=== PAGE {i + 1} ===")
        print(pdf.pages[i].extract_text() or "")
