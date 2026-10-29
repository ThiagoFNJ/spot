# Verba compensatória por categoria de despesa (e-TCM)

Gerado em 2026-10-28 por `spot.metrics.verba` a partir de `verba_processo`/`verba_processo_item` (PDFs `PP <n> - VC - <nome>.pdf` da consulta pública do e-TCM; ver `docs/etcm.md`). Categorias = incisos I..XV do art. 14 da Lei 9.828/2025 (`data/seeds/verba_categorias.csv`).

## Cobertura

| ano (competência) | processos | vereadores | competências | de | até | prestações lidas | alta | média | baixa | resumo | detalhamento | sem tabela | Σ declarado |
|---|---:|---:|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2025 | 485 | 45 | 12 | 2025-01 | 2025-12 | 2025-02, 2025-03, 2025-04, 2025-05, 2025-06, 2025-07, 2025-08, 2025-09, 2025-10, 2025-11, 2025-12, 2026-03 | 230 | 193 | 62 | 337 | 55 | 93 | R$ 13.426.877,46 |
| 2026 | 296 | 47 | 7 | 2026-01 | 2026-07 | 2025-05, 2026-02, 2026-03, 2026-04, 2026-05, 2026-06, 2026-07, 2026-08 | 154 | 93 | 49 | 294 | 0 | 2 | R$ 9.834.004,49 |

| competência | processos | vereadores | Σ declarado | Σ incisos | confiança baixa | página de categorias |
|---|---:|---:|---:|---:|---:|---|
| 2025-01 | 23 | 23 | R$ 386.649,94 | R$ 386.649,94 | 0 | detalhamento |
| 2025-02 | 39 | 36 | R$ 784.013,51 | R$ 687.697,22 | 1 | detalhamento/nenhum/resumo |
| 2025-03 | 42 | 41 | R$ 1.141.282,06 | R$ 0,00 | 1 | nenhum |
| 2025-04 | 41 | 41 | R$ 705.442,44 | R$ 0,00 | 4 | nenhum |
| 2025-05 | 41 | 41 | R$ 1.298.757,54 | R$ 1.485.811,58 | 13 | nenhum/resumo |
| 2025-06 | 43 | 42 | R$ 1.235.916,32 | R$ 1.149.121,95 | 7 | nenhum/resumo |
| 2025-07 | 42 | 42 | R$ 1.318.662,28 | R$ 1.319.531,82 | 7 | resumo |
| 2025-08 | 42 | 42 | R$ 1.273.049,80 | R$ 1.226.408,97 | 8 | resumo |
| 2025-09 | 43 | 43 | R$ 1.283.114,48 | R$ 1.274.641,30 | 7 | nenhum/resumo |
| 2025-10 | 43 | 43 | R$ 1.312.979,21 | R$ 1.317.620,20 | 4 | nenhum/resumo |
| 2025-11 | 43 | 43 | R$ 1.334.781,30 | R$ 1.239.259,88 | 6 | nenhum/resumo |
| 2025-12 | 43 | 43 | R$ 1.352.228,58 | R$ 1.292.978,58 | 4 | resumo |
| 2026-01 | 42 | 42 | R$ 1.322.792,51 | R$ 1.334.240,88 | 7 | resumo |
| 2026-02 | 39 | 39 | R$ 1.287.342,89 | R$ 1.254.217,75 | 10 | resumo |
| 2026-03 | 43 | 43 | R$ 1.506.376,68 | R$ 1.474.606,53 | 5 | resumo |
| 2026-04 | 44 | 43 | R$ 1.440.216,57 | R$ 1.704.749,24 | 9 | nenhum/resumo |
| 2026-05 | 43 | 43 | R$ 1.522.575,85 | R$ 1.493.595,85 | 6 | resumo |
| 2026-06 | 43 | 43 | R$ 1.373.657,89 | R$ 1.381.627,99 | 7 | nenhum/resumo |
| 2026-07 | 42 | 42 | R$ 1.381.042,10 | R$ 1.395.670,04 | 5 | resumo |

A Câmara tem 43 cadeiras: um mês com menos processos que isso tem PDFs ainda não baixados/lidos ou vereadores sem pedido.
Página de categorias: `resumo` = tabela dos 15 incisos (prestações de jun/2025 em diante); `detalhamento` = formulário antigo com uma linha por documento fiscal (nº e data da nota, glosa; prestações de fev–mar/2025); `nenhum` = o processo só traz o total autorizado pela Controladoria (prestações de abr–mai/2025) e não entra nas tabelas por categoria.

### Notas fiscais declaradas (formulário antigo)

| competência | notas | vereadores | com nº de documento | glosadas | Σ glosa | Σ compensado |
|---|---:|---:|---:|---:|---:|---:|
| 2025-01 | 130 | 23 | 71 | 5 | R$ 4.330,13 | R$ 405.499,94 |
| 2025-02 | 280 | 32 | 242 | 3 | R$ 11.628,94 | R$ 619.497,22 |

Tabela completa em `metrica_verba_nf` (sem fornecedor: o formulário não o traz).

## Por categoria

### Casa — 2025

| inciso | categoria | total | % | vereadores | processos | meses |
|---|---|---:|---:|---:|---:|---:|
| I | Softwares e aplicativos (aquisição e locação) | R$ 131.969,78 | 1.2 | 14 | 78 | 10 |
| II | Locação de móveis/equipamentos, manutenção e serviços de TI | R$ 8.922,90 | 0.1 | 5 | 17 | 10 |
| IV | Telefonia celular | R$ 9.501,87 | 0.1 | 4 | 23 | 10 |
| VI | Correspondência e mensagens eletrônicas | R$ 13.600,00 | 0.1 | 3 | 4 | 3 |
| VII | Filmagens e fotografias | R$ 1.000.680,00 | 8.8 | 34 | 177 | 10 |
| VIII | Viagens do parlamentar e assessores | R$ 62.439,60 | 0.5 | 8 | 19 | 7 |
| IX | Consultorias, assessorias, pesquisas e trabalhos técnicos | R$ 3.737.579,37 | 32.8 | 44 | 343 | 10 |
| X | Edição de jornais, livros e impressos gráficos | R$ 2.485.640,29 | 21.8 | 41 | 229 | 10 |
| XI | Material de expediente e de consumo | R$ 18.700,00 | 0.2 | 3 | 3 | 2 |
| XII | Serviços e profissionais de mídia/comunicação | R$ 2.977.562,28 | 26.2 | 43 | 323 | 10 |
| XIII | Impulsionamento de conteúdo | R$ 87.185,87 | 0.8 | 10 | 34 | 9 |
| XIV | Combustível | R$ 485.887,47 | 4.3 | 36 | 275 | 10 |
| XV | Locação de veículos | R$ 360.052,01 | 3.2 | 14 | 62 | 9 |

Σ 2025: R$ 11.379.721,44.

### Por vereador — 2025 (valores em R$ mil; `meses` = competências com processo lido)

