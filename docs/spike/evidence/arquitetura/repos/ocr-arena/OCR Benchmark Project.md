# OCR Benchmark Project

Este projeto implementa uma bateria de benchmark profissional para OCR e extração documental em PDFs, com foco em execução local em uma máquina com NVIDIA RTX 4070.

## Estrutura do Projeto

```
project_root/
  README.md
  pyproject.toml
  requirements.txt
  .env.example
  configs/
    models.yaml
    benchmark.yaml
    prompts.yaml
  data/
    raw_pdfs/
    selected_pdfs/
    rendered_pages/
    references/
  outputs/
    extracted/
      <engine_name>/<pdf_name>/
    normalized/
      <engine_name>/<pdf_name>/
    semantic_eval/
    summaries/
  logs/
    runs/
    pages/
    system/
  reports/
    pdf_inventory.csv
    pdf_complexity_rank.csv
    selected_20.csv
    benchmark_by_page.csv
    benchmark_by_document.csv
    model_summary.csv
    semantic_scores.csv
    final_report.md
    final_report.html
  src/
    main.py
    config.py
    utils/
      io_utils.py
      hash_utils.py
      time_utils.py
      gpu_monitor.py
      subprocess_utils.py
      logging_utils.py
    ingestion/
      pdf_inventory.py
      pdf_sampling.py
      pdf_render.py
      pdf_features.py
    engines/
      base_engine.py
      ollama_engine.py
      tesseract_engine.py
      docling_engine.py
      marker_engine.py
      markitdown_engine.py
    evaluation/
      text_normalization.py
      structure_metrics.py
      semantic_metrics.py
      pairwise_comparison.py
      routing_recommendation.py
    orchestration/
      benchmark_runner.py
      result_aggregator.py
      report_builder.py
  notebooks/
    exploratory_analysis.ipynb
```

## Instalação

Instruções detalhadas de instalação serão fornecidas aqui.

## Uso

Exemplos de execução serão fornecidos aqui.

## Instalação

1.  **Clone o repositório:**
    ```bash
    git clone https://github.com/gutoportelaa/langchain-minicurso.git # Substitua pelo seu repositório
    cd ocr_benchmark
    ```

2.  **Crie e ative um ambiente virtual (opcional, mas recomendado):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Instale as dependências Python:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure o Ollama:**
    -   Baixe e instale o Ollama em sua máquina: [https://ollama.com/download](https://ollama.com/download)
    -   Puxe os modelos necessários (conforme `configs/models.yaml`):
        ```bash
        ollama pull richardyoung/olmocr2
        ollama pull glm-ocr
        ollama pull openbmb/minicpm-v2.5:q6_K
        ```

5.  **Instale o Tesseract OCR:**
    -   No Ubuntu/Debian:
        ```bash
        sudo apt update
        sudo apt install tesseract-ocr tesseract-ocr-por tesseract-ocr-eng
        ```
    -   Certifique-se de que o caminho para o executável do Tesseract esteja configurado corretamente em seu `.env` (ex: `TESSERACT_PATH=/usr/bin/tesseract`).

6.  **Docling, Marker, MarkItDown:**
    -   Para Docling, Marker e MarkItDown, a integração é via CLI ou API Python local. As configurações no `configs/models.yaml` e `.env.example` fornecem placeholders. Você precisará instalar e configurar essas ferramentas separadamente conforme suas documentações oficiais e habilitá-las no `configs/models.yaml`.

7.  **Configure variáveis de ambiente:**
    -   Copie `.env.example` para `.env` e preencha com suas configurações (caminhos, chaves de API, etc.):
        ```bash
        cp .env.example .env
        ```

## Uso

O script principal `main.py` pode ser executado com diferentes comandos:

**1. Inventário de PDFs:**
```bash
ocr_benchmark inventory --raw_dir /path/to/your/raw_pdfs --output reports/pdf_inventory.csv
```

**2. Seleção de 20 PDFs:**
```bash
ocr_benchmark select --inventory reports/pdf_inventory.csv --output reports/selected_20.csv
```

**3. Executar Benchmark:**
```bash
ocr_benchmark benchmark --selected_pdfs reports/selected_20.csv
```

**4. Agregação de Resultados:**
```bash
ocr_benchmark aggregate --output reports/benchmark_results.csv
```

**5. Gerar Relatório Final:**
```bash
ocr_benchmark report --aggregated_results reports/benchmark_results.csv --output reports/final_report.md
```

**6. Pipeline Completo (tudo em um):**
```bash
ocr_benchmark all --raw_dir /path/to/your/raw_pdfs --inventory_output reports/pdf_inventory.csv --selected_output reports/selected_20.csv --aggregated_output reports/benchmark_results.csv --report_output reports/final_report.md
```

Certifique-se de substituir `/path/to/your/raw_pdfs` pelo diretório real dos seus PDFs.
