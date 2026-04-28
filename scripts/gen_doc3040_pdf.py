"""Gera documentação PDF da estrutura do XML SCR Doc 3040 (layout BACEN 202601).

Fontes consolidadas:
- XSD scr3040.202601.xsd (extraído do SCR3040_Validador.zip)
- Instruções de Preenchimento Doc 3040 (docs/scr3040/SCR_InstrucoesDePreenchimento_Doc3040.pdf)
- Planilha de Críticas (docs/scr3040/SCR3040_Criticas.xls)
- Exemplo oficial (docs/scr3040/exemploDocPadraoInfosBasicas.xml)
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether,
)
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY
from datetime import date


OUT = "docs/generated/SCR_Doc3040_Especificacao_XML.pdf"


# ---------- Estilos ----------
ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontSize=18, textColor=colors.HexColor("#005CA9"),
                    spaceAfter=14, spaceBefore=8)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=14, textColor=colors.HexColor("#005CA9"),
                    spaceAfter=10, spaceBefore=14)
H3 = ParagraphStyle("H3", parent=ss["Heading3"], fontSize=11, textColor=colors.HexColor("#333333"),
                    spaceAfter=6, spaceBefore=8)
BODY = ParagraphStyle("Body", parent=ss["BodyText"], fontSize=9.5, leading=13,
                      alignment=TA_JUSTIFY, spaceAfter=6)
SMALL = ParagraphStyle("Small", parent=ss["BodyText"], fontSize=8, leading=11,
                       textColor=colors.HexColor("#555555"))
CODE = ParagraphStyle("Code", parent=ss["Code"], fontSize=8, leading=10,
                      fontName="Courier", textColor=colors.HexColor("#222222"),
                      backColor=colors.HexColor("#F3F4F6"), leftIndent=8, rightIndent=8,
                      spaceBefore=4, spaceAfter=6)


def p(text, style=BODY):
    return Paragraph(text, style)


def header_table(columns, rows, col_widths):
    data = [columns] + rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#005CA9")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, 0), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


# Helper to wrap cell content as Paragraph (needed for long text)
def wrap(text, size=8):
    st = ParagraphStyle("cell", parent=ss["BodyText"], fontSize=size, leading=size + 2)
    return Paragraph(text, st)


# ---------- Conteúdo ----------
story = []

# Capa
story += [
    Spacer(1, 3 * cm),
    p("Especificação do Arquivo XML<br/>SCR Documento 3040",
      ParagraphStyle("cover1", parent=ss["Title"], fontSize=26,
                     textColor=colors.HexColor("#005CA9"), alignment=1)),
    Spacer(1, 0.6 * cm),
    p("Layout de referência: <b>scr3040.202601.xsd</b> (data-base ≥ jan/2026)",
      ParagraphStyle("cover2", parent=ss["Heading2"], fontSize=12, alignment=1,
                     textColor=colors.HexColor("#444444"))),
    Spacer(1, 4 * cm),
    p(f"<b>Gerado em:</b> {date.today().isoformat()}<br/>"
      f"<b>Projeto:</b> RC18 Starter Kit — BACEN Resolução Conjunta nº 18<br/>"
      f"<b>Autor da compilação:</b> Equipe de Governança SCR",
      ParagraphStyle("cover3", parent=BODY, alignment=1, fontSize=10)),
    Spacer(1, 2 * cm),
    p("Este documento consolida, em forma de referência prática, a estrutura do arquivo "
      "XML exigido pelo Banco Central do Brasil para o envio do Documento 3040 do SCR "
      "(Sistema de Informações de Crédito). Baseia-se no XSD oficial embarcado no "
      "Aplicativo Validador, nas Instruções de Preenchimento do BACEN e na planilha "
      "de Críticas (regras B/C/S/I) vigentes para o layout janeiro/2026.",
      ParagraphStyle("cover4", parent=BODY, alignment=TA_JUSTIFY, fontSize=10, leftIndent=40, rightIndent=40)),
    PageBreak(),
]

# 1. Introdução
story += [
    p("1. Introdução", H1),
    p("O Documento 3040 é a remessa mensal em que as instituições financeiras informam "
      "ao SCR os detalhes das operações de crédito em suas carteiras — individualmente "
      "(tag <b>Cli</b> / <b>Op</b>) ou em blocos agregados para valores abaixo do limite "
      "de responsabilidade (tag <b>Agreg</b>). A remessa é um arquivo <b>XML UTF-8</b> "
      "encapsulado em ZIP gerado pelo Aplicativo Validador antes do envio ao Banco Central."),
    p("Este documento foca a estrutura do XML <i>antes</i> da compactação, i.e., o payload "
      "com a árvore de elementos e atributos. Os atributos marcados como "
      "<b>obrigatórios</b> seguem o atributo <code>use=\"required\"</code> do XSD; demais "
      "são condicionais (obrigatórios sob regras de negócio do tipo C/S) ou opcionais."),

    p("2. Visão geral da hierarquia", H1),
    p("A árvore do arquivo segue a estrutura abaixo. Elementos marcados com <b>[0..N]</b> "
      "podem ocorrer várias vezes; <b>[0..1]</b> são opcionais e únicos quando presentes."),
    Paragraph(
        "<font face='Courier' size='9'>"
        "Doc3040<br/>"
        "├── ConIpocs        [0..N]  operações conectadas (IPOCs relacionados)<br/>"
        "├── Cli             [0..N]  cliente individualizado<br/>"
        "│   └── Op          [1..N]  operação de crédito do cliente<br/>"
        "│       ├── Venc    [0..1]  distribuição do saldo por bucket de prazo<br/>"
        "│       ├── Gar     [0..N]  garantias (real ou fidejussória)<br/>"
        "│       ├── Inf     [0..N]  informações adicionais (saídas, cessões, etc.)<br/>"
        "│       ├── Sicor   [0..1]  dados de crédito rural (Sicor)<br/>"
        "│       └── ContInstFinRes4966  [0..1]  contábil Res. 4.966 (Estagio/Perda)<br/>"
        "└── Agreg           [0..N]  operações agregadas (responsabilidade &lt; R$200)</font>",
        CODE),
    PageBreak(),
]


# 3. <Doc3040>
doc_rows = [
    ["DtBase", "Obrigatório", "tipoDataMesAno (YYYY-MM)",
     "Mês de referência da remessa. Deve corresponder à data-base esperada."],
    ["CNPJ", "Obrigatório", "tipoCNPJ8 (8 dígitos)",
     "Raiz do CNPJ (base) da instituição remetente."],
    ["Remessa", "Obrigatório", "tipoParteRemessa",
     "Número sequencial da remessa (substituições usam número crescente)."],
    ["Parte", "Obrigatório", "tipoParteRemessa",
     "Parte dentro da remessa (N≥1). A última parte deve indicar Fim-de-Remessa."],
    ["TpArq", "Opcional", "tipoArquivo (F, P)",
     "F=Full (completo); P=Parcial (substituição parcial via Doc 3042)."],
    ["NomeResp", "Obrigatório", "tipoNomeResp",
     "Nome do responsável pelo envio na IF."],
    ["EmailResp", "Obrigatório", "tipoEmailResp",
     "E-mail do responsável para contato BACEN."],
    ["TelResp", "Obrigatório", "tipoTelResp",
     "Telefone do responsável (DDD+número)."],
    ["TotalCli", "Opcional", "tipoQuantidadeComZero",
     "Número total de clientes informados no arquivo completo (consolidado entre partes)."],
    ["TpFundo", "Condicional", "tpFundo (36, 46, …)",
     "Obrigatório e exclusivo para FIDCs. Omitido para instituições comuns."],
    ["MetodApPE", "C69", "tipoMetodologia (C, S)",
     "Metodologia de Apuração da Perda Esperada: C=Completa, S=Simplificada. "
     "Obrigatório quando TpFundo está vazio."],
    ["MetodDifTJE", "C69", "tipoSimNao (S, N)",
     "Metodologia TJE diferenciada. Obrigatório quando TpFundo está vazio."],
]

story += [
    p("3. Elemento raiz &lt;Doc3040&gt;", H1),
    p("Cabeçalho do documento. Identifica a IF remetente, a data-base, a responsabilidade "
      "pela emissão e a metodologia contábil adotada (Res. 4.966/2021)."),
    header_table(
        ["Atributo", "Obrigat.", "Tipo (XSD)", "Descrição"],
        [[wrap(c) for c in row] for row in doc_rows],
        col_widths=[2.6*cm, 2.2*cm, 3.8*cm, 8.0*cm]),
    Spacer(1, 0.4*cm),
    p("<b>Exemplo:</b>", H3),
    p("<code>&lt;Doc3040 DtBase=\"2026-03\" CNPJ=\"99999999\" Remessa=\"1\" Parte=\"1\" "
      "TpArq=\"F\" NomeResp=\"Equipe SCR\" EmailResp=\"scr@if.com.br\" TelResp=\"1133000000\" "
      "TotalCli=\"500\" MetodApPE=\"C\" MetodDifTJE=\"N\"&gt;</code>", CODE),
    PageBreak(),
]


# 4. <Cli>
cli_rows = [
    ["Tp", "Obrigatório", "tipoDoCliente",
     "Tipo do cliente: 1=PF residente, 2=PJ residente, 3=PJ estrangeira, 4=Gov, 5=PF n-res, 6=Fundo/Assemelhada."],
    ["Cd", "Obrigatório", "tipoCodCliente (1–14 alfanum.)",
     "Identificador do cliente na IF. Para PJ, coincide com a raiz do CNPJ (8 dígitos)."],
    ["Autorzc", "Obrigatório", "tipoSimNao",
     "S/N — autorização do cliente para consulta de informações no SCR."],
    ["IniRelactCli", "Obrigatório", "tipoData (YYYY-MM-DD)",
     "Data de início do relacionamento bancário com o cliente."],
    ["FatAnual", "C31", "tipoValor10Trilhoes",
     "Faturamento anual (informação contábil mais recente). Obrigatório para Tp ∈ {2, 4, 6} "
     "em operações concedidas a partir de jul/2011."],
    ["PorteCli", "Opcional (C07 limita)", "tipoPorteCliente (0..8)",
     "Porte do cliente. Para Tp ∈ {2,4,6} é restrito a 0–4 (regra C07)."],
    ["TpCtrl", "C01", "tipoControle (01..04)",
     "Tipo de controle societário (Anexo 10). Obrigatório para Tp ∈ {2,4,6}."],
    ["CongEcon", "Opcional", "tipoCodConglomerado",
     "Código do conjunto de contrapartes conectadas. <b>Omitir</b> quando o cliente não "
     "pertence a conglomerado algum."],
    ["NomeCli", "Opcional", "tipoNomeCli",
     "Nome do cliente (texto livre). Use com parcimônia (dados pessoais)."],
    ["TpIdentExt, CodExt, IdLiderBR, IdPais", "Opcional", "tipos dedicados",
     "Campos para clientes estrangeiros / vinculados a líderes no Brasil."],
]

story += [
    p("4. Elemento &lt;Cli&gt;", H1),
    p("Cada tag <b>Cli</b> representa um tomador de crédito com pelo menos uma operação no "
      "documento. No layout 202601, o atributo <i>ClassCli</i> (classificação de risco do "
      "cliente) foi <b>descontinuado</b> e não deve ser informado."),
    header_table(
        ["Atributo", "Obrigat.", "Tipo (XSD)", "Descrição"],
        [[wrap(c) for c in row] for row in cli_rows],
        col_widths=[3.4*cm, 2.4*cm, 3.8*cm, 7.0*cm]),
    PageBreak(),
]


# 5. <Op>
op_rows = [
    ["DetCli", "Obrigatório", "tipoCNPJ14",
     "Detalhamento do cliente. Para PJ: CNPJ completo (14 dígitos, base+filial+DV). "
     "Para PF: o CPF é reportado em Cli/@Cd e DetCli segue regra específica."],
    ["Contrt", "Obrigatório", "tipoCodContrato",
     "Código interno do contrato. Único para o par (cliente, modalidade)."],
    ["NatuOp", "Obrigatório", "tipoNaturezaIndiv (01..05, 11..16, 32..34)",
     "Natureza da operação (Anexo 2). Ex.: 01=operação original; 11=cessão com coobrigação."],
    ["Mod", "Obrigatório", "tipoModalidade (pattern)",
     "Modalidade conforme Anexo 3 (ex.: 0101, 0202, 0204, 0301, 0401...)."],
    ["OrigemRec", "Obrigatório", "tipoOrigemRec",
     "Origem dos recursos. Pattern: 0?10[1-2] | 0?199 | 0?20[1-9] | 0?21[0-3] | 0?299. "
     "<b>0100 não é válido</b> no layout 2026."],
    ["Indx", "Obrigatório", "tipoIndexador (enum)",
     "Indexador do saldo (11=prefixado, 21/22/23=dólar/euro/cambial, 31=TR, 32/39=TJLP/outros, "
     "41-43=IGP, 49-54=índices diversos, 91=IPCA, 99=outros)."],
    ["PercIndx", "C32", "tipoTaxa",
     "Percentual do indexador aplicado. Obrigatório para operações concedidas a partir de set/2011."],
    ["VarCamb", "Obrigatório", "tipoVariacaoCambial",
     "Código da moeda de referência. 790=BRL (padrão)."],
    ["DtContr", "Obrigatório", "tipoData",
     "Data de contratação. Para rotativas e cartão, ver tratamento especial nas Instruções."],
    ["VlrContr", "C28", "tipoValor",
     "Valor contratado. Obrigatório para modalidades não rotativas com prazo > 80 dias. "
     "Não exigido para 0101, 0201, 0204, 0210, 0213, 0214, 0406, 1304, 19XX."],
    ["DtVencOp", "Obrigatório", "tipoData",
     "Data de vencimento da operação (data final do contrato)."],
    ["CEP", "Obrigatório", "tipoCEP (8 dígitos)",
     "CEP da agência de contratação."],
    ["TaxEft", "Obrigatório", "tipoTaxa",
     "Taxa efetiva anual contratada (em % ao ano)."],
    ["ProvConsttd", "Obrigatório", "tipoValor",
     "Valor da provisão constituída para a operação na data-base."],
    ["DiaAtraso", "Opcional (S28)", "integer",
     "Dias em atraso. Deve ser coerente com a distribuição de Venc (v2xx/v3xx exigem DiaAtraso > 0)."],
    ["CaracEspecial", "Opcional", "texto",
     "Características especiais (Anexo 8). Múltiplos valores concatenados com ';' (ex.: '02;03')."],
    ["DtaProxParcela, VlrProxParcela, QtdParcelas", "Opcional", "vários",
     "Informações da próxima parcela a vencer. Relevantes para amortização PRICE/SAC."],
    ["IPOC", "Obrigatório", "tipoIpoc (max 67 chars)",
     "Identificação Padronizada da Operação de Crédito (ver seção 9). Chave única no SCR."],
]

story += [
    p("5. Elemento &lt;Op&gt;", H1),
    p("Filho de <b>Cli</b>. Representa uma operação de crédito individualizada. No layout "
      "202601, os atributos <i>ClassOp</i> (classificação de risco da operação) e "
      "<i>Cosif</i> (conta contábil) foram <b>descontinuados</b> e não devem ser informados — "
      "esses controles migraram para a tag filha <b>ContInstFinRes4966</b> (Res. 4.966/2021)."),
    header_table(
        ["Atributo", "Obrigat.", "Tipo (XSD)", "Descrição"],
        [[wrap(c) for c in row] for row in op_rows],
        col_widths=[3.4*cm, 2.2*cm, 3.8*cm, 7.2*cm]),
    PageBreak(),
]


# 6. <Venc>
venc_rows = [
    ["v20", "Limite de crédito com vencimento até 360 dias"],
    ["v40", "Limite de crédito com vencimento acima de 360 dias"],
    ["v60", "Créditos a liberar até 360 dias"],
    ["v80", "Créditos a liberar acima de 360 dias"],
    ["v110", "Créditos a vencer até 30 dias"],
    ["v120", "Créditos a vencer de 31 a 60 dias"],
    ["v130", "Créditos a vencer de 61 a 90 dias"],
    ["v140", "Créditos a vencer de 91 a 180 dias"],
    ["v150", "Créditos a vencer de 181 a 360 dias"],
    ["v160", "Créditos a vencer de 361 a 720 dias"],
    ["v165", "Créditos a vencer de 721 a 1080 dias"],
    ["v170", "Créditos a vencer de 1081 a 1440 dias"],
    ["v175", "Créditos a vencer de 1441 a 1800 dias"],
    ["v180", "Créditos a vencer de 1801 a 5400 dias"],
    ["v190", "Créditos a vencer acima de 5400 dias"],
    ["v199", "Créditos a vencer com prazo indeterminado"],
    ["v205 a v290", "Créditos vencidos (escalonamento de 1 a >540 dias — atraso)"],
    ["v310, v320, v330", "Créditos baixados como prejuízo (até 12m, 12-48m, >48m)"],
]

story += [
    p("6. Elemento &lt;Venc&gt;", H1),
    p("Filho opcional de <b>Op</b>. Distribui o saldo da operação entre faixas de prazo "
      "(vértices). Cada atributo <i>vXXX</i> recebe um valor numérico que soma, para a "
      "operação, o total a vencer/vencido/prejuízo. Em operações normais a vencer, usar "
      "somente v1xx. Operações em atraso usam v2xx (com DiaAtraso > 0 coerente). Prejuízo "
      "usa v3xx. <b>Regra S103:</b> se v3xx > 0, todos os demais vértices e ProvConsttd = 0."),
    header_table(
        ["Bucket", "Faixa"],
        [[wrap(c) for c in row] for row in venc_rows],
        col_widths=[3.5*cm, 13.0*cm]),
    PageBreak(),
]


# 7. <Gar>
gar_rows = [
    ["Tp", "Obrigatório", "tipoDeGarantia (pattern 4 dígitos)",
     "Concatenação Tipo+Subtipo. Famílias: 01xx-08xx real, 09xx fidejussória, 10xx-13xx créditos/debêntures. "
     "Ver Anexo 12 do leiaute para a lista completa."],
    ["Ident", "Condicional (I08)", "tipoCodCliente",
     "Identificador do garantidor fidejussório. Obrigatório para Tp=0901 (CPF, 11 dígitos) "
     "ou 0902 (CNPJ, 14 dígitos)."],
    ["PercGar", "Cond. (fidejussória)", "tipoPorcentagem",
     "Percentual garantido pelo garantidor fidejussório. Vai junto com Ident."],
    ["VlrOrig", "Cond. (real)", "tipoValor",
     "Valor original da garantia real (bem dado em garantia)."],
    ["VlrData", "Cond. (real)", "tipoValor",
     "Valor atual da garantia na última reavaliação."],
    ["DtReav", "Cond. (real)", "tipoData",
     "Data da última reavaliação."],
]

story += [
    p("7. Elemento &lt;Gar&gt;", H1),
    p("Filho opcional de <b>Op</b> (0..N). Classifica cada garantia como <b>real</b> "
      "(ex.: cessão, alienação, hipoteca, penhor) ou <b>fidejussória</b> (aval de PF/PJ). "
      "Os atributos exigidos dependem do tipo:"),
    header_table(
        ["Atributo", "Obrigat.", "Tipo (XSD)", "Descrição"],
        [[wrap(c) for c in row] for row in gar_rows],
        col_widths=[2.4*cm, 3.4*cm, 4.2*cm, 6.6*cm]),
    Spacer(1, 0.3*cm),
    p("<b>Exemplos:</b>", H3),
    p("<code>&lt;Gar Tp=\"0902\" Ident=\"07816184592602\" PercGar=\"80.00\"/&gt;  &lt;!-- fidej. PJ --&gt;<br/>"
      "&lt;Gar Tp=\"0321\" VlrOrig=\"50000.00\" VlrData=\"52000.00\" DtReav=\"2025-06-01\"/&gt;  &lt;!-- real --&gt;</code>",
      CODE),
    PageBreak(),
]


# 8. <ContInstFinRes4966>
cif_rows = [
    ["ClasAtFin", "C70", "tipo1a3 (1..3)",
     "Classificação do Ativo Financeiro: 1=CA (Custo Amortizado), 2=VJORA, 3=VJR."],
    ["EstInstFin", "C71", "tipo1a3",
     "Estágio do Instrumento Financeiro (1, 2 ou 3). Obrigatório quando MetodApPE=C."],
    ["QtdInst", "Opcional", "tipoQuantidadeDoisBilhoes",
     "Quantidade de instrumentos. Uso específico p/ títulos/debêntures."],
    ["VlrContBr", "C79", "tipoValor10Trilhoes",
     "Valor contábil bruto do instrumento financeiro."],
    ["VlrPerdaAcum", "Opcional", "tipoValor",
     "Valor acumulado de perdas (write-off acumulado)."],
    ["VlrJusto", "Opcional", "tipoValor",
     "Valor justo do ativo (mensuração a valor justo)."],
    ["TJE", "C73", "tipoTaxa",
     "Taxa de Juros Efetiva. Obrigatória quando MetodDifTJE=N e ClasAtFin ∈ {1,2}."],
    ["RendMes", "C85", "tipoValor",
     "Rendimento do mês. Obrigatório para Mod 1-13 com Natu {1,2,3,11,13,14,15,32}."],
    ["PdEst1", "Opcional", "tipoSimNao",
     "Indicador de PD (probabilidade de default) em Estágio 1."],
    ["CartProvMin", "C74", "tipoCarteira (C1..C5)",
     "Carteira de provisão mínima (segmentação contábil)."],
    ["TratRisc", "Opcional", "tipoSimNao",
     "Tratamento diferenciado de risco."],
]

estagio_rows = [
    ["Motivo", "Obrigatório (C83)", "tipoMotivoEstagio",
     "Motivo da alocação no estágio. Valores válidos: 101-103 (Estágio 1), 201-202 (Estágio 2), 301-311 (Estágio 3)."],
    ["DtAlocacao", "Obrigatório (C83)", "tipoDataMesAnoDataAlocacao (YYYY-MM)",
     "Data-base em que o instrumento foi alocado no estágio. Deve ser ≤ DtBase."],
]

story += [
    p("8. Elemento &lt;ContInstFinRes4966&gt;", H1),
    p("Filho opcional de <b>Op</b>. Consolida os atributos contábeis exigidos pela "
      "<b>Resolução BCB nº 4.966/2021</b> (alinhamento ao IFRS 9). É obrigatório para "
      "instituições não-fundo nas operações das modalidades 1-14, 18 e 19 com "
      "característica especial 25 (natureza {1,2,3,11,13,14,15,32}). A tag contém filhas "
      "<b>&lt;Estagio&gt;</b> (obrigatória quando EstInstFin preenchido — regra C83) e "
      "<b>&lt;Perda&gt;</b> (para perdas alocadas)."),
    p("<b>Atributos:</b>", H3),
    header_table(
        ["Atributo", "Obrigat.", "Tipo (XSD)", "Descrição"],
        [[wrap(c) for c in row] for row in cif_rows],
        col_widths=[2.6*cm, 2.2*cm, 3.8*cm, 8.0*cm]),
    Spacer(1, 0.3*cm),
    p("<b>Filho &lt;Estagio&gt;:</b>", H3),
    header_table(
        ["Atributo", "Obrigat.", "Tipo (XSD)", "Descrição"],
        [[wrap(c) for c in row] for row in estagio_rows],
        col_widths=[2.6*cm, 3.4*cm, 4.0*cm, 6.6*cm]),
    Spacer(1, 0.3*cm),
    p("<b>Exemplo:</b>", H3),
    p("<code>&lt;ContInstFinRes4966 ClasAtFin=\"1\" EstInstFin=\"1\" CartProvMin=\"C1\" "
      "VlrContBr=\"50000.00\" TJE=\"15.50\" RendMes=\"0.00\"&gt;<br/>"
      "&nbsp;&nbsp;&lt;Estagio Motivo=\"101\" DtAlocacao=\"2026-03\"/&gt;<br/>"
      "&lt;/ContInstFinRes4966&gt;</code>", CODE),
    PageBreak(),
]


# 9. IPOC
story += [
    p("9. Composição do IPOC", H1),
    p("O <b>IPOC</b> (Identificação Padronizada da Operação de Crédito) é a chave única "
      "de uma operação no SCR. No layout 2026 é a concatenação determinística de:"),
    Paragraph(
        "<font face='Courier' size='10'>IPOC = CNPJ_IF(8) + Mod(4) + TpCli(1) + Cli.Cd(8) + Contrt(≤42)</font>",
        CODE),
    p("<b>Exemplo:</b> IF com CNPJ base 99999999, operação mod 0101, cliente PJ "
      "(TpCli=2) com código 00038166 e contrato ABC123 →"),
    Paragraph("<font face='Courier' size='10'>IPOC = 99999999 · 0101 · 2 · 00038166 · ABC123</font>", CODE),
    p("Observações importantes:"),
    p("• Uma vez atribuído, o IPOC <b>não pode mudar</b> — qualquer alteração nos seus "
      "componentes deve ser acompanhada de informação adicional de saída 0316 "
      "(\"Saída por alteração de IPOC\") com motivo específico (Anexo 34)."),
    p("• Duplicatas de IPOC no mesmo arquivo ou entre datas-base reprovam a remessa "
      "(crítica B01 de unicidade)."),
    PageBreak(),
]


# 10. <Agreg>
agreg_rows = [
    ["Mod", "Obrig.", "tipoModalidade"],
    ["NatuOp", "Obrig.", "tipoNaturezaAgreg"],
    ["OrigemRec", "Obrig.", "tipoOrigemRecAgreg (pattern 0?100 | 0?200)"],
    ["VincME", "Obrig.", "tipoSimNao"],
    ["FaixaVlr", "Obrig.", "tipoFaixaValor"],
    ["Localiz", "Obrig.", "tipoLocalizacao"],
    ["TpCli", "Obrig.", "tipoDoCliente"],
    ["TpCtrl", "Obrig.", "tipoControle"],
    ["DesempOp", "Obrig.", "tipoDesempOp"],
    ["QtdOp, QtdCli", "Obrig.", "tipoQuantidade"],
    ["ProvConsttd", "Obrig.", "tipoValorComZero100Bilhoes"],
    ["CaracEspecial", "Opc.", "texto (uma por cesta)"],
]

story += [
    p("10. Elemento &lt;Agreg&gt;", H1),
    p("Bloco de operações <b>agregadas</b> para clientes com responsabilidade total "
      "abaixo de R$200 (microvalores). Permite sumarizar operações homogêneas em cestas "
      "minimizando a granularidade do reporte. Cada tag Agreg representa uma cesta "
      "caracterizada pela combinação de (Mod, NatuOp, OrigemRec, VincME, FaixaVlr, Localiz, "
      "TpCli, TpCtrl, DesempOp, CaracEspecial). <b>Não inclui</b> ClassOp/Cosif (migrados "
      "para o nível 4.966) nem PrzProvm (removidos no layout 2026)."),
    header_table(
        ["Atributo", "Obrigat.", "Tipo (XSD)"],
        [[wrap(c) for c in row] for row in agreg_rows],
        col_widths=[4.5*cm, 2.6*cm, 9.0*cm]),
    p("<b>OrigemRec na Agregada</b> usa o tipo <i>tipoOrigemRecAgreg</i>, cujo pattern "
      "aceita somente <code>0?100 | 0?200</code> — diferente do individualizado "
      "(<i>tipoOrigemRec</i>)."),
    PageBreak(),
]


# 11. Domínios principais
story += [
    p("11. Domínios principais (referências)", H1),
    p("Os valores de atributos como <i>Mod</i>, <i>NatuOp</i>, <i>OrigemRec</i>, "
      "<i>Indx</i> etc. são restritos por patterns/enumerações no XSD. Abaixo um "
      "resumo; os Anexos do leiaute oficial trazem a lista completa."),
    p("<b>Modalidades (Anexo 3)</b> — pattern <code>0?101|0?20[2-4|7-9]|0?21[0-8]|…</code>. "
      "Famílias principais: 0101 (adiantamento), 02xx (empréstimos PF), 03xx (capital de giro), "
      "04xx (financiamento imobiliário/veículos), 05xx (ACC/ACE), 0701-0702 (consignado), "
      "12xx (arrendamento), 13xx (operações rurais).", BODY),
    p("<b>Natureza (Anexo 2)</b> — pattern <code>0?[1-5]|1[1-6]|32|33|34</code>. "
      "01=original; 02-05=modalidades dedicadas; 11-16=cessões/coobrigações; 32-34=reestruturações.", BODY),
    p("<b>Origem de Recursos Individualizada (Anexo 4)</b> — pattern "
      "<code>0?10[1-2]|0?199|0?20[1-9]|0?21[0-3]|0?299</code>. "
      "01xx=recursos livres; 02xx=direcionados (rural, habitacional, microcrédito, FGTS).", BODY),
    p("<b>Indexador (Anexo 5)</b> — enum: 11=prefixado; 21-25=cambial USD/EUR/JPY/GBP/misto; "
      "29=outros cambiais; 31=TR; 32=TJLP/TLP; 39=outros monetários; 41-43=IGP-M/IPCA-E/IPCA; "
      "49=outros índices; 51-54=rentabilidades específicas; 91=IPCA consolidado; 99=outros.", BODY),
    p("<b>Tipo de Garantia (Anexo 12)</b> — pattern abrangente: 01xx=cessão/cheque/duplicata; "
      "02xx=aplicações financeiras; 03xx=imóveis; 04xx=veículos; 05xx=máquinas; "
      "06xx=títulos; 07xx=outros bens; 08xx=seguros; <b>09xx=fidejussórias</b> "
      "(0901=PF, 0902=PJ, 0903=Gov, 0904=ISO); 10xx-13xx=operações/créditos específicos.", BODY),
    p("<b>Classificação Ativo Financeiro (4.966)</b> — <code>tipo1a3</code>: "
      "1=CA (Custo Amortizado), 2=VJORA (Valor Justo Outros Resultados Abrangentes), "
      "3=VJR (Valor Justo via Resultado).", BODY),
    p("<b>Carteira de Provisão Mínima</b> — pattern <code>C[1-5]</code>: "
      "C1-C5 representam níveis de segregação crescente.", BODY),
    p("<b>Motivo de Alocação em Estágio</b> — pattern "
      "<code>1(01|02|03)|2(01|02)|3(01-11)</code>: "
      "101=alocação inicial Estágio 1; 201-202=transição para Estágio 2 (deterioração); "
      "301-311=transição para Estágio 3 (default).", BODY),
    PageBreak(),
]


# 12. Regras (B/C/S/I)
regras_rows = [
    ["B01", "Erro de XML/XSD", "Estrutura não conforme ao XSD da data-base"],
    ["B02", "ZIP não gerado pelo validador", "Arquivo deve ser empacotado pelo Aplicativo Validador"],
    ["B06", "Nº de remessa incompatível", "Substituição exige novo Remessa; Parte repetida é rejeitada"],
    ["B07", "Composição de partes", "Partes numeradas 1..N, última com Fim-de-Remessa"],
    ["C01", "TpCtrl obrigatório", "Para Tp ∈ {2, 4, 6}"],
    ["C07", "PorteCli limitado", "Para Tp ∈ {2, 4, 6} → PorteCli ∈ {0..4}"],
    ["C28", "VlrContr obrigatório", "Exceto mods rotativas (0101, 0201, 0204, 0210, 0213, 0214, 0406, 1304, 19xx)"],
    ["C31", "FatAnual obrigatório", "Para Tp ∈ {2, 4, 6} e concessões ≥ jul/2011"],
    ["C32", "PercIndx obrigatório", "Concessões ≥ set/2011"],
    ["C69", "MetodApPE + MetodDifTJE", "Obrigatórios quando TpFundo = vazio"],
    ["C70", "ClasAtFin (4.966)", "Obrigatório no &lt;ContInstFinRes4966&gt; para Natu ∈ {1,2,3,11,13,14,15,32} e Mod 1-11, 13, 14, 18"],
    ["C71", "EstInstFin quando MetodApPE=C", "Obrigatório em &lt;ContInstFinRes4966&gt;"],
    ["C73", "TJE quando MetodDifTJE=N + ClasAtFin ∈ {1,2}", "Obrigatório em &lt;ContInstFinRes4966&gt;"],
    ["C74", "CartProvMin", "Obrigatório C1-C5 para Mod 1-14, 18 e Natu {1,2,3,11,13,14,15,32}"],
    ["C79", "VlrContBr", "Obrigatório no 4966 para as mesmas condições de C70"],
    ["C83", "Estagio exige Motivo + DtAlocacao", "Se EstInstFin informado (sem Inf de saída 03xx)"],
    ["C85", "RendMes", "Obrigatório para Mod 1-13 + Natu {1,2,3,11,13,14,15,32}"],
    ["S09", "Inf 0101/0105 única em NatuOp=04", "Apenas uma ocorrência permitida"],
    ["S26/S27", "Inf 1001/1002 para NatuOp 02/03", "Pelo menos uma <Inf> específica"],
    ["S28", "DiaAtraso coerente com Venc", "Se há v2xx/v3xx, DiaAtraso > 0"],
    ["S30/S31", "Inf de saída para NatuOp 05/12/16", "Obrigatória"],
    ["S48", "Inf 0401 (chassi) p/ Mod 0401/1206", "Obrigatória"],
    ["S54/S55", "Inf de negociação para NatuOp 11, 13-15", "Obrigatória"],
    ["S100", "Inf 15xx (consignante) p/ Mod 0202", "Obrigatória"],
    ["S103", "v3xx isolado", "Se v3xx > 0, demais vértices e ProvConsttd = 0"],
    ["I08", "Gar fidejussória coerente", "0901=CPF(11) • 0902=CNPJ(14)"],
]

story += [
    p("12. Principais regras da Planilha de Críticas", H1),
    p("Subconjunto das regras vigentes (B=básicas, C=obrigatoriedade de campos, "
      "S=semântica, I=individualizadas) mais relevantes para a geração do XML. A lista "
      "completa está em <b>SCR3040_Criticas.xls</b>."),
    header_table(
        ["Regra", "Resumo", "Condição"],
        [[wrap(c) for c in row] for row in regras_rows],
        col_widths=[1.5*cm, 4.5*cm, 10.0*cm]),
    PageBreak(),
]


# 13. Exemplo completo
story += [
    p("13. Exemplo mínimo completo", H1),
    p("Estrutura de um Doc 3040 contendo 1 cliente PJ com 1 operação (modalidade 0101, "
      "natureza 01), 1 garantia fidejussória PJ, Venc concentrado no bucket v150 "
      "(181-360 dias), e o bloco contábil 4.966."),
    Paragraph(
        "<font face='Courier' size='7'>"
        "&lt;?xml version='1.0' encoding='UTF-8'?&gt;<br/>"
        "&lt;Doc3040 DtBase=\"2026-03\" CNPJ=\"99999999\" Remessa=\"1\" Parte=\"1\" "
        "TpArq=\"F\"<br/>"
        "&nbsp;&nbsp;NomeResp=\"Equipe SCR\" EmailResp=\"scr@if.com.br\" "
        "TelResp=\"1133000000\"<br/>"
        "&nbsp;&nbsp;TotalCli=\"1\" MetodApPE=\"C\" MetodDifTJE=\"N\"&gt;<br/>"
        "&nbsp;&nbsp;&lt;Cli Tp=\"2\" Cd=\"00000001\" Autorzc=\"S\" PorteCli=\"2\" "
        "TpCtrl=\"01\"<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;IniRelactCli=\"2020-01-01\" FatAnual=\"1000000.00\"&gt;<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;&lt;Op DetCli=\"00000001576518\" Contrt=\"ABC123\" "
        "NatuOp=\"01\" Mod=\"0101\"<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;OrigemRec=\"0101\" Indx=\"11\" "
        "PercIndx=\"100.00\" VarCamb=\"790\"<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;DtVencOp=\"2026-09-01\" CEP=\"01310100\" "
        "TaxEft=\"15.50\"<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;DtContr=\"2024-01-01\" "
        "ProvConsttd=\"500.00\" DiaAtraso=\"0\"<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;IPOC=\"999999990101200000001ABC123\"&gt;<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&lt;Venc v150=\"50000.00\"/&gt;<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&lt;Gar Tp=\"0902\" Ident=\"12345678000195\" "
        "PercGar=\"100.00\"/&gt;<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&lt;ContInstFinRes4966 ClasAtFin=\"1\" "
        "EstInstFin=\"1\" CartProvMin=\"C1\"<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;VlrContBr=\"50000.00\" TJE=\"15.50\" "
        "RendMes=\"0.00\"&gt;<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&lt;Estagio Motivo=\"101\" "
        "DtAlocacao=\"2026-03\"/&gt;<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&lt;/ContInstFinRes4966&gt;<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;&lt;/Op&gt;<br/>"
        "&nbsp;&nbsp;&lt;/Cli&gt;<br/>"
        "&lt;/Doc3040&gt;"
        "</font>",
        CODE),
    PageBreak(),
]


# 14. Referências
story += [
    p("14. Referências e fontes", H1),
    p("• <b>BACEN SCR Doc 3040:</b> https://www.bcb.gov.br/estabilidadefinanceira/scrdoc3040"),
    p("• <b>XSD do layout 2026:</b> scr3040.202601.xsd (embarcado no Aplicativo Validador)"),
    p("• <b>Aplicativo Validador:</b> SCR3040_Validador.zip (versão Release 13267 em abr/2026)"),
    p("• <b>Instruções de Preenchimento:</b> SCR_InstrucoesDePreenchimento_Doc3040.pdf"),
    p("• <b>Leiaute Oficial (Anexos):</b> SCR3040_Leiaute.xls"),
    p("• <b>Planilha de Críticas:</b> SCR3040_Criticas.xls"),
    p("• <b>Exemplo oficial:</b> exemploDocPadraoInfosBasicas.xml"),
    p("• <b>Res. BCB nº 4.966/2021:</b> Alinhamento ao IFRS 9 e estrutura de estágios."),
    p("• <b>Res. CMN nº 4.557/2017 Art. 22:</b> Conceito de conjunto de contrapartes conectadas "
      "(conglomerado econômico)."),
    Spacer(1, 0.8*cm),
    p("<i>Documento compilado automaticamente a partir dos artefatos oficiais do BACEN. "
      "Em caso de divergência entre este documento e os materiais oficiais, prevalecem os "
      "materiais oficiais.</i>", SMALL),
]


# ---------- Build ----------
def _footer(canv, doc):
    canv.saveState()
    canv.setFont("Helvetica", 7)
    canv.setFillColor(colors.HexColor("#777777"))
    canv.drawString(2 * cm, 1 * cm,
                    "SCR Doc 3040 — Especificação XML (layout 202601) — RC18 Starter Kit")
    canv.drawRightString(A4[0] - 2 * cm, 1 * cm, f"Página {doc.page}")
    canv.restoreState()


doc = SimpleDocTemplate(OUT, pagesize=A4,
                        leftMargin=2*cm, rightMargin=2*cm,
                        topMargin=2*cm, bottomMargin=2*cm,
                        title="SCR Doc 3040 - Especificacao XML",
                        author="RC18 Starter Kit")
doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
print(f"PDF gerado: {OUT}")