| vereador | meses | total | I | II | III | IV | V | VI | VII | VIII | IX | X | XI | XII | XIII | XIV | XV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Maurício Trindade | 10 | 363.9 | 54.0 | 4.0 | · | 1.3 | · | · | 42.6 | · | 74.1 | 78.8 | · | 48.5 | 1.2 | 59.3 | · |
| Alexandre Aleluia | 8 | 342.2 | 0.1 | 0.0 | · | · | · | · | 51.2 | · | 102.1 | 60.5 | · | 94.1 | · | 9.1 | 25.0 |
| Ricardo Almeida | 10 | 337.5 | · | · | · | · | · | · | · | · | 132.8 | 52.0 | · | 102.7 | · | 9.3 | 40.8 |
| Aladilce Souza | 9 | 332.6 | 19.3 | · | · | · | · | · | · | · | 115.8 | 94.4 | · | 43.2 | · | 14.3 | 45.5 |
| Rodrigo Amaral | 10 | 321.2 | · | · | · | · | · | · | 13.6 | · | 110.4 | 153.9 | · | 32.2 | · | 6.6 | 4.5 |
| Duda Sanches | 10 | 317.1 | 4.0 | · | · | · | · | · | 20.4 | 0.7 | 111.5 | 80.1 | · | 82.3 | · | 18.0 | · |
| Débora Santana | 9 | 316.1 | · | · | · | · | · | · | 13.6 | · | 112.0 | 144.5 | · | 45.9 | · | 0.1 | · |
| Roberta Caires | 8 | 315.5 | · | · | · | · | · | · | 28.2 | · | 108.8 | 106.8 | · | 46.3 | 19.5 | 5.9 | · |
| Alex Alemão | 9 | 314.6 | · | · | · | · | · | · | 40.7 | · | 102.6 | 30.4 | 6.8 | 121.7 | · | 12.3 | · |
| Sidninho | 10 | 313.0 | · | · | · | · | · | · | 56.0 | · | 124.5 | 33.5 | · | 99.0 | · | · | · |
| Kiki Bispo | 9 | 311.0 | · | · | · | · | · | 5.1 | 42.5 | · | 116.4 | 16.8 | · | 130.2 | · | · | · |
| Anderson Ninho | 10 | 307.0 | 3.0 | · | · | · | · | · | 56.8 | · | 117.0 | 55.8 | · | 64.2 | · | · | 10.2 |
| Ireuda Silva | 9 | 305.4 | · | · | · | · | · | · | 57.3 | 20.7 | 81.6 | 79.9 | · | 53.2 | · | 12.6 | · |
| Daniel Alves | 10 | 301.5 | · | · | · | · | · | · | · | · | 129.2 | 53.1 | · | 37.1 | 1.5 | 14.0 | 66.6 |
| Omarzinho Gordilho | 9 | 301.3 | · | · | · | · | · | · | 49.1 | · | 103.8 | 39.2 | · | 100.5 | · | 8.7 | · |
| Felipe Santana | 9 | 299.3 | · | · | · | · | · | · | 27.7 | · | 81.5 | 63.3 | · | 102.6 | · | 24.3 | · |
| Helio Ferreira | 9 | 297.8 | · | · | · | · | · | 6.8 | 54.4 | · | 67.6 | 107.1 | 6.8 | 54.4 | · | 0.7 | · |
| Kel Torres | 9 | 296.1 | · | · | · | · | · | · | 54.4 | · | 67.8 | 105.9 | · | 54.4 | 1.6 | 12.0 | · |
| Jorge Araújo | 10 | 289.7 | · | · | · | · | · | · | · | · | 126.3 | 6.8 | · | 140.3 | · | 16.4 | · |
| David Rios | 9 | 289.3 | 8.4 | · | · | · | · | · | 10.0 | · | 73.5 | 124.5 | 5.1 | 18.8 | 1.4 | 6.8 | 40.8 |
| George Gordinho da Favela | 9 | 288.7 | · | · | · | · | · | · | 54.4 | · | 90.0 | 76.5 | · | 61.2 | · | 6.6 | · |
| Marcelle Moraes | 9 | 287.7 | · | · | · | · | · | · | 61.2 | · | 82.3 | 106.5 | · | 27.2 | · | 10.5 | · |
| Cris Correia | 9 | 286.8 | · | · | · | · | · | · | 6.5 | · | 109.8 | 52.7 | · | 108.7 | · | 9.0 | · |
| Hamilton Assis | 9 | 279.1 | 0.1 | 3.9 | · | 1.0 | · | · | 46.3 | · | 64.5 | 24.7 | · | 101.9 | 24.6 | 12.1 | · |
| Beca | 8 | 278.9 | · | · | · | · | · | · | 8.5 | · | 106.9 | 53.2 | · | 110.0 | 0.2 | · | · |
| Cezar Leite | 10 | 276.4 | · | · | · | · | · | · | 2.0 | · | 76.6 | 25.9 | · | 148.0 | 23.9 | · | · |
| Fábio Souza | 9 | 271.0 | · | · | · | · | · | · | 61.2 | · | 90.0 | 45.8 | · | 61.2 | · | 12.8 | · |
| Téo Senna | 8 | 267.9 | 1.7 | · | · | · | · | · | 6.5 | · | 83.0 | 63.5 | · | 100.5 | · | 12.7 | · |
| João Cláudio Bacelar | 10 | 266.6 | · | 0.5 | · | · | · | · | 19.6 | 2.1 | 53.2 | 46.3 | · | 102.0 | · | 19.7 | 23.1 |
| Orlando Palhinha | 8 | 261.5 | · | · | · | · | · | · | 52.1 | · | 89.7 | 9.8 | · | 110.0 | · | · | · |
| Randerson Leal | 9 | 252.6 | 1.4 | · | · | · | · | · | · | · | 108.8 | 100.2 | · | 33.0 | · | 9.2 | · |
| Kênio Rezende | 8 | 247.8 | · | 0.5 | · | · | · | · | 6.8 | · | 13.6 | 132.6 | · | 84.6 | · | 9.7 | · |
| Isabela Sousa | 9 | 242.9 | · | · | · | 2.1 | · | · | · | · | 96.1 | 67.6 | · | 31.5 | · | 13.3 | 32.4 |
| Marcelo Guimarães Neto | 9 | 239.9 | 1.7 | · | · | · | · | · | · | · | 99.3 | 39.4 | · | 61.2 | · | 17.2 | 21.0 |
| André Fraga | 9 | 218.6 | 24.5 | · | · | · | · | · | 0.7 | 15.0 | 97.5 | 52.8 | · | · | 4.6 | 23.5 | · |
| Claudio Tinoco | 9 | 207.7 | 8.0 | · | · | 5.1 | · | · | 1.6 | 13.6 | 95.2 | 13.6 | · | 52.0 | · | 9.0 | 9.6 |
| Eliete Paraguassu | 9 | 198.9 | · | · | · | · | · | · | 26.9 | · | 108.6 | 20.5 | · | 22.5 | · | 19.1 | 1.3 |
| Marta Rodrigues | 8 | 188.8 | · | · | · | · | · | · | · | 1.9 | 54.4 | · | · | 89.4 | · | 26.2 | 16.8 |
| Paulo Magalhães Júnior | 4 | 135.2 | · | · | · | · | · | · | 12.5 | · | 47.1 | 50.9 | · | 20.8 | · | 3.9 | · |
| Sandro Filho | 8 | 123.7 | · | · | · | · | · | · | 0.7 | · | 34.0 | · | · | 79.0 | · | 10.0 | · |
| Carlos Muniz | 4 | 121.6 | · | · | · | · | · | · | · | · | 54.0 | · | · | 67.6 | · | · | · |
| Sílvio Humberto | 7 | 52.3 | · | · | · | · | · | 1.7 | 1.4 | 1.5 | 7.5 | 2.4 | · | 9.7 | 8.6 | 19.4 | · |
| Julio Santos | 8 | 48.5 | 1.8 | · | · | · | · | · | · | 6.8 | 6.0 | · | · | · | · | 11.6 | 22.4 |
| Alberto Braga | 2 | 34.2 | · | · | · | · | · | · | 13.2 | · | · | · | · | 21.0 | · | · | · |
| Luiz Carlos | 1 | 30.4 | 3.9 | · | · | · | · | · | · | · | 10.3 | 13.4 | · | 3.0 | · | · | · |

