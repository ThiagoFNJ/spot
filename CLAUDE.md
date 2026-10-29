# spot — convenções

Dashboard de presença, produtividade e custo dos vereadores da Câmara Municipal de Salvador (CMS).
Contexto completo: `docs/spike/spike-dashboard-vereadores-cms.md` (fontes verificadas), `docs/HANDOVER.md` + `docs/HANDOVER-adendo-2026-10-27.md` (fluxo HTTP validado e correções). Fontes ainda não integradas: `docs/fontes-candidatas.md`.

## Escopo do MVP
Legislatura 2025–2028 (dados de 2025-01 em diante). Histórico 2018+ fica para fase 2.

## Layout
- `src/spot/scriptcase.py` — cliente HTTP compartilhado para os apps ScriptCase (`45.4.247.157/leg/salvador/<app>/` e `cmsalvador.sys.inf.br`). Use-o; não reimplemente `script_case_init`, `ajax_navigate`, export ou dump.
- `src/spot/collect/<fonte>.py` — um coletor por fonte. Escreve só em `data/bronze/<fonte>/`. Arquivos brutos imutáveis, um por combinação de filtro, nome determinístico; se já existe, não refaz (idempotente). Grava `manifest.jsonl` com url, parâmetros, sha256, bytes, coletado_em.
- `src/spot/parse/<fonte>.py` — bronze → tabelas limpas (CSV UTF-8 em `data/silver/`). Sem rede.
- `src/spot/build.py` — monta `data/silver/spot.duckdb` a partir dos CSVs silver + `data/seeds/`.
- `data/seeds/` — tabelas curadas à mão (`vereador_dim.csv`, `vereador_alias.csv`). Únicos dados versionados no git; nunca colocar CPF, agência ou conta nelas.
- Dados fora do git: bronze (bucket privado no GCP), silver e gold (buckets + BigQuery; `data/` é cache local). Toda fonte nova ganha uma linha em `docs/FONTES-BRONZE.md` (onde, quando, como). Normas citadas no painel ficam em `data/bronze/legislacao/` com manifesto. Licenças: código AGPL-3.0, dados CC BY-SA 4.0.
- CLI: `uv run python -m spot.collect.<fonte>`, `uv run python -m spot.parse.<fonte>`, `uv run python -m spot.build`.
- `collect/etcm.py` (PDFs do e-TCM, Playwright/Chromium headless, ~5 min por mês) fica fora de `make collect`/`refresh`: rode `make etcm` à parte (ver `docs/etcm.md`).
- `parse/tcm_pessoal.py` lê as planilhas da consulta de pessoal do TCM-BA exportadas **à mão** (reCAPTCHA; nunca automatizar — ver `data/bronze/tcm_pessoal/README.md`): `uv run python -m spot.parse.tcm_pessoal --ingest ~/Downloads/*.xlsx`. `metrics/custo.py` reconstrói com elas a folha de 2026 por gabinete (lotação = última matrícula vista na folha do site; `folha.fonte`, `metrica_lotacao_cobertura`).
- `parse/etcm_folha.py` lê as folhas sintéticas (classes PCMGE035/048 do e-TCM, 2ª linha de `make etcm`): única folha da Câmara em 2026, agregada por regime; `metrics/custo.py` cai nela quando a folha analítica do site não existe (`metrica_custo_camara_mensal.fonte`).
- `parse/etcm_vc.py` lida com três formatos de processo (`layout` = `resumo` / `detalhamento` / `nenhum`, ver `docs/etcm.md`); o formulário antigo item a item está em `parse/etcm_vc_detalhamento.py` e gera `verba_processo_nf.csv`. Nunca gravar agência/conta/CPF: tudo passa por `mascarar_sensiveis`.
- `src/spot/metrics/<metrica>.py` — lê `spot.duckdb`, cria suas tabelas derivadas (`metrica_*`) e escreve um relatório em `docs/relatorios/`. Não edita `build.py`.
- Testes: `uv run pytest`. Fixtures em `tests/fixtures/` (ex.: `frequencia_2025-03_tipo1.csv`, 430 linhas reais). Lint: `uv run ruff check` + `uv run ruff format` (regras em `pyproject.toml`).
- `collect/vereadores.py --fotos` baixa as fotos oficiais dos 50 vereadores para `data/bronze/vereadores/fotos/` e copia para `site/fotos/` (reduzidas a 400 px com `sips`); o Artifact publica `site/fotos/*.jpg` junto com os JSON (CSP do visualizador bloqueia imagens de outros hosts). Redes sociais vêm do seed `data/seeds/vereador_redes.csv`.
- Período no site: `ano = 0` é a legislatura inteira (linhas agregadas que o export acrescenta a cada tabela por ano; tabelas mensais são filtradas por competência). Toda tabela nova por ano deve ganhar a linha 0 no `export_site.py`.
- `src/spot/cloud.py` — sincroniza o bronze com `gs://spot-bronze-9122a143` (`make push-bronze`/`pull-bronze`, nunca apaga no bucket) e publica silver/gold em Parquet no GCS + BigQuery (`make publish`, datasets `spot_silver`/`spot_gold`, `southamerica-east1`). Silver = tabelas vindas de CSV + `presenca_mvp`; gold = o resto. A publicação aborta se `find_sensitive` achar CPF ou agência/conta: corrija o parser, não a trava.
- `src/spot/export_site.py` → `site/data/*.json`; `site/index.html` é o dashboard (HTML puro, SVG próprio, sem build). Publicado no GitHub Pages por `.github/workflows/pages.yml` (HTML do repo + JSON e fotos de `gs://spot-gold-9122a143/site/`, enviados por `make publish` e baixados por `spot.cloud pull-site`); também como Artifact em https://claude.ai/artifact/VjJTNXZauqBnibJ54Aobtp. Mantenha os dois em sincronia: toda mudança de schema no JSON exige mudar a página.
- `make` — alvos `collect`, `parse`, `build`, `metrics`, `site`, `refresh`, `test`, `lint`, `push-bronze`, `pull-bronze`, `publish` (ver `Makefile`). Mudanças entram sempre por PR; nunca commitar direto na master.

