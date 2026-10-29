# OCR Benchmark — Relatório Comparativo

## 1. Resumo por Engine

Engines ordenados por tempo médio por página (crescente).

| engine        |   success_rate_% |   avg_time_per_page |   total_time |   avg_chars_extracted |   total_chars_extracted |   pages_processed |   pdfs_processed |
|:--------------|-----------------:|--------------------:|-------------:|----------------------:|------------------------:|------------------:|-----------------:|
| docling       |                0 |               0     |        0     |                  0    |                       0 |                 0 |               20 |
| docling_gpu   |                0 |               0     |        0     |                  0    |                       0 |                 0 |               20 |
| unlimited_ocr |                0 |               0     |        0     |                  0    |                       0 |                29 |               20 |
| olmocr2       |                0 |               0     |        0     |                  0    |                       0 |                29 |               20 |
| glm_ocr       |              100 |               3.638 |      105.516 |                 18    |                     522 |                29 |               20 |
| tesseract     |              100 |               4.462 |      129.392 |               5264.45 |                  152669 |                29 |               20 |
| minicpm_v     |              100 |             195.513 |     5669.86  |              11089.6  |                  321597 |                29 |               20 |


**Legenda:**
- `success_rate_%` — % de páginas processadas com sucesso
- `avg_time_per_page` — tempo médio por página (segundos)
- `total_time` — tempo total acumulado (segundos)
- `avg_chars_extracted` — média de caracteres extraídos por página
- `total_chars_extracted` — total de caracteres extraídos


## 2. Comparativo de Tempo por Documento (segundos)

Tempo total por engine para cada documento do benchmark.

