# Como votou seu vereador — data sources of the Câmara Municipal do Rio de Janeiro

(São Paulo is documented after the Rio sections; other capitals at the end.)

Research date: 2026-10-13/14. All requests sent with User-Agent
`tomoyo-g0v-research (contact: g0v@tomoyo.systems)`, one request per second, every
response cached under `data/raw/<host>/<sha1>.body` with a `.json` sidecar (URL, method,
form data, time, SHA-256, status). Snapshot: `data/snapshot.json`
(`cd backend && .venv/bin/python -m app.etl.export_snapshot --all`), then the frontend files
(`.venv/bin/python -m app.etl.export_static_frontend`). See "Daily run" at the end.

## Summary

There is no open-data API for legislative activity. Everything parliamentary lives in a
set of HCL/Lotus Domino databases behind `aplicnt.camara.rj.gov.br/APL/Legislativos/*.nsf`
(iframed into the Joomla site `camara.rio`), plus a few PHP includes on `camara.rio`.
Domino's generic URL commands (`?ReadViewEntries&OutputFormat=JSON`, `?SearchView`,
`?OpenDocument`) are not blocked, which gives machine-readable JSON for proposições and
session items. Nominal roll-call votes exist only as free text inside the session
transcripts ("Discursos e Votações"); they are regular enough to parse. Attendance is a
monthly HTML table (also served as an "Excel" file that is really HTML).

TLS note: `*.camara.rio` and `*.camara.rj.gov.br` serve a Sectigo OV leaf certificate
without the intermediate, so Python/curl fail verification by default. The ETL ships
`backend/app/cabundle.pem` = system roots + `Sectigo Public Server Authentication CA OV R36`
(fetched from the AIA URL `http://crt.sectigo.com/SectigoPublicServerAuthenticationCAOVR36.crt`).
Do not disable verification.

robots.txt: `www.camara.rio/robots.txt` is the stock Joomla file (disallows only
`/administrator/`, `/components/`, etc.; nothing we touch). `aplicnt.camara.rj.gov.br`
has no robots.txt (404). `transparencia.camara.rj.gov.br` not checked beyond HTML.

## 1. Vereadores

| | |
|---|---|
| Source (current, 12ª legislatura 2025–2028; the Câmara numbers 2021–2024 as the 11ª) | `https://www.camara.rio/includes_php/vereadores_atuais.php?imprimir=N` (iframed by `/vereadores/quem-sao`) |
| Format | HTML table, ISO-8859-1. Columns: photo (inline base64 JPEG), name (link `vereador.php?cvd=<id>`), party (as `<img alt="PL">` logo), room ("Anexo - 803" / "Palácio - 32-B"), phones, e-mail (HTML-entity obfuscated) |
| Source (previous legislatures) | `https://www.camara.rio/vereadores/anteriores` — HTML table: name (link with same `cvd` id), "Nª - PARTIDO" per legislature, 1ª to 12ª (the 12ª rows are the current members) |
| Profile page | `vereador.php?cvd=N` redirects via JS to `https://www.camara.rio/vereadores/<slug>` (Joomla article; biography text, no structured fields) |
| Identifier | `cvd` (integer, stable across both pages; snapshot uses `cvd:<n>`) |
| Rows obtained | 51 current (list is the plenary roster as published, i.e. titulares plus suplentes in exercise); 330 names on the previous page, 65 of them in the 11ª legislatura (2021–2024) |
| Update frequency | Unknown; page shows the roster of the day |

Not available in structured form: titular vs suplente, start/end of mandate, licences.
The monthly attendance page prints "Considerada a presença do Sr. Vereador X (Proc. N/AAAA)"
notes that reveal licences/justifications; the ETL keeps them as `stats.presenca_pages[].observacoes`.
The `vereadores_atuais` list has 51 names while the attendance table has 56, because the
attendance table includes everyone who held a seat during the month (suplentes who have since left).

## 2. Nominal roll-call votes (votações nominais)

| | |
|---|---|
| Source | Domino database `discvot.nsf` ("Resultado das Sessões — Discursos e Votações"), iframed by `https://www.camara.rio/atividade-parlamentar/plenario/discursos-e-votacoes` |
| Index | View UNID `5d50d39bd976391b83256536006a2502`: `https://aplicnt.camara.rj.gov.br/APL/Legislativos/discvot.nsf/5d50d39bd976391b83256536006a2502?ReadViewEntries&OutputFormat=JSON&ExpandView&Start=1&Count=1000`. Categorised year > month > day; document rows carry session type, phase ("Ordem do Dia", "Prolongamento", "1ª Parte do Grande Expediente"...), item ("Projeto De Lei 758/2025", "Pela Ordem", "Requerimento ..."), author, session number |
| Document | `.../discvot.nsf/<viewunid>/<docunid>?OpenDocument` — HTML with "Data da Sessão: MM/DD/YYYY Hora: HH:MM AM/PM" (US format) and the verbatim transcript of that item of the agenda |
| Coverage | 2010 → today (17 year categories); about 2,500 item-documents per year in 2025–2026, ~70% of them proposições on the Ordem do Dia |
| Full-text search | `?SearchView&Query=<ft query>&Count=1000&SearchMax=5000&Start=N` works (default cap is 250 hits; `SearchMax` lifts it, `Start` pages). `RestrictToCategory` does not work on this view |
| Vote text | Nominal votes appear as: `(Concluída a votação nominal, constata-se que votaram SIM os Senhores Vereadores A, B, C e D 31 (trinta e um). E que votaram NÃO as Senhoras Vereadoras X e Y 2 (duas). Presentes e votando 33 (trinta e três) senhores vereadores)` followed by `O Projeto de Lei nº 758/2025 está aprovado.` Abstentions are written as `ABSTENÇÃO ...` / `absteve-se`. Symbolic votes read `Os senhores vereadores que aprovam permaneçam como estão. Aprovado.` and carry no individual votes. |
| Vote values | Only SIM / NÃO / ABSTENÇÃO are recorded by the painel (RICMRJ art. 273 §3º). There is no "obstrução" value; absence is not listed by name — only the count "Presentes e votando N" is given |

