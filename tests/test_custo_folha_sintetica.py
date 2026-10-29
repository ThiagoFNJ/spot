"""SQL da folha sintética em metrics/custo.py: deduplicação da mesma folha anexada a vários processos (e duas vezes ao
mesmo processo), contagem de subsídios derivada da remuneração quando o OCR perde a quantidade, e as tabelas por
rubrica e por tipo de folha (b13).

Cenário 2026-03: folha 030 (Normal, Estatutário) em 3 cópias — PP 467 a.pdf, PP 483 b.pdf e PP 483 b2.pdf (a última
com a quantidade lida como 16 em vez de 169); folha 035 Férias; folha 028 e 029 de agentes (028 sem quantidade);
folha 031 de comissionados (confiança média); e uma folha de agentes sem ``folha_id`` (só ``numero_folha`` 012,
como o PP 55 de 2026-01), com ``tipo_folha`` NULL."""

from __future__ import annotations

import duckdb

from spot.metrics import custo as m

COLS = (
    "mes_prestacao, pp_numero, arquivo, folha_id, competencia, tipo_folha, numero_folha, grupo_regime, "
    "total_servidores, total_remuneracao, total_descontos, liquido, soma_remuneracao, soma_descontos, n_rubricas, confianca"
)
RUB_COLS = (
    "mes_prestacao, pp_numero, arquivo, folha_id, competencia, tipo_folha, numero_folha, grupo_regime, "
    "rubrica_codigo, rubrica, qtd, valor, natureza"
)


def _db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("CREATE TABLE parametros_custo (parametro VARCHAR, valor DOUBLE)")
    con.execute("INSERT INTO parametros_custo VALUES ('subsidio_vereador', 26080.98), ('verba_teto', 34000)")
    con.execute(
        f"""CREATE TABLE folha_sintetica_resumo AS SELECT * FROM (VALUES
        ('2026-03','467','a.pdf','030','2026-03','Normal','1','Estatutário',169,3079399.91,1114229.54,1965170.37,3079399.91,1114229.54,34,'alta'),
        ('2026-03','483','b.pdf','030','2026-03','Normal','1','Estatutário',169,3079399.91,1114229.54,1965170.37,3079399.91,1114229.54,34,'alta'),
        ('2026-03','483','b2.pdf','030','2026-03','Normal','1','Estatutário',16,3079399.91,1114229.54,1965170.37,3079399.91,1114229.54,34,'alta'),
        ('2026-03','473','c.pdf','035','2026-03','Férias','1','Estatutário',8,108435.12,21213.98,87221.14,108435.12,21213.98,2,'alta'),
        ('2026-03','468','d.pdf','028','2026-03','Normal','1','Agente político',NULL,1069320.18,375732.91,693587.27,1069320.18,375732.91,4,'alta'),
        ('2026-03','469','e.pdf','029','2026-03','Normal','1','Agente político',1,26080.98,8910.75,17170.23,26080.98,8910.75,3,'alta'),
        ('2026-03','470','f.pdf','031','2026-03','Normal','1','Cargo em comissão',821,5930768.54,1290151.88,4640616.66,5930768.54,1290151.88,13,'media'),
        ('2026-03','471','g.pdf',NULL,'2026-03',NULL,'012','Agente político',1,10432.39,0.0,10432.39,10432.39,0.0,1,'alta')
        ) t({COLS})"""
    )
    con.execute(
        f"""CREATE TABLE folha_sintetica AS SELECT * FROM (VALUES
        ('2026-03','467','a.pdf','030','2026-03','Normal','1','Estatutário',1,'Vencimento',169,2000000.00,'remuneracao'),
        ('2026-03','467','a.pdf','030','2026-03','Normal','1','Estatutário',157,'Gratif Av Competência',169,1079399.91,'remuneracao'),
        ('2026-03','467','a.pdf','030','2026-03','Normal','1','Estatutário',399,'IRRF',150,1114229.54,'desconto'),
        ('2026-03','483','b.pdf','030','2026-03','Normal','1','Estatutário',1,'Vencimento',169,2000000.00,'remuneracao'),
        ('2026-03','483','b.pdf','030','2026-03','Normal','1','Estatutário',157,'Gratif Av Competência',169,1079399.91,'remuneracao'),
        ('2026-03','483','b.pdf','030','2026-03','Normal','1','Estatutário',399,'IRRF',150,1114229.54,'desconto'),
        ('2026-03','483','b2.pdf','030','2026-03','Normal','1','Estatutário',1,'Vencimento',16,2000000.00,'remuneracao'),
        ('2026-03','483','b2.pdf','030','2026-03','Normal','1','Estatutário',157,'Gratif Av Competência',16,1079399.91,'remuneracao'),
        ('2026-03','483','b2.pdf','030','2026-03','Normal','1','Estatutário',399,'IRRF',150,1114229.54,'desconto'),
        ('2026-03','473','c.pdf','035','2026-03','Férias','1','Estatutário',1,'Vencimento',8,108435.12,'remuneracao'),
        ('2026-03','473','c.pdf','035','2026-03','Férias','1','Estatutário',399,'IRRF',8,21213.98,'desconto'),
        ('2026-03','471','g.pdf',NULL,'2026-03',NULL,'012','Agente político',4,'Subsidio',1,10432.39,'remuneracao')
        ) t({RUB_COLS})"""
    )
    con.execute(m.SQL_FOLHA_SINTETICA)
    con.execute(m.SQL_FOLHA_SINTETICA_RUBRICA)
    con.execute(m.SQL_FOLHA_SINTETICA_TIPO)
    return con


