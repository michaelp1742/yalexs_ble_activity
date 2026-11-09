"""Tests for the Yale Access Bluetooth Activity integration."""

from datetime import timedelta
import time
from typing import Any
from unittest.mock import Mock

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockModule,
    async_fire_time_changed_exact,
    mock_integration,
    mock_platform,
)
from yalexs_ble import ExchangeTimes, LogRead, StatusReply

from custom_components.yalexs_ble_activity.const import DOMAIN, OWNER_DOMAIN
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

ADDRESS = "AA:BB:CC:DD:EE:FF"
TITLE = "Back Door"
FRONT_ADDRESS = "11:22:33:44:55:66"
FRONT_TITLE = "Front Door"

ENTITY_ID = "event.back_door_activity"


def with_checksum(frame: str) -> bytes:
    """Return the GetLog reply in frame with byte 3 set so the 18 bytes sum to 0 modulo 256."""
    raw = bytearray.fromhex(frame)
    raw[3] = 0
    raw[3] = -sum(raw) % 256
    return bytes(raw)


# GetLog replies captured from Yale locks.
CODE_OPERATION_SLOT_1 = bytes.fromhex("bb2d001d07fc2fe06a1300470b1701000200")
CODE_OPERATION_SLOT_FFEE = bytes.fromhex("bb2d00d007299c76a3330049e414eeff0200")
KEYPAD_INFO = bytes.fromhex("bb2d00c404922fe06ac30000008000000200")
RF_SLOT_7_UNLOCKED = bytes.fromhex("bb2d00300e51addd6a01070013421f170200")
KEYPAD_BUTTON_LOCKED = bytes.fromhex("bb2d001c000005ff0433e06a0817193d0200")
ONE_TOUCH_LOCKED = bytes.fromhex("bb2d0056000b0500a0a176a3df14194a0200")
REMOTE_UNLOCKED = bytes.fromhex("bb2d00080000030093aedd6a1f1719340200")
INSIDE_BUTTON_LOCKED = bytes.fromhex("bb2d00d4000c0500a7eedd6a1914190f0200")
AUTO_RELOCK_LOCKED = bytes.fromhex("bb2d000e000505007baddd6a2017193f0200")
DOOR_OPENED = bytes.fromhex("bb2d00ab2054addd6a030000000000000200")
DOOR_CLOSED = bytes.fromhex("bb2d00a4205daddd6a010000000000000200")
END_OF_LOG = bytes.fromhex("bb2d00de800200009aa176a3a8a176a30200")
# A GetLogError with the dirty bit set, answering a GetLog that raced a record's write.
END_OF_LOG_DIRTY = bytes.fromhex("bb2d00f0800a0000c542dd6ac542dd6a0200")

# Constructed GetLog replies. A CredentialOperation (0x0E) from a captured one,
# with the credential type at byte 9, the slot at bytes 10 and 11, and the lock
# and door states or a credential error at byte 12:
PIN_SLOT_3_UNLOCKED = with_checksum("bb2d00000ef3f7e36a0003001337f2160200")
INSIDE_DOOR_PIN_SLOT_3_UNLOCKED = with_checksum("bb2d00000ef3f7e36a0503001337f2160200")
FINGER_SLOT_2_UNLOCKED = with_checksum("bb2d00000ef3f7e36a0202001337f2160200")
FACE_SLOT_2_UNLOCKED = with_checksum("bb2d00000ef3f7e36a0402001337f2160200")
PALM_SLOT_2_UNLOCKED = with_checksum("bb2d00000ef3f7e36a0602001337f2160200")
ALIRO_SLOT_2_UNLOCKED = with_checksum("bb2d00000ef3f7e36a0802001337f2160200")
CREDENTIAL_TYPE_3_SLOT_2_UNLOCKED = with_checksum(
    "bb2d00000ef3f7e36a0302001337f2160200"
)
RF_SLOT_8_ERROR = with_checksum("bb2d00000ef3f7e36a010800f337f2160200")
# PIN_SLOT_3_UNLOCKED with the credential type RF and slot 7, in the same second.
RF_SLOT_7_AT_PIN_SLOT_3 = with_checksum("bb2d00000ef3f7e36a0107001337f2160200")
# A constructed KeypadInfo (0x04) from KEYPAD_INFO, with the own time of CODE_OPERATION_SLOT_1.
KEYPAD_INFO_AT_CODE_OPERATION_SLOT_1 = with_checksum(
    "bb2d000004fc2fe06ac30000008000000200"
)
# A LockOperation (0x00) from a captured one, with the op_code at byte 5 and the
# lock state at byte 6:
MANUAL_UNLOCKED = with_checksum("bb2d000000010300a7eedd6a1914190f0200")
AUTO_RELOCK_SECUREMODE = with_checksum("bb2d000000050c007baddd6a2017193f0200")
# A DoorStateChanged (0x20) from a captured one, with the door state at byte 9:
DOOR_AJAR = with_checksum("bb2d00002054addd6a020000000000000200")
DOOR_UNKNOWN = with_checksum("bb2d00002054addd6a000000000000000200")


def door_opened_at(time_stamp: int) -> bytes:
    """Return a constructed DoorStateChanged reply, door opened, with time_stamp at bytes 5 to 8."""
    return with_checksum(
        f"bb2d000020{time_stamp.to_bytes(4, 'little').hex()}030000000000000200"
    )


