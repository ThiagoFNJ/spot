# Backlog

Itens decididos mas ainda não construídos, em ordem de prioridade.

Diagnóstico de UX/dados do dashboard e backlog de produto (48 itens, 2026-10-28): `docs/BACKLOG-dashboard-diagnostico.md`.

## 1. Aba Votações
Uma aba só para votações: cada item votado em plenário (projeto, requerimento, veto…), com data da sessão, resultado e **quem votou e como votou**.

Estado das fontes (spike §3.4): a Câmara **não publica votos nominais em formato estruturado**. `LEG_SYS_votacao` responde 404; o painel eletrônico não é exportado; o único rastro é o texto das atas em PDF (`LEG_SYS_sessao_ata` → `177.21.11.131:8888/LEG/Upload/<GUID>.pdf`) e o Diário Oficial do Legislativo (DOL), que registram "aprovado", "rejeitado", votação simbólica ou nominal e, nas nominais, a lista de nomes.

Caminho proposto:
1. Coletar os PDFs das atas de 2025+ (≈ 275 arquivos, já catalogados com link em `data/silver/sessao.csv`).
2. Extrair por regra os blocos "votação" (texto nativo, sem OCR): item votado, tipo de votação (simbólica/nominal), resultado, e nas nominais a lista sim/não/abstenção.
3. Cruzar com `proposicao` pelo código e com `vereador_alias` (fonte `ata`, nomes em caixa alta).
4. Para votações simbólicas (a maioria), registrar apenas presença na sessão + resultado; o voto individual não existe na fonte e o dashboard deve dizer isso.
5. A imprensa publica o voto nominal em itens de repercussão (ex.: Correio 24h listou os 27 × 11 do título a Flávio Bolsonaro, 06/05/2026) — fonte complementar para validar a extração das atas.
6. Pedido LAI em paralelo: registros do painel eletrônico por sessão (RI art. 17 §§6-7 fala em chamada nominal na Ordem do Dia).

## 2. Taxa de aprovação (tramitação por proposição)
Crawl de `prop_interna_tram` (~4 mil GETs para 2025-26, uma sessão PHP por lote de 500) para obter desfecho (Aprovado / Sancionado + nº da lei) e data de protocolo. Destrava a "taxa de aprovação por coorte" do spike §4.2 e substitui a coluna "Situação" (retrato do momento) por um desfecho real.

## 3. Verba compensatória: detalhamento e verificação externa
Fontes candidatas levantadas em 2026-10-28 (SICONFI MSC, SIGA API, `trans_nf`, PNCP, TSE, Receita…): `docs/fontes-candidatas.md`.
Feito: empenhos por vereador (`collect/empenhos.py`) e processos de pagamento do e-TCM (`collect/etcm.py` + `parse/etcm_vc.py`,
três formatos — ver `docs/etcm.md`). Falta:
- **Pedido LAI** (Lei 9.828/2025 art. 15 §2 obriga publicar o Requerimento Padrão no portal e a Câmara não publica):
  pedir, por vereador e competência, as notas fiscais e o Requerimento Padrão dos processos `PRO-<n>/2025` já
  identificados; para jan–fev/2025 o pedido pode citar nº e data de cada documento fiscal (`verba_processo_nf`).
- **Impulsionamento (inciso XIII) × Biblioteca de Anúncios da Meta**: probe em `scratchpad/pw/meta_ads_mes.py`
  (Playwright, `ad_type=political_and_issue_ads`, país BR, janela de impressões no mês). Ago/2025: Roberta Caires fecha,
  Hamilton Assis na ordem de grandeza, Cezar Leite declarou ~6× o que a Meta mostra, Silvio Humberto declarou e não há
  anúncio. Produtizar: mapear a página oficial de cada vereador uma vez (`vereador_dim.meta_page_id`), coletor mensal,
  tabela `declarado × observado (faixa)` na aba Custo. Limites: faixas de gasto por anúncio (vida inteira), só anúncios
  com rótulo político mostram gasto, outras plataformas (Google Ads Transparency Center tem dataset público; TikTok).
- Diárias de viagem (inciso VIII) × portal da transparência / DOL.

## 4. Folha de 2026
A Câmara não publicou nenhum PDF de RH de 2026. **Nível Casa resolvido** (2026-10-28) com as folhas sintéticas do e-TCM
(`parse/etcm_folha.py`, visão Câmara do dashboard). **Por gabinete** (2026-10-28): reconstruído a partir da consulta de pessoal do TCM-BA exportada à mão (jan–jul/2026) + lotação de 2025; 0–14% dos servidores por mês sem lotação (contratados em 2026). Restante aberto: TCM Controle Social/Pessoal exige reCAPTCHA v2
(manual), ou LAI, ou reconstrução pelos atos de nomeação/exoneração publicados no DOL × tabela de símbolos (CC-10 por grau).
Também pendente: reconciliar a folha analítica de 2025 (RH do site) com a sintética do mesmo mês (o log de `metrics.custo` já compara).

## 5. Íntegra das proposições
Em andamento: coletor `collect/dol.py` localiza no DOL a edição que publicou cada proposição (texto completo em PDF). Cobertura por tipo a confirmar; requerimentos e indicações podem não ser publicados na íntegra.

## 6. Publicação pública
GitHub Pages servindo a pasta `site/`, com Actions rodando `make refresh` semanalmente. Exige `git init` em `spot/` e repositório no GitHub.

## 7. Qualidade de dados
- Reconciliar 42 subsídios pagos (SIGA 06/2025) vs 43 ocupantes no modelo; fonte do subsídio de jan/2025.
- Diff entre snapshots semanais da frequência para rastrear correções retroativas da Câmara.
- Presença em reuniões de comissão: sem fonte pública (RI art. 97 §3º); pedido LAI.
- e-TCM: ~2 processos/mês caem em `layout=nenhum` por falha de OCR no título (Paulo Magalhães lista itens só no termo
  de abertura); PP 567/2025 (Alex Souza) perde o item 01 embaralhado pelo OCR (dif R$ 244,32); 2025-12 tem 87 PDFs
  (duas prestações na mesma pasta?) e 2026-01 nenhum — conferir no e-TCM.
- Meta Ad Library: identificar a página por `page_id` e não por busca de nome (homônimos; "Cezar Leite" tem anúncios
  pagos pela própria pessoa física).
