"""Tests for the Yale Access Bluetooth Activity integration."""

from datetime import timedelta
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

from custom_components.yalexs_ble_activity.const import DOMAIN, OWNER_DOMAIN
from homeassistant.components.event import ATTR_EVENT_TYPES
from homeassistant.const import ATTR_FRIENDLY_NAME, CONF_ADDRESS
from homeassistant.core import HomeAssistant
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
# A LockOperation (0x00) from a captured one, with the op_code at byte 5 and the
# lock state at byte 6:
MANUAL_UNLOCKED = with_checksum("bb2d000000010300a7eedd6a1914190f0200")
AUTO_RELOCK_SECUREMODE = with_checksum("bb2d000000050c007baddd6a2017193f0200")
# A DoorStateChanged (0x20) from a captured one, with the door state at byte 9:
DOOR_AJAR = with_checksum("bb2d00002054addd6a020000000000000200")
DOOR_UNKNOWN = with_checksum("bb2d00002054addd6a000000000000000200")


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


async def async_deliver(
    owner: MockConfigEntry, raw: bytes, *, backlog: bool = False
) -> None:
    """Hand a GetLog reply to the registered reader, as the library's drain does."""
    reader = owner.runtime_data.lock.register_log_record_callback.call_args.args[0]
    await reader(raw, backlog)


async def async_advance(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float
) -> None:
    """Move the clock on and run the timers that fall due."""
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed_exact(hass)
    await hass.async_block_till_done()


def event_attributes(hass: HomeAssistant) -> dict[str, Any]:
    """Return the activity entity's event type and event attributes."""
    attributes = dict(hass.states.get(ENTITY_ID).attributes)
    del attributes[ATTR_EVENT_TYPES], attributes[ATTR_FRIENDLY_NAME]
    return attributes
