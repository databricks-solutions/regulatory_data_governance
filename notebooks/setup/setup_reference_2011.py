# Databricks notebook source
# MAGIC %md
# MAGIC # Setup Reference — CADOC 2011 (DDR)
# MAGIC
# MAGIC ⚠️ **ARQUIVO GERADO — não editar à mão.** Regenere com
# MAGIC `python scripts/gen_ddr2011_reference_seed.py` quando o BCB publicar uma
# MAGIC versão nova do leiaute.
# MAGIC
# MAGIC Semeia os domínios do **Documento 2011 — DDR** (*Demonstrativo Diário de
# MAGIC Acompanhamento das Parcelas de Requerimento de Capital e dos Limites
# MAGIC Operacionais*, periodicidade **diária**) em `reference.dominios` e cria as
# MAGIC views de domínio consumidas pelos checks DQX.
# MAGIC
# MAGIC Fonte: leiaute oficial v5 (vigente a partir de 01/07/2023), aba `Anexos` de
# MAGIC `docs/ddr2011/Leiaute_DDR_2011_v5_01072023.xls` —
# MAGIC bcb.gov.br/estabilidadefinanceira/leiautedocumentoDDR2011
# MAGIC
# MAGIC Domínios semeados: Anexo 1 tipoEnvio: 2 · Anexo 2 codigoParametro: 3 · Anexo 3 codigoElemento: 3 · Anexo 4 Conta: 92 · Anexo 5 moeda: 186 · Anexo 6 posicaoPaisExterior: 2 · Anexo 7 pais: 248.
# MAGIC
# MAGIC Os anexos grandes (contas, moedas, países) existem porque os checks DQX de
# MAGIC domínio fazem `col IN (SELECT valor_codigo FROM reference.v_dom_2011_*)` — a
# MAGIC `expression` do DQX Studio não aceita literais string (o `parse_json` inline
# MAGIC os corrompe), então a lista tem de viver numa view.
# MAGIC
# MAGIC Idempotente: apaga as linhas `documento = '2011'` antes de reinserir.

# COMMAND ----------

dbutils.widgets.text("catalog", "rc18_catalog", "Unity Catalog")
dbutils.widgets.text("schema", "reference", "Reference Schema")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")

DOCUMENTO = "2011"
LEIAUTE_VERSAO = "DDRv5"

print(f"Semeando domínios do CADOC {DOCUMENTO} em {CATALOG}.{SCHEMA}.dominios")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Domínios oficiais (Anexos 1 a 7 do leiaute)

# COMMAND ----------

# Anexo 1 — Indicador de inclusão ou alteração de documento (2 domínios).
_ANEXO_1 = [
    ("I", "Inclusão de documento", "2020-02-01", None),
    ("S", "Substituição de documento", "2020-02-01", None),
]

# Anexo 2 — Código do parâmetro (3 domínios).
_ANEXO_2 = [
    ("31", "Nome do responsável pelo envio do DLO", "2020-02-01", None),
    ("32", "Telefone do responsável pelo envio do DLO", "2020-02-01", None),
    ("33", "Email do responsável pelo envio do DLO", "2020-02-01", None),
]

# Anexo 3 — Código do elemento de cálculo (3 domínios).
_ANEXO_3 = [
    ("81", "País", "2020-02-01", None),
    ("84", "Posição país/exterior", "2020-02-01", None),
    ("83", "moeda", "2020-02-01", None),
]

