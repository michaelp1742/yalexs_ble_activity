"""Tests of the log record events as core's logbook returns them from the recorder."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from . import CODE_OPERATION_SLOT_1, ENTITY_ID, TITLE, async_deliver


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    recorder_db_url: str, auto_enable_custom_integrations: None
) -> None:
    """Prepare the test database before the conftest's fixture creates hass."""


async def _async_logbook_entries(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator, entity_ids: list[str]
) -> list[dict]:
    """Return the entries logbook/get_events gives for entity_ids."""
    await async_wait_recording_done(hass)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": "logbook/get_events",
            "start_time": "2000-01-01T00:00:00+00:00",
            "entity_ids": entity_ids,
        }
    )
    msg = await client.receive_json()
    assert msg["success"]
    return msg["result"]


@pytest.mark.usefixtures("recorder_mock")
async def test_the_logbook_of_cores_lock_entity_returns_the_record_at_its_time(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    owner_entry: MockConfigEntry,
    core_lock: er.RegistryEntry,
    loaded_entry: MockConfigEntry,
    log_records: list[Event],
) -> None:
    """The logbook asked for core's lock entity returns a fired record at its line's time, and the logbook asked for the event entity does not."""
    # The test environment has no frontend package, which the logbook needs only
    # to register its panel.
    hass.config.components.add("frontend")
    assert await async_setup_component(hass, "logbook", {})
    await hass.async_block_till_done()

    await async_deliver(owner_entry, CODE_OPERATION_SLOT_1)

    (event,) = log_records
    assert await _async_logbook_entries(
        hass, hass_ws_client, [core_lock.entity_id]
    ) == [
        {
            "name": TITLE,
            "message": "unlocked (keypad code at slot 1)",
            "domain": "yalexs_ble",
            "when": event.time_fired_timestamp,
        }
    ]
    assert await _async_logbook_entries(hass, hass_ws_client, [ENTITY_ID]) == []
