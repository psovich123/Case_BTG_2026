"""
Abstração de provider de LLM.

O agente (src/extraction.py) fala APENAS com esta interface. Trocar de
provider (Anthropic, OpenAI, ou outro) significa escrever um novo
adapter aqui dentro - nada no resto do pipeline muda, porque schema,
tools de validação, confiança e orquestração são agnósticos a quem
gerou o texto.

Cada provider precisa resolver 3 diferenças de "wire format" entre
APIs de tool calling:
  1. Como declarar as tools (Anthropic usa input_schema; OpenAI usa
     function.parameters).
  2. Como o modelo retorna uma chamada de tool (Anthropic: blocos
     tool_use no content; OpenAI: tool_calls na mensagem).
  3. Como devolver o resultado de uma tool (Anthropic: bloco
     tool_result no papel "user"; OpenAI: mensagem com role "tool").

Os métodos abaixo encapsulam exatamente essas 3 diferenças.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class ProviderResponse:
    tool_calls: List[ToolCall] = field(default_factory=list)
    text: Optional[str] = None
    raw: Any = None  # mensagem/bloco bruto do provider, necessário para reconstruir o histórico


class LLMProvider(ABC):
    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    def build_tools(self, tools_spec: List[dict]) -> Any:
        """Converte a especificação neutra de tools (name/description/input_schema) para o
        formato esperado pela API deste provider."""

    @abstractmethod
    def create_initial_messages(self, user_content: str) -> list:
        """Cria a lista inicial de mensagens (sem o system prompt, que é passado separadamente
        em cada chamada a `send`)."""

    @abstractmethod
    def send(self, system: str, messages: list, tools: Any) -> ProviderResponse:
        """Faz uma chamada ao modelo e devolve uma resposta normalizada."""

    @abstractmethod
    def append_assistant_turn(self, messages: list, response: ProviderResponse) -> None:
        """Adiciona ao histórico a resposta do assistente (texto e/ou chamadas de tool)."""

    @abstractmethod
    def append_tool_results(self, messages: list, tool_calls: List[ToolCall], results: List[dict]) -> None:
        """Adiciona ao histórico os resultados das tools executadas, na ordem de tool_calls."""

    @abstractmethod
    def append_user_text(self, messages: list, text: str) -> None:
        """Adiciona uma mensagem de usuário simples (ex.: para forçar o modelo a finalizar)."""
