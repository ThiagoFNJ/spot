# Produtividade legislativa — 2025 e 2026 (parcial)

Gerado em 2026-10-28 por `uv run python -m spot.metrics.produtividade` a partir de `data/silver/spot.duckdb` (tabelas `metrica_produtividade`, `metrica_produtividade_tipo`, `produtividade_outros_autores`, `produtividade_situacao_snapshot`, `produtividade_reconciliacao`). Fonte primária: export CSV de `cmsalvador.sys.inf.br/cl/prop_interna` (bronze `data/bronze/proposicoes/`), resumo oficial `LEG_SYS_produtividade_parlamentar_proposicao` para reconciliação, meses em exercício pela grade de frequência.

## Método (spike §4.2)

- **Autor** = primeiro signatário (RI art. 179): primeiro elemento de `autores` (campo *Autor* do grid, separado por `|`). Nomes resolvidos por `vereador_alias` (`fonte = proposicao`, strings idênticas às da grade de frequência). Autores institucionais (Executivo, Mesa, comissões) ficam em `produtividade_outros_autores`.
- **Volume bruto** `n_total` = proposições 2025+ por (vereador, ano), sem sentinelas (`PLE-9999/2025` é registro de teste).
- **Exclusões** por regex (RE2, sobre `strip_accents(lower(ementa))`) aplicadas **antes** da ponderação, cada uma só nos tipos indicados; a proposição excluída continua em `n_total` e em `n_<tipo>` mas vale 0 no volume ponderado.
- **Volume ponderado** `vol_ponderado = Σ_tipo peso_tipo × (n_tipo − n_excluídas_tipo)`; `vol_ponderado_12m = vol_ponderado / meses_exercicio × 12`.
- **Meses em exercício**: inferidos da grade de frequência (`presenca_mvp`): do primeiro ao último mês do ano em que o vereador tem linha, estendido a janeiro quando aparece no primeiro mês com sessão do ano (janeiro é recesso) e a dezembro — ou ao mês corrente, em 2026 — quando aparece no último. Licenças no meio do intervalo não são descontadas.
- **Taxa de aprovação**: não computável neste snapshot (exige o crawl de `prop_interna_tram`); ver §Situação (snapshot).

### Pesos v0 (`data/seeds/pesos_v0.csv`, parâmetro versionado)

| tipo | peso | proposições 2025-26 | observação |
|---|---:|---:|---|
| PDL | 3.0 | 2 | projeto de decreto legislativo; mesmo peso de PLE |
| PEL | 3.0 | 2 | projeto de emenda à Lei Orgânica; mesmo peso de PLE |
| PLC | 3.0 | 10 | projeto de lei complementar; mesmo peso de PLE |
| PLE | 3.0 | 875 | projeto de lei ordinária (RI art. 171); peso máximo v0 (spike §4.2) |
| PRE | 1.0 | 220 | projeto de resolução não honorífico (revoga resolução; institui prêmio; carteira funcional); PRE de honraria (Título de Cidadão / Medalha / Comenda) é excluído pelo regex honraria antes da ponderação = 0 (RI arts. 203-208) |
| REP | 1.0 | 436 | requerimento ao Plenário (RI art. 194-195) |
| RUP | 1.0 | 91 | requerimento de urgência / à Presidência; mesmo peso de REP |
| RUU | 1.0 | 0 | requerimento (código histórico; ausente em 2025-26); mesmo peso de REP |
| PIN | 0.5 | 1244 | indicação (RI art. 209); peso reduzido pela inflação documentada (spike §4.2); indicação de nome de logradouro/equipamento excluída pelo regex logradouro |
| MOC | 0.25 | 700 | moção (aplauso / repúdio / apoio); moção de pesar excluída pelo regex pesar = 0 |
| RAD | 0.0 | 0 | código único no histórico (1 linha; antes de 2025); sem definição conhecida |
| SUB | 0.0 | 1 | substitutivo; conta no eixo 3 (trabalho em comissão) — spike §4.2 |
| VTO | 0.0 | 7 | veto do Executivo; não é produção parlamentar |

### Exclusões por regex (contagens sobre 2025-26, todos os autores)

