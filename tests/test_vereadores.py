"""Testes offline da dimensão de vereadores: parser (fixtures) + integridade dos seeds."""

from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path

import pytest

from spot.collect.vereadores import slugs_from_index
from spot.parse.vereadores import (
    ALIAS_COLS,
    DIM_COLS,
    RE_GAB_NUM,
    alias_lookup,
    check_presenca,
    load_alias,
    load_dim,
    normalize_name,
    parse_index,
    parse_licenca,
    parse_profile,
    validate_seeds,
)

ROOT = Path(__file__).resolve().parents[1]
FIX = Path(__file__).parent / "fixtures"
INDEX = (FIX / "vereadores_index_2025-10-16.html").read_text(encoding="utf-8")
FELIPE = (FIX / "vereadores_perfil_felipe-santana.html").read_text(encoding="utf-8")
KLEBER = (FIX / "vereadores_perfil_carlos-kleber.html").read_text(encoding="utf-8")
DUMP = ROOT / "docs/spike/evidence/presenca/frequencia_full_dump.tsv"
RH = ROOT / "docs/spike/evidence/custo/rh_set2025.csv"
COMISSAO = ROOT / "docs/spike/evidence/produtividade/LEG_SYS_comissao_export.utf8.csv"

# Os 50 nomes da grade 2025-26 (HANDOVER §2.5), já com whitespace normalizado.
NOMES_GRADE = """Aladilce, Alberto Braga, Alex Alemão, Alexandre Aleluia, Anderson Ninho, André Fraga,
Augusto Vasconcelos, Beca, Carlos Kleber, Carlos Muniz, Cezar Leite, Claudio Tinoco,
Cris Correia, Daniel Alves, David Rios, Dr. José Antônio, Duda Sanches, Débora Santana,
Eliete Paraguassu Silva, Felipe Santana, Fábio Souza, George O Gordinho da Favela,
Hélio Lula Ferreira, Ireuda Silva, Isabela Sousa, Jorge Araújo, João Cláudio Bacelar,
Júlio Santos, Kel Torres, Kiki Bispo, Kênio Rezende, Luiz Carlos, Marcelle Moraes,
Marcelo Guimarães Neto, Marta Lula Rodrigues, Maurício Trindade, Omarzinho Gordilho,
Orlando Palhinha, Paulo Magalhães Júnior, Professor Hamilton, Randerson Leal,
Ricardo Almeida, Roberta Caires, Rodrigo Amaral, Sandro Bahiense, Sandro Filho,
Sidninho, Silvio Humberto, Tiago Queiroz, Téo Senna"""
NOMES_GRADE = [normalize_name(n) for n in NOMES_GRADE.replace("\n", " ").split(",")]


@pytest.fixture(scope="module")
def dim() -> list[dict[str, str]]:
    return load_dim()


@pytest.fixture(scope="module")
def alias() -> list[dict[str, str]]:
    return load_alias()


# ---- parser -----------------------------------------------------------------------------------


def test_slugs_from_index():
    slugs = slugs_from_index(INDEX)
    assert len(slugs) == 115
    assert slugs[0] == "aladilce-souza"
    assert len(set(slugs)) == 115


def test_parse_index_cards():
    cards = parse_index(INDEX)
    assert len(cards) == 115
    assert Counter(c["grupo"] for c in cards) == {"titular": 43, "ex_licenciado": 72}
    by_id = {c["vereador_id"]: c for c in cards}
    assert by_id["hamilton-assis"] == {
        "vereador_id": "hamilton-assis",
        "nome": "Hamilton Assis",
        "partido": "PSOL",
        "grupo": "titular",
    }
    assert by_id["felipe-santana"]["grupo"] == "ex_licenciado"
    assert by_id["marta-rodrigues"]["partido"] == "PT"


