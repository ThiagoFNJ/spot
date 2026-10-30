"""Custo mensal por gabinete (spike §4.3) sobre ``folha``, ``estagiarios`` e ``parametros_custo``.

Definições:
- chave do gabinete = ``centro_custo_codigo`` (estável entre titular e suplente; o rótulo muda para
  ``(SUP. ...)`` quando o suplente assume);
- ocupante do mês: para códigos compartilhados por mais de um vereador em ``vereador_dim``, quem teve mais
  linhas na grade de frequência (``presenca_mvp``) no mês civil; mês sem sessão herda o mês anterior;
  caso contrário, o vereador do rótulo (``vereador_alias``, ``fonte = 'centro_custo'``);
- ``folha_assessores`` = proventos das funções ``ASSESSOR PARLAMENTAR*`` (CC10 = mandato);
  ``folha_outros`` = demais símbolos lotados no gabinete (estrutura institucional da Mesa);
- ``custo_observado = subsídio + folha_assessores + folha_outros + bolsas de estagiários + verba compensatória
  observada``; componentes ausentes (subsídio sem vigência, estagiários sem PDF publicado, mês sem empenho de
  verba na fonte) entram como 0 e ficam listados em ``componentes_faltantes``;
- ``verba_compensatoria_observada`` = Σ empenhos de verba compensatória do ocupante do gabinete no mês
  (``empenho.categoria = 'verba_compensatoria'`` do ``gridRegistroEmpenho``, credor → ``vereador_alias`` com
  ``fonte = 'empenho'``), líquidos de anulações; o mês é ``competencia_ref`` ("MÊS/ANO" do objeto) ou, se vazio,
  a competência do processo do e-TCM de mesmo número (``verba_processo``) e, por último, o mês da emissão. Quando o
  mesmo processo tem mais de um empenho original sem anulação publicada, vale só o que o processo do e-TCM cita; os
  outros ficam em ``metrica_verba_empenho`` com ``descartado = true`` (um empenho por linha, com a origem do mês).
  Tabela auxiliar ``metrica_verba_vereador`` (vereador × mês, 2025 e 2026, inclusive credores
  sem alias com ``vereador_id`` NULL) e conciliação com o SIGA (elemento 3.3.90.93.01 Indenizações) só em log;
- ``verba_compensatoria_teto`` é o TETO legal (Lei 9.828/2025 → 9.922/2025) e só entra em ``custo_com_teto_verba``
  (comparação); ``diarias`` fica NULL até ser coletada;
- centros de custo que não são gabinete vão para ``custo_institucional`` (nada é descartado em silêncio);
- rotatividade de assessores (b5): ``rotatividade_assessor_mes`` (matrícula CC10 × mês × centro de custo, com
  ``entrada``/``saida``), ``metrica_rotatividade_mes``, ``metrica_rotatividade_gabinete`` (vereador × gabinete × ano)
  e ``metrica_rotatividade_casa`` — ver ``SQL_ROTATIVIDADE_BASE`` para as regras e a ressalva de 2026;
- folha sintética do e-TCM por rubrica e por tipo de folha (b13): ``metrica_folha_sintetica_rubrica`` e
  ``metrica_folha_sintetica_tipo``, cada folha (competência, nº, tipo, grupo) contada uma vez.

Grava ``custo_gabinete_ocupante``, ``metrica_verba_empenho``, ``metrica_verba_vereador``, ``metrica_custo_gabinete``, ``metrica_custo_anual``,
``custo_institucional`` e as tabelas acima no DuckDB e o relatório ``docs/relatorios/custo-2025.md``.
CLI: ``uv run python -m spot.metrics.custo [--db FILE] [--out FILE] [--parametros CSV]``.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import duckdb

from spot.config import ROOT, SEEDS, SILVER

log = logging.getLogger(__name__)

DB_DEFAULT = SILVER / "spot.duckdb"
REPORT_DEFAULT = ROOT / "docs" / "relatorios" / "custo-2025.md"
PARAMS_DEFAULT = SEEDS / "parametros_custo.csv"
ANO = 2025

# Revisor de RH / spike §3.3 corrigido: set/2025 tem 43 gabinetes (o 42 antigo perdia 10017183 MARTA RODRIGUES).
SANITY_SET2025 = {"competencia": "2025-09", "gabinetes": 43, "servidores": 733, "folha": 4_757_228.61}
CADEIRAS = 43
# SIGA (prestação de contas mensal, spike §3.3): elemento 3.3.90.93.01 Indenizações. 06/2025 lido como "R$ 1,43 mi"
# (arredondado); 11/2025 exato. Conciliação informativa: Σ empenhos de verba do mês (por emissão e por competência).
SIGA_INDENIZACOES = {"2025-06": 1_430_000.00, "2025-11": 1_539_369.63}
EMPENHO_COLS = (
    "numero VARCHAR, tipo VARCHAR, data VARCHAR, ano INTEGER, valor DOUBLE, credor VARCHAR, categoria VARCHAR, "
    "anulacao BOOLEAN, competencia_ref VARCHAR, processo VARCHAR, anula_numero VARCHAR"
)

GAB = "coalesce(gabinete_vereador, '') <> ''"
ASSESSOR = "funcao LIKE 'ASSESSOR PARLAMENTAR%'"
# Centro de custo fictício dos servidores de 2026 cuja lotação não foi publicada (ver reconstruir_folha).
CC_SEM_LOTACAO = "LOTAÇÃO NÃO PUBLICADA (TCM 2026)"
# Militares à disposição (Assistência Militar) nunca constaram na folha do site; são estrutura, não gabinete.
CC_MILITAR = "ASSISTÊNCIA MILITAR (fora da folha do site)"


class CustoError(RuntimeError):
    """Inconsistência que invalida a métrica (parâmetros sobrepostos, soma que não fecha)."""


# ---- parâmetros legais -------------------------------------------------------------------------------------


def _tables(con: duckdb.DuckDBPyConnection) -> set[str]:
    return {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}


def _require(con: duckdb.DuckDBPyConnection, *tables: str) -> None:
    missing = [t for t in tables if t not in _tables(con)]
    if missing:
        raise CustoError(f"tabelas obrigatórias ausentes: {', '.join(missing)}")


def ensure_parametros(con: duckdb.DuckDBPyConnection, path: Path = PARAMS_DEFAULT) -> None:
    """Garante ``parametros_custo`` (o ``build`` já a carrega de ``data/seeds``; aqui só se faltar) e valida vigências."""
    if "parametros_custo" not in _tables(con):
        con.execute(
            "CREATE TABLE parametros_custo AS SELECT * FROM read_csv(?, header = true, sample_size = -1, encoding = 'utf-8')",
            [str(path)],
        )
        log.info("parametros_custo carregada de %s", path)
    sobrepostos = con.execute(
        """
        SELECT a.parametro, a.vigencia_de, b.vigencia_de
        FROM parametros_custo a JOIN parametros_custo b
          ON a.parametro = b.parametro AND a.vigencia_de < b.vigencia_de
         AND (a.vigencia_ate IS NULL OR a.vigencia_ate >= b.vigencia_de)
        """
    ).fetchall()
    if sobrepostos:
        raise CustoError(f"vigências sobrepostas em parametros_custo: {sobrepostos}")


def ensure_empenho(con: duckdb.DuckDBPyConnection) -> bool:
    """Garante a tabela ``empenho`` (silver). Se não foi coletada, cria vazia: a verba fica NULL em todos os meses."""
    if "empenho" in _tables(con):
        return True
    con.execute(f"CREATE TABLE empenho ({EMPENHO_COLS})")
    log.warning("tabela empenho ausente (rode spot.collect.empenhos + spot.parse.empenhos): verba fica NULL")
    return False


# Processos do e-TCM (``verba_processo``, de ``parse/etcm_vc.py``): empenho citado e competência de cada processo.
SQL_VERBA_PROCESSO = """
SELECT pp_numero::VARCHAR || '/' || ano_processo::VARCHAR AS processo,
       mode(nullif(empenho_numero, '')) AS empenho_citado, mode(nullif(competencia, '')) AS competencia
FROM verba_processo GROUP BY 1
"""
SQL_VERBA_PROCESSO_VAZIO = "SELECT NULL::VARCHAR AS processo, NULL::VARCHAR AS empenho_citado, NULL::VARCHAR AS competencia WHERE false"

SQL_VERBA_EMPENHO = """
CREATE OR REPLACE TABLE metrica_verba_empenho AS
WITH pr AS ({processos}),
ev AS (
    SELECT e.numero, e.data, e.valor, e.anulacao, e.credor, a.vereador_id, e.competencia_ref,
           nullif(e.anula_numero, '') AS anula_numero,
           -- a anulação não traz o processo no objeto: herda o do empenho anulado
           coalesce(nullif(e.processo, ''), (SELECT nullif(o.processo, '') FROM empenho o WHERE o.numero = e.anula_numero
                                              LIMIT 1)) AS processo
    FROM empenho e
    LEFT JOIN vereador_alias a ON a.fonte = 'empenho' AND a.alias = e.credor
    WHERE e.categoria = 'verba_compensatoria'
),
anulados AS (
    -- originais anulados por inteiro: já se resolvem pela anulação
    SELECT o.numero FROM ev o JOIN ev a ON a.anulacao AND a.anula_numero = o.numero
    WHERE NOT o.anulacao GROUP BY o.numero, o.valor HAVING sum(a.valor) >= o.valor - 0.01
),
-- empenhos originais ainda de pé
orig AS (
    SELECT processo, vereador_id, count(*) AS n FROM ev
    WHERE NOT anulacao AND processo IS NOT NULL AND numero NOT IN (SELECT numero FROM anulados) GROUP BY 1, 2
),
dup AS (
    -- mesmo processo e mesmo credor com mais de um empenho original sem anulação publicada (PP 780/2025: NE 289,
    -- 302 e 303): vale o empenho que o processo do e-TCM cita; os outros ficam marcados e fora da soma. Só dentro do
    -- mesmo vereador: há objetos que citam o nº de processo de outro gabinete (NE 652/2025, de Felipe Santana, cita o
    -- PP 2116/2025, de André Fraga), e esse empenho é pagamento legítimo de quem o recebeu.
    SELECT ev.numero, pr.empenho_citado
    FROM ev JOIN orig ON orig.processo = ev.processo AND orig.vereador_id IS NOT DISTINCT FROM ev.vereador_id
    JOIN pr ON pr.processo = ev.processo
    WHERE NOT ev.anulacao AND orig.n > 1 AND ev.numero <> pr.empenho_citado
      AND ev.numero NOT IN (SELECT numero FROM anulados)
      AND EXISTS (SELECT 1 FROM ev c WHERE c.numero = pr.empenho_citado AND NOT c.anulacao AND c.processo = ev.processo
                                         AND c.vereador_id IS NOT DISTINCT FROM ev.vereador_id)
)
SELECT ev.numero, ev.data, ev.credor, ev.vereador_id, ev.processo, ev.anulacao, ev.anula_numero,
       CASE WHEN ev.anulacao THEN -ev.valor ELSE ev.valor END AS valor_liquido,
       coalesce(nullif(ev.competencia_ref, ''), pr.competencia, strftime(try_cast(ev.data AS DATE), '%Y-%m'))
           AS competencia,
       CASE WHEN nullif(ev.competencia_ref, '') IS NOT NULL THEN 'objeto'
            WHEN pr.competencia IS NOT NULL THEN 'processo_etcm'
            ELSE 'mes_emissao' END AS origem_competencia,
       d.numero IS NOT NULL OR da.numero IS NOT NULL AS descartado,
       coalesce(d.empenho_citado, da.empenho_citado) AS empenho_citado, 'portal' AS fonte
FROM ev
LEFT JOIN pr USING (processo)
LEFT JOIN dup d ON d.numero = ev.numero
LEFT JOIN dup da ON da.numero = ev.anula_numero
ORDER BY competencia, ev.vereador_id NULLS LAST, ev.numero
"""

# Processo do e-TCM pago (com data de pagamento) cujo empenho citado não está no portal financeiro da Câmara e sem
# nenhum outro empenho do vereador naquela competência (24 processos de set/2025 a jul/2026, ex.: 2026NE000549..556):
# o pagamento entra pelo total do processo, com ``fonte = 'processo_etcm'``.
SQL_VERBA_SO_TCM = """
INSERT INTO metrica_verba_empenho
SELECT p.empenho_numero, p.data_pagamento::VARCHAR, NULL, p.vereador_id,
       p.pp_numero::VARCHAR || '/' || p.ano_processo::VARCHAR, false, NULL, p.total_declarado, p.competencia,
       'processo_etcm', false, NULL, 'processo_etcm'
FROM (
    SELECT *, row_number() OVER (
        PARTITION BY pp_numero, ano_processo
        ORDER BY CASE confianca WHEN 'alta' THEN 0 WHEN 'media' THEN 1 ELSE 2 END, arquivo) AS rn
    FROM verba_processo
) p
WHERE p.rn = 1 AND p.vereador_id IS NOT NULL AND nullif(p.competencia, '') IS NOT NULL AND p.total_declarado > 0
  AND p.data_pagamento IS NOT NULL AND nullif(p.empenho_numero, '') IS NOT NULL
  AND p.empenho_numero NOT IN (SELECT numero FROM empenho)
  AND NOT EXISTS (SELECT 1 FROM metrica_verba_empenho x
                  WHERE x.vereador_id = p.vereador_id AND x.competencia = p.competencia AND NOT x.descartado)
