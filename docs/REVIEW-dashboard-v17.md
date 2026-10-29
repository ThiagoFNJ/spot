# Revisão do dashboard, versão 17 (2026-10-28)

Duas partes: (1) QA do que foi implementado nas versões 14–17 do Artifact (`site/index.html` + `site/data/*.json` gerados em 2026-10-28), (2) especificação do perfil do vereador (item b2 do `docs/BACKLOG-dashboard-diagnostico.md`), pronta para implementar em JS puro no mesmo arquivo.

**Método do QA.** Site servido de `/tmp/spotwww` (cópia de `site/`) e navegado com Playwright/Chromium headless em 1280×1000 e 400×900 (modo touch), claro e escuro. Estados testados pela URL: Resumo, Produtividade, Presença e Custo (Gabinetes e Câmara) em 2025 e 2026; com vereador selecionado (`debora-santana`, `alexandre-aleluia`, `tiago-queiroz`); com partido (`pcdob`); glossário; "Copiar link"; clique no card de partido; clique em nome do ranking e do Resumo. Além das telas, os números de cada bloco foram recalculados direto dos JSON para comparar abas entre si. Nenhum erro de console em nenhum estado. Acentos quebrados nas capturas são do servidor local (sem charset) e foram ignorados.

Severidade: **bloqueia** = número ou afirmação errada sobre pessoa nomeada, ou layout quebrado na página inicial; **incomoda** = confunde o leitor ou contradiz outra parte do site; **detalhe** = texto, concordância, acabamento.

---

## Parte 1 — QA da v17

### 1.1 Bloqueia

**B1. Alerta "acima do teto anual" da verba é um artefato do cálculo e nomeia 7 vereadores em 2025 (e 1 em 2026) que não passaram do teto do ano.**
`renderResumo` (bloco `byV`, tag `verba`) e `renderCustoGab` (pílula `acima do teto anual` em `#verba-bars`, `tipExtra` de `#vteto2-bars`) somam `verba_compensatoria_teto` **só dos meses em que há empenho** (`custo.json.verba`). Carlos Muniz tem 4 linhas (set–dez/2025, R$ 151.880, e dez com 2 empenhos = R$ 60.600) e o "teto acumulado" vira 4 × 34 mil = R$ 136 mil; o site publica "Carlos Muniz recebeu R$ 151.880 de verba no ano, R$ 15.880 acima da soma dos tetos mensais". O teto anual real de quem esteve em exercício o ano todo é 11 × 34 mil + 39 mil (dez) = R$ 413 mil. Com esse critério, em 2025 só Alexandre Aleluia (R$ 440.875) e Ricardo Almeida (R$ 415.343) ficam acima; Marcelle Moraes, Débora Santana, Omarzinho Gordilho, Paulo Magalhães Júnior e Carlos Muniz saem. Em 2026, Ricardo Almeida (R$ 249.550 vs 6 × 39 mil) está muito abaixo de 9 × 39 mil = R$ 351 mil. O "a validar" entre parênteses não salva: o leitor lê o nome e o valor.
*Correção:* o teto acumulado deve ser teto do mês × meses em exercício no ano (derivar de `presenca.vereadores.em_exercicio`/meses com sessão, ou exportar `teto_anual_exercicio` em `custo.json.anual`; o campo atual `verba_compensatoria_teto` = 12 × 34.000 também ignora o salto de dezembro). Manter o alerta nominal só para `total > teto_anual_exercicio`; o "n meses acima do teto mensal" fica como item agregado informativo, que é o que o art. 22 permite.

**B2. KPI com o nome do vereador mostra o valor da Casa.**
`renderPres`: `kpi(\`Presença · ${scopeLabel()}\`, fmtPct(P/(P+A)))` usa `scope` filtrado só por partido; com `state.ver` o rótulo diz "Presença · Débora Santana" e o valor é 96,1% (dela é 77,1%; para Tiago Queiroz, 92,5% vs 93,8%). `renderCustoGab`: "Custo mensal · Alexandre Aleluia — R$ 7.110.163 — Casa: R$ 7.110.163" (o gabinete dele custa R$ 216 mil). O `detailBox` logo abaixo tem o número certo, o que agrava: dois valores com o mesmo nome a 40 px de distância.
*Correção:* com `state.ver`, ou o KPI usa o valor do vereador (e o `sub` traz "Casa: x"), ou o rótulo volta a "Casa"/partido. Mesmo problema latente em `renderProd` (`#prod-kpis` mostra a Casa sem dizer) e em `#custo-kpis` "No ano de 2025 R$ 82 mi" com vereador selecionado.

**B3. Alerta "ritmo" de 2026 afirma algo falso sobre Duda Sanches e Maurício Trindade.**
`fracao_faltas_lom27` em 2026 é `ausentes / ordinarias_do_ano` com `ordinarias_do_ano = 45`, que são as sessões **já realizadas**, não as previstas para o ano (2025 teve 86). O Resumo escreve "já faltou a 20% das sessões previstas para o ano" e a pílula `alertaPres` diz "ritmo 20% do ano"; o correto é "faltou a 9 das 45 sessões realizadas até 06/10 (20%)", o que projeta ~17 faltas em 86 sessões, ou 20% do ano, longe do terço da LOM. O limiar `>= 0,2` também não representa "ritmo que leva a um terço": quem mantém 20% termina em 20%. Os dois ainda têm 9 licenças cada em 2026, o que o texto não menciona.
*Correção:* trocar texto e pílula para "9 faltas em 45 sessões (20%); limite da LOM: um terço das sessões do ano"; usar limiar 0,25 ou 0,3 para a tag "atenção"; ou exportar `ordinarias_previstas` (média 2025 = 86) e calcular a projeção de verdade.

**B4. Números do Resumo não batem com as abas para as quais ele linka.**