def test_parse_profile_felipe():
    r = parse_profile(FELIPE, "felipe-santana")
    assert r["nome"] == "Felipe Santana"
    assert r["partido"] == "PSD"
    assert r["nascimento"] == "1992-11-06"
    assert r["gabinete_numero"] == "34"
    assert r["legislatura"].startswith("20º Legislatura")
    assert r["licenca_data"] == "2026-08-04"
    assert r["licenca_dias"] == "121"
    assert r["suplente_nome"] == "Carlos Kleber"
    assert r["suplente_partido"] == "PSD"
    assert "licenciou-se" in r["licenca_texto"]
    assert r["fonte_url"] == "https://www.cms.ba.gov.br/vereadores/felipe-santana"


def test_parse_profile_kleber_sem_licenca_propria():
    r = parse_profile(KLEBER, "carlos-kleber")
    assert r["nome"] == "Carlos Kleber"
    assert r["licenca_data"] == ""
    assert r["suplente_nome"] == ""


@pytest.mark.parametrize(
    "bio, data, dias, sup",
    [
        (
            "OBS: Em 18 de junho de 2026, Kênio licenciou-se por um periodo de 121 dias. Em seu lugar assumiu o suplente Dr. José Antônio (PRD). Fim.",
            "2026-06-18",
            "121",
            "Dr. José Antônio",
        ),
        (
            "OBS: Em maio de 2026, o vereador licenciou-se por 140 dias, sendo substituído pelo suplente Tiago Queiroz (PP), que obteve votos.",
            "2026-05",
            "140",
            "Tiago Queiroz",
        ),
        (
            "Em 24 de fevereiro de 2025, licenciou-se para assumir a Semit. Em seu lugar, assumiu a vaga o suplente Orlando Palhinha (União).",
            "2025-02-24",
            "",
            "Orlando Palhinha",
        ),
        (
            "Retornou em 24 de fevereiro de 2025, por ocasião da saída do vereador Luiz Carlos (Republicanos), que licenciou-se para assumir a Seinfra.",
            "",
            "",
            "",
        ),
        (
            "OBS: Alan Castro licenciou-se (sem remuneração) no dia 09/07/2014 por 120 dias para cuidar da campanha. Em seu lugar assumiu o suplente Everaldo Lopes do Santos (Beca), do PTN.",
            "2014-07-09",
            "120",
            "Everaldo Lopes do Santos",
        ),
    ],
)
def test_parse_licenca(bio, data, dias, sup):
    r = parse_licenca(bio)
    assert r["licenca_data"] == data
    assert r["licenca_dias"] == dias
    assert r["suplente_nome"] == sup


@pytest.mark.parametrize(
    "endereco, num",
    [
        ("Rua Ruy Barbosa, s/n, Ed. Rio Lima, 2º andar, Gabinete 34", "34"),
        ("Ed. Bahia Center, 1º subsolo, gabinete nº 6", "6"),
        ("Ed. Bahia Center, 1° subsolo, gabinete n° 5", "5"),
        ("Ed. Bahia Center, 2º subsolo, gabinete nº1", "1"),
        ("Ed. Bahia Center, Gabinete. 27, 5º andar", "27"),
        ("Rua Ruy Barbosa, s/n", ""),
    ],
)
def test_gabinete_numero(endereco, num):
    m = RE_GAB_NUM.search(endereco)
    assert (m.group(1) if m else "") == num


def test_normalize_name():
    assert normalize_name("Randerson  Leal") == "Randerson Leal"
    assert normalize_name(" Téo Senna ") == "Téo Senna"


# ---- seeds ----------------------------------------------------------------------------------


def test_seeds_schema_and_integrity(dim, alias):
    assert list(dim[0].keys()) == DIM_COLS
    assert list(alias[0].keys()) == ALIAS_COLS
    assert validate_seeds(dim, alias) == []