| exclusão | tipos em que se aplica | regex | excluídas (2025 / 2026) | por tipo | acertos fora do escopo (ignorados) |
|---|---|---|---:|---|---:|
| logradouro — nome de rua / logradouro / equipamento público | PLE, PLC, PIN, REP, RUP | `^denomina\|passa a denominar\|\bo nome de\b\|denominacao d[aeo]s? \|logradouro denominad\|mudanca de nome\|seja denominad[oa] de\|para denominar` | 68 (48 / 20) | PLE 60, PIN 7, PLC 1 | 1 |
| honraria — Título de Cidadão, Medalha, Comenda, Diploma (RI arts. 203-208) | PRE | `titulo de cidad\|comenda\|medalha\|\bdiplomas?\b` | 216 (131 / 85) | PRE 216 | 10 |
| pesar — moção de pesar / in memoriam | MOC | `\bpesar\b\|falecimento\|falecid[oa]s?\b\|in memoriam\|pela morte\|condolencias\|\bluto\b` | 54 (33 / 21) | MOC 54 | 5 |

Conferência manual dos padrões nas ementas reais (27/10/2026): `denomina` solto pegava campanhas/programas "denominados" (Janeiro Branco, Agosto Dourado, Sala Lilás) e a "PEC denominada Blindagem" — daí o padrão ancorado (`^denomina`, `denominacao d[aeo]`, `o nome de`, `logradouro denominad`, `mudanca de nome`); restam como falsos positivos conhecidos 2–3 PLE que *regulam* denominação (veda denominação de vias; cessão onerosa do direito à denominação; denominação de nomes de vereadores falecidos). `diploma` pegava "relações diplomáticas" (MOC) — `\bdiplomas?\b`. `pesar` foi ampliado para `falecid[oa]`, `in memoriam`, `pela morte`, pois há aplausos *in memoriam* e um "Repúdio pela morte"; só vale para MOC — o PLE sobre mães atípicas "após o falecimento de filhos" e a PIN sobre abono de faltas não são excluídos. Honraria só em PRE: os 4 REP de sessão solene para entrega de medalha e o PLE do braile em medalhas continuam valendo.

## Reconciliação com o resumo oficial (`LEG_SYS_produtividade_parlamentar_proposicao`)

Volume bruto por primeiro autor em `prop_interna` (sem sentinelas) × soma por autor do resumo oficial (mesmo sistema; o resumo não tem coluna SUB).

| ano | prop_interna | resumo | autores divergentes |
|---:|---:|---:|---:|
| 2025 | 2038 | 2037 | 1 |
| 2026 | 1550 | 1550 | 0 |

Critério de aceite do spike (2025, volume bruto antes de exclusões e pesos):

| autor | esperado (BN 2025) | prop_interna | resumo | ok |
|---|---:|---:|---:|:---:|
| Aladilce | 148 | 148 | 148 | sim |
| Felipe Santana | 144 | 144 | 144 | sim |
| André Fraga | 124 | 124 | 124 | sim |

Autores com contagem diferente entre as duas fontes:

| ano | autor | prop_interna | resumo | Δ | explicação |
|---:|---|---:|---:|---:|---|
| 2025 | Professor Hamilton | 120 | 119 | +1 | SUB-1/2025 (substitutivo) existe em prop_interna mas o resumo não tem coluna SUB |

`João Marcelo` aparece em `prop_interna` só como autor do registro de teste `PLE-9999/2025` (`sentinela = true`) e, por isso, em nenhuma tabela desta métrica.

## Ranking 2025

45 vereadores com pelo menos uma proposição como 1º autor; 1987 proposições, 197 excluídas por regex.

- Top-5 por **volume bruto**: Aladilce Souza (148); Felipe Santana (144); André Fraga (124); Hamilton Assis (120); Kel Torres (109).
- Top-5 por **volume ponderado / 12 meses**: Hamilton Assis (156.0); André Fraga (134.0); Randerson Leal (132.8); Débora Santana (130.0); Felipe Santana (123.8).

`Δ posto` = posto bruto − posto ponderado (positivo = sobe quando indicações/moções/honrarias são descontadas). Ordenado pelo volume bruto.