### Casa — 2026

| inciso | categoria | total | % | vereadores | processos | meses |
|---|---|---:|---:|---:|---:|---:|
| I | Softwares e aplicativos (aquisição e locação) | R$ 177.103,26 | 1.8 | 12 | 69 | 7 |
| II | Locação de móveis/equipamentos, manutenção e serviços de TI | R$ 12.037,22 | 0.1 | 3 | 14 | 7 |
| III | Assinaturas de publicações e cursos de formação | R$ 20.399,00 | 0.2 | 3 | 4 | 2 |
| IV | Telefonia celular | R$ 8.384,08 | 0.1 | 4 | 24 | 7 |
| V | Cópias, digitalizações e impressões | R$ 6.450,00 | 0.1 | 1 | 1 | 1 |
| VI | Correspondência e mensagens eletrônicas | R$ 17.600,00 | 0.2 | 4 | 4 | 3 |
| VII | Filmagens e fotografias | R$ 1.041.420,00 | 10.4 | 31 | 160 | 7 |
| VIII | Viagens do parlamentar e assessores | R$ 12.856,83 | 0.1 | 2 | 3 | 3 |
| IX | Consultorias, assessorias, pesquisas e trabalhos técnicos | R$ 3.404.310,06 | 33.9 | 44 | 274 | 7 |
| X | Edição de jornais, livros e impressos gráficos | R$ 2.086.548,86 | 20.8 | 35 | 153 | 7 |
| XI | Material de expediente e de consumo | R$ 4.566,00 | 0.0 | 2 | 2 | 2 |
| XII | Serviços e profissionais de mídia/comunicação | R$ 2.633.482,50 | 26.2 | 46 | 230 | 7 |
| XIII | Impulsionamento de conteúdo | R$ 68.242,05 | 0.7 | 6 | 18 | 7 |
| XIV | Combustível | R$ 18.921,91 | 0.2 | 4 | 5 | 4 |
| XV | Locação de veículos | R$ 526.386,51 | 5.2 | 17 | 67 | 7 |

Σ 2026: R$ 10.038.708,28.

### Por vereador — 2026 (valores em R$ mil; `meses` = competências com processo lido)

