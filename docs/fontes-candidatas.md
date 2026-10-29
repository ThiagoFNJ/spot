# Fontes candidatas para agregar aos dados da Câmara (levantamento de 2026-10-28)

Complementa `docs/spike/spike-dashboard-vereadores-cms.md` (fontes já em produção: LEG_SYS frequência/sessões/
proposições/comissões, RH em PDF, `gridRegistroEmpenho`, DOL via dioly, e-TCM Consulta Pública). Marcação:
**[verificado hoje]** = testado com request real; **[a verificar]** = conhecido, sem teste neste projeto.

## 1. Estruturadas, com API (prioridade: barato e confiável)

| fonte | o que dá para a CMS | acesso | status |
|---|---|---|---|
| **SICONFI – Matriz de Saldos Contábeis (MSC)**, STN | Despesa **mensal** da Câmara por natureza (`33909300` indenizações = verba compensatória, `31901100` vencimentos, `33903900`, `44905200`…), por conta PCASP (dotação, empenhado, liquidado, pago), função/subfunção, fonte. Salvador = `id_ente=2927408`; Câmara = `poder_orgao=20231` (Executivo `10131`, `10132`). Jun/2025: 7.819 linhas, paginação `offset=5000` (`hasMore`). | `https://apidatalake.tesouro.gov.br/ords/siconfi/tt/msc_orcamentaria?id_ente=2927408&an_referencia=2025&me_referencia=6&co_tipo_matriz=MSCC&classe_conta=6&id_tv=ending_balance` (JSON; também `msc_patrimonial`, `msc_controle`, `rreo`, `rgf`, `dca`, `entes`) | [verificado hoje] |
| **TCM-BA – SIGA API** | `unidades_gestoras.rule?sys=SIG` (Câmara de Salvador = **cod_unidade 749**, Prefeitura 334); `wspublicidade.rule?sys=SIG&ano=2025&unidade=749` = pagamentos de publicidade da Câmara por mês/credor/empenho/dotação (W4 Comunicação & Marketing, R$ 265 mil em jan/2025); `wsmultaspagas.rule`. | `https://siga3.tcm.ba.gov.br/webrun/…` (JSON, ISO-8859-1) | [verificado hoje] |
| **TCM-BA – Controle Social / Pessoal (SIGA)** | Folha por servidor, por município/entidade/mês/regime (Câmara = `cdEntidade` 749). O formulário WordPress faz POST na própria página com **reCAPTCHA v2** (checkbox) e chama `webservice.tcm.ba.gov.br` (`entidades`, `tipoRegime` abertos; `exportar/pessoal` → 500). **Integrada manualmente** em 2026-10-28: exportação XLSX mensal feita por pessoa (`data/bronze/tcm_pessoal/README.md`), `parse/tcm_pessoal.py`. Colunas: nome, matrícula, regime, cargo+grau+símbolo, líquido, base, vantagens, gratificação, 13º, carga, situação, admissão — **sem lotação**. Base+vantagens+gratificação = `proventos` do site em ~95% das linhas (jan–mar/2025). A lotação de 2026 é recuperada pela matrícula na folha de 2025 (`metrics/custo.py: reconstruir_folha`); 0–7% dos servidores por mês ficam sem lotação (contratados em 2026). Não automatizar o captcha. | `https://www.tcm.ba.gov.br/controle-social/pessoal/` | em produção (manual) |
| **e-TCM – folhas sintéticas (PCMGE035/048)** | Folha mensal da Câmara por grupo de regime e rubrica (qtd. de servidores, remuneração, descontos) + subsídios pagos. **Integrada** em 2026-10-28: `collect/etcm.py --classes`, `parse/etcm_folha.py`, `metrica_custo_camara_mensal`. Mar/2026: 1.081 servidores, R$ 10,1 mi de folha, 42 subsídios. Sem servidor nem gabinete. | Playwright (`make etcm`) | em produção |
| **TCM-BA – e-TCM Consulta Pública** | Processos de pagamento (em uso). Outras classes: PCMGE048 subsídios, PCMGE056 relação de processos; checar se há classe de **folha de pagamento** mensal. | Playwright (`collect/etcm.py`) | em produção |
| **Querido Diário (OKBR)** | Diário Oficial do Município de Salvador (DOM, Executivo + leis sancionadas) desde 2020-11-24, busca full-text com excertos e PDF. "verba compensatória" → 7 edições (ex.: Lei 9.867/2025, que altera a 9.828). Serve para leis/decretos sobre subsídio e verba; atos da Câmara (nomeações de assessores) estão no **DOL** (dioly, já em uso). | `https://api.queridodiario.org.br/gazettes?territory_ids=2927408&querystring=…` | [verificado hoje] |
| **PNCP** (Lei 14.133) | Contratos/licitações da Câmara por `cnpjOrgao`. Busca por nome não acha a CMS; **falta o CNPJ da Câmara** (não está nas páginas públicas raspadas). API devolve 429 em HTML após rajadas; `tamanhoPagina` até 500 em contratos. | `https://pncp.gov.br/api/consulta/v1/contratos?…` | [parcial] |
| **TSE – dados abertos** | Candidatos 2024 (partido, bens declarados, CPF parcial), **prestação de contas eleitorais com fornecedores de campanha** → cruzar com fornecedores da verba (quando a LAI trouxer as NFs) e com a folha (assessores que foram doadores/fornecedores). | `https://dadosabertos.tse.jus.br` (CSV) + DivulgaCandContas | [a verificar] |
| **Receita Federal – CNPJ aberto** | QSA (sócios) e CNAE dos fornecedores: detectar empresa de assessor/parente, CNAE incompatível com o serviço (ex. "mídia" prestada por posto de gasolina). Espelho em Brasil.io. | `https://dadosabertos.rfb.gov.br` (dump mensal, ~5 GB) | [a verificar] |
| **Meta Ad Library** | Anúncios políticos por página, gasto em faixas, período. Probe funcional em `scratchpad/pw/meta_ads_mes.py`; a API oficial exige conta verificada. | Playwright / Graph API `ads_archive` | probe feito |
| **Google Ads Transparency Center** | Anúncios políticos por anunciante verificado; dataset público `bigquery-public-data.google_political_ads` (confirmar cobertura BR). | BigQuery / `adstransparency.google.com` | [a verificar] |

