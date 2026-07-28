import pytest
import httpx
from unittest.mock import patch, MagicMock
from raspyCode.services.connectivity_service import ConnectivityService
from raspyCode.core.event_bus import EventBus

@pytest.fixture
def connectivity_service():
    bus = EventBus()
    return ConnectivityService(bus, pi_ip="10.42.0.2")

@pytest.mark.asyncio
@patch("raspyCode.services.connectivity_service.httpx.AsyncClient.get")
async def test_connectivity_check_success(mock_get, connectivity_service):
    # Mock della risposta HTTP di Ollama
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"models": [{"name": "qwen3:4b"}, {"name": "gemma:e4b"}]}
    mock_get.return_value = mock_resp

    # _check_once richiede il client come argomento posizionale
    async with httpx.AsyncClient() as client:
        await connectivity_service._check_once(client)