| indicador | Resumo | aba | causa (função) |
|---|---|---|---|
| Custo dos gabinetes / mês, 2025 | R$ 7.275.276 "46 vereadores" | Custo: R$ 7.110.163 (= 43 × "Por gabinete" R$ 165.353) | `renderResumo` soma `media_mensal_custo_observado` das 46 linhas de `custo.anual` (3 licenciados com 2 meses de folha somam a média deles ao titular do mesmo centro de custo); `renderCustoGab` faz média mensal da Casa. Em 2026: R$ 7.019.559 vs R$ 6.843.174 (Luiz Carlos, 1 mês). |
| Custo total da Câmara / mês, 2025 | R$ 11.029.793 | Custo › Câmara: R$ 11.313.154 | Resumo faz média de 12 meses incluindo jan (sem subsídio); `renderCustoCam` usa `fd` (≥ 2025-02). |
| Presença · Casa, 2025 | 96,2% · 43 vereadores | Presença: 96,1% · 46 vereadores | Resumo exclui `sem_dado`; a aba não. Em 2026: 92,7% vs 92,5%. |
| Verba no ano, 2026 | R$ 12.155.985 | Custo: R$ 12.193.885 · "49 vereadores" | Resumo exige `vereador_id`; a aba inclui o credor não identificado "Everaldo Bispo" (2026-08, R$ 37.900, `vereador_id = null`). |

*Correção:* um único helper de "custo mensal da Casa/recorte" reutilizado nas duas abas (média mensal sobre `custo.mensal` do recorte, excluindo `parcial` ou avisando); mesma regra de inclusão de `sem_dado` e de credor não identificado; e o alias de Everaldo Bispo em `data/seeds/vereador_alias.csv`.

**B5. A tabela "Até quando vai cada dado" (`#res-fontes`) estoura o card e cria scroll horizontal na página inicial.**
`table { min-width: 640px }` (regra global) vale para `table.plain`; o card da segunda coluna do `.grid-2` tem 441 px em 1280 e ~370 px no celular. Medido: `document.documentElement.scrollWidth` = 1417 em viewport 1280 e 675 em 400. Os valores da coluna direita ("até 17/12/2025 (86ª sessão)") saem do card. É a aba padrão, em todos os estados.
*Correção:* `table.plain { min-width: 0 }` e `td.v { white-space: normal }` abaixo de 600 px.

### 1.2 Incomoda

**I1. Pílulas `verba`/`folha` informativas dos alertas viram um círculo de 24 px com o texto sobreposto.** `ul.alerts .tag.info` herda a regra `.info { width: 24px; height: 24px; border-radius: 50% }` escrita para o botão "i" (`#tipos-info`). Medido: `width 24px`, `scrollWidth 36 > clientWidth 22`. Visível no Resumo 2025 ("verba19 vereadores…") e 2026 ("folhaA Câmara não publica…"). *Correção:* renomear a classe para `.tag.soft` ou restringir a regra a `button.info`.

**I2. Glossário sem margem interna.** `dialog.tipos { padding: 0 }` e o conteúdo do `#gloss-dlg` não está dentro de `.dlg` (ao contrário de `#tipos-dlg`). Computado: `padding: 0px`; o texto encosta nas bordas em desktop e celular, e o botão "Fechar" fica colado ao canto. *Correção:* envolver em `<div class="dlg">`.

**I3. `readHash` não limpa o que o hash não traz.** Se a URL tem 4 partes (`#custo-2026-todos-gab`), `state.ver` (e `hashPartido`, `custoView`) mantêm o valor anterior; `renderAll` → `writeHash` reescreve a URL com o vereador antigo. Reproduzido: após `#custo-2025-todos-gab-carlos-muniz`, navegar para `#resumo-2025-todos-x` resulta em `#presenca-2025-todos-x-carlos-muniz` ao clicar na aba. Afeta "voltar" do navegador e links editados à mão. *Correção:* em `readHash`, `state.ver = parts.length >= 5 ? … : ""`, `hashPartido = parts[2] ?? "todos"`, `custoView = parts[3] === "cam" ? "cam" : "gab"`.

**I4. `#custo-note` (nota de 2026 da visão Gabinetes) fica visível na visão Câmara e em 2025.** `renderCusto` não esconde a nota quando `!gab`; ela está fora de `#custo-gab`. Fluxo real: Custo 2026 Gabinetes → clicar "Câmara" → trocar o ano para 2025: a página mostra "Em 2026 a Câmara não publicou… aparecem na visão Câmara como 'Lotação não publicada'" em cima da visão Câmara de 2025, abaixo do `#cam-note` que diz outra coisa. *Correção:* `note.hidden = !gab || state.ano === 2025 || …` em `renderCusto`.

**I5. "Maiores / menores" do Resumo (`topList`) mostram extremos que não informam.**
- Presença: 12 vereadores com 100% em 2025 (13 em 2026); os 5 "maiores" são os 5 primeiros em ordem alfabética. Mostrar "12 vereadores com 100%: …" ou listar quem tem 100% com menos licenças.
- Custo "menores" 2025: Alberto Braga e Augusto Vasconcelos (licenciados, 2 meses de folha) e Julio Santos; o menor gabinete de ano inteiro (Sandro Filho) fica misturado. Excluir `meses_com_folha < 6` dos extremos ou marcar "(2 meses)".
- Produção "menores" 2026: "Cris Correia 0" (tem 2 proposições, ambas excluídas da ponderação) e "Julio Santos 4" (1 proposição em 3 meses). "Maiores" 2026: "Felipe Santana 284,6" (240 em 8 meses, licenciado em agosto, normalizado × 1,5). Mostrar o bruto ao lado ("284,6 · 240 em 8 meses") e excluir `meses_exercicio < 6` dos extremos.
- Com partido de ≤ 10 vereadores (ex.: `#resumo-2025-pcdob-x`), os mesmos nomes aparecem nas duas colunas em ordem invertida. Se `rows.length <= 10`, uma lista só.
- Com vereador selecionado (`#resumo-…-debora-santana`), o `h2` diz "Débora Santana em 2025", os KPIs são dela, mas as listas e os alertas são da Casa, sem destaque dela. Marcar a linha dela (`hl`) ou mostrar "posição x de 43" no KPI.

**I6. Cards "Por partido": bancadas de 1 vereador dominam o topo.** Em 2025, 13 das 18 legendas têm 1–2 vereadores (8 com 1); em presença, as quatro primeiras barras são PSD, Cidadania, PT e PDT, todas 100% e todas um nome; em produção, PV (1) e PSD (1) lideram; em custo, Novo (1) = Alexandre Aleluia. A "média do partido" ali é a nota de uma pessoa, e o card sugere comparação de bancadas que não existe.
*Proposta:* (a) barras só para bancadas com n ≥ 3 (2025: PSDB 8, União 7, Republicanos 6, PP 5, PCdoB 3; 2026: PSDB, PP, Republicanos, União, PRD), com mín–máx dos membros como traço fino sobre a barra (já está no tooltip); (b) bancadas de 1–2 num bloco compacto abaixo, "Bancadas de 1 ou 2 vereadores (13)", como chips "PV · André Fraga 134", clicáveis, recolhido por padrão; (c) `valueText` do card de presença em p.p., não "%" (`+3,9% vs Casa` são 3,9 pontos); (d) opção de ordenar por n. A mediana em vez da média para n ≥ 3 evita que um gabinete da Mesa puxe o PSDB em custo.

