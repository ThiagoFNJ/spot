# Adendo ao HANDOVER — reconciliação com o spike e teste ao vivo (2026-10-27)

Cruzamento do `HANDOVER.md` (exploração manual de 16/10 via navegador) com o spike (`docs/spike/`) e com um teste do fluxo HTTP da §2.3 executado **desta máquina** em 27/10 (scripts e respostas brutas em `docs/spike/evidence/handover-test/{faithful,adversarial}/`).

## 1. O que o HANDOVER acertou (confirmado com dados)

- Base de frequência: os totais do HANDOVER batem exatamente com o dump do spike de 16/10: 23.472 linhas de dados, status 20.556 / 1.420 / 1.496, 2025 = 3.871, 2026 = 1.888, soma 5.759, 50 nomes distintos em 2025–26, 18 meses com dados, março/2025 = 430 linhas (sessões 9–18), sentinelas 888 e 999 com 43 linhas cada.
- Fluxo da §2.3: funcionou **literalmente, na primeira tentativa**, a partir desta máquina (httpx, 1 req/s). Março/2025 × ordinária → total da grade 430 → CSV com 430 linhas. Export completo sem filtro → CSV com 23.516 linhas (a base cresceu 44 linhas desde 16/10; última sessão 45/2026).
- A restrição de rede da §1 vale só para o sandbox em nuvem do claude.ai. O Claude Code local alcança `45.4.247.157`, `cmsalvador.sys.inf.br` e `cms.ba.gov.br` normalmente. O scraper pode ser desenvolvido e rodado daqui.

## 2. Correções ao HANDOVER

1. **"23.941 linhas" (§2.1) não é contagem de linhas.** `steps` da barra de progresso = N + floor(N/50): 430 → 438; 23.472 → 23.941; 23.516 → 23.986. O CSV não tem linhas de grupo nem subtotal. Usar o total da grade (regex `\[\d+ a \d+ de (\d+)\]`) e a contagem de linhas do CSV; ignorar `steps`.
2. **`SC_module_export=grid` é o campo que decide entre sucesso e o erro fatal.** O spike registrou um `Fatal error: Call to undefined method LEG_SYS_frequencia_total::Calc_resumo_sc_free_group_by()` em um dos verificadores: a causa é `SC_module_export` vazio (o script `evidence/verify-scripts/sc_export.py` mandava vazio). Com `grid`, CSV e XML funcionam de forma determinística. Com vazio, o export termina as linhas e morre na fase "Resumo" do group-by; o `sc_pb_*.txt` nunca chega a `complete=true`. Logo: **o loop de polling precisa de timeout**, e a página de erro aparece no corpo do GET do passo 3.
3. **Passo 3 bloqueia e devolve corpo vazio** (0 bytes, 0,3 s para 430 linhas, 3 s para a base inteira). Quando retorna, o primeiro poll do `sc_pb_<md5>.txt` já vem `complete=true`. A fase "404 no início" não foi observada. Corpo não vazio no passo 3 = página de erro PHP.
4. **`script_case_init` indexa o estado de filtro dentro da sessão PHP.** Export com init antigo devolve as linhas filtradas sob *aquele* init; misturar inits (filtro sob A, export sob B) é o que devolve a base inteira. Capturar o init no GET e usar o mesmo em todos os POSTs da combinação, como o HANDOVER já diz.
5. **Encoding do `parm`:** o JS da página (`ajax_navigate` em `LEG_SYS_frequencia_jquery.js`) manda a string crua em UTF-8, sem percent-encoding. Tanto a forma crua quanto a percent-encoded UTF-8 do httpx funcionaram. A nota do spike sobre latin-1 no `parm` não é necessária (latin-1 não foi testado; a resposta CSV continua ISO-8859-1).
6. **`nm_label_csv`:** o botão da página usa `N` (sem cabeçalho); `S` acrescenta o cabeçalho. Os dois funcionam. O formulário `Fexport` também envia `nmgp_tp_xls`, `nmgp_tot_xls`, `nm_xml_tag`, `nm_xml_label`, `nm_json_format`, `nm_json_label` vazios; opcionais.
7. **Combinações vazias podem ser puladas sem request:** a resposta do filtro de mês já lista só os tipos com dados (março/2025 → só `1##@@Sessão Ordinária`), via `nm_proc_int_search('link','nn','Tipo de Sessão','pre_tse_codigo','<código>##@@…')`. Março/2025 × solene e × extraordinária retornam `[1 a 0 de 0]`.
8. **Constantes de sanity check envelhecem:** hoje 2025+2026 = 3.871 + 1.932 = 5.803 e o filtro de mês tem 86 opções até 2026-10. Calcular o esperado a partir do total da grade sem filtro no momento da execução, não de constantes.
9. **Dump HTML vs CSV:** `muda_qt_linhas=30000` e o export CSV deram as mesmas 430 tuplas na mesma ordem. CSV tem 17,7 KB contra 573 KB do HTML. Com `SC_module_export=grid` fixado, o CSV por mês × tipo (HANDOVER) é o caminho primário; o dump HTML fica como fallback.
10. **Join com o catálogo de sessões:** o filtro de mês da frequência coloca a sessão 9/2025 em março (10 sessões), mas `LEG_SYS_sessao_ata` filtrado por 03/2025 lista só as sessões 10–18 (9 dias distintos). A data de cada sessão deve vir do catálogo por `(ano, tipo, nº)`, e o mês do filtro da frequência não deve ser usado como mês da sessão.

