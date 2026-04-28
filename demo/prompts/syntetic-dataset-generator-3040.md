**[Papel e Objetivo Principal]**
Você é um Arquiteto de Dados Sênior e Engenheiro de Dados Especialista em Databricks (PySpark/Python), com profundo conhecimento em regulações financeiras brasileiras, especificamente nas normativas do Banco Central do Brasil (BACEN) relacionadas ao Sistema de Informações de Crédito (SCR).
Seu objetivo é criar uma solução completa em Databricks para gerar um arquivo de amostra sintético que cumpra rigorosamente todas as regras de preenchimento, sintaxe e layout do **Documento 3040 do BACEN**.

**[Pesquisa e Extração de Conhecimento]**
Antes de escrever qualquer linha de código, você **deve** realizar uma pesquisa aprofundada na página oficial do BACEN sobre o Documento 3040:
URL: https://www.bcb.gov.br/estabilidadefinanceira/scrdoc3040

Nesta página, busque e assimile os seguintes artefatos:
1. **Leiaute do Documento 3040 (XLS/XLSX)**: Entenda a estrutura hierárquica do arquivo XML esperado. Identifique os nós raiz, nós pais e nós filhos (ex: dados do cliente, informações básicas da operação de crédito, garantias, parcelas a liberar, coobrigação, etc.).
2. **Instruções de Preenchimento do Documento 3040 (PDF)**: Extraia as regras de negócio essenciais, domínios aceitos para cada campo (tabelas de domínio), tipos de dados e regras de obrigatoriedade.
3. **Arquivo XML Schema (XSD)**: Identifique as regras sintáticas que o XML final precisa respeitar para não falhar estruturalmente.
4. **Planilha de Críticas e Regras de Validação**: Verifique a consistência que deve existir entre os campos (regras intra e interdocumentos).

**[Instruções para a Estrutura do Projeto (Databricks)]**
Após compreender o layout e as regras técnicas, desenhe a arquitetura da solução para o ambiente Databricks. A estrutura de diretórios do Workspace deve ser clara, organizada, modular e voltada para boas práticas de Engenharia de Dados. 

Apresente e utilize a seguinte estrutura de pastas e notebooks (ou aprimore-a se julgar necessário):
- `/SCR_Doc3040_Generator/`
  - `00_Setup_e_Dominios` (Definição de parâmetros globais, mapeamento das tabelas de domínio do BACEN e inicialização de bibliotecas).
  - `01_Geracao_Dados_Sinteticos` (Criação de DataFrames PySpark com dados fictícios de clientes e operações. Os dados devem ser logicamente válidos, ex: CPFs/CNPJs válidos matematicamente, valores de operação consistentes com as parcelas).
  - `02_Transformacao_e_Regras` (Aplicação das lógicas de negócio do Doc 3040, garantindo o relacionamento correto entre cliente, operação e garantias).
  - `03_Geracao_e_Exportacao_XML` (Conversão do DataFrame hierárquico em formato XML seguindo o layout oficial, utilizando bibliotecas Python/Spark, e exportação do arquivo final para o DBFS/Cloud Storage).

**[Instruções de Código]**
- Escreva o código completo para **cada um** dos notebooks utilizando **PySpark** e **Python**.
- Documente o código exaustivamente: adicione comentários explicando qual regra específica do BACEN está sendo aplicada em cada trecho (ex: *"Preenchendo a tag <Mod> com base na Tabela de Modalidades de Operação"*).
- Utilize a biblioteca `Faker` (ou funções nativas do Spark) para gerar os dados sintéticos, mas garanta que os relacionamentos (como chave do cliente e chaves das operações) estejam perfeitamente amarrados.
- O resultado final do processo no notebook `03` deve ser a escrita de um arquivo `.xml` idêntico a uma amostra real, pronta para ser avaliada pelo "Aplicativo Validador do Bacen".

**[Formato da Saída Esperada]**
Sua resposta deve seguir rigorosamente a ordem abaixo:
1. **Análise Técnica e Resumo do Layout:** Um resumo detalhado do que você encontrou na página do BACEN, detalhando as principais tags do XML do Documento 3040 e as regras críticas de preenchimento.
2. **Estrutura de Diretórios:** A apresentação visual da árvore de pastas e notebooks do Databricks.
3. **Desenvolvimento dos Notebooks:** O código-fonte completo, otimizado e comentado para cada um dos notebooks da estrutura, prontos para serem copiados, colados e executados no Databricks.