**I7. Visão Câmara 2026: KPIs de gabinetes e estrutura não fecham e julho aparece vazio.** "Em gabinetes de vereadores 41,2%" + "Na estrutura administrativa 43,5%" = 84,7%; o resto é lotação não publicada (até 11,3%) sem KPI, mais jul/2026 (folha sintética, `folha_gabinetes = null`) entrando como zero na média de 9 meses (`avg(mensal, "folha_gabinetes")`). Em `#cam-split-bars`, a linha jul/2026 tem valor (R$ 9.971.139) e barra vazia. "Por regime" 2026 lista "Cargo em comissão · gabinetes 663,8 pessoas" sem a parcela sem lotação. *Correção:* médias de quebra só sobre meses com `folha_gabinetes != null`; terceiro KPI "Lotação não publicada x%"; em julho, um segmento único "sem quebra (folha sintética)".

**I8. Na aba Custo com vereador selecionado há dois totais de verba para o mesmo ano.** `#verba-sub` "1 vereadores · 9 meses · R$ 348.250" (de `custo.verba`, inclui set/2026) e o `detailBox` "verba no ano: R$ 309.250 · 8 meses com ressarcimento" (de `custo.anual`, cortado nos meses com folha). Em 2025, o `fact` "teto R$ 34.000" vem de `verba_compensatoria_teto / meses_com_folha` = 408.000/12 e ignora o teto de dezembro (R$ 39 mil). *Correção:* o detalhe usa a mesma agregação de `custo.verba` do card, ou diz "até ago/2026 (meses com folha)".

**I9. Textos fixos que a2 deveria ter removido.** (a) Nota sob `#custo-timeline`: "Janeiro sem subsídio: a lei do subsídio vigora a partir de fevereiro de 2025. Estagiários só publicados de abril a novembro." aparece em 2026, ano em que estagiários não são publicados (`meses_com_estagiarios = 0`) e janeiro é "parcial" por outro motivo (1 subsídio na sintética). (b) `aria-label` do gráfico: "Custo observado por mês de 2025". (c) `detailBox` de custo sem linha: "Sem gabinete próprio na folha de 2025 (…)". (d) `#custo-kpis` "No ano de 2026 … 8 meses" e `#cam-kpis` "soma dos 9 meses" para o mesmo ano, sem dizer que jul/2026 não tem folha por gabinete (a exportação do TCM-BA de julho foi descartada em `custo.mensal` mas a sintética entrou em `custo_camara.mensal`). (e) KPI de custo em 2026 inclui jan/2026 (`parcial = true`) na média sem aviso; o aviso só existe no tooltip.

**I10. Celular (400 px).** (a) `.filters` sticky ocupa 186 px (21% da tela) em todas as abas; item a12 segue pendente e é o maior problema de uso no celular. (b) KPI "Verba compensatória no ano — R$ 13.925.478" corta o último dígito ("R$ 13.925.47") no grid de 2 colunas; o `.kpi .value` de 30 px não cabe em ~175 px. (c) Listas "Maiores/menores" do Resumo cortam os valores de custo ("R$ 113…", "R$ 12…") porque `.tops .split` força 2 colunas. (d) Tabelas com `min-width: 640px` rolam horizontalmente sem coluna fixa de nome (`#pres-table` mostra "Vereador | Faltas | Presença | …" e some a última coluna). (e) Faixa de presença com células de 11 × 16 px e "clique abre a ata": alvo pequeno demais para toque.

**I11. "O que merece atenção" é dominado pelos alertas de verba "a validar".** Em 2025, 7 dos 9 itens são B1; o bloco que deveria apontar o que é relevante vira uma lista de suspeitas não validadas. Após corrigir B1, ordenar: LOM 27 → ritmo → verba acima do teto anual (validado) → 1 item agregado "n vereadores com 3+ meses acima do teto mensal (ver aba Custo)" → cobertura (folha, categorias). Tag diferente para "alerta sobre pessoa" e "limite do dado" (hoje a diferença é só a cor da borda, e I1 esconde isso).

**I12. Cores da faixa de presença e do ranking de faltas.** Presente = laranja `--s2`, falta = azul `--s1`, licença = cinza; no mesmo painel, o card "Por partido" usa laranja para presença e o ranking usa azul para faltas, então é internamente consistente, mas laranja lê como "atenção" e azul como neutro: o olho vê a faixa de Débora Santana como cheia de alertas quando ela está presente. a10 pedia tom distinto para "quanto maior, pior". *Proposta:* presente `--s3` (verde) ou neutro, falta `--s2`, licença cinza; ranking de faltas em `--s2`. Verificar deuteranopia.

**I13. Funil "Onde as proposições estão hoje" lista situações com 1 proposição sem agrupar.** Em recorte pequeno (vereador: 19 proposições, 7 situações) o card vira uma lista de "1 · 5,3%". Agrupar abaixo de 3% em "outras (n)". E a legenda de `#loc-bars` corta "Supervisão de Gestão de…" (170 px de nome).

### 1.3 Detalhe

