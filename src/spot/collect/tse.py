"""Coletor das candidaturas do TSE (Portal de Dados Abertos) para contar os mandatos de cada vereador.

Fonte: ``https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_<ano>.zip``, um ZIP
por eleição com um CSV por UF (``;``, latin-1, cabeçalho na 1ª linha). O resultado de cada candidatura
está em ``DS_SIT_TOT_TURNO`` (``ELEITO POR QP``, ``ELEITO POR MÉDIA``, ``SUPLENTE``, ``NÃO ELEITO``…).

Só o CSV da Bahia interessa (Salvador é ``SG_UE = 38490``). O ZIP inteiro tem de 26 a 140 MB por ano;
o bronze guarda só o membro ``consulta_cand_<ano>_BA.csv``, byte a byte, e o manifesto registra a URL e o
``sha256`` do ZIP de origem e do membro. O CSV traz número do título de eleitor, e-mail e, em anos antigos,
CPF: fica no bronze privado e nunca passa para o silver (ver ``parse/tse.py``).

Eleições municipais de 1996 a 2024. Idempotente: ano já baixado não é refeito. O TSE regera os arquivos
(``DT_GERACAO``), então o ``sha256`` muda entre coletas mesmo sem mudança de conteúdo.

CLI: ``uv run python -m spot.collect.tse [--anos 2016,2020,2024] [-v]``.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import sys
import time
import zipfile
from pathlib import Path

from spot.config import BRONZE
from spot.scriptcase import Client

log = logging.getLogger(__name__)

TSE_CDN = "https://cdn.tse.jus.br"
URL = TSE_CDN + "/estatistica/sead/odsele/consulta_cand/consulta_cand_{ano}.zip"
ANOS = (1996, 2000, 2004, 2008, 2012, 2016, 2020, 2024)
UF = "BA"
BRONZE_TSE = BRONZE / "tse"


def nome_arquivo(ano: int) -> str:
    return f"consulta_cand_{ano}_{UF}.csv"


def coletar_ano(client: Client, ano: int, dir_: Path = BRONZE_TSE) -> Path:
    """Baixa o ZIP do ano e grava só o CSV da UF, com uma linha no manifest.jsonl."""
    dest = dir_ / nome_arquivo(ano)
    if dest.exists():
        log.info("já existe, não refaço: %s", dest)
        return dest
    url = URL.format(ano=ano)
    resp = client.request("GET", url, timeout=600)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        membro = next(n for n in zf.namelist() if n.upper().endswith(f"_{UF}.CSV"))
        dados = zf.read(membro)
    dir_.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(dados)
    entry = {
        "file": dest.name,
        "url": url,
        "method": "GET",
        "params": {"ano": ano, "uf": UF, "membro_zip": membro},
        "status": resp.status,
        "zip_bytes": len(resp.content),
        "zip_sha256": resp.sha256,
        "bytes": len(dados),
        "sha256": hashlib.sha256(dados).hexdigest(),
        "seconds": round(resp.seconds, 3),
        "coletado_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    with (dir_ / "manifest.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    log.info("%s: %d bytes (ZIP de %d bytes)", dest.name, len(dados), len(resp.content))
    return dest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Baixa as candidaturas do TSE (CSV da Bahia) por eleição municipal."
    )
    ap.add_argument("--anos", default=",".join(map(str, ANOS)), help="eleições separadas por vírgula")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    with Client(host=TSE_CDN, timeout=600) as client:
        for ano in (int(a) for a in args.anos.split(",")):
            coletar_ano(client, ano)
    return 0


if __name__ == "__main__":
    sys.exit(main())
