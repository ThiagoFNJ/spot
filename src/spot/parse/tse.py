"""Parser das candidaturas do TSE: bronze (CSV da Bahia por eleição) -> silver das candidaturas a vereador de Salvador.

Entrada (sem rede): ``data/bronze/tse/consulta_cand_<ano>_BA.csv`` (``;``, latin-1), de ``collect/tse.py``.

Saída: ``data/silver/tse_candidatura_vereador.csv``, uma linha por candidatura a vereador em Salvador
(``SG_UE = 38490``), com ``eleito`` (``ELEITO``, ``ELEITO POR QP``, ``ELEITO POR MÉDIA`` e o ``MÉDIA`` de
2004/2008), ``pessoa_id`` e ``vereador_id`` quando a pessoa é um dos vereadores da legislatura 2025–2028.

Ligação entre eleições: a mesma pessoa tem um ``SQ_CANDIDATO`` novo a cada eleição. Duas candidaturas são da
mesma pessoa quando têm o mesmo número de título de eleitor (presente de 2000 em diante) ou o mesmo nome civil
com a mesma data de nascimento (1996 não tem título). ``pessoa_id`` é ``<ano>-<SQ_CANDIDATO>`` da primeira
candidatura da pessoa. Título, CPF, e-mail e data de nascimento ficam só no bronze: o silver não os grava.

Ligação com ``vereador_id``: pela candidatura de 2024, na ordem nome de urna = ``nome_parlamentar`` do seed,
nome civil = ``nome_civil`` do seed, data de nascimento do perfil (``data/silver/vereadores.csv``); vale o
primeiro critério que achar exatamente uma candidatura. Vereador sem candidatura em 2024 é erro.

CLI: ``uv run python -m spot.parse.tse``.
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import unicodedata
from collections.abc import Iterable
from pathlib import Path

from spot.collect.tse import ANOS, BRONZE_TSE, nome_arquivo
from spot.config import SEEDS, SILVER

log = logging.getLogger(__name__)

SALVADOR = "38490"
ELEITO = {"ELEITO", "ELEITO POR QP", "ELEITO POR MÉDIA", "MÉDIA"}
ANO_LEGISLATURA = 2024
SILVER_CSV = SILVER / "tse_candidatura_vereador.csv"
COLS = [
    "ano",
    "sq_candidato",
    "nr_candidato",
    "nome_urna",
    "nome_candidato",
    "sg_partido",
    "situacao",
    "eleito",
    "pessoa_id",
    "vereador_id",
]


class TseError(RuntimeError):
    """Vereador da legislatura sem candidatura identificável em 2024."""


def fold(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s or "")
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c)).casefold()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", sem_acento).split())


def ler_candidaturas(bronze: Path = BRONZE_TSE, anos: Iterable[int] = ANOS) -> list[dict[str, str]]:
    """Candidaturas a vereador em Salvador, com as colunas originais do TSE e ``ano``."""
    rows: list[dict[str, str]] = []
    for ano in anos:
        path = bronze / nome_arquivo(ano)
        with path.open(encoding="latin-1", newline="") as f:
            for r in csv.DictReader(f, delimiter=";"):
                if r["SG_UE"] == SALVADOR and r["DS_CARGO"].upper() == "VEREADOR":
                    r["ano"] = str(ano)
                    rows.append(r)
    return rows


def ligar_pessoas(rows: list[dict[str, str]]) -> list[str]:
    """``pessoa_id`` de cada linha (mesmo índice), unindo por título de eleitor ou nome civil + nascimento."""
    pai = list(range(len(rows)))

    def raiz(i: int) -> int:
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i

    vistos: dict[tuple[str, str], int] = {}
    for i, r in enumerate(rows):
        titulo = r.get("NR_TITULO_ELEITORAL_CANDIDATO", "")
        chaves = [("nome_nasc", fold(r["NM_CANDIDATO"]) + "|" + r["DT_NASCIMENTO"])]
        if titulo.isdigit() and int(titulo):
            chaves.append(("titulo", titulo))
        for k in chaves:
            if k in vistos:
                pai[raiz(i)] = raiz(vistos[k])
            else:
                vistos[k] = i
    primeira: dict[int, int] = {}
    for i, r in enumerate(rows):
        g = raiz(i)
        if g not in primeira or int(r["ano"]) < int(rows[primeira[g]]["ano"]):
            primeira[g] = i
    return [
        f"{rows[primeira[raiz(i)]]['ano']}-{rows[primeira[raiz(i)]]['SQ_CANDIDATO']}"
        for i in range(len(rows))
    ]


def ligar_vereadores(
    rows: list[dict[str, str]], dim: list[dict[str, str]], nascimento: dict[str, str]
) -> dict[int, str]:
    """``{índice da candidatura de 2024: vereador_id}`` para cada vereador do seed."""
    r24 = [i for i, r in enumerate(rows) if int(r["ano"]) == ANO_LEGISLATURA]
    out: dict[int, str] = {}
    for d in dim:
        nasc = nascimento.get(d["vereador_id"], "")
        nasc_br = "/".join(reversed(nasc.split("-"))) if nasc else ""
        # (coluna do TSE, valor esperado já normalizado); critério com valor vazio é pulado
        criterios = [
            ("NM_URNA_CANDIDATO", fold(d["nome_parlamentar"])),
            ("NM_CANDIDATO", fold(d["nome_civil"])),
            ("DT_NASCIMENTO", nasc_br),
        ]
        for coluna, alvo in criterios:
            if not alvo:
                continue
            norm = (lambda x: x) if coluna == "DT_NASCIMENTO" else fold
            achados = [i for i in r24 if norm(rows[i][coluna]) == alvo]
            if len(achados) == 1:
                out[achados[0]] = d["vereador_id"]
                break
        else:
            raise TseError(f"{d['vereador_id']}: nenhuma candidatura única em {ANO_LEGISLATURA}")
    return out


def build_silver(
    rows: list[dict[str, str]], dim: list[dict[str, str]], nascimento: dict[str, str]
) -> list[dict[str, str]]:
    pessoas = ligar_pessoas(rows)
    por_vereador = ligar_vereadores(rows, dim, nascimento)
    vereador_da_pessoa = {pessoas[i]: v for i, v in por_vereador.items()}
    out = [
        {
            "ano": r["ano"],
            "sq_candidato": r["SQ_CANDIDATO"],
            "nr_candidato": r["NR_CANDIDATO"],
            "nome_urna": r["NM_URNA_CANDIDATO"],
            "nome_candidato": r["NM_CANDIDATO"],
            "sg_partido": r["SG_PARTIDO"],
            "situacao": r["DS_SIT_TOT_TURNO"],
            "eleito": str(r["DS_SIT_TOT_TURNO"] in ELEITO).lower(),
            "pessoa_id": pessoas[i],
            "vereador_id": vereador_da_pessoa.get(pessoas[i], ""),
        }
        for i, r in enumerate(rows)
    ]
    return sorted(out, key=lambda r: (int(r["ano"]), r["nome_urna"]))


def ler_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TSE (bronze) -> silver/tse_candidatura_vereador.csv")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    dim = ler_csv(SEEDS / "vereador_dim.csv")
    nascimento = {r["vereador_id"]: r["nascimento"] for r in ler_csv(SILVER / "vereadores.csv")}
    out = build_silver(ler_candidaturas(), dim, nascimento)
    with SILVER_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(out)
    n_ver = len({r["vereador_id"] for r in out if r["vereador_id"]})
    log.info("%d candidaturas, %d vereadores ligados -> %s", len(out), n_ver, SILVER_CSV)
    return 0


if __name__ == "__main__":
    sys.exit(main())