| pdf       |   docling_time_s |   docling_gpu_time_s |   glm_ocr_time_s |   minicpm_v_time_s |   olmocr2_time_s |   tesseract_time_s |   unlimited_ocr_time_s |
|:----------|-----------------:|---------------------:|-----------------:|-------------------:|-----------------:|-------------------:|-----------------------:|
| doc1      |                0 |                    0 |             4.85 |              15.6  |                0 |               4.15 |                      0 |
| doc1.pdf  |                0 |                    0 |             0    |               0    |                0 |               0    |                      0 |
| doc10     |                0 |                    0 |             6.08 |             902.22 |                0 |               6.23 |                      0 |
| doc10.pdf |                0 |                    0 |             0    |               0    |                0 |               0    |                      0 |
| doc11     |                0 |                    0 |             4.64 |              22.57 |                0 |               3.91 |                      0 |
| doc11.pdf |                0 |                    0 |             0    |               0    |                0 |               0    |                      0 |
| doc12     |                0 |                    0 |             4.79 |             890.26 |                0 |               4.91 |                      0 |
| doc12.pdf |                0 |                    0 |             0    |               0    |                0 |               0    |                      0 |
| doc13     |                0 |                    0 |             5.71 |             895.89 |                0 |               7.04 |                      0 |
| doc13.pdf |                0 |                    0 |             0    |               0    |                0 |               0    |                      0 |
| doc14     |                0 |                    0 |             4.74 |              28.68 |                0 |               3.41 |                      0 |
| doc14.pdf |                0 |                    0 |             0    |               0    |                0 |               0    |                      0 |
| doc15     |                0 |                    0 |             4.56 |              15.63 |                0 |               3.17 |                      0 |
| doc15.pdf |                0 |                    0 |             0    |               0    |                0 |               0    |                      0 |
| doc16     |                0 |                    0 |             4.63 |             879.16 |                0 |               4.63 |                      0 |
| doc16.pdf |                0 |                    0 |             0    |               0    |                0 |               0    |                      0 |
| doc17     |                0 |                    0 |             4.99 |              18.2  |                0 |               4.07 |                      0 |
| doc17.pdf |                0 |                    0 |             0    |               0    |                0 |               0    |                      0 |
| doc18     |                0 |                    0 |             5.41 |              15.32 |                0 |               5.73 |                      0 |
| doc18.pdf |                0 |                    0 |             0    |               0    |                0 |               0    |                      0 |
| doc19     |                0 |                    0 |             4.59 |               6.62 |                0 |               4.93 |                      0 |
| doc19.pdf |                0 |                    0 |             0    |               0    |                0 |               0    |                      0 |
| doc2      |                0 |                    0 |             4.65 |              15.74 |                0 |               4.91 |                      0 |
| doc2.pdf  |                0 |                    0 |             0    |               0    |                0 |               0    |                      0 |
| doc20     |                0 |                    0 |             4.67 |              18.15 |                0 |               5.76 |                      0 |
| doc20.pdf |                0 |                    0 |             0    |               0    |                0 |               0    |                      0 |
| doc3      |                0 |                    0 |             5.06 |              15.12 |                0 |               3.23 |                      0 |
| doc3.pdf  |                0 |                    0 |             0    |               0    |                0 |               0    |                      0 |
| doc4      |                0 |                    0 |             4.52 |             891.99 |                0 |               3.33 |                      0 |
| doc4.pdf  |                0 |                    0 |             0    |               0    |                0 |               0    |                      0 |
| doc5      |                0 |                    0 |             5.02 |              16.31 |                0 |               6.2  |                      0 |
| doc5.pdf  |                0 |                    0 |             0    |               0    |                0 |               0    |                      0 |
| doc6      |                0 |                    0 |             4.4  |             884.35 |                0 |               3.92 |                      0 |
| doc6.pdf  |                0 |                    0 |             0    |               0    |                0 |               0    |                      0 |
| doc7      |                0 |                    0 |            12.74 |             116.17 |                0 |              40.74 |                      0 |
| doc7.pdf  |                0 |                    0 |             0    |               0    |                0 |               0    |                      0 |
| doc8      |                0 |                    0 |             4.83 |               7.4  |                0 |               4.57 |                      0 |
| doc8.pdf  |                0 |                    0 |             0    |               0    |                0 |               0    |                      0 |
| doc9      |                0 |                    0 |             4.65 |              14.48 |                0 |               4.57 |                      0 |
| doc9.pdf  |                0 |                    0 |             0    |               0    |                0 |               0    |                      0 |


## 3. Comparativo de Caracteres Extraídos por Documento

Quantidade de caracteres extraídos por engine para cada documento. Volumes maiores indicam maior cobertura textual (não necessariamente maior qualidade).

