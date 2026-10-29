# spot

Monitoramento dos vereadores da Câmara Municipal de Salvador (CMS): presença nas sessões, produção legislativa,
custo do mandato e do gabinete, e uso da verba compensatória. Escopo atual: legislatura 2025–2028.

Tudo o que o painel mostra vem de fontes públicas oficiais (sistemas da Câmara, Diário Oficial do Legislativo,
TCM-BA). Cada número aponta para a fonte e a norma de origem.

## Como os dados estão organizados

| Camada | O que é | Onde fica | Acesso |
|---|---|---|---|
| Bronze | Arquivos brutos, imutáveis, como a fonte entregou, com manifesto de origem | Bucket no GCP | **Privado** (contém CPF e dados bancários) |
| Silver | Tabelas limpas, uma por entidade, sem CPF nem conta | Bucket no GCP e dataset no BigQuery | Leitura pública |
| Gold | Métricas por vereador, gabinete e mês, e o JSON do painel | Bucket no GCP e dataset no BigQuery | Leitura pública |
| Seeds | Tabelas curadas à mão (identidade dos vereadores, redes sociais, constantes legais, pesos) | Este repositório, `data/seeds/` | Público, revisável por PR |

O bronze é privado, mas é **reconstruível**: [`docs/FONTES-BRONZE.md`](docs/FONTES-BRONZE.md) diz onde, quando e
como cada arquivo foi obtido, e o código de coleta está todo em `src/spot/collect/`.

A migração do armazenamento local para o GCP está em andamento; hoje o pipeline ainda lê e grava em `data/`.

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