def lock_operation(op_code: int) -> bytes:
    """Return a constructed LockOperation reply of op_code, from INSIDE_BUTTON_LOCKED."""
    return with_checksum(f"bb2d000000{op_code:02x}0500a7eedd6a1914190f0200")


# Constructed GetLog replies of the other record classes, each with the time
# stamp 0x12345678 at bytes 5 to 8.
TIME = "1979-09-05T22:51:36+00:00"
KEYPAD_OPEN = with_checksum("bb2d00000178563412123456ffffffff0200")
KEYPAD_WRONG_CODE = with_checksum("bb2d00000278563412123456ffffffff0200")
KEYPAD_CLOSE = with_checksum("bb2d00000878563412123456ffffffff0200")
CODE_ADDED_SLOT_5 = with_checksum("bb2d0000037856341205123456ffffff0200")
CODE_DELETED_SLOT_5 = with_checksum("bb2d00000578563412050000000000000200")
ALL_CODES_DELETED = with_checksum("bb2d00000678563412000000000000000200")
FACTORY_RESET = with_checksum("bb2d00000978563412000000000000000200")
CODE_ADDED_V2_SLOT_4 = with_checksum("bb2d00000a78563412040040e20100000200")
CODE_DELETED_V2_SLOT_260 = with_checksum("bb2d00000b78563412040100000000000200")
CREDENTIAL_ADDED_RF_SLOT_7 = with_checksum("bb2d00000c7856341201070013421f170200")
CREDENTIAL_DELETED_RF_SLOT_7 = with_checksum("bb2d00000d7856341201070013421f170200")
TAMPER_DOOR_FORCED_OPEN = with_checksum("bb2d00000f78563412030000000000000200")
BCM_TEST = with_checksum("bb2d00001078563412013c00102700000200")
HOMEKEY_OPERATION = with_checksum("bb2d0000127856341203003aefbeadde0200")
DPS_INFO = with_checksum("bb2d00001378563412500000000000000200")
BATTERY_INFO = with_checksum("bb2d00001578563412f816fb5a6401000200")
LOCAL_EVENT_NOTIFICATION = with_checksum("bb2d00001678563412070000000000000200")
PRODUCT_MESSAGE = with_checksum("bb2d00001778563412341201020304050200")
MATTER_MESSAGE = with_checksum("bb2d00001878563412341201020304050200")
DIALOG_REBOOT = with_checksum("bb2d00004078563412152307785634120200")
# A log_type, 0x11, that Yale's numbering does not decode.
NO_DECODER = with_checksum("bb2d00001178563412010203040506070200")


async def async_setup_owner(
    hass: HomeAssistant, address: str = ADDRESS, title: str = TITLE
) -> MockConfigEntry:
    """Add and load an entry of core's yalexs_ble for one lock."""
    owner = MockConfigEntry(
        domain=OWNER_DOMAIN,
        title=title,
        data={CONF_ADDRESS: address},
        unique_id=address,
    )
    owner.add_to_hass(hass)
    assert await hass.config_entries.async_setup(owner.entry_id)
    return owner


async def async_setup_platform(
    hass: HomeAssistant, domain: str, **functions: Mock
) -> None:
    """Load a stand-in integration whose yalexs_ble_activity platform has functions."""
    for function in functions.values():
        function.__module__ = f"custom_components.{domain}.{DOMAIN}"
    mock_integration(hass, MockModule(domain))
    mock_platform(
        hass, f"{domain}.{DOMAIN}", Mock(spec_set=list(functions), **functions)
    )
    assert await async_setup_component(hass, domain, {})
    await hass.async_block_till_done()


def times_now(round_trip: float = 0.0) -> ExchangeTimes:
    """Return the times of an exchange whose reply arrives now, round_trip seconds after its request."""
    now = time.time()
    return ExchangeTimes(now - round_trip, now)


def status_reply(value: int, round_trip: float = 0.0) -> StatusReply:
    """Return a status read of value whose reply arrives now."""
    return StatusReply(value, times_now(round_trip))


async def async_deliver(
    owner: MockConfigEntry,
    raw: bytes,
    *,
    backlog: bool = False,
    round_trip: float = 0.0,
) -> None:
    """Hand a GetLog reply arriving now to the registered reader, as the library's drain does."""
    reader = owner.runtime_data.lock.register_log_record_callback.call_args.args[0]
    await reader(LogRead(raw, backlog, times_now(round_trip)))


async def async_advance(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float
) -> None:
    """Move the clock on and run the timers that fall due."""
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed_exact(hass)
    await hass.async_block_till_done()


def last_data(events: list[Event]) -> dict[str, Any]:
    """Return the data of the last log record event among events."""
    return dict(events[-1].data)


def activity_device(hass: HomeAssistant, entry: MockConfigEntry) -> dr.DeviceEntry:
    """Return the integration's device of entry."""
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    return device


def store_key(entry: MockConfigEntry) -> str:
    """Return the key of entry's store."""
    return f"{DOMAIN}.{entry.entry_id}"


def enable_entity(entity_registry: er.EntityRegistry, entry: MockConfigEntry) -> None:
    """Register the activity entity of entry enabled, before its setup."""
    entity_registry.async_get_or_create(
        Platform.EVENT,
        DOMAIN,
        f"{ADDRESS}_activity",
        suggested_object_id=ENTITY_ID.removeprefix(f"{Platform.EVENT}."),
        config_entry=entry,
    )
