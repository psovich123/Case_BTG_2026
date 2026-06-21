import os
from typing import Any, List

from .base import LLMProvider, ProviderResponse, ToolCall


class AnthropicProvider(LLMProvider):
    def __init__(self, model: str = "claude-sonnet-4-6"):
        super().__init__(model)
        from anthropic import Anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY não definida. Exporte sua chave: export ANTHROPIC_API_KEY=sk-ant-..."
            )
        self.client = Anthropic(api_key=api_key)

    def build_tools(self, tools_spec: List[dict]) -> Any:
        # Anthropic já usa o mesmo formato neutro (name/description/input_schema) - passa direto.
        return tools_spec

    def create_initial_messages(self, user_content: str) -> list:
        return [{"role": "user", "content": user_content}]

    def send(self, system: str, messages: list, tools: Any) -> ProviderResponse:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=4000,
            system=system,
            tools=tools,
            messages=messages,
        )
        tool_calls = [
            ToolCall(id=b.id, name=b.name, input=b.input)
            for b in resp.content if b.type == "tool_use"
        ]
        texto = "".join(b.text for b in resp.content if b.type == "text") or None
        return ProviderResponse(tool_calls=tool_calls, text=texto, raw=resp.content)

    def append_assistant_turn(self, messages: list, response: ProviderResponse) -> None:
        messages.append({"role": "assistant", "content": response.raw})

    def append_tool_results(self, messages: list, tool_calls: List[ToolCall], results: List[dict]) -> None:
        import json

        blocos = [
            {"type": "tool_result", "tool_use_id": tc.id, "content": json.dumps(r, ensure_ascii=False)}
            for tc, r in zip(tool_calls, results)
        ]
        messages.append({"role": "user", "content": blocos})

    def append_user_text(self, messages: list, text: str) -> None:
        messages.append({"role": "user", "content": text})
