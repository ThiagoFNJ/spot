# Vereadores

Câmaras Municipais do Rio de Janeiro, de São Paulo e dos outros 91 municípios do Estado do Rio:
votações nominais, presença em plenário e proposições de cada vereador, da Tomoyo, dentro do
g0v.tomoyo.systems. Um só build serve todas as cidades; o site busca os dados de cada uma em
`data/<pasta>/` (Rio em `rj`, São Paulo em `sp`, os municípios em `rjm/<slug>`).

Rio:

A Câmara não publica API nem arquivos abertos da atividade legislativa. O ETL lê as páginas do
site camara.rio e as bases Lotus Domino de aplicnt.camara.rj.gov.br: lista de vereadores,
frequência mensal, proposições do SPL e as atas de sessão, de onde as votações nominais são
extraídas por expressões regulares e conferidas contra a contagem impressa. Detalhes, contagens
reais e ressalvas em `FINDINGS.md`.

São Paulo: a Câmara publica dados abertos. O ETL lê o XML anual do painel de votações, a lista de
presença de cada sessão plenária em XML, o web service SPLegis (vereadores, filiações,
proposições e autores) e as páginas dos vereadores no portal (nome e foto). Todas as fontes trazem
o código SPLegis do vereador, e a junção é por esse código.

Municípios do Estado do Rio (desde 2026-10-16): todos entram pelos dados abertos do TSE (eleitos e
suplentes de 2020 e 2024, com partido, votos e foto). Onde a câmara usa o SAPL 3 do Interlegis, um
leitor genérico da API do SAPL acrescenta votos nominais, presença e proposições. Cada município tem
um nível de dado: 0, só vereadores; 1, proposições; 2, presença; 3, votos nominais. O levantamento
das 92 câmaras (site, sistema, o que publicam) está em `backend/data/rj-camaras.csv` e no FINDINGS.

Sites: https://g0v.tomoyo.systems/vereadores/ (Rio), https://g0v.tomoyo.systems/vereadores/sp/
(São Paulo) e https://g0v.tomoyo.systems/vereadores/rj/<município>/ (por exemplo `rj/niteroi/`).

## Layout

```text
backend/app/
  http.py                     downloads com cache, 1 req/s, checksums, cadeia TLS da Câmara do Rio
  config.py                   caminhos por UF (data/snapshot.json no Rio, data/sp/snapshot.json em SP), URLs das fontes
  parsers/vereadores.py       lista atual e legislaturas anteriores
  parsers/presenca.py         frequência mensal (POST em camara.rio)
  parsers/spl.py              visões do Sistema de Proposições Legislativas (Domino JSON)
  parsers/discvot.py          votações nominais a partir do texto das atas
  parsers/cmsp.py             São Paulo: XML de votações e de presença, árvore de sessões, SPLegis, portal
  etl/export_snapshot.py      snapshot de uma UF (--uf RJ|SP), incremental
  etl/snapshot_sp.py          o ETL de São Paulo (chamado por export_snapshot --uf SP)
  etl/export_static_frontend.py  frontend/data/<uf>: núcleo, votos por votação, votos e proposições por vereador, fotos
  etl/tse_rj.py               municípios do RJ: candidatos e votos do TSE, 2020 e 2024; fotos lidas do zip remoto por faixa de bytes
  etl/survey_camaras.py       levantamento das 92 câmaras: site, sistema, contagens do SAPL -> backend/data/rj-camaras.csv
  etl/sapl.py                 leitor genérico do SAPL 3 (1 req/s por câmara, incremental) e conversão para snapshot
  etl/municipios.py           frontend/data/rjm/<slug>/ e o índice frontend/data/rj-municipios.json
frontend/
  data/<uf>/static-data.generated.json         vereadores com agregados, votações com contagens, cobertura
  data/<uf>/static-votacoes/<id>.generated.json   quem votou o quê numa votação
  data/<uf>/static-vereadores/<id>.generated.json os votos e as proposições de um vereador
  data/<uf>/fotos/                               fotos (160 px)
  data/rjm/<slug>/                               o mesmo para cada município do Estado do Rio
  data/rj-municipios.json                        índice dos 92: nível de dado, sistema, site da câmara
  scripts/stage-data.mjs      copia data/ para public/data/, de onde o site busca (roda sozinho antes de build e dev)
  lib/uf.ts                   as cidades, a cidade de cada caminho, o que muda entre elas
  components/DataGate.tsx     busca o núcleo da cidade da página antes de mostrar a tela
  lib/method.ts               o texto da página Método de cada cidade
  app/, components/           Next.js App Router, Tailwind com tokens da tomoyo.systems
deploy/build-site.sh          roda no servidor, por cron, uma vez por dia; ETL e build das duas cidades
```

