"""Exporta as métricas do DuckDB para JSON em ``site/data/`` — a camada de dados do dashboard estático.

O site (``site/index.html``) é HTML puro e lê esses arquivos por ``fetch`` relativo, então o mesmo
diretório publica igual como Artifact, no GitHub Pages ou em qualquer servidor estático.

CLI: ``uv run python -m spot.export_site [--db FILE] [--out DIR]``.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import unicodedata
from collections.abc import Callable, Hashable
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

import duckdb

from spot.config import ROOT, SEEDS, SILVER
from spot.parse.empenhos import RE_CPF_EM_TEXTO, mascarar_cpf

log = logging.getLogger(__name__)

DB_DEFAULT = SILVER / "spot.duckdb"
OUT_DEFAULT = ROOT / "site" / "data"


def _json_default(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    raise TypeError(type(v))


def rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def _write(out: Path, name: str, payload: Any) -> None:
    path = out / name
    path.write_text(
        json.dumps(payload, ensure_ascii=False, default=_json_default, separators=(",", ":")), "utf-8"
    )
    log.info("%-20s %8d bytes", name, path.stat().st_size)


# ---- helpers puros (testáveis sem DuckDB) ----------------------------------------------------

STATUS_GRADE = {"Presente": "P", "Ausente": "A", "Licenciado": "L"}

# Prefixo do ``folha.centro_custo_label`` de um gabinete quando o vereador ocupa cargo na Mesa ou dirige um órgão da
# Casa pago pelo centro de custo do gabinete: "3ª VICE-PRESIDÊNCIA - GAB. VER. SIDNINHO", "PRESIDENCIA - GAB. VER.
# CARLOS MUNIZ", "CORRREGEDORIA - GAB. VER. ..." (grafia da fonte, com três R), "OUVIDORIA SUBSTITUTA - GAB. VER.
# ...", "DIRETORIA DA ESCOLA DO LEGISLATIVO - GAB. VER. ...". Gabinete comum começa por "GAB. VER." (ou por um
# código numérico) e não tem cargo.
RE_CARGO_MESA = re.compile(
    r"^\s*(?:[\d.]+\s*-\s*)?(?:(?P<ord>\d+)[ªa]\s*)?"
    r"(?P<cargo>VICE[\s-]*PRESID[ÊE]NCIA|PRESID[ÊE]NCIA|SECRETARIA|COR+EGEDORIA|OUVIDORIA(?:\s+SUBSTITUTA)?"
    r"|DIRETORIA\s+DA\s+ESCOLA\s+DO\s+LEGISLATIVO)\s*-\s*GAB",
    re.I,
)
_CARGO_TITULO = {
    "VICE-PRESIDENCIA": "Vice-Presidência",
    "PRESIDENCIA": "Presidência",
    "SECRETARIA": "Secretaria",
    "CORREGEDORIA": "Corregedoria",
    "OUVIDORIA": "Ouvidoria",
    "OUVIDORIA SUBSTITUTA": "Ouvidoria substituta",
    "DIRETORIA DA ESCOLA DO LEGISLATIVO": "Diretoria da Escola do Legislativo",
}


def cargo_mesa(centro_custo_label: str | None) -> str | None:
    """Rótulo legível do cargo embutido no ``centro_custo_label`` do gabinete, ou None.

    >>> cargo_mesa("3ª VICE-PRESIDÊNCIA - GAB. VER. SIDNINHO")
    '3ª Vice-Presidência'
    >>> cargo_mesa("GAB. VER. ALEX ALEMAO") is None
    True
    """
    if not centro_custo_label:
        return None
    m = RE_CARGO_MESA.match(centro_custo_label)
    if not m:
        return None
    chave = re.sub(
        r"\s+", " ", m.group("cargo").upper().replace("Ê", "E").replace("VICE PRESID", "VICE-PRESID")
    )
    chave = re.sub(r"COR+EGEDORIA", "CORREGEDORIA", chave)
    titulo = _CARGO_TITULO[chave]
    return f"{m.group('ord')}ª {titulo}" if m.group("ord") else titulo


def primeira_url(urls: str | list[str] | None) -> str | None:
    """Primeira URL de ``sessao.ata_urls`` (string única ou separada por ``|``/``;``/espaço, ou lista)."""
    if not urls:
        return None
    partes = urls if isinstance(urls, list) else re.split(r"[|;\s]+", urls)
    return next((u for u in partes if u), None)


def compactar_grade(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Agrupa células (vereador_id, ano, num_sessao, status) em uma linha por vereador × ano.

    Saída: ``[{"v": vereador_id, "ano": int, "n": [num_sessao, ...], "s": "PAL..."}]`` com ``n`` crescente e ``s[i]``
    o status da sessão ``n[i]`` (``P`` presente, ``A`` ausente, ``L`` licenciado, ``?`` desconhecido). Data e ata da
    sessão vêm de ``presenca.json.sessoes`` por (ano, num_sessao). ~94 linhas e ~30 KB em vez de 5,6 mil objetos.
    """
    por_chave: dict[tuple[str, int], list[tuple[int, str]]] = {}
    desconhecidos: set[str] = set()
    for c in cells:
        st = STATUS_GRADE.get(str(c["status"]))
        if st is None:
            desconhecidos.add(str(c["status"]))
            st = "?"
        por_chave.setdefault((c["vereador_id"], int(c["ano"])), []).append((int(c["num_sessao"]), st))
    if desconhecidos:
        log.warning("status de presença fora de %s: %s", sorted(STATUS_GRADE), sorted(desconhecidos))
    out = []
    for (v, ano), items in sorted(por_chave.items()):
        items.sort()
        out.append({"v": v, "ano": ano, "n": [n for n, _ in items], "s": "".join(st for _, st in items)})
    return out


def marcar_parciais(
    rows: list[dict[str, Any]],
    campo: str,
    grupo: Callable[[dict[str, Any]], Hashable],
    limiar: float = 0.8,
    extra: Callable[[dict[str, Any]], bool] | None = None,
) -> int:
    """Marca ``row["parcial"]`` em cada linha: True quando ``row[campo]`` < ``limiar`` × mediana do ``campo`` no grupo
    (``grupo(row)``, p.ex. o ano), ou quando ``extra(row)`` é verdadeiro; False explícito nos demais. Linhas com
    ``campo`` nulo não entram na mediana e só podem ser parciais via ``extra``. Devolve o nº de linhas marcadas."""
    medianas: dict[Hashable, float] = {}
    for g in {grupo(r) for r in rows}:
        vals = [float(r[campo]) for r in rows if grupo(r) == g and r.get(campo) is not None]
        if vals:
            medianas[g] = median(vals)
    n = 0
    for r in rows:
        med = medianas.get(grupo(r))
        abaixo = r.get(campo) is not None and med is not None and float(r[campo]) < limiar * med
        r["parcial"] = bool(abaixo or (extra is not None and extra(r)))
        n += r["parcial"]
    return n


