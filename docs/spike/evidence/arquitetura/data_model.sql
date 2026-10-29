-- Proposta de modelo (DuckDB/SQLite). Convenções: toda tabela de fato tem source_id (linhagem) e
-- as dimensões com validade temporal usam valid_from/valid_to (fechado-aberto).
CREATE TABLE source (            -- proveniência: 1 linha por documento/página bruta baixada
  source_id TEXT PRIMARY KEY,    -- sha256 do conteúdo
  url TEXT NOT NULL, fetched_at TIMESTAMP NOT NULL, http_status INT, content_type TEXT,
  raw_path TEXT NOT NULL,        -- raw/<host>/<sha256>.<ext> (arquivado, imutável)
  parser TEXT, parser_version TEXT, extracted_at TIMESTAMP, extraction_method TEXT -- 'html','pdfplumber','regex','llm:claude-haiku-5-5'
);
CREATE TABLE vereador (vereador_id TEXT PRIMARY KEY, nome_parlamentar TEXT NOT NULL, nome_civil TEXT, cpf_hash TEXT, foto_url TEXT);
CREATE TABLE vereador_alias (alias_norm TEXT PRIMARY KEY, vereador_id TEXT REFERENCES vereador); -- "TEO SENNA"/"TÉO SENNA"
CREATE TABLE legislatura (legislatura_id INT PRIMARY KEY, data_inicio DATE, data_fim DATE);
CREATE TABLE mandato (mandato_id TEXT PRIMARY KEY, vereador_id TEXT REFERENCES vereador, legislatura_id INT,
  titular BOOLEAN, valid_from DATE NOT NULL, valid_to DATE, partido_sigla TEXT, motivo_fim TEXT, source_id TEXT REFERENCES source);
CREATE TABLE sessao (sessao_id TEXT PRIMARY KEY, data DATE NOT NULL, numero INT, tipo TEXT, -- ordinaria|extraordinaria|solene|especial
  sessao_legislativa INT, legislatura_id INT, ata_url TEXT, ata_source_id TEXT REFERENCES source, quorum_minimo INT DEFAULT 14, realizada BOOLEAN);
CREATE TABLE presenca (sessao_id TEXT REFERENCES sessao, vereador_id TEXT REFERENCES vereador,
  status TEXT NOT NULL CHECK (status IN ('presente','ausente','ausencia_justificada','licenciado','afastado')),
  fonte TEXT NOT NULL, -- 'legsys_frequencia' | 'ata_regex' | 'ata_llm'
  source_id TEXT REFERENCES source, confidence REAL, PRIMARY KEY (sessao_id, vereador_id, fonte));
CREATE TABLE proposicao (proposicao_id TEXT PRIMARY KEY, tipo TEXT NOT NULL, numero INT, ano INT, ementa TEXT,
  data_apresentacao DATE, situacao_atual TEXT, url TEXT, source_id TEXT REFERENCES source);
CREATE TABLE autoria (proposicao_id TEXT REFERENCES proposicao, vereador_id TEXT REFERENCES vereador, ordem INT, primeiro_autor BOOLEAN, PRIMARY KEY (proposicao_id, vereador_id));
CREATE TABLE tramitacao (tramitacao_id TEXT PRIMARY KEY, proposicao_id TEXT REFERENCES proposicao, data DATE, unidade TEXT, status TEXT, texto TEXT, source_id TEXT REFERENCES source);
CREATE TABLE relatoria (proposicao_id TEXT, comissao TEXT, vereador_id TEXT, data_designacao DATE, data_fim DATE, parecer TEXT, source_id TEXT);
CREATE TABLE discurso (sessao_id TEXT, vereador_id TEXT, fase TEXT, ordem INT, source_id TEXT);
CREATE TABLE servidor (servidor_id TEXT PRIMARY KEY, matricula TEXT, nome TEXT, vinculo TEXT); -- comissionado|efetivo|estagiario|cedido
CREATE TABLE lotacao (servidor_id TEXT REFERENCES servidor, unidade_raw TEXT, gabinete_vereador_id TEXT REFERENCES vereador,
  cargo TEXT, valid_from DATE NOT NULL, valid_to DATE, source_id TEXT REFERENCES source, PRIMARY KEY (servidor_id, valid_from));
CREATE TABLE folha (competencia DATE NOT NULL, servidor_id TEXT REFERENCES servidor, bruto NUMERIC, liquido NUMERIC, rubricas JSON, source_id TEXT REFERENCES source, PRIMARY KEY (competencia, servidor_id));
CREATE TABLE despesa (despesa_id TEXT PRIMARY KEY, competencia DATE, vereador_id TEXT REFERENCES vereador, tipo TEXT, -- subsidio|verba_indenizatoria|cota|diaria
  valor NUMERIC, descricao TEXT, fornecedor TEXT, source_id TEXT REFERENCES source);
-- Métricas (reprodutíveis, views):
-- presenca_pct(vereador, periodo) = presentes / sessões em que tinha mandato vigente (mandato.valid_from<=sessao.data<valid_to), excluindo 'licenciado'; reportar também "faltas não justificadas".
-- produtividade(vereador, periodo) = contagens por tipo de proposicao (autoria) + relatorias + discursos + aprovadas (tramitacao.status like '%aprov%'); nunca somar tipos diferentes num único número sem pesos declarados.
-- custo_gabinete(vereador, competencia) = despesa(subsidio+verba) + SUM(folha.bruto) dos servidores com lotacao.gabinete_vereador_id = vereador vigente na competencia.
