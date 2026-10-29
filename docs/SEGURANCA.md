# Segurança dos dados e do repositório

O spot expõe nome, cargo e salário de quem trabalha nos gabinetes e o uso de dinheiro público por cada
vereador. Parte das pessoas expostas preferiria não estar. Por isso o projeto parte de duas premissas:
alguém vai tentar apagar ou adulterar os dados, e alguém vai tentar gerar custo para quem mantém o projeto.

## Quem pode o quê

| Recurso | Leitura | Escrita e exclusão |
|---|---|---|
| `gs://spot-bronze-9122a143` | só a equipe do projeto (contém CPF e dados bancários das fontes) | só a equipe |
| `gs://spot-silver-9122a143` | qualquer pessoa, sem login (`allUsers: roles/storage.objectViewer`) | só a equipe |
| `gs://spot-gold-9122a143` | qualquer pessoa, sem login | só a equipe |
| BigQuery `spot_silver`, `spot_gold` | só a equipe, por enquanto | só a equipe |
| Repositório `ThiagoFNJ/spot` | público quando for aberto | só por pull request revisado |

`roles/storage.objectViewer` dá apenas `storage.objects.get` e `storage.objects.list`. Não inclui criar,
sobrescrever nem apagar objetos, nem alterar permissões do bucket. Teste feito em 2026-10-29 sem credencial:

| Operação anônima | Resposta |
|---|---|
| Ler `_publicacao.json` do silver | 200 |
| Listar objetos do silver | 200 |
| Criar objeto no silver | 401 |
| Sobrescrever objeto no gold | 403 |
| Apagar objeto no gold | 401 |
| Ler o bronze | 403 |

## Defesa contra exclusão ou adulteração

Mesmo que uma credencial da equipe vaze, os dados podem ser recuperados:

- **Versionamento** nos três buckets. Sobrescrever um objeto guarda a versão anterior.
- **Soft delete de 90 dias** nos três buckets, o máximo que o GCS permite. Um objeto apagado, ou uma versão
  antiga, pode ser restaurado por 90 dias com `gcloud storage restore`.
- **Limite de versões** no silver e no gold: cada objeto guarda as 30 versões mais recentes, e versões antigas
  são removidas após um ano. O bronze guarda todas, porque é a prova de origem.
- **Bronze reconstruível**: [`FONTES-BRONZE.md`](FONTES-BRONZE.md) diz como baixar de novo cada arquivo das
  fontes oficiais, e o `manifest.jsonl` traz o `sha256` de cada um.
- **Silver e gold reconstruíveis**: são gerados do bronze por código versionado. `_publicacao.json` em cada
  bucket registra quando e a partir de qual commit a última publicação saiu.

Como restaurar um objeto apagado:

```sh
gcloud storage ls --soft-deleted gs://spot-gold-9122a143/**
gcloud storage restore gs://spot-gold-9122a143/<objeto>#<geração>
```

## Defesa contra custo forçado

Leitura pública no GCS é cobrada de quem mantém o bucket (tráfego de saída). Um ataque possível é baixar os
arquivos repetidamente. O risco é limitado porque os dados são pequenos (silver 2,2 MB e gold 5,2 MB em
2026-10-29). Mesmo assim, um alerta de orçamento no projeto é recomendado. O BigQuery não tem esse problema:
quem consulta paga a própria consulta.

## O que ainda depende de ação manual

- **Proteção da master**: o GitHub só permite regras de branch em repositório privado no plano Pro. Quando o
  repositório ficar público, aplicar: pull request obrigatório, sem force push, sem exclusão da master, valendo
  também para administradores.
- **Alerta de orçamento**: ativar a Cloud Billing Budget API e criar o alerta no console de faturamento.
- **Logs de escrita no GCS**: ativar os Data Access logs (`DATA_WRITE`) de `storage.googleapis.com` no projeto,
  para saber quem criou ou apagou cada objeto. Leituras públicas ficam de fora para não gerar volume.
- **Credenciais**: verificação em duas etapas na conta Google e no GitHub. Automação (CI, Cloud Run Job) com
  conta de serviço própria e federação de identidade, sem chave JSON de longa duração.
- **BigQuery público**: liberar leitura para qualquer conta Google autenticada nos dois datasets.