"""
COLS_VERBA_SO_TCM = {
    "vereador_id", "competencia", "total_declarado", "data_pagamento", "empenho_numero", "confianca", "arquivo",
}  # fmt: skip

SQL_VERBA = """
CREATE OR REPLACE TABLE metrica_verba_vereador AS
WITH g AS (
    SELECT vereador_id, competencia, any_value(credor) AS credor,
           count(*) AS n_empenhos,
           sum(CASE WHEN anulacao THEN 1 ELSE 0 END)::BIGINT AS n_anulacoes,
           sum(CASE WHEN origem_competencia = 'mes_emissao' THEN 1 ELSE 0 END)::BIGINT AS n_fallback_mes_emissao,
           sum(CASE WHEN origem_competencia = 'processo_etcm' THEN 1 ELSE 0 END)::BIGINT AS n_competencia_processo,
           sum(CASE WHEN fonte = 'processo_etcm' THEN 1 ELSE 0 END)::BIGINT AS n_pagos_so_etcm,
           round(sum(valor_liquido), 2) AS verba_compensatoria_observada,
           string_agg(numero, '|' ORDER BY data, numero) AS empenhos,
           strptime(competencia, '%Y-%m')::DATE AS d
    FROM metrica_verba_empenho WHERE NOT descartado AND competencia IS NOT NULL GROUP BY 1, 2
),
x AS (
    SELECT vereador_id, competencia, string_agg(numero, '|' ORDER BY numero) AS empenhos_descartados
    FROM metrica_verba_empenho WHERE descartado GROUP BY 1, 2
)
SELECT g.vereador_id, g.competencia, v.nome_parlamentar, g.credor, g.n_empenhos, g.n_anulacoes,
       g.n_fallback_mes_emissao, g.n_competencia_processo, g.n_pagos_so_etcm, g.verba_compensatoria_observada,
       (SELECT valor FROM parametros_custo p WHERE p.parametro = 'verba_compensatoria_teto'
         AND p.vigencia_de <= g.d AND (p.vigencia_ate IS NULL OR p.vigencia_ate >= g.d)) AS verba_compensatoria_teto,
       g.empenhos, x.empenhos_descartados
FROM g
LEFT JOIN x ON x.vereador_id IS NOT DISTINCT FROM g.vereador_id AND x.competencia = g.competencia
LEFT JOIN vereador_dim v ON v.vereador_id = g.vereador_id
ORDER BY g.competencia, g.vereador_id NULLS LAST, g.credor
"""

SQL_OCUPANTE = f"""
CREATE OR REPLACE TABLE custo_gabinete_ocupante AS
WITH cc AS (
    SELECT DISTINCT centro_custo_codigo, centro_custo_label, competencia FROM folha WHERE {GAB}
    UNION
    SELECT DISTINCT centro_custo_codigo, centro_custo_label, competencia FROM estagiarios WHERE {GAB}
),
rot AS (
    SELECT cc.*, a.vereador_id AS vereador_id_rotulo
    FROM cc
    LEFT JOIN vereador_alias a
      ON a.fonte = 'centro_custo' AND a.alias = cc.centro_custo_codigo || ' - ' || cc.centro_custo_label
),
cand AS (
    SELECT gabinete_cc_codigo AS centro_custo_codigo, vereador_id
    FROM vereador_dim WHERE gabinete_cc_codigo IS NOT NULL
),
n_cand AS (
    SELECT centro_custo_codigo, count(*) AS n_candidatos, min(vereador_id) AS candidato_unico FROM cand GROUP BY 1
),
grade AS (
    SELECT c.centro_custo_codigo, strftime(p.data_sessao, '%Y-%m') AS competencia, c.vereador_id,
           count(*) AS n_sessoes
    -- sessão em licença não conta: a grade lista o titular licenciado (e o suplente que saiu) com status Licenciado
    FROM cand c JOIN presenca_mvp p ON p.vereador_id = c.vereador_id AND p.em_exercicio
                                     AND coalesce(p.status, '') <> 'Licenciado'
    GROUP BY 1, 2, 3
),
grade_pick AS (
    SELECT centro_custo_codigo, competencia, vereador_id
    FROM (
        SELECT *, row_number() OVER (PARTITION BY centro_custo_codigo, competencia ORDER BY n_sessoes DESC, vereador_id) AS rn
        FROM grade
    ) WHERE rn = 1
),
base AS (
    SELECT r.*, coalesce(nc.n_candidatos, 0) AS n_candidatos, nc.candidato_unico,
           CASE WHEN nc.n_candidatos > 1 THEN g.vereador_id END AS vereador_id_grade
    FROM rot r
    LEFT JOIN n_cand nc USING (centro_custo_codigo)
    LEFT JOIN grade_pick g USING (centro_custo_codigo, competencia)
),
cf AS (
    SELECT *,
           last_value(vereador_id_grade IGNORE NULLS) OVER (
               PARTITION BY centro_custo_codigo ORDER BY competencia ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
           ) AS vereador_id_grade_anterior
    FROM base
)
SELECT
    centro_custo_codigo, centro_custo_label, competencia,
    CASE
        WHEN vereador_id_grade IS NOT NULL THEN vereador_id_grade
        WHEN vereador_id_grade_anterior IS NOT NULL THEN vereador_id_grade_anterior
        WHEN vereador_id_rotulo IS NOT NULL THEN vereador_id_rotulo
        WHEN n_candidatos = 1 THEN candidato_unico
    END AS vereador_id,
    CASE
        WHEN vereador_id_grade IS NOT NULL THEN 'grade'
        WHEN vereador_id_grade_anterior IS NOT NULL THEN 'grade_mes_anterior'
        WHEN vereador_id_rotulo IS NOT NULL THEN 'rotulo'
        WHEN n_candidatos = 1 THEN 'dim_codigo'
    END AS ocupante_fonte,
    vereador_id_rotulo, n_candidatos
FROM cf
ORDER BY centro_custo_codigo, competencia
"""

SQL_GABINETE = f"""
CREATE OR REPLACE TABLE metrica_custo_gabinete AS
WITH f AS (
    SELECT centro_custo_codigo, competencia,
           -- pessoas, não linhas: na folha reconstruída de 2026 a mesma matrícula aparece em mais de uma rubrica
           count(DISTINCT matricula) AS n_servidores,
           count(DISTINCT CASE WHEN {ASSESSOR} THEN matricula END)::BIGINT AS n_assessores_parlamentares,
           round(sum(CASE WHEN {ASSESSOR} THEN proventos ELSE 0 END), 2) AS folha_assessores,
           round(sum(CASE WHEN {ASSESSOR} THEN 0 ELSE proventos END), 2) AS folha_outros
    FROM folha WHERE {GAB} GROUP BY 1, 2
),
e AS (
    SELECT centro_custo_codigo, competencia, count(*) AS n_estagiarios, round(sum(proventos), 2) AS bolsas
    FROM estagiarios WHERE {GAB} GROUP BY 1, 2
),
e_cob AS (SELECT DISTINCT competencia FROM estagiarios),
vb AS (
    SELECT vereador_id, competencia, verba_compensatoria_observada, n_empenhos
    FROM metrica_verba_vereador WHERE vereador_id IS NOT NULL
),
vb_cob AS (SELECT DISTINCT competencia FROM metrica_verba_vereador),
meses AS (
    SELECT DISTINCT competencia, strptime(competencia, '%Y-%m')::DATE AS d FROM custo_gabinete_ocupante
),
par AS (
    SELECT m.competencia,
           (SELECT valor FROM parametros_custo p WHERE p.parametro = 'subsidio_vereador'
             AND p.vigencia_de <= m.d AND (p.vigencia_ate IS NULL OR p.vigencia_ate >= m.d)) AS subsidio,
           (SELECT valor FROM parametros_custo p WHERE p.parametro = 'verba_compensatoria_teto'
             AND p.vigencia_de <= m.d AND (p.vigencia_ate IS NULL OR p.vigencia_ate >= m.d)) AS verba_compensatoria_teto
    FROM meses m
),
j AS (
    SELECT
        o.centro_custo_codigo, o.vereador_id, v.nome_parlamentar, v.partido, o.centro_custo_label, o.competencia,
        o.ocupante_fonte,
        coalesce(f.n_servidores, 0) AS n_servidores,
        coalesce(f.n_assessores_parlamentares, 0) AS n_assessores_parlamentares,
        coalesce(f.folha_assessores, 0) AS folha_assessores,
        coalesce(f.folha_outros, 0) AS folha_outros,
        CASE WHEN ec.competencia IS NULL THEN NULL ELSE coalesce(e.n_estagiarios, 0) END AS n_estagiarios,
        CASE WHEN ec.competencia IS NULL THEN NULL ELSE coalesce(e.bolsas, 0) END AS bolsas_estagiarios,
        p.subsidio, p.verba_compensatoria_teto,
        CASE WHEN vc.competencia IS NULL THEN NULL ELSE coalesce(vb.verba_compensatoria_observada, 0) END
            AS verba_compensatoria_observada,
        CASE WHEN vc.competencia IS NULL THEN NULL ELSE coalesce(vb.n_empenhos, 0) END AS n_empenhos_verba,
        NULL::DOUBLE AS diarias
    FROM custo_gabinete_ocupante o
    LEFT JOIN f USING (centro_custo_codigo, competencia)
    LEFT JOIN e USING (centro_custo_codigo, competencia)
    LEFT JOIN e_cob ec ON ec.competencia = o.competencia
    LEFT JOIN vb ON vb.vereador_id = o.vereador_id AND vb.competencia = o.competencia
    LEFT JOIN vb_cob vc ON vc.competencia = o.competencia
    LEFT JOIN par p ON p.competencia = o.competencia
    LEFT JOIN vereador_dim v ON v.vereador_id = o.vereador_id
)
SELECT *,
    round(coalesce(subsidio, 0) + folha_assessores + folha_outros + coalesce(bolsas_estagiarios, 0)
          + coalesce(verba_compensatoria_observada, 0), 2) AS custo_observado,
    round(coalesce(subsidio, 0) + folha_assessores + folha_outros + coalesce(bolsas_estagiarios, 0)
          + coalesce(verba_compensatoria_teto, 0), 2) AS custo_com_teto_verba,
    concat_ws(', ',
        CASE WHEN subsidio IS NULL THEN 'subsidio' END,
        CASE WHEN bolsas_estagiarios IS NULL THEN 'estagiarios' END,
        CASE WHEN verba_compensatoria_observada IS NULL THEN 'verba_compensatoria' END,
        'diarias') AS componentes_faltantes
FROM j
ORDER BY competencia, centro_custo_codigo
"""

SQL_ANUAL = """
CREATE OR REPLACE TABLE metrica_custo_anual AS
WITH a AS (
    SELECT
        vereador_id, centro_custo_codigo, left(competencia, 4)::INTEGER AS ano,
        count(*) AS meses_com_folha,
        count(subsidio) AS meses_com_subsidio,
        count(bolsas_estagiarios) AS meses_com_estagiarios,
        count(*) FILTER (WHERE verba_compensatoria_observada > 0) AS meses_com_verba,
        min(competencia) AS primeiro_mes, max(competencia) AS ultimo_mes,
        round(avg(n_servidores), 1) AS media_servidores,
        round(avg(n_assessores_parlamentares), 1) AS media_assessores_parlamentares,
        round(sum(folha_assessores), 2) AS folha_assessores,
        round(sum(folha_outros), 2) AS folha_outros,
        round(sum(bolsas_estagiarios), 2) AS bolsas_estagiarios,
        round(sum(subsidio), 2) AS subsidio,
        round(sum(verba_compensatoria_observada), 2) AS verba_compensatoria_observada,
        round(sum(verba_compensatoria_teto), 2) AS verba_compensatoria_teto,
        round(sum(custo_observado), 2) AS custo_observado,
        round(sum(custo_com_teto_verba), 2) AS custo_com_teto_verba,
        round(sum(custo_observado) / count(*), 2) AS media_mensal_custo_observado
    FROM metrica_custo_gabinete
    GROUP BY 1, 2, 3
)
SELECT a.*, v.nome_parlamentar, v.partido, v.situacao,
       rank() OVER (PARTITION BY a.ano ORDER BY a.media_mensal_custo_observado DESC) AS ranking
FROM a LEFT JOIN vereador_dim v USING (vereador_id)
ORDER BY a.ano, ranking, a.centro_custo_codigo
"""

SQL_INSTITUCIONAL = f"""
CREATE OR REPLACE TABLE custo_institucional AS
SELECT centro_custo_codigo, centro_custo_label, competencia, 'folha' AS fonte,
       count(DISTINCT matricula) AS n, round(sum(proventos), 2) AS total
FROM folha WHERE NOT ({GAB}) GROUP BY 1, 2, 3
UNION ALL
SELECT centro_custo_codigo, centro_custo_label, competencia, 'estagiarios',
       count(*), round(sum(proventos), 2)