# Anexo 4 — Contas do DDR (92 domínios).
_ANEXO_4 = [
    ("111000", "Total da Exposição Ativa Comprada", "2020-02-01", None),
    ("121000", "Total da Exposição Passiva Vendida", "2020-02-01", None),
    ("121100", "Total das Exceções Previstas no Artigo 1º, § 5º, da Circular 3.641/2013 no Exterior", "2020-02-01", None),
    ("131000", "Total das Demais Posições Compradas", "2020-02-01", None),
    ("132000", "Total das Demais Posições Vendidas", "2020-02-01", None),
    ("141000", "Total das Posições Líquidas Compradas", "2020-02-01", None),
    ("151000", "Total das Posições Líquidas Vendidas", "2020-02-01", None),
    ("161000", "Total das Posições Vendidas no Patrimônio Líquido", "2020-02-01", None),
    ("171000", "Total das Posições em Investimentos no Exterior", "2020-02-01", None),
    ("181000", "Total do Excesso da Posição Vendida para Hedge em Participações no Exterior", "2020-02-01", None),
    ("191000", "Hedge de Fluxo de Caixa para Compensar Variação Cambial de Compromissos Futuros", "2023-07-01", None),
    ("210000", "Ativos de Alta Liquidez: Dinheiro em Espécie (em Moeda Estrangeira no Brasil e no Exterior)", "2020-02-01", None),
    ("220000", "Ativos de Alta Liquidez: Reservas Livres em Bancos Centrais no Exterior", "2020-02-01", None),
    ("230000", "Ativos de Alta Liquidez: Títulos Soberanos e Similares no Exterior", "2020-02-01", None),
    ("240000", "Entradas de Caixa: Depósitos a Liberar em 30 dias em Instituições Financeiras no Exterior", "2020-02-01", None),
    ("310000", "Requerimento de Capital para o RWACAM", "2020-02-01", None),
    ("310100", "Valor Total da Exposição Cambial", "2020-02-01", None),
    ("310101", "Exposição Líquida na Cesta de Moedas", "2020-02-01", None),
    ("310102", "Exposição em Cada Moeda Fora da Cesta de Moedas", "2020-02-01", None),
    ("310103", "Diferencial das Exposições Líquidas na Cesta de Moedas", "2020-02-01", None),
    ("310104", "Diferencial das Posições Líquidas entre País e Exterior", "2020-02-01", None),
    ("310105", "Fator F’’", "2020-02-01", None),
    ("410100", "Fator de Incorporação da Parcela Referente ao Valor em Risco Estressado referente ao componente RWAJUR1 - S.", "2020-02-01", None),
    ("410101", "Multiplicador MPRE diário", "2020-02-01", None),
    ("410200", "Valor em Risco agregado para os cenários normal e estressado", "2020-02-01", None),
    ("410201", "Valor em Risco", "2020-02-01", None),
    ("410202", "Valor em Risco Estressado", "2020-02-01", None),
    ("410300", "Valor em Risco médio agregado para os cenários normal e estressado", "2020-02-01", None),
    ("410301", "Valor em Risco Médio", "2020-02-01", None),
    ("410302", "Valor em Risco Estressado Médio", "2020-02-01", None),
    ("410400", "Requerimento de Capital para o componente RWAJUR1", "2020-02-01", None),
    ("410401", "Requerimento de Capital para o RWAJUR1 para o cenário normal", "2020-02-01", None),
    ("410402", "Requerimento de Capital para o RWAJUR1 para o cenário estressado", "2020-02-01", None),
    ("410500", "Requerimento de Capital para o componente RWAJUR2", "2020-02-01", None),
    ("410501", "Requerimento de Capital para Exposição Líquida do RWAJUR2 - ECEL[2]", "2020-02-01", None),
    ("410502", "Requerimento de Capital para Descasamento Vertical do RWAJUR2 - ECDV[2]", "2020-02-01", None),
    ("410503", "Requerimento de Capital para Descasamento Horizontal Dentro da Zona de Vencimento RWAJUR2- ECDHDZ[2]", "2020-02-01", None),
    ("410504", "Requerimento de Capital para Descasamento Horizontal Entre as Zonas de Vencimento RWAJUR2- ECDHEZ[2]", "2020-02-01", None),
    ("410600", "Requerimento de Capital para o componente RWAJUR3", "2020-02-01", None),
    ("410601", "Requerimento de Capital para Exposição Líquida RWAJUR3 - ECEL[3]", "2020-02-01", None),
    ("410602", "Requerimento de Capital para Descasamento Vertical RWAJUR3 - ECDV[3]", "2020-02-01", None),
    ("410603", "Exigência de Capital para Descasamento Horizontal Dentro da Zona de Vencimento RWAJUR3 - ECDHDZ[3]", "2020-02-01", None),
    ("410604", "Exigência de Capital para Descasamento Horizontal Entre as Zonas de Vencimento RWAJUR3- ECDHEZ[3]", "2020-02-01", None),
    ("410700", "Requerimento de Capital para o componente RWAJUR4", "2020-02-01", None),
    ("410701", "Requerimento de Capital para Exposição Líquida RWAJUR4 - ECEL[4]", "2020-02-01", None),
    ("410702", "Requerimento de Capital para Descasamento Vertical - ECDV[4]", "2020-02-01", None),
    ("410703", "Requerimento de Capital para Descasamento Horizontal Dentro da Zona de Vencimento RWAJUR4 - ECDHDZ[4]", "2020-02-01", None),
    ("410704", "Requerimento de Capital para Descasamento Horizontal Entre as Zonas de Vencimento RWAJUR4 - ECDHEZ[4]", "2020-02-01", None),
    ("410800", "Valor do RWACOM", "2020-02-01", None),
    ("410801", "Requerimento de Capital para Exposição Líquida RWACOM- ECEL[COM]", "2020-02-01", None),
    ("410802", "Requerimento de Capital para Exposição Bruta RWACOM- ECEB", "2020-02-01", None),
    ("410900", "Requerimento de Capital para o Componente RWAACS", "2020-02-01", None),
    ("410901", "Requerimento de Capital para o Valor Absoluto do Somatório das Exposições Líquidas em Ações no País - RWAACS ECVASELP", "2020-02-01", None),
    ("410904", "Requerimento de Capital para o Valor Absoluto do Somatório das Exposições Líquidas em Ações no Exterior - RWAACS ECVASELE", "2020-02-01", None),
    ("410907", "Requerimento de Capital para o Somatório do Valor Absoluto das Exposições Líquidas em Ações no País - RWAACS ECSVAELP", "2020-02-01", None),
    ("410908", "Requerimento de Capital para o Somatório do Valor Absoluto das Exposições Líquidas em Ações no Exterior - RWAACS ECSVAELE", "2020-02-01", None),
    ("410909", "Requerimento de Capital para o Somatório do Valor Absoluto das Exposições Líquidas em Índices de Ações no País - RWAACS ECSVAELIP", "2020-02-01", None),
    ("410910", "Requerimento de Capital para o Somatório do Valor Absoluto das Exposições Líquidas em Índices de Ações no Exterior - RWAACS ECSVAELIE", "2020-02-01", None),
    ("411000", "Requerimento de Capital relativamente ao CVA", "2023-07-01", None),
    ("412000", "Requerimento de Capital relativamente ao risco de crédito da carteira de negociação", "2023-07-01", None),
    ("501000", "Total das Demais Posições Compradas no País", "2020-02-01", None),
    ("502000", "Total das Demais Posições Vendidas no País", "2020-02-01", None),
    ("503000", "Requerimento de Capital para a Parcela RWAMPAD - VPRMPAD", "2020-02-01", None),
    ("504000", "Fator de Transição para Modelos Internos - S1", "2020-02-01", None),
    ("505000", "Requerimento de Capital para Exposições Não Relevantes - VADPAD", "2020-02-01", None),
    ("506000", "Fator de Incorporação da Parcela Referente ao Valor em Risco Estressado - S2", "2020-02-01", None),
    ("507000", "Adicional Relativo aos Testes de Aderência - ABKT", "2020-02-01", None),
    ("508000", "Adicional Relativo à Avaliação Qualitativa - AQLT", "2020-02-01", None),
    ("610000", "Requerimento de Capital para Parcela RWAMINT - VPRMMI", "2020-02-01", None),
    ("620000", "Valor em Risco Segundo Modelo Interno - VaRtMI", "2020-02-01", None),
    ("620100", "Efeito Diversificação entre os Grupos de Fatores de Risco de cada Parcela de Risco de Mercado - DIVPRM", "2020-02-01", None),
    ("620200", "Valor em Risco dos Fatores de Risco Associados a Exposição Cambial - VaRCAM", "2020-02-01", None),
    ("620300", "Valor em Risco dos Fatores de Risco Associados a Commodities - VaRCOM", "2020-02-01", None),
    ("620400", "Valor em Risco dos Fatores de Risco Associados a Ações - VaRACS", "2020-02-01", None),
    ("620500", "Valor em Risco dos Fatores de Risco Associados a Taxas de Juros - VaRJUR", "2020-02-01", None),
    ("620501", "Efeito Diversificação entre os Grupos de Fatores de Risco Associados a Juros - DIVJUR", "2020-02-01", None),
    ("620502", "Valor em Risco de Juros-Pré - VaRJUR[1]", "2020-02-01", None),
    ("620503", "Valor em Risco de Cupom de Moeda Estrangeira - VaRJUR[2]", "2020-02-01", None),
    ("620504", "Valor em Risco de Cupom de Taxa de Juros - VaRJUR[3]", "2020-02-01", None),
    ("620505", "Valor em Risco de Cupom de Índice de Preços - VaRJUR[4]", "2020-02-01", None),
    ("630000", "Valor em Risco Estressado Segundo Modelo Interno - sVaRMI", "2020-02-01", None),
    ("630100", "Efeito Diversificação entre os Grupos de Fatores de Risco de cada Parcela Estressada de Risco de Mercado – SDIVPRM", "2020-02-01", None),
    ("630200", "Valor em Risco Estressado dos Fatores de Risco Associados a Exposição Cambial - sVaRCAM", "2020-02-01", None),
    ("630300", "Valor em Risco Estressado dos Fatores de Risco Associados a Commodities - sVaRCOM", "2020-02-01", None),
    ("630400", "Valor em Risco Estressado dos Fatores de Risco Associados a Ações - sVaRACS", "2020-02-01", None),
    ("630500", "Valor em Risco Estressado dos Fatores de Risco Associados a Taxas de Juros - sVaRJUR", "2020-02-01", None),
    ("630501", "Efeito Diversificação entre os Grupos de Fatores de Risco Associados a Juros - DIVJUR", "2020-02-01", None),
    ("630502", "Valor em Risco Estressado de Juros-Pré - sVaRJUR[1]", "2020-02-01", None),
    ("630503", "Valor em Risco Estressado de Cupom de Moeda Estrangeira - sVaRJUR[2]", "2020-02-01", None),
    ("630504", "Valor em Risco Estressado de Cupom de Taxa de Juros - sVaRJUR[3]", "2020-02-01", None),
    ("630505", "Valor em Risco Estressado de Cupom de Índice de Preços - sVaRJUR[4]", "2020-02-01", None),
    ("710000", "Requerimento de Capital para a Parcela de Risco de Mercado - VPRM", "2020-02-01", None),
]

