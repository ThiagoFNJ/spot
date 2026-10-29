import pdfplumber, re, sys, csv, collections

src = sys.argv[1]
out = sys.argv[2]
rows = []
rx = re.compile(
    r"^(\d+)\s+(.+?)\s+(\d+ - .+?)\s+(\d+ - .+?)\s+(\d{2}/\d{2}/\d{4})\s+(\d+ - .+?)\s+([\d.]+,\d{2})$"
)
skip = (
    "CAMARA MUNICIPAL",
    "CNPJ",
    "PRACA THOME",
    "CENTRO",
    "RELAÇÃO DE",
    "Filtros",
    "Matrícula",
    "Sistema Integrado",
    "Total de Registros",
    "Emissão",
)
with pdfplumber.open(src) as pdf:
    for p in pdf.pages:
        for line in (p.extract_text() or "").splitlines():
            l = line.strip()
            m = rx.match(l)
            if m:
                rows.append(list(m.groups()) + [""])
            elif rows and l and not l.startswith(skip):
                rows[-1][7] += " " + l  # wrapped text (name/função/lotação) kept separately
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(
        [
            "matricula",
            "servidor",
            "regime",
            "funcao",
            "admissao",
            "centro_custo",
            "total_proventos",
            "continuacao",
        ]
    )
    w.writerows(rows)
print("rows", len(rows), collections.Counter(r[2] for r in rows))
