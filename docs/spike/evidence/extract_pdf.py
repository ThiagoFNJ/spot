import sys
from pypdf import PdfReader

r = PdfReader(sys.argv[1])
n = int(sys.argv[2]) if len(sys.argv) > 2 else len(r.pages)
for i, p in enumerate(r.pages[:n]):
    print(f"--- page {i + 1} ---")
    print(p.extract_text())
