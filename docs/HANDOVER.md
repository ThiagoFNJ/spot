# HANDOVER — Coleta de dados da Câmara Municipal de Salvador (CMS)

Projeto: dashboard de performance e custo dos vereadores de Salvador.
MVP: legislatura 2025–2028. Histórico desde 2018 fica para fase 2.
Este doc descreve o que já foi validado na exploração manual (2026-10-16) e como reproduzir a coleta em código.

---

## 1. Panorama das fontes

A CMS **não usa SAPL nem tem API/dados abertos**. São três sistemas distintos:

| Dimensão | URL | Tecnologia | Status da exploração |
|---|---|---|---|
| Frequência em sessões | `http://45.4.247.157/leg/salvador/LEG_SYS_frequencia/` | Scriptcase 9 ("LEG_SYS"), HTTP puro, sem domínio | **Validado** — export CSV completo funciona |
| Produtividade legislativa (proposições) | `http://45.4.247.157/leg/salvador/LEG_SYS_produtividade_parlamentar_proposicao/` | Mesmo Scriptcase | Não explorado; mesmo mecanismo de export deve servir |
| Processo legislativo (consulta de proposições) | `http://45.4.247.157/leg/salvador/consulta.html` | Mesmo Scriptcase | Não explorado |
| Discursos / atas | `http://45.4.247.157/leg/salvador/LEG_SYS_pronunciamento/`, `.../LEG_SYS_sessao_ata/` | Mesmo Scriptcase | Não explorado (fase 2) |
| Recursos Humanos (composição de gabinete) | `https://www.cms.ba.gov.br/transparencia/recursos-humanos` | Página HTML com links para PDFs mensais | Links mapeados; **nenhum PDF parseado ainda** |
| Transparência financeira (subsídio, verba indenizatória, diárias) | `https://cmsalvador.sys.inf.br/consulta.html` | Portal terceirizado | Não explorado |
| Leis sancionadas | `http://leismunicipais.com.br/camara/ba/salvador` | Terceiro | Não explorado |
| Perfil/partido/votos/patrimônio | TSE DivulgaCand 2024 (CSV oficial) | — | Não explorado (enriquecimento) |

**Restrição de rede importante:** a sessão em nuvem do Claude não alcança nenhuma dessas URLs (IP sem HTTPS bloqueado pelo proxy; `cms.ba.gov.br` retorna `CONNECT tunnel failed 403`). A coleta validada foi feita via navegador no desktop do Thiago, executando `fetch` na origem `http://45.4.247.157`. **O scraper deve rodar localmente ou em GitHub Actions**, nunca a partir do sandbox do Claude.

---

## 2. Frequência — mecanismo validado

### 2.1 O que o export entrega

Export CSV server-side devolveu a base inteira de uma vez:

- **23.941 linhas** (progress bar reportou `steps: 23941`), de 05/2018 a 09/2026
- Grão: **sessão × parlamentar**
- Colunas (apenas 4): `No. da Sessão; Ano da Sessão; Parlamentar; Status`
- Separador `;`, valores entre aspas, CRLF, **charset ISO-8859-1** (decodificar com `latin-1`, não UTF-8)
- Status observados na base completa: `Presente` 20.556 / `Ausente` 1.420 / `Licenciado` 1.496 → ausência é explícita, não precisa inferir por diferença

Exemplo das primeiras linhas:
```
"No. da Sessão";"Ano da Sessão";"Parlamentar";"Status"
"49";"2018";"J. Carlos Filho";"Presente"
"58";"2018";"Aladilce";"Presente"
```

### 2.2 Limitação crítica: o CSV não traz data nem tipo de sessão

Mês/ano (`pre_pre_data_presenca`) e tipo de sessão (`pre_tse_codigo`) existem **só como filtro** da busca interativa, não como coluna. A chave `(ano, nº sessão)` não é única entre tipos (sessões ordinárias e especiais numeram em sequências próprias).

**Solução:** iterar `mês × tipo`, aplicando os dois filtros na sessão PHP e exportando um CSV por combinação. Cada linha então ganha `(mes_ano, tipo_sessao)` do contexto do loop. Esse mecanismo foi validado para março/2025 (10 sessões ordinárias, 430 linhas = 43 × 10).

Tipos de sessão (`pre_tse_codigo`):