# Anexo 5 — Moedas (186 domínios).
_ANEXO_5 = [
    ("ADP", "Peseta de Andorra", "2020-02-01", None),
    ("AED", "Dirham dos Emirados", "2020-02-01", None),
    ("AFN", "Afegane", "2020-02-01", None),
    ("ALL", "Lek", "2020-02-01", None),
    ("AMD", "Dram", "2020-02-01", None),
    ("ANG", "Florim", "2020-02-01", None),
    ("AOA", "Kwanza", "2020-02-01", None),
    ("ARS", "Peso Argentino", "2020-02-01", None),
    ("ATS", "Xelim austríaco", "2020-02-01", None),
    ("AUD", "Dólar australiano", "2020-02-01", None),
    ("AWG", "Florim de Aruba", "2020-02-01", None),
    ("AZN", "Manat do Azerbaijão", "2020-02-01", None),
    ("BAM", "Marco convertível", "2020-02-01", None),
    ("BBD", "Dólar de Barbados", "2020-02-01", None),
    ("BDT", "Taka", "2020-02-01", None),
    ("BEF", "Franco belga", "2020-02-01", None),
    ("BGN", "Lev", "2020-02-01", None),
    ("BHD", "Dinar do Bahrein", "2020-02-01", None),
    ("BIF", "Franco do Burundi", "2020-02-01", None),
    ("BMD", "Dólar de Bermuda", "2020-02-01", None),
    ("BND", "Dólar do Brunei", "2020-02-01", None),
    ("BOB", "Boliviano", "2020-02-01", None),
    ("BOV", "Boliviano Mvdol", "2020-02-01", None),
    ("BRL", "Real", "2020-02-01", None),
    ("BSD", "Dólar das Bahamas", "2020-02-01", None),
    ("BTN", "Ngultrum", "2020-02-01", None),
    ("BWP", "Pula", "2020-02-01", None),
    ("BYR", "Rublo bielorrusso", "2020-02-01", None),
    ("BZD", "Dólar do Belize", "2020-02-01", None),
    ("CAD", "Dólar canadense", "2020-02-01", None),
    ("CDF", "Franco congolês", "2020-02-01", None),
    ("CHE", "WIR euro", "2020-02-01", None),
    ("CHF", "Franco suíço", "2020-02-01", None),
    ("CHW", "WIR franc", "2020-02-01", None),
    ("CLF", "Unidade de Fomento", "2020-02-01", None),
    ("CLP", "Peso chileno", "2020-02-01", None),
    ("CNY", "Renminbi", "2020-02-01", None),
    ("COP", "Peso colombiano", "2020-02-01", None),
    ("COU", "Unidade de Valor Real", "2020-02-01", None),
    ("CRC", "Colon da Costa Rica", "2020-02-01", None),
    ("CUC", "Cuban convertible peso", "2020-02-01", None),
    ("CUP", "Peso cubano", "2020-02-01", None),
    ("CVE", "Escudo cabo-verdiano", "2020-02-01", None),
    ("CZK", "Coroa", "2020-02-01", None),
    ("DEM", "Marco alemão", "2020-02-01", None),
    ("DJF", "Franco do Djibuti", "2020-02-01", None),
    ("DKK", "Coroa dinamarquesa", "2020-02-01", None),
    ("DOP", "Peso", "2020-02-01", None),
    ("DZD", "Dinar argelino", "2020-02-01", None),
    ("EEK", "Coroa estoniana", "2020-02-01", None),
    ("EGP", "Libra egípcia", "2020-02-01", None),
    ("ERN", "Nakfa", "2020-02-01", None),
    ("ESP", "Peseta espanhola", "2020-02-01", None),
    ("ETB", "Birr etíope", "2020-02-01", None),
    ("EUR", "Euro", "2020-02-01", None),
    ("FIM", "Markka finlandesa", "2020-02-01", None),
    ("FJD", "Dólar das Fiji", "2020-02-01", None),
    ("FKP", "Libra das Malvinas", "2020-02-01", None),
    ("FRF", "Franco francês", "2020-02-01", None),
    ("GBP", "Libra Esterlina", "2020-02-01", None),
    ("GEL", "Lari", "2020-02-01", None),
    ("GHS", "Cedi", "2020-02-01", None),
    ("GIP", "Libra de Gibraltar", "2020-02-01", None),
    ("GMD", "Dalasi", "2020-02-01", None),
    ("GNF", "Franco da Guiné", "2020-02-01", None),
    ("GRD", "Dracma grego", "2020-02-01", None),
    ("GTQ", "Quetzal guatemalteco", "2020-02-01", None),
    ("GYD", "Dólar da Guiana", "2020-02-01", None),
    ("HKD", "Dólar de Hong Kong", "2020-02-01", None),
    ("HNL", "Lempira", "2020-02-01", None),
    ("HRK", "Kuna", "2020-02-01", None),
    ("HTG", "Gourde", "2020-02-01", None),
    ("HUF", "Forint", "2020-02-01", None),
    ("IDR", "Rupia indonésia", "2020-02-01", None),
    ("IEP", "Libra irlandesa", "2020-02-01", None),
    ("ILS", "Shekel", "2020-02-01", None),
    ("INR", "Rupia indiana", "2020-02-01", None),
    ("IQD", "Dinar iraquiano", "2020-02-01", None),
    ("IRR", "Rial iraniano", "2020-02-01", None),
    ("ISK", "Krona islandesa", "2020-02-01", None),
    ("ITL", "Lira italiana", "2020-02-01", None),
    ("JMD", "Dólar jamaicano", "2020-02-01", None),
    ("JOD", "Dinar jordano", "2020-02-01", None),
    ("JPY", "Iene", "2020-02-01", None),
    ("KES", "Xelim queniano", "2020-02-01", None),
    ("KGS", "Som", "2020-02-01", None),
    ("KHR", "Riel", "2020-02-01", None),
    ("KMF", "Franco das Comoros", "2020-02-01", None),
    ("KPW", "Won norte coreano", "2020-02-01", None),
    ("KRW", "Won sul coreano", "2020-02-01", None),
    ("KWD", "Dinar do Kuwait", "2020-02-01", None),
    ("KYD", "Dólar das Ilhas Caimão", "2020-02-01", None),
    ("KZT", "Tenge", "2020-02-01", None),
    ("LAK", "Kip", "2020-02-01", None),
    ("LBP", "Libra libanesa", "2020-02-01", None),
    ("LKR", "Rupia do Sri Lanka", "2020-02-01", None),
    ("LRD", "Dólar da Libéria", "2020-02-01", None),
    ("LSL", "Loti", "2020-02-01", None),
    ("LTL", "Litas", "2020-02-01", None),
    ("LUF", "Franco luxemburguês", "2020-02-01", None),
    ("LVL", "Lats", "2020-02-01", None),
    ("LYD", "Dinar da Líbia", "2020-02-01", None),
    ("MAD", "Dirham marroquino", "2020-02-01", None),
    ("MDL", "Leu", "2020-02-01", None),
    ("MGA", "Ariary", "2020-02-01", None),
    ("MKD", "Denar", "2020-02-01", None),
    ("MMK", "Kyat", "2020-02-01", None),
    ("MNT", "Tugrik", "2020-02-01", None),
    ("MOP", "Pataca", "2020-02-01", None),
    ("MRO", "Ouguiya", "2020-02-01", None),
    ("MUR", "Rupia da Maurícia", "2020-02-01", None),
    ("MVR", "Rufiyaa", "2020-02-01", None),
    ("MWK", "Kwacha", "2020-02-01", None),
    ("MXN", "Peso Mexicano", "2020-02-01", None),
    ("MXV", "Unidade Mexicana de Investimento", "2020-02-01", None),
    ("MYR", "Ringgit", "2020-02-01", None),
    ("MZN", "Metical", "2020-02-01", None),
    ("NAD", "Dólar da Namíbia", "2020-02-01", None),
    ("NGN", "Naira", "2020-02-01", None),
    ("NIO", "Cordoba Oro", "2020-02-01", None),
    ("NLG", "Florim holandês", "2020-02-01", None),
    ("NOK", "Coroa norueguesa", "2020-02-01", None),
    ("NPR", "Rupia nepalesa", "2020-02-01", None),
    ("NZD", "Dólar da Nova Zelândia", "2020-02-01", None),
    ("OMR", "Rial Omani", "2020-02-01", None),
    ("PAB", "Balboa", "2020-02-01", None),
    ("PEN", "Nuevo Sol", "2020-02-01", None),
    ("PGK", "Kina", "2020-02-01", None),
    ("PHP", "Peso filipino", "2020-02-01", None),
    ("PKR", "Rupia paquistanesa", "2020-02-01", None),
    ("PLN", "Zloty", "2020-02-01", None),
    ("PTE", "Escudo português", "2020-02-01", None),
    ("PYG", "Guarani", "2020-02-01", None),
    ("QAR", "Rial do Qatar", "2020-02-01", None),
    ("RON", "Novo Leu", "2020-02-01", None),
    ("RSD", "Dinar Sérvio", "2020-02-01", None),
    ("RUB", "Rublo", "2020-02-01", None),
    ("RWF", "Franco do Ruanda", "2020-02-01", None),
    ("SAR", "Riyal", "2020-02-01", None),
    ("SBD", "Dólar das Ilhas Salomão", "2020-02-01", None),
    ("SCR", "Rupia das Seychelles", "2020-02-01", None),
    ("SDG", "Dinar sudanês", "2020-02-01", None),
    ("SEK", "Coroa Sueca", "2020-02-01", None),
    ("SGD", "Dólar de Cingapura", "2020-02-01", None),
    ("SHP", "Libra de Santa Helena", "2020-02-01", None),
    ("SLL", "Leone", "2020-02-01", None),
    ("SOS", "Xelim somali", "2020-02-01", None),
    ("SRD", "Dólar do Suriname", "2020-02-01", None),
    ("STD", "Dobra", "2020-02-01", None),
    ("SVC", "Colon de El Salvador", "2020-02-01", None),
    ("SYP", "Libra da Síria", "2020-02-01", None),
    ("SZL", "Lilangeni", "2020-02-01", None),
    ("THB", "Baht", "2020-02-01", None),
    ("TJS", "Somoni", "2020-02-01", None),
    ("TMT", "Manat turcomano", "2020-02-01", None),
    ("TND", "Dinar tunisino", "2020-02-01", None),
    ("TOP", "Pa'anga", "2020-02-01", None),
    ("TRY", "Nova Lira turca", "2020-02-01", None),
    ("TTD", "Dólar de Trindade e Tobago", "2020-02-01", None),
    ("TWD", "Novo Dólar de Taiwan", "2020-02-01", None),
    ("TZS", "Xelim da Tanzânia", "2020-02-01", None),
    ("UAH", "Hryvnia", "2020-02-01", None),
    ("UGX", "Xelim do Uganda", "2020-02-01", None),
    ("USD", "Dólar Americano", "2020-02-01", None),
    ("UYU", "Peso Uruguaio", "2020-02-01", None),
    ("UZS", "Som Uzbeque", "2020-02-01", None),
    ("VEF", "Bolívar", "2020-02-01", None),
    ("VES", "Bolívar Soberano", "2020-02-01", None),
    ("VND", "Dong", "2020-02-01", None),
    ("VUV", "Vatu", "2020-02-01", None),
    ("WST", "Tala", "2020-02-01", None),
    ("XAF", "Franco CFA BEAC", "2020-02-01", None),
    ("XAU", "Ouro", "2020-02-01", None),
    ("XBB", "Unidade Monetária Europeia", "2020-02-01", None),
    ("XCD", "Dólar das Caraíbas Orientais", "2020-02-01", None),
    ("XDR", "Direitos Especiais de Saque (FMI)", "2020-02-01", None),
    ("XEU", "Unidade Monetária Europeia (ECU)", "2020-02-01", None),
    ("XFU", "Franco UIC", "2020-02-01", None),
    ("XOF", "Franco CFA BCEAO", "2020-02-01", None),
    ("XPF", "Franco CFP", "2020-02-01", None),
    ("YER", "Rial do Iémene", "2020-02-01", None),
    ("ZAR", "Rand", "2020-02-01", None),
    ("ZMK", "Kwacha", "2020-02-01", None),
    ("ZMW", "Zambian Kwacha", "2020-02-01", None),
    ("ZWL", "Dolar do Zimbabwe", "2020-02-01", None),
    ("GEN", "Outras Exposições não Significativas, ou Fundos de Posição Desconhecida, valor não sujeito a compensação entre posições compradas e vendidas, valor agregado", "2020-02-01", None),
]