How the ETL gets them: it reads the expanded view for the years in range (to know every
item and its date), runs the full-text searches `votaram AND <year>` for each year,
intersects, and opens each hit document (newest first; `--max-docs 0` = all, which `--all`
sets). Each document yields 0..n roll calls. The proposição's ementa/authors come from the SPL
(section 4) when the number is found there, otherwise from the transcript's `DE AUTORIA DO
VEREADOR X, QUE "..."` sentence. Names are matched to the roster by `app.names.NameResolver`
(exact normalised name, alias table `ALIASES`, token-subset match for "Dr."/middle initials,
close spelling, and a split of run-on strings produced by a missing comma); unmatched names are
listed in `stats.votacoes.unmatched_names`.

Per roll call the parser also records:

- `contagem`: resolved voters per side, checked against the count printed after the names
  ("31 (trinta e um)"; the spelled-out number wins over the digits because the digits carry
  typos such as "2a6"). Differences are listed in `stats.votacoes.impresso_discrepancies`.
- `resultado`: the earliest outcome sentence after the roll call and before the next one:
  `está/estão/foi/foram/fica/considerado + aprovado|rejeitado|mantido|derrubado|prejudicado`,
  a bare "Aprovado."/"Aprovada a Emenda nº 1." line, "Não há quórum para deliberar" →
  `sem_quorum`. When the matter is a veto, "rejeitado" becomes `derrubado` (the veto fell, the
  project goes to promulgation) and "mantido" stays `mantido`. Vocabulary: `aprovado`,
  `rejeitado`, `mantido`, `derrubado`, `prejudicado`, `sem_quorum`, `null`.
- `objeto`: what was voted — `projeto`, `veto`, `emenda`, `substitutivo`, `destaque`,
  `redacao_final` — from the last "Em votação <objeto>" line before the roll call, an upper-case
  VETO in the agenda reading, or the outcome sentence.
- `presidente`: the officer named in "O SR. PRESIDENTE (X)" / "A SRA. PRESIDENTE (X)" that
  announces the result (else the last one before the roll call, else "Presidência do Vereador
  X" at the top). If that person did not vote they get `presidindo` instead of `ausente`.
- `votos`: sim/não/abstenção by id; then `presidindo`; then `ausente` for every other vereador
  in exercise that month, where "in exercise" = has a row in the attendance table of the
  session's month (section 3), falling back to the latest earlier month that has rows
  (`roster_mes` says which month was used; the current month is published only after it ends).

Counts actually obtained: see "Run results" below.

Also checked and discarded: `transparencia.camara.rj.gov.br/acesso-a-informacao/pesquisa/votacao`
is a site-satisfaction poll, not legislative votes. The hotsite
`camara.rio/hotsites/legislatura11/votacao.html` is an explainer. No PDF Diário da Câmara
(DCM) is needed for votes, since the transcripts are online as HTML.

## 3. Attendance (frequência em plenário)

| | |
|---|---|
| Source | `https://www.camara.rio/atividade-parlamentar/plenario/frequencia-dos-vereadores`, HTTP POST `ano=YYYY&mes=M|Nome&sessao=1&submit= Consultar ` |
| Alternative | `https://www.camara.rio/includes_php/vereadores_frequencia_excel.php?ano=YYYY&mes=M` — served as .xls but it is the same HTML table |
| Format | HTML table per month: Vereador (upper case), Faltas, Faltas Abonadas, Total de Faltas; a "last updated dd/mm/yyyy" line; free-text observations about justified presences (`Proc. N/AAAA`) |
| Coverage | Selector offers 2017–2026 |
| Granularity | Monthly totals of absences only. No per-session presence list and no number of sessions held in the month is given on this page (the number of sessions is in `atas.nsf`, see §5) |
| Rows obtained | see Run results (one row per vereador per month, 2021-01 → 2026-10) |

Caveat: the page warns that figures change retroactively when absences are excused
("abonos"); the ETL re-pulls the current and the previous month on every run and older months
only with `--presenca-refresh-from YYYY-MM`. Names are upper-case without the `cvd` id; the ETL
resolves them with `NameResolver` and stores `vereador_id` on each row (unresolved names go to
`stats.presenca_unmatched`). Vereadores that appear in an attendance table but on neither
roster page get a `nome:<slug>` id (`situacao = constou_na_frequencia`); voters that appear in
roll calls only get `nome:<slug>` with `situacao = constou_em_votacao` (3+ roll calls).

## 4. Proposições per vereador

| | |
|---|---|
| Source | SPL — Domino databases `scpro.nsf` (current: proposições in tramitação in the 12ª legislatura, including older ones still alive, oldest PL seen: 1989) and `scpro2124.nsf` (11ª legislatura, 2021–2024, same structure). Earlier legislatures are in the "SPL anterior" ScriptCase app `http://aplicsc.camara.rj.gov.br/scriptcase/sistemas/Spl_ant/` (not explored) |
| Human UI | `https://aplicnt.camara.rj.gov.br/APL/Legislativos/scpro.nsf/Internet/LeiInt?OpenForm` (iframed by `camara.rio/atividade-parlamentar/processo-legislativo/pl`, `.../plc`, `.../req` ...) |
| Machine access | `https://aplicnt.camara.rj.gov.br/APL/Legislativos/<db>/<view>?ReadViewEntries&OutputFormat=JSON&Start=N&Count=1000` |
| Views | `vlei` (PL), `vleicomp` (PLC), `vdecreto` (PDL), `vemenda` (PELOM), `vresolucao` (PR), `vreqinf` (Requerimento de Informações), `vreq` (Requerimentos, categorised Numerado/S/Nº), `vindicacao`, `vmocao`, `voficio`, `vmensagem`; `vprop` gives totals per type; `vautor` is categorised by author (598 author categories in scpro.nsf) |
| Columns (vlei) | `$12` "NNNN/AAAA" (suffix `-A` = substitutivo), `$3` code, `$1` "EMENTA =>AAAATTNNNNN => {Comissão A Comissão B ...}", `$0` date YYYYMMDD, `$8` author(s) ("VEREADOR X", "PODER EXECUTIVO", "MESA DIRETORA", several joined by ", " / " E ") |
| Totals (vprop, scpro.nsf, 2026-10-14) | Indicação 75,994; Mensagem 629; Moção 185,876; Ofício 8,983; PDL 1,615; PELOM 171; PL 12,988; PLC 873; PR 241; Requerimento 21,362; Requerimento de Informações 11,129 |
| Totals (vprop, scpro2124.nsf) | Indicação 28,707; Mensagem 126; Moção 55,376; Ofício 4,530; PDL 498; PELOM 53; PL 4,509; PLC 268; PR 71; Requerimento 4,615; Requerimento de Informações 3,979 |
| Document | `.../<db>/<viewunid>/<docunid>?OpenDocument` (HTML, full tramitação; not fetched by the ETL) |

