# Verificação "produtividade" — comandos reproduzidos em 2026-10-16

UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"

## 1. CSV completo de proposições (31.756 linhas) — confirmado
curl -sL -A "$UA" -c cj.txt -b cj.txt https://cmsalvador.sys.inf.br/cl/prop_interna/ -o pi.html
SCI=$(grep -o 'script_case_init" value="[0-9]*' pi.html | head -1 | grep -o "[0-9]*$")
curl -sL -A "$UA" -b cj.txt -c cj.txt -X POST https://cmsalvador.sys.inf.br/cl/prop_interna/ \
  --data "script_case_init=$SCI&nmgp_opcao=csv&nm_delim_line=1&nm_delim_col=1&nm_delim_dados=1&nm_label_csv=S&nmgp_password=&SC_module_export=grid" -o out.html
# out.html contém window.location='/p/tmp/sc_csv_<ts>_prop_interna.csv' -> GET com o mesmo cookie

## 2. TRAMITAÇÃO POR PROPOSIÇÃO FUNCIONA COM curl (refuta "Dados inválidos")
# a) pegar os links da grade (até 500 linhas/página):
curl -sL -A "$UA" -b cj.txt -c cj.txt -X POST https://cmsalvador.sys.inf.br/cl/prop_interna/index.php \
  --data "script_case_init=$SCI&nmgp_opcao=muda_qt_linhas&nmgp_quant_linhas=500&nmgp_fast_search=SC_all_Cmp" -o pi500.html
#    ou busca rápida por número:
curl -sL -A "$UA" -b cj.txt -c cj.txt -X POST https://cmsalvador.sys.inf.br/cl/prop_interna/index.php \
  --data-urlencode "nmgp_arg_fast_search=PLE-232/2025" --data "script_case_init=$SCI&nmgp_opcao=fast_search&nmgp_fast_search=SC_all_Cmp&nmgp_cond_fast_search=qp" -o fs.html
# b) extrair o 3º argumento de nm_gp_submit5('/cl/prop_interna_tram/', '/cl/prop_interna/', '@SC_par@<sci>@SC_par@prop_interna@SC_par@<md5>', 'modal', ...)
# c) GET exatamente como o JS monta (mesmo cookie jar):
curl -sL -A "$UA" -b cj.txt -c cj.txt "https://cmsalvador.sys.inf.br/cl/prop_interna_tram/?&nmgp_outra_jan=true&nmgp_url_saida=modal&SC_lig_apl_orig=prop_interna&nmgp_opcao=grid&nmgp_parms=<PARMS>&TB_iframe=true&modal=true&height=600&width=1024" -o tram.html
# d) a tram pagina em 20; pedir 500 (SCI próprio da tram, lido do tram.html):
curl -sL -A "$UA" -b cj.txt -c cj.txt -X POST https://cmsalvador.sys.inf.br/cl/prop_interna_tram/index.php \
  --data "script_case_init=<SCI_TRAM>&nmgp_opcao=muda_qt_linhas&nmgp_quant_linhas=500" -o tram500.html
# Exemplo PLE-232/2025: 40 movimentos, inclui "Aprovado | Conforme Acordo de Lideranças, em 15/10/2025, na 68ª Sessão Ordinária"
# e "Sancionado | LEI Nº 9919/2025 - PUBLICADO NO DOM DE 18/12/2025, PG 2."

## 3. Resumos por autor x ano (ajax resumo_search) — confirmado
# script_case_init aparece dentro do JS da página (script_case_init=NNNN)
curl -sL -A "$UA" -b cjp.txt -c cjp.txt -X POST http://45.4.247.157/leg/salvador/LEG_SYS_produtividade_parlamentar_proposicao/index.php \
  --data "script_case_init=<SCI>&nmgp_opcao=ajax_navigate&opc=resumo_search&parm=TRA_TRA_DT_MOVIMENTACAO_SC_1__DL__TRA.TRA_DT_MOVIMENTACAO__DL__dth__DL__eql__DL__actual__DL__YYYY__DL__2025"
# -> JSON setValue[field=summary_body] com a tabela (2025: Aladilce 148, Felipe Santana 144, André Fraga 124; total 2.037)

## 4. dioly (DOL) — API documentada e busca full-text
https://portal-api.dioly.com.br/docs  (Swagger)  /openapi.json
GET /api/diarios/?q=<texto>&tipo=DOL&ano=&mes=&numero=&data=&page=&per_page=   -> q busca no conteúdo dos PDFs
Ex.: q="Projeto de Lei n. 283/26" -> DOL 7292; q="Sidninho" -> 1.071 edições. Front dioly.com.br/diario/ dá 406 (Mod_Security) sem UA de navegador.

## 5. Prior art: github.com/Alzarus/to-de-olho-ssa (TCC, 2024-2025) — crawlers puppeteer para prop_interna (export JSON),
# LEG_SYS_frequencia (XML), produtividade_parlamentar(_proposicao), contratos (/ca/contrato/), despesas de viagem, vereadores; API Go + Postgres.