| vereador | meses | total | I | II | III | IV | V | VI | VII | VIII | IX | X | XI | XII | XIII | XIV | XV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Orlando Palhinha | 7 | 434.0 | · | · | · | · | · | 7.1 | 46.6 | · | 91.0 | · | · | 289.3 | · | · | · |
| Daniel Alves | 7 | 380.0 | · | · | · | · | · | · | · | · | 87.6 | 45.0 | 4.5 | 26.6 | 1.0 | · | 215.3 |
| Fábio Souza | 7 | 273.0 | · | · | · | · | · | · | 54.6 | · | 82.5 | 81.3 | · | 54.6 | · | · | · |
| Sidninho | 7 | 273.0 | · | · | · | · | · | · | 50.0 | · | 82.5 | 18.0 | · | 122.5 | · | · | · |
| Alexandre Aleluia | 7 | 273.0 | · | · | · | · | · | · | 49.0 | · | 105.0 | 35.0 | · | 49.0 | · | · | 35.0 |
| Maurício Trindade | 7 | 272.8 | 44.1 | 6.4 | · | 1.7 | 6.5 | 5.5 | 29.8 | · | 54.0 | 88.1 | · | 36.4 | · | · | 0.4 |
| Helio Ferreira | 7 | 272.6 | · | · | · | · | · | · | 77.6 | · | 47.6 | 94.8 | · | 52.6 | · | · | · |
| Aladilce Souza | 7 | 271.2 | · | · | · | · | · | · | · | · | 83.6 | 143.6 | · | 44.0 | · | · | · |
| Débora Santana | 7 | 269.0 | 15.6 | · | · | · | · | · | 15.6 | · | 109.2 | 97.5 | · | 19.5 | · | · | 11.6 |
| Roberta Caires | 7 | 267.5 | · | · | · | · | · | · | 33.0 | · | 103.8 | 123.8 | · | · | 6.8 | · | · |
| Omarzinho Gordilho | 7 | 263.5 | · | · | · | · | · | · | 49.6 | · | 69.5 | 50.4 | · | 94.0 | · | · | · |
| Marcelle Moraes | 7 | 263.0 | · | · | · | · | · | · | 52.8 | · | 109.2 | 10.0 | · | 76.0 | 15.0 | · | · |
| Alex Alemão | 7 | 262.0 | 27.3 | · | · | · | · | · | 43.5 | · | 76.6 | · | · | 114.4 | · | · | 0.2 |
| Rodrigo Amaral | 7 | 261.8 | · | · | · | · | · | · | 34.4 | · | 106.5 | 112.5 | · | 8.4 | · | · | · |
| Téo Senna | 7 | 260.1 | 1.7 | · | · | · | · | · | · | · | 74.0 | 84.0 | 0.1 | 100.3 | · | · | · |
| David Rios | 7 | 259.4 | 14.4 | · | · | · | · | · | 12.0 | · | 58.5 | 96.0 | · | 40.0 | · | · | 38.5 |
| Marcelo Guimarães Neto | 7 | 252.3 | 1.2 | · | · | · | · | · | · | · | 103.0 | 80.2 | · | 46.4 | · | 3.0 | 18.5 |
| Felipe Santana | 7 | 252.1 | · | · | · | · | · | · | 36.1 | · | 111.3 | 31.5 | · | 61.6 | · | · | 11.6 |
| Anderson Ninho | 7 | 251.6 | 17.8 | · | · | · | · | · | 50.6 | · | 113.4 | · | · | 35.0 | · | · | 34.8 |
| Randerson Leal | 7 | 247.6 | 1.4 | · | · | · | · | · | · | · | 109.2 | 102.0 | · | 35.0 | · | · | · |
| Duda Sanches | 7 | 247.2 | 9.8 | · | · | · | · | · | 21.1 | · | 102.8 | 39.1 | · | 74.4 | · | · | · |
| Beca | 7 | 243.7 | · | · | · | · | · | · | · | · | 150.5 | 36.9 | · | 35.9 | · | · | 20.4 |
| Carlos Muniz | 7 | 238.4 | · | · | · | · | · | · | · | · | 103.2 | · | · | 135.2 | · | · | · |
| Paulo Magalhães Júnior | 7 | 237.6 | · | · | · | · | · | · | 38.7 | · | 109.0 | 74.3 | · | 15.6 | · | · | · |
| Cris Correia | 7 | 235.9 | · | · | · | · | · | · | 45.7 | · | 78.2 | 101.6 | · | 10.4 | · | · | · |
| Kiki Bispo | 6 | 234.0 | · | · | · | · | · | · | 30.6 | · | 86.4 | · | · | 117.0 | · | · | · |
| Ricardo Almeida | 6 | 224.1 | · | · | · | · | · | · | · | · | 93.0 | 51.2 | · | 79.8 | · | · | · |
| Cezar Leite | 7 | 224.0 | · | · | · | · | · | · | 22.9 | · | 77.6 | 10.8 | · | 92.7 | 17.0 | · | 3.0 |
| Kênio Rezende | 6 | 219.0 | · | · | · | · | · | · | · | · | · | 109.5 | · | 109.5 | · | · | · |
| Ireuda Silva | 7 | 218.5 | · | · | 6.5 | · | · | · | 47.1 | · | 39.0 | 81.9 | · | 44.0 | · | · | · |
| Kel Torres | 7 | 195.5 | · | · | 13.5 | · | · | · | 47.2 | · | 48.1 | 19.1 | · | 29.8 | · | · | 37.8 |
| Hamilton Assis | 7 | 192.1 | · | 5.5 | · | 2.7 | · | · | 46.0 | · | 59.0 | 13.6 | · | 52.5 | 12.8 | · | · |
| João Cláudio Bacelar | 7 | 187.4 | · | · | · | · | · | · | 7.8 | · | 9.9 | 37.0 | · | 109.6 | · | · | 23.1 |
| Marta Rodrigues | 7 | 185.2 | · | · | · | · | · | · | · | · | 47.6 | 19.0 | · | 75.2 | · | · | 43.4 |
| André Fraga | 6 | 176.4 | 16.7 | 0.2 | 0.4 | · | · | · | 12.5 | · | 53.8 | 55.9 | · | 21.3 | 15.6 | · | · |
| Claudio Tinoco | 7 | 173.0 | 10.5 | · | · | 1.8 | · | · | · | · | 95.2 | · | · | 45.5 | · | 1.2 | 18.7 |
| Eliete Paraguassu | 7 | 164.2 | · | · | · | · | · | · | 28.1 | · | 108.0 | · | · | 28.1 | · | · | · |
| Isabela Sousa | 6 | 154.6 | · | · | · | 2.1 | · | · | · | · | 70.0 | 56.0 | · | 26.5 | · | · | · |
| Luiz Carlos | 4 | 132.3 | · | · | · | · | · | · | · | 5.1 | 62.3 | 12.8 | · | 52.1 | · | · | · |
| George Gordinho da Favela | 4 | 123.5 | · | · | · | · | · | 4.0 | 21.0 | · | 38.3 | 35.0 | · | 25.2 | · | · | · |
| Jorge Araújo | 3 | 97.1 | · | · | · | · | · | · | 7.0 | · | 42.8 | · | · | 44.0 | · | 3.3 | · |
| Sandro Bahiense | 4 | 91.4 | · | · | · | · | · | · | 15.2 | · | 54.4 | · | · | 21.8 | · | · | · |
| Sandro Filho | 6 | 85.3 | · | · | · | · | · | · | · | · | 34.0 | · | · | 31.0 | · | 11.4 | 8.9 |
| Tiago Queiroz | 2 | 75.2 | · | · | · | · | · | · | 14.0 | · | 22.0 | 19.6 | · | 19.6 | · | · | · |
| Sílvio Humberto | 7 | 51.7 | · | · | · | · | · | 1.0 | 1.3 | · | 41.2 | · | · | 8.2 | · | · | · |
| Dr. José Antonio | 1 | 39.0 | · | · | · | · | · | · | · | · | · | 19.5 | · | 19.5 | · | · | · |
| Julio Santos | 1 | 32.9 | 16.5 | · | · | · | · | · | · | 7.8 | · | · | · | 3.5 | · | · | 5.1 |

## Conciliação com os empenhos

| ano | processos | c/ vereador | c/ empenho na competência | batem | c/ empenho pelo nº | batem | incisos fecham | Σ declarado | Σ empenhado (competência) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2025 | 485 | 485 | 462 | 413 | 468 | 441 | 335 | R$ 13.426.877,46 | R$ 13.962.787,88 |
| 2026 | 296 | 296 | 276 | 261 | 276 | 262 | 245 | R$ 9.834.004,49 | R$ 9.387.001,60 |

Divergências e avisos (também no log):