- **D1. Concordância e contagem.** "1 vereadores" (KPIs do Resumo com vereador), "0 de 1 vereadores em 2026" (`#vteto2-sub`), "46 gabinetes" (`#custo-tl-sub`; são 43 gabinetes e 46 ocupantes), "49 vereadores" (`#verba-sub` 2026, inclui credor não identificado), "46 vereadores (titulares e suplentes)" ok.
- **D2.** `#vteto-sub` com vereador em 2026: "teto R$ 39.000 a R$ 39.000 por mês".
- **D3. Jargão residual (a8 parcial).** `detailBox` de produtividade: "Vol. ponderado / 12m", "bruto ponderado 27,3"; `valueText` do ranking: "156,0 · 120 brutas" / "120 · 156,0 pond."; botão "Ponderada / 12 meses"; tooltip "7 excluídas".
- **D4. Três totais na aba Produtividade sem conciliação:** KPI 1.987 (vereadores), `#sit-sub`/`#pp-count` 2.038 (com Executivo 32 e Mesa 19), `#prod-note` "Total oficial 2.037". Uma frase: "1.987 de vereadores + 51 de outros autores = 2.038; o resumo oficial conta 2.037".
- **D5.** Glossário, verbete "Folha analítica e sintética": "Em 2026 a Câmara publicou apenas a sintética, via TCM-BA" contradiz o `#cam-note` (consulta de pessoal do TCM-BA, servidor a servidor, jan–jun e ago–set).
- **D6.** `#custo-bars`: nome + partido + cargo da Mesa ("PSDB · Presidência") trunca em 170 px ("Carlos Muniz PSDB · Pres…"); cargo caberia melhor como pílula abaixo do nome ou só no tooltip.
- **D7.** `custo.anual.verba_compensatoria_teto` = 12 × 34.000 (export) ignora dezembro a R$ 39 mil; `tetoUnit` no JS acerta. Alinhar no `export_site.py`.
- **D8.** Credor "Everaldo Bispo" (2026-08, R$ 37.900) sem `vereador_id`: provável suplente ausente de `vereador_dim`/`vereador_alias`.
- **D9.** Produção "ritmo −8% vs 2025" (`refProd`) compara proposições/mês usando `max(meses_exercicio)` como meses do ano; em 2026 (10 meses até outubro) inclui o recesso de julho e janeiro de forma diferente de 2025. Dizer "por mês de mandato" no `sub`.
- **D10.** `selectVer` faz `scrollIntoView` da barra de filtros em desktop; ao clicar em Carlos Muniz no ranking de custo a página pulou (scrollY 796 → 1011) e o leitor perde o ranking em que clicou. Preferir manter a posição e só destacar.
- **D11.** `presStrip`: `<a>` sem `href` (quando não houver ata) não recebe foco de teclado; hoje todas as sessões têm ata, mas quando faltar, usar `<span tabindex=0>`.
- **D12.** Resumo com partido: tag "verba" agregada diz "1 vereadores tiveram 3 ou mais meses…".

### 1.4 O que está bom e deve ser mantido

Estado completo na URL (`#aba-ano-partido-visao-vereador`) e "Copiar link" funcionando (clipboard recebeu `…#resumo-2025-todos-x`, botão vira "Link copiado"); clique no card de partido filtra e atualiza o hash (`#presenca-2025-psd-x`); clique em nome no Resumo leva à aba certa com o vereador; notas de 2026 derivadas do dado (`#custo-note`, `#cam-note` "até 11,3%", "Folha dos gabinetes até set/2026 (consulta de pessoal do TCM-BA)"); funil de situação com o aviso "não é taxa de aprovação" no lugar certo; "Verba ressarcida por mês e o teto" lê bem (saldo claro, excesso escuro, "297,3% do teto" em mar/2025 chama atenção certa); faixa de presença com "maior sequência de faltas: 4" e link para a ata; cargo da Mesa e gabinete no cabeçalho do detalhe; tooltips aparecem ao toque no Chromium (emulação de `mousemove`); sem erro de console; contraste de `--fg-3` ok no claro e no escuro.

### 1.5 Ordem sugerida de correção

1. B5, I1, I2 (CSS, minutos). 2. B2, I3, I4 (JS, menos de uma hora). 3. B1 e B3 (regra de alerta; exige decidir o teto anual por exercício, de preferência no export). 4. B4 (helper único de custo/presença/verba entre Resumo e abas; alias de Everaldo Bispo). 5. I5, I6, I7, I8, I9, I11. 6. I10 (a12) e o resto.

---

## Parte 2 — Especificação do perfil do vereador (b2)

### 2.1 Onde entra: aba própria `#perfil`

**Decisão: aba `Perfil`, quinta na barra de abas, e não painel acima das abas.** Razões:

1. O hash já é `#<aba>-<ano>-<partido>-<visão>-<vereador>`; `#perfil-2025-todos-x-alexandre-aleluia` entra sem mudar `readHash`/`writeHash` além de `TABS`. É o link que o jornalista vai colar.
2. Um painel acima das abas, quando `state.ver` está preenchido, empurraria todo o conteúdo de todas as abas 1.500–2.500 px para baixo (o perfil tem faixa de presença, série de custo, pirâmide, lista de proposições) e duplicaria os `detailBox`, que continuam úteis dentro de cada aba por manterem o ranking de comparação ao lado.
3. No celular, painel fixo acima das abas é inviável; aba é só mais um botão com `overflow-x: auto`.
4. Separa dois gestos: "selecionar" (filtro, destaca no ranking, abre `detailBox`, continua a comparar) e "abrir o perfil" (sair da comparação e ler uma pessoa). Hoje o clique no nome faz o primeiro; o perfil é o segundo.

**Comportamento.**
- O botão `#tab-perfil` existe sempre. Sem `state.ver`, o painel mostra um estado vazio útil: "Escolha um vereador" + a lista dos 43 (nome, partido, cargo na Mesa) em 3 colunas, clicável. Com `state.ver`, o rótulo do botão vira "Perfil · Aleluia" (primeiro sobrenome) para o leitor saber que há alguém selecionado.
- Cada `detailBox` (`#prod-detail`, `#pres-detail`, `#custo-detail`) ganha um link "Ver perfil completo →" (`goTo("perfil", state.ver)`). Nos cards "Maiores/menores" do Resumo, o clique no nome passa a abrir o perfil (hoje abre a aba da métrica); nos rankings e tabelas, o clique continua selecionando.
- Filtro de ano vale (perfil é por ano, 2025 ou 2026); filtro de partido é ignorado no perfil (o `select` continua ativo para trocar de vereador, limitado ao partido, como hoje). Visão Gabinetes/Câmara não se aplica; o hash grava `x`.
- `selectVer` deixa de fazer `scrollIntoView` quando `state.tab === "perfil"`.

### 2.2 Ordem dos blocos (desktop)

| # | bloco | id | altura aprox. |
|---|---|---|---|
| 1 | Cabeçalho | `#pf-head` | 120 px |
| 2 | Seis fatos com posição e comparação | `#pf-facts` | 150 px |
| 3 | Presença sessão a sessão | `#pf-pres` | 200 px |
| 4 | Produção legislativa: composição, onde estão, últimas 10 | `#pf-prod` | 500 px |
| 5 | Gabinete: custo mensal, composição, pirâmide de graus | `#pf-gab` | 320 px |
| 6 | Verba compensatória: mês × teto, categorias, notas (2025) | `#pf-verba` | 320 px |
| 7 | Rodapé do perfil: fontes e limites deste vereador | `#pf-foot` | 90 px |

