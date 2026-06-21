"""
Schema dos registros estruturados de eventos corporativos.

Cada campo é envolvido em CampoExtraido para que NUNCA percamos a
rastreabilidade: todo valor carrega sua confiança e o trecho do
texto-fonte que o justifica. Isso é o que permite a um operador de
Asset Servicing auditar o registro sem reabrir o PDF.
"""
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class TipoEvento(str, Enum):
    DIVIDENDO = "dividendo"
    JCP = "jcp"
    BONIFICACAO = "bonificacao"
    GRUPAMENTO = "grupamento"
    DESDOBRAMENTO = "desdobramento"
    INDETERMINADO = "indeterminado"


class NivelConfianca(str, Enum):
    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"


class MetodoExtracao(str, Enum):
    TEXTO_NATIVO = "texto_nativo"  # extraído de PDF binário real via pdfplumber
    TEXTO_PLANO = "texto_plano"    # arquivo não é um PDF binário válido; lido como texto puro
    OCR = "ocr"
    INDISPONIVEL = "indisponivel"


class CampoExtraido(BaseModel):
    """Envelope de auditoria para um valor extraído."""
    valor: Optional[str] = None
    confianca: NivelConfianca = NivelConfianca.BAIXA
    fonte: Optional[str] = Field(
        default=None, description="Trecho literal do documento que originou o valor"
    )
    justificativa: Optional[str] = Field(
        default=None, description="Por que o modelo decidiu esse valor/confiança"
    )


class ResultadoValidacao(BaseModel):
    regra: str
    status: str  # "ok" | "falha" | "nao_aplicavel"
    detalhe: str


class RegistroEvento(BaseModel):
    documento: str
    metodo_extracao: MetodoExtracao = MetodoExtracao.TEXTO_NATIVO

    emissor: CampoExtraido = CampoExtraido()
    cnpj: CampoExtraido = CampoExtraido()
    isin: CampoExtraido = CampoExtraido()
    ticker: CampoExtraido = CampoExtraido()
    classe: CampoExtraido = CampoExtraido()  # ON / PN

    tipo_evento: CampoExtraido = CampoExtraido()

    data_aprovacao: CampoExtraido = CampoExtraido()
    data_com: CampoExtraido = CampoExtraido()
    data_ex: CampoExtraido = CampoExtraido()
    data_pagamento: CampoExtraido = CampoExtraido()

    valor_bruto_por_acao: CampoExtraido = CampoExtraido()
    valor_liquido_por_acao: CampoExtraido = CampoExtraido()
    aliquota_irrf: CampoExtraido = CampoExtraido()
    proporcao: CampoExtraido = CampoExtraido()  # bonificação / grupamento, ex: "1:20" ou "10:1"
    custo_atribuido_fiscal: CampoExtraido = CampoExtraido()
    moeda: CampoExtraido = CampoExtraido()

    validacoes: List[ResultadoValidacao] = []
    confianca_geral: NivelConfianca = NivelConfianca.BAIXA
    requer_revisao_humana: bool = False
    motivos_revisao: List[str] = []

    class Config:
        use_enum_values = True