# Anexo 6 — Posição País/Exterior (2 domínios).
_ANEXO_6 = [
    ("1", "País", "2019-08-01", None),
    ("2", "Exterior", "2019-08-01", None),
]

# Anexo 7 — País (248 domínios).
_ANEXO_7 = [
    ("AD", "Andorra", "2020-02-01", None),
    ("AE", "Emirados Árabes Unidos", "2020-02-01", None),
    ("AF", "Afeganistão", "2020-02-01", None),
    ("AG", "Antígua e Barbuda", "2020-02-01", None),
    ("AI", "Anguilla", "2020-02-01", None),
    ("AL", "Albânia", "2020-02-01", None),
    ("AM", "Arménia", "2020-02-01", None),
    ("AO", "Angola", "2020-02-01", None),
    ("AQ", "Antártida", "2020-02-01", None),
    ("AR", "Argentina", "2020-02-01", None),
    ("AS", "Samoa Americana", "2020-02-01", None),
    ("AT", "Áustria", "2020-02-01", None),
    ("AU", "Austrália", "2020-02-01", None),
    ("AW", "Aruba", "2020-02-01", None),
    ("AX", "Ilhas Aland", "2020-02-01", None),
    ("AZ", "Azerbaijão", "2020-02-01", None),
    ("BA", "Bósnia e Herzegovina", "2020-02-01", None),
    ("BB", "Barbados", "2020-02-01", None),
    ("BD", "Bangladesh", "2020-02-01", None),
    ("BE", "Bélgica", "2020-02-01", None),
    ("BF", "Burkina Faso", "2020-02-01", None),
    ("BG", "Bulgária", "2020-02-01", None),
    ("BH", "Bahrein", "2020-02-01", None),
    ("BI", "Burundi", "2020-02-01", None),
    ("BJ", "Benim", "2020-02-01", None),
    ("BL", "Saint Barthélemy", "2020-02-01", None),
    ("BM", "Bermudas", "2020-02-01", None),
    ("BN", "Brunei", "2020-02-01", None),
    ("BO", "Bolívia", "2020-02-01", None),
    ("BQ", "Bonaire, Saint Eustatius e Saba", "2020-02-01", None),
    ("BR", "Brasil", "2020-02-01", None),
    ("BS", "Bahamas", "2020-02-01", None),
    ("BT", "Butão", "2020-02-01", None),
    ("BV", "Ilha Bouvet", "2020-02-01", None),
    ("BW", "Botsuana", "2020-02-01", None),
    ("BY", "Bielorrússia", "2020-02-01", None),
    ("BZ", "Belize", "2020-02-01", None),
    ("CA", "Canadá", "2020-02-01", None),
    ("CC", "Ilhas Cocos (Keeling)", "2020-02-01", None),
    ("CD", "República Democrática do Congo", "2020-02-01", None),
    ("CF", "República Centro-Africana", "2020-02-01", None),
    ("CG", "República do Congo", "2020-02-01", None),
    ("CH", "Suíça", "2020-02-01", None),
    ("CI", "Costa do Marfim", "2020-02-01", None),
    ("CK", "Ilhas Cook", "2020-02-01", None),
    ("CL", "Chile", "2020-02-01", None),
    ("CM", "Camarões", "2020-02-01", None),
    ("CN", "China", "2020-02-01", None),
    ("CO", "Colômbia", "2020-02-01", None),
    ("CR", "Costa Rica", "2020-02-01", None),
    ("CU", "Cuba", "2020-02-01", None),
    ("CV", "Cabo Verde", "2020-02-01", None),
    ("CW", "Curaçao", "2020-02-01", None),
    ("CX", "Ilha de Natal", "2020-02-01", None),
    ("CY", "Chipre", "2020-02-01", None),
    ("CZ", "República Tcheca", "2020-02-01", None),
    ("DE", "Alemanha", "2020-02-01", None),
    ("DJ", "Djibouti", "2020-02-01", None),
    ("DK", "Dinamarca", "2020-02-01", None),
    ("DM", "Dominica", "2020-02-01", None),
    ("DO", "República Dominicana", "2020-02-01", None),
    ("DZ", "Argélia", "2020-02-01", None),
    ("EC", "Equador", "2020-02-01", None),
    ("EE", "Estônia", "2020-02-01", None),
    ("EG", "Egito", "2020-02-01", None),
    ("EH", "Saara Ocidental", "2020-02-01", None),
    ("ER", "Eritreia", "2020-02-01", None),
    ("ES", "Espanha", "2020-02-01", None),
    ("ET", "Etiópia", "2020-02-01", None),
    ("FI", "Finlândia", "2020-02-01", None),
    ("FJ", "Fiji", "2020-02-01", None),
    ("FK", "Ilhas Falkland", "2020-02-01", None),
    ("FM", "Estados Federados da Micronésia", "2020-02-01", None),
    ("FO", "Ilhas Faroé", "2020-02-01", None),
    ("FR", "França", "2020-02-01", None),
    ("GA", "Gabão", "2020-02-01", None),
    ("GB", "Reino Unido", "2020-02-01", None),
    ("GD", "Granada", "2020-02-01", None),
    ("GE", "Geórgia", "2020-02-01", None),
    ("GF", "Guiana Francesa", "2020-02-01", None),
    ("GG", "Guernesei", "2020-02-01", None),
    ("GH", "Gana", "2020-02-01", None),
    ("GI", "Gibraltar", "2020-02-01", None),
    ("GL", "Gronelândia", "2020-02-01", None),
    ("GM", "Gâmbia", "2020-02-01", None),
    ("GN", "Guiné", "2020-02-01", None),
    ("GP", "Guadalupe", "2020-02-01", None),
    ("GQ", "Guiné Equatorial", "2020-02-01", None),
    ("GR", "Grécia", "2020-02-01", None),
    ("GS", "Ilhas Geórgia do Sul e Sandwich do Sul", "2020-02-01", None),
    ("GT", "Guatemala", "2020-02-01", None),
    ("GU", "Guam", "2020-02-01", None),
    ("GW", "Guiné-Bissau", "2020-02-01", None),
    ("GY", "Guiana", "2020-02-01", None),
    ("HK", "Hong Kong", "2020-02-01", None),
    ("HM", "Ilha Heard e Ilhas McDonald", "2020-02-01", None),
    ("HN", "Honduras", "2020-02-01", None),
    ("HR", "Croácia", "2020-02-01", None),
    ("HT", "Haiti", "2020-02-01", None),
    ("HU", "Hungria", "2020-02-01", None),
    ("ID", "Indonésia", "2020-02-01", None),
    ("IE", "Irlanda", "2020-02-01", None),
    ("IL", "Israel", "2020-02-01", None),
    ("IM", "Ilha de Man", "2020-02-01", None),
    ("IN", "Índia", "2020-02-01", None),
    ("IO", "Território Britânico do Oceano Índico", "2020-02-01", None),
    ("IQ", "Iraque", "2020-02-01", None),
    ("IR", "Irã", "2020-02-01", None),
    ("IS", "Islândia", "2020-02-01", None),
    ("IT", "Itália", "2020-02-01", None),
    ("JE", "Jersey", "2020-02-01", None),
    ("JM", "Jamaica", "2020-02-01", None),
    ("JO", "Jordânia", "2020-02-01", None),
    ("JP", "Japão", "2020-02-01", None),
    ("KE", "Quênia", "2020-02-01", None),
    ("KG", "Quirguistão", "2020-02-01", None),
    ("KH", "Camboja", "2020-02-01", None),
    ("KI", "Quiribati", "2020-02-01", None),
    ("KM", "Comores", "2020-02-01", None),
    ("KN", "São Cristóvão e Nevis", "2020-02-01", None),
    ("KP", "Coreia do Norte", "2020-02-01", None),
    ("KR", "Coreia do Sul", "2020-02-01", None),
    ("KW", "Kuwait", "2020-02-01", None),
    ("KY", "Ilhas Cayman", "2020-02-01", None),
    ("KZ", "Cazaquistão", "2020-02-01", None),
    ("LA", "Laos", "2020-02-01", None),
    ("LB", "Líbano", "2020-02-01", None),
    ("LC", "Santa Lúcia", "2020-02-01", None),
    ("LI", "Liechtenstein", "2020-02-01", None),
    ("LK", "Sri Lanka", "2020-02-01", None),
    ("LR", "Libéria", "2020-02-01", None),
    ("LS", "Lesoto", "2020-02-01", None),
    ("LT", "Lituânia", "2020-02-01", None),
    ("LU", "Luxemburgo", "2020-02-01", None),
    ("LV", "Letônia", "2020-02-01", None),
    ("LY", "Líbia", "2020-02-01", None),
    ("MA", "Marrocos", "2020-02-01", None),
    ("MC", "Mónaco", "2020-02-01", None),
    ("MD", "Moldávia", "2020-02-01", None),
    ("ME", "Montenegro", "2020-02-01", None),
    ("MF", "Saint Martin", "2020-02-01", None),
    ("MG", "Madagáscar", "2020-02-01", None),
    ("MH", "Ilhas Marshall", "2020-02-01", None),
    ("MK", "Macedónia", "2020-02-01", None),
    ("ML", "Mali", "2020-02-01", None),
    ("MM", "Mianmar", "2020-02-01", None),
    ("MN", "Mongólia", "2020-02-01", None),
    ("MO", "Macau", "2020-02-01", None),
    ("MP", "Ilhas Marianas do Norte", "2020-02-01", None),
    ("MQ", "Martinica", "2020-02-01", None),
    ("MR", "Mauritânia", "2020-02-01", None),
    ("MS", "Monserrate", "2020-02-01", None),
    ("MT", "Malta", "2020-02-01", None),
    ("MU", "Maurícia", "2020-02-01", None),
    ("MV", "Maldivas", "2020-02-01", None),
    ("MW", "Malawi", "2020-02-01", None),
    ("MX", "México", "2020-02-01", None),
    ("MY", "Malásia", "2020-02-01", None),
    ("MZ", "Moçambique", "2020-02-01", None),
    ("NC", "Nova Caledônia", "2020-02-01", None),
    ("NE", "Níger", "2020-02-01", None),
    ("NF", "Ilha Norfolk", "2020-02-01", None),
    ("NG", "Nigéria", "2020-02-01", None),
    ("NI", "Nicarágua", "2020-02-01", None),
    ("NL", "Holanda", "2020-02-01", None),
    ("NO", "Noruega", "2020-02-01", None),
    ("NP", "Nepal", "2020-02-01", None),
    ("NR", "Nauru", "2020-02-01", None),
    ("NU", "Niue", "2020-02-01", None),
    ("NZ", "Nova Zelândia", "2020-02-01", None),
    ("OM", "Omã", "2020-02-01", None),
    ("PA", "Panamá", "2020-02-01", None),
    ("PE", "Peru", "2020-02-01", None),
    ("PF", "Polinésia Francesa", "2020-02-01", None),
    ("PG", "Papua-Nova Guiné", "2020-02-01", None),
    ("PH", "Filipinas", "2020-02-01", None),
    ("PK", "Paquistão", "2020-02-01", None),
    ("PL", "Polónia", "2020-02-01", None),
    ("PM", "São Pedro e Miquelão", "2020-02-01", None),
    ("PN", "Pitcairn", "2020-02-01", None),
    ("PR", "Porto Rico", "2020-02-01", None),
    ("PS", "Palestina", "2020-02-01", None),
    ("PT", "Portugal", "2020-02-01", None),
    ("PW", "Palau", "2020-02-01", None),
    ("PY", "Paraguai", "2020-02-01", None),
    ("QA", "Qatar", "2020-02-01", None),
    ("RE", "Reunião", "2020-02-01", None),
    ("RO", "Roménia", "2020-02-01", None),
    ("RS", "Sérvia", "2020-02-01", None),
    ("RU", "Rússia", "2020-02-01", None),
    ("RW", "Ruanda", "2020-02-01", None),
    ("SA", "Arábia Saudita", "2020-02-01", None),
    ("SB", "Ilhas Salomão", "2020-02-01", None),
    ("SC", "Seychelles", "2020-02-01", None),
    ("SD", "Sudão", "2020-02-01", None),
    ("SE", "Suécia", "2020-02-01", None),
    ("SG", "Singapura", "2020-02-01", None),
    ("SH", "Santa Helena, Ascensão e Tristão da Cunha", "2020-02-01", None),
    ("SI", "Eslovênia", "2020-02-01", None),
    ("SJ", "Svalbard e Jan Mayen", "2020-02-01", None),
    ("SK", "Eslováquia", "2020-02-01", None),
    ("SL", "Serra Leoa", "2020-02-01", None),
    ("SM", "San Marino", "2020-02-01", None),
    ("SN", "Senegal", "2020-02-01", None),
    ("SO", "Somália", "2020-02-01", None),
    ("SR", "Suriname", "2020-02-01", None),
    ("SS", "Sudão do Sul", "2020-02-01", None),
    ("ST", "São Tomé e Príncipe", "2020-02-01", None),
    ("SV", "El Salvador", "2020-02-01", None),
    ("SX", "Sint Maarten", "2020-02-01", None),
    ("SY", "Síria", "2020-02-01", None),
    ("SZ", "Suazilândia", "2020-02-01", None),
    ("TC", "Ilhas Turks e Caicos", "2020-02-01", None),
    ("TD", "Chade", "2020-02-01", None),
    ("TF", "Territórios Franceses Do Sul", "2020-02-01", None),
    ("TG", "Togo", "2020-02-01", None),
    ("TH", "Tailândia", "2020-02-01", None),
    ("TJ", "Tajiquistão", "2020-02-01", None),
    ("TK", "Toquelau", "2020-02-01", None),
    ("TL", "Timor-Leste", "2020-02-01", None),
    ("TM", "Turcomenistão", "2020-02-01", None),
    ("TN", "Tunísia", "2020-02-01", None),
    ("TO", "Tonga", "2020-02-01", None),
    ("TR", "Turquia", "2020-02-01", None),
    ("TT", "Trinidad e Tobago", "2020-02-01", None),
    ("TV", "Tuvalu", "2020-02-01", None),
    ("TW", "Taiwan", "2020-02-01", None),
    ("TZ", "Tanzânia", "2020-02-01", None),
    ("UA", "Ucrânia", "2020-02-01", None),
    ("UG", "Uganda", "2020-02-01", None),
    ("UM", "Ilhas Menores Distantes dos Estados Unidos", "2020-02-01", None),
    ("US", "Estados Unidos", "2020-02-01", None),
    ("UY", "Uruguai", "2020-02-01", None),
    ("UZ", "Uzbequistão", "2020-02-01", None),
    ("VA", "Vaticano", "2020-02-01", None),
    ("VC", "São Vicente e Granadinas", "2020-02-01", None),
    ("VE", "Venezuela", "2020-02-01", None),
    ("VG", "Ilhas Virgens Britânicas", "2020-02-01", None),
    ("VI", "Ilhas Virgens Americanas", "2020-02-01", None),
    ("VN", "Vietnã", "2020-02-01", None),
    ("VU", "Vanuatu", "2020-02-01", None),
    ("WF", "Wallis e Futuna", "2020-02-01", None),
    ("WS", "Samoa", "2020-02-01", None),
    ("YE", "Iêmen", "2020-02-01", None),
    ("YT", "Mayotte", "2020-02-01", None),
    ("ZA", "África do Sul", "2020-02-01", None),
    ("ZM", "Zâmbia", "2020-02-01", None),
    ("ZW", "Zimbábue", "2020-02-01", None),
]

