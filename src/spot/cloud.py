"""Ligação do pipeline com o GCP: bronze no GCS (privado), silver e gold no GCS + BigQuery.

O pipeline continua trabalhando em ``data/`` (cache local); este módulo só sincroniza:

- ``push-bronze``: envia ao bucket privado do bronze os arquivos locais que faltam lá ou mudaram (md5). Nunca
  apaga nada no bucket; o bucket tem versionamento, então um ``--force`` de coleta guarda a versão anterior.
- ``pull-bronze``: baixa do bucket o que falta ou mudou localmente (para rodar ``make parse`` em outra máquina).
- ``publish``: lê ``data/silver/spot.duckdb``, separa as tabelas em silver (as que o build carrega de CSV:
  ``data/silver/*.csv`` + ``data/seeds/*.csv`` + ``presenca_mvp``) e gold (as que as métricas criam), grava cada uma
  em Parquet em ``gs://<bucket>/<tabela>/<tabela>.parquet``, carrega no BigQuery (``WRITE_TRUNCATE``) e envia o
  JSON do painel para ``gs://<bucket-gold>/site/data/``. Antes de enviar qualquer coisa, procura CPF e dados
  bancários em todas as colunas de texto e aborta se achar.

Quem contribui sem credencial roda tudo localmente e não precisa deste módulo.

CLI: ``uv run --extra gcp python -m spot.cloud {push-bronze,pull-bronze,publish} [--dry-run] [--only silver|gold]``.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import os
import subprocess
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from spot.build import DB_NAME, csv_tables
from spot.config import BRONZE, ROOT, SEEDS, SILVER

log = logging.getLogger(__name__)

PROJECT = os.environ.get("SPOT_GCP_PROJECT", "project-9122a143-6019-495b-93e")
BQ_LOCATION = os.environ.get("SPOT_BQ_LOCATION", "southamerica-east1")
BUCKETS = {
    "bronze": os.environ.get("SPOT_BUCKET_BRONZE", "spot-bronze-9122a143"),
    "silver": os.environ.get("SPOT_BUCKET_SILVER", "spot-silver-9122a143"),
    "gold": os.environ.get("SPOT_BUCKET_GOLD", "spot-gold-9122a143"),
}
DATASETS = {"silver": "spot_silver", "gold": "spot_gold"}
SITE_DATA = ROOT / "site" / "data"
# Tabelas que o build cria além dos CSVs e que são silver (limpeza, não métrica).
SILVER_DERIVADAS = {"presenca_mvp"}

# Padrões que nunca podem sair publicados. CPF só no formato pontuado (11 dígitos soltos colidem com números de
# processo); CPF/agência/conta com rótulo seguido de dígitos. Máscaras do parser (``***``) não casam.
PADROES_SENSIVEIS = {
    "cpf": r"\d{3}\.\d{3}\.\d{3}-\d{2}",
    "cpf_rotulado": r"(?i)c\W?pf\W{0,3}\d{5,}",
    "agencia_conta": r"(?i)(ag[êeé]ncia|conta corrente|c/c)\W{0,3}\d{3,}",
}


class SensitiveDataError(RuntimeError):
    """Dado sensível encontrado em tabela que seria publicada."""


@dataclass(frozen=True)
class Achado:
    tabela: str
    coluna: str
    padrao: str
    linhas: int


# ---------------------------------------------------------------- sincronização do bronze


def md5_b64(path: Path) -> str:
    """md5 em base64, o mesmo formato de ``Blob.md5_hash`` do GCS."""
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return base64.b64encode(h.digest()).decode()


def local_index(root: Path) -> dict[str, Path]:
    """``{caminho relativo com '/': Path}`` de todos os arquivos sob ``root`` (ignora ocultos do sistema)."""
    return {
        p.relative_to(root).as_posix(): p
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != ".DS_Store"
    }


def plan_transfer(origem: Mapping[str, str], destino: Mapping[str, str | None]) -> list[str]:
    """Chaves de ``origem`` que faltam no destino ou têm md5 diferente. Nunca propõe apagar."""
    return sorted(k for k, md5 in origem.items() if destino.get(k) != md5)


def _storage_client():
    from google.cloud import storage  # import tardio: só quem publica precisa do extra "gcp"

    return storage.Client(project=PROJECT)


def remote_index(bucket, prefix: str = "") -> dict[str, str | None]:
    return {b.name: b.md5_hash for b in bucket.list_blobs(prefix=prefix or None)}


def push_bronze(root: Path = BRONZE, dry_run: bool = False) -> list[str]:
    bucket = _storage_client().bucket(BUCKETS["bronze"])
    files = local_index(root)
    todo = plan_transfer({k: md5_b64(p) for k, p in files.items()}, remote_index(bucket))
    log.info("bronze: %d arquivos locais, %d a enviar para gs://%s", len(files), len(todo), bucket.name)
    for key in todo:
        if dry_run:
            log.info("[dry-run] enviaria %s", key)
            continue
        bucket.blob(key).upload_from_filename(str(files[key]))
        log.debug("enviado %s", key)
    return todo


def pull_bronze(root: Path = BRONZE, dry_run: bool = False, prefix: str = "") -> list[str]:
    bucket = _storage_client().bucket(BUCKETS["bronze"])
    remoto = {k: v for k, v in remote_index(bucket, prefix).items() if not k.endswith("/")}
    locais = local_index(root) if root.exists() else {}
    todo = plan_transfer(remoto, {k: md5_b64(p) for k, p in locais.items() if k in remoto})
    log.info("bronze: %d objetos no bucket, %d a baixar para %s", len(remoto), len(todo), root)
    for key in todo:
        if dry_run:
            log.info("[dry-run] baixaria %s", key)
            continue
        dest = root / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        bucket.blob(key).download_to_filename(str(dest))
    return todo


# ---------------------------------------------------------------- publicação de silver e gold


def camadas(
    con: duckdb.DuckDBPyConnection, silver: Path = SILVER, seeds: Path = SEEDS
) -> dict[str, list[str]]:
    """Separa as tabelas do banco: silver = carregadas de CSV + derivadas de limpeza; gold = o resto (métricas)."""
    tabelas = [r[0] for r in con.execute("SELECT table_name FROM duckdb_tables() ORDER BY 1").fetchall()]
    de_csv = set(csv_tables(silver, seeds)) | SILVER_DERIVADAS
    return {
        "silver": [t for t in tabelas if t in de_csv],
        "gold": [t for t in tabelas if t not in de_csv],
    }


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def find_sensitive(con: duckdb.DuckDBPyConnection, tabelas: Iterable[str]) -> list[Achado]:
    """Procura os ``PADROES_SENSIVEIS`` em toda coluna de texto e CPF com 11 dígitos em colunas com ``cpf`` no nome."""
    achados: list[Achado] = []
    for t in tabelas:
        cols = con.execute(
            "SELECT column_name, data_type FROM duckdb_columns() WHERE table_name = ? ORDER BY column_index",
            [t],
        ).fetchall()
        for col, tipo in cols:
            if "cpf" in col.lower():
                # coluna de documento: CNPJ (14 dígitos) e CPF mascarado (0 dígitos) passam; 11 dígitos visíveis não.
                q = f"SELECT count(*) FROM {_ident(t)} WHERE length(regexp_replace(CAST({_ident(col)} AS VARCHAR), '\\D', '', 'g')) = 11"
                (n,) = con.execute(q).fetchone()
                if n:
                    achados.append(Achado(t, col, "coluna_cpf", n))
            if tipo != "VARCHAR":
                continue
            for nome, rx in PADROES_SENSIVEIS.items():
                (n,) = con.execute(
                    f"SELECT count(*) FROM {_ident(t)} WHERE regexp_matches({_ident(col)}, ?)", [rx]
                ).fetchone()
                if n:
                    achados.append(Achado(t, col, nome, n))
    return achados


def _git_sha() -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def export_parquet(con: duckdb.DuckDBPyConnection, tabela: str, out_dir: Path) -> Path:
    path = out_dir / f"{tabela}.parquet"
    con.execute(f"COPY {_ident(tabela)} TO '{path.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
    return path


def _load_bigquery(bq, dataset: str, tabela: str, uri: str) -> int:
    from google.cloud import bigquery

    cfg = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    job = bq.load_table_from_uri(uri, f"{PROJECT}.{dataset}.{tabela}", job_config=cfg, location=BQ_LOCATION)
    job.result()
    return bq.get_table(f"{PROJECT}.{dataset}.{tabela}").num_rows


def publish(
    db_path: Path = SILVER / DB_NAME,
    camadas_alvo: tuple[str, ...] = ("silver", "gold"),
    dry_run: bool = False,
    site_data: Path = SITE_DATA,
) -> dict[str, dict[str, int]]:
    """Publica silver/gold. Devolve ``{camada: {tabela: linhas}}``."""
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        por_camada = camadas(con)
        alvo = {c: por_camada[c] for c in camadas_alvo}
        achados = find_sensitive(con, [t for ts in alvo.values() for t in ts])
        if achados:
            for a in achados:
                log.error("dado sensível: %s.%s (%s) em %d linhas", a.tabela, a.coluna, a.padrao, a.linhas)
            raise SensitiveDataError(f"{len(achados)} coluna(s) com CPF ou dado bancário; nada foi publicado")
        resumo: dict[str, dict[str, int]] = {}
        if dry_run:
            for camada, tabelas in alvo.items():
                resumo[camada] = {
                    t: con.execute(f"SELECT count(*) FROM {_ident(t)}").fetchone()[0] for t in tabelas
                }
                log.info("[dry-run] %s: %d tabelas -> gs://%s", camada, len(tabelas), BUCKETS[camada])
            return resumo
        from google.cloud import bigquery

        gcs, bq = _storage_client(), bigquery.Client(project=PROJECT, location=BQ_LOCATION)
        with tempfile.TemporaryDirectory() as tmp:
            for camada, tabelas in alvo.items():
                bucket = gcs.bucket(BUCKETS[camada])
                resumo[camada] = {}
                for t in tabelas:
                    pq = export_parquet(con, t, Path(tmp))
                    key = f"{t}/{t}.parquet"
                    bucket.blob(key).upload_from_filename(str(pq))
                    resumo[camada][t] = _load_bigquery(bq, DATASETS[camada], t, f"gs://{bucket.name}/{key}")
                    log.info("%s.%s: %d linhas", DATASETS[camada], t, resumo[camada][t])
                meta = {
                    "publicado_em": datetime.now(UTC).isoformat(timespec="seconds"),
                    "git_sha": _git_sha(),
                    "tabelas": resumo[camada],
                }
                bucket.blob("_publicacao.json").upload_from_string(
                    json.dumps(meta, ensure_ascii=False, indent=2), content_type="application/json"
                )
        if "gold" in alvo and site_data.exists():
            bucket = gcs.bucket(BUCKETS["gold"])
            for p in sorted(site_data.glob("*.json")):
                bucket.blob(f"site/data/{p.name}").upload_from_filename(
                    str(p), content_type="application/json"
                )
            log.info(
                "painel: %d JSON em gs://%s/site/data/", len(list(site_data.glob("*.json"))), bucket.name
            )
        return resumo
    finally:
        con.close()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Sincroniza o bronze e publica silver/gold no GCP")
    ap.add_argument("acao", choices=["push-bronze", "pull-bronze", "publish"])
    ap.add_argument(
        "--dry-run", action="store_true", help="só mostra o que faria (publish ainda roda a trava de CPF)"
    )
    ap.add_argument("--only", choices=["silver", "gold"], help="publish: só uma camada")
    ap.add_argument(
        "--prefix", default="", help="pull-bronze: só objetos com este prefixo (ex.: frequencia/)"
    )
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.acao == "push-bronze":
        push_bronze(dry_run=args.dry_run)
    elif args.acao == "pull-bronze":
        pull_bronze(dry_run=args.dry_run, prefix=args.prefix)
    else:
        publish(camadas_alvo=(args.only,) if args.only else ("silver", "gold"), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