## Regras de coleta
- ≤ 1 request/s por host, User-Agent identificado (`spot-cms-monitor/0.1 (+github)`), timeout explícito, retry 3x com backoff.
- Respostas do LEG_SYS são ISO-8859-1: decodificar `latin-1`. CSVs silver sempre UTF-8.
- Nunca confiar em constantes de contagem (23.472, 5.759…): validar contra o total da grade (`[a a b de N]`) no momento da execução.
- `script_case_init` é capturado por GET e reutilizado em todos os POSTs daquela combinação; nunca misturar inits.
- Export: `SC_module_export=grid` obrigatório; GET de geração bloqueia e devolve corpo vazio em caso de sucesso; corpo não vazio = página de erro PHP; polling com timeout.
- Nomes de parlamentar: normalizar whitespace (há `Randerson  Leal` com espaço duplo); manter o nome original na coluna `nome_fonte`.
- Sessões 888 e 999 são sentinelas: manter no bronze, marcar no silver (`sentinela = true`), excluir das métricas. No catálogo (`LEG_SYS_sessao_ata`) qualquer nº ≥ 500 também é sentinela (há um "6.789" em 2024-07-05; o maior nº real por ano é 117). No `prop_interna` há um registro de teste `PLE-9999/2025`, idem.
- Fontes corrigem dados retroativamente (status de presença mudou entre 16/10 e 27/10/2026). Política de atualização: `make refresh` recoleta com `--force` o mês corrente e o anterior da frequência e tira um snapshot novo do catálogo, das proposições e do RH; meses mais antigos só com `--force` explícito.
- Dois fluxos de export coexistem: `Client.export_csv` (export_ctrl + pbmd5, apps do `45.4.247.157`) e o POST `nmgp_opcao=csv` direto do `prop_interna` em `cmsalvador.sys.inf.br` (o pbmd5 nunca completa lá). Está em `collect/proposicoes.py`; não tente unificar.
- Bronze de snapshots diários (`prop_interna_{data}.csv`, `sessoes_catalogo_{data}.html`, `resumo_{ano}_{data}.html`) é um arquivo por dia; o parser usa o mais recente.

## Estilo
Python 3.12, type hints, funções pequenas, sem classes desnecessárias. Logs com `logging`, não print. Nada de LLM no pipeline do MVP.
