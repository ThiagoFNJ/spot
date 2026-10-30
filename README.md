<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/img/spot-marca-escuro.png">
    <img src="docs/img/spot-marca-claro.png" alt="Spot: uma luminária ilumina um vereador" width="347">
  </picture>
</p>

<p align="center"><strong>Vereadores de Salvador: presença, produção e custo, a partir de dados públicos.</strong><br>
<a href="https://thiagofnj.github.io/spot/">Abrir o painel</a> · <a href="https://thiagofnj.github.io/spot/#sobre">Manifesto</a></p>

# Spot

O Spot é uma iniciativa de inovação cívica para que qualquer pessoa em Salvador possa acompanhar e fiscalizar o
trabalho da Câmara Municipal (CMS). O painel mostra quem vai às sessões, o que cada vereador propõe, quanto custa
cada gabinete e como a verba compensatória é usada. O escopo atual é a legislatura 2025–2028.

O nome vem de *spotlight*. A luminária do símbolo se vira para jogar luz sobre o que já é público, mas fica
escondido em sistemas difíceis de consultar. O Spot é inspirado no **Parlametria**, que acompanha o Congresso
Nacional, e une dados e inteligência artificial para levar o mesmo tipo de acompanhamento à Câmara de Salvador.

### Todos os dados são públicos

Nada aqui vem de fonte privada, de pedido especial ou de vazamento. Tudo sai de sistemas que a própria Câmara, o
Tribunal de Contas dos Municípios (TCM-BA) e o TSE publicam:

- a grade de frequência das sessões e o catálogo de sessões e atas;
- o sistema legislativo, com as proposições e a tramitação, e o Diário Oficial do Legislativo;
- a folha de pessoal e os empenhos do portal da transparência da Câmara;
- as prestações de contas mensais enviadas ao TCM-BA (e-TCM), com os processos da verba compensatória;
- a consulta de pessoal do TCM-BA e os dados abertos do TSE sobre as eleições.

A lista completa de fontes, com endereço, data de coleta e método, está em
[`docs/FONTES-BRONZE.md`](docs/FONTES-BRONZE.md). No painel, cada número aponta para a fonte e a norma de origem.

### O papel do Spot: tratar e cruzar

O Spot não produz dado novo e não faz juízo sobre ninguém. O trabalho é transformar dado em informação. Ele coleta
o que está espalhado em planilhas, telas de consulta e PDFs escaneados, padroniza nomes e datas e cruza as fontes.
Assim, a presença de um vereador fica ao lado do que ele propôs e do custo do seu gabinete. Os números saem de
regras fixas e testadas, aplicadas sempre da mesma forma aos 43 vereadores.

### Onde entra a inteligência artificial

A inteligência artificial é ferramenta de construção. Ela ajudou a escrever o código que coleta, lê e cruza os
documentos, a encontrar inconsistências entre as fontes e a desenhar o painel. O pipeline não chama modelos de IA:
cada valor exibido sai de código determinístico e tem um caminho rastreável até o documento oficial de onde veio.

### Limites

O Spot só mostra o que as fontes publicam, no ritmo em que publicam. Há meses que chegam com atraso, documentos
escaneados difíceis de ler e registros que a Câmara corrige depois. Quando uma fonte tem buraco, o painel diz isso
em vez de esconder. Presença e produção medem atividade registrada, não a qualidade do mandato. Os números são um
ponto de partida para perguntar, não um veredito.

## Como os dados estão organizados

| Camada | O que é | Onde fica | Acesso |
|---|---|---|---|
| Bronze | Arquivos brutos, imutáveis, como a fonte entregou, com manifesto de origem | Bucket no GCP | **Privado** (contém CPF e dados bancários) |
| Silver | Tabelas limpas, uma por entidade, sem CPF nem conta | Bucket no GCP (leitura pública) e dataset no BigQuery | Leitura pública no bucket; escrita só da equipe |
| Gold | Métricas por vereador, gabinete e mês, e o JSON do painel | Bucket no GCP (leitura pública) e dataset no BigQuery | Leitura pública no bucket; escrita só da equipe |
| Seeds | Tabelas curadas à mão (identidade dos vereadores, redes sociais, constantes legais, pesos) | Este repositório, `data/seeds/` | Público, revisável por PR |

O bronze é privado, mas é **reconstruível**: [`docs/FONTES-BRONZE.md`](docs/FONTES-BRONZE.md) diz onde, quando e
como cada arquivo foi obtido, e o código de coleta está todo em `src/spot/collect/`.

