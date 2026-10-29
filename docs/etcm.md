# e-TCM (TCM-BA) — processos de pagamento da Câmara Municipal de Salvador

Fonte complementar de **custo**: os processos de pagamento que a CMS envia mensalmente ao Tribunal de Contas dos
Municípios da Bahia e que o TCM publica na consulta pública do e-TCM. Para a verba compensatória, é a única fonte
pública com a **quebra por categoria de despesa** (os 15 incisos do art. 14 da Lei 9.828/2025); o
`gridRegistroEmpenho` do portal da CMS (`collect/empenhos.py`) só traz o total empenhado por credor/mês.

## Onde está

URL: <https://e.tcm.ba.gov.br/epp/ConsultaPublica/listView.seam>

Filtros, nesta ordem (cada um recarrega o seguinte via AJAX):

1. **Periodicidade**: Mensal
2. **Ano** (2025, 2026…)
3. **Mês**
4. **Município**: SALVADOR
5. **Unidade**: "Camara Municipal de SALVADOR"
6. **Tipo Gestão**

Resultado: a lista de arquivos enviados pela unidade naquele mês, cada um com uma **classificação** (código `PCMGE0nn`).
As que interessam:

| classificação | conteúdo | uso no spot |
|---|---|---|
| `PCMGE049` | **processos de pagamento**, um PDF por processo | verba compensatória: arquivos `PP <n> - VC - <nome civil>.pdf` → `parse/etcm_vc.py` |
| `PCMGE056` | relação dos processos de pagamento do mês | inventário/controle de completude dos `PCMGE049` |
| `PCMGE048` | **folha sintética dos subsídios** (agentes políticos): `PP <n> Fl. Pagamento - (Agentes Políticos I) - Fl. Sintética.pdf` | `parse/etcm_folha.py` → quantos vereadores receberam e quanto (mar/2026: 41 + 1 = 42 × R$ 26.080,98) |
| `PCMGE035` | **folhas sintéticas de pessoal**: Estatutários, Cargo em Comissão (+ Assistência Militar), Estagiários, Auxílio Transporte, Férias, 13º, Abono, complementares — página "Resumo - Geral" do RH com uma linha por rubrica (código, descrição, qtd. de servidores, remuneração ou desconto) e totais | `parse/etcm_folha.py` → `folha_sintetica*.csv`; única fonte da folha da Câmara em 2026 (o site parou em dez/2025). Agregada por grupo de regime: sem servidor nem gabinete |

Os processos de pagamento do mês M são publicados junto da prestação de contas de M (ex.: o processo da verba de
agosto/2025, pago em 12/09/2025, está no envio de setembro/2025). Um PDF por processo; o nome traz o número do
processo (`PP 2130`), a sigla da natureza (`VC` = verba compensatória; há outras, como diárias e fornecedores) e o
**nome civil** do vereador — que casa com o credor do empenho (`vereador_alias.csv`, fonte `empenho`).

## O que há dentro de um `PP <n> - VC - <nome>.pdf`

~12 páginas digitalizadas com camada de texto OCR (acentos frequentemente corrompidos: `Competéncia n°`,
`servigos`, `20250B000595` para `2025OB000595`):

1. Capa do processo (`PRO-<n>/<ano>`, requerente, data de entrada, "Solicitação de verbas compensatórias") — às vezes duplicada.
2. Termo de abertura ("…Verba Compensatória durante o mês de agosto de 2025", dados bancários **com CPF do vereador**).
3. Declaração de responsabilidade (Leis 9.828/2025 e 9.830/2025).
4. **Resumo das despesas pagas** — tabela com os incisos I..XV e "Valor Pago" por inciso; "TOTAL DAS DESPESAS PAGAS >> R$ …".
5. Autorização para pagamento da Controladoria (`Auditoria nº`, `Competência nº: MM/AAAA`, objeto com o valor) + protocolo de assinaturas (**CPFs dos signatários**).
6. Despacho da Diretoria Financeira.
7. Nota de Empenho SIGEF (`2025NE000656`), Liquidação (`2025NL007402`), Ordem Bancária / Preparação de Pagamento (`2025OB000595`, `2025PP003024`, data do pagamento no banco) — todos com **CPF do credor** e de servidores.
8. Despacho final da Controladoria.