| código | label (tem que ir exato, com acento) |
|---|---|
| 1 | `Sessão Ordinária` |
| 2 | `Sessão Especial` |
| 3 | `Sessão Solene` |
| 4 | `Sessão Extraordinária` |

Meses com dados em 2025–2026 (do filtro da página; não há julho nem janeiro/2026 — recesso):
`2025-01 … 2025-06, 2025-08 … 2025-12, 2026-02 … 2026-06, 2026-08, 2026-09`

### 2.3 Fluxo HTTP exato (Scriptcase)

Tudo é stateful na sessão PHP (cookie `PHPSESSID`). Usar um `httpx.Client`/`requests.Session` único.

**Passo 0 — abrir a aplicação e capturar `script_case_init`**

```
GET http://45.4.247.157/leg/salvador/LEG_SYS_frequencia/
```
No HTML, extrair `name="script_case_init" value="NNNN"` (ex.: 9130, 9067). **Muda a cada carregamento da página** — foi a causa do primeiro loop ter falhado. Capturar uma vez por sessão e reutilizar em todos os POSTs seguintes.

**Passo 1 — aplicar filtro (um POST por filtro; são cumulativos)**

```
POST http://45.4.247.157/leg/salvador/LEG_SYS_frequencia/index.php
Content-Type: application/x-www-form-urlencoded

nmgp_opcao=ajax_navigate&script_case_init={INIT}&opc=interativ_search&parm={PARM}
```

Formato de `PARM` (delimitador literal `__DL__`):
```
{campo_db}__DL__{label}__DL__{tipo_obj}__DL__{valor}##@@{valor_exibido}__DL__S
```

Exemplos reais (o `S` final é `int_search_load_html`):
```
pre_pre_data_presenca__DL__Mês e Ano__DL__dh__DL__2025-04##@@04/2025 __DL__S
pre_tse_codigo__DL__Tipo de Sessão__DL__nn__DL__1##@@Sessão Ordinária__DL__S
```
Atenção ao **espaço após `04/2025`** no valor exibido do mês — está assim no HTML original.

Antes de enviar, o JS da página faz: `+` → `__NM_PLUS__`, `&` → `__NM_AMP__`, `%` → `__NM_PRC__`. Depois disso o corpo é url-encoded normalmente.

Para limpar um filtro: `tp_link='clear'` gera `{campo}__DL__{label}__DL__{tipo}__DL__clear_interativ__DL__S`. Mais simples: recarregar a página (novo `GET`) a cada combinação, o que também renova o `script_case_init`.

A resposta é JSON-like (começa com `{`), contém o HTML da grade. Para validar o filtro, procurar na resposta o regex `\[\d+ a \d+ de (\d+)\]` — é o total de linhas filtradas.

**Passo 2 — disparar o export CSV e obter o `pbmd5`**

```
POST http://45.4.247.157/leg/salvador/LEG_SYS_frequencia/LEG_SYS_frequencia_export_ctrl.php

nmgp_opcao=csv&nm_delim_line=1&nm_delim_col=1&nm_delim_dados=1&nm_label_csv=S
&nmgp_password=&SC_module_export=grid&script_case_init={INIT}
```
Resposta: página HTML de progresso. Extrair `pbmd5=([0-9a-f]{32})` (aparece no `src` de um iframe).

**Passo 3 — iniciar a geração (o iframe faz isso)**

```
GET http://45.4.247.157/leg/salvador/LEG_SYS_frequencia/index.php
  ?nmgp_opcao=csv&nm_delim_line=1&nm_delim_col=1&nm_delim_dados=1&nm_label_csv=S
  &nmgp_password=&SC_module_export=grid&script_case_init={INIT}&pbmd5={PBMD5}
```
Pode ser disparado sem aguardar o corpo (é bloqueante até terminar).

**Passo 4 — polling do progresso**

```
GET http://45.4.247.157/producao/tmp/sc_pb_{PBMD5}.txt
```
JSON:
```json
{"steps":23941,"count":23941,"message":"Arquivo gerado com sucesso",
 "link":"/producao/tmp/sc_csv_20261016133622_906_LEG_SYS_frequencia.csv",
 "md5":"dad9e3d5...","returnUrl":"./","returnOption":"volta_grid","complete":true}
```
Repetir a cada ~0,5 s até `complete == true` (404 no início é normal). Base completa levou poucos segundos.