FROM estagiarios WHERE NOT ({GAB}) GROUP BY 1, 2, 3
ORDER BY competencia, fonte, centro_custo_codigo
"""


# Folha sintética do e-TCM (parse/etcm_folha.py): única fonte da folha em 2026. A mesma folha é anexada a mais de um
# processo de pagamento (líquido, INSS, abono...) e, às vezes, duas vezes ao mesmo processo (dois PDFs): fica UMA cópia
# por folha. Identidade da folha = (competência, nº da folha, tipo, grupo): ``folha_id`` sozinho não basta (em 2025-02
# o nº 026 é uma rescisão de comissionados e férias de estatutários) e pode ser NULL (PP 55 de 2026-01, só
# ``numero_folha``); ``tipo_folha`` pode ser NULL ("Férias Complementar", "Agentes Políticos II"). Os totais das
# cópias são iguais, exceto quando o OCR perde um dígito da quantidade (folha 119 de 2025-10: 17/171/17 servidores) —
# um DISTINCT sobre as colunas contaria a folha duas vezes; por isso max() por folha. A cópia de maior confiança
# (depois menor processo/arquivo) é a que fornece as rubricas.
REGIMES_FOLHA = ("Estatutário", "Cargo em comissão", "Assistência militar", "Celetista", "Temporário")
_IN_FOLHA = ", ".join(f"'{r}'" for r in REGIMES_FOLHA)
FOLHA_CHAVE = "coalesce(nullif(folha_id, ''), '#' || numero_folha)"
SQL_FOLHA_ESCOLHIDA = f"""
    SELECT competencia, {FOLHA_CHAVE} AS folha_chave, tipo_folha, grupo_regime,
           arg_min(pp_numero, ordem) AS pp_numero, arg_min(arquivo, ordem) AS arquivo,
           arg_min(confianca, ordem) AS confianca,
           max(total_servidores) AS total_servidores, max(total_remuneracao) AS total_remuneracao,
           max(total_descontos) AS total_descontos, max(liquido) AS liquido, count(*) AS n_copias
    FROM (
        SELECT *, (CASE confianca WHEN 'alta' THEN '0' WHEN 'media' THEN '1' ELSE '2' END)
                  || lpad(CAST(pp_numero AS VARCHAR), 8, '0') || arquivo AS ordem
        FROM folha_sintetica_resumo WHERE competencia <> ''
    ) GROUP BY 1, 2, 3, 4
"""
SQL_FOLHA_SINTETICA = f"""
CREATE OR REPLACE TABLE metrica_folha_sintetica AS
WITH f AS ({SQL_FOLHA_ESCOLHIDA})
, sub AS (SELECT max(valor) AS v FROM parametros_custo WHERE parametro = 'subsidio_vereador'),
g AS (
    SELECT competencia, grupo_regime, count(*) AS n_folhas,
           sum(CASE WHEN tipo_folha = 'Normal' THEN total_servidores END) AS servidores_lidos,
           round(sum(total_remuneracao), 2) AS remuneracao,
           round(sum(CASE WHEN tipo_folha = 'Normal' THEN total_remuneracao END), 2) AS remuneracao_normal,
           round(sum(total_descontos), 2) AS descontos, round(sum(liquido), 2) AS liquido,
           sum(CASE WHEN confianca <> 'alta' THEN 1 ELSE 0 END) AS n_nao_alta,
           sum(CASE WHEN tipo_folha = 'Normal' AND total_servidores IS NULL THEN 1 ELSE 0 END) AS n_sem_qtd
    FROM f GROUP BY 1, 2
)
-- Agentes políticos: a quantidade sai da própria remuneração (múltiplo exato do subsídio) quando o OCR a perdeu.
SELECT g.competencia, g.grupo_regime, g.n_folhas,
       CASE WHEN g.grupo_regime = 'Agente político' AND g.n_sem_qtd > 0 AND sub.v > 0
                 AND abs(g.remuneracao_normal / sub.v - round(g.remuneracao_normal / sub.v)) < 0.001
            THEN round(g.remuneracao_normal / sub.v)::BIGINT
            ELSE g.servidores_lidos END AS servidores,
       g.remuneracao, g.remuneracao_normal, g.descontos, g.liquido, g.n_nao_alta
FROM g, sub ORDER BY 1, 2
"""
SQL_FOLHA_SINTETICA_VAZIA = """
CREATE OR REPLACE TABLE metrica_folha_sintetica (
    competencia VARCHAR, grupo_regime VARCHAR, n_folhas BIGINT, servidores BIGINT, remuneracao DOUBLE,
    remuneracao_normal DOUBLE, descontos DOUBLE, liquido DOUBLE, n_nao_alta BIGINT
)
"""
# Custo mensal da Casa: folha analítica (PDF de RH do site, 2025) quando existe; senão a sintética do e-TCM.
# Subsídios: o modelo (43 × valor legal) em 2025, o pago de fato (folha de agentes políticos) depois; uma folha
# sintética com menos de 30 vereadores é prestação incompleta (ago/2026 só tem a 'II') e fica NULL.
SQL_CAMARA_MENSAL = f"""
CREATE OR REPLACE TABLE metrica_custo_camara_mensal AS
WITH a AS (
    SELECT competencia, count(DISTINCT matricula) AS n_servidores, round(sum(proventos), 2) AS folha_total,
           round(sum(CASE WHEN {GAB} THEN proventos ELSE 0 END), 2) AS folha_gabinetes,
           round(sum(CASE WHEN {GAB} OR centro_custo_label = '{CC_SEM_LOTACAO}' THEN 0 ELSE proventos END), 2) AS folha_estrutura,
           round(sum(CASE WHEN centro_custo_label = '{CC_SEM_LOTACAO}' THEN proventos ELSE 0 END), 2) AS folha_sem_lotacao,
           count(DISTINCT CASE WHEN {GAB} THEN matricula END) AS n_gabinetes,
           count(DISTINCT CASE WHEN {GAB} OR centro_custo_label = '{CC_SEM_LOTACAO}' THEN NULL ELSE matricula END)
               AS n_estrutura,
           count(DISTINCT CASE WHEN centro_custo_label = '{CC_SEM_LOTACAO}' THEN matricula END) AS n_sem_lotacao,
           max(CASE WHEN coalesce(fonte, 'rh_site') = 'rh_site' THEN 1 ELSE 0 END) AS tem_rh_site
    FROM folha GROUP BY 1
),
e AS (SELECT competencia, count(*) AS n_estagiarios, round(sum(proventos), 2) AS bolsas FROM estagiarios GROUP BY 1),
s AS (
    SELECT competencia,
           round(sum(CASE WHEN grupo_regime IN ({_IN_FOLHA}) THEN remuneracao END), 2) AS folha_total,
           round(sum(CASE WHEN grupo_regime IN ({_IN_FOLHA}) THEN remuneracao_normal END), 2) AS folha_normal,
           sum(CASE WHEN grupo_regime IN ({_IN_FOLHA}) THEN servidores END) AS n_servidores,
           round(sum(CASE WHEN grupo_regime = 'Estagiário' THEN remuneracao END), 2) AS bolsas,
           sum(CASE WHEN grupo_regime = 'Estagiário' THEN servidores END) AS n_estagiarios,
           round(sum(CASE WHEN grupo_regime = 'Agente político' THEN remuneracao END), 2) AS subsidios,
           sum(CASE WHEN grupo_regime = 'Agente político' THEN servidores END) AS n_subsidios
    FROM metrica_folha_sintetica GROUP BY 1
),
g AS (SELECT competencia, round(sum(subsidio), 2) AS subsidios FROM metrica_custo_gabinete GROUP BY 1),
v AS (SELECT competencia, round(sum(verba_compensatoria_observada), 2) AS verba FROM metrica_verba_vereador GROUP BY 1),
c AS (SELECT competencia FROM a UNION SELECT competencia FROM s)
SELECT c.competencia, left(c.competencia, 4)::INTEGER AS ano,
       CASE WHEN a.competencia IS NULL THEN 'folha_sintetica_etcm'
            WHEN a.tem_rh_site = 1 THEN 'folha_analitica' ELSE 'folha_reconstruida_tcm' END AS fonte,
       coalesce(a.folha_total, s.folha_normal) AS folha_total,
       coalesce(a.n_servidores, s.n_servidores) AS n_servidores,
       a.folha_gabinetes, a.folha_estrutura, a.folha_sem_lotacao, a.n_gabinetes, a.n_estrutura, a.n_sem_lotacao,
       coalesce(e.bolsas, s.bolsas) AS bolsas, coalesce(e.n_estagiarios, s.n_estagiarios) AS n_estagiarios,
       coalesce(g.subsidios, CASE WHEN s.n_subsidios >= 30 THEN s.subsidios END) AS subsidios, v.verba,
       s.folha_total AS folha_sintetica_total, s.folha_normal AS folha_sintetica_normal,
       s.subsidios AS subsidios_pagos, s.n_subsidios,
       round(coalesce(a.folha_total, s.folha_normal, 0) + coalesce(e.bolsas, s.bolsas, 0)
             + coalesce(g.subsidios, CASE WHEN s.n_subsidios >= 30 THEN s.subsidios END, 0) + coalesce(v.verba, 0), 2) AS custo_total
FROM c LEFT JOIN a USING (competencia) LEFT JOIN s USING (competencia) LEFT JOIN e USING (competencia)
       LEFT JOIN g USING (competencia) LEFT JOIN v USING (competencia)
ORDER BY c.competencia
"""


# ---- folha sintética por rubrica e por tipo de folha (b13) ----------------------------------------------------
# Mesma seleção de uma cópia por folha (SQL_FOLHA_ESCOLHIDA). As rubricas vêm da cópia escolhida; em folhas com
# ``confianca`` ≠ 'alta' a soma das rubricas pode não fechar com o total da folha (OCR), e ``n_nao_alta`` em
# ``metrica_folha_sintetica_tipo`` marca onde isso acontece. ``qtd`` é a soma das folhas do mesmo tipo no mês (duas
# folhas complementares podem conter a mesma pessoa).
SQL_FOLHA_SINTETICA_RUBRICA = f"""
CREATE OR REPLACE TABLE metrica_folha_sintetica_rubrica AS
WITH esc AS ({SQL_FOLHA_ESCOLHIDA})
SELECT r.competencia, r.grupo_regime, r.tipo_folha, r.rubrica_codigo, r.rubrica, r.natureza,
       sum(r.qtd) AS qtd, round(sum(r.valor), 2) AS valor, count(DISTINCT esc.folha_chave) AS n_folhas
FROM folha_sintetica r
JOIN esc ON esc.competencia = r.competencia AND esc.folha_chave = coalesce(nullif(r.folha_id, ''), '#' || r.numero_folha)
        AND esc.grupo_regime = r.grupo_regime AND esc.tipo_folha IS NOT DISTINCT FROM r.tipo_folha
        AND esc.pp_numero = r.pp_numero AND esc.arquivo = r.arquivo
GROUP BY 1, 2, 3, 4, 5, 6
ORDER BY 1, 2, 3, 6, valor DESC
"""
SQL_FOLHA_SINTETICA_TIPO = f"""
CREATE OR REPLACE TABLE metrica_folha_sintetica_tipo AS
WITH esc AS ({SQL_FOLHA_ESCOLHIDA})
SELECT competencia, grupo_regime, tipo_folha, count(*) AS n_folhas,
       sum(total_servidores) AS servidores, round(sum(total_remuneracao), 2) AS remuneracao,
       round(sum(total_descontos), 2) AS descontos, round(sum(liquido), 2) AS liquido,
       sum(CASE WHEN confianca <> 'alta' THEN 1 ELSE 0 END) AS n_nao_alta