A ordem segue a pergunta do leitor: quem é → como se compara → foi às sessões? → o que fez → quanto custa → verba. Presença antes de produção porque é a métrica que a imprensa usa e a que tem o visual mais imediato (a faixa).

### 2.3 Cada bloco: dados, chaves, cálculo, texto

Convenções: `v = D.byId[state.ver]`, `ano = state.ano`, `anoK = String(ano)`. "Casa" = todos os vereadores do ano; "partido" = `V(id).partido === v.partido`, comparação só exibida se a bancada tem ≥ 3 vereadores no ano (senão "único(a) do partido" / "bancada de 2"). Posição = `índice + 1` na ordenação da métrica entre os vereadores do ano com dado; mostrar "x de N" com N = tamanho da lista ordenada (não fixar 43: há suplentes).

**Bloco 1 — Cabeçalho (`#pf-head`)**
- `v.nome_parlamentar` (h2), `v.partido`, `v.situacao` (`titular` omitido; `suplente`, `licenciado` como pílula).
- Cargo na Mesa: `v.cargo_mesa[anoK]` (ex.: "Corregedoria", "1ª Vice-Presidência", "Presidência", "Diretoria da Escola do Legislativo"); pílula "cargo na Mesa: …" com `title` "A estrutura do cargo é paga pelo centro de custo do gabinete".
- Gabinete: `v.gabinete_numero` ("gabinete 38"); omitir se nulo (Augusto Vasconcelos, Dr. José Antonio, Tiago Queiroz).
- Idade: calculada de `v.nascimento` (`YYYY-MM-DD`) → "43 anos"; omitir se nulo (9 casos). O dado é do site da Câmara (`v.fonte_url`).
- Licença: se `v.licenca_data`: "licenciado desde dd/mm/aaaa" + (`v.licenca_dias` ? " por n dias" : "") + (`v.suplente_nome` ? ", suplente: " + link : ""). `licenca_data` pode vir como `YYYY-MM` (George Gordinho "2026-05", Julio Santos "2022-04"): formatar "mai/2026" quando tiver 7 caracteres. Datas antigas (David Rios 2014, Maurício Trindade 2013) são ruído do cadastro: só mostrar licença se `licenca_data >= "2025-01"`.
- Suplência: para `v.situacao === "suplente"`, achar o titular com `fold(t.suplente_nome) === fold(v.nome_parlamentar)` (resolve Orlando Palhinha, Carlos Kleber, Tiago Queiroz, Dr. José Antonio, Beca; "Alcindo da Anunciação" não existe no JSON, ignorar) e escrever "suplente de <titular>" com link para o perfil dele; período em exercício vem da grade: primeira e última sessão com status ≠ ausência de registro (`presenca.grade[].n[0]` e `n[n.length-1]` → datas em `presenca.sessoes`).
- Link "Perfil na Câmara" (`v.fonte_url`), botão "Copiar link" já existe na barra.
- Sem foto: não exportada; não hotlinkar o site da Câmara.

**Bloco 2 — Seis fatos (`#pf-facts`)**, grid `auto-fit, minmax(160px, 1fr)`, cada tile = valor grande, linha de posição, linha de comparação.

| fato | valor | fonte | posição (ordenação) | comparação |
|---|---|---|---|---|
| Presença | `taxa_presenca` (`presenca.vereadores`, `ano`), "menos de 10 sessões" se `sem_dado` | presença | desc entre `!sem_dado` | Casa = ΣP/Σ(P+A) do ano; partido idem com membros |
| Faltas | `ausentes` + "de `em_exercicio` sessões" + pílula `alertaPres` | presença | desc (1º = mais faltas) | mediana da Casa |
| Projetos de lei e afins | `n_ple+n_plc+n_pel+n_pdl` (`produtividade.vereadores`) | produtividade | desc | Casa: total/n autores |
| Produção ponderada | `vol_ponderado_12m` + "`n_total` proposições em `meses_exercicio` meses" | produtividade | desc entre `n_total > 0` | média da Casa; partido |
| Custo do gabinete / mês | `media_mensal_custo_observado` (`custo.anual`, `ano`) + "`media_assessores_parlamentares` assessores" | custo | `ranking` já exportado (1 = mais caro); "de `anual.length`" | "Por gabinete" da Casa = média mensal da Casa ÷ 43 (mesmo helper de B4) |
| Verba compensatória no ano | Σ `verba_compensatoria_observada` de `custo.verba` com `vereador_id === v && competencia.startsWith(anoK)` + "`n` meses" | custo | desc | "x% do teto anual em exercício" (ver B1) + pílula "n meses acima do teto mensal" |

Texto do rodapé do bloco: "Posições entre os N vereadores com dado em {ano} (titulares e suplentes). Comparação com o partido só para bancadas de 3 ou mais." Vereador sem linha em `custo.anual` (Carlos Kleber, Dr. José Antonio, Sandro Bahiense, Tiago Queiroz em 2026): tile "Custo do gabinete — sem gabinete próprio na folha; o centro de custo é do titular" com link para o titular.

**Bloco 3 — Presença sessão a sessão (`#pf-pres`)**
- Reutilizar `presStrip(state.ver, ano, sessAll)` (`presenca.grade`: `v`, `ano`, `n[]` = nº da sessão, `s` = string de `P`/`A`/`L`; `presenca.sessoes`: `num_sessao`, `data_sessao`, `ata_url`).
- Acrescentar: (a) lista das faltas com data e link da ata, uma linha por falta, a partir de `presenca.faltas[].sessoes_ausente` cruzado com `sessoes` ("7ª · 11/03/2025 · ata"), recolhida em "ver as 9 faltas" quando > 5; (b) faltas por mês como mini-barras (contagem de `A` agrupada por `data_sessao.slice(0,7)`), 12 células; (c) frase da Casa: "Na Casa, a presença média foi x%; a sessão mais esvaziada foi a nª (dd/mm), com n ausentes" (reuso de `worst` de `renderPres`).
- Licença no período: se houver `L` na grade, "n sessões em licença (de dd/mm a dd/mm)" calculado dos trechos contíguos de `L`.
- Cores conforme I12.

