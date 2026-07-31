import asyncio

import pytest

from raspyCode.core.event_bus import EventBus
from raspyCode.core.events import Event, StatusEvent


@pytest.mark.asyncio
async def test_event_bus_subscription_and_publishing():
    bus = EventBus()

    # Simula due microservizi che si iscrivono al bus
    queue_1 = bus.subscribe()
    queue_2 = bus.subscribe()

    # Pubblica un evento
    test_event = StatusEvent(text="Test", level="info")
    await bus.publish(test_event)

    # Entrambi i subscriber dovrebbero ricevere esattamente la stessa istanza
    received_1 = await asyncio.wait_for(queue_1.get(), timeout=1.0)
    received_2 = await asyncio.wait_for(queue_2.get(), timeout=1.0)

    assert isinstance(received_1, StatusEvent)
    assert received_1.text == "Test"
    assert received_1 is test_event
    assert received_2 is test_event


@pytest.mark.asyncio
async def test_event_bus_multiple_events():
    bus = EventBus()
    queue = bus.subscribe()

    await bus.publish(Event())
    await bus.publish(StatusEvent(text="Msg 1"))
    await bus.publish(StatusEvent(text="Msg 2"))

    assert queue.qsize() == 3
