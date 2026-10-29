# Como obter cada arquivo do bronze

O bronze do spot é **privado**: os PDFs do e-TCM trazem CPF, agência e conta de servidores e fornecedores, e o
projeto não redistribui esses dados. Em troca, este documento diz **onde**, **quando** e **como** cada arquivo
foi obtido, para que qualquer pessoa consiga reconstruir o bronze por conta própria com o código do repositório.

Todo coletor grava, ao lado dos arquivos, um `manifest.jsonl` com `url`, parâmetros, `sha256`, `bytes` e
`coletado_em`. O manifesto é a prova de origem de cada arquivo: quem recoletar pode comparar o `sha256` (arquivos
que a fonte não alterou batem byte a byte; snapshots diários e PDFs gerados na hora não batem, e isso é esperado).

Regras de coleta que valem para todos (detalhes em `CLAUDE.md`): no máximo 1 request por segundo por host,
User-Agent `spot-cms-monitor/0.1`, timeout explícito, 3 tentativas com backoff, arquivo existente não é baixado de
novo (idempotente), escopo a partir de 2025-01 (legislatura 2025–2028).

## Fontes automatizadas

| Fonte (`data/bronze/…`) | Onde | Como | Quando | Arquivos |
|---|---|---|---|---|
| `frequencia/` | App ScriptCase `LEG_SYS_frequencia` em `http://45.4.247.157/leg/salvador/` | `uv run python -m spot.collect.frequencia [--since AAAA-MM] [--until AAAA-MM] [--force]` | Mensal. `make refresh` recoleta o mês corrente e o anterior com `--force`, porque a Câmara corrige presença retroativamente | `<AAAA-MM>_tipo<N>.csv`, um por mês × tipo de sessão (1 ordinária, 2 especial, 3 solene, 4 extraordinária) |
| `sessoes/` | App `LEG_SYS_sessao_ata` no mesmo host | `uv run python -m spot.collect.sessoes [--date AAAA-MM-DD]` | Snapshot diário (no `refresh`) | `sessoes_catalogo_<data>.html` (grade inteira, com os links das atas) e `.csv` (contagem de conferência) |
| `proposicoes/` | Grade `prop_interna` em `https://cmsalvador.sys.inf.br/cl/prop_interna/` e resumo `LEG_SYS_produtividade_parlamentar_proposicao` em `45.4.247.157` | `uv run python -m spot.collect.proposicoes [--snapshot AAAA-MM-DD]` | Snapshot diário (no `refresh`) | `prop_interna_<data>.csv` e `resumo_<ano>_<data>.html` |
| `dol/` | API do Diário Oficial do Legislativo: `https://portal-api.dioly.com.br/api/diarios/?tipo=DOL&q=` | `uv run python -m spot.collect.dol [--since-ano 2025]` (lê `data/silver/proposicao.csv`, então roda depois do parse de proposições) | Sob demanda, quando entram proposições novas | `<codigo>.json`, `<codigo>__termos.json`, `<codigo>__numero.json`: resposta bruta da busca por proposição |
| `rh/` | Página de Recursos Humanos: `https://www.cms.ba.gov.br/transparencia/recursos-humanos` | `uv run python -m spot.collect.rh` | Mensal (no `refresh`). Em 2026 a Câmara parou de publicar a folha por gabinete | `recursos-humanos_<data>.html`, `links_<data>.json`, `servidores_<AAAA-MM>.pdf`, `estagiarios_<AAAA-MM>.pdf` |
| `vereadores/` | `https://www.cms.ba.gov.br/vereadores` e cada perfil `/vereadores/<slug>` | `uv run python -m spot.collect.vereadores [--fotos]` | No início da legislatura e quando há posse de suplente | `vereadores.html`, `<slug>.html`; com `--fotos`, `fotos/<slug>.jpg` |
| `empenhos/` | Grade `gridRegistroEmpenho` em `https://cmsalvador.sys.inf.br/ca/gridRegistroEmpenho/` | `uv run python -m spot.collect.empenhos [--date AAAA-MM-DD]` | Snapshot diário (no `refresh`) | `empenhos_<data>_p<NNN>.html`, uma página de 500 empenhos por arquivo |
| `etcm/` | Consulta pública do e-TCM (TCM-BA): `https://e.tcm.ba.gov.br/epp/ConsultaPublica/listView.seam` | `make etcm`, que roda `spot.collect.etcm --todos-meses` (processos de verba compensatória) e `--filtro "" --classes PCMGE035,PCMGE048` (folhas sintéticas). Exige Chromium do Playwright: `uv run playwright install chromium` | Mensal, fora do `refresh` (cerca de 5 min por mês). O TCM recebe a prestação com atraso de 1 a 2 meses | `<AAAA-MM>/<nome original do documento>.pdf`, `_lista_<filtro>.json` (inventário do que a prestação lista) |