def test_dim_cobre_50_nomes_e_ids_unicos(dim):
    ids = [d["vereador_id"] for d in dim]
    assert len(ids) == len(set(ids)) == 50
    assert all(re.fullmatch(r"[a-z0-9-]+", i) for i in ids)
    assert (
        Counter(d["situacao"] for d in dim)["titular"] + Counter(d["situacao"] for d in dim)["licenciado"]
        == 43
    )


def test_dim_ids_existem_no_indice(dim):
    cards = {c["vereador_id"] for c in parse_index(INDEX)}
    assert {d["vereador_id"] for d in dim} <= cards


def test_alias_cobre_os_50_nomes_da_grade(alias):
    lookup = alias_lookup(alias, "frequencia")
    assert len(NOMES_GRADE) == 50
    faltam = [n for n in NOMES_GRADE if n not in lookup]
    assert faltam == []
    assert len(lookup) == 50


@pytest.mark.skipif(not DUMP.exists(), reason="dump do spike ausente")
def test_alias_cobre_o_dump_do_spike(alias):
    lookup = alias_lookup(alias, "frequencia")
    with DUMP.open(encoding="utf-8") as f:
        nomes = {
            normalize_name(r["parlamentar"])
            for r in csv.DictReader(f, delimiter="\t")
            if r["ano"] in ("2025", "2026")
        }
    assert nomes == set(lookup)


def test_alias_sem_duplicata_alias_fonte(alias):
    keys = [(a["alias"], a["fonte"]) for a in alias]
    assert len(keys) == len(set(keys))


def test_alias_ids_existem_na_dim(dim, alias):
    ids = {d["vereador_id"] for d in dim}
    assert {a["vereador_id"] for a in alias} <= ids


def test_alias_casos_conhecidos(alias):
    f = alias_lookup(alias, "frequencia")
    assert f["Marta Lula Rodrigues"] == "marta-rodrigues"
    assert f["Professor Hamilton"] == "hamilton-assis"
    assert f["Omarzinho Gordilho"] == "omarzinho-gordilho"
    assert f["Hélio Lula Ferreira"] == "helio-ferreira"
    assert f["George O Gordinho da Favela"] == "george-gordinho-da-favela"
    assert f["Randerson Leal"] == "randerson-leal"
    assert f["Sandro Filho"] != f["Sandro Bahiense"]


@pytest.mark.skipif(not COMISSAO.exists(), reason="export de comissão ausente")
def test_alias_cobre_comissao(alias):
    lookup = alias_lookup(alias, "comissao")
    with COMISSAO.open(encoding="utf-8") as f:
        nomes = {normalize_name(r["Membro"]) for r in csv.DictReader(f, delimiter=";")}
    assert nomes <= set(lookup)


@pytest.mark.skipif(not RH.exists(), reason="RH set/2025 ausente")
def test_alias_cobre_rotulos_gab_ver(alias, dim):
    lookup = alias_lookup(alias, "centro_custo")
    with RH.open(encoding="utf-8") as f:
        labels = {normalize_name(r["centro_custo"] + " " + r["continuacao"]) for r in csv.DictReader(f)}
    labels = {lab for lab in labels if "VER." in lab}
    faltam = sorted(lab for lab in labels if lab not in lookup)
    assert faltam == []
    # todo código de gabinete do RH aparece em gabinete_cc_codigo de algum vereador
    codes = {lab.split(" - ")[0] for lab in labels}
    dim_codes = {d["gabinete_cc_codigo"] for d in dim if d["gabinete_cc_codigo"]}
    assert codes <= dim_codes


def test_check_presenca(tmp_path, alias):
    p = tmp_path / "presenca.csv"
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["num_sessao", "ano", "nome_fonte", "nome", "status"])
        w.writerow(["1", "2025", "Randerson  Leal", "Randerson Leal", "Presente"])
        w.writerow(["1", "2025", "Fulano de Tal", "Fulano de Tal", "Presente"])
        w.writerow(["2", "2025", "Fulano de Tal", "Fulano de Tal", "Ausente"])
    assert check_presenca(p, alias) == {"Fulano de Tal": 2}
