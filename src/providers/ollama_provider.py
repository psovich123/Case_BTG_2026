"""
Provider para Ollama (modelos locais).

O Ollama expõe um endpoint compatível com a API de Chat Completions da
OpenAI (http://localhost:11434/v1), então este adapter REAPROVEITA todo o
wire format de OpenAIProvider (build_tools, parsing de tool_calls, etc.) -
só troca o client para apontar para o servidor local e não exigir
OPENAI_API_KEY.

Importante: tool/function calling com Ollama só funciona bem se o modelo
local tiver suporte real a isso. Modelos testados com bom suporte:
llama3.1, qwen2.5, mistral-nemo, firefunction-v2. Modelos menores ou sem
fine-tuning para tools tendem a ignorar as tools ou alucinar argumentos -
isso afeta diretamente a confiança dos campos extraídos, então vale
validar manualmente os primeiros documentos ao trocar de modelo local.

Pré-requisitos na máquina do usuário:
    ollama pull llama3.1     # ou outro modelo com suporte a tools
    ollama serve              # geralmente já roda como serviço em background
"""
import os
from .base import LLMProvider
from .openai_provider import OpenAIProvider


class OllamaProvider(OpenAIProvider):
    def __init__(self, model: str = "llama3.1"):
        # Não chama OpenAIProvider.__init__ (exigiria OPENAI_API_KEY) - monta o client
        # manualmente apontando para o servidor local.
        LLMProvider.__init__(self, model)
        from openai import OpenAI

        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        # Default de 20 minutos por requisição: inferência local (especialmente sem GPU,
        # ou com contexto grande/system prompt + tools pesados) pode ser bem mais lenta
        # que uma API em nuvem. O default do client da OpenAI é de só 10 minutos, o que
        # já se mostrou insuficiente em testes locais. Ajustável via OLLAMA_TIMEOUT_SECONDS.
        timeout = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "6000"))
        # Ollama não valida a api_key, mas o client da OpenAI exige que o campo não seja vazio.
        self.client = OpenAI(base_url=base_url, api_key="ollama", timeout=timeout)