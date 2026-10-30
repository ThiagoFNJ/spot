# Seeds curados — dimensão de vereadores (legislatura 2025–2028)

Tabelas mantidas à mão. Chave canônica = slug de `https://www.cms.ba.gov.br/vereadores/<slug>`.
Geradas em 2026-10-27 a partir de: índice vivo de `/vereadores` (bronze `data/bronze/vereadores/vereadores.html`,
113 cartões: 43 titulares + 70 ex/licenciados), 113 perfis (`<slug>.html`), snapshot do índice de 16/10/2026
(`docs/spike/evidence/custo/https___www_cms_ba_gov_br_vereadores.html`, 115 cartões), dump da grade de frequência
(`docs/spike/evidence/presenca/frequencia_full_dump.tsv`, 16/10/2026), RH set/2025 e dez/2025
(`docs/spike/evidence/custo/rh_*.csv`) e export de comissões (`docs/spike/evidence/produtividade/LEG_SYS_comissao_export.utf8.csv`).

Validação: `uv run python -m spot.parse.vereadores --check` (integridade + nomes de `data/silver/presenca.csv` sem alias)
e `uv run pytest tests/test_vereadores.py`.

## vereador_dim.csv (50 linhas)

| coluna | conteúdo |
|---|---|
| `vereador_id` | slug de `/vereadores` |
| `nome_parlamentar` | nome do cartão no índice (ex. `Hamilton Assis`, `Marta Rodrigues`) |
| `nome_civil` | da biografia do perfil quando explícita (23 casos); `Debora Santos de Santana` vem do credor do empenho citado no spike §3.3; vazio nos demais |
| `partido` | do cartão no índice |
| `situacao` | em 2026-10-27: `titular` (eleito, em exercício), `licenciado` (eleito, afastado), `suplente` (em exercício ou não — ver `observacao`); `ex` não foi necessário |
| `gabinete_cc_codigo` | código do centro de custo no RH (`<código> - GAB. VER. ...`), set/dez 2025; para suplentes que assumiram em 2026 fica vazio (RH 2026 não publicado), com o código esperado em `observacao` |
| `legislatura` | `2025-2028` |
| `fonte_url` | perfil no site; para os 2 perfis já removidos, o índice |
| `confianca` | `alta` = perfil + grade + RH coerentes; `media` = inferência (ver abaixo) |

Composição: 43 cadeiras = 38 titulares em exercício + 5 licenciados (Alberto Braga, Augusto Vasconcelos, Felipe Santana,
George Gordinho da Favela, Julio Santos) e 7 suplentes (Beca, Orlando Palhinha, Helio Ferreira, Carlos Kleber,
Sandro Bahiense em exercício; Tiago Queiroz e Dr. José Antonio já fora). 43 + 7 = os 50 nomes da grade 2025–26.

Substituições documentadas (perfil, grade ou rótulo do RH):

| titular afastado | suplente | desde | fonte |
|---|---|---|---|
| Augusto Vasconcelos (PCdoB) | Helio Ferreira | sessão 8/2025 (fev/2025) | **inferido**: grade (Augusto só nas sessões 2–7/2025) + RH `GAB. VER. HELIO FERREIRA (SUP. VER. AUGUSTO VASCONCELOS)`; perfis não mencionam — `confianca=media` |
| Luiz Carlos (Republicanos) | Beca | 24/02/2025 | perfis de ambos; Luiz Carlos voltou em abr/2026 e Beca ficou (Julio Santos saiu na sessão 14/2026) |
| Alberto Braga (União) | Orlando Palhinha | 24/02/2025 | perfis de ambos (Semit) |
| Jorge Araújo (PP) | Sandro Bahiense | sessão 17/2026 (abr/2026) | grade; motivo não publicado; Jorge voltou a ser titular no índice em 27/10/2026 — `media` |
| George Gordinho da Favela (PP) | Tiago Queiroz | mai/2026, 140 dias | perfil de George; perfil de Tiago removido do site em 27/10/2026 |
| Kênio Rezende (PRD) | Dr. José Antonio | 18/06/2026, 121 dias (grade: sessões 38–44/2026) | perfil de Kênio; retornou out/2026; perfil de Dr. José Antonio removido |
| Felipe Santana (PSD) | Carlos Kleber | 04/08/2026, 121 dias | perfis de ambos |

## vereador_alias.csv (268 linhas)

`alias` sempre com whitespace normalizado (`Randerson  Leal` na fonte → `Randerson Leal`). Sem duplicata de `(alias, fonte)`.

- `proposicao` (50): nome do autor como aparece no `prop_interna` (idêntico ao da grade de frequência nos 49
  nomes observados; Augusto Vasconcelos e Dr. José Antônio adicionados preventivamente, `confianca=media`).
  Autores não vereadores (Executivo Municipal, Mesa Executiva, comissões) não têm alias: vão para
  `produtividade_outros_autores`.