## 3. Itens do HANDOVER que o spike já resolveu

| HANDOVER | Estado após o spike |
|---|---|
| §1 produtividade "não explorado" | `https://cmsalvador.sys.inf.br/cl/prop_interna/` exporta CSV único com 31.756 proposições (2004–2026) por POST `nmgp_opcao=csv`; tramitação por proposição abre por GET na mesma sessão PHP (desfecho, lei, página do DOM). Os resumos `LEG_SYS_produtividade_parlamentar_proposicao` (por autor × ano × tipo) e `LEG_SYS_produtividade_parlamentar` (pareceres/relatorias) saem via `ajax_navigate&opc=resumo_search`; o `export_ctrl` desses apps falha. Ver spike §3.2. |
| §1 financeiro "não explorado" | Verba compensatória (R$ 39 mil/mês, Lei 9.922/2025) com empenho por vereador em `https://cmsalvador.sys.inf.br/ca/gridRegistroEmpenho/` (POST `muda_qt_linhas=500` + `fast_search`); subsídio R$ 26.080,98 (Lei 9.825/2024); SIGA mensal em PDF. Spike §3.3. |
| §1 leismunicipais | 403 Cloudflare. Leis sancionadas vêm da tramitação do `prop_interna` e do DOM via API `https://portal-api.dioly.com.br/api/diarios/`. |
| §4 "validar se o PDF de RH traz lotação e símbolo" | Traz. Colunas: Matrícula, Servidor, Regime, Função (`ASSESSOR PARLAMENTAR-G-16 CC10`), Admissão, Centro de Custo (`10679961 - GAB. VER. ANDRE FRAGA`), Total de Proventos. Set/2025 parseado com pdfplumber: 999 linhas, 716 servidores, 42 gabinetes, R$ 4,63 mi/mês. Parser em `docs/spike/evidence/custo/scripts/parse_rh.py`; saída em `custo/gabinetes_set2025.csv`. Dois layouts (Excel→PDF até nov/2025; iText de dez/2025 em diante). 2026 continua sem publicação. |
| §2.5 chave de junção manual entre fontes | Especificação da tabela `vereador_alias` (grade, comissão, ata, empenho, centro de custo) no spike §3.3. |
| §5 "Licenciado fora do denominador (a confirmar)" | Base regimental: RI art. 17 §7 II e LOM art. 27. Confirmado. Detalhe adicional: a grade não distingue sessão encerrada por falta de quórum (RI art. 25); só a ata diz. |

## 4. Próximos passos revisados

1. `scrape_frequencia.py` conforme §2.3 do HANDOVER **com as correções 2, 3, 4 e 7 acima**; sanity check = total da grade sem filtro. Base de referência para teste: `docs/spike/evidence/handover-test/faithful/run1/2025-03_tipo1.csv` (430 linhas).
2. `scrape_sessoes.py` sobre `LEG_SYS_sessao_ata` (mesmo padrão `ajax_navigate`, campos `ses_tse_codigo` e `mes`) para obter a data por `(ano, tipo, nº)`.
3. `vereador_dim` manual (nome parlamentar → slug de `/vereadores` → nome civil → centro de custo → partido → vigência), partindo dos 50 nomes e de `custo/gabinetes_set2025.csv`.
4. Primeiro corte de presença 2025–26 (ordinárias, sem 888/999, Licenciado fora do denominador).
5. Produtividade e custo seguem o spike §3.2–3.3; o RH já tem parser.

Decisão de escopo registrada no HANDOVER e mantida: MVP = legislatura 2025–2028; histórico 2018+ na fase 2.

## 5. Correções posteriores (27/10, pipeline rodando)

- **Constante de RH do spike estava defasada.** Set/2025 tem 43 gabinetes, 733 servidores e R$ 4.757.228,61 de folha de assessores, não 42/716/R$ 4.633.426,74: o parser do spike perdeu o centro de custo 10017183 (Marta Rodrigues). Os números corretos estão em `docs/relatorios/custo-2025.md`.
- **"Total de Proventos" é remuneração bruta do mês**, sem 13º em dezembro (897 de 989 matrículas com valor idêntico entre nov e dez/2025). Não precisa de deflator; 13º, férias e encargos só existem agregados no SIGA.
- **Rótulos de suplência no PDF de RH são o cadastro atual, não o do mês** (`(SUP. VER. X)` aparece igual nos 12 PDFs de 2025). A atribuição titular/suplente por mês vem da grade de frequência.
- **Subsídio de jan/2025 sem fonte**: a Lei 9.825/2024 vigora de 1º/02/2025; o valor de janeiro (19ª legislatura) continua em aberto (§8 do spike). SIGA 06/2025 mostra 42 subsídios pagos contra 43 ocupantes no modelo; reconciliar.
- **Dados corrigidos retroativamente pela fonte** entre 16/10 e 27/10 (dois status de presença em 2026). Política em `make refresh` (CLAUDE.md).
