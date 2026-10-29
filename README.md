# spot

Monitoramento dos vereadores da Câmara Municipal de Salvador (CMS): presença nas sessões, produção legislativa,
custo do mandato e do gabinete, e uso da verba compensatória. Escopo atual: legislatura 2025–2028.

Tudo o que o painel mostra vem de fontes públicas oficiais (sistemas da Câmara, Diário Oficial do Legislativo,
TCM-BA). Cada número aponta para a fonte e a norma de origem.

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
