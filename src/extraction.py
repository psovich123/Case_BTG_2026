"""
Agente de extração.

Loop agentic: o modelo recebe o texto do aviso, extrai os campos, decide
quando chamar as tools de validação (golden_records e coerência) e só
termina quando chama `submit_registro` com o payload final já considerando
o resultado dessas validações.

Este módulo é agnóstico de provider: fala apenas com a interface
LLMProvider (src/providers/base.py). Trocar Anthropic <-> OpenAI é uma
variável de ambiente (LLM_PROVIDER), não uma mudança de código aqui.

Por que não pedir direto um JSON num único turno?
Porque o requisito 3 do case pede validação "usando tool/function calling" -
ou seja, o próprio modelo precisa consultar as tools como parte do
raciocínio, e não apenas o pipeline aplicar checagens depois, por fora, sem
o modelo ver o resultado.
"""
from . import tools
from .providers.factory import get_provider

MAX_TURNS = 6

SUBMIT_TOOL = {
    "name": "submit_registro",
    "description": "Envia o registro final estruturado do evento corporativo, já considerando os resultados das validações.",
    "input_schema": {
        "type": "object",
        "properties": {
            "campos": {
                "type": "object",
                "description": "Um objeto por campo do schema, cada um com {valor, confianca, fonte, justificativa}",
                "properties": {
                    nome: {
                        "type": "object",
                        "properties": {
                            "valor": {"type": ["string", "null"]},
                            "confianca": {"type": "string", "enum": ["alta", "media", "baixa"]},
                            "fonte": {"type": ["string", "null"]},
                            "justificativa": {"type": ["string", "null"]},
                        },
                        "required": ["valor", "confianca"],
                    }
                    for nome in [
                        "emissor", "cnpj", "isin", "ticker", "classe", "tipo_evento",
                        "data_aprovacao", "data_com", "data_ex", "data_pagamento",
                        "valor_bruto_por_acao", "valor_liquido_por_acao", "aliquota_irrf",
                        "proporcao", "custo_atribuido_fiscal", "moeda",
                    ]
                },
            },
            "resumo_validacoes": {
                "type": "array",
                "description": "Lista das validações feitas via tools e seus resultados",
                "items": {
                    "type": "object",
                    "properties": {
                        "regra": {"type": "string"},
                        "status": {"type": "string", "enum": ["ok", "falha", "nao_aplicavel"]},
                        "detalhe": {"type": "string"},
                    },
                    "required": ["regra", "status", "detalhe"],
                },
            },
        },
        "required": ["campos", "resumo_validacoes"],
    },
}