- `frequencia` (50): os 50 nomes da grade 2025–26 → slug. `valido_de`/`valido_ate` = primeiro/último mês em que o nome
  aparece no dump de 16/10/2026 (granularidade mensal; `valido_ate` vazio quando aparece no último mês do dump, set/2026).
  Regenerar a partir de `data/silver/presenca.csv` + `sessao.csv` quando houver data por sessão. Kênio Rezende tem
  `valido_ate=2026-08-31` mas voltou em out/2026: use a vigência como informativa, não como filtro rígido.
- `comissao` (40): membros de `LEG_SYS_comissao`, mesmos apelidos da grade.
- `centro_custo` (58): rótulo completo do RH (`<código> - [cargo da Mesa - ]GAB. VER. <nome>[ (SUP. ...)]`), com a
  coluna `continuacao` do parser do PDF já colada, → **ocupante** do gabinete nomeado no rótulo. Rótulos
  `GAB. VER. X (SUP. [VER.] Y)` significam "X, suplente de Y" (confirmado para Beca/Luiz Carlos e Orlando/Alberto Braga)
  e mapeiam para X; Y está em `observacao` e em `vereador_dim.gabinete_cc_codigo` (titular e suplente compartilham o código).
  Variantes de 1 linha (`... ANDERSON ROCHA NINHO`, `... PROFESSOR HAMILTON SAMPAIO`, `... JOAO CLAUDIO BACELAR CC10`)
  são vazamento da coluna vizinha na quebra de linha do PDF; estão mapeadas com `confianca=baixa` para o join não falhar.
  O rótulo de Marta Rodrigues (`10017183 - DIRETORIA DA ESCOLA DO LEGISLATIVO - GAB. VER. MARTA RODRIGUES`) falta em
  `gabinetes_set2025.csv` (42 gabinetes) pela mesma quebra de linha — o RH tem 43 gabinetes.
  Join com `data/silver/folha.csv` (que separa `centro_custo_codigo` e `centro_custo_label`): alias =
  `f"{centro_custo_codigo} - {normalize_name(centro_custo_label)}"`; verificado em 2026-10-27: os 43 pares (código, rótulo)
  `GAB. VER.` de 2025-01..2025-12 mapeiam. Para o join por código puro use `vereador_dim.gabinete_cc_codigo` (3 códigos
  compartilhados titular/suplente — atribuir por período).
- `empenho` (68): credor do `gridRegistroEmpenho` → slug, grafia exata do credor (whitespace normalizado), uma linha por
  grafia observada nos 857 empenhos de verba compensatória do snapshot 2026-10-27 (58 grafias de 50 pessoas) + 10 nomes
  civis da biografia nunca vistos como credor (mantidos, `confianca=baixa`). O credor alterna nome civil e nome
  parlamentar para a mesma pessoa (`David Rios` / `David Silva Rios`, `Rodrigo Amaral` / `Rodrigo Bahia Amaral Alves`,
  `Daniel Almeida` / `Daniel Vianna Alves de Almeida`) e tem erros de cadastro (`XXXXMARCELE MORAES`, `Isabela de Sousa
  Pereira`, `Helio Miguel de Oliveira`, `Fabio Almeida da Silva` — resolvidos pelos meses em que a grafia usual não
  aparece, `confianca=media`). `Paulo Sergio Mato Grosso de Jesus` (out/2025) e `Paulo Sérgio da Conceição Santos`
  (nov/2025) foram atribuídos a Paulo Magalhães Júnior por inferência (`confianca=baixa`; ver `observacao`).
  **Sem alias**: `Everaldo Bispo` (ex-vereador, 1 empenho de verba ago/2026, R$ 37.900) — não está em `vereador_dim`.
  `valido_de` = primeira competência observada; `valido_ate` vazio. Regenerar com o script da coleta quando houver novo
  snapshot (`uv run python -m spot.parse.empenhos` e conferir `metrica_verba_vereador` com `vereador_id` NULL).
- `etcm` (2): requerente dos processos de verba compensatória no e-TCM (`parse/etcm_vc.py`) quando nem o nome civil
  nem o nome parlamentar da dimensão casam — hoje só as grafias OCR de Theófilo Virgílio de Senna (Téo Senna).
- `ata` (0): a fazer com fuzzy match em caixa alta (spike §3.3 e).

## vereador_redes.csv (50 linhas)

Redes sociais **oficiais** de cada vereador, levantadas em **2026-10-28**. Uma linha por `vereador_id` de `vereador_dim.csv`,
mesmo sem redes. Colunas: `instagram` e `x` como URL completa (`https://www.instagram.com/<handle>/`, `https://x.com/<handle>`),
`fonte_url` (onde o perfil foi confirmado), `confianca`, `observacao`.

Origem, em ordem de precedência: (1) handles de Instagram informados pelo mantenedor (17 casos, `fonte_url` =
`informado pelo mantenedor em 2026-10-28`; parâmetros `?igsh=`/`?srtk=` removidos); (2) bio do próprio perfil, lida via busca
restrita a `instagram.com`/`x.com` ou fetch direto, citando "vereador(a)", "Salvador", partido ou Câmara; (3) link declarado ao TSE
na candidatura de 2024, via páginas O Tempo/Tribuna PR (Carlos Kleber, David Rios, Marcelle Moraes, Paulo Magalhães Jr., Roberta
Caires, Sidninho); (4) créditos de foto em A Tarde/Bahia Notícias/Aratu On, sempre confirmados depois pela bio. As biografias dos
perfis da CMS (`data/bronze/vereadores/<slug>.html`) **não** citam redes pessoais — o único link é o `@camaradesalvador` do rodapé.