def diaria_objeto(texto: str | None, limite: int = 200) -> str:
    """Objeto do empenho de diária para o site: CPF mascarado (o parser já mascara; aqui é cinto e suspensório),
    whitespace normalizado e corte em ``limite`` caracteres com reticências.

    >>> diaria_objeto("DIÁRIAS  PARA   BRASÍLIA, CPF 123.456.789-00")
    'DIÁRIAS PARA BRASÍLIA, CPF ***.***.***-**'
    """
    t = re.sub(r"\s+", " ", mascarar_cpf(texto or "")).strip()
    if RE_CPF_EM_TEXTO.search(t):  # pragma: no cover - a máscara acima garante; fica como sentinela
        raise ValueError("CPF não mascarado no objeto do empenho")
    return t if len(t) <= limite else t[: limite - 1].rstrip() + "…"


def resumo_diarias(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resumo anual das diárias: ``[{ano, n, total, n_vereador, total_vereador}]``, ordenado por ano. ``total`` é
    líquido de anulações (``anulacao`` subtrai); ``n`` conta empenhos (anulações inclusive); ``*_vereador`` só os
    empenhos cujo credor tem alias de vereador (``vereador_id`` não nulo)."""
    por_ano: dict[int, dict[str, Any]] = {}
    for r in rows:
        a = por_ano.setdefault(
            int(r["ano"]),
            {"ano": int(r["ano"]), "n": 0, "total": 0.0, "n_vereador": 0, "total_vereador": 0.0},
        )
        v = -float(r["valor"]) if r.get("anulacao") else float(r["valor"])
        a["n"] += 1
        a["total"] += v
        if r.get("vereador_id"):
            a["n_vereador"] += 1
            a["total_vereador"] += v
    for a in por_ano.values():
        a["total"] = round(a["total"], 2)
        a["total_vereador"] = round(a["total_vereador"], 2)
    return [por_ano[k] for k in sorted(por_ano)]


def agregar_rubricas_pequenas(rows: list[dict[str, Any]], limiar: float = 0.005) -> list[dict[str, Any]]:
    """Agrega em uma linha ``Outras`` as rubricas com menos de ``limiar`` (0,5%) do Σ|valor| do seu grupo
    (``competencia``, ``grupo_regime``, ``tipo_folha``, ``natureza``). A linha agregada tem ``rubrica_codigo`` None,
    ``rubrica = "Outras"``, ``qtd`` None (somar pessoas de rubricas diferentes não faz sentido) e ``outras`` = nº de
    rubricas agregadas; as demais linhas saem como entraram, na mesma ordem. Mantém o JSON pequeno sem mexer nos totais."""
    chave = lambda r: (r["competencia"], r["grupo_regime"], r["tipo_folha"], r["natureza"])  # noqa: E731
    totais: dict[tuple[Any, ...], float] = {}
    for r in rows:
        totais[chave(r)] = totais.get(chave(r), 0.0) + abs(float(r["valor"] or 0))
    out: list[dict[str, Any]] = []
    outras: dict[tuple[Any, ...], dict[str, Any]] = {}
    for r in rows:
        k = chave(r)
        if totais[k] and abs(float(r["valor"] or 0)) < limiar * totais[k]:
            o = outras.get(k)
            if o is None:
                o = outras[k] = {
                    "competencia": r["competencia"],
                    "grupo_regime": r["grupo_regime"],
                    "tipo_folha": r["tipo_folha"],
                    "rubrica_codigo": None,
                    "rubrica": "Outras",
                    "natureza": r["natureza"],
                    "qtd": None,
                    "valor": 0.0,
                    "outras": 0,
                }
                out.append(o)
            o["valor"] = round(o["valor"] + float(r["valor"] or 0), 2)
            o["outras"] += 1
        else:
            out.append(r)
    return out


def _has_column(con: duckdb.DuckDBPyConnection, table: str, column: str) -> bool:
    return bool(
        con.execute(
            "select 1 from information_schema.columns where table_name = ? and column_name = ?",
            [table, column],
        ).fetchone()
    )


def _has_table(con: duckdb.DuckDBPyConnection, name: str) -> bool:
    return (
        con.execute("select count(*) from information_schema.tables where table_name = ?", [name]).fetchone()[
            0
        ]
        > 0
    )


def verba_categorias(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Verba compensatória por categoria (e-TCM, ``spot.metrics.verba``):
    ``{categorias: [{romano, descricao, ordem}],
    por_vereador: [{vereador_id, ano, competencia, categoria, valor, pp, ano_processo}],
    cobertura: {ano: {processos, com_categorias, sem_categorias, meses_sem_categorias}},
    processos: [{vereador_id, ano, competencia, pp, ano_processo, mes_prestacao, arquivo, total, pago, layout}]}``.
    ``processos`` dá a origem de cada linha (documento do e-TCM e mês da prestação em que está), o total declarado
    e o valor pago (empenhos do processo). As linhas de ``por_vereador`` de um processo somam o pago; a categoria
    ``-`` é a parte sem divisão por categoria (processo ``layout = 'nenhum'`` ou incisos que não fecham). As notas fiscais do formulário antigo (só jan–fev/2025) ficam
    no silver/gold (``metrica_verba_nf``) e não vão para o painel, por cobrirem só parte dos reembolsos.
    Sem as tabelas (métrica ainda não rodou), listas/dicionário vazios."""
    categorias = (
        rows(
            con,
            "select categoria_romano as romano, categoria_descricao as descricao, categoria_ordem as ordem "
            "from verba_categorias order by categoria_ordem",
        )
        if _has_table(con, "verba_categorias")
        else []
    )
    if not _has_table(con, "metrica_verba_vereador_categoria_mes"):
        log.warning(
            "metrica_verba_vereador_categoria_mes ausente (rode spot.metrics.verba): verba_categorias vazio"
        )
        return {"categorias": categorias, "por_vereador": [], "cobertura": {}, "processos": []}
    por_vereador = rows(
        con,
        """
        select vereador_id, ano, competencia, categoria_romano as categoria, valor,
               pp_numero as pp, ano_processo
        from metrica_verba_vereador_categoria_mes order by competencia, vereador_id nulls last, categoria_ordem
        """,
    )
    tem_layout = _has_column(con, "metrica_verba_processo", "layout")
    layout = "layout" if tem_layout else "'resumo'"
    cobertura = {
        str(r["ano"]): {
            "processos": r["processos"],
            "com_categorias": r["com_categorias"],
            "sem_categorias": r["sem_categorias"],
            "meses_sem_categorias": sorted(m for m in (r["meses_sem"] or "").split(",") if m),
        }
        for r in rows(
            con,
            f"""
            select ano, count(*) as processos,
                   sum(case when {layout} <> 'nenhum' then 1 else 0 end)::int as com_categorias,
                   sum(case when {layout} = 'nenhum' then 1 else 0 end)::int as sem_categorias,
                   string_agg(distinct case when {layout} = 'nenhum' then competencia end, ',' order by 1) as meses_sem
            from metrica_verba_processo group by 1 order by 1
            """,
        )
    }
    pago = "valor_pago" if _has_column(con, "metrica_verba_processo", "valor_pago") else "total_declarado"
    processos = rows(
        con,
        f"""
        select vereador_id, ano, competencia, pp_numero as pp, ano_processo, mes_prestacao, arquivo,
               total_declarado as total, {pago} as pago, {layout} as layout
        from metrica_verba_processo where vereador_id is not null order by competencia, vereador_id, pp_numero
        """,
    )
    if cobertura:
        cobertura["0"] = {
            "processos": sum(c["processos"] for c in cobertura.values()),
            "com_categorias": sum(c["com_categorias"] for c in cobertura.values()),
            "sem_categorias": sum(c["sem_categorias"] for c in cobertura.values()),
            "meses_sem_categorias": sorted(m for c in cobertura.values() for m in c["meses_sem_categorias"]),
        }
    return {
        "categorias": categorias,
        "por_vereador": por_vereador,
        "cobertura": cobertura,
        "processos": processos,
    }


def composicao_camara(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """``camara.json``: quem ocupa as cadeiras, a Mesa Diretora e o tamanho da equipe de assessores.

    - ``cadeiras``: ``vereador_id`` em exercício na última sessão ordinária da frequência (sem sentinelas), com a
      data em ``referencia``. É a lista que fecha 43, ao contrário da ``situacao`` do site da Câmara, que mistura
      suplentes que já saíram.
    - ``mesa``: seed ``mesa_diretora.csv`` (página oficial /mesa-diretora), ``[{ordem, cargo, v, tipo}]``.
    - ``assessores``: matrículas distintas com função ``ASSESSOR PARLAMENTAR%`` (inclui o Especial G-30) na última
      competência completa da consulta de pessoal do TCM-BA (meses com menos de 75% da mediana são descartados,
      como em ``metrics/custo.py``). ``null`` sem a tabela ``tcm_pessoal``.
    """
    ref = con.execute(
        "select max(data_sessao) from presenca_mvp where tipo_sessao_codigo = 1 and not sentinela"
    ).fetchone()[0]
    cadeiras = [
        r["vereador_id"]
        for r in rows(
            con,
            f"""
            select distinct vereador_id from presenca_mvp
            where data_sessao = DATE '{ref}' and tipo_sessao_codigo = 1 and not sentinela and em_exercicio
              and vereador_id is not null
            order by 1
            """,
        )
    ]
    mesa = (
        rows(con, "select ordem, cargo, vereador_id as v, tipo from mesa_diretora order by ordem")
        if _has_table(con, "mesa_diretora")
        else []
    )
    assessores = None
    if _has_table(con, "tcm_pessoal"):
        meses = rows(
            con,
            """
            select competencia, count(distinct matricula) as total,
                   count(distinct matricula) filter (where funcao ilike 'ASSESSOR PARLAMENTAR%') as n,
                   count(distinct matricula) filter (where funcao ilike 'ASSESSOR PARLAMENTAR ESPECIAL%') as especiais
            from tcm_pessoal group by 1 order by 1
            """,
        )
        if meses:
            mediana = sorted(m["total"] for m in meses)[len(meses) // 2]
            completos = [m for m in meses if m["total"] >= 0.75 * mediana]
            ult = completos[-1]
            assessores = {
                "n": ult["n"],
                "especiais": ult["especiais"],
                "servidores": ult["total"],
                "competencia": ult["competencia"],
                "fonte": "TCM-BA, consulta de pessoal",
            }
    return {
        "referencia": str(ref) if ref else None,
        "cadeiras": cadeiras,
        "mesa": mesa,
        "assessores": assessores,
    }


def _nome(s: str | None) -> str:
    return " ".join(re.sub(r"[^A-Z ]", " ", _sem_acento(s or "").upper()).split())


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def subsidios_pagos(con: duckdb.DuckDBPyConnection) -> dict[str, list[dict[str, Any]]]:
    """``{vereador_id: [{c: competencia, bruto, d13}]}`` das linhas "Agente Político" de ``tcm_pessoal``.

    A consulta do TCM não traz todos os vereadores em todo mês (36 de 43 em set/2026): ausência na folha não
    quer dizer que o subsídio não foi pago."""
    if not _has_table(con, "tcm_pessoal"):
        return {}
    nomes: dict[str, str] = {}
    if _has_table(con, "tse_candidatura_vereador"):
        for r in rows(
            con,
            "select vereador_id, nome_candidato from tse_candidatura_vereador "
            "where vereador_id is not null and ano = 2024",
        ):
            nomes[_nome(r["nome_candidato"])] = r["vereador_id"]
    for r in rows(con, "select vereador_id, nome_civil from vereador_dim where nome_civil is not null"):
        nomes.setdefault(_nome(r["nome_civil"]), r["vereador_id"])
    pontas: dict[tuple[str, str], list[str]] = {}
    for n, vid in nomes.items():
        t = n.split()
        if t:
            pontas.setdefault((t[0], t[-1]), []).append(vid)
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows(
        con,
        """
        select competencia, servidor, remuneracao_bruta as bruto, coalesce(decimo_terceiro, 0) as d13
        from tcm_pessoal where regime = 'Agente Político' order by competencia
        """,
    ):
        n = _nome(r["servidor"])
        t = n.split()
        vid = nomes.get(n) or (lambda c: c[0] if len(set(c)) == 1 else None)(pontas.get((t[0], t[-1]), []))
        if vid:
            out.setdefault(vid, []).append({"c": r["competencia"], "bruto": r["bruto"], "d13": r["d13"]})
    return out


def export(db: Path = DB_DEFAULT, out: Path = OUT_DEFAULT, hoje: date | None = None) -> Path:
    """Gera os JSON de ``site/data/``. Chaves acrescentadas pelo backlog do dashboard:

    - ``vereadores.json[]``: ``nascimento``, ``gabinete_numero``, ``licenca_data``, ``licenca_dias``, ``suplente_nome``
      (perfil da Câmara) e ``cargo_mesa`` = ``{"2025": "3ª Vice-Presidência" | null, ...}`` por ano com folha.
      ``eleicoes`` = anos em que foi eleito vereador de Salvador (TSE), ex. ``[2012, 2016, 2020, 2024]``.
    - ``presenca.json.sessoes[].ata_url`` (primeira URL da ata no catálogo) e ``presenca.json.grade`` =
      ``[{"v": vereador_id, "ano": int, "n": [num_sessao...], "s": "PAL..."}]`` (ver ``compactar_grade``).
    - ``custo.json.mensal[].parcial`` e ``custo_camara.json.mensal[].parcial`` (bool, ver ``marcar_parciais``).
    - ``custo.json.rotatividade`` (b5, ``spot.metrics.custo`` → ``metrica_rotatividade_*``; só assessores CC10):
      ``anual`` = ``[{v: vereador_id | null, cc: centro_custo_codigo, ano, meses, pessoas: matrículas distintas,
      vagas: média de assessores/mês, razao: pessoas ÷ vagas, ent: entradas, sai: saídas, perm: permanência média em
      meses, fonte: "rh_site" | "tcm_reconstruida" | "nao_publicada"}]`` (a linha ``v = null, cc = 0`` é o centro de
      custo fictício "lotação não publicada" de 2026); ``mensal`` = ``[{comp: competência, cc, v, ent, sai,
      n: assessores no mês, fonte}]``; ``casa`` = ``[{ano, meses, pessoas, pessoas_sem_lot, vagas, razao, ent, sai,
      perm}]``. Entrada = matrícula presente no mês e ausente no mês anterior da série (2025-01 não gera entradas);
      saída = presente e ausente no seguinte (o último mês não gera saídas); 2026-07 não existe na folha. Em 2026 a
      folha é reconstruída do TCM e os contratados de 2026 não têm lotação: entradas de gabinete subestimadas, todas
      no ``cc = 0``; ``fonte`` marca isso linha a linha (ver ``SQL_ROTATIVIDADE_BASE`` em ``metrics/custo.py``).
    - ``custo_camara.json.diarias`` (b16) = ``[{numero, data, ano, competencia_ref, credor, vereador_id | null,
      objeto (≤ 200 chars, CPF mascarado), valor, anulacao}]`` dos empenhos ``categoria = 'diaria'`` (credor →
      ``vereador_alias`` com ``fonte = 'empenho'``), e ``diarias_resumo`` = ``[{ano, n, total, n_vereador,
      total_vereador}]`` (``total`` líquido de anulações; ver ``resumo_diarias``).
    - ``custo_camara.json.rubricas`` (b13) = ``[{competencia, grupo_regime, tipo_folha | null, rubrica_codigo | null,
      rubrica, natureza: "remuneracao" | "desconto", qtd | null, valor, outras?}]`` da folha sintética do e-TCM, cada
      folha contada uma vez (``metrica_folha_sintetica_rubrica``); rubricas < 0,5% do Σ|valor| do grupo
      (competência × grupo × tipo × natureza) viram uma linha ``rubrica = "Outras"`` com ``outras`` = nº agregado
      (ver ``agregar_rubricas_pequenas``). ``custo_camara.json.folha_tipos`` = ``[{competencia, grupo_regime,
      tipo_folha | null, n_folhas, servidores, remuneracao, descontos, liquido, n_nao_alta}]``
      (``metrica_folha_sintetica_tipo``; ``tipo_folha`` null = folha cujo tipo o PDF não traz, p.ex. "Férias
      Complementar"; ``n_nao_alta`` > 0 = OCR com confiança média/baixa, a soma das rubricas pode não fechar).
    """
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db), read_only=True)
    hoje = hoje or date.today()

    # vereadores.json: dimensão + cadastro do perfil da Câmara (tabela ``vereadores``: nascimento, gabinete_numero,
    # licenca_data, licenca_dias, suplente_nome; null quando o perfil não traz) + ``cargo_mesa`` por ano
    # ({"2025": "3ª Vice-Presidência", "2026": null}; {} para quem não teve folha de gabinete), derivado do
    # ``centro_custo_label`` da última competência de cada ano em ``metrica_custo_gabinete`` (ver ``cargo_mesa``).
    vereadores = rows(
        con,
        """
        select d.vereador_id, d.nome_parlamentar, d.partido, d.situacao, d.gabinete_cc_codigo, d.fonte_url,
               v.nascimento, v.gabinete_numero, v.licenca_data, v.licenca_dias, v.suplente_nome,
               {bio} as bio, {foto} as foto_url
        from vereador_dim d left join vereadores v using (vereador_id) order by d.nome_parlamentar
        """.format(
            bio="v.bio" if _has_column(con, "vereadores", "bio") else "NULL::VARCHAR",
            foto="v.foto_url" if _has_column(con, "vereadores", "foto_url") else "NULL::VARCHAR",
        ),
    )
    # Foto: só quando o arquivo já está em site/fotos/<slug>.jpg (collect.vereadores --fotos); caminho relativo ao site.
    # Redes sociais: seed curado data/seeds/vereador_redes.csv (instagram, x), quando existir.
    redes: dict[str, dict[str, str]] = {}
    redes_csv = SEEDS / "vereador_redes.csv"
    if redes_csv.exists():
        with redes_csv.open(encoding="utf-8") as f:
            redes = {r["vereador_id"]: r for r in csv.DictReader(f)}
    for v in vereadores:
        foto = out.parent / "fotos" / f"{v['vereador_id']}.jpg"
        v["foto"] = f"fotos/{v['vereador_id']}.jpg" if foto.exists() else None
        v.pop("foto_url", None)
        r = redes.get(v["vereador_id"], {})
        v["instagram"] = r.get("instagram") or None
        v["x"] = r.get("x") or None
    cargos: dict[str, dict[str, str | None]] = {}
    for r in rows(
        con,
        """
        select vereador_id, left(competencia, 4) as ano, arg_max(centro_custo_label, competencia) as centro_custo_label
        from metrica_custo_gabinete group by 1, 2 order by 1, 2
        """,
    ):
        cargos.setdefault(r["vereador_id"], {})[r["ano"]] = cargo_mesa(r["centro_custo_label"])
    for v in vereadores:
        v["cargo_mesa"] = cargos.get(v["vereador_id"], {})
    # Bloco político (seed curado data/seeds/vereador_bloco.csv, com fonte por linha): "base" | "oposicao" | null.
    blocos = (
        {r["vereador_id"]: r for r in rows(con, "select vereador_id, bloco, lideranca from vereador_bloco")}
        if _has_table(con, "vereador_bloco")
        else {}
    )
    for v in vereadores:
        b = blocos.get(v["vereador_id"], {})
        v["bloco"] = b.get("bloco") or None
        v["lideranca"] = b.get("lideranca") or None
    # Eleições municipais em que foi eleito vereador de Salvador (TSE, parse/tse.py). Suplência exercida não conta.
    eleicoes: dict[str, list[int]] = {}
    if _has_table(con, "tse_candidatura_vereador"):
        for r in rows(
            con,
            "select vereador_id, ano from tse_candidatura_vereador "
            "where eleito and vereador_id is not null order by ano",
        ):
            eleicoes.setdefault(r["vereador_id"], []).append(int(r["ano"]))
    for v in vereadores:
        v["eleicoes"] = eleicoes.get(v["vereador_id"], [])
    # Subsídio pago, mês a mês, pela consulta de pessoal do TCM-BA (regime "Agente Político"). A folha não tem
    # vereador_id: liga pelo nome civil (TSE 2024 ou seed); se não houver nome exato, primeiro + último nome únicos.
    pagos = subsidios_pagos(con)
    for v in vereadores:
        v["subsidios"] = pagos.get(v["vereador_id"], [])

    presenca = rows(
        con,
        """
        select vereador_id, ano, sessoes_ordinarias_em_exercicio as em_exercicio, presentes, ausentes, licenciado,
               taxa_presenca, sem_dado, ordinarias_do_ano, fracao_faltas_lom27, alerta_lom27
        from metrica_presenca
        union all
        -- legislatura inteira (ano = 0): somas por vereador; taxa e fração recalculadas; alerta se algum ano alertou
        select vereador_id, 0 as ano, sum(sessoes_ordinarias_em_exercicio), sum(presentes), sum(ausentes), sum(licenciado),
               case when sum(presentes) + sum(ausentes) > 0 then round(sum(presentes) * 1.0 / (sum(presentes) + sum(ausentes)), 4) end,
               sum(sessoes_ordinarias_em_exercicio) < 10, sum(ordinarias_do_ano),
               case when sum(ordinarias_do_ano) > 0 then round(sum(ausentes) * 1.0 / sum(ordinarias_do_ano), 3) end,
               bool_or(alerta_lom27)
        from metrica_presenca group by vereador_id
        order by ano, ausentes desc, vereador_id
        """,
    )
    # Linha do tempo da Casa: % de presentes por sessão ordinária (Licenciado fora da base) + ``ata_url`` (primeira
    # URL de ``sessao.ata_urls`` do catálogo; null quando a sessão não está no catálogo ou não tem PDF).
    sessoes = rows(
        con,
        """
        select p.ano, p.num_sessao, p.data_sessao,
               count(*) filter (where p.status = 'Presente') as presentes,
               count(*) filter (where p.status = 'Ausente') as ausentes,
               count(*) filter (where p.status = 'Licenciado') as licenciados,
               any_value(s.ata_urls) as ata_urls
        from presenca_mvp p
        left join sessao s on s.ano = p.ano and s.num_sessao = p.num_sessao and s.tipo_sessao_codigo = 1
             and not s.sentinela
        where p.tipo_sessao_codigo = 1 and not p.sentinela
        group by 1, 2, 3 order by p.data_sessao, p.num_sessao
        """,
    )
    for s_ in sessoes:
        s_["ata_url"] = primeira_url(s_.pop("ata_urls"))
    # Grade individual (b7): status de cada vereador em cada sessão ordinária não sentinela de 2025+, compactada por
    # vereador × ano (ver ``compactar_grade``).
    grade = compactar_grade(
        rows(
            con,
            """
            select vereador_id, ano, num_sessao, status from presenca_mvp
            where tipo_sessao_codigo = 1 and not sentinela and ano >= 2025 and vereador_id is not null
            """,
        )
    )
    # Faltas por vereador por sessão (para o detalhe individual): lista compacta de sessões ausentes.
    faltas = rows(
        con,
        """
        select vereador_id, ano, list(num_sessao order by num_sessao) as sessoes_ausente
        from presenca_mvp
        where tipo_sessao_codigo = 1 and not sentinela and status = 'Ausente'
        group by 1, 2
        """,
    )

    produtividade = rows(
        con,
        """
        select vereador_id, ano, meses_exercicio, n_total, n_ple, n_plc, n_pel, n_pdl, n_pre, n_rep, n_rup, n_pin,
               n_moc, n_outros, n_excluidas_regex, vol_ponderado, vol_ponderado_12m
        from metrica_produtividade
        union all
        -- legislatura (ano = 0): somas; ritmo anual = ponderado / meses × 12
        select vereador_id, 0, sum(meses_exercicio), sum(n_total), sum(n_ple), sum(n_plc), sum(n_pel), sum(n_pdl), sum(n_pre),
               sum(n_rep), sum(n_rup), sum(n_pin), sum(n_moc), sum(n_outros), sum(n_excluidas_regex), round(sum(vol_ponderado), 2),
               case when sum(meses_exercicio) > 0 then round(sum(vol_ponderado) * 12.0 / sum(meses_exercicio), 2) else 0 end
        from metrica_produtividade group by vereador_id
        order by ano, vol_ponderado_12m desc
        """,
    )
    pesos = rows(con, "select tipo, peso, observacao from pesos_v0 order by peso desc, tipo")
    outros_autores = rows(
        con,
        "select autor_fonte, ano, n from produtividade_outros_autores "
        "union all select autor_fonte, 0, sum(n) from produtividade_outros_autores group by autor_fonte order by ano, n desc",
    )
    resumo_check = rows(
        con,
        """
        select ano, sum(quantidade) as total_resumo from produtividade_resumo group by ano order by ano
        """,
    )

    custo_anual = rows(
        con,
        """
        select vereador_id, centro_custo_codigo, ano, meses_com_folha, meses_com_subsidio, meses_com_estagiarios,
               media_servidores, media_assessores_parlamentares, folha_assessores, folha_outros, bolsas_estagiarios,
               subsidio, meses_com_verba, verba_compensatoria_observada, verba_compensatoria_teto, custo_observado,
               custo_com_teto_verba, media_mensal_custo_observado, ranking
        from metrica_custo_anual
        union all
        -- legislatura (ano = 0): agregado de todos os meses do gabinete em metrica_custo_gabinete
        select * from (
            select vereador_id, centro_custo_codigo, 0 as ano, count(*) as meses_com_folha,
                   count(*) filter (where coalesce(subsidio, 0) > 0) as meses_com_subsidio,
                   count(*) filter (where bolsas_estagiarios is not null) as meses_com_estagiarios,
                   round(avg(n_servidores), 2), round(avg(n_assessores_parlamentares), 2),
                   round(sum(folha_assessores), 2), round(sum(folha_outros), 2), round(sum(coalesce(bolsas_estagiarios, 0)), 2),
                   round(sum(coalesce(subsidio, 0)), 2), count(*) filter (where coalesce(verba_compensatoria_observada, 0) > 0),
                   round(sum(coalesce(verba_compensatoria_observada, 0)), 2), round(sum(coalesce(verba_compensatoria_teto, 0)), 2),
                   round(sum(custo_observado), 2), round(sum(custo_com_teto_verba), 2),
                   round(sum(custo_observado) / count(*), 2) as media_mensal_custo_observado,
                   row_number() over (order by sum(custo_observado) / count(*) desc) as ranking
            from metrica_custo_gabinete where vereador_id is not null group by vereador_id, centro_custo_codigo
        )
        order by ano, ranking
        """,
    )
    custo_mensal = rows(
        con,
        """
        select vereador_id, centro_custo_codigo, competencia, n_assessores_parlamentares as n_assessores,
               folha_assessores, n_estagiarios, bolsas_estagiarios, subsidio, verba_compensatoria_observada,
               n_empenhos_verba, custo_observado
        from metrica_custo_gabinete order by competencia, vereador_id
        """,
    )
    custo_casa = rows(
        con,
        """
        select competencia, sum(folha_assessores) as folha_assessores, sum(coalesce(bolsas_estagiarios, 0)) as bolsas,
               sum(coalesce(subsidio, 0)) as subsidio,
               sum(coalesce(verba_compensatoria_observada, 0)) as verba_compensatoria_observada,
               sum(custo_observado) as custo_observado,
               count(*) as gabinetes, sum(n_assessores_parlamentares) as assessores
        from metrica_custo_gabinete group by 1 order by 1
        """,
    )
    parametros = rows(con, "select * from parametros_custo")
    # Verba compensatória por vereador × competência (2025 e 2026; independe da folha, que só existe para 2025).
    # vereador_id NULL = credor sem alias (fica visível, não entra no custo por gabinete).
    verba = rows(
        con,
        """
        select vereador_id, competencia, credor, n_empenhos, n_anulacoes, n_fallback_mes_emissao,
               verba_compensatoria_observada, verba_compensatoria_teto,
               verba_compensatoria_observada > verba_compensatoria_teto as acima_do_teto, empenhos
        from metrica_verba_vereador order by competencia, vereador_id nulls last
        """,
    )

    # Rotatividade de assessores (b5): tabelas de ``spot.metrics.custo``; vazias se a métrica ainda não rodou.
    tem_rot = _has_table(con, "metrica_rotatividade_gabinete")
    if not tem_rot:
        log.warning("metrica_rotatividade_* ausente (rode spot.metrics.custo): custo.json.rotatividade vazio")
    rotatividade = {
        "anual": rows(
            con,
            """
            select vereador_id as v, centro_custo_codigo as cc, ano, meses, pessoas_distintas as pessoas,
                   vagas_medias as vagas, razao, entradas as ent, saidas as sai, permanencia_media_meses as perm,
                   fonte_lotacao as fonte
            from metrica_rotatividade_gabinete order by ano, razao desc, cc
            """,
        )
        if tem_rot
        else [],
        "mensal": rows(
            con,
            """
            select competencia as comp, centro_custo_codigo as cc, vereador_id as v, entradas as ent, saidas as sai,
                   n_assessores as n, fonte_lotacao as fonte
            from metrica_rotatividade_mes order by comp, cc
            """,
        )
        if tem_rot
        else [],
        "casa": rows(
            con,
            """
            select ano, meses, pessoas_distintas as pessoas, pessoas_sem_lotacao as pessoas_sem_lot,
                   vagas_medias as vagas, razao, entradas as ent, saidas as sai, permanencia_media_meses as perm
            from metrica_rotatividade_casa order by ano
            """,
        )
        if tem_rot
        else [],
    }

    # Diárias (b16): empenhos ``categoria = 'diaria'`` (2024+), credor → vereador quando há alias ``fonte = 'empenho'``.
    diarias = (
        rows(
            con,
            """
            select e.numero, e.data, e.ano, e.competencia_ref, e.credor, a.vereador_id, e.objeto, e.valor, e.anulacao
            from empenho e left join vereador_alias a on a.fonte = 'empenho' and a.alias = e.credor
            where e.categoria = 'diaria' order by e.data, e.numero
            """,
        )
        if _has_table(con, "empenho")
        else []
    )
    for d in diarias:
        d["objeto"] = diaria_objeto(d["objeto"])
    diarias_resumo = resumo_diarias(diarias)
    for a in diarias_resumo:
        log.info(
            "diárias %d: %d empenhos, R$ %.2f; a vereadores: %d, R$ %.2f",
            a["ano"], a["n"], a["total"], a["n_vereador"], a["total_vereador"],
        )  # fmt: skip

    # Folha sintética por rubrica e por tipo de folha (b13); vazias se a métrica ainda não rodou.
    rubricas = (
        agregar_rubricas_pequenas(
            rows(
                con,
                """
                select competencia, grupo_regime, tipo_folha, rubrica_codigo, rubrica, natureza, qtd, valor
                from metrica_folha_sintetica_rubrica order by competencia, grupo_regime, tipo_folha, natureza, valor desc
                """,
            )
        )
        if _has_table(con, "metrica_folha_sintetica_rubrica")
        else []
    )
    folha_tipos = (
        rows(
            con,
            """
            select competencia, grupo_regime, tipo_folha, n_folhas, servidores, remuneracao, descontos, liquido, n_nao_alta
            from metrica_folha_sintetica_tipo order by competencia, grupo_regime, tipo_folha
            """,
        )
        if _has_table(con, "metrica_folha_sintetica_tipo")
        else []
    )

    # ---- Custo da Câmara (folha inteira, por regime, função, grau e setor) ----
    con.execute(
        """
        create temp view folha_n as
        select *,
               case when regime ilike '%estatut%' then 'Estatutário'
                    when regime ilike '%comiss%' then 'Cargo em comissão' else regime end as regime_n,
               (gabinete_vereador is not null and gabinete_vereador <> '') as em_gabinete,
               case when funcao like 'ASSESSOR PARLAMENTAR%CC10' then 'ASSESSOR PARLAMENTAR (CC10)'
                    else funcao end as funcao_grupo,
               case
                 when centro_custo_label like 'GABINETE DA PRESIDENCIA%' then 'Gabinete da Presidência (estrutura)'
                 when centro_custo_label like 'DIREL%' or centro_custo_label like 'DIRETORIA LEGISLATIVA%' then 'Diretoria Legislativa'
                 when centro_custo_label like 'DG %' or centro_custo_label like 'DG-%' or centro_custo_label like 'DIRETORIA GERAL%' then 'Diretoria Geral'
                 when centro_custo_label like 'DF %' or centro_custo_label like 'DIRETORIA FINANCEIRA%' then 'Diretoria Financeira'
                 when centro_custo_label like 'PROCURADORIA%' or centro_custo_label like 'PROJUR%' then 'Procuradoria'
                 when centro_custo_label like 'DIRETORIA DE COMUNICA%' then 'Comunicação'
                 when centro_custo_label like 'CONTROLADORIA%' then 'Controladoria'
                 when centro_custo_label like 'LOTAÇÃO NÃO PUBLICADA%' then 'Lotação não publicada (2026)'
                 when centro_custo_label like 'ASSISTÊNCIA MILITAR%' then 'Assistência militar'
                 else 'Outros setores' end as setor
        from folha
        """
    )
    camara_mensal = rows(
        con,
        """
        select competencia, ano, fonte, n_servidores, folha_total, folha_gabinetes, folha_estrutura, folha_sem_lotacao,
               n_gabinetes, n_estrutura, n_sem_lotacao, n_estagiarios, bolsas, subsidios, verba, folha_sintetica_total,
               folha_sintetica_normal, subsidios_pagos, n_subsidios, custo_total
        from metrica_custo_camara_mensal order by competencia
        """,
    )
    # a5: ``parcial`` (exportação do TCM-BA possivelmente incompleta). Casa: n_servidores < 80% da mediana do ano,
    # ou n_subsidios conhecido e < 30 (2026-01 tem 1). False explícito nos demais.
    n_parc_casa = marcar_parciais(
        camara_mensal,
        "n_servidores",
        lambda r: r["ano"],
        extra=lambda r: r["n_subsidios"] is not None and r["n_subsidios"] < 30,
    )
    meses_parciais_casa = {r["competencia"] for r in camara_mensal if r["parcial"]}
    # Gabinete × mês herda só o sinal da Casa: a mediana por gabinete marcaria variação real de lotação
    # (jan/2025, contratados de 2026 sem lotação) como "exportação incompleta".
    n_parc_gab = 0
    for r in custo_mensal:
        r["parcial"] = r["competencia"] in meses_parciais_casa
        n_parc_gab += r["parcial"]
    log.info(
        "meses parciais: Casa %d (%s); gabinete × mês %d",
        n_parc_casa,
        sorted(meses_parciais_casa),
        n_parc_gab,
    )
    # Regime pela folha sintética do e-TCM (todos os anos; em 2026 é a única fonte): média mensal por grupo.
    camara_regime_sintetico = rows(
        con,
        """
        select left(competencia, 4)::int as ano, grupo_regime as regime, count(*) as meses,
               avg(servidores) as n_medio, sum(remuneracao) as total_ano, sum(remuneracao) / count(*) as media_mensal,
               sum(remuneracao_normal) / count(*) as media_mensal_normal
        from metrica_folha_sintetica group by 1, 2 order by 1, 2
        """,
    )
    camara_regime = rows(
        con,
        """
        select left(competencia, 4)::int as ano, regime_n as regime, em_gabinete, count(distinct matricula) as pessoas,
               count(*) * 1.0 / count(distinct competencia) as n_medio, sum(proventos) as total_ano,
               sum(proventos) / count(distinct competencia) as media_mensal
        from folha_n group by 1, 2, 3
        union all
        select 0, regime_n, em_gabinete, count(distinct matricula), count(*) * 1.0 / count(distinct competencia), sum(proventos),
               sum(proventos) / count(distinct competencia)
        from folha_n group by 2, 3 order by 1, 2, 3
        """,
    )
    camara_funcao = rows(
        con,
        """
        select left(competencia, 4)::int as ano, funcao, funcao_grupo, grau, regime_n as regime, em_gabinete,
               count(distinct matricula) as pessoas, count(*) * 1.0 / count(distinct competencia) as n_medio,
               sum(proventos) as total_ano, sum(proventos) / count(distinct competencia) as media_mensal,
               sum(proventos) / count(*) as media_por_servidor_mes
        from folha_n group by 1, 2, 3, 4, 5, 6
        union all
        select 0, funcao, funcao_grupo, grau, regime_n, em_gabinete, count(distinct matricula),
               count(*) * 1.0 / count(distinct competencia), sum(proventos), sum(proventos) / count(distinct competencia),
               sum(proventos) / count(*)
        from folha_n group by 2, 3, 4, 5, 6 order by total_ano desc
        """,
    )
    camara_setor = rows(
        con,
        """
        select left(competencia, 4)::int as ano, setor, centro_custo_codigo, any_value(centro_custo_label) as centro_custo_label,
               count(distinct matricula) as pessoas, count(*) * 1.0 / count(distinct competencia) as n_medio,
               sum(proventos) as total_ano, sum(proventos) / count(distinct competencia) as media_mensal
        from folha_n where not em_gabinete group by 1, 2, 3
        union all
        select 0, setor, centro_custo_codigo, any_value(centro_custo_label), count(distinct matricula),
               count(*) * 1.0 / count(distinct competencia), sum(proventos), sum(proventos) / count(distinct competencia)
        from folha_n where not em_gabinete group by 2, 3 order by total_ano desc
        """,
    )
    camara_setor_mensal = rows(
        con,
        """
        select setor, competencia, count(*) as n, sum(proventos) as total
        from folha_n where not em_gabinete group by 1, 2 order by 1, 2
        """,
    )
    # Gabinetes: assessores por grau e por vereador (para o breakdown por função dentro da visão Gabinetes)
    gab_grau = rows(
        con,
        """
        with base as (
            select left(f.competencia, 4)::int as ano, g.vereador_id, coalesce(f.grau, '') as grau, f.funcao_grupo,
                   f.matricula, f.proventos, f.competencia
            from folha_n f
            join metrica_custo_gabinete g on g.centro_custo_codigo = f.centro_custo_codigo and g.competencia = f.competencia
            where f.em_gabinete and g.vereador_id is not null
        ),
        meses as (select ano, vereador_id, count(distinct competencia) as m from base group by 1, 2),
        meses0 as (select vereador_id, count(distinct competencia) as m from base group by 1)
        select b.ano, b.vereador_id, b.grau, b.funcao_grupo, count(*) * 1.0 / m.m as n_medio,
               sum(b.proventos) / m.m as media_mensal, count(distinct b.matricula) as pessoas
        from base b join meses m using (ano, vereador_id) group by 1, 2, 3, 4, m.m
        union all
        select 0, b.vereador_id, b.grau, b.funcao_grupo, count(*) * 1.0 / m.m, sum(b.proventos) / m.m, count(distinct b.matricula)
        from base b join meses0 m using (vereador_id) group by 2, 3, 4, m.m
        """,
    )

    # Proposições individuais 2025+ (para a tabela filtrável); link da íntegra via DOL quando já coletado.
    has_dol = (
        con.execute(
            "select count(*) from information_schema.tables where table_name = 'proposicao_dol'"
        ).fetchone()[0]
        > 0
    )
    dol_join = (
        "left join proposicao_dol d on d.codigo = b.codigo"
        if has_dol
        else "left join (select null as codigo) d on false"
    )
    dol_cols = (
        "d.dol_data, d.pdf_url, d.n_edicoes, d.variante, d.confianca"
        if has_dol
        else "null as dol_data, null as pdf_url, null as n_edicoes, null as variante, null as confianca"
    )
    proposicoes = rows(
        con,
        f"""
        select b.codigo, b.tipo, b.ano, b.vereador_id, b.autor, b.ementa, b.movimentado, b.situacao, p.localizacao,
               b.exclusao, b.peso, {dol_cols}
        from produtividade_base b
        join proposicao p on p.codigo = b.codigo
        {dol_join}
        order by b.movimentado desc, b.codigo
        """,
    )
    if not has_dol:
        log.warning("tabela proposicao_dol ausente: links da íntegra ficam vazios")

    (ult_2026,) = con.execute(
        "select max(data_sessao) from presenca_mvp where ano = 2026 and tipo_sessao_codigo = 1"
    ).fetchone()
    (n_prop,) = con.execute("select count(*) from proposicao where not sentinela").fetchone()
    meta = {
        "gerado_em": hoje.isoformat(),
        "anos": [2025, 2026],
        "legislatura": {"ano": 0, "rotulo": "2025–2028", "inicio": "2025-01"},
        "ultima_sessao_2026": ult_2026,
        "n_proposicoes_base": n_prop,
        "resumo_oficial_por_ano": resumo_check,
        "parametros_custo": parametros,
        "pesos": pesos,
        "fontes": {
            "frequencia": "http://45.4.247.157/leg/salvador/LEG_SYS_frequencia/",
            "sessoes": "http://45.4.247.157/leg/salvador/LEG_SYS_sessao_ata/",
            "proposicoes": "https://cmsalvador.sys.inf.br/cl/prop_interna/",
            "resumo_proposicoes": "http://45.4.247.157/leg/salvador/LEG_SYS_produtividade_parlamentar_proposicao/",
            "rh": "https://www.cms.ba.gov.br/transparencia/recursos-humanos",
            "empenhos": "https://cmsalvador.sys.inf.br/ca/gridRegistroEmpenho/",
            "etcm": "https://e.tcm.ba.gov.br/epp/ConsultaPublica/listView.seam",
            "vereadores": "https://www.cms.ba.gov.br/vereadores",
            "subsidio": "http://www.dom.salvador.ba.gov.br/images/stories/pdf/2024/dezembro/dom-8937-20-12-2024.pdf",
        },
    }

    _write(out, "meta.json", meta)
    _write(out, "vereadores.json", vereadores)
    _write(out, "camara.json", composicao_camara(con))
    _write(
        out, "presenca.json", {"vereadores": presenca, "sessoes": sessoes, "faltas": faltas, "grade": grade}
    )
    _write(out, "produtividade.json", {"vereadores": produtividade, "outros_autores": outros_autores})
    _write(
        out,
        "custo.json",
        {
            "anual": custo_anual,
            "mensal": custo_mensal,
            "casa": custo_casa,
            "verba": verba,
            "rotatividade": rotatividade,
        },
    )
    # gabinetes.json: quem trabalhou em cada gabinete (perfil). Uma linha por pessoa × vereador: nome e matrícula
    # (agentes públicos, já publicados pela Câmara), função e grau da última competência, salário = mediana mensal dos
    # proventos (evita 13º e férias), admissão, primeira e última competência no gabinete e se segue lotado na última
    # competência do gabinete. Em 2026 a lotação é a última conhecida de 2025 (``fonte_ultima = 'tcm_pessoal'``).
    gabinetes = rows(
        con,
        """
        with base as (
            select g.vereador_id, f.matricula, f.servidor, f.funcao, f.grau, f.admissao, f.proventos, f.competencia,
                   coalesce(f.fonte, 'rh_site') as fonte
            from folha f
            join metrica_custo_gabinete g
              on cast(g.centro_custo_codigo as varchar) = cast(f.centro_custo_codigo as varchar)
             and g.competencia = f.competencia
            where g.vereador_id is not null and coalesce(f.gabinete_vereador, '') <> ''
        ),
        ult_gab as (select vereador_id, max(competencia) as ult from base group by 1)
        select b.vereador_id as v, b.matricula as mat, any_value(b.servidor) as nome,
               arg_max(b.funcao, b.competencia) as funcao, arg_max(b.grau, b.competencia) as grau,
               min(b.admissao) as admissao, min(b.competencia) as inicio, max(b.competencia) as fim,
               max(b.competencia) = any_value(u.ult) as atual, count(*) as meses,
               round(median(b.proventos), 2) as salario, arg_max(b.fonte, b.competencia) as fonte_ultima
        from base b join ult_gab u using (vereador_id)
        group by 1, 2 order by 1, atual desc, salario desc
        """,
    )
    for g in gabinetes:
        g["funcao"] = re.sub(r"-?\s*G-?\d+\s*(CC\s*\d+)?\s*$", "", g["funcao"] or "").strip(" -") or None
    _write(out, "gabinetes.json", gabinetes)
    _write(out, "proposicoes.json", proposicoes)
    _write(out, "verba_categorias.json", verba_categorias(con))
    _write(
        out,
        "custo_camara.json",
        {
            "mensal": camara_mensal,
            "regime": camara_regime,
            "regime_sintetico": camara_regime_sintetico,
            "lotacao_cobertura": rows(con, "select * from metrica_lotacao_cobertura order by competencia")
            if _has_table(con, "metrica_lotacao_cobertura")
            else [],
            "funcao": camara_funcao,
            "setor": camara_setor,
            "setor_mensal": camara_setor_mensal,
            "gab_grau": gab_grau,
            "diarias": diarias,
            "diarias_resumo": diarias_resumo,
            "rubricas": rubricas,
            "folha_tipos": folha_tipos,
        },
    )
    con.close()
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DB_DEFAULT)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s"
    )
    export(args.db, args.out)


if __name__ == "__main__":
    main()