**Passo 5 — baixar**

```
GET http://45.4.247.157{link}
```
Decodificar como `latin-1`.

Há também `LEG_SYS_frequencia_download.php?script_case_init=…&nm_tit_doc=LEG_SYS_frequencia&nm_name_doc={md5}` (botão "Baixar"), mas o `link` direto em `/producao/tmp/` funcionou.

### 2.4 Pseudocódigo do loop

```python
MESES = [
    "2025-01",
    "2025-02",
    "2025-03",
    "2025-04",
    "2025-05",
    "2025-06",
    "2025-08",
    "2025-09",
    "2025-10",
    "2025-11",
    "2025-12",
    "2026-02",
    "2026-03",
    "2026-04",
    "2026-05",
    "2026-06",
    "2026-08",
    "2026-09",
]
TIPOS = {1: "Sessão Ordinária", 2: "Sessão Especial", 3: "Sessão Solene", 4: "Sessão Extraordinária"}
BASE = "http://45.4.247.157/leg/salvador/LEG_SYS_frequencia/"

with httpx.Client(base_url=BASE, timeout=60) as c:
    for ym in MESES:
        for code, label in TIPOS.items():
            init = get_init(c)  # GET / → regex script_case_init
            y, m = ym.split("-")
            nav(c, init, f"pre_pre_data_presenca__DL__Mês e Ano__DL__dh__DL__{ym}##@@{m}/{y} __DL__S")
            n = nav(c, init, f"pre_tse_codigo__DL__Tipo de Sessão__DL__nn__DL__{code}##@@{label}__DL__S")
            if not n:
                continue  # combinação vazia
            csv_text = export_csv(c, init)  # passos 2–5
            save(f"bronze/frequencia/{ym}_tipo{code}.csv", csv_text)  # imutável, 1 arquivo por combinação
```

Sanity check: a soma das linhas de todos os arquivos de 2025–2026 deve bater com **5.759** (3.871 em 2025 + 1.888 em 2026 na base completa). Se um mês × tipo vier com o total da base inteira (~23k), o filtro não pegou — quase sempre `script_case_init` stale.

### 2.5 Sujeira já conhecida

- `"Randerson  Leal"` tem espaço duplo → normalizar whitespace nos nomes.
- Sessões nº **888** e **999** existem e estão fora da sequência (sentinelas/sessões atípicas). Tratar antes de calcular qualquer percentual — provavelmente excluir do denominador.
- 2025–2026 tem **50 nomes distintos para 43 cadeiras** → há suplentes e licenças. É obrigatória uma `vereador_dim` curada com vigência de mandato.
- Nomes são **nome parlamentar** ("Suíca Lula", "George O Gordinho da Favela"); o RH usa nome civil; o TSE usa nome de urna. A chave de junção entre fontes vai ser manual.

Lista de nomes 2025–2026 (como aparecem na fonte):
```
Aladilce, Alberto Braga, Alex Alemão, Alexandre Aleluia, Anderson Ninho, André Fraga,
Augusto Vasconcelos, Beca, Carlos Kleber, Carlos Muniz, Cezar Leite, Claudio Tinoco,
Cris Correia, Daniel Alves, David Rios, Dr. José Antônio, Duda Sanches, Débora Santana,
Eliete Paraguassu Silva, Felipe Santana, Fábio Souza, George O Gordinho da Favela,
Hélio Lula Ferreira, Ireuda Silva, Isabela Sousa, Jorge Araújo, João Cláudio Bacelar,
Júlio Santos, Kel Torres, Kiki Bispo, Kênio Rezende, Luiz Carlos, Marcelle Moraes,
Marcelo Guimarães Neto, Marta Lula Rodrigues, Maurício Trindade, Omarzinho Gordilho,
Orlando Palhinha, Paulo Magalhães Júnior, Professor Hamilton, Randerson  Leal,
Ricardo Almeida, Roberta Caires, Rodrigo Amaral, Sandro Bahiense, Sandro Filho,
Sidninho, Silvio Humberto, Tiago Queiroz, Téo Senna
```

---

## 3. Outras telas do LEG_SYS (não validadas, mesmo padrão esperado)

Todas são apps Scriptcase no mesmo host; o fluxo de `ajax_navigate` + `*_export_ctrl.php` + `pbmd5` + `/producao/tmp/sc_pb_*.txt` deve ser idêntico, trocando o prefixo da app:

- `LEG_SYS_produtividade_parlamentar_proposicao/` → `LEG_SYS_produtividade_parlamentar_proposicao_export_ctrl.php`
- `LEG_SYS_pronunciamento/`, `LEG_SYS_sessao_ata/`, `LEG_SYS_comissao/`, `LEG_SYS_mensagem/`

Primeiro passo para cada uma: `GET` na raiz da app e inspecionar os formulários `F3`, `Fexport`, `FInterat_search` (os nomes dos campos de filtro aparecem como `int_search_{campo}[]`). Verificar se o export tem mais colunas do que a grade mostra — na frequência, não tinha.

Para proposições, o ponto crítico de modelagem é separar tipo substantivo (PL, PLC, emenda) de honorífico/rotina (moção, indicação, requerimento, título de cidadão) antes de rankear.

---

## 4. Recursos Humanos (composição de gabinete)

Página: `https://www.cms.ba.gov.br/transparencia/recursos-humanos` — HTML simples, links por ano/mês.

Padrão de URL dos PDFs mensais "Relações de Servidores" (efetivos + cargos em comissão):
- 2025: `https://www.cms.ba.gov.br/uploads/rh/transparencia-{jan|fev|mar}-2025.pdf` e, de abril em diante, `https://www.cms.ba.gov.br/uploads/rh/EFETIVOS E CARGOS EM COMISSÃO ABRIL 2025.pdf` (com espaços e acentos no nome; setembro–dezembro sem til: `COMISSAO`). Fazer url-encode.
- 2024: `transparencia-{jan…dez}-2024.pdf` (março é `servidores-03-2024.pdf`)
- 2020–2022: nomes com hash `{md5}_{timestamp}.pdf` — pegar da página, não inferir
- out–dez/2019: são **`.xlsm`**, não PDF
- **2026: nenhum arquivo publicado** (seção vazia) — já é um achado de transparência; registrar.

Tabelas de referência úteis (vencimento por símbolo de cargo):
- `TABELA DE ASSESSORES PARLAMENTARES` — `https://www.cms.ba.gov.br/uploads/rh/cd4b78a5026aaff9159f31e5c5997089_1555357765.pdf`
- `ANEXO I-D RELAÇÃO DOS CARGOS EM COMISSÃO` — `https://www.cms.ba.gov.br/uploads/rh/83243ef1141e35730a9dfe926dd3ba04_1554407127.pdf`
- `Relação dos Cargos da Mesa` — `https://www.cms.ba.gov.br/uploads/rh/bc294f4e5c13bf55b22c1e23bc73b886_1618263919.pdf`

**A validar com o primeiro PDF parseado (pdfplumber):** se a relação de servidores traz coluna de **lotação/gabinete** e **símbolo do cargo**. Sem lotação, a composição por gabinete não sai dessa fonte e precisa vir do Diário Oficial (`dioly.com.br/diario/`) ou de pedido via LAI.

---

## 5. Decisões de arquitetura já tomadas

- Camadas: `bronze/` (resposta crua, 1 arquivo por fonte × combinação de filtro, imutável) → `silver/` (DuckDB + dbt-duckdb: `vereador_dim`, `sessao`, `presenca`, `proposicao`, `lotacao_gabinete`) → `gold/` (métricas por vereador × período).
- O dataset tabular versionado no repositório é parte do produto — hoje não existe para Salvador.
- Métrica de presença: % em **sessões ordinárias**, excluindo solenes/especiais do denominador e excluindo sentinelas 888/999. `Licenciado` fora do denominador (decisão a confirmar).
- Dashboard do MVP: artifact/HTML estático por enquanto; GitHub Pages depois.

---

## 6. Próximos passos sugeridos, em ordem

1. Script `scrape_frequencia.py` implementando §2.3–2.4. Rodar e conferir o sanity check de 5.759 linhas.
2. Baixar `EFETIVOS E CARGOS EM COMISSÃO DEZEMBRO 2025.pdf` e validar §4 (lotação por gabinete?).
3. Abrir `LEG_SYS_produtividade_parlamentar_proposicao/` e mapear colunas/filtros (§3).
4. Construir `vereador_dim` manualmente (nome parlamentar → nome civil → partido → vigência).
5. Primeiro corte de presença por vereador em 2025–2026.
