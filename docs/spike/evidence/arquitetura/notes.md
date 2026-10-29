# ARQUITETURA — notas do spike (2026-10-16)

## Fatos verificados hands-on sobre a CMS (afetam a arquitetura)
- www.cms.ba.gov.br NÃO usa SAPL (sapl.cms.ba.gov.br não resolve). Site institucional (WordPress-like) + grids ScriptCase em http://45.4.247.157/leg/salvador/ (IP, HTTP sem TLS, charset ISO-8859-1):
  - LEG_SYS_frequencia/ ("Consulta Frequência") — grid agrupado por Mês/Ano desde Maio/2018; grupos carregam via POST ajax (nm_gp_submit_ajax); export csv/xml/json/xls/pdf existe no toolbar (nm_gp_csv_conf, LEG_SYS_frequencia_export_ctrl) mas GET ?nmgp_opcao=csv devolve o grid (export exige POST com sessão). como-votou/FINDINGS.md reporta 23.472 linhas (vereador x sessão, 05/2018→09/2026) exportáveis em CSV/XML.
  - LEG_SYS_produtividade_parlamentar_proposicao/ — grid "resumo" com filtros CAD.CAD_NOME_ABREVIADO (vereador) e TRA.TRA_DT_MOVIMENTACAO (ano); POST script_case_init.
  - LEG_SYS_sessao_ata/ ("Consulta Sessão Plenária") — 20 linhas/página com ícones texto/áudio/vídeo; atas em PDF em http://177.21.11.131:8888/LEG/Upload/<GUID>.pdf.
- Ata sample (cms/samples/ata_FF25DF0D.pdf): Word→PDF, 3 págs, TEM camada de texto (pdfplumber 1763 chars na pág 1). Começa com "Compareceram os senhores vereadores: ..." + "estando licenciados ..." => presença extraível por regex/LLM sem OCR.
- RH: /transparencia/recursos-humanos lista ~dezenas de PDFs (Excel→PDF) e alguns .xlsm em /uploads/rh/. Sample (rh_sample.pdf, 16 págs): tabela por servidor com colunas matrícula, nome, nível, admissão, lotação ("GAB. VER. <nome>"), valor. pdfplumber extrai tabela, mas células colam (ex.: "SUPERIOR I" quebrado) => validação obrigatória.
- Ordem do dia: PDFs em /uploads/ordem-do-dia/.
- Diário Oficial do Município (executivo) já tem raspador no Querido Diário: gazette/spiders/ba/ba_salvador.py (Joomla dom.salvador.ba.gov.br, PDF por edição, zyte proxy).

## Projetos de referência (lidos)
- okfn-brasil/querido-diario (★1405, ativo): Scrapy 2.14 + spidermon (Discord alerts) + scrapinghub/Zyte Scrapy Cloud; GH Actions cron (daily_crawl.yaml 21:00 UTC) só agenda jobs; PDFs em S3/Minio com checksum (Gazette.file_checksum, file_path, scraped_at); metadados em Postgres (SQLAlchemy). Spiders-base por "sistema de diário" (sigpub, doem, instar...). querido-diario-data-processing: Apache Tika (texto, sem OCR nativo) → OpenSearch; sentence-transformers p/ temas. API: FastAPI.
- okfn-brasil/serenata-de-amor (★4616, pouco mantido): Rosie (pandas/scikit) + Jarbas (Django 2.1 + DRF + Celery + Postgres, Elm), rodado "manualmente ~1x/mês", DigitalOcean+Docker.
- parlametria/leggo* (inativo desde 2022): leggoR (R) gera CSVs → leggo-backend (Django) importa → leggo-frontend (Vue); Airflow p/ agendamento. Lição: pipeline CSV-first desacoplado do backend.
- interlegis/sapl (3.1.x, ativo): Django + DRF; modelos canônicos (sapl/sessao/models.py: SessaoPlenaria, SessaoPlenariaPresenca(unique sessao,parlamentar), PresencaOrdemDia, RegistroVotacao, VotoParlamentar, JustificativaAusencia, Orador*; sapl/materia: MateriaLegislativa, Autoria, Tramitacao, Relatoria, Parecer; parlamentares: Legislatura, Mandato, Filiacao, Parlamentar). API DRF em /api/<app>/<modelo>/ com paginação page_size≤100 e OpenAPI em /api/schema/ (verificado em sapl.lapa.pr.leg.br; 283 paths).
- Tomoyo-Computer-Science-Research-Unit/como-votou (ativo, 2026-10-16): Python 3.12 httpx+lxml+bs4 → snapshot JSON → Next.js estático; Downloader com cache em disco keyed sha1(method,url,body) + sha256 + accessed_at, 1 req/s; votações extraídas de atas por regex com checagem contra contagem impressa; FINDINGS.md documenta fontes/ressalvas; build-site.sh cron diário, "último snapshot bom", alerta por e-mail; leitor genérico SAPL (etl/sapl.py) incremental ?o=-id.
- pedrosolb/olho-na-camara-lapa: versão mínima — coletar_dados.py (requests, SAPL API) → data.json → montar_pagina.py embute JSON no HTML → GitHub Pages /docs; Actions cron diário commitando data.json.
- gutoportelaa/ocr-arena: benchmark OCR em docs de câmaras do PI (RTX 4070): tesseract 4.5 s/pág; minicpm-v 195 s/pág; docling/olmocr2 falharam; roteamento: texto nativo→Marker/Docling, simples→Tesseract.
- tekoryu/contato-vereadores-nacional: Playwright + Ollama qwen2.5:14b, medallion bronze/silver/gold em parquet, Git LFS; scripts/sapl_harvest.py usa export SIGI p/ listar câmaras SAPL.
- CodeForCuritiba/cmc-transparencia-spider (2017): Scrapy p/ holerites por grupo (Vereadores, Efetivos, Comissionados...) → MongoDB; exige login CPF.
- Zeukio/scraper-camara-florianopolis: requests+bs4→CSV. TapiocaAberta/presenca-vereadores-sjc (2017): ETL shell+Java → JSON → site estático GH Pages.

## Stacks (fatos)
- Observable Framework (ISC, ★3666, último push 2026-05-15): data loaders (py/sh/js) rodam no build, saída p/ stdout, cache em src/.observablehq/cache; deploy GH Pages documentado (docs/deploying.md: actions/upload-pages-artifact + deploy-pages@v4, actions/cache por dia). DuckDB-WASM embutido.
- Evidence (MIT, ★7029, ativo): SQL+markdown, build estático, DuckDB como fonte; docs agora em docs.evidence.studio; self-host via Docker/estático.
- GitHub Pages: site ≤1 GB, 100 GB/mês soft, deploy timeout 10 min. Actions: cron em repo público é desativado após 60 dias sem atividade (commits do próprio bot contam); cache 10 GB/7 dias.
- Streamlit Community Cloud: dorme após 12h sem tráfego; ~1 GB RAM. Supabase free: pausa após 7 dias inativo, 500 MB DB.
- Metabase/Superset: exigem servidor sempre ligado (VPS ~US$5-10/mês) + Postgres.

## LLM (preços Anthropic 2026-10): Haiku 5.5 $0.10/$0.50 por MTok; Sonnet 5.5 $2/$10; Opus 5.5 $4/$20; Batch API -50%.
Escala: ~100 atas/ano x ~3 págs x ~1.5k tokens = ~0.5 MTok/ano entrada => centavos (Haiku) a ~US$1-2 (Sonnet). Backfill 2018-2026 (~900 atas) < US$20 mesmo com Opus.