O pipeline trabalha em `data/` como cache local e sincroniza com o GCP (projeto na região `southamerica-east1`):

| Recurso | Nome |
|---|---|
| Bronze | `gs://spot-bronze-9122a143` (privado, versionado) |
| Silver | `gs://spot-silver-9122a143` e dataset BigQuery `spot_silver` |
| Gold | `gs://spot-gold-9122a143` (inclui `site/data/`) e dataset BigQuery `spot_gold` |

Permissões, versionamento, recuperação de dados apagados e o que ainda falta proteger: [`docs/SEGURANCA.md`](docs/SEGURANCA.md).

Silver e gold são publicados em Parquet, uma pasta por tabela, com `_publicacao.json` (data, commit e linhas).
`make publish` só envia depois de verificar que nenhuma coluna tem CPF ou dado bancário.

## Painel

O painel é uma página estática (`site/index.html`, sem build) publicada no GitHub Pages pelo workflow
`.github/workflows/pages.yml`. O HTML vem deste repositório; os JSON e as fotos vêm do bucket gold público. O
workflow roda a cada merge que mexa no painel, uma vez por dia e sob demanda (Actions → "Painel no GitHub Pages").

Para ver localmente sem rodar o pipeline:

```sh
uv run python -m spot.cloud pull-site   # baixa JSON e fotos do bucket público, sem credencial
python3 -m http.server -d site 8000      # abre em http://localhost:8000
```

## Rodando localmente

Requer Python 3.12 e [uv](https://docs.astral.sh/uv/).

```sh
uv sync
make collect   # bronze: coleta das fontes automatizadas
make etcm      # bronze: PDFs do e-TCM (lento, requer `uv run playwright install chromium`)
make parse     # silver: data/silver/*.csv
make build     # data/silver/spot.duckdb
make metrics   # gold: tabelas metrica_* e relatórios em docs/relatorios/
make site      # site/data/*.json para o painel em site/index.html
make test lint

# Com credencial do GCP (`gcloud auth application-default login`):
make pull-bronze   # baixa o bronze do bucket privado (pede acesso de leitura)
make push-bronze   # envia ao bucket o que a coleta trouxe de novo
make publish       # silver e gold: Parquet no GCS + carga no BigQuery
```

Convenções do código (layout, regras de coleta, sentinelas, política de atualização): [`CLAUDE.md`](CLAUDE.md).

## Base legal para publicar nomes e salários

O painel mostra nome, cargo e remuneração dos servidores lotados em cada gabinete. Isso se apoia em:

- **STF, Tema 483 de Repercussão Geral** (ARE 652.777, relator Min. Teori Zavascki, trânsito em julgado em
  14/08/2015). Tese: *"É legítima a publicação, inclusive em sítio eletrônico mantido pela Administração Pública,
  dos nomes dos seus servidores e do valor dos correspondentes vencimentos e vantagens pecuniárias."*
- **Lei de Acesso à Informação** (Lei 12.527/2011), art. 8º, § 3º: a informação pública deve estar em formato
  aberto e permitir acesso automatizado.
- **LGPD** (Lei 13.709/2018), art. 7º, §§ 3º e 4º: tratamento de dados tornados públicos pelo Poder Público,
  respeitadas a finalidade e o interesse público que justificaram a publicação.

O Tema 483 trata da publicação feita pelo próprio órgão. A republicação por este projeto se apoia na LGPD e no
caráter público dos dados, por isso o projeto segue estas regras:

- nunca grava ou publica CPF, agência ou conta bancária (o parser mascara esses campos antes do silver);
- não publica data de nascimento nem lista de aniversariantes de servidores;
- compara gabinetes e vereadores, não servidores individualmente;
- a finalidade é o controle social do mandato parlamentar.

## Contribuindo

Contribuições são bem-vindas: novas fontes, correções de parser, métricas e visualizações. Antes de abrir um PR,
rode `make test lint`. Fonte nova entra com coletor em `src/spot/collect/`, parser em `src/spot/parse/` e uma linha
em [`docs/FONTES-BRONZE.md`](docs/FONTES-BRONZE.md). O projeto não automatiza nem contorna captcha.

## Licença

- **Código:** [GNU AGPL-3.0](LICENSE). Forks e versões modificadas, inclusive as que rodam como serviço web,
  precisam publicar o código-fonte sob a mesma licença.
- **Dados** (silver, gold e seeds): [CC BY-SA 4.0](LICENSE-DATA). Uso livre com atribuição; obras derivadas
  sob a mesma licença.
