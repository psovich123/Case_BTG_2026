"""
Escolha do provider via variável de ambiente:

    LLM_PROVIDER=anthropic   (default)
    LLM_PROVIDER=openai
    LLM_PROVIDER=ollama       (modelos locais, sem custo de API)

    LLM_MODEL=<nome do modelo>   (opcional, sobrescreve o default de cada provider)
    OLLAMA_BASE_URL=<url>         (opcional, default http://localhost:11434/v1)

Adicionar um novo provider (ex.: Google Gemini): criar
src/providers/<nome>_provider.py implementando LLMProvider (src/providers/base.py)
e registrar aqui em _PROVIDERS. Nada em src/extraction.py precisa mudar.
"""
import os
from .base import LLMProvider

# Segurança extra: carrega o .env aqui também (idempotente - não tem problema se
# run.py já tiver chamado). Isso cobre o caso de get_provider() ser chamado num
# contexto onde o load_dotenv() do run.py não rodou primeiro, ou foi rodado a
# partir de outro diretório de trabalho.
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass

_PROVIDERS = {
    "anthropic": ("src.providers.anthropic_provider", "AnthropicProvider", "claude-sonnet-4-6"),
    "openai": ("src.providers.openai_provider", "OpenAIProvider", "gpt-4.1"),
    "ollama": ("src.providers.ollama_provider", "OllamaProvider", "llama3.1"),
}


def _ler_env(nome: str, default: str = "") -> str:
    """Lê uma variável de ambiente removendo espaços e aspas que às vezes sobram ao
    editar o .env manualmente (ex.: LLM_PROVIDER="ollama" com aspas literais)."""
    valor = os.environ.get(nome, default)
    return valor.strip().strip('"').strip("'")


def get_provider() -> LLMProvider:
    nome = _ler_env("LLM_PROVIDER", "anthropic").lower()
    if nome not in _PROVIDERS:
        raise ValueError(
            f"LLM_PROVIDER='{nome}' desconhecido. Opções disponíveis: {list(_PROVIDERS)}"
        )

    modulo_path, classe_nome, modelo_default = _PROVIDERS[nome]
    import importlib

    modulo = importlib.import_module(modulo_path)
    classe = getattr(modulo, classe_nome)
    modelo = _ler_env("LLM_MODEL", modelo_default)

    # Print de diagnóstico: deixa explícito no terminal qual provider/modelo foi
    # escolhido, pra não depender de adivinhar se o .env foi lido corretamente.
    extra = f" | OLLAMA_BASE_URL={_ler_env('OLLAMA_BASE_URL', '(default)')}" if nome == "ollama" else ""
    print(f"[LLM] provider='{nome}' modelo='{modelo}'{extra}")

    return classe(model=modelo)