FROM esc GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
"""
SQL_FOLHA_SINTETICA_RUBRICA_VAZIA = """
CREATE OR REPLACE TABLE metrica_folha_sintetica_rubrica (
    competencia VARCHAR, grupo_regime VARCHAR, tipo_folha VARCHAR, rubrica_codigo BIGINT, rubrica VARCHAR,
    natureza VARCHAR, qtd BIGINT, valor DOUBLE, n_folhas BIGINT
)
"""
SQL_FOLHA_SINTETICA_TIPO_VAZIA = """
CREATE OR REPLACE TABLE metrica_folha_sintetica_tipo (
    competencia VARCHAR, grupo_regime VARCHAR, tipo_folha VARCHAR, n_folhas BIGINT, servidores BIGINT,
    remuneracao DOUBLE, descontos DOUBLE, liquido DOUBLE, n_nao_alta BIGINT
)
"""


# ---- rotatividade de assessores por gabinete (b5) ---------------------------------------------------------------
# Base: matrículas com função ``ASSESSOR PARLAMENTAR*`` (CC10) lotadas num gabinete, mais as do centro de custo
# fictício CC_SEM_LOTACAO (contratados de 2026 cuja lotação o TCM não publica; ``vereador_id`` NULL). Uma matrícula
# conta uma vez por (mês, centro de custo) mesmo quando a folha a lista duas vezes (3 casos em 2026, uma linha com
# proventos 0).
#
# A série de meses é a das competências existentes em ``folha`` (2026-07 não existe: 2026-06 → 2026-08 são
# consecutivos). entrada = presente no mês e ausente no mês anterior da série, no mesmo centro de custo (o primeiro
# mês da série não gera entradas); saída = presente no mês e ausente no seguinte (o último mês não gera saídas).
#
# ``fonte_lotacao``: 'rh_site' (2025, folha analítica do site com lotação publicada), 'tcm_reconstruida' (2026,
# ``folha.fonte = 'tcm_pessoal'``: a lotação é a última vista em 2025, herdada pela matrícula) e 'nao_publicada'
# (CC_SEM_LOTACAO). Em 2026, portanto: quem foi contratado depois de dez/2025 nunca "entra" num gabinete (cai em
# 'nao_publicada'), logo as entradas dos gabinetes ficam subestimadas e as do centro fictício concentram todas as
# contratações; uma "saída" de um gabinete é a matrícula sumindo da consulta do TCM (desligamento, troca de
# matrícula ou de função), não necessariamente o fim do vínculo com aquele vereador; e ``n_assessores`` dos gabinetes
# cai ao longo de 2026 porque as reposições não têm lotação. Leia 2026 como "piso de rotatividade".
SQL_ROTATIVIDADE_BASE = f"""
CREATE OR REPLACE TABLE rotatividade_assessor_mes AS
WITH meses AS (
    SELECT competencia, row_number() OVER (ORDER BY competencia) AS i, count(*) OVER () AS n_meses,
           fonte_mes
    FROM (SELECT competencia, max(coalesce(fonte, 'rh_site')) AS fonte_mes FROM folha GROUP BY 1)
),
base AS (
    SELECT DISTINCT competencia, centro_custo_codigo, matricula,
           centro_custo_label = '{CC_SEM_LOTACAO}' AS sem_lotacao
    FROM folha
    WHERE {ASSESSOR} AND ({GAB} OR centro_custo_label = '{CC_SEM_LOTACAO}')
),
seq AS (
    SELECT b.*, m.i, m.n_meses, m.fonte_mes,
           lag(m.i) OVER (PARTITION BY b.centro_custo_codigo, b.matricula ORDER BY m.i) AS i_ant,
           lead(m.i) OVER (PARTITION BY b.centro_custo_codigo, b.matricula ORDER BY m.i) AS i_seg
    FROM base b JOIN meses m USING (competencia)
)
SELECT competencia, centro_custo_codigo, matricula,
       i > 1 AND coalesce(i_ant, -1) <> i - 1 AS entrada,
       i < n_meses AND coalesce(i_seg, -1) <> i + 1 AS saida,
       CASE WHEN sem_lotacao THEN 'nao_publicada'
            WHEN fonte_mes = 'tcm_pessoal' THEN 'tcm_reconstruida' ELSE 'rh_site' END AS fonte_lotacao
FROM seq ORDER BY competencia, centro_custo_codigo, matricula
"""
SQL_ROTATIVIDADE_MES = """
CREATE OR REPLACE TABLE metrica_rotatividade_mes AS
SELECT r.competencia, r.centro_custo_codigo, g.vereador_id,
       sum(CASE WHEN r.entrada THEN 1 ELSE 0 END)::BIGINT AS entradas,
       sum(CASE WHEN r.saida THEN 1 ELSE 0 END)::BIGINT AS saidas,
       count(*) AS n_assessores, max(r.fonte_lotacao) AS fonte_lotacao
FROM rotatividade_assessor_mes r
LEFT JOIN metrica_custo_gabinete g USING (centro_custo_codigo, competencia)
GROUP BY 1, 2, 3 ORDER BY 1, 2
"""
# ``permanencia_media_meses``: média, entre as pessoas distintas do ano, do nº de meses em que a matrícula aparece
# nesse centro de custo em toda a série disponível (censurada nas pontas: quem já estava em 2025-01 ou ainda está no
# último mês só conta os meses observados). Chave (vereador_id, centro_custo_codigo, ano) como em
# ``metrica_custo_anual``: código compartilhado por titular e suplente gera uma linha por ocupante, com os meses dele.
SQL_ROTATIVIDADE_GABINETE = """
CREATE OR REPLACE TABLE metrica_rotatividade_gabinete AS
WITH a AS (
    SELECT r.*, left(r.competencia, 4)::INTEGER AS ano, g.vereador_id
    FROM rotatividade_assessor_mes r
    LEFT JOIN metrica_custo_gabinete g USING (centro_custo_codigo, competencia)
),
perm AS (SELECT centro_custo_codigo, matricula, count(*) AS meses_na_folha FROM rotatividade_assessor_mes GROUP BY 1, 2),
pessoas AS (
    SELECT a.vereador_id, a.centro_custo_codigo, a.ano, a.matricula, p.meses_na_folha
    FROM a JOIN perm p USING (centro_custo_codigo, matricula) GROUP BY ALL
),
pm AS (
    SELECT vereador_id, centro_custo_codigo, ano, count(*) AS pessoas_distintas,
           round(avg(meses_na_folha), 1) AS permanencia_media_meses
    FROM pessoas GROUP BY 1, 2, 3
),
g AS (
    SELECT vereador_id, centro_custo_codigo, ano, count(DISTINCT competencia) AS meses,
           round(count(*) * 1.0 / count(DISTINCT competencia), 1) AS vagas_medias,
           sum(CASE WHEN entrada THEN 1 ELSE 0 END)::BIGINT AS entradas,
           sum(CASE WHEN saida THEN 1 ELSE 0 END)::BIGINT AS saidas,
           max(fonte_lotacao) AS fonte_lotacao
    FROM a GROUP BY 1, 2, 3
)
SELECT g.vereador_id, g.centro_custo_codigo, g.ano, g.meses, pm.pessoas_distintas, g.vagas_medias,
       round(pm.pessoas_distintas / g.vagas_medias, 2) AS razao, g.entradas, g.saidas, pm.permanencia_media_meses,
       g.fonte_lotacao
FROM g JOIN pm ON pm.vereador_id IS NOT DISTINCT FROM g.vereador_id
             AND pm.centro_custo_codigo = g.centro_custo_codigo AND pm.ano = g.ano
ORDER BY g.ano, razao DESC, g.centro_custo_codigo
"""
# Casa = todos os assessores CC10 da base (gabinetes + centro fictício de 2026). ``pessoas_sem_lotacao`` isola as
# matrículas que só aparecem em 'nao_publicada'.
SQL_ROTATIVIDADE_CASA = """
CREATE OR REPLACE TABLE metrica_rotatividade_casa AS
WITH a AS (SELECT *, left(competencia, 4)::INTEGER AS ano FROM rotatividade_assessor_mes),
perm AS (SELECT centro_custo_codigo, matricula, count(*) AS meses_na_folha FROM rotatividade_assessor_mes GROUP BY 1, 2),
pessoas AS (
    SELECT a.ano, a.matricula, max(p.meses_na_folha) AS meses_na_folha,
           bool_and(a.fonte_lotacao = 'nao_publicada') AS so_sem_lotacao
    FROM a JOIN perm p USING (centro_custo_codigo, matricula) GROUP BY 1, 2
),
pm AS (
    SELECT ano, count(*) AS pessoas_distintas, sum(CASE WHEN so_sem_lotacao THEN 1 ELSE 0 END)::BIGINT AS pessoas_sem_lotacao,
           round(avg(meses_na_folha), 1) AS permanencia_media_meses
    FROM pessoas GROUP BY 1
),
g AS (
    SELECT ano, count(DISTINCT competencia) AS meses, round(count(*) * 1.0 / count(DISTINCT competencia), 1) AS vagas_medias,
           sum(CASE WHEN entrada THEN 1 ELSE 0 END)::BIGINT AS entradas, sum(CASE WHEN saida THEN 1 ELSE 0 END)::BIGINT AS saidas
    FROM a GROUP BY 1
)
SELECT g.ano, g.meses, pm.pessoas_distintas, pm.pessoas_sem_lotacao, g.vagas_medias,
       round(pm.pessoas_distintas / g.vagas_medias, 2) AS razao, g.entradas, g.saidas, pm.permanencia_media_meses
FROM g JOIN pm USING (ano) ORDER BY g.ano
"""


def computar_rotatividade(con: duckdb.DuckDBPyConnection) -> None:
    """Cria ``rotatividade_assessor_mes``, ``metrica_rotatividade_mes``, ``_gabinete`` e ``_casa`` (ver SQL_ROTATIVIDADE_BASE)."""
    con.execute(SQL_ROTATIVIDADE_BASE)
    con.execute(SQL_ROTATIVIDADE_MES)
    con.execute(SQL_ROTATIVIDADE_GABINETE)
    con.execute(SQL_ROTATIVIDADE_CASA)
    for c in _rows(con, "SELECT * FROM metrica_rotatividade_casa"):
        log.info(
            "rotatividade %d: %d pessoas distintas (%d só sem lotação) para %.1f vagas médias = %.2f×; %d entradas, "
            "%d saídas em %d meses; permanência média %.1f meses",
            c["ano"], c["pessoas_distintas"], c["pessoas_sem_lotacao"], c["vagas_medias"], c["razao"], c["entradas"],
            c["saidas"], c["meses"], c["permanencia_media_meses"],
        )  # fmt: skip


# Folha reconstruída: a consulta de pessoal do TCM-BA (`parse/tcm_pessoal.py`, exportada à mão) traz servidor,
# matrícula, cargo/grau e remuneração de 2026, mas não a lotação; a lotação vem da última aparição da matrícula na
# folha do site (2025). Em 2025 nenhum assessor mudou de gabinete ao longo do ano, o que sustenta a hipótese.
# Quem não aparece em 2025 (contratados em 2026) fica no centro de custo fictício LOTACAO_NAO_PUBLICADA.
SQL_FOLHA_RECONSTRUIDA = f"""
CREATE OR REPLACE TABLE folha_reconstruida AS
WITH ult AS (
    SELECT * EXCLUDE (rn) FROM (
        SELECT ltrim(CAST(matricula AS VARCHAR), '0') AS mat, regime, funcao_codigo, centro_custo_codigo, centro_custo_label,
               gabinete_vereador, suplente_vereador, competencia AS lotacao_competencia,
               row_number() OVER (PARTITION BY ltrim(CAST(matricula AS VARCHAR), '0') ORDER BY competencia DESC) AS rn
        FROM folha
    ) WHERE rn = 1
),
t0 AS (SELECT * FROM tcm_pessoal WHERE regime NOT ILIKE '%agente%'),
-- mês ainda em carga no SIGA (ex.: jul/2026 com 2/3 das linhas) distorceria a série: exige >= 75% da mediana
n AS (SELECT competencia, count(*) AS n FROM t0 GROUP BY 1),
ok AS (SELECT competencia FROM n WHERE n >= 0.75 * (SELECT median(n) FROM n)),
t AS (
    SELECT * FROM t0
    WHERE competencia IN (SELECT competencia FROM ok)
      AND competencia NOT IN (SELECT DISTINCT competencia FROM folha WHERE coalesce(fonte, 'rh_site') = 'rh_site')
)
SELECT t.competencia, t.matricula, t.servidor,
       coalesce(u.regime, CASE WHEN t.regime ILIKE '%comiss%' THEN '3 - CARGO EM COMISSÃO'
                               WHEN t.regime ILIKE '%estatut%' THEN '1 - Estatutário' ELSE t.regime END) AS regime,
       coalesce(CAST(u.funcao_codigo AS VARCHAR), '') AS funcao_codigo, t.cargo AS funcao, t.simbolo, t.grau,
       try_cast(nullif(CAST(t.admissao AS VARCHAR), '') AS DATE) AS admissao,
       coalesce(CAST(u.centro_custo_codigo AS VARCHAR),
                CASE WHEN t.funcao ILIKE 'ASSISTENCIA MILITAR%' THEN '0M' ELSE '0' END) AS centro_custo_codigo,
       coalesce(u.centro_custo_label,
                CASE WHEN t.funcao ILIKE 'ASSISTENCIA MILITAR%' THEN '{CC_MILITAR}' ELSE '{CC_SEM_LOTACAO}' END) AS centro_custo_label,
       u.gabinete_vereador, u.suplente_vereador,
       round(coalesce(t.salario_base, 0) + coalesce(t.vantagens, 0) + coalesce(t.gratificacao, 0), 2) AS proventos,
       t.arquivo AS bronze_file, 'tcm_pessoal' AS fonte, u.lotacao_competencia,
       (u.mat IS NOT NULL OR t.funcao ILIKE 'ASSISTENCIA MILITAR%') AS lotacao_conhecida
