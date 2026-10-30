import pytest

from spot.parse.tse import TseError, build_silver, fold, ligar_pessoas


def cand(ano, sq, urna, nome, nasc, titulo, sit):
    return {
        "ano": str(ano),
        "SQ_CANDIDATO": sq,
        "NR_CANDIDATO": "1",
        "NM_URNA_CANDIDATO": urna,
        "NM_CANDIDATO": nome,
        "DT_NASCIMENTO": nasc,
        "NR_TITULO_ELEITORAL_CANDIDATO": titulo,
        "SG_PARTIDO": "X",
        "DS_SIT_TOT_TURNO": sit,
    }


ROWS = [
    # 1996 não tem título: liga por nome civil + nascimento
    cand(1996, "a", "TEO", "THEOFILO DE SENNA", "14/07/1958", "#NE", "ELEITO"),
    cand(2004, "b", "THEO", "THEOFILO DE SENNA", "14/07/1958", "039000000000", "MÉDIA"),
    # nome civil mudou, título igual
    cand(2024, "c", "THEO SENNA", "THEÓFILO V. DE SENNA", "14/07/1958", "039000000000", "ELEITO POR QP"),
    # homônimo com outra data de nascimento e outro título
    cand(2024, "d", "TEO", "THEOFILO DE SENNA", "01/01/1990", "111000000000", "SUPLENTE"),
]
DIM = [{"vereador_id": "teo-senna", "nome_parlamentar": "Téo Senna", "nome_civil": ""}]


def test_fold():
    assert fold("Dr. José  Antônio") == "dr jose antonio"


def test_ligar_pessoas_por_titulo_e_nome_nascimento():
    p = ligar_pessoas(ROWS)
    assert p[0] == p[1] == p[2] == "1996-a"
    assert p[3] == "2024-d"


def test_build_silver_conta_eleicoes_e_nao_grava_titulo():
    out = build_silver(ROWS, DIM, {"teo-senna": "1958-07-14"})
    teo = [r for r in out if r["vereador_id"] == "teo-senna"]
    assert [r["ano"] for r in teo if r["eleito"] == "true"] == ["1996", "2004", "2024"]
    assert all("titulo" not in k.lower() and "nasc" not in k.lower() for k in out[0])


def test_vereador_sem_candidatura_falha():
    with pytest.raises(TseError):
        build_silver(ROWS, [{"vereador_id": "x", "nome_parlamentar": "Fulano", "nome_civil": ""}], {})