Todo rodapé repete "Anexado via login e senha por <servidor>, Cpf. …" — por isso o parser **mascara qualquer CPF**
(e agência/conta) em tudo que grava e os fixtures de testes são dumps de texto mascarado
(`tests/fixtures/etcm_vc_pp2130.txt`, `etcm_vc_pp367.txt`), não o PDF.

### Três formatos da página de categorias (coluna `layout` do silver)

A Controladoria mudou o formulário duas vezes em 2025; o parser detecta o formato por processo:

| `layout` | prestações (pasta bronze) | competências | o que a página traz |
|---|---|---|---|
| `detalhamento` | 2025-02, 2025-03 | jan e fev/2025 | **"DETALHAMENTO / RESUMO - PROCESSO VERBA COMPENSATORIA"**: uma linha por documento fiscal — item, inciso (do Ato 009/2025, preenchido pelo gabinete e inconsistente: combustível aparece como VIII, XIV e XVI), tipo da despesa, **nº do documento fiscal**, data de emissão, valor apresentado, glosa, saldo a compensar; às vezes em 2 páginas. Sem fornecedor. Página paisagem, nasceu digital (OCR bom). O cabeçalho pode trazer agência/conta do vereador. |
| `nenhum` | 2025-04, 2025-05 (+ ~2 por mês depois) | fev–abr/2025 | nenhuma tabela: só a Autorização para Pagamento ("importância de R$ …"). Alguns termos de abertura listam as NFs em prosa (David Rios, abr/2025). Entram em `verba_processo` com o total e `confianca=media`, sem itens. |
| `resumo` | 2025-06 em diante | mai/2025 em diante | **"RESUMO DA DESPESAS PAGAS"**: tabela dos 15 incisos do art. 14 da Lei 9.828/2025 com o valor pago em cada um; "TOTAL DAS DESPESAS PAGAS >> R$ …". |

Também caem no filtro "VC" processos que não são de verba (PP 2404/2025: contribuições previdenciárias de um servidor);
o parser rejeita PDFs sem "verba compensatória" no texto (`LayoutError`).

## Parser

`uv run python -m spot.parse.etcm_vc [--bronze data/bronze/etcm]` lê todo `*VC*.pdf` do diretório e grava:

- `data/silver/verba_processo.csv` (uma linha por processo): `arquivo, pp_numero, ano_processo, requerente, vereador_id,
  competencia, data_entrada, total_declarado, auditoria_numero, empenho_numero, liquidacao_numero, ordem_bancaria,
  pagamento_numero, data_pagamento, n_paginas, mes_prestacao, confianca, layout`.
- `data/silver/verba_processo_item.csv` (uma linha por inciso com valor): `pp_numero, ano_processo, competencia,
  categoria_romano, categoria_descricao, valor`. Rótulos em `data/seeds/verba_categorias.csv`. No `layout=detalhamento`
  é a soma do saldo a compensar por categoria inferida.
- `data/silver/verba_processo_nf.csv` (só `layout=detalhamento`; uma linha por documento fiscal): `pp_numero, ano_processo,
  competencia, item, inciso_fonte, categoria_romano, descricao, documento_fiscal, data_emissao, valor_apresentado,
  valor_glosa, valor_compensado`. A categoria da lei vem de palavras-chave sobre a descrição
  (`parse/etcm_vc_detalhamento.py: REGRAS_CATEGORIA`; "assessoria de imprensa" é XII, "assessoria jurídica" é IX,
  "cupom fiscal" sem mais nada é XIV); `inciso_fonte` guarda o que o gabinete escreveu. Linhas de valor sem número de
  item (vários cupons de um mesmo item) viram linhas próprias com `item` vazio.