**Bloco 4 — Produção legislativa (`#pf-prod`)**, `.grid-2`.
- Esquerda: barra empilhada única por grupo (`GRUPOS` × `grp(r, g)`) com legenda e números; abaixo, "Excluídas da ponderação: `n_excluidas_regex` (homenagens, nomes de rua, pesar)"; `vol_ponderado` bruto e `vol_ponderado_12m`.
- Direita: funil "Onde estão hoje" reutilizando `renderSituacao` sobre `D.proposicoes.filter(p => p.ano === ano && p.vereador_id === state.ver)` (chaves `situacao`, `localizacao`), agrupando < 3% em "outras", com o aviso "retrato do sistema no dia da coleta; não é aprovação".
- Largura total: "Últimas 10 proposições": `proposicoes` do vereador no ano ordenadas por `movimentado` desc; colunas tipo (ponto colorido `TIPO_GRUPO`), ementa (link `pdf_url` se houver, senão `CONSULTA_URL`), código + "íntegra no DOL de `dol_data`" / "íntegra não localizada", situação, `exclusao` como tag. Botão "Ver todas as n na aba Produtividade" → `goTo("produtividade", state.ver)`.
- Rodapé: "Só o primeiro autor conta (RI art. 179). Proposições da Mesa e do Executivo não aparecem aqui."

**Bloco 5 — Gabinete (`#pf-gab`)**, `.grid-2` + card largo.
- Esquerda: `lineChart` do custo mensal do vereador: `custo.mensal` filtrado por `vereador_id` e `competencia.startsWith(anoK)` (`custo_observado`, `folha_assessores`, `n_assessores`, `subsidio`, `bolsas_estagiarios`, `verba_compensatoria_observada`, `parcial`); tooltip como em `renderCustoGab`; ponto tracejado se `parcial`.
- Direita: composição média mensal (4 barras `SEGC` a partir de `custo.anual` ÷ `meses_com_folha`) com "% do total" e "Folha por assessor = folha_assessores ÷ meses ÷ media_assessores_parlamentares".
- Largo: pirâmide de graus do gabinete: `custo_camara.gab_grau` filtrado por `vereador_id` e `ano`, agregando `n_medio` por faixa (G-05–14, G-15–24, G-25–28, G-29, G-30) e `media_mensal`; barras horizontais "pessoas (média mensal) · R$/mês"; ao lado, a mesma distribuição da Casa em % (2025: G-05–14 308, G-15–24 187, G-25–28 75, G-29 152, G-30 46 de ~769) para comparação, como barra 100% empilhada. Texto: "G-29 (R$ 9.651) e G-30 (R$ 14.976) são os graus mais altos; o grau define o salário (CC-10)". Cargo na Mesa: nota "Gabinete com cargo na Mesa: a estrutura de {cargo} é paga por este centro de custo, o que explica parte do custo" quando `v.cargo_mesa[anoK]`.
- Sem `gab_grau` para o vereador/ano → card oculto e frase "sem folha por gabinete em {ano}".

**Bloco 6 — Verba compensatória (`#pf-verba`)**, `.grid-2` + tabela opcional.
- Esquerda: mês × teto, reaproveitando o bloco `serieV` de `renderCustoGab` com `vb` filtrado pelo vereador (`custo.verba`: `competencia`, `verba_compensatoria_observada`, `verba_compensatoria_teto`, `acima_do_teto`, `n_empenhos`, `n_anulacoes`, `n_fallback_mes_emissao`, `empenhos`); tooltip com os nºs de empenho; `sub` "acima" conforme hoje; nota do art. 22.
- Direita: categorias do ano (`verba_categorias.por_vereador` filtrado por `vereador_id` e `ano`, agregado por `categoria` → descrição em `verba_categorias.categorias[].descricao`, cor por `VGRUPOS`); "n meses com prestação de contas lida"; se vazio, "prestação de contas deste vereador não lida no e-TCM em {ano}".
- Tabela (só 2025, se `verba_categorias.notas` tiver linhas do vereador): reutilizar `renderVerbaNotas` com escopo do vereador (hoje já funciona com `state.ver`).
- Rodapé: "Ressarcido = valor pago ao vereador (empenhos); as notas fiscais não são publicadas, salvo jan–fev/2025."

**Bloco 7 — Rodapé do perfil (`#pf-foot`)**
Lista fixa de 5 linhas, com datas derivadas do dado: "Presença até dd/mm (nª sessão) · Proposições até dd/mm (última movimentação) · Folha do gabinete até mmm/aaaa ({fonte: RH da Câmara | consulta de pessoal do TCM-BA}) · Verba (empenhos) até mmm/aaaa · Categorias (e-TCM) até mmm/aaaa". Mais: "Não há registro público de votos nominais, presença em comissões, discursos nem patrimônio; diárias: nenhuma a este vereador em 2025–26 (exceto Hélio Ferreira, ago/2026)". Link "Como as métricas são calculadas" → `#method`.

### 2.4 O que fica de fora por falta de dado (e onde isso está no backlog)

| item | motivo | referência |
|---|---|---|
| Foto, e-mail, telefones | não exportados em `vereadores.json` (existem no DuckDB `vereadores`); decidir se exporta `foto_url` | export_site |
| Como votou | sem voto nominal | c1 / `BACKLOG §1` |
| Comissões de que participa | sem coleta | c4 |
| Discursos | sem coleta | c3 |
| Taxa de aprovação, tempo de tramitação | só situação do momento | c2 / `BACKLOG §2` |
| Rotatividade e nomes dos assessores | `folha` não exportada ao site; `rotatividade.json` não existe | b5 |
| Fornecedores da verba | notas não publicadas | c5 / `BACKLOG §3` |
| Histórico 2018–2024 | fora do MVP | escopo |
| Sessões não ordinárias | não exportadas | b18 |
| Diárias | nenhuma a vereador (exceto 1) | b16 |

