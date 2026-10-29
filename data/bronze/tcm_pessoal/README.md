# TCM-BA · Controle Social · Pessoal — coleta manual mensal

A consulta pública de pessoal do TCM-BA (`https://www.tcm.ba.gov.br/controle-social/pessoal/`) fica atrás de um
reCAPTCHA v2 e por decisão do projeto **não é automatizada**. Uma pessoa faz a consulta uma vez por mês e salva o
resultado aqui; `parse/tcm_pessoal.py` lê o que estiver nesta pasta.

## Passo a passo (≈2 min por mês)

1. Abrir `https://www.tcm.ba.gov.br/controle-social/pessoal/`.
2. Preencher: **Município** = SALVADOR · **Entidade** = Câmara Municipal de SALVADOR (código 749) · **Ano** · **Mês** ·
   **Tipo Regime** = Todos · **Situação** = (deixar como está) · marcar o captcha · **Pesquisar**.
3. Na página de resultado:
   - salvar a página completa (Ctrl+S / Cmd+S, "Página da Web, somente HTML") como
     `data/bronze/tcm_pessoal/<AAAA-MM>/pessoal_749_<AAAA-MM>.html`;
   - se houver botão/ícone de exportar (planilha/PDF, link `webservice.tcm.ba.gov.br/exportar/pessoal?tipo=...`),
     baixar e salvar na mesma pasta com o nome original (ex.: `pessoal_749_<AAAA-MM>.xlsx`).
4. Se a consulta tiver mais de uma página de resultados e não houver exportação, salvar cada página como
   `pessoal_749_<AAAA-MM>_p<N>.html`.

Começar por **2026-09** (último mês com folha sintética no e-TCM) e depois 2026-01..2026-08. Um mês de 2025
(ex.: 2025-12) serve para conferir contra a folha analítica do site.

## Ingestão

`uv run python -m spot.parse.tcm_pessoal --ingest ~/Downloads/*.xlsx` descobre a competência no cabeçalho da planilha
("Câmara Municipal de SALVADORMARÇO/2026"), copia para `<AAAA-MM>/pessoal_749_<AAAA-MM>.xlsx`, anota o `manifest.jsonl`
e gera `data/silver/tcm_pessoal.csv`. Cargas de 2026-10-28: jan–mar/2025 e jan–set/2026. Jul/2026 veio duas vezes com 837 linhas (contra ~1.230 nos
outros meses): o SIGA ainda não tem o mês completo; `metrics/custo.py` descarta meses com menos de 75% da mediana e
usa a folha sintética do e-TCM no lugar. Reexportar julho mais adiante substitui o arquivo (mesmo nome).

## O que a planilha traz

Colunas: Nome, Matrícula, Tipo Regime, Cargo (com grau e símbolo: `ASSESSOR PARLAMENTAR-G-13 CC10`), Salário Líquido,
Salário Base, Vantagens, Gratificação, 13º Salário, Carga H Semanal, Situação, Ingresso/Admissão. **Não há lotação**: a
matrícula é a mesma da folha do site, e `base + vantagens + gratificação` bate com o `proventos` do site em ~95% das
linhas (jan–mar/2025). Inclui Assistência Militar (não está na folha do site) e os 42 agentes políticos. CPF **não** deve ser salvo em lugar nenhum fora do bronze (que fica fora do git); se o arquivo trouxer
CPF, o parser mascara.

## Por que não automatizar

Ver `docs/fontes-candidatas.md` (TCM pessoal). Alternativa em paralelo: pedir ao TCM, via e-SIC, a inclusão de
pessoal por unidade gestora na API do SIGA (`https://www.tcm.ba.gov.br/dados-abertos/`, que hoje expõe só
municípios, unidades gestoras, publicidade e multas).