A tabela de incisos não é detectada por `pdfplumber.extract_tables` (sem linhas de grade no scan); a atribuição usa a
posição das palavras: valores `R$ 9.999,99` na coluna da direita (x0 > 78 % da largura) e blocos de texto iniciados à
esquerda por um numeral romano (OCR: `1`, `ll_`, `1V`, `X1V`…), que aparecem sempre na ordem I..XV — o valor vai para o
bloco cuja faixa vertical contém o `top` do valor. `confianca=baixa` quando a soma dos itens difere do total declarado
ou não se encontram exatamente 15 blocos; `media` quando falta algum campo de cabeçalho. Números SIGEF (NE/NL/PP) são
tomados pela ocorrência mais frequente no documento, porque o OCR erra dígitos isolados (`2025NE000856` numa linha de
lançamento, `2025NEC00656` noutra).

`vereador_id` resolve o requerente (ou o nome do arquivo, sem o sufixo `-compressed`) contra `vereador_alias.csv`
(fontes `empenho` e `etcm`) e `vereador_dim.nome_civil`/`nome_parlamentar`, ignorando acentos e caixa; fica vazio
quando não resolve.

No formulário antigo o saldo a compensar é recalculado como apresentado − glosa (a última coluna é a que o OCR mais
destrói); `confianca=alta` quando a soma dos itens fecha com a linha `TOTAL >>` ou com a "importância" da Controladoria.
`competencia` cai para "Período Analisado: 01 a 28 DE FEVEREIRO 2025" ou "mês de <mês>" + ano do processo quando falta
o "Competência nº".

## Coleta

`uv run python -m spot.collect.etcm --ano 2025 --mes 09 [--filtro VC] [--max N]` ou `--todos-meses` (= `make etcm`,
de 2025-01 ao mês corrente; fica fora de `make collect`/`refresh` por ser lento, ~2-5 min por mês).

A consulta é um formulário JSF/Seam (RichFaces) com estado de view no servidor e filtros encadeados por AJAX, e o
download passa por um `commandLink` com `cid` de conversa — por isso a navegação é feita com um Chromium headless
(Playwright, dependência de desenvolvimento; `uv run playwright install chromium`) e não com `httpx`: Mensal → ano →
mês → SALVADOR → Camara Municipal de SALVADOR → Gestão → Pesquisar → abre a prestação → filtra "Nome do Documento"
(`VC`) → pagina a tabela e baixa cada PDF (`a[id$='downloadDocBinario']`). Um contexto de navegador por mês,
≤ 1 download/s, uma nova tentativa por download, headless.

Saída em `data/bronze/etcm/<YYYY-MM>/` (mês da **prestação**, não da competência): os PDFs com o nome original
(só `/` e `\` virados `_`), `manifest.jsonl` (nome, classificacao, bytes, sha256, coletado_em, mes_prestacao, url,
filtro) e `_lista_VC.json` com todos os documentos listados para o filtro, baixados ou não — a conferência de
completude é contra ele (~42-43 processos VC/mês; menos indica licenças/suplentes ou pedidos não feitos). Mês sem
prestação publicada só loga e devolve código 2 (a Câmara envia ~40 dias depois do fim do mês). Arquivo já existente
não é baixado de novo (idempotente).

## Folhas sintéticas (`make etcm` 2ª linha → `parse/etcm_folha.py`)

Coleta: `uv run python -m spot.collect.etcm --todos-meses --filtro "" --classes PCMGE035,PCMGE048` (lista todos os ~260–470
documentos do mês e baixa só essas classes; `_lista_todos.json` guarda o inventário completo do mês). Parse por posição das
palavras na página "Resumo - Geral" (descrição x < 228, quantidade 228–300, REMUNERAÇÃO 300–450, DESCONTOS ≥ 450; carimbos
laterais fora). Saídas `data/silver/folha_sintetica.csv` (rubricas) e `folha_sintetica_resumo.csv` (uma linha por folha com
totais e `confianca`; a mesma folha — mesmo `folha_id` na competência — vem anexada a vários processos: líquido, INSS, abono…
e é deduplicada em `metrica_folha_sintetica`). `metrica_custo_camara_mensal` usa a folha analítica do site quando existe
(2025) e a sintética quando não (2026), com `fonte` dizendo qual; nos meses em que as duas existem a diferença é logada.
