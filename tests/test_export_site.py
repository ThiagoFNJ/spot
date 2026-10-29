"""Helpers puros de ``spot.export_site`` (sem DuckDB): cargo na Mesa, grade de presença, meses parciais, ata."""

from __future__ import annotations

import pytest

from spot import export_site as es


@pytest.mark.parametrize(
    ("label", "esperado"),
    [
        # rótulos reais de folha.centro_custo_label (2025–2026)
        ("3ª VICE-PRESIDÊNCIA - GAB. VER. SIDNINHO", "3ª Vice-Presidência"),
        ("1ª VICE-PRESIDENCIA - GAB. VER. MAURICIO TRINDADE", "1ª Vice-Presidência"),
        ("2ª VICE-PRESIDÊNCIA - GAB. VER. EDUARDO SANCHES (DUDA SANCHES) - 0110", "2ª Vice-Presidência"),
        ("PRESIDENCIA - GAB. VER. CARLOS MUNIZ", "Presidência"),
        ("1ª SECRETARIA - GAB. VER. CLAUDIO TINOCO", "1ª Secretaria"),
        ("4ª SECRETARIA - GAB. VER. KEL TORRES", "4ª Secretaria"),
        ("CORRREGEDORIA - GAB. VER. ALEXANDRE ALELUIA", "Corregedoria"),  # três R na fonte
        ("OUVIDORIA SUBSTITUTA - GAB. VER. ANDERSON NINHO", "Ouvidoria substituta"),
        (
            "DIRETORIA DA ESCOLA DO LEGISLATIVO - GAB. VER. MARTA RODRIGUES",
            "Diretoria da Escola do Legislativo",
        ),
        ("10679962 - 3ª VICE-PRESIDÊNCIA - GAB. VER. X", "3ª Vice-Presidência"),  # com código na frente
        ("GAB. VER. ALEX ALEMAO", None),
        ("GAB. VER. SILVIO HUMBERTO - 0124", None),
        ("GAB. VER. EVERALDO LOPES BECA (SUP. LUIZ CARLOS DE SOUZA)", None),
        ("GABINETE DA PRESIDENCIA", None),  # estrutura, não é gabinete de vereador
        ("", None),
        (None, None),
    ],
)
def test_cargo_mesa(label: str | None, esperado: str | None) -> None:
    assert es.cargo_mesa(label) == esperado


def test_primeira_url() -> None:
    assert es.primeira_url(None) is None and es.primeira_url("") is None
    assert es.primeira_url("http://a/1.pdf") == "http://a/1.pdf"
    assert es.primeira_url("http://a/1.pdf|http://a/2.pdf") == "http://a/1.pdf"
    assert es.primeira_url(" http://a/1.pdf ; http://a/2.pdf") == "http://a/1.pdf"
    assert es.primeira_url(["http://a/1.pdf", "http://a/2.pdf"]) == "http://a/1.pdf"


def test_compactar_grade(caplog: pytest.LogCaptureFixture) -> None:
    cells = [
        {"vereador_id": "b", "ano": 2025, "num_sessao": 3, "status": "Ausente"},
        {"vereador_id": "a", "ano": 2025, "num_sessao": 2, "status": "Presente"},
        {"vereador_id": "a", "ano": 2025, "num_sessao": 1, "status": "Presente"},
        {"vereador_id": "a", "ano": 2026, "num_sessao": 1, "status": "Licenciado"},
        {"vereador_id": "a", "ano": 2025, "num_sessao": 10, "status": "Justificado"},
    ]
    grade = es.compactar_grade(cells)
    assert grade == [
        {"v": "a", "ano": 2025, "n": [1, 2, 10], "s": "PP?"},
        {"v": "a", "ano": 2026, "n": [1], "s": "L"},
        {"v": "b", "ano": 2025, "n": [3], "s": "A"},
    ]
    assert all(len(g["n"]) == len(g["s"]) for g in grade)
    assert "Justificado" in caplog.text
    assert es.compactar_grade([]) == []


def test_marcar_parciais_mediana_e_extra() -> None:
    rows = [
        {"competencia": "2026-01", "ano": 2026, "n": 1191, "sub": 1},
        {"competencia": "2026-02", "ano": 2026, "n": 1189, "sub": 42},
        {"competencia": "2026-03", "ano": 2026, "n": 900, "sub": 42},  # < 80% da mediana (~1190)
        {"competencia": "2026-04", "ano": 2026, "n": None, "sub": None},  # nulo: só via extra
        {"competencia": "2025-12", "ano": 2025, "n": 1000, "sub": 42},  # outro grupo: mediana própria
    ]
    n = es.marcar_parciais(
        rows, "n", lambda r: r["ano"], extra=lambda r: r["sub"] is not None and r["sub"] < 30
    )
    assert n == 2
    assert [r["parcial"] for r in rows] == [True, False, True, False, False]
    assert all(isinstance(r["parcial"], bool) for r in rows)


