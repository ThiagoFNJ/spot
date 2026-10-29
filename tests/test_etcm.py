"""Testes offline dos helpers puros de ``spot.collect.etcm`` (sem navegador, sem rede)."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from spot.collect import etcm


def test_playwright_nao_e_importado_ao_carregar_o_modulo() -> None:
    import sys

    assert "playwright.sync_api" not in sys.modules or etcm.coletar is not None
    # O módulo expõe tudo que a CLI precisa sem ter importado o Playwright no topo.
    assert "playwright" not in {m.split(".")[0] for m in vars(etcm) if not m.startswith("_")}


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("PP 2130 - VC - Debora Santos de Santana.pdf", "PP 2130 - VC - Debora Santos de Santana.pdf"),
        ("PP 1/2025 - VC - João\\Maria.pdf", "PP 1_2025 - VC - João_Maria.pdf"),
        ("  PP   2131 - VC - Randerson  Leal.pdf  ", "PP 2131 - VC - Randerson Leal.pdf"),
        ("..oculto.pdf.", "oculto.pdf"),
        ("", "_sem_nome"),
        ("///", "___"),
    ],
)
def test_sanitize_filename(nome: str, esperado: str) -> None:
    assert etcm.sanitize_filename(nome) == esperado


def test_iter_meses_cruza_ano() -> None:
    assert list(etcm.iter_meses("2025-11", "2026-02")) == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_iter_meses_um_mes_e_intervalo_invertido() -> None:
    assert list(etcm.iter_meses("2025-09", "2025-09")) == ["2025-09"]
    assert list(etcm.iter_meses("2025-10", "2025-09")) == []


def test_iter_meses_mvp_ate_mes_corrente() -> None:
    meses = list(etcm.iter_meses("2025-01", etcm.mes_corrente(date(2026, 10, 28))))
    assert meses[0] == "2025-01" and meses[-1] == "2026-10" and len(meses) == 22


def test_manifest_entry_e_append(tmp_path: Path) -> None:
    pdf = tmp_path / "2025-09" / "PP 2016 - VC - Mauricio Trindade.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"%PDF-1.4 fake")
    doc = etcm.Documento(nome="PP 2016 - VC - Mauricio Trindade.pdf", classificacao="PCMGE049 – Processos")
    entry = etcm.manifest_entry(pdf, doc, "2025-09", "VC")
    assert entry["nome"] == doc.nome
    assert entry["classificacao"] == doc.classificacao
    assert entry["bytes"] == len(b"%PDF-1.4 fake")
    assert entry["sha256"] == hashlib.sha256(b"%PDF-1.4 fake").hexdigest()
    assert entry["mes_prestacao"] == "2025-09"
    assert entry["filtro"] == "VC"
    assert entry["url"] == etcm.URL
    assert entry["coletado_em"].startswith("20")

    manifest = pdf.parent / "manifest.jsonl"
    etcm.append_manifest(manifest, entry)
    etcm.append_manifest(manifest, {**entry, "arquivo": "outro.pdf"})
    linhas = manifest.read_text("utf-8").splitlines()
    assert len(linhas) == 2
    assert json.loads(linhas[0]) == entry
    assert [e["arquivo"] for e in etcm.read_manifest(manifest)] == [pdf.name, "outro.pdf"]
    assert etcm.read_manifest(tmp_path / "nao-existe.jsonl") == []


def test_write_lista_inclui_todos_os_listados(tmp_path: Path) -> None:
    res = etcm.ResultadoMes(mes_prestacao="2025-09", filtro="VC", prestacao="09/2025 Gestão ...")
    res.listados = [
        etcm.Documento("PP 2013 - VC - B.pdf", "PCMGE049"),
        etcm.Documento("PP 2012 - VC - A.pdf", "PCMGE049"),
    ]
    res.baixados = ["PP 2012 - VC - A.pdf"]
    res.erros = ["PP 2013 - VC - B.pdf"]
    path = etcm.write_lista(tmp_path / "2025-09", res)
    assert path.name == "_lista_VC.json"
    payload = json.loads(path.read_text("utf-8"))
    assert payload["n_listados"] == 2
    assert [d["nome"] for d in payload["docs"]] == ["PP 2012 - VC - A.pdf", "PP 2013 - VC - B.pdf"]
    assert payload["baixados"] == ["PP 2012 - VC - A.pdf"]
    assert payload["erros"] == ["PP 2013 - VC - B.pdf"]
    assert payload["mes_prestacao"] == "2025-09" and payload["filtro"] == "VC"


def test_mes_dir() -> None:
    assert etcm.mes_dir(Path("/x"), "2025-09") == Path("/x/2025-09")
