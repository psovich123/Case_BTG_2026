"""
Tools expostas ao agente via function/tool calling do Anthropic.

Importante: estas funções são DETERMINÍSTICAS (puro Python/pandas),
não outra chamada de LLM. O modelo decide QUANDO chamar e COMO
interpretar o resultado, mas o cálculo em si (comparar com a base de
referência, validar datas, validar valores) não depende de
"julgamento" de IA - isso é o que torna o resultado auditável e
reprodutível.
"""
import pandas as pd
from datetime import datetime
from typing import Optional

_GOLDEN_PATH = "data/golden_records.csv"
_golden_df: Optional[pd.DataFrame] = None


def _load_golden() -> pd.DataFrame:
    global _golden_df
    if _golden_df is None:
        _golden_df = pd.read_csv(_GOLDEN_PATH)
        for col in ["isin", "ticker", "cnpj"]:
            _golden_df[col] = _golden_df[col].astype(str).str.strip().str.upper()
    return _golden_df


def lookup_golden_record(isin: str = "", ticker: str = "", cnpj: str = "") -> dict:
    """Busca o registro canônico do emissor na base golden_records.csv por ISIN, ticker ou CNPJ."""
    df = _load_golden()
    isin, ticker, cnpj = isin.strip().upper(), ticker.strip().upper(), cnpj.strip().upper()

    match = pd.DataFrame()
    if isin:
        match = df[df["isin"] == isin]
    if match.empty and ticker:
        match = df[df["ticker"] == ticker]
    if match.empty and cnpj:
        match = df[df["cnpj"] == cnpj]

    if match.empty:
        return {"encontrado": False, "motivo": "Nenhum registro correspondente em golden_records.csv"}

    row = match.iloc[0].to_dict()
    return {"encontrado": True, "registro": row}


def _parse_data(s: str) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


def check_date_coherence(
    data_aprovacao: str = "",
    data_com: str = "",
    data_ex: str = "",
    data_pagamento: str = "",
) -> dict:
    """Verifica a ordem cronológica esperada: aprovacao <= data_com < data_ex <= pagamento.
    Datas vazias ou valores como 'a definir' são tratados como ausentes, não como erro."""
    datas = {
        "data_aprovacao": _parse_data(data_aprovacao),
        "data_com": _parse_data(data_com),
        "data_ex": _parse_data(data_ex),
        "data_pagamento": _parse_data(data_pagamento),
    }
    problemas = []

    if datas["data_com"] and datas["data_ex"] and datas["data_com"] >= datas["data_ex"]:
        problemas.append("data_com deveria ser anterior a data_ex")
    if datas["data_aprovacao"] and datas["data_com"] and datas["data_aprovacao"] > datas["data_com"]:
        problemas.append("data_aprovacao posterior a data_com")
    if datas["data_ex"] and datas["data_pagamento"] and datas["data_ex"] > datas["data_pagamento"]:
        problemas.append("data_ex posterior a data_pagamento")

    return {
        "coerente": len(problemas) == 0,
        "problemas": problemas,
        "datas_ausentes": [k for k, v in datas.items() if v is None],
    }


def check_value_coherence(
    valor_bruto: str = "",
    valor_liquido: str = "",
    aliquota_irrf_pct: str = "",
    tolerancia: float = 0.0005,
) -> dict:
    """Verifica se valor_liquido ≈ valor_bruto * (1 - aliquota/100), dentro de uma tolerância."""
    try:
        bruto = float(valor_bruto.replace(",", "."))
        liquido = float(valor_liquido.replace(",", "."))
        aliquota = float(aliquota_irrf_pct.replace(",", ".").replace("%", "")) / 100
    except (ValueError, AttributeError):
        return {"aplicavel": False, "motivo": "valores insuficientes ou não numéricos para checagem"}

    esperado = round(bruto * (1 - aliquota), 10)
    diferenca = abs(esperado - liquido)
    return {
        "aplicavel": True,
        "coerente": diferenca <= tolerancia,
        "valor_liquido_esperado": esperado,
        "valor_liquido_informado": liquido,
        "diferenca": diferenca,
    }


# ---- Definições de tools no formato esperado pela API da Anthropic ----

TOOLS_SPEC = [
    {
        "name": "lookup_golden_record",
        "description": "Busca o registro canônico (emissor, CNPJ, ISIN, ticker, classe) na base de referência golden_records.csv.",
        "input_schema": {
            "type": "object",
            "properties": {
                "isin": {"type": "string"},
                "ticker": {"type": "string"},
                "cnpj": {"type": "string"},
            },
        },
    },
    {
        "name": "check_date_coherence",
        "description": "Valida a ordem cronológica das datas do evento corporativo (formato DD/MM/AAAA). Use string vazia para datas ausentes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "data_aprovacao": {"type": "string"},
                "data_com": {"type": "string"},
                "data_ex": {"type": "string"},
                "data_pagamento": {"type": "string"},
            },
        },
    },
    {
        "name": "check_value_coherence",
        "description": "Valida se o valor líquido por ação é consistente com o valor bruto e a alíquota de IRRF informados.",
        "input_schema": {
            "type": "object",
            "properties": {
                "valor_bruto": {"type": "string"},
                "valor_liquido": {"type": "string"},
                "aliquota_irrf_pct": {"type": "string"},
            },
        },
    },
]

TOOL_IMPL = {
    "lookup_golden_record": lookup_golden_record,
    "check_date_coherence": check_date_coherence,
    "check_value_coherence": check_value_coherence,
}