| # bruto | # pond. | Δ posto | vereador | partido | meses | total | PLE | PLC+PEL+PDL | PRE | REP+RUP | PIN | MOC | outros | excl. regex | vol. pond. | vol. pond./12m | coaut. |
|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 8 | -7 | Aladilce Souza | PCdoB | 12 | 148 | 15 | 0 | 3 | 56 | 12 | 62 | 0 | 13 | 111.8 | 111.8 | 0 |
| 2 | 5 | -3 | Felipe Santana | PSD | 12 | 144 | 22 | 0 | 2 | 19 | 59 | 42 | 0 | 7 | 123.8 | 123.8 | 0 |
| 3 | 2 | +1 | André Fraga | PV | 12 | 124 | 39 | 0 | 3 | 5 | 68 | 9 | 0 | 12 | 134.0 | 134.0 | 0 |
| 4 | 1 | +3 | Hamilton Assis | PSOL | 12 | 120 | 38 | 0 | 1 | 21 | 38 | 21 | 1 | 3 | 156.0 | 156.0 | 0 |
| 5 | 20 | -15 | Kel Torres | Republicanos | 12 | 109 | 16 | 0 | 3 | 5 | 19 | 66 | 0 | 15 | 43.0 | 43.0 | 0 |
| 6 | 3 | +3 | Randerson Leal | Podemos | 12 | 102 | 35 | 0 | 1 | 0 | 45 | 21 | 0 | 1 | 132.8 | 132.8 | 0 |
| 6 | 6 | +0 | Sandro Filho | PP | 12 | 102 | 29 | 0 | 0 | 1 | 48 | 24 | 0 | 1 | 117.8 | 117.8 | 0 |
| 8 | 4 | +4 | Débora Santana | PSDB | 12 | 95 | 33 | 0 | 3 | 8 | 42 | 9 | 0 | 4 | 130.0 | 130.0 | 0 |
| 9 | 13 | -4 | Cezar Leite | PL | 12 | 56 | 19 | 1 | 3 | 6 | 14 | 13 | 0 | 4 | 73.2 | 73.2 | 0 |
| 10 | 10 | +0 | Eliete Paraguassu | PSOL | 12 | 55 | 18 | 2 | 3 | 7 | 18 | 7 | 0 | 4 | 77.5 | 77.5 | 0 |
| 11 | 7 | +4 | Jorge Araújo | PP | 12 | 53 | 35 | 0 | 0 | 0 | 18 | 0 | 0 | 0 | 114.0 | 114.0 | 0 |
| 12 | 16 | -4 | Marta Rodrigues | PT | 12 | 51 | 10 | 0 | 1 | 34 | 2 | 4 | 0 | 3 | 60.0 | 60.0 | 0 |
| 13 | 12 | +1 | Isabela Sousa | Cidadania | 12 | 48 | 20 | 0 | 1 | 6 | 18 | 3 | 0 | 1 | 73.8 | 73.8 | 0 |
| 14 | 21 | -7 | João Cláudio Bacelar | Podemos | 12 | 46 | 8 | 0 | 3 | 2 | 31 | 2 | 0 | 5 | 41.5 | 41.5 | 0 |
| 15 | 31 | -16 | Roberta Caires | Republicanos | 12 | 43 | 2 | 0 | 3 | 5 | 26 | 7 | 0 | 3 | 25.8 | 25.8 | 0 |
| 15 | 22 | -7 | Sílvio Humberto | PSB | 12 | 43 | 3 | 0 | 3 | 22 | 12 | 3 | 0 | 3 | 37.8 | 37.8 | 0 |
| 17 | 18 | -1 | Anderson Ninho | PSDB | 12 | 38 | 16 | 0 | 3 | 6 | 12 | 1 | 0 | 4 | 57.2 | 57.2 | 0 |
| 17 | 14 | +3 | Claudio Tinoco | União | 12 | 38 | 22 | 0 | 2 | 3 | 3 | 8 | 0 | 10 | 65.0 | 65.0 | 0 |
| 17 | 28 | -11 | Téo Senna | PSDB | 12 | 38 | 2 | 0 | 1 | 25 | 1 | 9 | 0 | 4 | 30.2 | 30.2 | 0 |
| 20 | 43 | -23 | Carlos Muniz | PSDB | 12 | 36 | 1 | 0 | 27 | 7 | 0 | 1 | 0 | 27 | 10.2 | 10.2 | 0 |
| 21 | 19 | +2 | Kênio Rezende | PRD | 12 | 35 | 10 | 0 | 1 | 17 | 5 | 2 | 0 | 2 | 49.8 | 49.8 | 0 |
| 22 | 25 | -3 | George Gordinho da Favela | PP | 12 | 31 | 8 | 0 | 3 | 3 | 10 | 7 | 0 | 3 | 33.8 | 33.8 | 0 |
| 23 | 29 | -6 | Maurício Trindade | PP | 12 | 28 | 8 | 0 | 3 | 6 | 10 | 1 | 0 | 5 | 29.2 | 29.2 | 0 |
| 24 | 9 | +15 | Beca | Republicanos | 11 | 27 | 26 | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 78.0 | 85.1 | 0 |
| 25 | 23 | +2 | Marcelle Moraes | União | 12 | 26 | 9 | 0 | 0 | 4 | 13 | 0 | 0 | 0 | 37.5 | 37.5 | 0 |
| 26 | 26 | +0 | Julio Santos | Republicanos | 12 | 25 | 6 | 0 | 2 | 12 | 4 | 1 | 0 | 2 | 32.2 | 32.2 | 0 |
| 27 | 38 | -11 | Orlando Palhinha | União | 11 | 22 | 1 | 0 | 2 | 5 | 14 | 0 | 0 | 2 | 15.0 | 16.4 | 0 |
| 28 | 15 | +13 | David Rios | MDB | 12 | 21 | 21 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 63.0 | 63.0 | 0 |
| 28 | 24 | +4 | Marcelo Guimarães Neto | União | 12 | 21 | 12 | 0 | 1 | 1 | 6 | 1 | 0 | 3 | 34.2 | 34.2 | 0 |
| 28 | 33 | -5 | Ricardo Almeida | DC | 12 | 21 | 5 | 0 | 3 | 8 | 5 | 0 | 0 | 4 | 25.0 | 25.0 | 0 |
| 31 | 11 | +20 | Alberto Braga | União | 2 | 20 | 2 | 0 | 3 | 3 | 3 | 9 | 0 | 3 | 12.8 | 76.5 | 0 |
| 31 | 32 | -1 | Duda Sanches | PSDB | 12 | 20 | 8 | 0 | 3 | 1 | 7 | 1 | 0 | 5 | 25.2 | 25.2 | 0 |
| 33 | 30 | +3 | Alexandre Aleluia | Novo | 12 | 19 | 11 | 0 | 3 | 3 | 0 | 2 | 0 | 7 | 27.2 | 27.2 | 0 |
| 33 | 43 | -10 | Daniel Alves | PSDB | 12 | 19 | 4 | 0 | 3 | 4 | 6 | 2 | 0 | 7 | 10.2 | 10.2 | 0 |
| 33 | 36 | -3 | Helio Ferreira | PCdoB | 11 | 19 | 4 | 0 | 5 | 3 | 7 | 0 | 0 | 3 | 20.5 | 22.4 | 0 |
| 33 | 35 | -2 | Ireuda Silva | Republicanos | 12 | 19 | 5 | 0 | 3 | 6 | 3 | 2 | 0 | 3 | 23.0 | 23.0 | 0 |
| 33 | 37 | -4 | Rodrigo Amaral | PSDB | 12 | 19 | 4 | 0 | 3 | 2 | 9 | 1 | 0 | 5 | 18.0 | 18.0 | 0 |
| 38 | 39 | -1 | Alex Alemão | DC | 12 | 17 | 3 | 0 | 1 | 8 | 4 | 1 | 0 | 2 | 16.2 | 16.2 | 0 |
| 38 | 34 | +4 | Omarzinho Gordilho | PDT | 12 | 17 | 7 | 0 | 3 | 2 | 3 | 2 | 0 | 4 | 24.8 | 24.8 | 0 |
| 40 | 27 | +13 | Cris Correia | PSDB | 12 | 15 | 10 | 0 | 2 | 1 | 2 | 0 | 0 | 2 | 32.0 | 32.0 | 0 |
| 40 | 40 | +0 | Kiki Bispo | União | 12 | 15 | 2 | 0 | 3 | 5 | 3 | 2 | 0 | 3 | 13.0 | 13.0 | 0 |
| 40 | 40 | +0 | Sidninho | PP | 12 | 15 | 1 | 0 | 2 | 9 | 2 | 1 | 0 | 3 | 13.0 | 13.0 | 0 |
| 43 | 40 | +3 | Paulo Magalhães Júnior | União | 12 | 13 | 3 | 0 | 3 | 1 | 6 | 0 | 0 | 3 | 13.0 | 13.0 | 0 |
| 44 | 16 | +28 | Luiz Carlos | Republicanos | 2 | 11 | 1 | 0 | 1 | 6 | 1 | 2 | 0 | 1 | 10.0 | 60.0 | 0 |
| 45 | 45 | +0 | Fábio Souza | PRD | 12 | 3 | 2 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 7.0 | 7.0 | 0 |