def test_marcar_parciais_sem_extra_e_limiar() -> None:
    rows = [{"g": 1, "n": 10}, {"g": 1, "n": 10}, {"g": 1, "n": 8}]
    assert es.marcar_parciais(rows, "n", lambda r: r["g"]) == 0  # 8 ≥ 0,8 × 10
    assert es.marcar_parciais(rows, "n", lambda r: r["g"], limiar=0.9) == 1
    assert rows[2]["parcial"] is True


# ---- diárias (b16) e rubricas (b13) ------------------------------------------------------------------------------


def test_diaria_objeto_mascara_cpf_normaliza_e_corta() -> None:
    assert (
        es.diaria_objeto("DIÁRIAS  PARA   BRASÍLIA,\nCPF 123.456.789-00.")
        == "DIÁRIAS PARA BRASÍLIA, CPF ***.***.***-**."
    )
    assert es.diaria_objeto(None) == "" and es.diaria_objeto("  ") == ""
    longo = "X" * 250
    cortado = es.diaria_objeto(longo)
    assert len(cortado) == 200 and cortado.endswith("…") and cortado[:199] == "X" * 199
    assert es.diaria_objeto("Y" * 200) == "Y" * 200  # no limite não corta
    assert es.diaria_objeto("A B", limite=2) == "A…"


def test_resumo_diarias_liquido_de_anulacoes_e_por_vereador() -> None:
    rows = [
        {"ano": 2025, "valor": 100.0, "anulacao": False, "vereador_id": None},
        {"ano": 2025, "valor": 40.0, "anulacao": True, "vereador_id": None},
        {"ano": 2026, "valor": 1400.0, "anulacao": False, "vereador_id": "helio-ferreira"},
        {"ano": 2026, "valor": 250.5, "anulacao": False, "vereador_id": None},
        {"ano": 2024, "valor": 1.0, "anulacao": False, "vereador_id": ""},
    ]
    assert es.resumo_diarias(rows) == [
        {"ano": 2024, "n": 1, "total": 1.0, "n_vereador": 0, "total_vereador": 0.0},
        {"ano": 2025, "n": 2, "total": 60.0, "n_vereador": 0, "total_vereador": 0.0},
        {"ano": 2026, "n": 2, "total": 1650.5, "n_vereador": 1, "total_vereador": 1400.0},
    ]
    assert es.resumo_diarias([]) == []


def _rub(rubrica: str, valor: float, natureza: str = "remuneracao", tipo: str | None = "Normal") -> dict:
    return {
        "competencia": "2025-12",
        "grupo_regime": "Estatutário",
        "tipo_folha": tipo,
        "rubrica_codigo": hash(rubrica) % 1000,
        "rubrica": rubrica,
        "natureza": natureza,
        "qtd": 10,
        "valor": valor,
    }


def test_agregar_rubricas_pequenas() -> None:
    rows = [
        _rub("Vencimento", 900.0),
        _rub("Gratificação", 96.0),
        _rub("Jeton", 3.0),  # 0,3% do grupo remuneração (999 + ... ) → Outras
        _rub("Auxílio", 1.0),  # idem
        _rub("IRRF", 50.0, "desconto"),  # grupo desconto: 100% → fica
        _rub("Férias", 100.0, tipo="Férias"),  # outro tipo: grupo próprio → fica
        _rub("Nulo", 0.0, tipo="Férias"),  # 0 < 0,5% de 100 → Outras do grupo Férias
    ]
    out = es.agregar_rubricas_pequenas(rows)
    assert [r["rubrica"] for r in out] == ["Vencimento", "Gratificação", "Outras", "IRRF", "Férias", "Outras"]
    outras = out[2]
    assert (outras["valor"], outras["outras"], outras["qtd"], outras["rubrica_codigo"]) == (
        4.0,
        2,
        None,
        None,
    )
    assert (outras["tipo_folha"], outras["natureza"]) == ("Normal", "remuneracao")
    assert out[5] == {**_rub("Outras", 0.0, tipo="Férias"), "rubrica_codigo": None, "qtd": None, "outras": 1}
    # totais preservados por grupo
    assert (
        round(
            sum(r["valor"] for r in out if r["natureza"] == "remuneracao" and r["tipo_folha"] == "Normal"), 2
        )
        == 1000.0
    )
    assert es.agregar_rubricas_pequenas([]) == []
    assert es.agregar_rubricas_pequenas(rows, limiar=0.0) == rows  # nada abaixo de 0