### 2.5 Wireframe — desktop (1120 px)

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ [Ano 2025 ▾] [Partido ▾] [Vereador: Alexandre Aleluia · Novo ▾]  Limpar  Copiar link  Glossário │
├──────────────────────────────────────────────────────────────────────────────────┤
│ Resumo   Produtividade   Presença   Custo   Perfil · Aleluia                       │
├──────────────────────────────────────────────────────────────────────────────────┤
│ #pf-head                                                                          │
│ Alexandre Aleluia         Novo · [Corregedoria da Mesa] · gabinete 38 · 43 anos   │
│ titular · em exercício desde fev/2025            Perfil na Câmara ↗               │
├──────────────────────────────────────────────────────────────────────────────────┤
│ #pf-facts                                                                         │
│ ┌ Presença ──┐┌ Faltas ────┐┌ Projetos de lei ┐┌ Produção pond.┐┌ Custo/mês ──┐┌ Verba no ano ┐│
│ │ 89,0%      ││ 9          ││ 11              ││ 27,3          ││ R$ 216.224  ││ R$ 440.875   ││
│ │ 40º de 43  ││ 2º de 46   ││ 12º de 45       ││ 30º de 45     ││ 2º de 46    ││ 1º de 45     ││
│ │ Casa 96,1% ││ mediana 3  ││ Casa 12,4       ││ Casa 53,4     ││ Casa 165 mil││ 107% do teto ││
│ │ único Novo ││            ││                 ││ 19 em 12 meses││ 15,8 assess.││ [5 meses >teto]│
│ └────────────┘└────────────┘└─────────────────┘└───────────────┘└─────────────┘└──────────────┘│
│ Posições entre os N vereadores com dado em 2025. Comparação com partido só para bancadas ≥ 3.  │
├──────────────────────────────────────────────────────────────────────────────────┤
│ #pf-pres  Presença sessão a sessão · 2025 (86 ordinárias em exercício)            │
│ ■■■■■■□■■■■■■■■□■■□■■■■□■■■□■■■■■■■■□■■■■■■■■■■■■■■■■■■□■■■■□■■■■■■■■■■■■■□■■■■■■■■■■■ │
│ ■ presente  □ falta  ░ licença   clique abre a ata     maior sequência: 2        │
│ ┌ Faltas (9) ──────────────────────┐ ┌ Faltas por mês ────────────────────────┐   │
│ │ 7ª · 11/03 · ata ↗               │ │ fev mar abr mai jun jul ago set out nov dez│  │
│ │ 15ª · 02/04 · ata ↗  … [ver 9]   │ │  0   2   1   1   1   –   0   1   1   1   1 │  │
│ └──────────────────────────────────┘ └──────────────────────────────────────────┘  │
│ Na Casa: presença média 96,1%; sessão mais esvaziada: 35ª (20/05), 12 ausentes.   │
├──────────────────────────────────────────────────────────────────────────────────┤
│ #pf-prod  Produção legislativa · 2025                                             │
│ ┌ Por tipo ──────────────────────────────┐ ┌ Onde estão hoje ───────────────────┐ │
│ │ ███████████▒▒▒▒░░░░▓▓  19 proposições   │ │ Encaminhado      ██████  6  32%     │ │
│ │ ■ Projetos de lei 11 ■ Req. 3 ■ Moções 2│ │ Armazenado       ███     3  16%     │ │
│ │ ■ Homenagens/outros 3                   │ │ Ordem do Dia     ██      2          │ │
│ │ Excluídas da ponderação: 7              │ │ outras (4)       ████    4          │ │
│ │ Ponderado 27,3 · ritmo anual 27,3       │ │ retrato do sistema; não é aprovação │ │
│ └─────────────────────────────────────────┘ └─────────────────────────────────────┘ │
│ Últimas 10 proposições                                   Ver todas as 19 na aba → │
│ ● PLE  Dispõe sobre …                        PLE-123/2025 · íntegra DOL 12/11   Encaminhado │
│ ● REP  Requer …                              REP-45/2025 · íntegra DOL 03/10    Ordem do Dia│
│ …                                                                                 │
├──────────────────────────────────────────────────────────────────────────────────┤
│ #pf-gab  Gabinete · 2025                                                          │
│ ┌ Custo por mês ─────────────────────────┐ ┌ Composição (média mensal) ─────────┐ │
│ │ R$ 300 mil ╭─╮                          │ │ Assessores     ████████ R$ 154.115 71%│ │
│ │ R$ 225 mil ╯  ╰──────────────────────── │ │ Verba          ███      R$ 36.740  17%│ │
│ │ jan fev mar … dez  (○ = mês incompleto) │ │ Subsídio       ██       R$ 26.081  12%│ │
│ └─────────────────────────────────────────┘ │ Estagiários    ▏        R$ 2.193    1%│ │
│                                             │ Folha por assessor: R$ 9.754        │ │
│ ┌ Assessores por grau (média mensal) ─────┐ └─────────────────────────────────────┘ │
│ │ G-30   █            1,0 · R$ 14.560     │  Casa: ▓▓▓▓▓▓▓▓▓▒▒▒▒▒░░▓▓▓▓▓█  (G-05–14 40% …) │
│ │ G-29   ████████████ 12,8 · R$ 122.138   │  Gabinete com cargo na Mesa (Corregedoria): │
│ │ G-25–28 ██          2,0 · R$ 17.417     │  a estrutura do cargo é paga por este centro │
│ │ G-15–24             0                   │  de custo.                                   │
│ │ G-05–14             0                   │                                              │
│ └─────────────────────────────────────────┘                                              │
├──────────────────────────────────────────────────────────────────────────────────┤
│ #pf-verba  Verba compensatória · 2025                                             │
│ ┌ Mês × teto ────────────────────────────┐ ┌ Em que foi gasta (e-TCM, 9 meses) ──┐ │
│ │ fev ██████████░  R$ 32.486  95%         │ │ IX  Consultorias   ████████ R$ 102.100│ │
│ │ mar ██████████████████████ R$ 101.087   │ │ XII Mídia social   ███████  R$ 94.085 │ │
│ │     297% ▲ acima                        │ │ X   Impressos      █████    R$ 60.520 │ │
│ │ … dez ██████████  R$ 34.000 100%        │ │ VII Divulgação     ████     R$ 51.200 │ │
│ │ teto R$ 34 mil (R$ 39 mil em dez)       │ │ …                                     │ │
│ └─────────────────────────────────────────┘ └───────────────────────────────────────┘ │
│ Notas fiscais declaradas (jan–fev/2025): 5 documentos · R$ 14.376   [tabela]      │
├──────────────────────────────────────────────────────────────────────────────────┤
│ #pf-foot  Presença até 17/12/2025 (86ª) · Proposições até 17/12/2025 · Folha até  │
│ dez/2025 (RH da Câmara) · Verba até dez/2025 · Categorias até dez/2025.           │
│ Não há registro público de votos nominais, comissões, discursos nem patrimônio.   │
│ Como as métricas são calculadas ↓                                                 │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 2.6 Wireframe — celular (400 px)