## Ranking 2026 (YTD, até 2026-10-28)

44 vereadores com pelo menos uma proposição como 1º autor; 1518 proposições, 112 excluídas por regex.

- Top-5 por **volume bruto**: Sandro Filho (272); Felipe Santana (240); André Fraga (148); Marta Rodrigues (80); Hamilton Assis (77).
- Top-5 por **volume ponderado / 12 meses**: Felipe Santana (284.6); André Fraga (168.0); Isabela Sousa (132.6); Sandro Filho (132.3); Hamilton Assis (78.6).

`Δ posto` = posto bruto − posto ponderado (positivo = sobe quando indicações/moções/honrarias são descontadas). Ordenado pelo volume bruto.

| # bruto | # pond. | Δ posto | vereador | partido | meses | total | PLE | PLC+PEL+PDL | PRE | REP+RUP | PIN | MOC | outros | excl. regex | vol. pond. | vol. pond./12m | coaut. |
|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 4 | -3 | Sandro Filho | PP | 10 | 272 | 3 | 0 | 0 | 0 | 153 | 116 | 0 | 6 | 110.2 | 132.3 | 0 |
| 2 | 1 | +1 | Felipe Santana | PSD | 8 | 240 | 25 | 0 | 1 | 42 | 137 | 35 | 0 | 8 | 189.8 | 284.6 | 0 |
| 3 | 2 | +1 | André Fraga | PV | 10 | 148 | 28 | 0 | 3 | 1 | 116 | 0 | 0 | 4 | 140.0 | 168.0 | 0 |
| 4 | 7 | -3 | Marta Rodrigues | PT | 10 | 80 | 7 | 0 | 0 | 34 | 10 | 29 | 0 | 9 | 56.5 | 67.8 | 0 |
| 5 | 5 | +0 | Hamilton Assis | PSOL | 10 | 77 | 12 | 1 | 2 | 13 | 17 | 32 | 0 | 3 | 65.5 | 78.6 | 0 |
| 6 | 8 | -2 | Aladilce Souza | PCdoB | 10 | 75 | 4 | 1 | 1 | 22 | 11 | 36 | 0 | 8 | 49.2 | 59.1 | 0 |
| 7 | 3 | +4 | Isabela Sousa | Cidadania | 10 | 66 | 31 | 0 | 1 | 1 | 33 | 0 | 0 | 1 | 110.5 | 132.6 | 0 |
| 8 | 6 | +2 | João Cláudio Bacelar | Podemos | 10 | 51 | 15 | 0 | 1 | 3 | 26 | 6 | 0 | 1 | 62.5 | 75.0 | 0 |
| 9 | 12 | -3 | Sílvio Humberto | PSB | 10 | 37 | 8 | 0 | 3 | 10 | 12 | 4 | 0 | 4 | 38.0 | 45.6 | 0 |
| 10 | 20 | -10 | Eliete Paraguassu | PSOL | 10 | 35 | 5 | 0 | 2 | 2 | 19 | 7 | 0 | 2 | 28.2 | 33.9 | 0 |
| 10 | 18 | -8 | Kel Torres | Republicanos | 10 | 35 | 7 | 0 | 1 | 3 | 4 | 20 | 0 | 1 | 31.0 | 37.2 | 0 |
| 12 | 26 | -14 | Tiago Queiroz | PP | 6 | 34 | 0 | 0 | 0 | 1 | 5 | 28 | 0 | 0 | 10.5 | 21.0 | 0 |
| 13 | 11 | +2 | Randerson Leal | Podemos | 10 | 33 | 11 | 0 | 2 | 1 | 13 | 6 | 0 | 3 | 39.0 | 46.8 | 0 |
| 14 | 13 | +1 | Alex Alemão | DC | 10 | 30 | 8 | 0 | 2 | 4 | 16 | 0 | 0 | 1 | 37.0 | 44.4 | 0 |
| 15 | 42 | -27 | Carlos Muniz | PSDB | 10 | 27 | 1 | 0 | 26 | 0 | 0 | 0 | 0 | 26 | 3.0 | 3.6 | 0 |
| 15 | 9 | +6 | Ricardo Almeida | DC | 10 | 27 | 13 | 0 | 3 | 2 | 6 | 3 | 0 | 3 | 44.8 | 53.7 | 0 |
| 17 | 16 | +1 | Marcelo Guimarães Neto | União | 10 | 25 | 9 | 0 | 3 | 1 | 10 | 2 | 0 | 3 | 33.5 | 40.2 | 0 |
| 18 | 21 | -3 | Téo Senna | PSDB | 10 | 22 | 4 | 0 | 1 | 12 | 1 | 4 | 0 | 1 | 25.5 | 30.6 | 0 |
| 19 | 14 | +5 | Cezar Leite | PL | 10 | 21 | 10 | 0 | 3 | 3 | 5 | 0 | 0 | 3 | 35.5 | 42.6 | 0 |
| 20 | 24 | -4 | Omarzinho Gordilho | PDT | 10 | 17 | 5 | 0 | 0 | 1 | 3 | 8 | 0 | 0 | 19.5 | 23.4 | 0 |
| 21 | 23 | -2 | Luiz Carlos | Republicanos | 7 | 14 | 3 | 0 | 2 | 3 | 3 | 3 | 0 | 2 | 14.2 | 24.4 | 0 |
| 22 | 19 | +3 | Marcelle Moraes | União | 10 | 12 | 10 | 0 | 0 | 0 | 1 | 1 | 0 | 0 | 30.8 | 36.9 | 0 |
| 23 | 27 | -4 | Daniel Alves | PSDB | 10 | 11 | 7 | 0 | 1 | 1 | 1 | 1 | 0 | 3 | 16.8 | 20.1 | 0 |
| 23 | 17 | +6 | David Rios | MDB | 10 | 11 | 11 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 33.0 | 39.6 | 0 |
| 23 | 36 | -13 | Sandro Bahiense | PP | 7 | 11 | 1 | 0 | 3 | 0 | 7 | 0 | 0 | 4 | 3.5 | 6.0 | 0 |
| 26 | 24 | +2 | Helio Ferreira | PCdoB | 10 | 10 | 6 | 0 | 2 | 1 | 1 | 0 | 0 | 2 | 19.5 | 23.4 | 0 |
| 26 | 22 | +4 | Maurício Trindade | PP | 10 | 10 | 7 | 0 | 0 | 2 | 1 | 0 | 0 | 0 | 23.5 | 28.2 | 0 |
| 28 | 34 | -6 | Kiki Bispo | União | 10 | 9 | 1 | 0 | 0 | 1 | 4 | 3 | 0 | 0 | 6.8 | 8.1 | 0 |
| 29 | 29 | +0 | Alexandre Aleluia | Novo | 10 | 7 | 4 | 0 | 1 | 1 | 0 | 1 | 0 | 1 | 13.2 | 15.9 | 0 |
| 29 | 10 | +19 | Carlos Kleber | PSD | 3 | 7 | 4 | 0 | 0 | 0 | 1 | 2 | 0 | 0 | 13.0 | 52.0 | 0 |
| 29 | 38 | -9 | Débora Santana | PSDB | 10 | 7 | 0 | 0 | 2 | 3 | 2 | 0 | 0 | 2 | 4.0 | 4.8 | 0 |
| 29 | 28 | +1 | George Gordinho da Favela | PP | 5 | 7 | 2 | 0 | 0 | 0 | 3 | 2 | 0 | 0 | 8.0 | 19.2 | 0 |
| 29 | 15 | +14 | Jorge Araújo | PP | 4 | 7 | 4 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 13.5 | 40.5 | 0 |
| 29 | 30 | -1 | Paulo Magalhães Júnior | União | 10 | 7 | 2 | 0 | 1 | 2 | 2 | 0 | 0 | 1 | 9.0 | 10.8 | 0 |
| 35 | 33 | +2 | Anderson Ninho | PSDB | 10 | 6 | 2 | 0 | 1 | 0 | 3 | 0 | 0 | 1 | 7.5 | 9.0 | 0 |
| 36 | 43 | -7 | Duda Sanches | PSDB | 10 | 5 | 3 | 0 | 0 | 1 | 0 | 1 | 0 | 3 | 1.2 | 1.5 | 0 |
| 36 | 30 | +6 | Orlando Palhinha | União | 10 | 5 | 3 | 0 | 2 | 0 | 0 | 0 | 0 | 2 | 9.0 | 10.8 | 0 |
| 36 | 41 | -5 | Rodrigo Amaral | PSDB | 10 | 5 | 0 | 0 | 0 | 3 | 1 | 1 | 0 | 1 | 3.2 | 3.9 | 0 |
| 39 | 30 | +9 | Fábio Souza | PRD | 10 | 4 | 3 | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 9.0 | 10.8 | 0 |
| 39 | 35 | +4 | Ireuda Silva | Republicanos | 10 | 4 | 1 | 0 | 0 | 2 | 1 | 0 | 0 | 0 | 5.5 | 6.6 | 0 |
| 41 | 44 | -3 | Cris Correia | PSDB | 10 | 2 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 2 | 0.0 | 0.0 | 0 |
| 41 | 37 | +4 | Kênio Rezende | PRD | 8 | 2 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 3.5 | 5.2 | 0 |
| 41 | 38 | +3 | Roberta Caires | Republicanos | 10 | 2 | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 4.0 | 4.8 | 0 |
| 44 | 40 | +4 | Julio Santos | Republicanos | 3 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 1.0 | 4.0 | 0 |