| pdf       |   docling_chars |   docling_gpu_chars |   glm_ocr_chars |   minicpm_v_chars |   olmocr2_chars |   tesseract_chars |   unlimited_ocr_chars |
|:----------|----------------:|--------------------:|----------------:|------------------:|----------------:|------------------:|----------------------:|
| doc1      |               0 |                   0 |              18 |               142 |               0 |              5205 |                     0 |
| doc1.pdf  |               0 |                   0 |               0 |                 0 |               0 |                 0 |                     0 |
| doc10     |               0 |                   0 |              36 |             50453 |               0 |              4554 |                     0 |
| doc10.pdf |               0 |                   0 |               0 |                 0 |               0 |                 0 |                     0 |
| doc11     |               0 |                   0 |              18 |               431 |               0 |              4309 |                     0 |
| doc11.pdf |               0 |                   0 |               0 |                 0 |               0 |                 0 |                     0 |
| doc12     |               0 |                   0 |              18 |             46453 |               0 |              5151 |                     0 |
| doc12.pdf |               0 |                   0 |               0 |                 0 |               0 |                 0 |                     0 |
| doc13     |               0 |                   0 |              36 |             74830 |               0 |              8491 |                     0 |
| doc13.pdf |               0 |                   0 |               0 |                 0 |               0 |                 0 |                     0 |
| doc14     |               0 |                   0 |              18 |               961 |               0 |              4292 |                     0 |
| doc14.pdf |               0 |                   0 |               0 |                 0 |               0 |                 0 |                     0 |
| doc15     |               0 |                   0 |              18 |               148 |               0 |              2833 |                     0 |
| doc15.pdf |               0 |                   0 |               0 |                 0 |               0 |                 0 |                     0 |
| doc16     |               0 |                   0 |              18 |             38824 |               0 |              4759 |                     0 |
| doc16.pdf |               0 |                   0 |               0 |                 0 |               0 |                 0 |                     0 |
| doc17     |               0 |                   0 |              18 |               143 |               0 |              5242 |                     0 |
| doc17.pdf |               0 |                   0 |               0 |                 0 |               0 |                 0 |                     0 |
| doc18     |               0 |                   0 |              18 |               176 |               0 |              7468 |                     0 |
| doc18.pdf |               0 |                   0 |               0 |                 0 |               0 |                 0 |                     0 |
| doc19     |               0 |                   0 |              18 |               110 |               0 |              6094 |                     0 |
| doc19.pdf |               0 |                   0 |               0 |                 0 |               0 |                 0 |                     0 |
| doc2      |               0 |                   0 |              18 |               180 |               0 |              7146 |                     0 |
| doc2.pdf  |               0 |                   0 |               0 |                 0 |               0 |                 0 |                     0 |
| doc20     |               0 |                   0 |              18 |               358 |               0 |              6961 |                     0 |
| doc20.pdf |               0 |                   0 |               0 |                 0 |               0 |                 0 |                     0 |
| doc3      |               0 |                   0 |              18 |               136 |               0 |              4023 |                     0 |
| doc3.pdf  |               0 |                   0 |               0 |                 0 |               0 |                 0 |                     0 |
| doc4      |               0 |                   0 |              18 |             58095 |               0 |              4235 |                     0 |
| doc4.pdf  |               0 |                   0 |               0 |                 0 |               0 |                 0 |                     0 |
| doc5      |               0 |                   0 |              18 |               696 |               0 |              5854 |                     0 |
| doc5.pdf  |               0 |                   0 |               0 |                 0 |               0 |                 0 |                     0 |
| doc6      |               0 |                   0 |              18 |             47867 |               0 |              4387 |                     0 |
| doc6.pdf  |               0 |                   0 |               0 |                 0 |               0 |                 0 |                     0 |
| doc7      |               0 |                   0 |             144 |              1315 |               0 |             50592 |                     0 |
| doc7.pdf  |               0 |                   0 |               0 |                 0 |               0 |                 0 |                     0 |
| doc8      |               0 |                   0 |              18 |               103 |               0 |              5120 |                     0 |
| doc8.pdf  |               0 |                   0 |               0 |                 0 |               0 |                 0 |                     0 |
| doc9      |               0 |                   0 |              18 |               176 |               0 |              5953 |                     0 |
| doc9.pdf  |               0 |                   0 |               0 |                 0 |               0 |                 0 |                     0 |


## 4. Docling: CPU vs GPU

| Métrica | Valor |
|---------|-------|
| Tempo total — Docling CPU (s) | `0.0` |
| Tempo total — Docling GPU/CUDA (s) | `0.0` |
| Fator de speedup GPU/CPU | **nan×** |

> O speedup real pode variar conforme o tamanho dos documentos, a GPU disponível e a carga do sistema.


## 5. Desempenho por Documento

