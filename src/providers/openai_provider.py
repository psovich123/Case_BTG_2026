import json
import os
from typing import Any, List

from .base import LLMProvider, ProviderResponse, ToolCall


class OpenAIProvider(LLMProvider):
    def __init__(self, model: str = "gpt-4.1"):
        super().__init__(model)
        from openai import OpenAI

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY não definida. Exporte sua chave: export OPENAI_API_KEY=sk-..."
            )
        self.client = OpenAI(api_key=api_key)

    def build_tools(self, tools_spec: List[dict]) -> Any:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in tools_spec
        ]

    def create_initial_messages(self, user_content: str) -> list:
        return [{"role": "user", "content": user_content}]

    def send(self, system: str, messages: list, tools: Any) -> ProviderResponse:
        api_messages = [{"role": "system", "content": system}] + messages
        resp = self.client.chat.completions.create(
            model=self.model,
            max_tokens=4000,
            messages=api_messages,
            tools=tools,
            tool_choice="auto",
        )
        msg = resp.choices[0].message

        tool_calls = []
        for tc in (msg.tool_calls or []):
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, input=args))

        return ProviderResponse(tool_calls=tool_calls, text=msg.content, raw=msg)

    def append_assistant_turn(self, messages: list, response: ProviderResponse) -> None:
        messages.append(response.raw.model_dump(exclude_none=True))

    def append_tool_results(self, messages: list, tool_calls: List[ToolCall], results: List[dict]) -> None:
        for tc, r in zip(tool_calls, results):
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(r, ensure_ascii=False),
            })

    def append_user_text(self, messages: list, text: str) -> None:
        messages.append({"role": "user", "content": text})