## Outros autores (fora do ranking de vereadores)

| autor | ano | proposições | por tipo |
|---|---:|---:|---|
| Executivo Municipal | 2025 | 32 | PLE 20, VTO 7, PLC 5 |
| Mesa Executiva | 2025 | 19 | PRE 14, PLE 4, PDL 1 |
| Mesa Executiva | 2026 | 18 | PRE 14, PLE 3, PDL 1 |
| Executivo Municipal | 2026 | 11 | PLE 9, PLC 2 |
| Comissão de Legislação Participativa | 2026 | 3 | PIN 3 |

## Situação das proposições de 2025 — **snapshot** de 27/10/2026, não é taxa de aprovação

O campo `Situação` do grid é só o estado atual do processo; o desfecho (Aprovado / Sancionado / lei) está na tramitação (`prop_interna_tram`), ainda não coletada. Distribuição geral das proposições de vereadores do ano:

| situação | n | % |
|---|---:|---:|
| Encaminhado | 798 | 40.2% |
| Armazenado | 758 | 38.1% |
| Redistribuido | 100 | 5.0% |
| Aguardando Deliberação | 65 | 3.3% |
| Designado Relator | 61 | 3.1% |
| Ordem do Dia | 54 | 2.7% |
| Aguardando Designacao do Relator | 44 | 2.2% |
| Diligência | 40 | 2.0% |
| Aguardando Parecer | 39 | 2.0% |
| Arquivado | 11 | 0.6% |
| Anexado Recurso | 10 | 0.5% |
| Expedido | 2 | 0.1% |
| Aguardando Assinatura | 1 | 0.1% |
| Anexado CI | 1 | 0.1% |
| Aguardando Sancao/Promulgacao | 1 | 0.1% |
| Anexado Estudo Técnico | 1 | 0.1% |
| Protocolado | 1 | 0.1% |