|                                |   success_rate |   total_time |   total_chars |
|:-------------------------------|---------------:|-------------:|--------------:|
| ('doc1', 'docling')            |              0 |        0     |             0 |
| ('doc1', 'docling_gpu')        |              0 |        0     |             0 |
| ('doc1', 'glm_ocr')            |              1 |        4.847 |            18 |
| ('doc1', 'minicpm_v')          |              1 |       15.597 |           142 |
| ('doc1', 'olmocr2')            |              0 |        0     |             0 |
| ('doc1', 'tesseract')          |              1 |        4.15  |          5205 |
| ('doc1.pdf', 'unlimited_ocr')  |              0 |        0     |             0 |
| ('doc10', 'docling')           |              0 |        0     |             0 |
| ('doc10', 'docling_gpu')       |              0 |        0     |             0 |
| ('doc10', 'glm_ocr')           |              1 |        6.082 |            36 |
| ('doc10', 'minicpm_v')         |              1 |      902.217 |         50453 |
| ('doc10', 'olmocr2')           |              0 |        0     |             0 |
| ('doc10', 'tesseract')         |              1 |        6.229 |          4554 |
| ('doc10.pdf', 'unlimited_ocr') |              0 |        0     |             0 |
| ('doc11', 'docling')           |              0 |        0     |             0 |
| ('doc11', 'docling_gpu')       |              0 |        0     |             0 |
| ('doc11', 'glm_ocr')           |              1 |        4.637 |            18 |
| ('doc11', 'minicpm_v')         |              1 |       22.575 |           431 |
| ('doc11', 'olmocr2')           |              0 |        0     |             0 |
| ('doc11', 'tesseract')         |              1 |        3.914 |          4309 |
| ('doc11.pdf', 'unlimited_ocr') |              0 |        0     |             0 |
| ('doc12', 'docling')           |              0 |        0     |             0 |
| ('doc12', 'docling_gpu')       |              0 |        0     |             0 |
| ('doc12', 'glm_ocr')           |              1 |        4.787 |            18 |
| ('doc12', 'minicpm_v')         |              1 |      890.262 |         46453 |
| ('doc12', 'olmocr2')           |              0 |        0     |             0 |
| ('doc12', 'tesseract')         |              1 |        4.906 |          5151 |
| ('doc12.pdf', 'unlimited_ocr') |              0 |        0     |             0 |
| ('doc13', 'docling')           |              0 |        0     |             0 |
| ('doc13', 'docling_gpu')       |              0 |        0     |             0 |
| ('doc13', 'glm_ocr')           |              1 |        5.715 |            36 |
| ('doc13', 'minicpm_v')         |              1 |      895.895 |         74830 |
| ('doc13', 'olmocr2')           |              0 |        0     |             0 |
| ('doc13', 'tesseract')         |              1 |        7.037 |          8491 |
| ('doc13.pdf', 'unlimited_ocr') |              0 |        0     |             0 |
| ('doc14', 'docling')           |              0 |        0     |             0 |
| ('doc14', 'docling_gpu')       |              0 |        0     |             0 |
| ('doc14', 'glm_ocr')           |              1 |        4.739 |            18 |
| ('doc14', 'minicpm_v')         |              1 |       28.678 |           961 |
| ('doc14', 'olmocr2')           |              0 |        0     |             0 |


## 6. Pipeline de Roteamento Recomendado

# Proposed Routing Logic
    1. IF document is highly complex (complexity_score > 0.8) -> ROUTE TO Ollama (olmocr2)
    2. IF document has high native text density (> 0.9) -> ROUTE TO Marker/Docling
    3. IF document is low complexity AND mostly text -> ROUTE TO Tesseract
    4. DEFAULT -> ROUTE TO Ollama (MiniCPM-V)


## 7. Metodologia

- **Seleção:** 20 PDFs escolhidos por score de complexidade (alta, média, baixa, outliers).
- **Engines avaliados:** Tesseract, Docling (CPU), Docling (GPU/CUDA), Marker, MarkItDown, Ollama (olmocr2, glm-ocr, minicpm-v).
- **Hardware:** execução local — GPU NVIDIA RTX 4070 para engines com aceleração.
- **Métricas:** taxa de sucesso, tempo de execução por página, total de caracteres extraídos.
- **Resolução de renderização:** 300 DPI.
- **Seed aleatório:** 42.