FROM t LEFT JOIN ult u ON u.mat = ltrim(CAST(t.matricula AS VARCHAR), '0')
"""
SQL_TCM_MESES_EXCLUIDOS = """
WITH t0 AS (
    SELECT competencia, count(*) AS n FROM tcm_pessoal WHERE regime NOT ILIKE '%agente%' GROUP BY 1
)
SELECT competencia, n, (SELECT median(n) FROM t0) AS mediana FROM t0 WHERE n < 0.75 * (SELECT median(n) FROM t0)
"""
SQL_LOTACAO_COBERTURA = """
CREATE OR REPLACE TABLE metrica_lotacao_cobertura AS
SELECT competencia, count(*) AS n_servidores,
       sum(CASE WHEN lotacao_conhecida THEN 1 ELSE 0 END) AS n_lotacao_conhecida,
       sum(CASE WHEN lotacao_conhecida THEN 0 ELSE 1 END) AS n_sem_lotacao,
       round(100.0 * sum(CASE WHEN lotacao_conhecida THEN 0 ELSE 1 END) / count(*), 1) AS pct_sem_lotacao,
       sum(CASE WHEN simbolo = 'CC10' THEN 1 ELSE 0 END) AS n_assessores,
       sum(CASE WHEN simbolo = 'CC10' AND NOT lotacao_conhecida THEN 1 ELSE 0 END) AS n_assessores_sem_lotacao,
       round(sum(CASE WHEN lotacao_conhecida THEN 0 ELSE proventos END), 2) AS proventos_sem_lotacao
FROM folha_reconstruida GROUP BY 1 ORDER BY 1
"""


def reconstruir_folha(con: duckdb.DuckDBPyConnection) -> int:
    """Acrescenta à tabela ``folha`` (recriada a cada build) os meses que só existem na consulta do TCM.

    Devolve o nº de linhas acrescentadas. ``folha.fonte`` = 'rh_site' | 'tcm_pessoal'."""
    cols = {r[0] for r in con.execute("DESCRIBE folha").fetchall()}
    if "fonte" not in cols:
        con.execute("ALTER TABLE folha ADD COLUMN fonte VARCHAR DEFAULT 'rh_site'")
        con.execute("UPDATE folha SET fonte = 'rh_site' WHERE fonte IS NULL")
    con.execute(
        "DELETE FROM folha WHERE fonte = 'tcm_pessoal'"
    )  # idempotente: rodar a métrica 2x não duplica
    if "tcm_pessoal" not in _tables(con):
        con.execute(
            """
            CREATE OR REPLACE TABLE folha_reconstruida (
                competencia VARCHAR, matricula VARCHAR, servidor VARCHAR, regime VARCHAR, funcao_codigo VARCHAR,
                funcao VARCHAR, simbolo VARCHAR, grau VARCHAR, admissao DATE, centro_custo_codigo VARCHAR,
                centro_custo_label VARCHAR, gabinete_vereador VARCHAR, suplente_vereador VARCHAR, proventos DOUBLE,
                bronze_file VARCHAR, fonte VARCHAR, lotacao_competencia VARCHAR, lotacao_conhecida BOOLEAN
            )
            """
        )
        con.execute(SQL_LOTACAO_COBERTURA)
        log.warning("tcm_pessoal ausente (parse/tcm_pessoal.py): folha só com os meses do RH do site")
        return 0
    for m in _rows(con, SQL_TCM_MESES_EXCLUIDOS):
        log.warning(
            "tcm_pessoal %s: %d servidores contra mediana de %d — mês incompleto no SIGA, fora da folha reconstruída",
            m["competencia"], m["n"], m["mediana"],
        )  # fmt: skip
    con.execute(SQL_FOLHA_RECONSTRUIDA)
    con.execute(SQL_LOTACAO_COBERTURA)
    tipos = {
        r[0]: r[1] for r in con.execute("DESCRIBE folha").fetchall()
    }  # read_csv infere BIGINT/DATE/VARCHAR
    campos = [
        "competencia", "matricula", "servidor", "regime", "funcao_codigo", "funcao", "simbolo", "grau", "admissao",
        "centro_custo_codigo", "centro_custo_label", "gabinete_vereador", "suplente_vereador", "proventos",
        "bronze_file", "fonte",
    ]  # fmt: skip
    sel = ", ".join(f"TRY_CAST({c} AS {tipos.get(c, 'VARCHAR')}) AS {c}" for c in campos)
    con.execute(f"INSERT INTO folha ({', '.join(campos)}) SELECT {sel} FROM folha_reconstruida")
    (n,) = con.execute("SELECT count(*) FROM folha_reconstruida").fetchone()
    for c in _rows(con, "SELECT * FROM metrica_lotacao_cobertura"):
        log.info(
            "folha %s reconstruída do TCM: %d servidores, %d sem lotação publicada (%.1f%%; %d assessores CC10)",
            c["competencia"], c["n_servidores"], c["n_sem_lotacao"], c["pct_sem_lotacao"], c["n_assessores_sem_lotacao"],
        )  # fmt: skip
    return n


def _rows(con: duckdb.DuckDBPyConnection, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    cur = con.execute(sql, list(params))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def gabinetes_sem_alias(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Rótulos de gabinete (``GAB. VER.``) sem alias ``fonte = 'centro_custo'``; ``vereador_id`` pode ter vindo do código."""
    return _rows(
        con,
        """
        SELECT centro_custo_codigo, centro_custo_label, min(competencia) AS de, max(competencia) AS ate,
               count(*) AS meses, max(vereador_id) AS vereador_id_resolvido
        FROM custo_gabinete_ocupante WHERE vereador_id_rotulo IS NULL GROUP BY 1, 2 ORDER BY 1, 2
        """,
    )


def reconciliar(con: duckdb.DuckDBPyConnection, fonte: str) -> None:
    """Σ fonte = Σ gabinetes + Σ institucional, mês a mês (nada descartado em silêncio)."""
    col = "folha_assessores + folha_outros" if fonte == "folha" else "coalesce(bolsas_estagiarios, 0)"
    diff = con.execute(
        f"""
        -- folha: pessoas por centro de custo (a mesma matrícula pode ter mais de uma rubrica); estagiários: linhas
        WITH tot AS (SELECT competencia, sum(n) AS n, round(sum(total), 2) AS total FROM (
                         SELECT competencia, {"count(DISTINCT matricula)" if fonte == "folha" else "count(*)"} AS n,
                                sum(proventos) AS total
                         FROM {fonte} GROUP BY competencia, centro_custo_codigo, centro_custo_label) GROUP BY 1),
        gab AS (SELECT competencia, sum({"n_servidores" if fonte == "folha" else "coalesce(n_estagiarios, 0)"}) AS n,
                       round(sum({col}), 2) AS total FROM metrica_custo_gabinete GROUP BY 1),
        inst AS (SELECT competencia, sum(n) AS n, round(sum(total), 2) AS total FROM custo_institucional
                 WHERE fonte = ? GROUP BY 1)
        SELECT t.competencia, t.n, coalesce(g.n, 0) + coalesce(i.n, 0), t.total,
               round(coalesce(g.total, 0) + coalesce(i.total, 0), 2)
        FROM tot t LEFT JOIN gab g USING (competencia) LEFT JOIN inst i USING (competencia)
        WHERE t.n <> coalesce(g.n, 0) + coalesce(i.n, 0) OR abs(t.total - coalesce(g.total, 0) - coalesce(i.total, 0)) > 0.01
        """,
        [fonte],
    ).fetchall()
    if diff:
        raise CustoError(f"{fonte}: gabinetes + institucional não fecham com a fonte: {diff}")


def compute(con: duckdb.DuckDBPyConnection, parametros: Path = PARAMS_DEFAULT) -> dict[str, int]:
    """Cria as tabelas derivadas (ver docstring do módulo) e devolve o nº de linhas de cada uma."""
    _require(con, "folha", "estagiarios", "vereador_alias", "vereador_dim", "presenca_mvp")
    ensure_parametros(con, parametros)
    tem_empenho = ensure_empenho(con)
    reconstruir_folha(con)
    con.execute(SQL_OCUPANTE)
    tem_processo = "verba_processo" in _tables(con)
    con.execute(
        SQL_VERBA_EMPENHO.format(processos=SQL_VERBA_PROCESSO if tem_processo else SQL_VERBA_PROCESSO_VAZIO)
    )
    cols_processo = {
        r[0]
        for r in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'verba_processo'"
        ).fetchall()
    }
    if cols_processo >= COLS_VERBA_SO_TCM:
        con.execute(SQL_VERBA_SO_TCM)
    con.execute(SQL_VERBA)
    for d in empenhos_descartados(con):
        log.warning(
            "processo %s: empenho %s (%s) descartado — o e-TCM cita o %s e não há anulação publicada",
            d["processo"], d["numero"], _brl(d["valor_liquido"]), d["empenho_citado"],
        )  # fmt: skip
    con.execute(SQL_GABINETE)
    con.execute(SQL_ANUAL)
    con.execute(SQL_INSTITUCIONAL)
    computar_rotatividade(con)
    tem_sintetica = "folha_sintetica_resumo" in _tables(con)
    con.execute(SQL_FOLHA_SINTETICA if tem_sintetica else SQL_FOLHA_SINTETICA_VAZIA)
    tem_rubricas = tem_sintetica and "folha_sintetica" in _tables(con)
    con.execute(SQL_FOLHA_SINTETICA_RUBRICA if tem_rubricas else SQL_FOLHA_SINTETICA_RUBRICA_VAZIA)
    con.execute(SQL_FOLHA_SINTETICA_TIPO if tem_sintetica else SQL_FOLHA_SINTETICA_TIPO_VAZIA)
    if not tem_sintetica:
        log.warning(
            "folha_sintetica_resumo ausente (rode spot.parse.etcm_folha): custo da Casa só com a folha analítica"
        )
    con.execute(SQL_CAMARA_MENSAL)
    for d in _rows(
        con,
        """
        SELECT competencia, fonte, folha_total, folha_sintetica_normal, folha_sintetica_total,
               round(folha_sintetica_normal - folha_total, 2) AS dif
        FROM metrica_custo_camara_mensal
        WHERE fonte <> 'folha_sintetica_etcm' AND folha_sintetica_normal IS NOT NULL ORDER BY 1
        """,
    ):
        # A folha "normal" do e-TCM inclui a Assistência Militar (~R$ 0,2 mi), que o RH do site nunca listou; férias,
        # 13º e complementares ficam em folha_sintetica_total.
        log.info(
            "folha %s (%s): %s × sintética normal e-TCM %s (dif %s, %.1f%%); com férias/13º/compl.: %s",
            d["competencia"], d["fonte"], _brl(d["folha_total"]), _brl(d["folha_sintetica_normal"]), _brl(d["dif"]),
            100 * d["dif"] / d["folha_total"] if d["folha_total"] else 0, _brl(d["folha_sintetica_total"]),
        )  # fmt: skip
    reconciliar(con, "folha")
    reconciliar(con, "estagiarios")
    if tem_empenho:
        reconciliar_verba(con)
        for s in siga_check(con):
            log.info(
                "SIGA %s 3.3.90.93.01 = %s | Σ verba por emissão = %s (%.1f%%) | por competência = %s (%.1f%%)",
                s["competencia"],
                _brl(s["siga"]),
                _brl(s["por_emissao"]),
                100 * s["razao_emissao"],
                _brl(s["por_competencia"]),
                100 * s["razao_competencia"],
            )
        for u in verba_nao_mapeada(con):
            log.warning(
                "credor de verba sem alias (fonte=empenho): %r — %d empenho(s), %s, %s",
                u["credor"],
                u["n_empenhos"],
                u["competencias"],
                _brl(u["total"]),
            )
    (drift,) = con.execute(
        f"SELECT count(*) FROM folha WHERE centro_custo_label LIKE '%GAB. VER.%' AND NOT ({GAB})"
    ).fetchone()
    if drift:
        log.warning("%d linha(s) da folha com 'GAB. VER.' no rótulo sem gabinete_vereador (parser?)", drift)
    for g in gabinetes_sem_alias(con):
        log.warning(
            "gabinete sem alias centro_custo: %s - %s (%s..%s; resolvido por código: %s)",
            g["centro_custo_codigo"],
            g["centro_custo_label"],
            g["de"],
            g["ate"],
            g["vereador_id_resolvido"],
        )
    sizes = {
        t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        for t in (
            "custo_gabinete_ocupante",
            "metrica_verba_empenho",
            "metrica_verba_vereador",
            "metrica_custo_gabinete",
            "metrica_custo_anual",
            "custo_institucional",
            "metrica_folha_sintetica",
            "metrica_folha_sintetica_rubrica",
            "metrica_folha_sintetica_tipo",
            "metrica_custo_camara_mensal",
            "folha_reconstruida",
            "metrica_lotacao_cobertura",
            "rotatividade_assessor_mes",
            "metrica_rotatividade_mes",
            "metrica_rotatividade_gabinete",
            "metrica_rotatividade_casa",
        )
    }
    log.info("tabelas de custo: %s", sizes)
    return sizes


# ---- verba compensatória ----------------------------------------------------------------------------------