SYSTEM_PROMPT = """Você é um agente especialista em eventos corporativos de companhias abertas \
brasileiras (padrão B3/CVM), trabalhando para a área de Asset Servicing de uma instituição financeira.

Sua tarefa: ler o texto de um aviso aos acionistas e extrair um registro estruturado, \
classificando corretamente o tipo de evento e usando as tools disponíveis para validar \
os dados ANTES de finalizar.

## Tipos de evento e como distingui-los
- DIVIDENDO: distribuição de lucros aos acionistas. Pode haver retenção de IR apenas sobre \
parcela que exceda algum limite legal específico (caso raro), mas em geral não tem retenção \
padrão de 17,5%.
- JCP (Juros sobre o Capital Próprio): SEMPRE tem retenção de IRRF (tipicamente 17,5%) sobre \
o valor bruto, calculado com base no patrimônio líquido, e costuma citar o art. 9º da Lei \
9.249/95 ou "imputação ao dividendo obrigatório". Atenção: alguns avisos descrevem esse \
tratamento tributário e essa lógica de cálculo SEM jamais usar literalmente a sigla "JCP" - \
nesse caso, classifique pela SUBSTÂNCIA do tratamento descrito, não apenas pelo título do \
documento, e reduza a confiança do campo tipo_evento se o título do documento e a substância \
do texto sugerirem coisas diferentes, explicando o conflito na justificativa.
- BONIFICAÇÃO: emissão de novas ações aos acionistas existentes, numa proporção (ex: 1 nova \
para cada 20), geralmente com um "custo atribuído" fiscal por ação bonificada.
- GRUPAMENTO: redução do número de ações em circulação numa proporção (ex: 10 para 1), sem \
provento em dinheiro.
- DESDOBRAMENTO: aumento do número de ações em circulação numa proporção (ex: 1 para 2), sem \
provento em dinheiro.

## Regras de extração
1. Para cada campo, cite o trecho EXATO do texto que originou o valor (campo "fonte"). Se o \
campo não existir no documento, valor=null e diga isso na justificativa - NUNCA invente ou \
infira um valor que não esteja no texto.
2. Um campo ausente porque o documento diz explicitamente algo como "a definir" ou "a ser \
divulgado posteriormente" NÃO é um erro de extração: valor=null, confiança média/alta, e \
justificativa citando essa frase. Isso é diferente de um campo ausente porque o texto está \
incompleto ou ilegível (que deve ter confiança baixa).
3. Para eventos sem valor monetário (grupamento/desdobramento), os campos valor_bruto_por_acao, \
valor_liquido_por_acao e aliquota_irrf devem ser valor=null, e o campo "proporcao" deve ser \
preenchido (ex: "10:1").
4. Para bonificação, preencha "proporcao" (ex: "1:20") e "custo_atribuido_fiscal".
5. Use a tool lookup_golden_record assim que tiver emissor/ISIN/ticker extraídos, para \
confirmar CNPJ, ISIN, ticker e classe (ON/PN) contra a base de referência.
6. Use check_date_coherence com as datas extraídas (mesmo as ausentes, como string vazia).
7. Se houver valor bruto, líquido e alíquota, use check_value_coherence.
8. Só chame submit_registro depois de ter chamado as tools de validação relevantes. Inclua em \
"resumo_validacoes" os resultados de TODAS as tools chamadas - isso compõe o relatório de \
auditoria.
9. Se o texto recebido estiver vazio ou ilegível (ex: falha de OCR), ainda assim chame \
submit_registro, mas com todos os campos valor=null, confianca="baixa" e uma justificativa \
clara de que o conteúdo não pôde ser lido.
"""


def extrair_registro(nome_documento: str, texto: str, metodo_extracao: str) -> dict:
    """Roda o loop agentic de extração+validação para um documento e retorna o payload final.
    O provider (Anthropic/OpenAI/...) é resolvido via LLM_PROVIDER no ambiente."""
    provider = get_provider()

    user_msg = (
        f"Documento: {nome_documento}\n"
        f"Método de extração de texto: {metodo_extracao}\n\n"
        f"--- TEXTO DO AVISO ---\n{texto if texto.strip() else '(texto vazio - extração indisponível)'}"
    )

    messages = provider.create_initial_messages(user_msg)
    all_tools = provider.build_tools(tools.TOOLS_SPEC + [SUBMIT_TOOL])

    for _ in range(MAX_TURNS):
        response = provider.send(system=SYSTEM_PROMPT, messages=messages, tools=all_tools)

        if not response.tool_calls:
            provider.append_assistant_turn(messages, response)
            provider.append_user_text(
                messages, "Por favor finalize chamando a tool submit_registro com o payload completo."
            )
            continue

        submit = next((t for t in response.tool_calls if t.name == "submit_registro"), None)
        if submit:
            return submit.input

        provider.append_assistant_turn(messages, response)
        resultados = []
        for tc in response.tool_calls:
            fn = tools.TOOL_IMPL.get(tc.name)
            try:
                resultado = fn(**tc.input) if fn else {"erro": f"tool desconhecida: {tc.name}"}
            except Exception as e:
                resultado = {"erro": str(e)}
            resultados.append(resultado)
        provider.append_tool_results(messages, response.tool_calls, resultados)

    raise RuntimeError(f"Agente não finalizou em {MAX_TURNS} turnos para {nome_documento}")