# (numero_anexo, campo em reference.dominios, linhas)
_ANEXOS = [
    (1, "tipoEnvio", _ANEXO_1),
    (2, "codigoParametro", _ANEXO_2),
    (3, "codigoElemento", _ANEXO_3),
    (4, "Conta", _ANEXO_4),
    (5, "moeda", _ANEXO_5),
    (6, "posicaoPaisExterior", _ANEXO_6),
    (7, "pais", _ANEXO_7),
]

# COMMAND ----------
# MAGIC %md
# MAGIC ## Carga em `reference.dominios`
# MAGIC
# MAGIC A tabela é criada por `setup_reference_tables.py` (task anterior do mesmo
# MAGIC job). Aqui só inserimos — com `CREATE TABLE IF NOT EXISTS` defensivo para o
# MAGIC caso deste notebook rodar isolado.

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.dominios (
    dominio_sk BIGINT GENERATED ALWAYS AS IDENTITY,
    documento STRING NOT NULL,
    campo STRING NOT NULL,
    valor_codigo STRING NOT NULL,
    valor_descricao STRING NOT NULL,
    anexo_referencia STRING,
    leiaute_versao STRING NOT NULL,
    dt_vigencia_ini DATE NOT NULL,
    dt_vigencia_fim DATE,
    is_current BOOLEAN NOT NULL,
    observacoes STRING
)
TBLPROPERTIES ('delta.logRetentionDuration' = 'interval 1825 days')
""")

# Idempotência: este notebook é dono EXCLUSIVO das linhas do documento 2011.
spark.sql(f"DELETE FROM {CATALOG}.{SCHEMA}.dominios WHERE documento = '{DOCUMENTO}'")

_registros = []
for _numero, _campo, _linhas in _ANEXOS:
    for _codigo, _descricao, _dt_ini, _dt_fim in _linhas:
        _registros.append(
            (
                DOCUMENTO,
                _campo,
                _codigo,
                _descricao,
                f"Anexo {_numero}",
                LEIAUTE_VERSAO,
                _dt_ini,
                _dt_fim,
                _dt_fim is None,   # is_current: sem data-fim = vigente
                None,
            )
        )

_df = spark.createDataFrame(
    _registros,
    "documento STRING, campo STRING, valor_codigo STRING, valor_descricao STRING, "
    "anexo_referencia STRING, leiaute_versao STRING, dt_vigencia_ini STRING, "
    "dt_vigencia_fim STRING, is_current BOOLEAN, observacoes STRING",
).selectExpr(
    "documento", "campo", "valor_codigo", "valor_descricao", "anexo_referencia",
    "leiaute_versao", "CAST(dt_vigencia_ini AS DATE) AS dt_vigencia_ini",
    "CAST(dt_vigencia_fim AS DATE) AS dt_vigencia_fim", "is_current", "observacoes",
)
_df.write.mode("append").saveAsTable(f"{CATALOG}.{SCHEMA}.dominios")

print(f"  {len(_registros)} domínios do CADOC {DOCUMENTO} inseridos.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Views de domínio para os checks DQX
# MAGIC
# MAGIC Uma view por campo, com o filtro `documento`/`campo` encapsulado — o check
# MAGIC no DQX Studio fica só com
# MAGIC `col IN (SELECT valor_codigo FROM reference.v_dom_2011_<campo>)`, sem literal
# MAGIC string. Mesma convenção das views `v_dom_3040_*`.

# COMMAND ----------

for _campo, _view in [
    ("tipoEnvio", "v_dom_2011_tipoenvio"),
    ("codigoParametro", "v_dom_2011_parametro"),
    ("codigoElemento", "v_dom_2011_elemento"),
    ("Conta", "v_dom_2011_conta"),
    ("moeda", "v_dom_2011_moeda"),
    ("posicaoPaisExterior", "v_dom_2011_posicao"),
    ("pais", "v_dom_2011_pais"),
]:
    spark.sql(f"""
        CREATE OR REPLACE VIEW {CATALOG}.{SCHEMA}.{_view} AS
        SELECT valor_codigo
        FROM {CATALOG}.{SCHEMA}.dominios
        WHERE documento = '{DOCUMENTO}' AND campo = '{_campo}' AND is_current
    """)
    print(f"  view {_view} pronta")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Datas-base válidas (dias úteis do calendário BCB)
# MAGIC
# MAGIC O DDR é o único CADOC **diário** do acelerador, então "a data-base é dia
# MAGIC útil" é um check próprio dele. A view expõe só a coluna `data` dos dias
# MAGIC úteis para o check ficar em `dt_base IN (SELECT data FROM …)`, sem literal.
# MAGIC
# MAGIC Depende de `reference.bcb_calendar`, criada pela task `setup_reference` —
# MAGIC que é predecessora desta em `setup_job.yml` e no `rc18_end_to_end`.

# COMMAND ----------

spark.sql(f"""
    CREATE OR REPLACE VIEW {CATALOG}.{SCHEMA}.v_dom_2011_data_base AS
    SELECT data
    FROM {CATALOG}.{SCHEMA}.bcb_calendar
    WHERE is_dia_util
