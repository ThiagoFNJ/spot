# Web Scraper de Proposições Legislativas

Este projeto contém um web scraper desenvolvido para coletar dados de proposições legislativas do site da Câmara de Vereadores de Florianópolis. A ferramenta extrai informações detalhadas sobre os projetos e as salva em um arquivo CSV para posterior análise.
Visão Geral

O objetivo deste projeto é automatizar a coleta de dados legislativos, fornecendo um conjunto de dados estruturado. O scraper é capaz de navegar pela paginação do site e extrair informações de múltiplos projetos ao longo de diferentes anos.
Estrutura do Projeto

O projeto é composto pelos seguintes arquivos principais:

    scraper.py: Contém a classe LegislativeScraper, que encapsula toda a lógica de raspagem de dados, incluindo o tratamento de requisições HTTP e o parsing do HTML.

    main.py: É o script principal que orquestra o processo de scraping. Ele define os parâmetros da coleta, como o período (anos) e os tipos de matéria, e gerencia o salvamento dos dados.

    requirements.txt: Lista todas as dependências de bibliotecas Python necessárias para executar o scraper.

# Funcionalidades

    Raspagem de Dados Web: O scraper.py acessa o portal de proposições da Câmara de Vereadores de Florianópolis para extrair informações detalhadas sobre os projetos.

    Extração de Informações: Para cada projeto, são coletados dados como:

        Ano

        Tipo de Matéria

        Data de Apresentação

        Número do Projeto

        Descrição

        Autoria

        Situação

        Data da Situação

        Link para a proposição

    Armazenamento de Dados: Os dados coletados são armazenados em um arquivo CSV (projetos_lei_florianopolis.csv por padrão) para fácil utilização em outras ferramentas de análise de dados.

# Como Executar o Projeto

Para executar o scraper em sua máquina local, siga os passos abaixo.
Pré-requisitos

    Python 3.x

    Pip (gerenciador de pacotes do Python)

# Instalação

    Clone o repositório:

    git clone https://github.com/Zeukio/scraper-camara-florianopolis.git
    cd scraper-camara-florianopolis

    Crie e ative um ambiente virtual (recomendado):

    python -m venv venv
    source venv/bin/activate  # No Windows, use `venv\Scripts\activate`

    Instale as dependências:

    pip install -r requirements.txt

# Coleta de Dados

Para iniciar a coleta de dados, execute o script main.py. Ele irá buscar as informações no site e salvar os resultados em um arquivo CSV.

python main.py

Observação: Você pode configurar o período da coleta alterando as variáveis start_year e end_year no arquivo main.py.
Dependências

As principais bibliotecas utilizadas neste projeto são:

    requests: Para realizar as requisições HTTP ao site.

    beautifulsoup4: Para fazer o parsing do conteúdo HTML das páginas.

    pandas: Para a manipulação e armazenamento dos dados em formato CSV.

Todas as dependências estão listadas no arquivo requirements.txt.
Contribuição

Contribuições para este projeto são bem-vindas. Se você tiver sugestões de melhorias, otimizações no scraper ou correções de bugs, sinta-se à vontade para abrir uma issue ou enviar um pull request.