# Pipeline do spot. Rode `make all` para bronze -> silver -> duckdb -> métricas.
PY := uv run python
CUR := $(shell date +%Y-%m)
PREV := $(shell date -v-1m +%Y-%m 2>/dev/null || date -d "-1 month" +%Y-%m)

.PHONY: all collect etcm parse build metrics site refresh test lint push-bronze pull-bronze publish

all: collect parse build metrics site

collect:
	$(PY) -m spot.collect.frequencia
	$(PY) -m spot.collect.sessoes
	$(PY) -m spot.collect.proposicoes
	$(PY) -m spot.collect.rh
	$(PY) -m spot.collect.vereadores
	$(PY) -m spot.collect.empenhos
	$(PY) -m spot.collect.tse

# e-TCM (processos de pagamento, PDFs via Chromium headless): lento (~5 min/mês), por isso fora de collect/refresh.
etcm:
	$(PY) -m spot.collect.etcm --todos-meses
	$(PY) -m spot.collect.etcm --todos-meses --filtro "" --classes PCMGE035,PCMGE048

parse:
	$(PY) -m spot.parse.frequencia
	$(PY) -m spot.parse.sessoes
	$(PY) -m spot.parse.proposicoes
	$(PY) -m spot.parse.rh
	$(PY) -m spot.parse.vereadores
	$(PY) -m spot.parse.empenhos
	$(PY) -m spot.parse.tse
	-$(PY) -m spot.parse.etcm_vc
	-$(PY) -m spot.parse.etcm_folha
	-$(PY) -m spot.parse.tcm_pessoal

build:
	$(PY) -m spot.build

metrics:
	$(PY) -m spot.metrics.presenca
	-$(PY) -m spot.metrics.produtividade
	-$(PY) -m spot.metrics.custo
	-$(PY) -m spot.metrics.verba

# Dashboard estático: JSON em site/data/ lido por site/index.html (publica igual como Artifact ou GitHub Pages).
site:
	$(PY) -m spot.export_site

# Atualização periódica: fontes corrigem dados retroativamente, então o mês corrente e o anterior
# da frequência são recoletados; as demais fontes tiram um snapshot novo do dia (idempotentes por data).
refresh:
	$(PY) -m spot.collect.frequencia --since $(PREV) --until $(CUR) --force
	$(PY) -m spot.collect.sessoes
	$(PY) -m spot.collect.proposicoes
	$(PY) -m spot.collect.rh
	$(PY) -m spot.collect.empenhos
	$(MAKE) parse build metrics site

test:
	uv run pytest -q

lint:
	uv run ruff check src tests && uv run ruff format --check src tests

# GCP (requer credencial: `gcloud auth application-default login`). Bronze privado; silver/gold públicos + BigQuery.
GCP := uv run --extra gcp python -m spot.cloud
push-bronze:
	$(GCP) push-bronze

pull-bronze:
	$(GCP) pull-bronze

publish:
	$(GCP) publish