def _f(r: tuple) -> tuple:
    """DECIMAL do DuckDB → float, para comparar com literais."""
    return tuple(float(x) if hasattr(x, "quantize") else x for x in r)


def test_rubricas_contam_cada_folha_uma_vez() -> None:
    con = _db()
    rows = {
        (r[0], r[1], r[2]): _f(r[3:])
        for r in con.execute(
            "SELECT tipo_folha, rubrica_codigo, natureza, rubrica, qtd, valor, n_folhas FROM metrica_folha_sintetica_rubrica "
            "WHERE competencia = '2026-03' AND grupo_regime = 'Estatutário'"
        ).fetchall()
    }
    assert rows["Normal", 1, "remuneracao"] == ("Vencimento", 169, 2000000.0, 1)  # 3 cópias → 1
    assert rows["Normal", 399, "desconto"] == ("IRRF", 150, 1114229.54, 1)
    assert rows["Férias", 1, "remuneracao"] == ("Vencimento", 8, 108435.12, 1)
    (soma,) = con.execute(
        "SELECT round(sum(valor), 2) FROM metrica_folha_sintetica_rubrica WHERE natureza = 'remuneracao' AND grupo_regime = 'Estatutário'"
    ).fetchone()
    assert float(soma) == 3187835.03  # 3.079.399,91 + 108.435,12
    # folha sem folha_id (chave pelo nº da folha) e tipo NULL não se perde
    assert [
        _f(r)
        for r in con.execute(
            "SELECT rubrica, valor FROM metrica_folha_sintetica_rubrica WHERE tipo_folha IS NULL"
        ).fetchall()
    ] == [("Subsidio", 10432.39)]


def test_tipos_por_folha_com_quantidade_maxima_entre_copias() -> None:
    con = _db()
    rows = {
        (r[0], r[1]): _f(r[2:])
        for r in con.execute(
            "SELECT grupo_regime, tipo_folha, n_folhas, servidores, remuneracao, n_nao_alta FROM metrica_folha_sintetica_tipo "
            "WHERE competencia = '2026-03'"
        ).fetchall()
    }
    assert rows["Estatutário", "Normal"] == (1, 169, 3079399.91, 0)  # 169 e não 16 (OCR) nem 2× a folha
    assert rows["Estatutário", "Férias"] == (1, 8, 108435.12, 0)
    assert rows["Agente político", "Normal"] == (2, 1, 1095401.16, 0)
    assert rows["Agente político", None] == (1, 1, 10432.39, 0)
    assert rows["Cargo em comissão", "Normal"][3] == 1
    # fecha com metrica_folha_sintetica por grupo
    dif = con.execute(
        """
        SELECT count(*) FROM (
            SELECT competencia, grupo_regime, round(sum(remuneracao), 2) AS t FROM metrica_folha_sintetica_tipo GROUP BY 1, 2
        ) t JOIN metrica_folha_sintetica m USING (competencia, grupo_regime) WHERE abs(t.t - m.remuneracao) > 0.01
        """
    ).fetchone()[0]
    assert dif == 0


def test_deduplica_folha_e_soma_tipos() -> None:
    con = _db()
    rows = {
        r[0]: tuple(float(x) if hasattr(x, "quantize") else x for x in r)
        for r in con.execute(
            "SELECT grupo_regime, n_folhas, servidores, remuneracao, remuneracao_normal, n_nao_alta FROM metrica_folha_sintetica WHERE competencia = '2026-03'"
        ).fetchall()
    }
    assert rows["Estatutário"] == (
        "Estatutário",
        2,
        169,
        3187835.03,
        3079399.91,
        0,
    )  # folha 030 contada uma vez + férias
    assert rows["Cargo em comissão"][2:] == (821, 5930768.54, 5930768.54, 1)


def test_subsidios_pela_remuneracao_quando_falta_quantidade() -> None:
    con = _db()
    (servidores, rem) = con.execute(
        "SELECT servidores, remuneracao FROM metrica_folha_sintetica WHERE grupo_regime = 'Agente político'"
    ).fetchone()
    assert servidores == 42  # 41 (1.069.320,18 / 26.080,98) + 1; a folha sem tipo (012) não entra na contagem
    assert float(rem) == 1105833.55  # 1.095.401,16 + 10.432,39
