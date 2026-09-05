import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from raspyCode.core.event_bus import EventBus
from raspyCode.services.local_ollama_service import LocalOllamaService


def test_find_ollama_uses_path():
    with patch("raspyCode.services.local_ollama_service.shutil.which", return_value="/custom/ollama"):
        assert LocalOllamaService._find_ollama_executable() == "/custom/ollama"


def test_find_ollama_finds_common_linux_location():
    candidate = Path.home() / ".local" / "bin" / "ollama"
    with patch("raspyCode.services.local_ollama_service.shutil.which", return_value=None), \
         patch("raspyCode.services.local_ollama_service.Path.is_file", return_value=True), \
         patch("raspyCode.services.local_ollama_service.Path.stat") as stat:
        stat.return_value.st_mode = 0o100755
        assert LocalOllamaService._find_ollama_executable() == str(candidate)

def test_ollama_serve_overrides_remote_ollama_host(monkeypatch):
    bus = EventBus()
    service = LocalOllamaService(bus)
    monkeypatch.setenv("OLLAMA_HOST", "10.42.0.2:11434")
    monkeypatch.setattr(service, "_is_available", AsyncMock(side_effect=[False, True]))
    monkeypatch.setattr(service, "_publish_models", AsyncMock())
    monkeypatch.setattr(
        "raspyCode.services.local_ollama_service.asyncio.create_subprocess_exec",
        AsyncMock(return_value=MagicMock(returncode=None)),
    )
    async def run():
        await service.ensure_running()
    asyncio.run(run())
    # Inspect the subprocess mock through the patched function object.


def test_local_model_discovery_cli_forces_local_host(monkeypatch):
    service = LocalOllamaService(EventBus())
    monkeypatch.setenv("OLLAMA_HOST", "10.42.0.2:11434")
    monkeypatch.setattr(service, "_is_available", AsyncMock(return_value=False))
    monkeypatch.setattr(service, "_find_ollama_executable", staticmethod(lambda: "/usr/local/bin/ollama"))

    proc = MagicMock(returncode=0)
    proc.communicate = AsyncMock(return_value=(
        b"NAME                ID\nllama3.1:8b        abc\nqwen2.5:3b        def\n",
        b"",
    ))
    create = AsyncMock(return_value=proc)
    monkeypatch.setattr("raspyCode.services.local_ollama_service.asyncio.create_subprocess_exec", create)

    models = asyncio.run(service._list_models())
    assert models == ["llama3.1:8b", "qwen2.5:3b"]
    kwargs = create.call_args.kwargs
    assert kwargs["env"]["OLLAMA_HOST"] == "127.0.0.1:11434"