```
┌──────────────────────────────┐
│ 2025 · Todos · Aleluia [edit]│  ← barra compacta (a12); expande ao tocar
├──────────────────────────────┤
│ Resumo Produt. Presença Custo│
│ Perfil·Aleluia ──            │  ← abas roláveis, Perfil selecionada
├──────────────────────────────┤
│ Alexandre Aleluia            │
│ Novo · [Corregedoria] · gab 38│
│ 43 anos · titular            │
│ Perfil na Câmara ↗           │
├──────────────────────────────┤
│ ┌ Presença ──┐┌ Faltas ────┐ │
│ │ 89,0%      ││ 9          │ │
│ │ 40º de 43  ││ 2º de 46   │ │
│ │ Casa 96,1% ││ mediana 3  │ │
│ └────────────┘└────────────┘ │
│ ┌ Projetos ──┐┌ Produção ──┐ │
│ │ 11         ││ 27,3       │ │
│ │ 12º de 45  ││ 30º de 45  │ │
│ └────────────┘└────────────┘ │
│ ┌ Custo/mês ─┐┌ Verba/ano ─┐ │
│ │ R$ 216 mil ││ R$ 441 mil │ │
│ │ 2º de 46   ││ 107% teto  │ │
│ └────────────┘└────────────┘ │
│ posições entre N com dado    │
├──────────────────────────────┤
│ Sessão a sessão · 2025       │
│ ■■■■■■□■■■■■■■■□■■□■■■■□■■■□ │
│ ■■■■■■■■□■■■■■■■■■■■■■■■■■■■ │  ← células 14×14, quebra em linhas
│ ■■■■■■□■■■■□■■■■■■■■■■■■■□■■ │
│ ■ presente □ falta ░ licença │
│ ▸ 9 faltas (datas e atas)    │  ← <details>
│ Faltas por mês               │
│ f m a m j j a s o n d        │
│ 0 2 1 1 1 – 0 1 1 1 1        │
├──────────────────────────────┤
│ Produção · 2025              │
│ ███████████▒▒▒░░▓▓  19       │
│ ■ PL 11 ■ Req 3 ■ Moç 2 ■ 3  │
│ Excluídas 7 · ponderado 27,3 │
│ Onde estão hoje              │
│ Encaminhado  ██████ 6        │
│ Armazenado   ███    3        │
│ outras       ████   4        │
│ Últimas 10 proposições       │
│ ● PLE Dispõe sobre …         │
│   PLE-123/2025 · DOL 12/11   │
│   Encaminhado                │
│ ● REP Requer …               │
│ ▸ Ver todas as 19 →          │
├──────────────────────────────┤
│ Gabinete · 2025              │
│ [linha custo/mês, 12 pts]    │
│ Assessores ████████ 154 mil  │
│ Verba      ███      37 mil   │
│ Subsídio   ██       26 mil   │
│ Estagiários▏         2 mil   │
│ Folha por assessor R$ 9.754  │
│ Por grau                     │
│ G-30    █          1,0       │
│ G-29    ██████████ 12,8      │
│ G-25–28 ██         2,0       │
│ ▸ comparar com a Casa        │
├──────────────────────────────┤
│ Verba · 2025                 │
│ fev ████████░ 32 mil   95%   │
│ mar █████████████ 101 mil ▲  │
│ …                            │
│ Em que foi gasta (9 meses)   │
│ IX Consultorias ████ 102 mil │
│ XII Mídia       ███   94 mil │
│ ▸ notas fiscais (5)          │
├──────────────────────────────┤
│ Até quando: presença 17/12 · │
│ folha dez/25 · verba dez/25  │
│ Sem votos nominais, comissões│
│ discursos, patrimônio.       │
└──────────────────────────────┘
```

No celular: tiles em 2 colunas (`minmax(150px,1fr)`), valores monetários abreviados ("R$ 216 mil") para não cortar (I10b), faixa com células de 14 px e quebra de linha, listas longas em `<details>`, tabela de notas só sob demanda.

### 2.7 Esqueleto de implementação (JS puro, mesmo `index.html`)

1. `TABS = ["resumo", "produtividade", "presenca", "custo", "perfil"]`; `<button role="tab" id="tab-perfil">` e `<section id="panel-perfil">` com os sete `div`s de id acima; `renderTab` chama `renderPerfil()`.
2. Helpers novos: `rankPos(rows, key, dir, id)` → `{pos, n}`; `casaMedia(rows, key)`; `partidoMedia(rows, key, partido)` (retorna `null` se `n < 3`); `tetoAnualExercicio(id, ano)` (ver B1); `fmtBRLk` para "R$ 216 mil" no celular (`matchMedia("(max-width: 600px)")`).
3. Reaproveitar sem copiar: `presStrip`, `lineChart`, `barsChart`, `renderSituacao` (parametrizar o `root`), `renderVerbaNotas`, `GRUPOS`, `SEGC`, `VGRUPOS`, `TIPO_NOME`, `TIPO_GRUPO`, `cargoMesa`, `alertaPres`.
4. `goTo("perfil", id)` nos `topList` do Resumo e link "Ver perfil completo →" em `detailBox`.
5. Estado vazio: `renderPerfil` sem `state.ver` lista `idsAno(ano)` ordenados por nome, 3 colunas, cada um `onclick: () => goTo("perfil", id)`.
6. Testes manuais mínimos: `#perfil-2025-todos-x-alexandre-aleluia`, `#perfil-2026-todos-x-tiago-queiroz` (suplente, sem `custo.anual`, 16 sessões), `#perfil-2026-todos-x-felipe-santana` (licenciado em agosto, suplente Carlos Kleber), `#perfil-2025-todos-x-luiz-carlos` (`sem_dado`, 2 meses de folha), `#perfil-2025-todos-x` (vazio), 400 px.

Dependências do backlog que o perfil absorve: b7 (faixa, já existe), b10 (pirâmide, dado já exportado), b14 (cargo na Mesa, já exportado). Pendências que o perfil deixa evidentes e cabem em `export_site.py`: `teto_anual_exercicio` (B1), `foto_url`/`email` em `vereadores.json`, alias de Everaldo Bispo.
