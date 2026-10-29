"""Folhas sintéticas do e-TCM (classes PCMGE035/048). Fixture: palavras (texto mascarado) das páginas
"Resumo - Geral" do PP 470/2026 (Cargo em Comissão + Assistência Militar, março/2026), geradas com
pdfplumber.extract_words(x_tolerance=2, y_tolerance=3) e `mascarar_sensiveis` no texto."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from spot.parse import etcm_folha as m

FIX = Path(__file__).parent / "fixtures" / "etcm_folha_pp470.words.json"


@pytest.fixture(scope="module")
def pages() -> list[dict]:
    return json.loads(FIX.read_text(encoding="utf-8"))


def test_fixture_sem_cpf(pages: list[dict]) -> None:
    import re

    txt = " ".join(w["text"] for p in pages for w in p["words"])
    assert not re.search(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}", txt)


def test_pagina_cargo_em_comissao(pages: list[dict]) -> None:
    assert m.is_resumo_page(pages[0]["words"])
    folha, fechou = m.parse_pagina(pages[0]["words"])
    assert fechou
    assert (folha.folha_id, folha.competencia, folha.tipo_folha, folha.numero_folha) == (
        "031",
        "2026-03",
        "Normal",
        "1",
    )
    assert folha.grupo_regime == "Cargo em comissão"
    assert folha.total_servidores == 821
    assert folha.total_remuneracao == Decimal("5930768.54")
    assert folha.total_descontos == Decimal("1290151.88")
    assert folha.liquido == Decimal("4640616.66")
    assert folha.soma == (Decimal("5930768.54"), Decimal("1290151.88"))
    assert folha.confianca == "alta"
    rem = {r.descricao: (r.codigo, r.qtd, r.valor) for r in folha.rubricas if r.natureza == "remuneracao"}
    assert rem["Cargeom Comissao"] == ("3", 816, Decimal("5098266.16"))  # OCR do "Cargo em Comissao"
    assert rem["Acrescimo Salarial"] == ("352", 129, Decimal("747072.36"))
    des = {r.descricao: (r.codigo, r.qtd, r.valor) for r in folha.rubricas if r.natureza == "desconto"}
    assert des["INSS"] == ("397", 815, Decimal("541155.50"))
    assert des["BANCO SANTANDER S.A."] == ("", 6, Decimal("12744.35"))
    assert des["Bloqueio judicial2"] == ("546", 1, Decimal("800.00"))  # "3" do carimbo lateral ignorado


def test_pagina_assistencia_militar(pages: list[dict]) -> None:
    folha, fechou = m.parse_pagina(pages[1]["words"])
    assert fechou and folha.grupo_regime == "Assistência militar" and folha.folha_id == "032"
    assert folha.total_servidores == 91 and folha.total_remuneracao == Decimal("221278.71")
    assert folha.total_descontos == Decimal("0.00") and folha.liquido == Decimal(
        "221278.71"
    )  # "221.278.71" no OCR
    assert [(r.codigo, r.descricao, r.qtd, r.valor) for r in folha.rubricas] == [
        ("153", "Complemento Soldo", 91, Decimal("221278.71"))
    ]
    assert folha.confianca == "alta"


def test_rows(pages: list[dict]) -> None:
    folhas = [m.parse_pagina(p["words"])[0] for p in pages]
    rubs, res = m.rows_de(folhas, "2026-03", "PP 470 Fl. Pagamento - Cargo em Comissão - Fl. Sintética.pdf")
    assert [list(r) for r in rubs] == [m.RUBRICA_COLUMNS] * len(rubs) and len(rubs) == 14
    assert [list(r) for r in res] == [m.RESUMO_COLUMNS] * 2
    assert (
        res[0]["pp_numero"] == "470"
        and res[0]["soma_remuneracao"] == "5930768.54"
        and res[0]["confianca"] == "alta"
    )


@pytest.mark.parametrize(
    "raw, esperado",
    [
        ("CARGO EM COMISSÃO", "Cargo em comissão"),
        ("Cargo Em Comissao", "Cargo em comissão"),
        ("Estatutário", "Estatutário"),
        ("Agente Político", "Agente político"),
        ("ESTAGIARIO", "Estagiário"),
        ("ASSISTÊNCIA MILITAR", "Assistência militar"),
        ("Outro Grupo", "Outro Grupo"),
    ],
)
def test_grupo_regime_canonico(raw: str, esperado: str) -> None:
    assert m.grupo_regime_canonico(raw) == esperado


@pytest.mark.parametrize(
    "raw, esperado",
    [
        ("Normal", "Normal"),
        ("Complementar", "Complementar"),
        ("Férias", "Férias"),
        ("F", "Férias"),
        ("Rescisão", "Rescisão"),
        ("Adiantamento", "Adiantamento 13º"),
    ],
)
def test_tipo_folha_canonico(raw: str, esperado: str) -> None:
    assert m.tipo_folha_canonico(raw) == esperado


def test_arquivos_de_folha_por_manifest(tmp_path: Path) -> None:
    (tmp_path / "PP 470 Fl. Pagamento - Cargo em Comissão - Fl. Sintética.pdf").write_bytes(b"%PDF")
    (tmp_path / "PP 325 - VC - Marcelo Neto.pdf").write_bytes(b"%PDF")
    (tmp_path / "PP 304 W4 Comunicação.pdf").write_bytes(b"%PDF")
    man = [
        {
            "arquivo": "PP 470 Fl. Pagamento - Cargo em Comissão - Fl. Sintética.pdf",
            "classificacao": "PCMGE035 – Processos de pagamento - folha",
        },
        {"arquivo": "PP 325 - VC - Marcelo Neto.pdf", "classificacao": "PCMGE049 – Processos de pagamento"},
        {"arquivo": "PP 304 W4 Comunicação.pdf", "classificacao": "PCMGE049 – Processos de pagamento"},
    ]
    (tmp_path / "manifest.jsonl").write_text("\n".join(json.dumps(e) for e in man), encoding="utf-8")
    assert [p.name for p in m.arquivos_de_folha(tmp_path)] == [
        "PP 470 Fl. Pagamento - Cargo em Comissão - Fl. Sintética.pdf"
    ]


def test_grupo_todos_vem_do_nome_do_processo() -> None:
    f = m.Folha(
        grupo_regime="(Todos)",
        rubricas=[m.Rubrica("4", "Subsidio", 41, Decimal("1069320.18"), "remuneracao")],
    )
    assert (
        m.grupo_por_contexto(f, "PP 1744 Folha de Pgto. - Agentes Políticos (Fl. Sintética).pdf")
        == "Agente político"
    )
    assert (
        m.grupo_por_contexto(
            m.Folha(grupo_regime="(Todos)"), "PP 1746 Folha de Pgto. - Cargo em Comissão (Fl. Sintética).pdf"
        )
        == "Cargo em comissão"
    )
    assert m.grupo_por_contexto(f, "PP 9 Folha.pdf") == "Agente político"  # pela rubrica
    assert (
        m.grupo_por_contexto(m.Folha(grupo_regime="Estatutário"), "PP 1744 Agentes Políticos.pdf")
        == "Estatutário"
    )