The ETL downloads PL, PLC, PDL, PELOM, PR (both DBs) and REQINF (current DB) and keeps
rows with `ano >= 2025` (flag `--from-year`). Indicações, moções, requerimentos and ofícios are
skipped for size; the same code path handles them (`SPL_VIEWS` in `export_snapshot.py`).
Author strings are not linked to `cvd` ids by the source. `app.names.split_authors` splits
"VEREADOR A, VEREADORA B E VEREADOR C" (and the transcript form "VEREADORES A, B E C ... E DAS
COMISSÕES ...") into one entry per author, keeping committee names whole; the snapshot stores
`autores` (split, prefix removed), `autores_raw`, `autores_ids` (resolved `cvd`/`nome:` ids,
institutional authors skipped) and `autores_outros` ("E OUTROS" present). Unresolved person
names go to `stats.proposicoes.unmatched_authors`.

## 5. Other published data

- **Atas das sessões**: `https://aplicnt.camara.rj.gov.br/APL/Legislativos/atas.nsf/AtasInt`
  (Domino view by year/month, one HTML document per session: "Ata da 77ª Sessão ORDINÁRIA
  ocorrida em 01/10/2026"). Not parsed. Per-session presence lists, if anywhere, are here.
- **Ordem do dia**: `.../ordemdia.nsf/Formularios/OrdemInt?OpenDocument` (HTML).
- **Comissões**: `https://www.camara.rio/atividade-parlamentar/comissoes/permanentes` etc.
  (Joomla HTML pages; membership not structured). Not parsed.
- **Cota de gabinete / verba de gabinete**: `https://transparencia.camara.rj.gov.br/vereadores/cota-de-gabinete/`
  — four categories (abastecimento e manutenção, auxílio alimentação, locação de veículos
  blindados, selos e correspondências), one DOCman folder per year (2025, 2026) with one
  `.xlsx` per year (e.g. `/vereadores/cota-de-gabinete/auxilio-alimentacao/2026/982-auxilio-alimentacao-2026/file`,
  38 KB). Downloadable and machine-readable but not parsed in this prototype.
- **Salário / lotação dos gabinetes**: `transparencia.camara.rj.gov.br/vereadores/...` pointing to
  the ScriptCase "contracheque" app (`aplicsc.camara.rj.gov.br/scriptcase/sistemas/contracheque/Ctrl_Pesquisa/`).
  Not explored.
- **Official "Dados Abertos" API** (`transparencia.camara.rj.gov.br/acesso-a-informacao/dados-abertos`):
  only two datasets — monthly transfers received (duodécimo) and the staff list, as
  CSV/XML/JSON from `https://aplicsc.camara.rj.gov.br/scriptcase/Sistemas/Portal_Transparencia/DadosAbertos/Cons_Evolucao_Receita_Credito_API_{csv,xml,json}/?ANOREFERENCIA=YYYY`.
  Nothing legislative.
- **Emendas ao orçamento**: not found as data; LOA/LDO pages under
  `camara.rio/atividade-parlamentar/legislacao/orcamento-municipal` are documents.
- **dados.rio**: the municipal data-lake belongs to the Prefeitura; no Câmara datasets were
  found in web search.
- **Existing scrapers**: none found on GitHub/web search for `camara.rj.gov.br` / `camara.rio`.

## Legal basis

- Lei Federal 12.527/2011 (LAI), art. 8º §2º–§3º (publication in open, machine-readable formats),
  cited by the Câmara's own "Dados abertos" page.
- The Câmara's LAI regulation page (`transparencia.camara.rj.gov.br/acesso-a-informacao/regulamentacao-da-lai-na-camara`)
  reproduces the internal procedure (20-day deadline, extension by 10 days, digital delivery
  presumed for internet requests); the page text does not cite the number of the internal
  resolution. No municipal open-data law was identified in this pass.
- Votes: Regimento Interno (RICMRJ) arts. 266 and 273 §3º define the painel options (sim/não/abstenção).

## Data quality caveats

1. Roll-call parsing is regex over transcripts; wording varies by year ("votaram SIM os
   Senhores Vereadores", "votou NÃO o Senhor Vereador", semicolon-separated names and "; e que
   votaram NÃO" in 2021–2023, typos such as "voltaram NÃO", "Abteve-se", "2a6 (vinte e seis)").
   `contagem` is derived from the resolved votes, so it always agrees with `votos`; the printed
   per-side counts are the independent check (`stats.votacoes.impresso_discrepancies`).
   "Presentes e votando N" often differs by one from the names listed (the presiding officer is
   counted as present but is not in the list); that is reported separately and not treated as
   an error.
2. "ausente" in `votos` is inferred from the attendance table of the month (who held a seat
   that month), not from a per-session presence list, which the Câmara does not publish. A
   vereador who took office or left in the middle of the month is wrong for the other part of
   the month; for the current month (not yet published) the previous month's roster is used.
   `presidindo` is only as good as the "PRESIDENTE (X)" detection.
3. Roster-dependent joins (attendance names, vote names, SPL author strings) are by
   normalised name, not id; homonyms and renamed parliamentary names will mis-join. Suplentes
   that camara.rio lists on neither roster page have `nome:` ids and no party/photo.
4. `scpro.nsf` mixes legislatures (proposições still alive from earlier years), so
   "authored in 2025–2028" must filter by `ano`, which the ETL does.
5. Session dates in `discvot.nsf` documents are rendered MM/DD/YYYY (US locale); the view
   categories are dd/mm. Both are handled.
6. The full-text search index may lag behind newly published transcripts; the expanded view
   is authoritative for the list of items.

## Run results (2026-10-14, `python -m app.etl.export_snapshot --all`)

Snapshot `data/snapshot.json`, 14.7 MB, 2,934 source URLs with SHA-256. Cold cache ≈ 1 h
(2,144 session documents at 1 req/s plus index pages); daily re-run from cache ≈ 3 min with
54 network requests (roster pages, 2 attendance months, the live SPL views, the two newest
months of the session index, the current-year search). Tests: `cd backend && .venv/bin/python
-m pytest -q -W error` → 30 passed.

| Entity | Rows | Notes |
|---|---|---|
| vereadores | 95 | 51 em exercício (photo, room, phone, e-mail, party); 40 more from the 11ª (2021–24) list; 3 from 2025–26 attendance tables only (Diego Vaz, Flavio Pato, Wagner Tavares — suplentes with no `cvd`, `nome:` ids); 1 from roll calls only (Matheus Floriano, 119 votes Aug–Dec 2022). Legislature tags: 12ª = 60, 11ª = 69 |
| votações (nominal roll calls) | 1,934 | 2021: 359 · 2022: 415 · 2023: 213 · 2024: 425 · 2025: 346 · 2026: 176. 1,342 PL, 421 PLC, 44 PDL, 38 PR, 27 PELOM, 62 without a parsed proposição (item "Requerimento", "Pela Ordem"). Individual entries: 34,016 sim, 29,974 não, 1,041 abstenção, 60 presidindo, 35,501 inferred ausente |
| — coverage | 2,144 / 2,144 | candidate documents (search ∩ index) read per year: 2021 363, 2022 423, 2023 463, 2024 397, 2025 320, 2026 178 — all read, 0 failed; 1,544 contained ≥ 1 roll call (2023 is low because most hits that year are symbolic votes that only mention "votaram") |
| — resultado | 1,926 / 1,934 | 889 aprovado, 712 derrubado (veto rejected), 98 rejeitado, 95 mantido (veto kept), 112 sem_quorum (vote void, matter returns), 20 prejudicado, 8 not detected (2021: 3, 2022: 1, 2023: 1, 2024: 2, 2026: 1 — result announced in a later document or only by a symbolic re-vote). objeto: 864 veto, 536 emenda, 434 projeto, 82 redação final, 13 substitutivo |
| — consistency | 0 / 34 / 35 | 0 `contagem` vs `votos` mismatches (by construction); 34 roll calls where the count printed after the names differs from the names listed (2024: 15, 2025: 7, 2023: 6, 2021: 3, 2022: 2, 2026: 1; all off by one or two, source-side, listed in `stats.votacoes.impresso_discrepancies`); 35 where "Presentes e votando N" ≠ names (presiding officer counted as present) |
| — presiding officer | 1,933 / 1,934 | detected in all but one; marked `presidindo` when they did not vote (60 cases: Carlo Caiado 24, Tânia Bastos 16, Willian Coelho 5 ...). Absence roster: attendance table of the month; 17 votações (Oct 2026) used Sep 2026 because October is not published yet |
| — names | 42 unmatched strings, all count 1 | 10ª-legislature or guest officers caught by "PRESIDENTE (X)" in 2021 docs (Chiquinho Brazão, Renato Cinco, Tio Carlos, Cláudio Castro ...), 11 roll-call fragments where the transcript lacks the separator the parser expects ("Dr. Gilberto. Dr. João Ricardo", "Presentes 31 (trinta e um) senhores vereadores"), and 2 committee fragments. Each affects one vote entry under a `nome:` id |
| session index | 16,583 items 2021-01→2026-10 | 10,125 are proposições on the agenda; full-text search `votaram AND <year>` returned 2,185 hits |
| presencas | 2,955 | 57 months with rows (2021-01 → 2026-09; 13 recess/unpublished months are empty); every row resolved to an id (`presenca_unmatched` = []) |
| proposicoes | 12,544 | ano ≥ 2021: 6,423 PL, 5,073 REQINF, 633 PDL, 326 PLC, 48 PR, 41 PELOM; per year 2021 2,599 · 2022 1,664 · 2023 2,299 · 2024 1,800 · 2025 2,865 · 2026 1,317. Authors resolved to ids for all but 2 (the committee strings "CONSELHO DE ÉTICA", "DECORO PARLAMENTAR"); 0 with "E OUTROS". Raw view sizes: scpro.nsf vlei 12,988, vleicomp 873, vdecreto 1,615, vemenda 171, vresolucao 241, vreqinf 11,129; scpro2124.nsf vlei 4,508, vleicomp 268, vdecreto 498, vemenda 53, vresolucao 71, vreqinf 3,979 |

Interpretation note: most nominal votes in this Câmara are on vetos (864 of 1,934) and the
usual outcome is `derrubado` (712). An earlier run labelled these "rejeitado" and read the
share as opposition defeats; they are veto overrides by the majority. Treat
`resultado` together with `objeto`.

### Frontend files (`python -m app.etl.export_static_frontend`)

Written under `frontend/lib/`, shapes follow `frontend/lib/static-api.ts`:

| File | Size | Content |
|---|---|---|
| `static-data.generated.json` | 2,863 KB (2.9 MB) | `{generated_at, snapshot_generated_at, legislaturas, vereadores[95], votacoes[1934], presenca_meses[57], stats, sources[7]}`. Each vereador: identity, `presenca.{por_ano, por_mes}`, `votos.{por_legislatura, por_ano, total}` (sim/nao/abstencao/ausente/presidindo), `participacao` (voted ÷ (voted + ausente)), `com_maioria` (sim/não votes equal to `lado_vencedor` ÷ sim/não votes), `contra_partido` (count of sim/não votes against the party majority, party = `partidos_por_legislatura[leg]`, majority defined when ≥ 2 members voted and no tie), `contra_partido_taxa`, `contra_partido_base`, `proposicoes_por_tipo[tipo][ano]`, `totais`. Each votação: id, data, hora, legislatura, sessao, proposicao (ementa cut at 240 chars, autores, autores_ids), objeto, resultado, contagem, lado_vencedor (null on tie), por_partido (zero sides omitted), presidente, ausentes, fonte — no per-vereador votes |
| `static-votacoes/<unid>-<k>.generated.json` | 1,934 files, 4,525 KB total (≈ 2.3 KB each) | full votação incl. `votos: {vereador_id: voto}`, full ementa, `resultado_frase`, `roster_mes`, `fonte` |
| `static-vereadores/cvd-<n>.generated.json` | 95 files, 9,715 KB total (≤ 424 KB each) | `{id, votos: [{votacao_id, voto}], proposicoes: [{id, tipo, numero, ano, ementa, data, coautores, autores_raw, outros}]}`, newest first |
| `public/fotos/<cvd>.jpg` | 51 files, 75 KB | downscaled to 160 px wide (Pillow) |

The 2.9 MB core is over the ~400 KB target because `static-api.ts` reads `por_partido`
(≈ 570 B per votação, 1.1 MB in all), `fonte` (142 B each) and `presenca.por_mes` from the
core file. Moving those three to the per-votação / per-vereador files would bring the core to
≈ 1.1 MB; restricting the core list to the 12ª legislature as well would bring it to ≈ 300 KB.
Both need the TypeScript side to change, so they were not done here.

## Daily run

```
cd /home/arete/Work/como-votou/backend \
  && .venv/bin/python -m app.etl.export_snapshot --all \
  && .venv/bin/python -m app.etl.export_static_frontend
```

`--all` = `--from-year 2021 --presenca-from 2021 --max-docs 0` with index refresh on. It is
idempotent: every response is cached in `data/raw/`; a run re-fetches only the roster pages,
the current and previous attendance months, the `scpro.nsf` views (the 11ª database is
frozen), the two newest months of the session index, the current-year full-text search, and
session documents never read before (≈ 54 requests + new documents, at 1 req/s). Add
`--presenca-refresh-from 2026-01` once a month or so, because abonos change past months.
`--offline` rebuilds the snapshot from the cache without any request (useful after parser
changes); `--no-refresh` keeps the network for new documents only.

---

# São Paulo — data sources of the Câmara Municipal de São Paulo (CMSP)

Research and first full run: 2026-10-14. Same politeness rules as Rio (User-Agent
`tomoyo-g0v-research (contact: g0v@tomoyo.systems)`, 1 request/s, every response cached under
`data/raw/<host>/` with a sidecar). Snapshot `data/sp/snapshot.json`
(`cd backend && .venv/bin/python -m app.etl.export_snapshot --uf SP --all`), frontend files
`frontend/data/sp/` (`.venv/bin/python -m app.etl.export_static_frontend --uf SP`). Code:
`backend/app/parsers/cmsp.py`, `backend/app/etl/snapshot_sp.py`.

## Summary

Unlike Rio, the CMSP publishes structured data, and every source carries the same SPLegis
parliamentary id (`IDParlamentar` / `chave` / `_cmsp_vereador_consulta_splegis_id`). The ETL joins
by that id; there is no name matching. The index page is
`https://www.saopaulo.sp.leg.br/transparencia/dados-abertos/dados-disponibilizados-em-formato-aberto/`.

| Entity | Source | Format | Coverage |
|---|---|---|---|
| Nominal votes | `https://splegispdarmazenamento.blob.core.windows.net/containersip/VOTACOES_<ano>.xml` (the "Baixar arquivo em padrão de dados abertos (XML)" link of the page `.../atividade-legislativa/sessao-plenaria/votacao-em-plenario/`, which iframes `.../containersip/Votacoes.html`) | XML, one file per year (0.2–0.9 MB) | Aug 2012 → today |
| Session list | `.../containersip/Presencas.html` (and `Votacoes.html`): jsTree with `data_app_id="SESSAO dd_mm_aaaa Nª Sessão Tipo"` | HTML | 2,310 sessions, Aug 2012 → today |
| Presence per session | `.../containersip/PRESENCAS_<dd_mm_aaaa>_<Tipo>_<n>.xml` (e.g. `PRESENCAS_04_02_2025_Ordinária_1.xml`, URL-encoded) | XML, one per session | every session in the tree |
| Vereadores | SPLegis web service `https://splegisws.saopaulo.sp.leg.br/ws/ws2.asmx/VereadoresCMSPJSON` | JSON, 1.7 MB | 364 people since 1948: `mandatos` (start/end, party), `filiacoes` (party changes with dates), `cargos` |
| Gabinetes | `.../ws2.asmx/OcupacaoGabineteJSON` | JSON | gabinete number per legislature |
| Proposições | `.../ws2.asmx/ProjetosPorAnoJSON?Ano=<ano>` (ementa, date; every document type, ~51,000 rows and 10 MB for 2025) and `.../ws2.asmx/ProjetosAutoresJSON?ano=<ano>&tipo=<sigla>&numero=` (empty `numero` returns all of that type and year, with author ids) | JSON | SPLegis, 1992 → today (older ones as `.txt` files on the open-data page) |
| Names, photos, pages | Portal WordPress REST `https://www.saopaulo.sp.leg.br/wp-json/wp/v2/vereador?per_page=100&page=N` (`meta_all._cmsp_vereador_consulta_splegis_id`, `_cmsp_vereador_name`, `_cmsp_vereador_image`, `link`) and `/vereadores/membros/` (55 cards of the vereadores in office) | JSON / HTML | 191 posts, 144 with an SPLegis id, current and former vereadores |

The web service lists 25 methods (`ws2.asmx`, each with a `JSON` twin): projects, authors,
committees, audiences, agendas, vetoed and approved laws by promoter, office occupancy. It has no
vote or presence method; those live only in the blob storage above. `ProjetosAutoresJSON` with an
empty `tipo` fails with a .NET stack trace (`Sequence contains no elements`); `tipo` is required.
`VOTACOES_<dd_mm_aaaa>_<Tipo>_<n>.xml` (per session) does not exist (404), only the `.html` of the
same name, which the site links as the source of each vote.

## Nominal votes

`<Sessao Nome="9ª Sessão Ordinária" Data="20/02/2025"><Votacao VotacaoID TipoVotacao="Nominal|Simbólica"
Materia Ementa Resultado Presentes Sim Nao Abstencao Branco NotasRodape><Vereador Nome Partido
IDParlamentar Voto="Sim|Não|Abstenção"/>…`. Symbolic votes carry no `Vereador` rows (some carry
`<VotoContrario Partido_Vereador="NOME - PARTIDO"/>` for declared dissent); they are left out, as
in Rio. Only vereadores who voted are listed; `Presentes` is the painel count at the time of the vote.

Per vote the ETL derives:

- `objeto` from the subject line (`Materia`): `projeto`, `substitutivo` (a PL voted with a
  committee substitute, from `NotasRodape`), `emenda` (amendments and blocks of amendments),
  `veto` ("Rejeição aos vetos" / "Manutenção aos vetos"; `resultado` becomes `derrubado`/`mantido`),
  `redacao_final`, `contas` (TCM opinions on the accounts of the Executive and of the TCM,
  `DOCREC`), `parecer`, `eleicao` (Mesa, corregedor), `requerimento` (adjournment, suspension or
  extension of the session, agenda changes, CPI creation, reading of papers). 125 of the 408 nominal
  votes are procedural requerimentos; Rio's parser keeps such votes only when they name a proposição.
- `resultado`: Aprovado → `aprovado`; Reprovado/Rejeitado → `rejeitado`; "Sem quórum"/"Sem Quorum
  Suficiente" → `sem_quorum`; "Pendente de Votação" → `pendente` (the nominal vote did not reach the
  quorum and the matter stays on the agenda); "Eleito X" → `eleito`.
- `fase` (1ª/2ª discussão) from `NotasRodape` ("volta em 2º", "FASE DA DISCUSSÃO: 2ª", "Vai à sanção").
- `proposicao` from the first `PL|PLO|PDL|PR|RDP|RPP|DOCREC N/AAAA` in the subject line; authors from
  `ProjetosAutoresJSON` (one cached call for bills presented before 2021).
- `partidos`: each voter's party as printed on the vote; `por_partido` uses it (Rio uses the party
  of the legislature).
- `votos`: sim/nao/abstencao from the XML; then `ausente` for every vereador in office at that
  session who did not vote. **In office = has a row in that session's presence list with any mark
  other than `*`**. Rio infers the roster from the monthly attendance table; SP uses the session
  itself. The per-vote file also keeps `sem_voto_presentes` (ids marked present at the session who
  did not vote; this includes the presiding officer, whom the painel does not name, so no SP vote has
  `presidindo`).

## Presence

`<Presencas TipoDaSessao NumeroDaSessao NomeDaSessao Data/><Vereador Nome IDParlamentar Partido Presenca/>`.
Marks seen 2021-02 → 2026-10: `Presente` 44,160; `Licença<sup>n</sup>` 541 (n = article 112 reason:
1 illness, 3 municipal mission, 4 private interest…); blank 1,289 (unexcused absence); `*` = suplente
not in office that day or vereador who resigned (excluded). The legend also defines "Justificação"
codes 6–9, but no session in the period carries one. The yearly and monthly XMLs
(`PRESENCAS_2025.xml`, `PRESENCAS_03_2025.xml`) list only ordinary sessions, by day; the ETL uses the
per-session files, which cover ordinary and extraordinary sessions.

Contract mapping (monthly rows, same shape as Rio): `faltas` = blank marks, `faltas_abonadas` =
licenças + justificações, `total_faltas` = both, plus `sessoes`, `presencas`, `licencas`,
`justificadas`. Sessions of the last 45 days are re-read every run; `--presenca-refresh-from AAAA-MM-DD`
re-reads older ones.

## Run results (2026-10-14, `export_snapshot --uf SP --all`)

Cold cache: 1,023 requests, about 25 minutes (836 session files at roughly 0.5 s of server time plus
the 1 s delay). Daily re-run: the session tree, the current year's votes XML, sessions of the last
45 days (about 20), the vereador sources and the current year's proposições (9 requests, ~11 MB):
about 40 requests, under a minute plus new sessions.

| Entity | Rows | Notes |
|---|---|---|
| vereadores | 100 | everyone with a presence mark other than `*`, or a vote, from 2021: 79 in the 18ª legislature (2021–2024), 63 in the 19ª (2025–2028), 42 in both. 55 in office (present in the session list of 2026-10-13; matches the 55 cards on `/vereadores/membros/`). 98 with photo from the portal, former vereadores included; 2 without (Armandinho Ferreiro, Felipe Franco) get initials |
| votações nominais | 408 | 2021: 112 · 2022: 68 · 2023: 36 · 2024: 83 · 2025: 98 · 2026: 11 (one 2021 vote marked "Votação ANULADA" is dropped). Symbolic votes left out: 2,884 (2021 663, 2022 459, 2023 526, 2024 381, 2025 515, 2026 340). objeto: 125 requerimento, 122 projeto, 54 emenda, 50 substitutivo, 29 eleicao, 24 contas, 2 veto, 1 redacao_final, 1 parecer. resultado: 298 aprovado, 81 rejeitado, 19 pendente, 7 sem_quorum, 1 derrubado, 1 mantido, 1 eleito; 0 undetected |
| — individual entries | 22,443 | 13,306 sim, 4,747 não, 260 abstenção, 4,130 ausente (3,347 of them marked present at the session; 783 absent from it or on licence) |
| — consistency | 42 | votes where the printed `Sim`/`Nao`/`Abstencao` differ from the listed names (41 by one vote, 1 by two; 24 of them in 2021). `contagem` counts the names. All 408 votes found their session's presence list |
| presence | 836 sessions | 2021-02 → 2026-10, 0 files missing; 3,347 vereador-month rows; 1,289 unexcused absences, 541 licences |
| proposições | 9,828 | from 2021, types PL 5,621 · IND 2,611 · PDL 691 · MOC 317 · PR 305 · RDP 175 · RPP 72 · PLO 36; per year 2021 1,940 · 2022 1,060 · 2023 1,200 · 2024 1,399 · 2025 2,748 · 2026 1,481. 221 without a vereador author (Executive "RICARDO NUNES" 127, Mesa 32, committees, TCM) |

Left out on purpose: RDS/RPS requerimentos (about 2,000 a year in 2025; 647 agenda inclusions,
520 coauthorship requests, votes of praise, licence requests) and the internal document types
(DSP, ARQ, CV, REGTAQ, LISTPRE…), which make up most of the 51,342 rows of `ProjetosPorAno` 2025.

Frontend files: `static-data.generated.json` 724 KB; `static-votacoes/` 408 files, 974 KB;
`static-vereadores/` 100 files, 9.5 MB; `fotos/` 98 files, 466 KB.

## Caveats (SP)

1. "Ausente" in SP means "in office at the session, no vote on the painel". 81% of those
   entries are vereadores who signed in at the session and did not vote: they may have left the
   floor, abstained by not voting, or presided. The painel does not record obstruction.
2. Party per legislature (`partidos_por_legislatura`) is the party printed on the latest vote or
   presence row of that legislature, falling back to the SPLegis affiliation in force at the end
   of it. Party switches inside a legislature (the 2024 window) show on the votes, not on the list.
3. `objeto`/`fase` come from free text the painel operator types (`Materia`, `NotasRodape`);
   subject lines are cut at about 50 characters and end in "..." (the site drops the dots).
4. The yearly votes XML is rewritten during the year; votes of the current year are re-read daily.
5. Proposições are counted by presentation year (from 2021) and joined to authors by id.

## Daily run (SP)

```
cd /home/arete/Work/como-votou/backend \
  && .venv/bin/python -m app.etl.export_snapshot --uf SP --all \
  && .venv/bin/python -m app.etl.export_static_frontend --uf SP
```

`--offline` rebuilds from `data/raw` only; `--no-refresh` reads only what is not cached. The server
script `deploy/build-site.sh` runs this for every city of `frontend/data/cities.json`.

---

# Other capitals — what each Câmara publishes (checked 2026-10-14)

Survey to choose the next cities. Checked live with curl, a few requests per site. "API" = machine
interface with per-record data (mostly Interlegis SAPL 3: `/api/sessao/votoparlamentar/`,
`/api/sessao/sessaopresenca/`, `/api/materia/autoria/`); "dados abertos" = downloadable files;
"HTML"/"PDF" = pages or documents only. Brasília is the Câmara Legislativa do DF, not a câmara municipal.

| Capital (UF) | Main system | Nominal votes | Presence | Bills/authors | Note |
|---|---|---|---|---|---|
| Rio Branco (AC) | SAPL 3, sapl.riobranco.ac.leg.br | API | API | API | votoparlamentar 41,028 rows, 06/2019 → 08/10/2026 |
| Maceió (AL) | maceio.al.leg.br | none | PDF | HTML | monthly attendance PDFs stop at 12/2024; sessions suspended 09/2026 |
| Macapá (AP) | macapa.ap.leg.br (n2gov) | none | none | API (undocumented) | api_macapa.n2gov.com.br/proposicoes, /parlamentares |
| Manaus (AM) | SAPL 3, sapl.cmm.am.gov.br | totals only (API) | API | API | votoparlamentar empty; registrovotacao 8,042 with totals |
| Salvador (BA) | cms.ba.gov.br, ScriptCase grids | PDF (not verified) | dados abertos | dados abertos | LEG_SYS_frequencia 23,472 rows per vereador and session, 05/2018 → 09/2026, CSV/XML |
| Fortaleza (CE) | SAPL 3, sapl.fortaleza.ce.leg.br | not verified | API (to 2020) | API | votoparlamentar empty; virtual painel publishes nothing |
| Brasília (DF), CLDF | cl.df.gov.br, dados.cl.df.gov.br, PLE API | PDF (not verified) | PDF | API + dados abertos | ple.cl.df.gov.br/pleservico/api/public documented |
| Vitória (ES) | Câmara sem Papel | PDF | PDF | HTML | "Boletim de Votação/Presença" PDF per session, current |
| Goiânia (GO) | goiania.go.leg.br + SUAP | PDF (no names) | PDF (scanned) | HTML | atas give only the outcome |
| São Luís (MA) | cmsaoluis.ma.gov.br | PDF | PDF + HTML totals | HTML | per-session PDF report lists each vote (376 reports) |
| Cuiabá (MT) | Câmara sem Papel | PDF | PDF | HTML | "Ficha de Votação/Presença" per session |
| Campo Grande (MS) | camara.ms.gov.br | not verified | not verified | not verified | whole site behind reCAPTCHA |
| Belo Horizonte (MG) | cmbh.mg.gov.br (SIL) | totals only (DOCX/PDF) | dados abertos (XLSX) | HTML | XLSX per meeting: 41 vereadores × events (P/F/AJ), presence at each vote, not the vote |
| Belém (PA) | cmb.pa.gov.br | none | none | dados abertos (JSON) | projetos-de-lei/exportar?formato=json with proponente |
| João Pessoa (PB) | SAPL 3, sapl.joaopessoa.pb.leg.br | API | API | API | votoparlamentar 13,299 rows to 13/10/2026; committee votes mixed in |
| Curitiba (PR) | cmc.pr.gov.br (SPL II) | not verified | not verified | HTML behind captcha | presence on a Betha portal with reCAPTCHA |
| Recife (PE) | publico.recife.pe.leg.br (SAPL 2.5 JSON views) | API (sparse) | API | API | /@@sessoes/id/{ID}/votacao; 2 of 14 recent sessions carry votes |
| Teresina (PI) | Câmara sem Papel | none | none recent | HTML + CSV | author production exports CSV by postback |
| Natal (RN) | SAPL 3, sapl.natal.rn.leg.br | API (stops 07/2024) | API | API | votoparlamentar 617 rows 2019 → 04/07/2024 |
| Porto Alegre (RS) | votacoes.camarapoa.rs.gov.br | dados abertos (CSV) | HTML (quorum calls) | HTML | 8,828 nominal votes 2010 → 07/10/2026; /votacoes/por_votacao.csv?votacao_id=N, /votacoes/por_periodo?mes=M&ano=A&format=csv |
| Porto Velho (RO) | SAPL 3, sapl.portovelho.ro.leg.br | API | API | API | votoparlamentar 78,584 rows, 10/2019 → 13/10/2026 |
| Boa Vista (RR) | SAPL 3, sapl.boavista.rr.leg.br | none | API (partial, to 08/2026) | API | votoparlamentar empty |
| Florianópolis (SC) | cmf.sc.gov.br | not verified | not verified | not verified | site behind anti-robot check |
| Aracaju (SE) | aracaju.se.leg.br + SAPL 2.5 | dados abertos (XLSX) | XLSX (yearly totals) | HTML | one XLSX per nominal vote (Parlamentar/Partido/Voto), to 06/2026 |
| Palmas (TO) | SAPL 3, sapl.palmas.to.leg.br | none | API (to 03/2024) | API (to 2024) | SAPL apparently abandoned since 03/2024 |

Order suggested by cost: (1) Rio Branco, Porto Velho, João Pessoa: one SAPL 3 adapter serves the
three, with per-vereador votes, presence and authorship current to this week. (2) Porto Alegre:
the longest nominal series, as CSV; presence has to come from quorum calls. (3) Recife, Natal,
Aracaju: partial or lagging votes. (4) Salvador, Belém, CLDF, Manaus: presence and bills but no
per-vereador votes. (5) São Luís, Vitória, Cuiabá need PDF parsing; Campo Grande, Florianópolis
and Curitiba sit behind captchas.

# Estado do Rio de Janeiro — os 92 municípios (2026-10-16)

## Nível 0: TSE

Todos os 92 entram pelos dados abertos do TSE: `consulta_cand_<ano>.zip` e
`votacao_candidato_munzona_<ano>.zip` (arquivos nacionais com um CSV por UF; 255 MB os quatro, 2020
e 2024), filtrados para cargo 13 (vereador) e eleição ordinária (a suplementar de Itaguaí em
10/2026 fica de fora). Votos = soma de `QT_VOTOS_NOMINAIS_VALIDOS` por zona; situação = 
`DS_SIT_TOT_TURNO` da votação (eleito por QP, por média, suplente). Ficam os eleitos e os cinco
suplentes mais votados de cada partido ou federação: 1.208 eleitos em 2024 e 6.845 pessoas nos 92.
A pessoa é a mesma nas duas eleições quando o título eleitoral é o mesmo (o id publicado é um hash).
O TSE regera os arquivos de 2024 quase todo dia; o ETL só os baixa de novo quando o Last-Modified
muda e a cópia tem mais de 7 dias. `NM_CANDIDATO` vem sem acento em parte dos registros.

Fotos: `foto_cand<ano>_RJ_div.zip` (515 MB em 2024, 747 MB em 2020) é lido por faixa de bytes
(HTTP Range, 96 KB por pedido, 4 por segundo ao CDN): ~4.700 pedidos para 6.600 fotos, ~35 min na
primeira vez, depois nada. `divulgacandcontas.tse.jus.br` responde 403 a clientes fora do navegador.
O site publica a foto de quem foi eleito ao menos uma vez.

## Levantamento das câmaras (`backend/data/rj-camaras.csv`)

`python -m app.etl.survey_camaras`: hosts no padrão do Interlegis (`sapl.<x>.rj.leg.br`,
`<x>.rj.leg.br`, `cm<x>.rj.gov.br`…), 14 endereços achados à mão, assinatura do sistema no HTML e,
nos SAPL 3, contagem das tabelas da API. 765 requisições, 180 s. O resolvedor DNS local nega nomes
`*.rj.leg.br` que existem; o script tenta DNS sobre HTTPS quando a busca falha.

| Sistema | Câmaras |
|---|---|
| SAPL 3 (com dados) | 34 |
| WordPress | 18 |
| Portal Modelo (Interlegis) | 12 |
| outro | 6 |
| fora do ar | 5 |
| MTW PortalGov | 4 |
| NPI Brasil | 3 |
| Joomla | 2 |
| Câmara sem Papel | 2 |
| Drupal, Wix, Siscam, PLE (Porto Real), aplicativo web, Domino (Rio) | 1 cada |

Nenhum SAPL 2.5. Cinco câmaras têm um SAPL 3 vazio (Areal, Itaocara, Paraíba do Sul, Santo Antônio
de Pádua, Campos dos Goytacazes) e foram classificadas pelo site principal. O que cada uma publica,
pelo levantamento: votos nominais 25 (24 SAPL 3 e o Rio), presença 5, proposições 36, só PDF 13,
nada 3, não verificado 10. Fora do SAPL a classificação é um palpite pelas palavras da página inicial.

## Nível por município, depois do leitor SAPL

`python -m app.etl.sapl --all` lê os 34 SAPL 3; `python -m app.etl.municipios` exporta.

| Nível | Municípios |
|---|---|
| 3, votos nominais | 22 (+ a capital) |
| 2, presença | 6 |
| 1, proposições | 3 |
| 0, só vereadores (TSE) | 61 |

Votações nominais lidas desde 2021, por município: Macaé 2.984, Petrópolis 2.556 (a última em
14/11/2024: a Câmara parou de registrar votos no SAPL), Rio das Ostras 2.328, Mangaratiba 2.292,
Barra do Piraí 2.220, Nova Friburgo 825, Piraí 819, Quissamã 779 (até 12/2024), Barra Mansa 500,
Quatis 402, Engenheiro Paulo de Frontin 341, Cachoeiras de Macacu 189, Valença 177 (até 04/2023), Duas Barras 164; Paty do
Alferes, Itaguaí, Cantagalo, Miguel Pereira, Mendes, Conceição de Macabu e Belford Roxo têm menos de
25: o painel quase não é usado e o resto é votação simbólica.

O leitor SAPL:

- lê `parlamentares/{legislatura,parlamentar,mandato,filiacao,partido}`,
  `sessao/{sessaoplenaria,sessaoplenariapresenca,registrovotacao,votoparlamentar,tiporesultadovotacao}`,
  `materia/materialegislativa` (por ano, `?ano=`, desde 2021; o campo `autores` dispensa
  `materia/autoria`), `materia/tipomaterialegislativa`, `base/{autor,tipoautor}`;
- ordena por `?o=-id` (`ordering=` e `ano__gte=` são ignorados em silêncio) e, nas rodadas
  seguintes, para na primeira página sem nada novo; se o total guardado fica abaixo do
  `total_entries` anunciado, relê a tabela inteira (um 404 transitório no meio da paginação cortou
  a presença de Petrópolis na primeira tentativa);
- liga parlamentar a candidato do TSE por nome completo, depois nome parlamentar, depois nome
  parecido (razão ≥ 0,93, ou ≥ 0,85 com o mesmo partido); quem não casa entra como `sapl:<id>`;
- conta como votação nominal o registro com voto individual; ficam de fora as unânimes sobre
  indicação, requerimento, moção e ofício (dezenas de milhares, sem informação);
- falta = sessão com lista de presença publicada, mandato vigente no dia, parlamentar fora da lista.
  O SAPL não diz se a falta foi justificada.

Primeira leitura dos 34: 34 min 53 s com 12 câmaras em paralelo, cada uma a 1 req/s; as maiores
foram Rio das Ostras (1.771 requisições), Petrópolis (1.504), Macaé (1.450) e Nova Friburgo (1.089).
Duas câmaras (Bom Jardim, Cachoeiras de Macacu) falharam por DNS e entraram na segunda rodada.
Rodada incremental seguinte: 4 min 37 s, de 19 a 277 requisições por câmara (as matérias do ano
corrente e do anterior são relidas inteiras).
Dados do frontend dos 91 municípios: 94 MB em `frontend/data/rjm/` (votos por votação e fichas
por vereador são a maior parte).

Próximos sistemas, pelo custo: (1) WordPress e Portal Modelo (30 câmaras) publicam proposições e
atas como páginas e PDF, sem padrão comum; (2) MTW PortalGov e Siscam publicam pautas e atas em PDF
num formato repetido entre câmaras, o que permitiria um leitor por fornecedor; (3) as cinco fora do
ar e as dez não verificadas pedem uma segunda passada à mão.