Detalhes de protocolo de cada fonte estão no docstring do coletor (`src/spot/collect/<fonte>.py`), em
`docs/HANDOVER.md`, `docs/HANDOVER-adendo-2026-10-27.md` e `docs/etcm.md`.

## Fontes manuais

| Fonte (`data/bronze/…`) | Onde | Como | Quando | Por que é manual |
|---|---|---|---|---|
| `tcm_pessoal/` | Consulta de pessoal do TCM-BA: `https://www.tcm.ba.gov.br/controle-social/pessoal/`, entidade 749 (Câmara Municipal de Salvador) | Uma pessoa exporta a planilha de cada mês e roda `uv run python -m spot.parse.tcm_pessoal --ingest ~/Downloads/*.xlsx`, que descobre a competência no cabeçalho e grava `<AAAA-MM>/pessoal_749_<AAAA-MM>.xlsx` com manifesto. Passo a passo em `data/bronze/tcm_pessoal/README.md` | Mensal. Reexportar um mês incompleto (ex.: jul/2026) substitui o arquivo | A consulta exige reCAPTCHA. O projeto não automatiza nem contorna captcha |
| `legislacao/dol/` | Edições do Diário Oficial do Legislativo com os decretos sobre gabinete e assessores | Busca na mesma API do DOL (`q="Decreto Legislativo" assessor pontos`, por exemplo) e download do PDF da edição. Hoje é manual; o manifesto registra URL, edição e normas de cada PDF | Quando uma norma nova é citada no dashboard | Ainda não virou coletor (pendência: `collect/legislacao.py`) |

## Normas citadas e onde estão

| Norma | Assunto | Edição do DOL |
|---|---|---|
| DL 946/2010 | Limite de 157 pontos por gabinete | nº 3.564, 14/12/2010 |
| DL 958/2015 | Máximo de 17 assessores, cargos G-30, pontos da Mesa e lideranças | nº 4.473, 27/02/2015 |
| DL 968/2017 | De 8 a 16 assessores, mais 5 pontos | nº 5.029, 17/07/2017 |
| DL 983/2021 | Gabinete do Presidente (12 a 33 assessores) e lideranças | nº 5.899, 12/02/2021 |
| DL 985/2022 | Ponto a R$ 332,80 | nº 6.355, 15/12/2022 |
| DL 990/2026 | Ponto a R$ 346,11 desde 01/05/2026 | nº 7.200, 19/05/2026 |

Leis municipais (subsídio, plano de cargos, verba compensatória) e o Regimento Interno estão em
`docs/spike/evidence/legal/`, com as URLs de origem no spike (`docs/spike/spike-dashboard-vereadores-cms.md`).

## Tabelas curadas à mão (`data/seeds/`)

Ficam **no repositório**, não no bucket, porque são decisões editoriais revisáveis por PR:
`vereador_dim.csv`, `vereador_alias.csv`, `vereador_redes.csv` (Instagram e X), `verba_categorias.csv`,
`parametros_custo.csv`, `pesos_v0.csv`. Cada uma tem a origem descrita em `data/seeds/README.md`.

## Onde o bronze fica guardado

O caminho local `data/bronze/<fonte>/…` é espelhado 1:1 em `gs://spot-bronze-9122a143/<fonte>/…`, com o mesmo
`manifest.jsonl` (`make push-bronze` e `make pull-bronze`, módulo `src/spot/cloud.py`). O bucket é privado, tem
versionamento e bloqueio de acesso público. As evidências binárias do spike estão em
`gs://spot-bronze-9122a143/_evidencias_spike/`. Quem precisar do bronze para pesquisa pode pedir acesso de leitura.