## 2. Portais da própria Câmara ainda não explorados (ScriptCase, mesmo protocolo de `scriptcase.py`)

`https://cmsalvador.sys.inf.br/consulta.html` ("Transparência Financeira") lista, além de `gridRegistroEmpenho` (em uso):

| app | conteúdo | sondagem |
|---|---|---|
| `ca/trans_nf/` | **Notas fiscais de fornecedores** da Câmara: processo PRO-n/ano, origem, situação, período, valor, nº da NF, solicitante (fornecedor) e **PDF da NF** (`adm.cmsalvador.sys.inf.br/Upload/adm-sys/PRO<n><ano>/<guid>.pdf`). 11.789 NFs de 2007 a 2026 (2025: 2.707). **Nenhum dos 602 processos de verba compensatória aparece** — é o fluxo de pagamento a fornecedores, não de ressarcimento. Útil para: custo da Casa por fornecedor, publicidade institucional, cruzamento de fornecedores. | [verificado hoje: dump de 30k linhas ok] |
| `ca/trans_liq/` | Liquidações (9.393, com PDF) | [verificado hoje] |
| `ca/trans_pagamento/` | Pagamentos (mesmo layout) | [verificado hoje] |
| `ca/gridRegistroDespesa` | Despesas (par do empenho; já citado no backlog) | [a verificar] |
| `ca/contrato/` | Contratos: nº, fornecedor, assinatura, vigência, valor, meses, publicação/diário, aditivos | [verificado hoje] |
| `ca/licitacao/` | Processos licitatórios | [a verificar] |
| `ca/gridAcompanhamento/` | Convênios/obras/projetos — tem registro "teste" de R$ 90 mil | baixa prioridade |
| `leg/salvador/LEG_SYS_pronunciamento/` | **Discursos dos vereadores** (sinal de atividade além das proposições) | [a verificar] |
| `leg/salvador/LEG_SYS_mensagem/` | Mensagens do Executivo (origem dos PLEs) | [a verificar] |
| `cms.ba.gov.br/transparencia/ordem-do-dia` | Pauta por sessão (insumo da aba Votações do backlog) | [a verificar] |

## 3. Avaliação externa e alavancas

- **Radar da Transparência Pública (Atricon/TCs)**: nota itemizada do portal da CMS (quais itens obrigatórios LAI/LRF faltam — base objetiva para o pedido LAI e para a cobrança do art. 15 §2 da Lei 9.828). `radardatransparencia.atricon.org.br`. [a verificar]
- **Portal da Transparência da Prefeitura** (`transparencia.salvador.ba.gov.br`): a Câmara é a UG 200002 no SIGEF municipal; checar se o portal/API do Executivo expõe todas as UGs (empenhos com credor e CNPJ). [a verificar]
- **e-SIC da Câmara**: via Ouvidoria (`cms.ba.gov.br/ouvidoria/estamos-te-ouvindo`).
- **TV Câmara / YouTube**: sessões gravadas → votações nominais por transcrição (backlog, custo alto).

## 4. Ordem sugerida

1. **SICONFI MSC** como "fonte de verdade" mensal do custo da Casa por natureza (fecha o `custo_camara` sem depender do PDF de RH) e conciliação com os empenhos.
2. ~~SIGA pessoal~~ → Casa: folhas sintéticas do e-TCM; gabinete: consulta de pessoal do TCM exportada à mão + lotação de 2025. Pendente: pedido ao TCM (e-SIC, LAI art. 8º §3º II e III) para publicar pessoal por unidade gestora na API do SIGA, e à Câmara para retomar a relação de servidores com centro de custo. Os atos de nomeação no DOL não trazem gabinete (verificado em 2026-10-28).
3. **`trans_nf` + `contrato`**: fornecedores e NFs da Casa (publicidade institucional, terceirizados) — coletor idêntico ao de empenhos.
4. **CNPJ da Câmara → PNCP**; TSE + Receita para o grafo fornecedor–assessor–candidato.
5. Meta/Google para o inciso XIII.