- processo 377/2025 lido 2x no bronze; mantido PP 377 - VC - Ricardo Almeida.pdf
- processo 2116/2025 lido 2x no bronze; mantido PP 2116 - VC - Andre Moreira Fraga.pdf
- processo 2680/2025 lido 2x no bronze; mantido PP 2680 - VC - Thedfilo Virgilio de Senna.pdf
- processo 567/2025 2025-02: incisos somam R$ 30.417,24 (5 itens) vs total declarado R$ 30.661,56 (confianca=baixa)
- processo 1224/2025 2025-05: incisos somam R$ 23.234,92 (6 itens) vs total declarado R$ 24.234,92 (confianca=baixa)
- processo 1226/2025 2025-05: incisos somam R$ 25.719,20 (5 itens) vs total declarado R$ 33.719,20 (confianca=baixa)
- processo 1228/2025 2025-05: incisos somam R$ 39.082,00 (5 itens) vs total declarado R$ 49.082,00 (confianca=baixa)
- processo 1229/2025 2025-05: incisos somam R$ 0,00 (0 itens) vs total declarado R$ 4.165,38 (confianca=baixa)
- processo 1277/2025 2025-05: incisos somam R$ 90.441,18 (8 itens) vs total declarado R$ 45.220,59 (confianca=baixa)
- processo 1278/2025 2025-05: incisos somam R$ 18.976,83 (5 itens) vs total declarado R$ 28.976,83 (confianca=baixa)
- processo 1283/2025 2025-05: incisos somam R$ 29.866,64 (3 itens) vs total declarado R$ 14.933,32 (confianca=baixa)
- processo 1286/2025 2025-05: incisos somam R$ 17.489,85 (3 itens) vs total declarado R$ 35,30 (confianca=baixa)
- processo 1289/2025 2025-05: incisos somam R$ 16.060,00 (2 itens) vs total declarado R$ 43.300,00 (confianca=baixa)
- processo 1292/2025 2025-05: incisos somam R$ 20.406,01 (4 itens) vs total declarado R$ 34.406,01 (confianca=baixa)
- processo 1296/2025 2025-05: incisos somam R$ 46.300,00 (4 itens) vs total declarado R$ 46,66 (confianca=baixa)
- processo 1297/2025 2025-05: incisos somam R$ 83.551,70 (6 itens) vs total declarado R$ 45,52 (confianca=baixa)
- processo 1502/2025 2025-06: incisos somam R$ 18.214,70 (2 itens) vs total declarado R$ 35.156,70 (confianca=baixa)
- processo 1521/2025 2025-06: incisos somam R$ 36.327,17 (7 itens) vs total declarado R$ 42,35 (confianca=baixa)
- processo 1522/2025 2025-06: incisos somam R$ 24.200,00 (3 itens) vs total declarado R$ 34.000,00 (confianca=baixa)
- processo 1528/2025 2025-06: incisos somam R$ 23.659,59 (4 itens) vs total declarado R$ 23.900,49 (confianca=baixa)
- processo 1529/2025 2025-06: incisos somam R$ 0,00 (0 itens) vs total declarado R$ 34.000,00 (confianca=baixa)
- processo 1547/2025 2025-06: incisos somam R$ 9.600,00 (2 itens) vs total declarado R$ 26.680,98 (confianca=baixa)
- processo 1624/2025 2025-06: incisos somam R$ 24.000,00 (5 itens) vs total declarado R$ 34.000,00 (confianca=baixa)
- processo 1785/2025 2025-07: incisos somam R$ 25.600,00 (4 itens) vs total declarado R$ 33.900,00 (confianca=baixa)
- processo 1787/2025 2025-07: incisos somam R$ 25.317,44 (3 itens) vs total declarado R$ 35.317,44 (confianca=baixa)
- processo 1800/2025 2025-07: incisos somam R$ 36.869,78 (4 itens) vs total declarado R$ 38.069,78 (confianca=baixa)
- processo 1820/2025 2025-07: incisos somam R$ 21.827,37 (5 itens) vs total declarado R$ 21.822,37 (confianca=baixa)
- processo 1836/2025 2025-07: incisos somam R$ 64.729,08 (6 itens) vs total declarado R$ 32.364,54 (confianca=baixa)
- processo 1856/2025 2025-07: incisos somam R$ 2.846,25 (2 itens) vs total declarado R$ 4.846,25 (confianca=baixa)
- processo 1859/2025 2025-07: incisos somam R$ 10.105,03 (3 itens) vs total declarado R$ 20.105,03 (confianca=baixa)
- processo 2026/2025 2025-08: incisos somam R$ 32.930,87 (3 itens) vs total declarado R$ 32.030,87 (confianca=baixa)
- processo 2027/2025 2025-08: incisos somam R$ 25.300,00 (3 itens) vs total declarado R$ 32.600,00 (confianca=baixa)
- processo 2057/2025 2025-08: incisos somam R$ 1.159,31 (1 itens) vs total declarado R$ 35.149,31 (confianca=baixa)
- processo 2074/2025 2025-08: incisos somam R$ 31.234,89 (5 itens) vs total declarado R$ 41.234,89 (confianca=baixa)
- processo 2087/2025 2025-08: incisos somam R$ 33.002,55 (5 itens) vs total declarado R$ 33.402,55 (confianca=baixa)
- processo 2113/2025 2025-08: incisos somam R$ 25.872,62 (5 itens) vs total declarado R$ 33.872,62 (confianca=baixa)
- processo 2115/2025 2025-08: incisos somam R$ 23.800,00 (3 itens) vs total declarado R$ 33.800,00 (confianca=baixa)
- processo 2326/2025 2025-09: incisos somam R$ 34.000,00 (3 itens) vs total declarado R$ 34,00 (confianca=baixa)
- processo 2340/2025 2025-09: incisos somam R$ 25.300,00 (3 itens) vs total declarado R$ 32.600,00 (confianca=baixa)
- processo 2342/2025 2025-09: incisos somam R$ 33.800,00 (5 itens) vs total declarado R$ 33.800,15 (confianca=baixa)
- processo 2361/2025 2025-09: incisos somam R$ 22.570,00 (3 itens) vs total declarado R$ 32.570,00 (confianca=baixa)
- processo 2384/2025 2025-09: incisos somam R$ 51.800,00 (4 itens) vs total declarado R$ 25.900,00 (confianca=baixa)
- processo 2390/2025 2025-09: incisos somam R$ 16.184,63 (4 itens) vs total declarado R$ 33.054,63 (confianca=baixa)
- processo 2470/2025 2025-09: incisos somam R$ 30.109,99 (4 itens) vs total declarado R$ 30.309,99 (confianca=baixa)
- processo 2621/2025 2025-10: incisos somam R$ 33.447,27 (5 itens) vs total declarado R$ 33.448,27 (confianca=baixa)
- processo 2651/2025 2025-10: incisos somam R$ 29.308,18 (5 itens) vs total declarado R$ 29.307,18 (confianca=baixa)
- processo 2681/2025 2025-10: incisos somam R$ 15.825,50 (4 itens) vs total declarado R$ 7.912,75 (confianca=baixa)
- processo 2831/2025 2025-11: incisos somam R$ 23.400,00 (2 itens) vs total declarado R$ 32.900,00 (confianca=baixa)
- processo 2833/2025 2025-11: incisos somam R$ 23.600,00 (3 itens) vs total declarado R$ 32.950,00 (confianca=baixa)
- processo 2887/2025 2025-11: incisos somam R$ 15.432,74 (4 itens) vs total declarado R$ 32.302,74 (confianca=baixa)
- processo 2891/2025 2025-11: incisos somam R$ 24.900,00 (5 itens) vs total declarado R$ 32.900,00 (confianca=baixa)
- processo 2984/2025 2025-11: incisos somam R$ 33.953,06 (5 itens) vs total declarado R$ 43.953,06 (confianca=baixa)
- processo 2985/2025 2025-11: incisos somam R$ 27.926,96 (6 itens) vs total declarado R$ 35.876,96 (confianca=baixa)
- processo 3124/2025 2025-12: incisos somam R$ 24.000,00 (3 itens) vs total declarado R$ 34.000,00 (confianca=baixa)
- processo 3130/2025 2025-12: incisos somam R$ 14.565,25 (2 itens) vs total declarado R$ 33.565,25 (confianca=baixa)
- processo 3193/2025 2025-12: incisos somam R$ 23.104,34 (3 itens) vs total declarado R$ 36.354,34 (confianca=baixa)
- processo 3203/2025 2025-12: incisos somam R$ 14.826,74 (3 itens) vs total declarado R$ 31.826,74 (confianca=baixa)
- processo 148/2026 2026-01: incisos somam R$ 39.099,00 (5 itens) vs total declarado R$ 39.000,00 (confianca=baixa)
- processo 149/2026 2026-01: incisos somam R$ 45.000,00 (3 itens) vs total declarado R$ 39.000,00 (confianca=baixa)
- processo 173/2026 2026-01: incisos somam R$ 24.294,33 (4 itens) vs total declarado R$ 23.300,00 (confianca=baixa)
- processo 185/2026 2026-01: incisos somam R$ 13.800,00 (3 itens) vs total declarado R$ 23.800,00 (confianca=baixa)
- processo 186/2026 2026-01: incisos somam R$ 23.364,44 (5 itens) vs total declarado R$ 22.165,90 (confianca=baixa)
- processo 204/2026 2026-01: incisos somam R$ 13.750,00 (3 itens) vs total declarado R$ 21.750,00 (confianca=baixa)
- processo 325/2026 2026-02: incisos somam R$ 35.894,00 (4 itens) vs total declarado R$ 36.143,90 (confianca=baixa)
- processo 328/2026 2026-02: incisos somam R$ 65.970,00 (3 itens) vs total declarado R$ 42.060,00 (confianca=baixa)
- processo 354/2026 2026-02: incisos somam R$ 47.600,00 (3 itens) vs total declarado R$ 23.800,00 (confianca=baixa)
- processo 376/2026 2026-02: incisos somam R$ 26.799,90 (4 itens) vs total declarado R$ 36.799,90 (confianca=baixa)
- processo 378/2026 2026-02: incisos somam R$ 20.700,00 (3 itens) vs total declarado R$ 29.700,00 (confianca=baixa)
- processo 394/2026 2026-02: incisos somam R$ 29.050,06 (4 itens) vs total declarado R$ 39.050,00 (confianca=baixa)
- processo 399/2026 2026-02: incisos somam R$ 24.908,56 (7 itens) vs total declarado R$ 29.448,56 (confianca=baixa)
- processo 411/2026 2026-02: incisos somam R$ 13.500,00 (2 itens) vs total declarado R$ 33.000,00 (confianca=baixa)
- processo 416/2026 2026-02: incisos somam R$ 25.839,75 (4 itens) vs total declarado R$ 26.079,05 (confianca=baixa)
- processo 428/2026 2026-02: incisos somam R$ 13.250,00 (2 itens) vs total declarado R$ 40.556,00 (confianca=baixa)
- processo 595/2026 2026-03: incisos somam R$ 20.130,00 (3 itens) vs total declarado R$ 30.130,00 (confianca=baixa)
- processo 621/2026 2026-03: incisos somam R$ 27.800,00 (3 itens) vs total declarado R$ 37.600,00 (confianca=baixa)
- processo 674/2026 2026-03: incisos somam R$ 35.465,90 (5 itens) vs total declarado R$ 35.456,55 (confianca=baixa)
- processo 762/2026 2026-03: incisos somam R$ 13.300,00 (2 itens) vs total declarado R$ 41.100,00 (confianca=baixa)
- processo 820/2026 2026-04: incisos somam R$ 35.712,00 (4 itens) vs total declarado R$ 35.961,90 (confianca=baixa)
- processo 825/2026 2026-04: incisos somam R$ 123.500,00 (2 itens) vs total declarado R$ 30.500,00 (confianca=baixa)
- processo 854/2026 2026-04: incisos somam R$ 12.500,00 (1 itens) vs total declarado R$ 32.430,00 (confianca=baixa)
- processo 856/2026 2026-04: incisos somam R$ 201.100,00 (3 itens) vs total declarado R$ 38.200,00 (confianca=baixa)
- processo 857/2026 2026-04: incisos somam R$ 39.830,13 (8 itens) vs total declarado R$ 39.100,53 (confianca=baixa)
- processo 887/2026 2026-04: incisos somam R$ 32.700,00 (4 itens) vs total declarado R$ 38.700,00 (confianca=baixa)
- processo 891/2026 2026-04: incisos somam R$ 39.050,00 (4 itens) vs total declarado R$ 39.050,10 (confianca=baixa)
- processo 911/2026 2026-04: incisos somam R$ 37.000,00 (3 itens) vs total declarado R$ 25.300,00 (confianca=baixa)
- processo 1066/2026 2026-05: incisos somam R$ 29.000,00 (4 itens) vs total declarado R$ 39.000,00 (confianca=baixa)
- processo 1083/2026 2026-05: incisos somam R$ 6.580,00 (2 itens) vs total declarado R$ 7.880,00 (confianca=baixa)
- processo 1123/2026 2026-05: incisos somam R$ 12.930,00 (2 itens) vs total declarado R$ 32.430,00 (confianca=baixa)
- processo 1133/2026 2026-05: incisos somam R$ 78.600,00 (3 itens) vs total declarado R$ 43.000,00 (confianca=baixa)
- processo 1135/2026 2026-05: incisos somam R$ 13.250,00 (2 itens) vs total declarado R$ 38.780,00 (confianca=baixa)
- processo 1158/2026 2026-05: incisos somam R$ 30.749,76 (4 itens) vs total declarado R$ 38.999,76 (confianca=baixa)
- processo 1337/2026 2026-06: incisos somam R$ 39.000,00 (3 itens) vs total declarado R$ 39.900,00 (confianca=baixa)
- processo 1366/2026 2026-06: incisos somam R$ 81.600,00 (4 itens) vs total declarado R$ 41.800,00 (confianca=baixa)
- processo 1395/2026 2026-06: incisos somam R$ 52.200,00 (4 itens) vs total declarado R$ 26.100,00 (confianca=baixa)
- processo 1405/2026 2026-06: incisos somam R$ 22.800,00 (2 itens) vs total declarado R$ 23.300,00 (confianca=baixa)
- processo 1408/2026 2026-06: incisos somam R$ 23.400,00 (2 itens) vs total declarado R$ 23.799,00 (confianca=baixa)
- processo 1429/2026 2026-06: incisos somam R$ 34.150,00 (2 itens) vs total declarado R$ 34.150,90 (confianca=baixa)
- processo 1430/2026 2026-06: incisos somam R$ 17.048,33 (2 itens) vs total declarado R$ 40.748,33 (confianca=baixa)
- processo 1608/2026 2026-07: incisos somam R$ 31.200,00 (3 itens) vs total declarado R$ 41.200,00 (confianca=baixa)
- processo 1644/2026 2026-07: incisos somam R$ 53.575,20 (3 itens) vs total declarado R$ 26.787,60 (confianca=baixa)
- processo 1653/2026 2026-07: incisos somam R$ 31.199,00 (3 itens) vs total declarado R$ 33.759,00 (confianca=baixa)
- processo 1661/2026 2026-07: incisos somam R$ 26.323,67 (3 itens) vs total declarado R$ 26.323,33 (confianca=baixa)
- processo 1662/2026 2026-07: incisos somam R$ 39.500,00 (5 itens) vs total declarado R$ 39.100,00 (confianca=baixa)
- processo 431/2025 2025-01 mauricio-trindade: total declarado R$ 20.140,02 × empenhado ao vereador na competência R$ 40.280,02 (dif R$ -20.140,00)
- processo 331/2026 2025-02 kiki-bispo: total declarado R$ 39.000,00 × empenhado ao vereador na competência R$ 34.000,00 (dif R$ 5.000,00)
- processo 333/2026 2025-02 ricardo-almeida: total declarado R$ 29.200,00 × empenhado ao vereador na competência R$ 37.700,00 (dif R$ -8.500,00)
- processo 432/2025 2025-02 rodrigo-amaral: total declarado R$ 10.102,99 × empenhado ao vereador na competência R$ 32.676,14 (dif R$ -22.573,15)
- processo 557/2025 2025-02 cezar-leite: total declarado R$ 14.500,00 × empenhado ao vereador na competência R$ 30.000,00 (dif R$ -15.500,00)
- processo 560/2025 2025-02 anderson-ninho: total declarado R$ 6.500,00 × empenhado ao vereador na competência R$ 33.000,00 (dif R$ -26.500,00)
- processo 561/2025 2025-02 andre-fraga: total declarado R$ 17.704,26 × empenhado ao vereador na competência R$ 18.664,26 (dif R$ -960,00)
- processo 563/2025 2025-02 omarzinho-gordilho: total declarado R$ 8.000,00 × empenhado ao vereador na competência R$ 59.651,12 (dif R$ -51.651,12)
- processo 564/2025 2025-02 sidninho: total declarado R$ 6.500,00 × empenhado ao vereador na competência R$ 33.500,00 (dif R$ -27.000,00)
- processo 566/2025 2025-02 alexandre-aleluia: total declarado R$ 18.110,02 × empenhado ao vereador na competência R$ 32.485,77 (dif R$ -14.375,75)
- processo 572/2025 2025-02 duda-sanches: total declarado R$ 23.619,34 × empenhado ao vereador na competência R$ 32.825,88 (dif R$ -9.206,54)
- processo 573/2025 2025-02 ricardo-almeida: total declarado R$ 17.659,04 × empenhado ao vereador na competência R$ 37.700,00 (dif R$ -20.040,96)
- processo 575/2025 2025-02 kiki-bispo: total declarado R$ 5.100,00 × empenhado ao vereador na competência R$ 34.000,00 (dif R$ -28.900,00)
- processo 581/2025 2025-02 paulo-magalhaes-junior: total declarado R$ 9.181,37 × empenhado ao vereador na competência R$ 33.744,47 (dif R$ -24.563,10)
- processo 610/2025 2025-02 joao-claudio-bacelar: total declarado R$ 20.340,01 × empenhado ao vereador na competência R$ 33.795,04 (dif R$ -13.455,03)
- processo 637/2025 2025-02 david-rios: total declarado R$ 33.500,00 × empenhado ao vereador na competência R$ 27.673,83 (dif R$ 5.826,17)
- processo 654/2025 2025-02 claudio-tinoco: total declarado R$ 26.524,54 × empenhado ao vereador na competência R$ 27.874,16 (dif R$ -1.349,62)
- processo 707/2025 2025-02 cezar-leite: total declarado R$ 15.500,00 × empenhado ao vereador na competência R$ 30.000,00 (dif R$ -14.500,00)
- processo 708/2025 2025-03 marcelle-moraes: total declarado R$ 37.000,00 × empenhado ao vereador na competência R$ 74.000,00 (dif R$ -37.000,00)
- processo 725/2025 2025-03 marcelo-guimaraes-neto: total declarado R$ 22.518,35 × empenhado ao vereador na competência R$ 42.072,49 (dif R$ -19.554,14)
- processo 738/2025 2025-03 ricardo-almeida: total declarado R$ 30.277,45 × empenhado ao vereador na competência R$ 47.936,49 (dif R$ -17.659,04)
- processo 780/2025 2025-03 alexandre-aleluia: total declarado R$ 33.889,12 × empenhado ao vereador na competência R$ 101.087,36 (dif R$ -67.198,24); empenho 2025NE000302 vale R$ 33.309,12 (dif R$ 580,00)
- processo 797/2025 2025-03 kel-torres: total declarado R$ 30.410,42 × empenho 2025NE000275 vale R$ 34.000,00 (dif R$ -3.589,58)
- processo 799/2025 2025-03 andre-fraga: total declarado R$ 2.075,53 × empenhado ao vereador na competência R$ 4.150,86 (dif R$ -2.075,33)
- processo 801/2025 2025-03 david-rios: total declarado R$ 27.673,83 × empenhado ao vereador na competência R$ 33.500,00 (dif R$ -5.826,17)
- processo 906/2025 2025-03 isabela-sousa: total declarado R$ 32.465,69 × empenhado ao vereador na competência R$ 31.740,41 (dif R$ 725,28)
- processo 983/2025 2025-04 paulo-magalhaes-junior: total declarado R$ 16.993,25 × empenhado ao vereador na competência R$ 39.597,37 (dif R$ -22.604,12)
- processo 1023/2025 2025-04 ireuda-silva: total declarado R$ 16.027,08 × empenhado ao vereador na competência R$ 26.371,54 (dif R$ -10.344,46)
- processo 1286/2025 2025-05 isabela-sousa: total declarado R$ 35,30 × empenhado ao vereador na competência R$ 35.302,13 (dif R$ -35.266,83); empenho 2025NE000457 vale R$ 35.302,13 (dif R$ -35.266,83)
- processo 1292/2025 2025-05 joao-claudio-bacelar: total declarado R$ 34.406,01 × empenhado ao vereador na competência R$ 30.406,01 (dif R$ 4.000,00); empenho 2025NE000452 vale R$ 30.406,01 (dif R$ 4.000,00)
- processo 1296/2025 2025-05 ricardo-almeida: total declarado R$ 46,66 × empenhado ao vereador na competência R$ 46.677,17 (dif R$ -46.630,51); empenho 2025NE000466 vale R$ 46.677,17 (dif R$ -46.630,51)
- processo 1297/2025 2025-05 aladilce-souza: total declarado R$ 45,52 × empenhado ao vereador na competência R$ 45.525,85 (dif R$ -45.480,33); empenho 2025NE000471 vale R$ 45.525,85 (dif R$ -45.480,33)
- processo 1281/2025 2025-06 julio-santos: total declarado R$ 4.726,18 × empenhado ao vereador na competência R$ 7.792,26 (dif R$ -3.066,08)
- processo 1521/2025 2025-06 hamilton-assis: total declarado R$ 42,35 × empenhado ao vereador na competência R$ 42.357,07 (dif R$ -42.314,72); empenho 2025NE000503 vale R$ 42.357,07 (dif R$ -42.314,72)
- processo 1543/2025 2025-06 david-rios: total declarado R$ 9.000,00 × empenhado ao vereador na competência R$ 38.293,31 (dif R$ -29.293,31); empenho 2025NE000511 vale R$ 38.293,31 (dif R$ -29.293,31)
- processo 1867/2025 2025-07 teo-senna: total declarado R$ 31.500,00 × empenhado ao vereador na competência R$ 31.376,75 (dif R$ 123,25)
- processo 2326/2025 2025-09 rodrigo-amaral: total declarado R$ 34,00 × empenhado ao vereador na competência R$ 34.000,00 (dif R$ -33.966,00); empenho 2025NE000690 vale R$ 34.000,00 (dif R$ -33.966,00)
- processo 2606/2025 2025-10 cezar-leite: total declarado R$ 34.875,30 × empenho 2025NE000777 vale R$ 26.718,56 (dif R$ 8.156,74)
- processo 2607/2025 2025-10 marta-rodrigues: total declarado R$ 26.718,56 × empenho 2025NE000775 vale R$ 34.875,30 (dif R$ -8.156,74)
- processo 2624/2025 2025-10 ricardo-almeida: total declarado R$ 30.583,33 × empenhado ao vereador na competência R$ 61.166,66 (dif R$ -30.583,33)
- processo 2652/2025 2025-10 debora-santana: total declarado R$ 34.000,00 × empenhado ao vereador na competência R$ 68.000,00 (dif R$ -34.000,00)
- processo 2672/2025 2025-10 hamilton-assis: total declarado R$ 25.769,57 × empenhado ao vereador na competência R$ 51.539,14 (dif R$ -25.769,57)
- processo 2679/2025 2025-10 felipe-santana: total declarado R$ 34.019,10 × empenho 2025NE000815 vale R$ 36.099,89 (dif R$ -2.080,79)
- processo 2804/2025 2025-11 kenio-rezende: total declarado R$ 33.400,00 × empenhado ao vereador na competência R$ 34.000,00 (dif R$ -600,00); empenho 2025NE000840 vale R$ 34.000,00 (dif R$ -600,00)
- processo 3116/2025 2025-12 ricardo-almeida: total declarado R$ 44.514,48 × empenho 2025NE000901 vale R$ 25.769,57 (dif R$ 18.744,91)
- processo 3122/2025 2025-12 duda-sanches: total declarado R$ 34.938,13 × empenho 2025NE000900 vale R$ 34.000,00 (dif R$ 938,13)
- processo 3128/2025 2025-12 alexandre-aleluia: total declarado R$ 34.000,00 × empenho 2025NE000952 vale R$ 32.021,99 (dif R$ 1.978,01)
- processo 3131/2025 2025-12 jorge-araujo: total declarado R$ 32.021,99 × empenho 2025NE000902 vale R$ 33.906,56 (dif R$ -1.884,57)
- processo 3176/2025 2025-12 daniel-alves: total declarado R$ 38.505,02 × empenho 2025NE000951 vale R$ 44.514,48 (dif R$ -6.009,46)
- processo 3204/2025 2025-12 marta-rodrigues: total declarado R$ 25.791,14 × empenho 2025NE000950 vale R$ 34.938,13 (dif R$ -9.146,99)
- processo 3223/2025 2025-12 carlos-muniz: total declarado R$ 30.300,00 × empenhado ao vereador na competência R$ 60.600,00 (dif R$ -30.300,00)
- processo 124/2026 2026-01 joao-claudio-bacelar: total declarado R$ 13.100,00 × empenhado ao vereador na competência R$ 13.000,00 (dif R$ 100,00); empenho 2026NE000093 vale R$ 13.000,00 (dif R$ 100,00)
- processo 125/2026 2026-01 george-gordinho-da-favela: total declarado R$ 36.600,00 × empenhado ao vereador na competência R$ 36.800,00 (dif R$ -200,00); empenho 2026NE000094 vale R$ 36.800,00 (dif R$ -200,00)
- processo 184/2026 2026-01 hamilton-assis: total declarado R$ 22.319,90 × empenhado ao vereador na competência R$ 36.100,00 (dif R$ -13.780,10); empenho 2026NE000130 vale R$ 36.100,00 (dif R$ -13.780,10)
- processo 329/2026 2026-02 mauricio-trindade: total declarado R$ 39.200,71 × empenhado ao vereador na competência R$ 39.000,00 (dif R$ 200,71); empenho 2026NE000163 vale R$ 39.900,00 (dif R$ -699,29)
- processo 332/2026 2026-02 rodrigo-amaral: total declarado R$ 39.900,00 × empenho 2026NE000162 vale R$ 39.000,00 (dif R$ 900,00)
- processo 581/2026 2026-03 ricardo-almeida: total declarado R$ 41.700,00 × empenhado ao vereador na competência R$ 71.525,00 (dif R$ -29.825,00)
- processo 614/2026 2026-03 mauricio-trindade: total declarado R$ 38.908,68 × empenhado ao vereador na competência R$ 39.908,68 (dif R$ -1.000,00); empenho 2026NE000271 vale R$ 39.908,68 (dif R$ -1.000,00)
- processo 638/2026 2026-03 andre-fraga: total declarado R$ 43.721,86 × empenhado ao vereador na competência R$ 43.721,83 (dif R$ 0,03); empenho 2026NE000284 vale R$ 43.721,83 (dif R$ 0,03)
- processo 854/2026 2026-04 isabela-sousa: total declarado R$ 32.430,00 × empenhado ao vereador na competência R$ 64.869,36 (dif R$ -32.439,36)
- processo 891/2026 2026-04 cezar-leite: total declarado R$ 39.050,10 × empenhado ao vereador na competência R$ 39.050,00 (dif R$ 0,10)
- processo 1003/2025 2026-04 ricardo-almeida: total declarado R$ 16,93 × empenho 2025NE000347 vale R$ 16.935,81 (dif R$ -16.918,88)
- processo 1082/2026 2026-05 mauricio-trindade: total declarado R$ 39.175,88 × empenhado ao vereador na competência R$ 39.000,00 (dif R$ 175,88); empenho 2026NE000425 vale R$ 39.000,00 (dif R$ 175,88)
- processo 1337/2026 2026-06 kiki-bispo: total declarado R$ 39.900,00 × empenhado ao vereador na competência R$ 39.000,00 (dif R$ 900,00); empenho 2026NE000481 vale R$ 39.000,00 (dif R$ 900,00)
- processo 1429/2026 2026-06 carlos-muniz: total declarado R$ 34.150,90 × empenhado ao vereador na competência R$ 34.150,00 (dif R$ 0,90); empenho 2026NE000538 vale R$ 34.150,00 (dif R$ 0,90)
