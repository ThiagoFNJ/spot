# Custo dos gabinetes — 2025

Gerado em 2026-10-28 por `uv run python -m spot.metrics.custo` a partir de `data/silver/spot.duckdb` (tabelas `metrica_custo_gabinete`, `metrica_custo_anual`, `custo_institucional`, `custo_gabinete_ocupante`). Fontes: folha mensal de servidores efetivos e comissionados e relação de estagiários (`https://www.cms.ba.gov.br/transparencia/recursos-humanos`, PDFs em `data/bronze/rh/`), constantes legais em `data/seeds/parametros_custo.csv`, identidade por `data/seeds/vereador_alias.csv` (`fonte = centro_custo`) e `vereador_dim.gabinete_cc_codigo`, exercício mensal pela grade de frequência (`presenca_mvp`).

**Só 2025 tem folha publicada.** A CMS não publicou a folha de 2026 até 2026-10-28 (aba 2026 da página de RH vazia).

## Método (spike §4.3)

- Unidade: gabinete = `centro_custo_codigo` do RH (estável entre titular e suplente), mês de competência.
- `custo_observado = subsídio + folha de assessores parlamentares + folha de outros símbolos no gabinete + bolsas de estagiários + verba compensatória observada`.
- `folha_assessores`: funções `ASSESSOR PARLAMENTAR*` (símbolo CC10, graus G-05 a G-30) = custo do mandato. `folha_outros`: qualquer outro símbolo lotado num centro de custo `GAB. VER.` = estrutura institucional (Mesa). Ver a seção *Mesa* para o que os dados mostram.
- Ocupante do mês: o vereador do rótulo (`GAB. VER. X (SUP. Y)` → X). Para códigos compartilhados por titular licenciado e suplente, prevalece quem teve mais sessões na grade de frequência no mês civil; mês sem sessão (recesso) herda o anterior. O subsídio do mês vai a esse ocupante.
- `verba_compensatoria_observada`: Σ dos empenhos de verba compensatória (`https://cmsalvador.sys.inf.br/ca/gridRegistroEmpenho/`, `data/silver/empenho.csv`, `categoria = verba_compensatoria`) cujo credor (nome civil ou parlamentar, `vereador_alias` com `fonte = empenho`) é o ocupante do gabinete no mês, líquidos de anulações. O mês é o citado no objeto ("MÊS DE X/ANO"); quando o objeto não cita mês (lote de 26/02/2025), vale o mês da emissão. Meses sem nenhum empenho de verba na fonte ficam NULL e aparecem em `componentes_faltantes`.
- `verba_compensatoria_teto` é o **teto legal** da cota mensal (Lei 9.828/2025, R$ 34.000; Lei 9.922/2025, R$ 39.000 a partir de 30/12/2025), mostrado à parte em `custo_com_teto_verba` para comparação. Valores observados acima do teto decorrem do art. 22 da Lei 9.828/2025 (uso de saldo não consumido em meses anteriores, explícito em vários objetos: "com utilização de saldo remanescente").
- `diarias`: NULL (fonte `transparencia/despesas-viagem` ainda não coletada; em 2025 o spike não viu nenhum registro de vereador).
- Centros de custo que não são gabinete (PROJUR, DF, DG, DIREL, Controladoria…) ficam em `custo_institucional`, e a soma gabinetes + institucional é conferida contra a folha mês a mês.

### Constantes legais (`data/seeds/parametros_custo.csv`)