Critério: só conta do próprio parlamentar (nada de fã-clube — `@leite_neles`, `@bahia_ama_keltorres` —, gabinete ou homônimo:
`@carlosmunizp` é do Recife, `@kikibispo` é dos EUA, `@DeputadoBacelar` é o pai, `@ricardo_mbl` é outro Ricardo Almeida,
`@sidinhodaong` não é Sidninho, `@MarcellMoraes_` ≠ Marcelle). `confianca` = mínima entre os handles preenchidos: `alta` (bio ou
declaração ao TSE), `media` (indício consistente sem confirmação direta), vazia quando não achou. Resultado: 49 Instagram, 24 X;
46 `alta`, 3 `media` (David Rios — perfil declarado ao TSE não carregou; Débora Santana e Helio Ferreira — X pouco ativo/pequeno),
1 sem nada (Dr. José Antonio). Marcelle Moraes tem dois perfis de Instagram com bio de vereadora; ficou o declarado ao TSE
(`@marcellecmoraes`). Sandro Filho aparece no X como `@SandroFilhoMBL` e `@SandroFilhoBA` (handle anterior); ficou o atual.
Handles mudam: reconferir antes de publicar links no site.

## verba_categorias.csv (15 linhas)

As 15 categorias de despesa da verba compensatória (incisos I a XV do art. 14 da Lei 9.828/2025, DOM 8.943 de
03/01/2025), com o numeral romano que as prestações de contas usam. `parse/etcm_vc.py` casa cada item declarado com
uma categoria por esse numeral.

## parametros_custo.csv

Constantes legais do custo do mandato: subsídio (Lei 9.825/2024), teto da verba compensatória (Lei 9.828/2025 e
alterações) e outras. Cada linha tem vigência, a norma, a URL da publicação oficial e o arquivo de evidência em
`docs/spike/evidence/`. Valor novo entra como linha nova com vigência própria, nunca sobrescrevendo a anterior.

## pesos_v0.csv

Pesos por tipo de proposição usados no índice de produtividade (`metrics/produtividade.py`). É uma escolha
editorial do projeto, não um dado de fonte; a justificativa de cada peso está na coluna `observacao` e no spike §4.2.
Mudar um peso é decisão a discutir em PR.

## mesa_diretora.csv (14 linhas)

Mesa Diretora do biênio em curso: 11 titulares (Presidente, vice-presidentes, secretários, Ouvidor) e 3 suplentes,
na ordem da página oficial `https://www.cms.ba.gov.br/mesa-diretora` (cópia em
`data/bronze/vereadores/mesa-diretora_2026-10-29.html`). `consultado_em` é a data da consulta. Atualizar quando a
Mesa mudar (eleição do biênio ou substituição).

## vereador_bloco.csv (44 linhas)

Bloco de cada vereador em exercício (`base` ou `oposicao`) e as lideranças de governo e de oposição, referência
2026-10. A Câmara não publica lista oficial de base e oposição: a bancada de oposição (10 vereadores) vem de
votações e notícias citadas em `fonte` e `fonte_url` (bahia.ba 15/10/2026, Bahia Notícias 28/10/2026); quem não
aparece nelas é marcado como base, e a coluna `fonte` diz isso. É decisão editorial: mudar um bloco se discute em PR.

## Não resolvido / atenção

- Nenhum dos 50 nomes da grade nem dos rótulos `GAB. VER.` de set/dez 2025 ficou sem mapa.
- Homônimos no índice que **não** são os titulares de 2025–28: `Alemão` (PHS) ≠ `Alex Alemão`; `Marcell Moraes` (PV)
  ≠ `Marcelle Moraes`; `Everaldo Bispo` ≠ `Kiki Bispo`; `Daniel Rios` ≠ `David Rios`; `Tiago Correia` ≠ `Tiago Queiroz`;
  `Everaldo Augusto` ≠ `Augusto Vasconcelos`; `Luizinho Sobral` ≠ `Luiz Carlos`; `Sandro Filho` ≠ `Sandro Bahiense`.
- `nome_civil` vazio para 27 vereadores (sem menção explícita no perfil). Pistas do RH não usadas por serem só
  rótulos: `CLISTENES BISPO - KIKI`, `JORGE ARAUJO REPORTER`.
- Motivo do afastamento de Augusto Vasconcelos, Julio Santos e Jorge Araújo não está publicado no perfil.
- Os rótulos de RH de jun/2024 (19ª legislatura) ficaram fora: alguns códigos mudaram de dono
  (ex. `10679962` era Augusto Vasconcelos, hoje Helio Ferreira).
- Tiago Queiroz e Dr. José Antonio não têm mais perfil no site (27/10/2026); dados vêm do índice de 16/10 e da grade.