def reconciliar_verba(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Σ verba mapeada a vereador vs Σ que entrou nos gabinetes, por mês com folha. Diferença = verba de quem não é
    o ocupante do gabinete naquele mês (ex.: titular licenciado recebendo no mês em que o suplente aparece na grade)
    ou vereador sem gabinete no RH. Só avisa."""
    diff = _rows(
        con,
        """
        WITH m AS (SELECT competencia, round(sum(verba_compensatoria_observada), 2) AS mapeada
                   FROM metrica_verba_vereador WHERE vereador_id IS NOT NULL GROUP BY 1),
             g AS (SELECT competencia, round(sum(verba_compensatoria_observada), 2) AS gabinetes
                   FROM metrica_custo_gabinete GROUP BY 1)
        SELECT m.competencia, m.mapeada, g.gabinetes, round(m.mapeada - g.gabinetes, 2) AS fora_do_gabinete
        FROM m JOIN g USING (competencia) WHERE abs(m.mapeada - g.gabinetes) > 0.01 ORDER BY 1
        """,
    )
    for d in diff:
        log.warning(
            "verba %s: %s mapeada a vereadores, %s atribuída a gabinetes (%s de vereador que não é o ocupante do mês)",
            d["competencia"],
            _brl(d["mapeada"]),
            _brl(d["gabinetes"]),
            _brl(d["fora_do_gabinete"]),
        )
    return diff


def empenhos_descartados(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Empenhos originais repetidos para o mesmo processo que ficaram fora da soma (ver ``SQL_VERBA_EMPENHO``)."""
    return _rows(
        con,
        "SELECT processo, numero, vereador_id, competencia, valor_liquido, empenho_citado "
        "FROM metrica_verba_empenho WHERE descartado AND NOT anulacao ORDER BY competencia, processo, numero",
    )


def verba_nao_mapeada(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Credores de empenhos de verba sem alias ``fonte = 'empenho'`` (ficam fora do custo por gabinete)."""
    return _rows(
        con,
        """
        SELECT credor, sum(n_empenhos) AS n_empenhos, string_agg(competencia, ', ' ORDER BY competencia) AS competencias,
               round(sum(verba_compensatoria_observada), 2) AS total
        FROM metrica_verba_vereador WHERE vereador_id IS NULL GROUP BY 1 ORDER BY 1
        """,
    )


def siga_check(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Σ empenhos de verba do mês (por mês de emissão e por competência) × SIGA 3.3.90.93.01 (``SIGA_INDENIZACOES``)."""
    out: list[dict[str, Any]] = []
    for comp, siga in sorted(SIGA_INDENIZACOES.items()):
        (por_emissao,) = con.execute(
            """
            SELECT coalesce(round(sum(CASE WHEN anulacao THEN -valor ELSE valor END), 2), 0) FROM empenho
            WHERE categoria = 'verba_compensatoria' AND strftime(try_cast(data AS DATE), '%Y-%m') = ?
            """,
            [comp],
        ).fetchone()
        (por_comp,) = con.execute(
            "SELECT coalesce(round(sum(verba_compensatoria_observada), 2), 0) FROM metrica_verba_vereador WHERE competencia = ?",
            [comp],
        ).fetchone()
        out.append(
            {
                "competencia": comp,
                "siga": siga,
                "por_emissao": por_emissao,
                "razao_emissao": por_emissao / siga,
                "por_competencia": por_comp,
                "razao_competencia": por_comp / siga,
            }
        )
    return out


def verba_mensal(con: duckdb.DuckDBPyConnection, ano: int) -> list[dict[str, Any]]:
    """Por competência: nº de empenhos, vereadores, Σ, mín/máx, quantos acima do teto, quantos por mês de emissão."""
    return _rows(
        con,
        """
        SELECT competencia, sum(n_empenhos) AS empenhos, sum(n_anulacoes) AS anulacoes,
               count(vereador_id) AS vereadores, count(*) - count(vereador_id) AS sem_alias,
               round(sum(verba_compensatoria_observada), 2) AS total,
               round(min(verba_compensatoria_observada), 2) AS minimo, round(max(verba_compensatoria_observada), 2) AS maximo,
               any_value(verba_compensatoria_teto) AS teto,
               sum(CASE WHEN verba_compensatoria_observada > verba_compensatoria_teto THEN 1 ELSE 0 END)::BIGINT AS acima_do_teto,
               sum(n_fallback_mes_emissao) AS por_mes_emissao
        FROM metrica_verba_vereador WHERE left(competencia, 4)::INTEGER = ? GROUP BY 1 ORDER BY 1
        """,
        [ano],
    )


# ---- análises para o relatório -----------------------------------------------------------------------------


def totais_mensais(con: duckdb.DuckDBPyConnection, ano: int = ANO) -> list[dict[str, Any]]:
    return _rows(
        con,
        """
        SELECT competencia, count(*) AS gabinetes, count(vereador_id) AS com_vereador,
               sum(n_servidores) AS servidores, sum(n_assessores_parlamentares) AS assessores,
               round(sum(folha_assessores), 2) AS folha_assessores, round(sum(folha_outros), 2) AS folha_outros,
               sum(n_estagiarios) AS estagiarios, round(sum(bolsas_estagiarios), 2) AS bolsas,
               count(subsidio) AS subsidios, round(sum(subsidio), 2) AS subsidio_total,
               count(verba_compensatoria_observada) AS com_verba, round(sum(verba_compensatoria_observada), 2) AS verba_observada,
               round(sum(custo_observado), 2) AS custo_observado,
               round(sum(verba_compensatoria_teto), 2) AS teto_verba, round(sum(custo_com_teto_verba), 2) AS custo_com_teto
        FROM metrica_custo_gabinete WHERE left(competencia, 4)::INTEGER = ? GROUP BY 1 ORDER BY 1
        """,
        [ano],
    )


def ranking_gabinetes(con: duckdb.DuckDBPyConnection, ano: int = ANO) -> list[dict[str, Any]]:
    """Ranking por centro de custo (43 gabinetes); ocupantes do ano listados com os meses de cada um."""
    return _rows(
        con,
        """
        WITH g AS (
            SELECT centro_custo_codigo, count(*) AS meses,
                   round(avg(n_servidores), 1) AS media_servidores,
                   round(avg(n_assessores_parlamentares), 1) AS media_assessores,
                   round(sum(folha_assessores), 2) AS folha_assessores, round(sum(folha_outros), 2) AS folha_outros,
                   round(sum(bolsas_estagiarios), 2) AS bolsas, round(sum(subsidio), 2) AS subsidio,
                   round(sum(verba_compensatoria_observada), 2) AS verba_observada,
                   round(sum(custo_observado), 2) AS custo_observado,
                   round(sum(custo_observado) / count(*), 2) AS media_mensal,
                   round(sum(custo_com_teto_verba) / count(*), 2) AS media_mensal_com_teto,
                   max(centro_custo_label) AS centro_custo_label
            FROM metrica_custo_gabinete WHERE left(competencia, 4)::INTEGER = ? GROUP BY 1
        ),
        occ AS (
            SELECT centro_custo_codigo,
                   string_agg(coalesce(nome_parlamentar, vereador_id, '?') || ' (' || meses || 'm)', ' → ' ORDER BY primeiro) AS ocupantes,
                   string_agg(DISTINCT partido, '/') AS partidos
            FROM (
                SELECT centro_custo_codigo, vereador_id, nome_parlamentar, partido, count(*) AS meses, min(competencia) AS primeiro
                FROM metrica_custo_gabinete WHERE left(competencia, 4)::INTEGER = ? GROUP BY 1, 2, 3, 4
            ) GROUP BY 1
        )
        SELECT g.*, occ.ocupantes, occ.partidos, rank() OVER (ORDER BY g.media_mensal DESC) AS ranking
        FROM g JOIN occ USING (centro_custo_codigo) ORDER BY ranking, g.centro_custo_codigo
        """,
        [ano, ano],
    )


def mesa_split(con: duckdb.DuckDBPyConnection, ano: int = ANO) -> list[dict[str, Any]]:
    """Gabinetes cujo rótulo traz um cargo institucional antes de ``GAB. VER.`` (Mesa, Corregedoria, Ouvidoria, Escola)."""
    return _rows(
        con,
        """
        SELECT centro_custo_codigo, max(centro_custo_label) AS centro_custo_label,
               trim(left(max(centro_custo_label), position('GAB. VER.' IN max(centro_custo_label)) - 1), ' -') AS cargo,
               max(nome_parlamentar) AS nome_parlamentar, count(*) AS meses,
               round(avg(n_servidores), 1) AS media_servidores, round(avg(n_assessores_parlamentares), 1) AS media_assessores,
               round(sum(folha_assessores), 2) AS folha_assessores, round(sum(folha_outros), 2) AS folha_outros
        FROM metrica_custo_gabinete
        WHERE left(competencia, 4)::INTEGER = ? AND position('GAB. VER.' IN centro_custo_label) > 1
        GROUP BY 1 ORDER BY folha_assessores DESC
        """,
        [ano],
    )


def institucional_resumo(con: duckdb.DuckDBPyConnection, ano: int = ANO, top: int = 12) -> dict[str, Any]:
    tot = _rows(
        con,
        """
        SELECT fonte, count(DISTINCT centro_custo_codigo) AS centros, sum(n) AS linhas, round(sum(total), 2) AS total,
               count(DISTINCT competencia) AS meses
        FROM custo_institucional WHERE left(competencia, 4)::INTEGER = ? GROUP BY 1 ORDER BY 1
        """,
        [ano],
    )
    maiores = _rows(
        con,
        f"""
        SELECT centro_custo_codigo, max(centro_custo_label) AS centro_custo_label, count(*) AS meses,
               round(avg(n), 1) AS media_n, round(sum(total), 2) AS total, round(sum(total) / count(*), 2) AS media_mensal
        FROM custo_institucional WHERE fonte = 'folha' AND left(competencia, 4)::INTEGER = ?
        GROUP BY 1 ORDER BY total DESC LIMIT {int(top)}
        """,
        [ano],
    )
    return {"totais": tot, "maiores": maiores}


def ocupantes_compartilhados(con: duckdb.DuckDBPyConnection, ano: int = ANO) -> list[dict[str, Any]]:
    """Mês a mês dos códigos com mais de um candidato em ``vereador_dim`` (titular licenciado + suplente)."""
    return _rows(
        con,
        """
        SELECT o.centro_custo_codigo, o.centro_custo_label, o.competencia, o.vereador_id, v.nome_parlamentar,
               o.ocupante_fonte, o.vereador_id_rotulo
        FROM custo_gabinete_ocupante o LEFT JOIN vereador_dim v USING (vereador_id)
        WHERE o.n_candidatos > 1 AND left(o.competencia, 4)::INTEGER = ?
        ORDER BY 1, 3
        """,
        [ano],
    )


def analise_13(con: duckdb.DuckDBPyConnection, ano: int = ANO) -> dict[str, Any]:
    """'Total de Proventos' traz 13º em dezembro? Compara nov × dez por matrícula e a variação mês a mês."""
    nov, dez = f"{ano}-11", f"{ano}-12"
    (comuns, iguais, maior, menor, mediana, razao_2x) = con.execute(
        """
        WITH n AS (SELECT matricula, proventos AS p FROM folha WHERE competencia = ?),
             d AS (SELECT matricula, proventos AS p FROM folha WHERE competencia = ?)
        SELECT count(*), sum(CASE WHEN d.p = n.p THEN 1 ELSE 0 END), sum(CASE WHEN d.p > n.p THEN 1 ELSE 0 END),
               sum(CASE WHEN d.p < n.p THEN 1 ELSE 0 END), round(median(d.p / n.p), 4),
               sum(CASE WHEN d.p / n.p BETWEEN 1.9 AND 2.1 THEN 1 ELSE 0 END)
        FROM n JOIN d USING (matricula)
        """,
        [nov, dez],
    ).fetchone()
    por_mes = _rows(
        con,
        """
        WITH m AS (
            SELECT matricula, competencia, regime, proventos,
                   lag(proventos) OVER (PARTITION BY matricula ORDER BY competencia) AS prev,
                   lag(competencia) OVER (PARTITION BY matricula ORDER BY competencia) AS prev_c
            FROM folha
        )
        SELECT competencia, count(*) AS com_mes_anterior,
               sum(CASE WHEN proventos = prev THEN 1 ELSE 0 END) AS iguais,
               sum(CASE WHEN proventos > prev THEN 1 ELSE 0 END) AS subiu,
               sum(CASE WHEN proventos < prev THEN 1 ELSE 0 END) AS caiu,
               round(median(proventos / prev), 3) AS mediana_razao
        FROM m
        WHERE prev IS NOT NULL AND left(competencia, 4)::INTEGER = ?
          AND prev_c = strftime(strptime(competencia, '%Y-%m') - INTERVAL 1 MONTH, '%Y-%m')
        GROUP BY 1 ORDER BY 1
        """,
        [ano],
    )
    regime = _rows(
        con,
        """
        WITH m AS (
            SELECT regime, proventos, lag(proventos) OVER (PARTITION BY matricula ORDER BY competencia) AS prev
            FROM folha WHERE left(competencia, 4)::INTEGER = ?
        )
        SELECT CASE WHEN regime ILIKE '%estatut%' THEN 'estatutário' ELSE 'comissionado' END AS grupo,
               count(*) AS pares, sum(CASE WHEN proventos <> prev THEN 1 ELSE 0 END) AS mudou
        FROM m WHERE prev IS NOT NULL GROUP BY 1 ORDER BY 1
        """,
        [ano],
    )
    g29 = _rows(
        con,
        """
        SELECT competencia, proventos, count(*) AS n FROM folha
        WHERE funcao = 'ASSESSOR PARLAMENTAR-G-29 CC10' AND competencia IN (?, ?, ?)
        GROUP BY 1, 2 ORDER BY 1, n DESC
        """,
        [f"{ano}-09", nov, dez],
    )
    return {
        "nov": nov,
        "dez": dez,
        "comuns": comuns,
        "iguais": iguais,
        "maior_dez": maior,
        "menor_dez": menor,
        "mediana_razao": mediana,
        "razao_2x": razao_2x,
        "por_mes": por_mes,
        "regime": regime,
        "g29": g29,
    }


def sanity(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    comp = SANITY_SET2025["competencia"]
    (gabs, serv, folha) = con.execute(
        "SELECT count(*), sum(n_servidores), round(sum(folha_assessores + folha_outros), 2) "
        "FROM metrica_custo_gabinete WHERE competencia = ?",
        [comp],
    ).fetchone()
    ok = (gabs, serv) == (SANITY_SET2025["gabinetes"], SANITY_SET2025["servidores"]) and abs(
        (folha or 0) - SANITY_SET2025["folha"]
    ) < 0.01
    subs = _rows(
        con,
        """
        SELECT competencia, count(subsidio) AS n_subsidios, round(sum(subsidio), 2) AS total,
               count(DISTINCT vereador_id) AS vereadores, count(*) - count(vereador_id) AS sem_vereador
        FROM metrica_custo_gabinete GROUP BY 1 ORDER BY 1
        """,
    )
    return {
        "competencia": comp,
        "gabinetes": gabs,
        "servidores": serv,
        "folha": folha,
        "ok": ok,
        "subsidios": subs,
    }


# ---- relatório ---------------------------------------------------------------------------------------------


def _brl(v: float | None) -> str:
    if v is None:
        return "n/d"
    s = f"{v:,.2f}".replace(",", "\u0000").replace(".", ",").replace("\u0000", ".")
    return f"R$ {s}"


def _n(v: Any) -> str:
    return "n/d" if v is None else str(v)


def _parametros_md(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = _rows(con, "SELECT * FROM parametros_custo ORDER BY parametro, vigencia_de")
    out = ["| parâmetro | valor | tipo | vigência | fonte |", "|---|---:|---|---|---|"]
    for r in rows:
        vig = f"{r['vigencia_de']} → {r['vigencia_ate'] or '…'}"
        out.append(
            f"| `{r['parametro']}` | {_brl(r['valor'])}/mês | {r['tipo']} | {vig} | {r['fonte']} ([pdf]({r['fonte_url']})) |"
        )
    return out


def _totais_md(tot: list[dict[str, Any]]) -> list[str]:
    out = [
        "| mês | gab. | servidores | assessores CC10 | folha assessores | folha outros | estag. | bolsas | subsídios | verba obs. | custo observado | teto verba | custo c/ teto |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for t in tot:
        subs = f"{t['subsidios']} × = {_brl(t['subsidio_total'])}" if t["subsidios"] else "sem vigência"
        verba = f"{_brl(t['verba_observada'])} ({t['com_verba']} gab.)" if t["com_verba"] else "sem empenhos"
        out.append(
            f"| {t['competencia']} | {t['gabinetes']} | {t['servidores']} | {t['assessores']} | {_brl(t['folha_assessores'])} | "
            f"{_brl(t['folha_outros'])} | {_n(t['estagiarios'])} | {_brl(t['bolsas'])} | {subs} | {verba} | {_brl(t['custo_observado'])} | "
            f"{_brl(t['teto_verba'])} | {_brl(t['custo_com_teto'])} |"
        )
    return out


def _ranking_md(rows: list[dict[str, Any]]) -> list[str]:
    out = [
        "| # | centro de custo | ocupante(s) 2025 (meses) | partido | meses | servidores (média) | assessores CC10 (média) | folha assessores (ano) | folha outros | bolsas | subsídio | verba compensatória (obs.) | custo observado (ano) | **média mensal** | média c/ teto verba |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        out.append(
            f"| {r['ranking']} | {r['centro_custo_codigo']} · {r['centro_custo_label']} | {r['ocupantes']} | {r['partidos'] or ''} | "
            f"{r['meses']} | {r['media_servidores']} | {r['media_assessores']} | {_brl(r['folha_assessores'])} | "
            f"{_brl(r['folha_outros'])} | {_brl(r['bolsas'])} | {_brl(r['subsidio'])} | {_brl(r['verba_observada'])} | "
            f"{_brl(r['custo_observado'])} | **{_brl(r['media_mensal'])}** | {_brl(r['media_mensal_com_teto'])} |"
        )
    return out


def _mesa_md(rows: list[dict[str, Any]], inst: list[dict[str, Any]]) -> list[str]:
    out = [
        "| centro de custo | cargo no rótulo | vereador | servidores (média) | assessores CC10 (média) | folha assessores (mandato) | folha outros (estrutura) |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for r in rows:
        out.append(
            f"| {r['centro_custo_codigo']} | {r['cargo']} | {r['nome_parlamentar'] or ''} | {r['media_servidores']} | "
            f"{r['media_assessores']} | {_brl(r['folha_assessores'])} | {_brl(r['folha_outros'])} |"
        )
    pres = [i for i in inst if "GABINETE DA PRESIDENCIA" in (i["centro_custo_label"] or "")]
    if pres:
        p = pres[0]
        out += [
            "",
            (
                f"Estrutura institucional da Presidência fora do gabinete parlamentar: CC `{p['centro_custo_codigo']} - "
                f"{p['centro_custo_label']}` (símbolos CC-40/50/70/80/90: secretários de gabinete, secretário particular, "
                f"assessor especial, chefe de gabinete) — {p['media_n']} servidores/mês, {_brl(p['total'])} em {p['meses']} meses "
                f"({_brl(p['media_mensal'])}/mês). Está em `custo_institucional`, não no custo do mandato de Carlos Muniz."
            ),
        ]
    return out


def _compartilhados_md(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Nenhum código compartilhado por titular e suplente em `vereador_dim`."]
    por_cc: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        por_cc.setdefault(r["centro_custo_codigo"], []).append(r)
    out = ["| centro de custo | rótulo do RH | atribuição mês a mês (fonte) |", "|---|---|---|"]
    for cc, lst in por_cc.items():
        seq: list[str] = []
        for r in lst:
            nome = r["nome_parlamentar"] or r["vereador_id"] or "?"
            seq.append(f"{r['competencia'][5:]}: {nome} ({r['ocupante_fonte']})")
        out.append(f"| {cc} | {lst[0]['centro_custo_label']} | {'; '.join(seq)} |")
    return out


def _decimo_md(a: dict[str, Any]) -> list[str]:
    pct = 100 * a["iguais"] / a["comuns"] if a["comuns"] else 0
    out = [
        (
            f"- **{a['nov']} × {a['dez']} por matrícula**: {a['comuns']} matrículas presentes nos dois meses; "
            f"{a['iguais']} ({pct:.1f}%) com proventos idênticos, {a['maior_dez']} maiores em dezembro, {a['menor_dez']} menores; "
            f"mediana da razão dez/nov = {a['mediana_razao']}; matrículas com razão ≈ 2 (13º integral somado): **{a['razao_2x']}**."
        ),
        (
            f"- Conclusão: **dezembro não traz 13º** ({a['razao_2x'] or 0} caso(s) isolado(s) de valor dobrado em "
            f"{a['comuns'] or 0}). 'Total de Proventos' é a remuneração bruta mensal do mês de competência, sem 13º nem "
            "adicionais sazonais; a série anual **não precisa de deflator de 13º**, mas o custo por gabinete **subestima** "
            "o encargo real (13º, férias e INSS/RPPS patronal só aparecem agregados no SIGA)."
        ),
    ]
    for g in a["g29"]:
        out.append(
            f"  - `ASSESSOR PARLAMENTAR-G-29 CC10` em {g['competencia']}: {_brl(g['proventos'])} para {g['n']} servidores"
            + (" (valor de tabela, igual em todos os meses de comparação)" if g is a["g29"][-1] else "")
        )
    out += [
        "",
        "Variação mês a mês (matrículas presentes em dois meses consecutivos):",
        "",
        "| mês | pares | iguais | subiu | caiu | mediana razão |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for m in a["por_mes"]:
        out.append(
            f"| {m['competencia']} | {m['com_mes_anterior']} | {m['iguais']} | {m['subiu']} | {m['caiu']} | {m['mediana_razao']} |"
        )
    out.append("")
    for r in a["regime"]:
        frac = 100 * r["mudou"] / r["pares"] if r["pares"] else 0
        out.append(
            f"- {r['grupo']}: {r['mudou']} de {r['pares']} pares mês-a-mês mudaram de valor ({frac:.0f}%)."
        )
    out.append(
        "- Leitura: comissionados (CC10) recebem valor de tabela por grau e só variam na admissão/saída (mês proporcional) ou "
        "mudança de grau; estatutários variam todo mês (vantagens pessoais, gratificações), o que confirma que o campo é a "
        "remuneração efetiva do mês e não o vencimento-base."
    )
    return out


def _verba_md(con: duckdb.DuckDBPyConnection) -> list[str]:
    out: list[str] = []
    for ano in (ANO, ANO + 1):
        rows = verba_mensal(con, ano)
        if not rows:
            out.append(f"- {ano}: nenhum empenho de verba compensatória na fonte.")
            continue
        out += [
            f"**{ano}** — por competência (mês citado no objeto; sem mês → mês da emissão):",
            "",
            "| competência | empenhos | anulações | vereadores | sem alias | Σ verba | mínimo | máximo | teto | acima do teto | atribuídos pelo mês da emissão |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for r in rows:
            out.append(
                f"| {r['competencia']} | {r['empenhos']} | {r['anulacoes']} | {r['vereadores']} | {r['sem_alias']} | {_brl(r['total'])} | "
                f"{_brl(r['minimo'])} | {_brl(r['maximo'])} | {_brl(r['teto'])} | {r['acima_do_teto']} | {r['por_mes_emissao']} |"
            )
        tot = sum(r["total"] or 0 for r in rows)
        out += ["", f"Σ {ano}: {_brl(tot)} em {sum(r['empenhos'] for r in rows)} empenhos.", ""]
    for s in siga_check(con):
        out.append(
            f"- Conciliação SIGA {s['competencia']} (3.3.90.93.01 Indenizações = {_brl(s['siga'])}): Σ empenhos de verba emitidos no mês "
            f"= {_brl(s['por_emissao'])} ({100 * s['razao_emissao']:.0f}%); Σ por competência = {_brl(s['por_competencia'])} "
            f"({100 * s['razao_competencia']:.0f}%). O elemento inclui outras indenizações, e empenho ≠ liquidação: ordem de grandeza, não igualdade."
        )
    nm = verba_nao_mapeada(con)
    if nm:
        out.append(
            "- Credores de verba **sem alias** (fora do custo por gabinete): "
            + "; ".join(
                f"`{u['credor']}` ({u['n_empenhos']} empenho(s), {u['competencias']}, {_brl(u['total'])})"
                for u in nm
            )
        )
    else:
        out.append("- Todos os credores de verba compensatória têm alias `fonte = empenho`.")
    return out


def render_report(con: duckdb.DuckDBPyConnection, hoje: date | None = None) -> str:
    hoje = hoje or date.today()
    tot = totais_mensais(con)
    rank = ranking_gabinetes(con)
    mesa = mesa_split(con)
    inst = institucional_resumo(con)
    san = sanity(con)
    sem_alias = gabinetes_sem_alias(con)
    comp = ocupantes_compartilhados(con)
    a13 = analise_13(con)
    est_meses = [t["competencia"] for t in tot if t["estagiarios"] is not None]
    sem_sub = [t["competencia"] for t in tot if not t["subsidios"]]
    sem_ver = [s for s in san["subsidios"] if s["sem_vereador"]]
    n_gab = len(rank)
    total_obs = sum(t["custo_observado"] for t in tot)
    total_folha = sum(t["folha_assessores"] + t["folha_outros"] for t in tot)
    total_sub = sum(t["subsidio_total"] or 0 for t in tot)
    total_bolsas = sum(t["bolsas"] or 0 for t in tot)
    md: list[str] = [
        f"# Custo dos gabinetes — {ANO}",
        "",
        (
            f"Gerado em {hoje.isoformat()} por `uv run python -m spot.metrics.custo` a partir de `data/silver/spot.duckdb` "
            "(tabelas `metrica_custo_gabinete`, `metrica_custo_anual`, `custo_institucional`, `custo_gabinete_ocupante`). "
            "Fontes: folha mensal de servidores efetivos e comissionados e relação de estagiários "
            "(`https://www.cms.ba.gov.br/transparencia/recursos-humanos`, PDFs em `data/bronze/rh/`), constantes legais em "
            "`data/seeds/parametros_custo.csv`, identidade por `data/seeds/vereador_alias.csv` (`fonte = centro_custo`) e "
            "`vereador_dim.gabinete_cc_codigo`, exercício mensal pela grade de frequência (`presenca_mvp`)."
        ),
        "",
        f"**Só {ANO} tem folha publicada.** A CMS não publicou a folha de 2026 até {hoje.isoformat()} (aba 2026 da página de RH vazia).",
        "",
        "## Método (spike §4.3)",
        "",
        "- Unidade: gabinete = `centro_custo_codigo` do RH (estável entre titular e suplente), mês de competência.",
        "- `custo_observado = subsídio + folha de assessores parlamentares + folha de outros símbolos no gabinete + bolsas de estagiários + verba compensatória observada`.",
        (
            "- `folha_assessores`: funções `ASSESSOR PARLAMENTAR*` (símbolo CC10, graus G-05 a G-30) = custo do mandato. "
            "`folha_outros`: qualquer outro símbolo lotado num centro de custo `GAB. VER.` = estrutura institucional "
            "(Mesa). Ver a seção *Mesa* para o que os dados mostram."
        ),
        (
            "- Ocupante do mês: o vereador do rótulo (`GAB. VER. X (SUP. Y)` → X). Para códigos compartilhados por "
            "titular licenciado e suplente, prevalece quem teve mais sessões na grade de frequência no mês civil; mês sem "
            "sessão (recesso) herda o anterior. O subsídio do mês vai a esse ocupante."
        ),
        (
            "- `verba_compensatoria_observada`: Σ dos empenhos de verba compensatória (`https://cmsalvador.sys.inf.br/ca/gridRegistroEmpenho/`, "
            "`data/silver/empenho.csv`, `categoria = verba_compensatoria`) cujo credor (nome civil ou parlamentar, "
            "`vereador_alias` com `fonte = empenho`) é o ocupante do gabinete no mês, líquidos de anulações. O mês é o "
            'citado no objeto ("MÊS DE X/ANO"); quando o objeto não cita mês (lote de 26/02/2025), vale a competência do '
            "processo do e-TCM de mesmo número e, sem processo, o mês da emissão. Processo com mais de um empenho original "
            "sem anulação publicada conta só o empenho que o processo do e-TCM cita (os demais: `metrica_verba_empenho`, "
            "`descartado`). Meses sem nenhum empenho de verba na fonte ficam NULL e aparecem em `componentes_faltantes`."
        ),
        (
            "- `verba_compensatoria_teto` é o **teto legal** da cota mensal (Lei 9.828/2025, R$ 34.000; Lei 9.922/2025, "
            "R$ 39.000 a partir de 30/12/2025), mostrado à parte em `custo_com_teto_verba` para comparação. Valores observados "
            "acima do teto decorrem do art. 22 da Lei 9.828/2025 (uso de saldo não consumido em meses anteriores, explícito em "
            'vários objetos: "com utilização de saldo remanescente").'
        ),
        "- `diarias`: NULL (fonte `transparencia/despesas-viagem` ainda não coletada; em 2025 o spike não viu nenhum registro de vereador).",
        "- Centros de custo que não são gabinete (PROJUR, DF, DG, DIREL, Controladoria…) ficam em `custo_institucional`, e a soma gabinetes + institucional é conferida contra a folha mês a mês.",
        "",
        "### Constantes legais (`data/seeds/parametros_custo.csv`)",
        "",
        *_parametros_md(con),
        "",
        "## Totais mensais",
        "",
        *_totais_md(tot),
        "",
        (
            f"Ano: folha dos gabinetes {_brl(total_folha)}, subsídios {_brl(total_sub)} ({sum(t['subsidios'] for t in tot)} "
            f"vereador-mês), bolsas {_brl(total_bolsas)} ({len(est_meses)} meses publicados), custo observado {_brl(total_obs)}."
        ),
        "",
        "### Conferências",
        "",
        (
            f"- Sanidade {san['competencia']} (revisor de RH): {san['gabinetes']} gabinetes, {san['servidores']} servidores, "
            f"{_brl(san['folha'])} — esperado {SANITY_SET2025['gabinetes']} / {SANITY_SET2025['servidores']} / "
            f"{_brl(SANITY_SET2025['folha'])}: **{'confirmado' if san['ok'] else 'DIVERGE'}**. O 42 / 716 / R$ 4.633.426,74 "
            "do spike §3.3 perdia o gabinete 10017183 (Marta Rodrigues, rótulo quebrado em duas linhas no PDF)."
        ),
    ]
    sub_ok = [s for s in san["subsidios"] if s["n_subsidios"]]
    sub_mensal = sub_ok[0]["total"] / sub_ok[0]["n_subsidios"] if sub_ok else 0.0
    if sub_ok:
        esperado = CADEIRAS * sub_ok[0]["total"] / sub_ok[0]["n_subsidios"]
        batem = all(s["n_subsidios"] == CADEIRAS and abs(s["total"] - esperado) < 0.01 for s in sub_ok)
        md.append(
            f"- Σ subsídio por mês = {CADEIRAS} × {_brl(sub_ok[0]['total'] / sub_ok[0]['n_subsidios'])} = {_brl(esperado)} em "
            f"{'todos os' if batem else 'NEM TODOS os'} {len(sub_ok)} meses com vigência: cada gabinete tem exatamente um ocupante "
            "por mês (titular ou suplente), logo 43 subsídios/mês mesmo com 3 titulares licenciados. "
            "Atenção: o SIGA de 06/2025 (spike §3.3) registrou subsídios pagos = 42 × 26.080,98 — um vereador-mês a menos que "
            "este modelo; conciliar com a linha 3.1.90.11.74 quando o SIGA for coletado."
        )
    if sem_sub:
        md.append(
            f"- Meses sem subsídio na métrica: {', '.join(sem_sub)} — a Lei 9.825/2024 vige de 1º/02/2025; o valor de janeiro/2025 "
            "(19ª legislatura) não foi verificado em fonte primária (spike §8: R$ 24.759,74 vs R$ 23.428,64). Entra como 0 em "
            "`custo_observado` e está marcado em `componentes_faltantes`."
        )
    if sem_ver:
        md.append(
            "- Linhas de gabinete sem `vereador_id`: "
            + "; ".join(f"{s['competencia']}: {s['sem_vereador']}" for s in sem_ver)
        )
    else:
        md.append("- Todas as linhas gabinete × mês têm `vereador_id` resolvido.")
    md += [
        "",
        f"## Ranking dos {n_gab} gabinetes por média mensal de custo observado ({ANO})",
        "",
        *_ranking_md(rank),
        "",
        (
            f"Leitura: a média mensal divide o custo observado do ano pelos meses com folha ({len(tot)}). "
            f"{len(sem_sub)} mês(es) entra(m) sem subsídio e só {len(est_meses)} têm estagiários, para todos os gabinetes "
            f"igualmente — o ranking não muda, o nível fica subestimado em ~{_brl(sub_mensal * len(sem_sub) / max(len(tot), 1))}/mês "
            "(subsídio faltante ÷ meses) e pelas bolsas não publicadas."
        ),
        "",
        "## Verba compensatória observada (empenhos)",
        "",
        *_verba_md(con),
        "",
        "## Gabinetes da Mesa e cargos institucionais no rótulo",
        "",
        (
            "O rótulo do RH prefixa o cargo da Mesa (Presidência, Vice-Presidências, Secretarias, Corregedoria) ou a "
            "função institucional (Ouvidoria Substituta, Diretoria da Escola do Legislativo) ao gabinete. Divisão por função:"
        ),
        "",
        *_mesa_md(mesa, inst["maiores"]),
        "",
    ]
    if mesa and all(r["folha_outros"] == 0 for r in mesa) and all(t["folha_outros"] == 0 for t in tot):
        maior = max(mesa, key=lambda r: r["media_assessores"])
        md.append(
            f"**Achado**: em {ANO} **todos** os servidores lotados nos {n_gab} centros de custo `GAB. VER.` são "
            "`ASSESSOR PARLAMENTAR*` (CC10) — `folha_outros` = 0 em todos os gabinetes, inclusive os da Mesa. Os cargos "
            "CC-40/50/70/80/90 da estrutura da Presidência estão num centro de custo próprio (`367177 - GABINETE DA "
            "PRESIDENCIA - 00831`), e os das Secretarias/Vice-Presidências não aparecem como lotação separada no PDF. A divisão "
            "mandato/estrutura por função fica implementada e vazia; o que diferencia os gabinetes da Mesa é o **número de "
            f"assessores** ({maior['cargo']}: {maior['media_assessores']} em média)."
        )
    md += [
        "",
        "## Suplências: atribuição do mês ao ocupante",
        "",
        (
            "Os rótulos `(SUP. ...)` são idênticos em todos os 12 PDFs de 2025, inclusive janeiro e fevereiro, quando os titulares "
            "ainda estavam em exercício (Augusto Vasconcelos até 18/02, Luiz Carlos e Alberto Braga até 19/02 pela grade; "
            "licenças em 24/02/2025). O rótulo reflete o estado atual do cadastro, não o do mês — por isso a atribuição usa a grade."
        ),
        "",
        *_compartilhados_md(comp),
        "",
        "## 'Total de Proventos' é remuneração efetiva do mês? (pergunta aberta do spike §4.3/§8)",
        "",
        *_decimo_md(a13),
        "",
        "## Estagiários",
        "",
        (
            f"- PDFs de estagiários disponíveis para {len(est_meses)} meses ({est_meses[0] if est_meses else '—'} a "
            f"{est_meses[-1] if est_meses else '—'}): a página de RH só lista estagiários a partir de abril/2025 e o PDF de "
            "dezembro/2025 não está no bronze. Nos meses sem PDF, `n_estagiarios`/`bolsas_estagiarios` são NULL "
            "(e não 0) e `componentes_faltantes` registra `estagiarios`."
        ),
        "- Bolsas: R$ 623,20 (nível médio) e R$ 923,20 (nível superior); 2 casos de valor dobrado em mai/2025 (retroativo de admissão).",
        "",
        "## Custo institucional (fora dos gabinetes)",
        "",
    ]
    for t in inst["totais"]:
        md.append(
            f"- `{t['fonte']}`: {t['centros']} centros de custo, {t['linhas']} linhas-mês, {_brl(t['total'])} em {t['meses']} meses."
        )
    md += ["", "| centro de custo | servidores (média) | total 2025 | média mensal |", "|---|---:|---:|---:|"]
    for i in inst["maiores"]:
        md.append(
            f"| {i['centro_custo_codigo']} · {i['centro_custo_label']} | {i['media_n']} | {_brl(i['total'])} | {_brl(i['media_mensal'])} |"
        )
    md += ["", "## O que ainda falta", ""]
    md += [
        "- **Verba compensatória — liquidação/pagamento**: o modelo usa o valor **empenhado** (`gridRegistroEmpenho`); `gridRegistroDespesa` (92 mil linhas, fases liquidado/pago, join pelo número do empenho) não foi coletada.",
        "- **Verba compensatória — meses sem empenho**: janeiro/2025 só tem 9 empenhos (emitidos em março) e o lote de 26/02/2025 não cita mês; a competência cai no mês da emissão (fevereiro).",
        "- **Diárias**: `transparencia/despesas-viagem` não coletada (14 registros em 2025, nenhum vereador, segundo o spike).",
        "- **Encargos patronais, 13º e férias**: só agregados no SIGA (prestação de contas mensal) — exibir como rodapé institucional, não por gabinete.",
        "- **Subsídio de janeiro/2025**: sem fonte primária (ver Conferências).",
        "- **Folha de 2026**: não publicada pela CMS; a métrica para 2026 depende dessa publicação (ou de pedido LAI).",
        "- **Estagiários dez/2025 e jan–mar/2025**: sem PDF.",
        "- **Conciliação com o SIGA**: Σ subsídios (43 × 26.080,98) vs linha 3.1.90.11.74 (SIGA 06/2025 mostrou 42 ×); Σ folha de gabinetes vs vencimentos de cargos em comissão; Σ verba vs 3.3.90.93.01 (ver seção acima).",
    ]
    md += ["", "## Centros de custo `GAB. VER.` sem alias", ""]
    if sem_alias:
        md += ["| centro de custo | rótulo | meses | resolvido por código |", "|---|---|---|---|"]
        md += [
            f"| {g['centro_custo_codigo']} | {g['centro_custo_label']} | {g['de']}..{g['ate']} ({g['meses']}) | {g['vereador_id_resolvido'] or '**não resolvido**'} |"
            for g in sem_alias
        ]
        md.append("")
        md.append("Adicionar os rótulos acima a `data/seeds/vereador_alias.csv` (`fonte = centro_custo`).")
    else:
        md.append(
            "Nenhum: todos os pares (código, rótulo) `GAB. VER.` de 2025 na folha e nos estagiários têm alias "
            '`fonte = centro_custo` (`alias = "<código> - <rótulo>"`).'
        )
    md.append("")
    return "\n".join(md)


def run(
    db_path: Path = DB_DEFAULT,
    out: Path = REPORT_DEFAULT,
    parametros: Path = PARAMS_DEFAULT,
    hoje: date | None = None,
) -> Path:
    con = duckdb.connect(str(db_path))
    try:
        compute(con, parametros)
        text = render_report(con, hoje)
    finally:
        con.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    log.info("relatório gravado em %s (%d bytes)", out, len(text.encode("utf-8")))
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="metrica_custo_gabinete/anual + custo_institucional + relatório")
    ap.add_argument("--db", type=Path, default=DB_DEFAULT)
    ap.add_argument("--out", type=Path, default=REPORT_DEFAULT)
    ap.add_argument("--parametros", type=Path, default=PARAMS_DEFAULT)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run(args.db, args.out, args.parametros)


if __name__ == "__main__":
    main()
