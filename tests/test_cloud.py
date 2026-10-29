"""Testes offline de ``spot.cloud``: plano de sincronização, separação de camadas e trava de dados sensíveis."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from spot import cloud


def test_md5_b64_formato_do_gcs(tmp_path: Path) -> None:
    p = tmp_path / "a.txt"
    p.write_bytes(b"spot")
    # md5("spot") em base64, como Blob.md5_hash
    assert cloud.md5_b64(p) == "suGJq/hegJpRUizbDlMIOg=="


def test_plan_transfer_envia_faltantes_e_alterados_nunca_apaga() -> None:
    origem = {"a.csv": "x", "b.csv": "y", "c.csv": "z"}
    destino = {"a.csv": "x", "b.csv": "OUTRO", "so_no_destino.csv": "w"}
    assert cloud.plan_transfer(origem, destino) == ["b.csv", "c.csv"]


def test_local_index_relativo_e_ignora_ds_store(tmp_path: Path) -> None:
    (tmp_path / "frequencia").mkdir()
    (tmp_path / "frequencia" / "2025-03_tipo1.csv").write_text("x")
    (tmp_path / ".DS_Store").write_text("x")
    assert list(cloud.local_index(tmp_path)) == ["frequencia/2025-03_tipo1.csv"]


@pytest.fixture
def con(tmp_path: Path):
    silver, seeds = tmp_path / "silver", tmp_path / "seeds"
    silver.mkdir()
    seeds.mkdir()
    (silver / "presenca.csv").write_text("x\n1\n")
    (seeds / "vereador_dim.csv").write_text("x\n1\n")
    c = duckdb.connect()
    for t in ("presenca", "vereador_dim", "presenca_mvp", "metrica_presenca", "custo_institucional"):
        c.execute(f"CREATE TABLE {t} (x INT)")
    yield c, silver, seeds
    c.close()


def test_camadas_silver_vem_de_csv_gold_e_o_resto(con) -> None:
    c, silver, seeds = con
    assert cloud.camadas(c, silver, seeds) == {
        "silver": ["presenca", "presenca_mvp", "vereador_dim"],
        "gold": ["custo_institucional", "metrica_presenca"],
    }


def test_find_sensitive_bloqueia_cpf_e_banco_mas_aceita_mascara_e_cnpj() -> None:
    c = duckdb.connect()
    c.execute("CREATE TABLE empenho (credor VARCHAR, cnpj_cpf VARCHAR, n INT)")
    c.execute(
        "INSERT INTO empenho VALUES ('Fulana', '***.***.***-**', 1), ('Empresa', '01.736.132/0001-49', 2), "
        "('Beltrano', '123.456.789-01', 3)"
    )
    c.execute("CREATE TABLE verba (texto VARCHAR)")
    c.execute("INSERT INTO verba VALUES ('Agência: 1234 Conta Corrente: ****'), ('Cpf. 12345678901, Mat. 1')")
    c.execute("CREATE TABLE limpa (texto VARCHAR)")
    c.execute("INSERT INTO limpa VALUES ('PLE-232/2025 aprovado'), ('processo 12345678901234')")
    achados = {(a.tabela, a.coluna, a.padrao) for a in cloud.find_sensitive(c, ["empenho", "verba", "limpa"])}
    assert achados == {
        ("empenho", "cnpj_cpf", "coluna_cpf"),
        ("empenho", "cnpj_cpf", "cpf"),
        ("verba", "texto", "agencia_conta"),
        ("verba", "texto", "cpf_rotulado"),
    }