Telas: Vereadores (`/`), Votações (`/votacoes`), Presença (`/presenca`), Partidos (`/partidos`),
Método (`/metodologia`), as mesmas em todas as cidades, sob `/sp/` e `/rj/<slug>/`. Num município de
nível 0, Vereadores mostra a lista do TSE, Partidos as cadeiras por partido, e Votações e Presença
dizem o que a câmara não publica. Teclas `1`–`5` trocam de tela, `u` passa à próxima cidade; o campo
de cidade no cabeçalho busca pelo nome; setas, `v`, `e`, `r` por tela.

## Setup

```bash
cd backend && uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev]"
# Rio
.venv/bin/python -m app.etl.export_snapshot --all                 # ~1 h na primeira vez (1 req/s), depois incremental
.venv/bin/python -m app.etl.export_static_frontend                # frontend/data/rj
# São Paulo
.venv/bin/python -m app.etl.export_snapshot --uf SP --all         # ~20 min na primeira vez, depois ~1 min
.venv/bin/python -m app.etl.export_static_frontend --uf SP        # frontend/data/sp
# Municípios do Estado do Rio
.venv/bin/python -m app.etl.tse_rj                                # ~255 MB de zips do TSE (uma vez) e ~6.600 fotos (~35 min na primeira vez)
.venv/bin/python -m app.etl.survey_camaras                        # levantamento das câmaras -> backend/data/rj-camaras.csv
.venv/bin/python -m app.etl.sapl --all --workers 8                # câmaras com SAPL 3; ver FINDINGS para o tempo
.venv/bin/python -m app.etl.municipios                            # frontend/data/rjm e rj-municipios.json
cd ../frontend && npm ci && npm run dev                           # todas as cidades em http://localhost:3000/vereadores/
```

Gates: `cd backend && .venv/bin/python -m pytest -q -W error`;
`cd frontend && npm run typecheck && npm run test:visual` (Playwright constrói com base vazia e
testa Rio, São Paulo, Niterói, Macuco e Petrópolis).

Build de produção: `npm run build` (base `/vereadores`; `NEXT_PUBLIC_BASE_PATH=` serve na raiz).

## Deploy

O site vive em `g0v.tomoyo.systems/vereadores`, no nginx estático do g0v (ver o repositório
[g0v](https://github.com/Tomoyo-Computer-Science-Research-Unit/g0v)). O cron roda
`/root/g0v/build-vereadores.sh` (cópia de `deploy/build-site.sh`, que se atualiza sozinha) todo dia:
puxa `main`, relê o que muda nas duas capitais, no TSE e nos SAPL dos municípios, regenera os dados
e, se algo mudou, faz um build só e o publica em `/root/g0v/site/vereadores/`. Cada parte que roda
bem guarda a sua saída em `/root/g0v/data-ok-vereadores/`; se uma parte falha, ela segue com esse último
snapshot bom (ou, sem ele, com o de `main`). `SKIP_DATA=1` não lê fonte nenhuma e constrói com os
últimos snapshots bons. Falhas avisam por e-mail.