| parâmetro | valor | tipo | vigência | fonte |
|---|---:|---|---|---|
| `subsidio_vereador` | R$ 26.080,98/mês | valor_legal | 2025-02-01 → 2028-12-31 | Lei 9.825/2024, art. 3º (DOM 8.937, 20/12/2024, p. 2) ([pdf](http://www.dom.salvador.ba.gov.br/images/stories/pdf/2024/dezembro/dom-8937-20-12-2024.pdf)) |
| `verba_compensatoria_teto` | R$ 34.000,00/mês | teto | 2025-01-01 → 2025-12-29 | Lei 9.828/2025, art. 13 (DOM 8.943, 03/01/2025) ([pdf](http://www.dom.salvador.ba.gov.br/images/stories/pdf/2025/janeiro/dom-8943-03-01-2025.pdf)) |
| `verba_compensatoria_teto` | R$ 39.000,00/mês | teto | 2025-12-30 → … | Lei 9.922/2025, art. 1º (DOM 9.181, 30/12/2025) ([pdf](https://portal-api.dioly.com.br/uploads/pdfs/3058d71b-ec2f-4444-90e4-1ed6300560e2_dom-9181-30-12-2025_(1).pdf)) |

## Totais mensais

| mês | gab. | servidores | assessores CC10 | folha assessores | folha outros | estag. | bolsas | subsídios | verba obs. | custo observado | teto verba | custo c/ teto |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2025-01 | 43 | 634 | 634 | R$ 3.963.294,37 | R$ 0,00 | n/d | n/d | sem vigência | R$ 140.449,81 (43 gab.) | R$ 4.103.744,18 | R$ 1.462.000,00 | R$ 5.425.294,37 |
| 2025-02 | 43 | 704 | 704 | R$ 4.569.351,54 | R$ 0,00 | n/d | n/d | 43 × = R$ 1.121.482,14 | R$ 972.950,99 (43 gab.) | R$ 6.663.784,67 | R$ 1.462.000,00 | R$ 7.152.833,68 |
| 2025-03 | 43 | 733 | 733 | R$ 4.731.780,40 | R$ 0,00 | n/d | n/d | 43 × = R$ 1.121.482,14 | R$ 1.308.662,86 (43 gab.) | R$ 7.161.925,40 | R$ 1.462.000,00 | R$ 7.315.262,54 |
| 2025-04 | 43 | 715 | 715 | R$ 4.637.375,84 | R$ 0,00 | 77 | R$ 63.886,40 | 43 × = R$ 1.121.482,14 | R$ 839.482,19 (43 gab.) | R$ 6.662.226,57 | R$ 1.462.000,00 | R$ 7.284.744,38 |
| 2025-05 | 43 | 734 | 734 | R$ 4.741.076,53 | R$ 0,00 | 89 | R$ 74.134,24 | 43 × = R$ 1.121.482,14 | R$ 1.472.346,87 (43 gab.) | R$ 7.409.039,78 | R$ 1.462.000,00 | R$ 7.398.692,91 |
| 2025-06 | 43 | 733 | 733 | R$ 4.747.843,59 | R$ 0,00 | 101 | R$ 83.043,20 | 43 × = R$ 1.121.482,14 | R$ 1.302.798,17 (43 gab.) | R$ 7.255.167,10 | R$ 1.462.000,00 | R$ 7.414.368,93 |
| 2025-07 | 43 | 695 | 695 | R$ 4.517.101,62 | R$ 0,00 | 82 | R$ 65.802,40 | 43 × = R$ 1.121.482,14 | R$ 1.318.539,03 (43 gab.) | R$ 7.022.925,19 | R$ 1.462.000,00 | R$ 7.166.386,16 |
| 2025-08 | 43 | 710 | 710 | R$ 4.622.599,52 | R$ 0,00 | 87 | R$ 69.818,40 | 43 × = R$ 1.121.482,14 | R$ 1.306.704,97 (43 gab.) | R$ 7.120.605,03 | R$ 1.462.000,00 | R$ 7.275.900,06 |
| 2025-09 | 43 | 733 | 733 | R$ 4.757.228,61 | R$ 0,00 | 98 | R$ 79.073,60 | 43 × = R$ 1.121.482,14 | R$ 1.285.345,66 (43 gab.) | R$ 7.243.130,01 | R$ 1.462.000,00 | R$ 7.419.784,35 |
| 2025-10 | 43 | 722 | 722 | R$ 4.692.820,98 | R$ 0,00 | 105 | R$ 83.736,00 | 43 × = R$ 1.121.482,14 | R$ 1.263.709,94 (43 gab.) | R$ 7.161.749,06 | R$ 1.462.000,00 | R$ 7.360.039,12 |
| 2025-11 | 43 | 729 | 729 | R$ 4.737.083,05 | R$ 0,00 | 111 | R$ 88.975,20 | 43 × = R$ 1.121.482,14 | R$ 1.302.474,21 (43 gab.) | R$ 7.250.014,60 | R$ 1.462.000,00 | R$ 7.409.540,39 |
| 2025-12 | 43 | 735 | 735 | R$ 4.757.218,72 | R$ 0,00 | n/d | n/d | 43 × = R$ 1.121.482,14 | R$ 1.382.528,59 (43 gab.) | R$ 7.261.229,45 | R$ 1.462.000,00 | R$ 7.340.700,86 |

Ano: folha dos gabinetes R$ 55.474.774,77, subsídios R$ 12.336.303,54 (473 vereador-mês), bolsas R$ 608.469,44 (8 meses publicados), custo observado R$ 82.315.541,04.

### Conferências

- Sanidade 2025-09 (revisor de RH): 43 gabinetes, 733 servidores, R$ 4.757.228,61 — esperado 43 / 733 / R$ 4.757.228,61: **confirmado**. O 42 / 716 / R$ 4.633.426,74 do spike §3.3 perdia o gabinete 10017183 (Marta Rodrigues, rótulo quebrado em duas linhas no PDF).
- Σ subsídio por mês = 43 × R$ 26.080,98 = R$ 1.121.482,14 em todos os 19 meses com vigência: cada gabinete tem exatamente um ocupante por mês (titular ou suplente), logo 43 subsídios/mês mesmo com 3 titulares licenciados. Atenção: o SIGA de 06/2025 (spike §3.3) registrou subsídios pagos = 42 × 26.080,98 — um vereador-mês a menos que este modelo; conciliar com a linha 3.1.90.11.74 quando o SIGA for coletado.
- Meses sem subsídio na métrica: 2025-01 — a Lei 9.825/2024 vige de 1º/02/2025; o valor de janeiro/2025 (19ª legislatura) não foi verificado em fonte primária (spike §8: R$ 24.759,74 vs R$ 23.428,64). Entra como 0 em `custo_observado` e está marcado em `componentes_faltantes`.
- Todas as linhas gabinete × mês têm `vereador_id` resolvido.

## Ranking dos 43 gabinetes por média mensal de custo observado (2025)

| # | centro de custo | ocupante(s) 2025 (meses) | partido | meses | servidores (média) | assessores CC10 (média) | folha assessores (ano) | folha outros | bolsas | subsídio | verba compensatória (obs.) | custo observado (ano) | **média mensal** | média c/ teto verba |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 367063 · PRESIDENCIA - GAB. VER. CARLOS MUNIZ | Carlos Muniz (12m) | PSDB | 12 | 32.3 | 32.3 | R$ 2.536.607,48 | R$ 0,00 | R$ 44.799,20 | R$ 286.890,78 | R$ 151.880,00 | R$ 3.020.177,46 | **R$ 251.681,46** | R$ 273.024,79 |
| 2 | 10039458 · CORRREGEDORIA - GAB. VER. ALEXANDRE ALELUIA | Alexandre Aleluia (12m) | Novo | 12 | 15.8 | 15.8 | R$ 1.849.376,92 | R$ 0,00 | R$ 17.540,80 | R$ 286.890,78 | R$ 440.875,30 | R$ 2.594.683,80 | **R$ 216.223,65** | R$ 213.484,04 |
| 3 | 10017685 · 3ª VICE-PRESIDÊNCIA - GAB. VER. SIDNINHO | Sidninho (12m) | PP | 12 | 20.5 | 20.5 | R$ 1.820.089,00 | R$ 0,00 | R$ 20.680,00 | R$ 286.890,78 | R$ 374.000,00 | R$ 2.501.659,78 | **R$ 208.471,65** | R$ 211.304,98 |
| 4 | 9066037 · GAB. VER. PAULO MAGALHAES | Paulo Magalhães Júnior (12m) | União | 12 | 23.3 | 23.3 | R$ 1.522.228,28 | R$ 0,00 | R$ 28.204,80 | R$ 286.890,78 | R$ 379.576,36 | R$ 2.216.900,22 | **R$ 184.741,69** | R$ 187.110,32 |
| 5 | 10017417 · 1ª VICE-PRESIDENCIA - GAB. VER. MAURICIO TRINDADE | Maurício Trindade (12m) | PP | 12 | 21.3 | 21.3 | R$ 1.555.508,93 | R$ 0,00 | R$ 7.385,60 | R$ 286.890,78 | R$ 355.821,88 | R$ 2.205.607,19 | **R$ 183.800,60** | R$ 188.148,78 |
| 6 | 10017721 · GAB. VER. MARCELLE MORAES | Marcelle Moraes (12m) | União | 12 | 14.8 | 14.8 | R$ 1.482.628,67 | R$ 0,00 | R$ 22.156,80 | R$ 286.890,78 | R$ 408.932,15 | R$ 2.200.608,40 | **R$ 183.384,03** | R$ 183.306,35 |
| 7 | 10680003 · GAB. VER. MARIA ALADILCE | Aladilce Souza (12m) | PCdoB | 12 | 19.6 | 19.6 | R$ 1.499.553,62 | R$ 0,00 | R$ 26.588,80 | R$ 286.890,78 | R$ 365.479,14 | R$ 2.178.512,34 | **R$ 181.542,69** | R$ 185.086,10 |
| 8 | 10679974 · 2ª SECRETARIA - GAB. VER. RICARDO ALMEIDA | Ricardo Almeida (12m) | DC | 12 | 20.6 | 20.6 | R$ 1.429.045,84 | R$ 0,00 | R$ 24.465,60 | R$ 286.890,78 | R$ 415.343,25 | R$ 2.155.745,47 | **R$ 179.645,46** | R$ 179.033,52 |
| 9 | 367157 · 2ª VICE-PRESIDÊNCIA - GAB. VER. EDUARDO SANCHES (DUDA SANCHES) - 0110 | Duda Sanches (12m) | PSDB | 12 | 17.7 | 17.7 | R$ 1.459.996,76 | R$ 0,00 | R$ 5.539,20 | R$ 286.890,78 | R$ 372.585,06 | R$ 2.125.011,80 | **R$ 177.084,32** | R$ 180.035,56 |
| 10 | 367169 · GAB. VER. EVERALDO LOPES BECA (SUP. LUIZ CARLOS DE SOUZA) | Luiz Carlos (2m) → Beca (10m) | Republicanos | 12 | 20.2 | 20.2 | R$ 1.383.783,69 | R$ 0,00 | R$ 42.952,80 | R$ 286.890,78 | R$ 369.753,37 | R$ 2.083.380,64 | **R$ 173.615,05** | R$ 176.802,27 |
| 11 | 367071 · GAB. VER. THEO SENNA | Téo Senna (12m) | PSDB | 12 | 16.2 | 16.2 | R$ 1.452.675,87 | R$ 0,00 | R$ 16.940,80 | R$ 286.890,78 | R$ 267.845,91 | R$ 2.024.353,36 | **R$ 168.696,11** | R$ 180.375,62 |
| 12 | 10679964 · GAB. VER. DANIEL ALVES | Daniel Alves (12m) | PSDB | 12 | 19.3 | 19.3 | R$ 1.429.045,39 | R$ 0,00 | R$ 6.462,40 | R$ 286.890,78 | R$ 288.073,26 | R$ 2.010.471,83 | **R$ 167.539,32** | R$ 177.533,21 |
| 13 | 10017183 · DIRETORIA DA ESCOLA DO LEGISLATIVO - GAB. VER. MARTA RODRIGUES | Marta Rodrigues (12m) | PT | 12 | 16.6 | 16.6 | R$ 1.436.700,48 | R$ 0,00 | R$ 24.049,60 | R$ 286.890,78 | R$ 252.711,24 | R$ 2.000.352,10 | **R$ 166.696,01** | R$ 179.636,74 |
| 14 | 10679962 · GAB. VER. HELIO FERREIRA (SUP. VER. AUGUSTO VASCONCELOS) | Augusto Vasconcelos (2m) → Helio Ferreira (10m) | PCdoB | 12 | 19.8 | 19.8 | R$ 1.356.139,28 | R$ 0,00 | R$ 20.080,00 | R$ 286.890,78 | R$ 335.422,74 | R$ 1.998.532,80 | **R$ 166.544,40** | R$ 172.592,51 |
| 15 | 10679968 · GAB. VER. GEORGE GORDINHO DA FAVELA | George Gordinho da Favela (12m) | PP | 12 | 15.6 | 15.6 | R$ 1.289.934,69 | R$ 0,00 | R$ 7.755,20 | R$ 286.890,78 | R$ 363.468,39 | R$ 1.948.049,06 | **R$ 162.337,42** | R$ 166.048,39 |
| 16 | 10679963 · 3ª SECRETARIA - GAB. VER. CRIS CORREIA | Cris Correia (12m) | PSDB | 12 | 18.3 | 18.3 | R$ 1.315.226,36 | R$ 0,00 | R$ 20.310,40 | R$ 286.890,78 | R$ 318.122,94 | R$ 1.940.550,48 | **R$ 161.712,54** | R$ 169.202,30 |
| 17 | 10680011 · GAB. VER. FELIPE SANTANA | Felipe Santana (12m) | PSD | 12 | 15.9 | 15.9 | R$ 1.302.582,19 | R$ 0,00 | R$ 10.201,60 | R$ 286.890,78 | R$ 338.568,19 | R$ 1.938.242,76 | **R$ 161.520,23** | R$ 167.306,21 |
| 18 | 10679975 · GAB. VER. ROBERTA CAIRES | Roberta Caires (12m) | Republicanos | 12 | 16.6 | 16.6 | R$ 1.250.995,87 | R$ 0,00 | R$ 9.255,20 | R$ 286.890,78 | R$ 366.073,36 | R$ 1.913.215,21 | **R$ 159.434,60** | R$ 162.928,49 |
| 19 | 367159 · 1ª SECRETARIA - GAB. VER. CLAUDIO TINOCO | Claudio Tinoco (12m) | União | 12 | 18.7 | 18.7 | R$ 1.332.532,36 | R$ 0,00 | R$ 6.462,40 | R$ 286.890,78 | R$ 282.323,52 | R$ 1.908.209,06 | **R$ 159.017,42** | R$ 169.490,46 |
| 20 | 10679959 · GAB. VER. FABIO SOUZA | Fábio Souza (12m) | PRD | 12 | 15.8 | 15.8 | R$ 1.255.324,06 | R$ 0,00 | R$ 16.826,40 | R$ 286.890,78 | R$ 345.490,16 | R$ 1.904.531,40 | **R$ 158.710,95** | R$ 163.920,10 |
| 21 | 10680002 · GAB. VER. DAVID RIOS | David Rios (12m) | MDB | 12 | 16.8 | 16.8 | R$ 1.230.364,76 | R$ 0,00 | R$ 9.901,60 | R$ 286.890,78 | R$ 370.376,31 | R$ 1.897.533,45 | **R$ 158.127,79** | R$ 161.263,09 |
| 22 | 367116 · GAB. VER. CLISTENES BISPO - KIKI | Kiki Bispo (12m) | União | 12 | 12.5 | 12.5 | R$ 1.218.383,31 | R$ 0,00 | R$ 17.910,40 | R$ 286.890,78 | R$ 374.000,00 | R$ 1.897.184,49 | **R$ 158.098,71** | R$ 160.932,04 |
| 23 | 10680007 · GAB. VER. RANDERSON LEAL | Randerson Leal (12m) | Podemos | 12 | 12.7 | 12.7 | R$ 1.256.990,01 | R$ 0,00 | R$ 7.385,60 | R$ 286.890,78 | R$ 325.495,77 | R$ 1.876.762,16 | **R$ 156.396,85** | R$ 163.272,20 |
| 24 | 10680005 · GAB. VER. CEZAR LEITE | Cezar Leite (12m) | PL | 12 | 15.6 | 15.6 | R$ 1.224.372,85 | R$ 0,00 | R$ 0,00 | R$ 286.890,78 | R$ 342.675,30 | R$ 1.853.938,93 | **R$ 154.494,91** | R$ 159.938,64 |
| 25 | 10680016 · GAB. VER. ORLANDO PALHINHA (SUPLENTE ALBERTO BRAGA) | Alberto Braga (2m) → Orlando Palhinha (10m) | União | 12 | 16.3 | 16.3 | R$ 1.181.440,49 | R$ 0,00 | R$ 11.494,40 | R$ 286.890,78 | R$ 373.650,00 | R$ 1.853.475,67 | **R$ 154.456,31** | R$ 157.318,81 |
| 26 | 10680012 · GAB. VER. RODRIGO AMARAL | Rodrigo Amaral (12m) | PSDB | 12 | 16.0 | 16.0 | R$ 1.171.457,88 | R$ 0,00 | R$ 4.362,40 | R$ 286.890,78 | R$ 371.885,82 | R$ 1.834.596,88 | **R$ 152.883,07** | R$ 155.892,59 |
| 27 | 10017896 · GAB. VER. IREUDA SILVA | Ireuda Silva (12m) | Republicanos | 12 | 13.8 | 13.8 | R$ 1.124.200,13 | R$ 0,00 | R$ 60.793,44 | R$ 286.890,78 | R$ 360.812,81 | R$ 1.832.697,16 | **R$ 152.724,76** | R$ 156.657,03 |
| 28 | 10679965 · GAB. VER. DEBORA SANTANA | Débora Santana (12m) | PSDB | 12 | 11.8 | 11.8 | R$ 1.129.526,61 | R$ 0,00 | R$ 12.924,80 | R$ 286.890,78 | R$ 401.094,83 | R$ 1.830.437,02 | **R$ 152.536,42** | R$ 153.111,85 |
| 29 | 10679960 · OUVIDORIA SUBSTITUTA - GAB. VER. ANDERSON NINHO | Anderson Ninho (12m) | PSDB | 12 | 15.2 | 15.2 | R$ 1.126.195,93 | R$ 0,00 | R$ 17.910,40 | R$ 286.890,78 | R$ 358.000,00 | R$ 1.788.997,11 | **R$ 149.083,09** | R$ 153.249,76 |
| 30 | 10680001 · GAB. VER. ALEX ALEMAO | Alex Alemão (12m) | DC | 12 | 16.6 | 16.6 | R$ 1.133.184,96 | R$ 0,00 | R$ 0,00 | R$ 286.890,78 | R$ 365.496,46 | R$ 1.785.572,20 | **R$ 148.797,68** | R$ 152.339,64 |
| 31 | 10680004 · GAB. VER. OMAR GORDILHO | Omarzinho Gordilho (12m) | PDT | 12 | 10.1 | 10.1 | R$ 1.110.557,02 | R$ 0,00 | R$ 923,20 | R$ 286.890,78 | R$ 386.764,45 | R$ 1.785.135,45 | **R$ 148.761,29** | R$ 150.530,92 |
| 32 | 10680000 · GAB. VER. ISABELA SOUSA | Isabela Sousa (12m) | Cidadania | 12 | 16.8 | 16.8 | R$ 1.151.820,48 | R$ 0,00 | R$ 13.087,20 | R$ 286.890,78 | R$ 326.002,39 | R$ 1.777.800,85 | **R$ 148.150,07** | R$ 154.983,20 |
| 33 | 10679961 · GAB. VER. ANDRE FRAGA | André Fraga (12m) | PV | 12 | 15.6 | 15.6 | R$ 1.227.035,42 | R$ 0,00 | R$ 19.387,20 | R$ 286.890,78 | R$ 236.210,45 | R$ 1.769.523,85 | **R$ 147.460,32** | R$ 161.776,12 |
| 34 | 10680015 · 4ª SECRETARIA - GAB. VER. KEL TORRES | Kel Torres (12m) | Republicanos | 12 | 20.0 | 20.0 | R$ 980.396,93 | R$ 0,00 | R$ 9.232,00 | R$ 286.890,78 | R$ 372.627,86 | R$ 1.649.147,57 | **R$ 137.428,96** | R$ 140.376,64 |
| 35 | 10680008 · GAB. VER. JORGE ARAUJO REPORTER | Jorge Araújo (12m) | PP | 12 | 9.8 | 9.8 | R$ 1.012.378,93 | R$ 0,00 | R$ 0,00 | R$ 286.890,78 | R$ 349.709,04 | R$ 1.648.978,75 | **R$ 137.414,90** | R$ 142.272,48 |
| 36 | 10680006 · GAB. VER. JOAO CLAUDIO BACELAR | João Cláudio Bacelar (12m) | Podemos | 12 | 14.8 | 14.8 | R$ 1.029.705,67 | R$ 0,00 | R$ 2.492,80 | R$ 286.890,78 | R$ 325.156,29 | R$ 1.644.245,54 | **R$ 137.020,46** | R$ 143.924,10 |
| 37 | 367171 · GAB. VER. SILVIO HUMBERTO - 0124 | Sílvio Humberto (12m) | PSB | 12 | 16.9 | 16.9 | R$ 1.253.325,86 | R$ 0,00 | R$ 10.524,80 | R$ 286.890,78 | R$ 58.550,35 | R$ 1.609.291,79 | **R$ 134.107,65** | R$ 163.228,45 |
| 38 | 10680013 · GAB. VER. ELIETE PARAGUASSU | Eliete Paraguassu (12m) | PSOL | 12 | 14.1 | 14.1 | R$ 1.030.682,97 | R$ 0,00 | R$ 0,00 | R$ 286.890,78 | R$ 287.434,25 | R$ 1.605.008,00 | **R$ 133.750,67** | R$ 143.797,81 |
| 39 | 10680014 · GAB. VER. PROFESSOR HAMILTON | Hamilton Assis (12m) | PSOL | 12 | 11.9 | 11.9 | R$ 907.878,92 | R$ 0,00 | R$ 9.901,60 | R$ 286.890,78 | R$ 362.895,48 | R$ 1.567.566,78 | **R$ 130.630,57** | R$ 134.389,28 |
| 40 | 10680010 · GAB. VER. KENIO REZENDE | Kênio Rezende (12m) | PRD | 12 | 14.4 | 14.4 | R$ 982.426,38 | R$ 0,00 | R$ 1.546,40 | R$ 286.890,78 | R$ 293.155,86 | R$ 1.564.019,42 | **R$ 130.334,95** | R$ 139.905,30 |
| 41 | 10680017 · GAB. VER. MARCELO GUIMARAES NETO | Marcelo Guimarães Neto (12m) | União | 12 | 13.9 | 13.9 | R$ 958.464,13 | R$ 0,00 | R$ 0,00 | R$ 286.890,78 | R$ 278.024,54 | R$ 1.523.379,45 | **R$ 126.948,29** | R$ 137.779,58 |
| 42 | 10679970 · GAB. VER. JÚLIO SANTOS | Julio Santos (12m) | Republicanos | 12 | 16.8 | 16.8 | R$ 1.123.865,16 | R$ 0,00 | R$ 19.110,40 | R$ 286.890,78 | R$ 58.419,95 | R$ 1.488.286,29 | **R$ 124.023,86** | R$ 153.155,53 |
| 43 | 10680009 · GAB. VER. SANDRO FILHO | Sandro Filho (12m) | PP | 12 | 14.3 | 14.3 | R$ 950.144,23 | R$ 0,00 | R$ 923,20 | R$ 286.890,78 | R$ 125.208,86 | R$ 1.363.167,07 | **R$ 113.597,26** | R$ 137.163,18 |

Leitura: a média mensal divide o custo observado do ano pelos meses com folha (12). 1 mês(es) entra(m) sem subsídio e só 8 têm estagiários, para todos os gabinetes igualmente — o ranking não muda, o nível fica subestimado em ~R$ 2.173,41/mês (subsídio faltante ÷ meses) e pelas bolsas não publicadas.

## Verba compensatória observada (empenhos)

**2025** — por competência (mês citado no objeto; sem mês → mês da emissão):

| competência | empenhos | anulações | vereadores | sem alias | Σ verba | mínimo | máximo | teto | acima do teto | atribuídos pelo mês da emissão |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2025-01 | 9 | 0 | 8 | 0 | R$ 140.449,81 | R$ 2.832,77 | R$ 40.280,02 | R$ 34.000,00 | 1 | 0 |
| 2025-02 | 53 | 0 | 39 | 0 | R$ 1.002.435,82 | R$ 1.895,90 | R$ 59.651,12 | R$ 34.000,00 | 2 | 16 |
| 2025-03 | 47 | 0 | 41 | 0 | R$ 1.308.662,86 | R$ 1.603,13 | R$ 101.087,36 | R$ 34.000,00 | 6 | 0 |
| 2025-04 | 43 | 0 | 42 | 0 | R$ 839.482,19 | R$ 1.495,31 | R$ 39.597,37 | R$ 34.000,00 | 2 | 0 |
| 2025-05 | 44 | 1 | 42 | 0 | R$ 1.472.346,87 | R$ 1.509,80 | R$ 52.274,38 | R$ 34.000,00 | 25 | 0 |
| 2025-06 | 42 | 0 | 42 | 0 | R$ 1.302.798,17 | R$ 4.078,30 | R$ 44.594,11 | R$ 34.000,00 | 13 | 0 |
| 2025-07 | 42 | 0 | 42 | 0 | R$ 1.318.539,03 | R$ 4.846,25 | R$ 42.919,10 | R$ 34.000,00 | 14 | 0 |
| 2025-08 | 42 | 0 | 42 | 0 | R$ 1.306.704,97 | R$ 4.835,72 | R$ 44.820,36 | R$ 34.000,00 | 10 | 0 |
| 2025-09 | 42 | 0 | 42 | 0 | R$ 1.285.345,66 | R$ 4.848,40 | R$ 39.453,96 | R$ 34.000,00 | 5 | 0 |
| 2025-10 | 41 | 0 | 38 | 0 | R$ 1.263.709,94 | R$ 5.408,15 | R$ 68.000,00 | R$ 34.000,00 | 8 | 0 |
| 2025-11 | 42 | 0 | 42 | 0 | R$ 1.302.474,21 | R$ 5.085,91 | R$ 43.953,06 | R$ 34.000,00 | 8 | 0 |
| 2025-12 | 44 | 0 | 43 | 0 | R$ 1.382.528,59 | R$ 4.434,73 | R$ 60.600,00 | R$ 34.000,00 | 12 | 0 |

Σ 2025: R$ 13.925.478,12 em 491 empenhos.

**2026** — por competência (mês citado no objeto; sem mês → mês da emissão):

| competência | empenhos | anulações | vereadores | sem alias | Σ verba | mínimo | máximo | teto | acima do teto | atribuídos pelo mês da emissão |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026-01 | 36 | 0 | 36 | 0 | R$ 1.167.164,21 | R$ 8.380,00 | R$ 39.000,00 | R$ 39.000,00 | 0 | 0 |
| 2026-02 | 43 | 0 | 43 | 0 | R$ 1.418.846,65 | R$ 9.180,00 | R$ 42.060,00 | R$ 39.000,00 | 5 | 0 |
| 2026-03 | 43 | 0 | 42 | 0 | R$ 1.514.022,15 | R$ 7.880,00 | R$ 71.525,00 | R$ 39.000,00 | 7 | 0 |
| 2026-04 | 43 | 0 | 42 | 0 | R$ 1.482.213,90 | R$ 7.880,00 | R$ 64.869,36 | R$ 39.000,00 | 9 | 0 |
| 2026-05 | 45 | 1 | 43 | 0 | R$ 1.522.399,97 | R$ 7.880,00 | R$ 46.022,82 | R$ 39.000,00 | 8 | 0 |
| 2026-06 | 38 | 0 | 38 | 0 | R$ 1.249.057,09 | R$ 5.880,00 | R$ 41.800,00 | R$ 39.000,00 | 4 | 0 |
| 2026-07 | 36 | 0 | 36 | 0 | R$ 1.165.002,10 | R$ 13.379,08 | R$ 43.700,00 | R$ 39.000,00 | 3 | 0 |
| 2026-08 | 41 | 0 | 39 | 1 | R$ 1.336.323,58 | R$ 13.499,90 | R$ 51.300,00 | R$ 39.000,00 | 3 | 0 |
| 2026-09 | 41 | 0 | 41 | 0 | R$ 1.338.855,47 | R$ 13.600,00 | R$ 45.948,00 | R$ 39.000,00 | 2 | 0 |

Σ 2026: R$ 12.193.885,12 em 366 empenhos.

- Conciliação SIGA 2025-06 (3.3.90.93.01 Indenizações = R$ 1.430.000,00): Σ empenhos de verba emitidos no mês = R$ 1.433.241,28 (100%); Σ por competência = R$ 1.302.798,17 (91%). O elemento inclui outras indenizações, e empenho ≠ liquidação: ordem de grandeza, não igualdade.
- Conciliação SIGA 2025-11 (3.3.90.93.01 Indenizações = R$ 1.539.369,63): Σ empenhos de verba emitidos no mês = R$ 1.460.200,36 (95%); Σ por competência = R$ 1.302.474,21 (85%). O elemento inclui outras indenizações, e empenho ≠ liquidação: ordem de grandeza, não igualdade.
- Credores de verba **sem alias** (fora do custo por gabinete): `Everaldo Bispo` (1 empenho(s), 2026-08, R$ 37.900,00)

## Gabinetes da Mesa e cargos institucionais no rótulo

O rótulo do RH prefixa o cargo da Mesa (Presidência, Vice-Presidências, Secretarias, Corregedoria) ou a função institucional (Ouvidoria Substituta, Diretoria da Escola do Legislativo) ao gabinete. Divisão por função:

| centro de custo | cargo no rótulo | vereador | servidores (média) | assessores CC10 (média) | folha assessores (mandato) | folha outros (estrutura) |
|---|---|---|---:|---:|---:|---:|
| 367063 | PRESIDENCIA | Carlos Muniz | 32.3 | 32.3 | R$ 2.536.607,48 | R$ 0,00 |
| 10039458 | CORRREGEDORIA | Alexandre Aleluia | 15.8 | 15.8 | R$ 1.849.376,92 | R$ 0,00 |
| 10017685 | 3ª VICE-PRESIDÊNCIA | Sidninho | 20.5 | 20.5 | R$ 1.820.089,00 | R$ 0,00 |
| 10017417 | 1ª VICE-PRESIDENCIA | Maurício Trindade | 21.3 | 21.3 | R$ 1.555.508,93 | R$ 0,00 |
| 367157 | 2ª VICE-PRESIDÊNCIA | Duda Sanches | 17.7 | 17.7 | R$ 1.459.996,76 | R$ 0,00 |
| 10017183 | DIRETORIA DA ESCOLA DO LEGISLATIVO | Marta Rodrigues | 16.6 | 16.6 | R$ 1.436.700,48 | R$ 0,00 |
| 10679974 | 2ª SECRETARIA | Ricardo Almeida | 20.6 | 20.6 | R$ 1.429.045,84 | R$ 0,00 |
| 367159 | 1ª SECRETARIA | Claudio Tinoco | 18.7 | 18.7 | R$ 1.332.532,36 | R$ 0,00 |
| 10679963 | 3ª SECRETARIA | Cris Correia | 18.3 | 18.3 | R$ 1.315.226,36 | R$ 0,00 |
| 10679960 | OUVIDORIA SUBSTITUTA | Anderson Ninho | 15.2 | 15.2 | R$ 1.126.195,93 | R$ 0,00 |
| 10680015 | 4ª SECRETARIA | Kel Torres | 20.0 | 20.0 | R$ 980.396,93 | R$ 0,00 |

Estrutura institucional da Presidência fora do gabinete parlamentar: CC `367177 - GABINETE DA PRESIDENCIA - 00831` (símbolos CC-40/50/70/80/90: secretários de gabinete, secretário particular, assessor especial, chefe de gabinete) — 30.7 servidores/mês, R$ 4.950.411,40 em 12 meses (R$ 412.534,28/mês). Está em `custo_institucional`, não no custo do mandato de Carlos Muniz.

**Achado**: em 2025 **todos** os servidores lotados nos 43 centros de custo `GAB. VER.` são `ASSESSOR PARLAMENTAR*` (CC10) — `folha_outros` = 0 em todos os gabinetes, inclusive os da Mesa. Os cargos CC-40/50/70/80/90 da estrutura da Presidência estão num centro de custo próprio (`367177 - GABINETE DA PRESIDENCIA - 00831`), e os das Secretarias/Vice-Presidências não aparecem como lotação separada no PDF. A divisão mandato/estrutura por função fica implementada e vazia; o que diferencia os gabinetes da Mesa é o **número de assessores** (PRESIDENCIA: 32.3 em média).

## Suplências: atribuição do mês ao ocupante

Os rótulos `(SUP. ...)` são idênticos em todos os 12 PDFs de 2025, inclusive janeiro e fevereiro, quando os titulares ainda estavam em exercício (Augusto Vasconcelos até 18/02, Luiz Carlos e Alberto Braga até 19/02 pela grade; licenças em 24/02/2025). O rótulo reflete o estado atual do cadastro, não o do mês — por isso a atribuição usa a grade.

| centro de custo | rótulo do RH | atribuição mês a mês (fonte) |
|---|---|---|
| 367169 | GAB. VER. EVERALDO LOPES BECA (SUP. LUIZ CARLOS DE SOUZA) | 01: Luiz Carlos (grade); 02: Luiz Carlos (grade); 03: Beca (grade); 04: Beca (grade); 05: Beca (grade); 06: Beca (grade); 07: Beca (grade_mes_anterior); 08: Beca (grade); 09: Beca (grade); 10: Beca (grade); 11: Beca (grade); 12: Beca (grade) |
| 10679962 | GAB. VER. HELIO FERREIRA (SUP. VER. AUGUSTO VASCONCELOS) | 01: Augusto Vasconcelos (grade); 02: Augusto Vasconcelos (grade); 03: Helio Ferreira (grade); 04: Helio Ferreira (grade); 05: Helio Ferreira (grade); 06: Helio Ferreira (grade); 07: Helio Ferreira (grade_mes_anterior); 08: Helio Ferreira (grade); 09: Helio Ferreira (grade); 10: Helio Ferreira (grade); 11: Helio Ferreira (grade); 12: Helio Ferreira (grade) |
| 10680016 | GAB. VER. ORLANDO PALHINHA (SUPLENTE ALBERTO BRAGA) | 01: Alberto Braga (grade); 02: Alberto Braga (grade); 03: Orlando Palhinha (grade); 04: Orlando Palhinha (grade); 05: Orlando Palhinha (grade); 06: Orlando Palhinha (grade); 07: Orlando Palhinha (grade_mes_anterior); 08: Orlando Palhinha (grade); 09: Orlando Palhinha (grade); 10: Orlando Palhinha (grade); 11: Orlando Palhinha (grade); 12: Orlando Palhinha (grade) |

## 'Total de Proventos' é remuneração efetiva do mês? (pergunta aberta do spike §4.3/§8)

- **2025-11 × 2025-12 por matrícula**: 989 matrículas presentes nos dois meses; 897 (90.7%) com proventos idênticos, 34 maiores em dezembro, 58 menores; mediana da razão dez/nov = 1.0; matrículas com razão ≈ 2 (13º integral somado): **1**.
- Conclusão: **dezembro não traz 13º** (1 caso(s) isolado(s) de valor dobrado em 989). 'Total de Proventos' é a remuneração bruta mensal do mês de competência, sem 13º nem adicionais sazonais; a série anual **não precisa de deflator de 13º**, mas o custo por gabinete **subestima** o encargo real (13º, férias e INSS/RPPS patronal só aparecem agregados no SIGA).
  - `ASSESSOR PARLAMENTAR-G-29 CC10` em 2025-09: R$ 9.651,25 para 152 servidores
  - `ASSESSOR PARLAMENTAR-G-29 CC10` em 2025-11: R$ 9.651,25 para 145 servidores
  - `ASSESSOR PARLAMENTAR-G-29 CC10` em 2025-12: R$ 9.651,25 para 146 servidores (valor de tabela, igual em todos os meses de comparação)

Variação mês a mês (matrículas presentes em dois meses consecutivos):

| mês | pares | iguais | subiu | caiu | mediana razão |
|---|---:|---:|---:|---:|---:|
| 2025-02 | 897 | 574 | 178 | 145 | 1.0 |
| 2025-03 | 970 | 863 | 46 | 61 | 1.0 |
| 2025-04 | 950 | 730 | 184 | 36 | 1.0 |
| 2025-05 | 982 | 823 | 112 | 47 | 1.0 |
| 2025-06 | 990 | 771 | 193 | 26 | 1.0 |
| 2025-07 | 945 | 760 | 30 | 155 | 1.0 |
| 2025-08 | 961 | 864 | 46 | 51 | 1.0 |
| 2025-09 | 975 | 877 | 50 | 48 | 1.0 |
| 2025-10 | 976 | 883 | 45 | 48 | 1.0 |
| 2025-11 | 985 | 895 | 47 | 43 | 1.0 |
| 2025-12 | 989 | 897 | 34 | 58 | 1.0 |

- comissionado: 542 de 8731 pares mês-a-mês mudaram de valor (6%).
- estatutário: 1141 de 1889 pares mês-a-mês mudaram de valor (60%).
- Leitura: comissionados (CC10) recebem valor de tabela por grau e só variam na admissão/saída (mês proporcional) ou mudança de grau; estatutários variam todo mês (vantagens pessoais, gratificações), o que confirma que o campo é a remuneração efetiva do mês e não o vencimento-base.

## Estagiários

- PDFs de estagiários disponíveis para 8 meses (2025-04 a 2025-11): a página de RH só lista estagiários a partir de abril/2025 e o PDF de dezembro/2025 não está no bronze. Nos meses sem PDF, `n_estagiarios`/`bolsas_estagiarios` são NULL (e não 0) e `componentes_faltantes` registra `estagiarios`.
- Bolsas: R$ 623,20 (nível médio) e R$ 923,20 (nível superior); 2 casos de valor dobrado em mai/2025 (retroativo de admissão).

## Custo institucional (fora dos gabinetes)

- `estagiarios`: 28 centros de custo, 422 linhas-mês, R$ 355.713,44 em 8 meses.
- `folha`: 73 centros de custo, 3193 linhas-mês, R$ 49.289.914,15 em 12 meses.

| centro de custo | servidores (média) | total 2025 | média mensal |
|---|---:|---:|---:|
| 367177 · GABINETE DA PRESIDENCIA - 00831 | 30.7 | R$ 4.950.411,40 | R$ 412.534,28 |
| 367074 · PROCURADORIA JURIDICA - 0007 | 9.0 | R$ 2.112.792,81 | R$ 176.066,07 |
| 10679978 · DIRETORIA GERAL | 8.3 | R$ 1.952.131,06 | R$ 162.677,59 |
| 367075 · DIRETORIA LEGISLATIVA - 0003 | 7.0 | R$ 1.923.385,14 | R$ 160.282,09 |
| 367082 · DG - SGP - CEDASB - SUPERVISÃO DE ATENÇÃO A SAÚDE E QUALIDADE DE VIDA | 7.5 | R$ 1.875.035,98 | R$ 156.253,00 |
| 367113 · DIREL - C. COM. - SUPERVISÃO DE TRAMITAÇÃO - 0074 | 9.3 | R$ 1.831.132,67 | R$ 152.594,39 |
| 367028 · DIREL - COORDENAÇÃO DE TAQUIGRAFIA - 0010.2 | 8.0 | R$ 1.724.283,91 | R$ 143.690,33 |
| 367035 · DIRETORIA DE COMUNICAÇÃO - 0015 | 15.7 | R$ 1.442.518,75 | R$ 120.209,90 |
| 367129 · CONTROLADORIA - 0089 | 6.9 | R$ 1.287.292,36 | R$ 107.274,36 |
| 10679990 · DIRETORIA FINANCEIRA | 5.8 | R$ 1.228.905,68 | R$ 102.408,81 |
| 367084 · DG - SGP - CGP - SUPERVISÃO DE ADMINISTRAÇÃO DE PESSOAL | 6.0 | R$ 1.167.932,78 | R$ 97.327,73 |
| 367031 · DIREL - COORDENAÇÃO DE COMISSÕES - 0012 | 5.0 | R$ 1.080.756,13 | R$ 90.063,01 |

## O que ainda falta

- **Verba compensatória — liquidação/pagamento**: o modelo usa o valor **empenhado** (`gridRegistroEmpenho`); `gridRegistroDespesa` (92 mil linhas, fases liquidado/pago, join pelo número do empenho) não foi coletada.
- **Verba compensatória — meses sem empenho**: janeiro/2025 só tem 9 empenhos (emitidos em março) e o lote de 26/02/2025 não cita mês; a competência cai no mês da emissão (fevereiro).
- **Diárias**: `transparencia/despesas-viagem` não coletada (14 registros em 2025, nenhum vereador, segundo o spike).
- **Encargos patronais, 13º e férias**: só agregados no SIGA (prestação de contas mensal) — exibir como rodapé institucional, não por gabinete.
- **Subsídio de janeiro/2025**: sem fonte primária (ver Conferências).
- **Folha de 2026**: não publicada pela CMS; a métrica para 2026 depende dessa publicação (ou de pedido LAI).
- **Estagiários dez/2025 e jan–mar/2025**: sem PDF.
- **Conciliação com o SIGA**: Σ subsídios (43 × 26.080,98) vs linha 3.1.90.11.74 (SIGA 06/2025 mostrou 42 ×); Σ folha de gabinetes vs vencimentos de cargos em comissão; Σ verba vs 3.3.90.93.01 (ver seção acima).

## Centros de custo `GAB. VER.` sem alias

Nenhum: todos os pares (código, rótulo) `GAB. VER.` de 2025 na folha e nos estagiários têm alias `fonte = centro_custo` (`alias = "<código> - <rótulo>"`).