Por vereador, só projetos (PLE, PLC, PEL, PDL, PRE — os que tramitam em comissão e Plenário; indicações e moções vão para `Encaminhado`/`Armazenado` por construção):

| vereador | projetos | Encaminhado | Armazenado | em comissão | Plenário | pós-aprovação | Arquivado |
|---|---:|---:|---:|---:|---:|---:|---:|
| André Fraga | 42 | 6 | 1 | 27 | 7 | 0 | 1 |
| Hamilton Assis | 39 | 5 | 8 | 22 | 4 | 0 | 0 |
| Débora Santana | 36 | 5 | 6 | 15 | 10 | 0 | 0 |
| Randerson Leal | 36 | 3 | 14 | 13 | 4 | 0 | 1 |
| Jorge Araújo | 35 | 2 | 5 | 21 | 7 | 0 | 0 |
| Sandro Filho | 29 | 1 | 8 | 12 | 6 | 0 | 0 |
| Carlos Muniz | 28 | 25 | 0 | 1 | 2 | 0 | 0 |
| Beca | 27 | 1 | 6 | 15 | 5 | 0 | 0 |
| Claudio Tinoco | 24 | 5 | 1 | 14 | 4 | 0 | 0 |
| Felipe Santana | 24 | 6 | 4 | 11 | 1 | 0 | 1 |
| Cezar Leite | 23 | 8 | 0 | 11 | 3 | 0 | 0 |
| Eliete Paraguassu | 23 | 9 | 6 | 5 | 1 | 0 | 0 |
| David Rios | 21 | 0 | 1 | 16 | 4 | 0 | 0 |
| Isabela Sousa | 21 | 3 | 2 | 13 | 3 | 0 | 0 |
| Anderson Ninho | 19 | 4 | 6 | 7 | 2 | 0 | 0 |
| Kel Torres | 19 | 4 | 3 | 12 | 0 | 0 | 0 |
| Aladilce Souza | 18 | 5 | 3 | 7 | 3 | 0 | 0 |
| Alexandre Aleluia | 14 | 3 | 2 | 7 | 2 | 0 | 0 |
| Marcelo Guimarães Neto | 13 | 4 | 2 | 4 | 3 | 0 | 0 |
| Cris Correia | 12 | 2 | 0 | 8 | 1 | 0 | 1 |
| Duda Sanches | 11 | 4 | 1 | 0 | 6 | 0 | 0 |
| George Gordinho da Favela | 11 | 4 | 1 | 1 | 5 | 0 | 0 |
| João Cláudio Bacelar | 11 | 4 | 1 | 4 | 2 | 0 | 0 |
| Kênio Rezende | 11 | 1 | 2 | 6 | 2 | 0 | 0 |
| Marta Rodrigues | 11 | 2 | 1 | 8 | 0 | 0 | 0 |
| Maurício Trindade | 11 | 2 | 3 | 5 | 1 | 0 | 0 |
| Omarzinho Gordilho | 10 | 5 | 3 | 2 | 0 | 0 | 0 |
| Helio Ferreira | 9 | 6 | 1 | 2 | 0 | 0 | 0 |
| Marcelle Moraes | 9 | 3 | 3 | 1 | 2 | 0 | 0 |
| Ireuda Silva | 8 | 5 | 3 | 0 | 0 | 0 | 0 |
| Julio Santos | 8 | 1 | 2 | 3 | 2 | 0 | 0 |
| Ricardo Almeida | 8 | 5 | 1 | 2 | 0 | 0 | 0 |
| Daniel Alves | 7 | 4 | 0 | 3 | 0 | 0 | 0 |
| Rodrigo Amaral | 7 | 5 | 1 | 1 | 0 | 0 | 0 |
| Paulo Magalhães Júnior | 6 | 6 | 0 | 0 | 0 | 0 | 0 |
| Sílvio Humberto | 6 | 4 | 1 | 0 | 1 | 0 | 0 |
| Alberto Braga | 5 | 3 | 0 | 1 | 1 | 0 | 0 |
| Kiki Bispo | 5 | 3 | 2 | 0 | 0 | 0 | 0 |
| Roberta Caires | 5 | 3 | 1 | 1 | 0 | 0 | 0 |
| Alex Alemão | 4 | 2 | 1 | 1 | 0 | 0 | 0 |
| Orlando Palhinha | 3 | 3 | 0 | 0 | 0 | 0 | 0 |
| Sidninho | 3 | 3 | 0 | 0 | 0 | 0 | 0 |
| Téo Senna | 3 | 2 | 0 | 1 | 0 | 0 | 0 |
| Fábio Souza | 2 | 0 | 1 | 0 | 1 | 0 | 0 |
| Luiz Carlos | 2 | 1 | 0 | 1 | 0 | 0 | 0 |

