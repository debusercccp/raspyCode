from .bio import build_bio_tools
from .registry import DEFAULT_TOOL_TIMEOUT_SECONDS, ToolDefinition, ToolRegistry
from .system import SYSTEM_CMD_TIMEOUT_SECONDS, build_system_run_cmd_tool


def build_default_registry() -> ToolRegistry:
    """Assembla il ToolRegistry di default con tutti i tool biotoolkit_*
    piu' system_run_cmd. Questa e' l'unica fonte di verita' condivisa da
    LLMGatewayService (schema Ollama) e ToolExecutorService (esecuzione)."""
    registry = ToolRegistry()
    for tool in build_bio_tools():
        registry.register(tool)
    registry.register(build_system_run_cmd_tool())
    return registry


__all__ = [
    "DEFAULT_TOOL_TIMEOUT_SECONDS",
    "SYSTEM_CMD_TIMEOUT_SECONDS",
    "ToolDefinition",
    "ToolRegistry",
    "build_default_registry",
]