""")
print("  view v_dom_2011_data_base pronta (dias úteis do calendário BCB)")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Status bloqueante das críticas do DDR
# MAGIC
# MAGIC `gold.criticas_ddr_2011` materializa as duas críticas INTRA-documento do BCB
# MAGIC (4693 e 4751) com uma coluna `status`; o check DQX faz
# MAGIC `status NOT IN (SELECT valor_codigo FROM v_crit_2011_status_bloqueante)`.
# MAGIC Mesmo padrão de `v_recon_status_bloqueante` para o batimento COSIF.

# COMMAND ----------

spark.sql(f"""
INSERT INTO {CATALOG}.{SCHEMA}.dominios
    (documento, campo, valor_codigo, valor_descricao, anexo_referencia,
     leiaute_versao, dt_vigencia_ini, dt_vigencia_fim, is_current, observacoes)
VALUES
  ('{DOCUMENTO}', 'CriticaStatusBloqueante', 'BLOQUEADO',
   'Crítica intra-documento do DDR violada — impede a remessa',
   'Críticas de Pós-processamento 2011 V2', '{LEIAUTE_VERSAO}',
   DATE'2020-03-01', NULL, true, NULL)
""")

spark.sql(f"""
    CREATE OR REPLACE VIEW {CATALOG}.{SCHEMA}.v_crit_2011_status_bloqueante AS
    SELECT valor_codigo
    FROM {CATALOG}.{SCHEMA}.dominios
    WHERE documento = '{DOCUMENTO}' AND campo = 'CriticaStatusBloqueante' AND is_current
""")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Resumo

# COMMAND ----------

display(
    spark.sql(f"""
        SELECT campo, anexo_referencia, COUNT(*) AS dominios,
               SUM(CASE WHEN is_current THEN 1 ELSE 0 END) AS vigentes
        FROM {CATALOG}.{SCHEMA}.dominios
        WHERE documento = '{DOCUMENTO}'
        GROUP BY campo, anexo_referencia
        ORDER BY anexo_referencia, campo
    """)
)
print(f"Domínios do CADOC {DOCUMENTO} prontos em {CATALOG}.{SCHEMA}.dominios")
