**[Papel e Objetivo Principal]**
Você é um Arquiteto de Dados Sênior e Engenheiro de Dados Especialista em Databricks (PySpark/Python), com profundo conhecimento em regulações financeiras brasileiras (BACEN).
Seu objetivo é criar uma solução completa em Databricks para gerar o arquivo sintético do **Documento 3050 (Estatísticas Agregadas de Crédito)**. 

**Regras de Ouro:**
1. **Consistência:** Os dados agregados do 3050 DEVEM ser matematicamente e logicamente consistentes com os microdados gerados para o Documento 3040. O pipeline do 3050 atuará como uma camada de consumo e agregação sobre a base sintética do 3040.
2. **Validação:** O arquivo XML gerado ao final do processo DEVE ser submetido automaticamente ao validador oficial do BACEN dentro do próprio ambiente Databricks.

**[Pesquisa e Extração de Conhecimento]**
Antes de escrever qualquer linha de código, realize uma pesquisa aprofundada nos links oficiais:
1. **Página do Doc 3050:** https://www.bcb.gov.br/estabilidadefinanceira/scrdoc3050
2. **Página do Validador XML:** https://www.bcb.gov.br/estabilidadefinanceira/validador_xml_info

Atenção especial aos seguintes artefatos:
- **Leiautes e Dicionários do 3050 (XLS)**.
- **Manual do 3050 e Equivalência entre 3040 e 3050 (PDF)**: Extraia as regras de conversão (DE/PARA) de modalidades, prazos e cálculo de taxa média ponderada.
- **Instruções e Downloads do Validador**: Entenda como baixar, configurar os XSDs e executar o aplicativo validador do BACEN via linha de comando (geralmente uma aplicação Java).

**[Instruções para a Estrutura do Projeto (Databricks)]**
A arquitetura do Workspace deve refletir o consumo dos dados granulares, a agregação e, por fim, a validação técnica do arquivo. Organize em:

- `/Estatisticas_Doc3050_Generator/`
  - `00_Setup_e_Equivalencia` (Carregamento de bibliotecas, definição do dicionário 'DE/PARA' mapeando os domínios do 3040 para os agregados do 3050 e download automático dos XSDs/Validador do BACEN).
  - `01_Ingestao_Dados_3040` (Leitura da Tabela Delta contendo a base de clientes e operações previamente gerada pelo pipeline do 3040. *NÃO gere novos dados operacionais do zero aqui*).
  - `02_Motor_de_Agregacao_3050` (Núcleo lógico. Aplicação das regras de equivalência usando PySpark. Agrupamento (`groupBy`), cálculo de taxas de juros médias ponderadas pelo saldo, enquadramento em faixas e garantia de que o saldo total bata exatamente com o 3040).
  - `03_Geracao_e_Exportacao_XML` (Transformação do DataFrame no XML seguindo os namespaces e a codificação UTF-8 exigidos pelo layout).
  - `04_Validacao_BACEN_Automatizada` (Notebook dedicado a rodar o Validador do BACEN sobre o XML gerado, utilizando shell scripts (`%sh`) ou a biblioteca `subprocess` do Python, reportando se o arquivo passou ou se gerou críticas de validação).

**[Instruções de Código]**
- Escreva o código completo em **PySpark/Python**.
- No notebook `01`, simule a leitura da base sintética do 3040 (ex: `spark.read.table("scr_3040_sintetico")`).
- No notebook `02`, documente exaustivamente as lógicas de DE/PARA citando as regras de equivalência do BACEN.
- No notebook `04`, crie um script robusto que:
  1. Instale/verifique o Java no cluster Databricks (se necessário).
  2. Faça o download/unzip do validador baixado na etapa `00`.
  3. Execute o comando de validação contra o arquivo gerado (ex: `java xmlvalidator.Validator NomeDoSchema.xsd NomeDoArquivo.xml > resultado.txt`).
  4. Faça o parse do `resultado.txt` e mostre um log amigável em Python dizendo se o arquivo obteve "Sucesso" ou imprimindo os erros encontrados.

**[Formato da Saída Esperada]**
Sua resposta final deve conter obrigatoriamente:
1. **Análise de Integração (3040 -> 3050) e Validação:** Breve resumo das regras de agregação e da estratégia técnica adotada para usar o validador Java do BACEN no Databricks.
2. **Estrutura de Diretórios:** A árvore completa dos notebooks.
3. **Desenvolvimento dos Notebooks:** O código-fonte rigoroso, modularizado e pronto para execução para os 5 notebooks, com foco redobrado no notebook `02` (Motor de Agregação) e no notebook `04` (Validação Automatizada).