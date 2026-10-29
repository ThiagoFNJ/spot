"""Testes offline do DOL (coletor + parser) sobre respostas reais salvas em tests/fixtures/dol/."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import httpx
import pytest

from spot.collect import dol
from spot.parse import dol as parse

FIX = Path(__file__).parent / "fixtures" / "dol"


# ---- texto e queries ------------------------------------------------------------------------


def test_normalizar_como_o_indice():
    assert (
        dol.normalizar('Acrescenta  dispositivos à Lei nº 1, "art. 2°"')
        == "Acrescenta dispositivos à Lei no 1, art. 2o"
    )
    assert dol.normalizar("Discussão única – Votação") == "Discussão única Votação"  # travessão solto cai
    assert dol.tokens("todos(as) os(as) 230-A") == ["todos", "as", "os", "as", "a"]


@pytest.mark.parametrize(
    ("tipo", "numero", "ano", "esperado"),
    [
        ("PLE", 232, 2025, '"Projeto de Lei no 232/25"'),
        ("PIN", 1, 2025, '"Projeto de Indicação no 1/25"'),
        ("RUP", 32, 2026, '"Requerimento de Utilidade Pública no 32/26"'),
        ("MOC", 348, 2026, '"Moção no 348/26"'),
        ("PEL", 2, 2025, '"Projeto de Emenda à Lei Orgânica no 2/25"'),
    ],
)
def test_query_numero(tipo, numero, ano, esperado):
    assert dol.query_numero(tipo, numero, ano) == esperado


def test_query_numero_tipo_desconhecido():
    assert dol.query_numero("XYZ", 1, 2025) is None


@pytest.fixture(scope="module")
def corpus():
    ementas = [
        "Requeiro, nos termos do art. 215 do Regimento Interno, a Utilidade Pública da Associação Alfa",
        "Requeiro, nos termos do art. 215 do Regimento Interno, a Utilidade Pública do Clube Beta",
        "Requeiro, nos termos do art. 215 do Regimento Interno, a Utilidade Pública do Instituto Gama",
        "Dispõe sobre a criação do bairro Boa Vista do Lobato no Município de Salvador e dá outras providências.",
        "Dispõe sobre a criação do Programa Visão Plena para a Melhor Idade no Município de Salvador",
        "Pesar pelo falecimento do cantor e compositor baiano Ernesto de Souza Andrade Júnior, o Netinho.",
        "Pesar pelo falecimento do cantor e compositor baiano Fulano de Tal.",
        "Indica ao Prefeito a criação de um programa.",
    ]
    return dol.Corpus.das_ementas(ementas)


def test_query_frase_pula_janela_de_template(corpus):
    q = dol.query_frase(
        "Requeiro, nos termos do art. 215 do Regimento Interno, a Utilidade Pública do Clube Beta", corpus
    )
    assert q.startswith('"') and q.endswith('"')
    assert "Requeiro, nos termos" not in q  # janela repetida em 3 ementas
    assert "Clube Beta" in q


def test_query_frase_prefere_palavras_raras(corpus):
    q = dol.query_frase(
        "Pesar pelo falecimento do cantor e compositor baiano Ernesto de Souza Andrade Júnior, o Netinho.",
        corpus,
    )
    assert "Netinho" in q or "Ernesto" in q
    assert "Pesar pelo falecimento" not in q


def test_query_frase_ementa_curta(corpus):
    assert dol.query_frase("Indica ao Prefeito a criação.", corpus) == '"Indica ao Prefeito a criação"'
    assert dol.query_frase("Pesar.", corpus) is None
    assert dol.query_frase("", corpus) is None


def test_query_frase_seis_palavras_sem_aspas_internas(corpus):
    q = dol.query_frase(
        'Dispõe sobre a "criação" do bairro Boa Vista do Lobato no Município de Salvador', corpus
    )
    assert q.count('"') == 2
    assert len(q.strip('"').split(" ")) == dol.JANELA


def test_query_termos(corpus):
    q = dol.query_termos(
        "Pesar pelo falecimento do cantor e compositor baiano Ernesto de Souza Andrade Júnior, o Netinho.",
        corpus,
    )
    termos = q.split(" ")
    assert len(termos) == dol.N_TERMOS and '"' not in q
    assert "netinho" in termos and "ernesto" in termos
    assert "pesar" not in termos  # aparece em 2 ementas, perde para nomes próprios
    assert termos == sorted(termos, key=q.index)  # ordem de aparição


def test_query_termos_poucas_palavras(corpus):
    assert dol.query_termos("Pesar por isso.", corpus) is None


# ---- nomes de arquivo -----------------------------------------------------------------------


def test_bronze_nome_e_codigo_de_nome():
    assert dol.bronze_nome("PLE-232/2025", "frase") == "PLE-232_2025.json"
    assert dol.bronze_nome("PLE-232/2025", "termos") == "PLE-232_2025__termos.json"
    assert dol.codigo_de_nome("PLE-232_2025") == "PLE-232/2025"
    assert dol.codigo_de_nome("PLE-232_2025__numero") == "PLE-232/2025"
    assert dol.split_codigo("RUP-32/2026") == ("RUP", 32, 2026)
    with pytest.raises(ValueError):
        dol.split_codigo("xyz")


# ---- decisão --------------------------------------------------------------------------------


def test_em_intervalo_ordena_e_filtra():
    items = dol.itens((FIX / "PLE-232_2025.json").read_bytes())
    assert len(items) == 9
    ok = dol.em_intervalo(items, 2025)
    assert [i["numero"] for i in ok] == [6971, 7034, 7035, 7061]
    assert ok[0]["data_publicacao"] == "2025-06-12"
    assert dol.itens(b'{"detail": "erro"}') == [] and dol.itens(b"[]") == []


def test_proxima_variante_fluxo():
    qs = {"frase": '"a b c d e f"', "termos": "a b c", "numero": '"Projeto de Lei no 1/25"'}
    assert dol.proxima_variante({}, qs) == "frase"
    assert dol.proxima_variante({"frase": 2}, qs) is None
    assert dol.proxima_variante({"frase": 0}, qs) == "termos"
    assert dol.proxima_variante({"frase": 0, "termos": 3}, qs) is None
    assert dol.proxima_variante({"frase": 0, "termos": 0}, qs) == "numero"
    assert dol.proxima_variante({"frase": 0, "termos": 40}, qs) == "numero"
    assert dol.proxima_variante({"frase": 37}, qs) == "numero"  # genérica: pula termos
    assert dol.proxima_variante({"frase": 37, "numero": 0}, qs) is None
    assert dol.proxima_variante({"frase": 0, "termos": 0, "numero": 1}, qs) is None


def test_proxima_variante_sem_query():
    sem = {"frase": None, "termos": None, "numero": '"Moção no 1/25"'}
    assert dol.proxima_variante({}, sem) == "numero"
    assert dol.proxima_variante({"numero": 0}, sem) is None
    assert dol.proxima_variante({}, {"frase": None, "termos": None, "numero": None}) is None


def test_escolher():
    um = [{"data_publicacao": "2025-02-07"}]
    assert dol.escolher({"frase": um}) == ("frase", um)
    assert dol.escolher({"frase": [], "termos": um}) == ("termos", um)
    assert dol.escolher({"frase": [], "termos": [], "numero": um}) == ("numero", um)
    assert dol.escolher({"frase": um * 11, "numero": um}) == ("numero", um)
    assert dol.escolher({"frase": um * 11, "numero": []}) is None
    assert dol.escolher({"frase": []}) is None


# ---- entrada --------------------------------------------------------------------------------


def test_ler_proposicoes_filtra_e_ordena(tmp_path):
    cols = "codigo,tipo,numero,ano,autor_fonte,autores,ementa,movimentado,localizacao,situacao,outros_fonte,sentinela,bronze_file"
    linhas = [
        "PIN-5/2025,PIN,5,2025,A,A,Indica x y z w,,,,,false,b",
        "PLE-9/2025,PLE,9,2025,A,A,Dispõe x y z w,,,,,false,b",
        "PLE-2/2026,PLE,2,2026,A,A|B,Dispõe x y z v,,,,,false,b",
        "MOC-1/2026,MOC,1,2026,A,A,Aplausos x y z,,,,,false,b",
        "PLE-9999/2025,PLE,9999,2025,A,A,Documento de teste,,,,,true,b",
        "PLE-3/2025,PLE,3,2025,Executivo Municipal,Executivo Municipal,Dispõe,,,,,false,b",
        "PLE-4/2025,PLE,4,2025,B,B|A,Dispõe,,,,,false,b",
        "PLE-1/2024,PLE,1,2024,A,A,Dispõe,,,,,false,b",
    ]
    p = tmp_path / "proposicao.csv"
    p.write_text(cols + "\n" + "\n".join(linhas) + "\n", encoding="utf-8")
    alvo, corpus = dol.ler_proposicoes(p, aliases={"A"})
    assert [a.codigo for a in alvo] == ["PLE-2/2026", "MOC-1/2026", "PLE-9/2025", "PIN-5/2025"]
    assert corpus.n_docs == 8  # corpus usa todas as ementas, inclusive as excluídas
    so_ple, _ = dol.ler_proposicoes(p, aliases={"A"}, tipos={"PLE"})
    assert [a.codigo for a in so_ple] == ["PLE-2/2026", "PLE-9/2025"]


def test_ler_aliases_reais():
    aliases = dol.ler_aliases()
    assert "Aladilce" in aliases and len(aliases) >= 40


# ---- HTTP com transporte falso ---------------------------------------------------------------


def test_buscar_monta_url_e_devolve_response(monkeypatch):
    monkeypatch.setattr(dol.time, "sleep", lambda s: None)
    visto: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        visto.append(req)
        return httpx.Response(200, content=(FIX / "REP-1_2025__numero.json").read_bytes())

    with httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": dol.BROWSER_UA}) as http:
        resp = dol.buscar(http, '"Requerimento no 1/25"')
    assert resp.status == 200 and resp.method == "GET"
    assert dol.query_da_url(resp.url) == '"Requerimento no 1/25"'
    assert "tipo=DOL" in resp.url and "per_page=100" in resp.url
    assert visto[0].headers["User-Agent"].endswith(dol.USER_AGENT)
    assert dol.itens(resp.content)[0]["numero"] == 6885


def test_buscar_retenta_5xx_e_nao_retenta_4xx(monkeypatch):
    monkeypatch.setattr(dol.time, "sleep", lambda s: None)
    chamadas = {"n": 0}

    def flaky(req: httpx.Request) -> httpx.Response:
        chamadas["n"] += 1
        return httpx.Response(503 if chamadas["n"] == 1 else 200, content=(FIX / "vazio.json").read_bytes())

    with httpx.Client(transport=httpx.MockTransport(flaky)) as http:
        assert dol.buscar(http, "x").status == 200
    assert chamadas["n"] == 2

    def bad(req: httpx.Request) -> httpx.Response:
        chamadas["n"] += 1
        return httpx.Response(422, json={"detail": "x"})

    chamadas["n"] = 0
    with httpx.Client(transport=httpx.MockTransport(bad)) as http, pytest.raises(dol.DolError):
        dol.buscar(http, "x")
    assert chamadas["n"] == 1


def test_coletar_proposicao_idempotente(tmp_path, monkeypatch):
    """Com o bronze da frase já no disco (0 edições), só faz as queries que faltam e não reescreve."""
    monkeypatch.setattr(dol.time, "sleep", lambda s: None)
    shutil.copy(FIX / "MOC-348_2026.json", tmp_path / "MOC-348_2026.json")
    pedidos: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        q = dol.query_da_url(str(req.url))
        pedidos.append(q)
        return httpx.Response(200, content=(FIX / "MOC-348_2026__termos.json").read_bytes())

    p = dol.Proposicao("MOC-348/2026", "MOC", 348, 2026, "Pesar pelo falecimento do cantor Netinho.")
    qs = {"frase": '"x"', "termos": "ernesto souza andrade netinho", "numero": '"Moção no 348/26"'}
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        assert dol.coletar_proposicao(http, p, qs, tmp_path) == 1
        assert dol.coletar_proposicao(http, p, qs, tmp_path) == 0  # segunda vez: nada a fazer
    assert pedidos == ["ernesto souza andrade netinho"]
    assert (tmp_path / "MOC-348_2026__termos.json").exists()
    entradas = [json.loads(l) for l in (tmp_path / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(entradas) == 1 and entradas[0]["params"]["variante"] == "termos"
    assert entradas[0]["params"]["query"] == "ernesto souza andrade netinho"


def test_escrever_progresso(tmp_path):
    from datetime import datetime, timedelta

    started = datetime.now().astimezone() - timedelta(seconds=100)
    dol.escrever_progresso(tmp_path / "progress.json", 50, 200, started, 70)
    d = json.loads((tmp_path / "progress.json").read_text(encoding="utf-8"))
    assert d["done"] == 50 and d["total"] == 200 and d["requests"] == 70
    assert 290 <= d["eta_seconds"] <= 310 and d["eta"] > d["updated"]


# ---- parser ---------------------------------------------------------------------------------


@pytest.fixture
def bronze(tmp_path):
    """Bronze sintético com manifest: frase OK (PLE-232), frase 0 + termos (MOC-348), só numero (REP-1),
    frase alta (RUP-1) e frase vazia sem fallback (PLE-1/2025, coleta interrompida)."""
    d = tmp_path / "dol"
    d.mkdir()
    arquivos = {
        "PLE-232_2025.json": ("frase", '"bairro Boa Vista do Lobato no"'),
        "MOC-348_2026.json": ("frase", '"compositor baiano Ernesto de Souza Andrade"'),
        "MOC-348_2026__termos.json": ("termos", "ernesto souza andrade netinho"),
        "REP-1_2025__numero.json": ("numero", '"Requerimento no 1/25"'),
        "RUP-1_2025.json": ("frase", '"Utilidade Pública Municipal do Instituto de"'),
    }
    with (d / "manifest.jsonl").open("w", encoding="utf-8") as m:
        for nome, (variante, q) in arquivos.items():
            shutil.copy(FIX / nome, d / nome)
            m.write(
                json.dumps({"file": nome, "url": "u", "params": {"variante": variante, "query": q}}) + "\n"
            )
        shutil.copy(FIX / "vazio.json", d / "PLE-1_2025.json")
        m.write(
            json.dumps({"file": "PLE-1_2025.json", "url": dol.API_URL + "?tipo=DOL&q=%22Programa+X%22"})
            + "\n"
        )
    (d / "progress.json").write_text("{}", encoding="utf-8")
    return d


def test_parse_dir(bronze):
    rows = {r["codigo"]: r for r in parse.parse_dir(bronze)}
    assert set(rows) == {"PLE-232/2025", "MOC-348/2026", "REP-1/2025", "RUP-1/2025", "PLE-1/2025"}

    r = rows["PLE-232/2025"]
    assert (r["variante"], r["n_edicoes"], r["dol_numero"], r["dol_data"]) == ("frase", 4, 6971, "2025-06-12")
    assert r["ultima_dol_data"] == "2025-10-17" and r["confianca"] == "media"  # 4 edições > 3
    assert "DOL-2025-06-12-6971.pdf" in r["pdf_url"] and r["dol_id"] == 578
    assert r["query"] == '"bairro Boa Vista do Lobato no"' and r["bronze_file"] == "PLE-232_2025.json"

    r = rows["MOC-348/2026"]
    assert (r["variante"], r["n_edicoes"], r["dol_numero"], r["confianca"]) == ("termos", 2, 7293, "baixa")
    assert r["bronze_file"] == "MOC-348_2026__termos.json" and r["query"] == "ernesto souza andrade netinho"

    r = rows["REP-1/2025"]
    assert (r["variante"], r["dol_numero"], r["dol_data"], r["confianca"]) == (
        "numero",
        6885,
        "2025-02-07",
        "baixa",
    )

    r = rows["RUP-1/2025"]
    assert (r["variante"], r["n_edicoes"], r["dol_numero"], r["dol_data"]) == ("frase", 3, 6892, "2025-02-17")
    assert r["confianca"] == "alta"  # a edição de 2021 fica fora do intervalo

    r = rows["PLE-1/2025"]
    assert r["variante"] == "" and r["n_edicoes"] == 0 and r["dol_numero"] == "" and r["confianca"] == ""
    assert r["query"] == '"Programa X"'  # query recuperada da URL quando o manifest não tem params


def test_parse_dir_ordenado(bronze):
    codigos = [r["codigo"] for r in parse.parse_dir(bronze)]
    assert codigos == ["PLE-1/2025", "PLE-232/2025", "REP-1/2025", "RUP-1/2025", "MOC-348/2026"]


def test_build_csv(bronze, tmp_path):
    out = tmp_path / "silver" / "proposicao_dol.csv"
    assert parse.build(bronze, out) == 5
    with out.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == parse.COLUMNS
    assert {r["confianca"] for r in rows} == {"alta", "media", "baixa", ""}


def test_build_sem_bronze(tmp_path):
    assert parse.build(tmp_path / "nada", tmp_path / "out.csv") == 0


def test_confianca_media_quando_edicao_tardia():
    ed = [{"data_publicacao": "2027-03-01"}]
    assert parse.confianca("frase", ed, 2025) == "media"
    assert parse.confianca("frase", [{"data_publicacao": "2026-03-01"}], 2025) == "alta"
    assert parse.confianca("termos", ed, 2025) == "baixa"