`em comissão` = Designado Relator, Aguardando Designação do Relator, Redistribuído, Aguardando Parecer, Diligência; `Plenário` = Ordem do Dia, Pauta, Aguardando Deliberação; `pós-aprovação` = Redação Final, Aguardando Sanção/Promulgação, Aguardando Publicação, Aprovado, Sancionado, Promulgado.

## Ressalvas

- **Primeiro autor** (RI art. 179): o campo *Autor* do grid traz um nome só em 100% das proposições 2025-26 (nenhum `|`), logo `co_autorias` é 0 para todos — a coautoria, quando existe, não é publicada no grid; a coluna `Autor/Requerente/Vistas/Outros` (`outros_fonte`) registra pedidos de vista/relatoria (Alexandre Aleluia 315), não coautoria.
- **Indicações e moções inflam** (spike §4.2): PIN + MOC são mais da metade do volume bruto; por isso a leitura deve ser sempre pelos dois rankings lado a lado, e os pesos v0 são hipótese versionada, não verdade.
- **Exclusões por regex** têm falsos positivos/negativos conhecidos (ver §Método) e só olham a ementa; indicações de nome de logradouro que não usam 'denomina'/'nome de' não são capturadas.
- **PRE não honorífico** vale 1 (hipótese v0: só 4 casos em 2025-26); PRE de honraria vale 0 pela exclusão.
- **2026 é parcial**: proposições até 27/10/2026 e meses em exercício até outubro; `vol_ponderado_12m` anualiza, mas o fim de ano legislativo (dez.) costuma concentrar protocolos.
- **Meses em exercício** vêm da grade de frequência coletada (até a 44ª ordinária de 2026); suplentes com poucos meses têm `vol_ponderado_12m` muito sensível (Carlos Kleber, Dr. José Antônio, Tiago Queiroz, Sandro Bahiense). Vereador com proposição mas sem linha na grade no ano fica com `n/d`.
- **Taxa de aprovação não é mensurável** neste snapshot; `Situação` é estado atual, não desfecho. Fase seguinte: crawl de `prop_interna_tram` por coorte de ano (spike §3.2).
- A data `movimentado` é a da última movimentação, não a do protocolo; o ano da coorte é o do código (`-/2025`).
