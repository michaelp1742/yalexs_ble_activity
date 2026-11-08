"""The event type, the attributes, and the credential name of an activity log record."""

from collections.abc import Callable
from dataclasses import fields
from enum import Enum
import logging
from types import ModuleType
from typing import Any, NamedTuple

from yalexs_ble import (
    AllCodesDeleted,
    BatteryInfo,
    BCMTest,
    CodeAdded,
    CodeAddedv2,
    CodeDeleted,
    CodeDeletedv2,
    CodeOperation,
    CredentialAdded,
    CredentialDeleted,
    CredentialOperation,
    DialogReboot,
    DoorStateChanged,
    DoorStatus,
    DPSInfo,
    FactoryReset,
    HomekeyOperation,
    KeypadClose,
    KeypadInfo,
    KeypadOpen,
    KeypadWrongCode,
    LocalEventNotification,
    LockCred,
    LockOperation,
    LogRecord,
    MatterMessage,
    OpCode,
    ProductMessage,
    Tamper,
)

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.integration_platform import (
    async_process_integration_platforms,
)
from homeassistant.util import dt as dt_util
from homeassistant.util.hass_dict import HassKey

from .const import (
    ATTR_BACKLOG,
    ATTR_RAW,
    ATTR_TIMESTAMP,
    DOMAIN,
    EVENT_TYPE_ALIRO,
    EVENT_TYPE_ALIRO_OPERATION,
    EVENT_TYPE_ALL_CODES_DELETED,
    EVENT_TYPE_AUTO_LOCK,
    EVENT_TYPE_BATTERY_INFO,
    EVENT_TYPE_BCM_TEST,
    EVENT_TYPE_CODE_ADDED,
    EVENT_TYPE_CODE_ADDED_V2,
    EVENT_TYPE_CODE_DELETED,
    EVENT_TYPE_CODE_DELETED_V2,
    EVENT_TYPE_CREDENTIAL,
    EVENT_TYPE_CREDENTIAL_ADDED,
    EVENT_TYPE_CREDENTIAL_DELETED,
    EVENT_TYPE_CREDENTIAL_ERROR,
    EVENT_TYPE_DIALOG_REBOOT,
    EVENT_TYPE_DOOR_AJAR,
    EVENT_TYPE_DOOR_CLOSED,
    EVENT_TYPE_DOOR_OPENED,
    EVENT_TYPE_DOOR_STATE_CHANGED,
    EVENT_TYPE_DPS_INFO,
    EVENT_TYPE_FACE,
    EVENT_TYPE_FACTORY_RESET,
    EVENT_TYPE_FINGER,
    EVENT_TYPE_HOMEKEY_OPERATION,
    EVENT_TYPE_KEYPAD_BUTTON,
    EVENT_TYPE_KEYPAD_CLOSE,
    EVENT_TYPE_KEYPAD_INFO,
    EVENT_TYPE_KEYPAD_OPEN,
    EVENT_TYPE_KEYPAD_WRONG_CODE,
    EVENT_TYPE_LOCAL_EVENT_NOTIFICATION,
    EVENT_TYPE_LOCK_OPERATION,
    EVENT_TYPE_MANUAL,
    EVENT_TYPE_MASTER_CODE,
    EVENT_TYPE_MATTER_MESSAGE,
    EVENT_TYPE_PALM,
    EVENT_TYPE_PIN,
    EVENT_TYPE_PRODUCT_MESSAGE,
    EVENT_TYPE_REMOTE,
    EVENT_TYPE_RF,
    EVENT_TYPE_TAMPER,
    EVENT_TYPE_UNKNOWN_RECORD,
)
from .models import LockModel

_LOGGER = logging.getLogger(__name__)

type CredentialNamer = Callable[[HomeAssistant, str, LockCred, int], str | None]

DATA_NAMERS: HassKey[list[CredentialNamer]] = HassKey(f"{DOMAIN}_namers")

_CREDENTIAL_EVENT_TYPES = {
    LockCred.RF: EVENT_TYPE_RF,
    LockCred.FINGER: EVENT_TYPE_FINGER,
    LockCred.FACE: EVENT_TYPE_FACE,
    LockCred.PALM: EVENT_TYPE_PALM,
    LockCred.ALIRO: EVENT_TYPE_ALIRO,
}

_DOOR_EVENT_TYPES = {
    DoorStatus.OPENED: EVENT_TYPE_DOOR_OPENED,
    DoorStatus.CLOSED: EVENT_TYPE_DOOR_CLOSED,
    DoorStatus.AJAR: EVENT_TYPE_DOOR_AJAR,
}

_RECORD_EVENT_TYPES: dict[type[LogRecord], str] = {
    CodeAdded: EVENT_TYPE_CODE_ADDED,
    CodeDeleted: EVENT_TYPE_CODE_DELETED,
    CodeAddedv2: EVENT_TYPE_CODE_ADDED_V2,
    CodeDeletedv2: EVENT_TYPE_CODE_DELETED_V2,
    CredentialAdded: EVENT_TYPE_CREDENTIAL_ADDED,
    CredentialDeleted: EVENT_TYPE_CREDENTIAL_DELETED,
    KeypadOpen: EVENT_TYPE_KEYPAD_OPEN,
    KeypadWrongCode: EVENT_TYPE_KEYPAD_WRONG_CODE,
    KeypadClose: EVENT_TYPE_KEYPAD_CLOSE,
    KeypadInfo: EVENT_TYPE_KEYPAD_INFO,
    AllCodesDeleted: EVENT_TYPE_ALL_CODES_DELETED,
    FactoryReset: EVENT_TYPE_FACTORY_RESET,
    Tamper: EVENT_TYPE_TAMPER,
    BCMTest: EVENT_TYPE_BCM_TEST,
    HomekeyOperation: EVENT_TYPE_HOMEKEY_OPERATION,
    DPSInfo: EVENT_TYPE_DPS_INFO,
    BatteryInfo: EVENT_TYPE_BATTERY_INFO,
    LocalEventNotification: EVENT_TYPE_LOCAL_EVENT_NOTIFICATION,
    ProductMessage: EVENT_TYPE_PRODUCT_MESSAGE,
    MatterMessage: EVENT_TYPE_MATTER_MESSAGE,
    DialogReboot: EVENT_TYPE_DIALOG_REBOOT,
}


class Activity(NamedTuple):
    """The event type of a record, and the credential slot and type a name is asked for."""

    event_type: str
    slot: int | None
    credential_type: LockCred | None


def _code_activity(slot: int, credential_type: LockCred, model: LockModel) -> Activity:
    """Return master_code at the model row's master code slot, else pin with slot and credential_type."""
    if slot == model.master_code_slot:
        return Activity(EVENT_TYPE_MASTER_CODE, None, None)
    return Activity(EVENT_TYPE_PIN, slot, credential_type)


def activity_for(record: LogRecord, model: LockModel) -> Activity:
    """Return the activity of a record: the source of a use or an operation, else its kind."""
    match record:
        case CodeOperation(slot=slot):
            return _code_activity(slot, LockCred.PIN, model)
        case CredentialOperation(
            credential_type=LockCred() as credential_type,
            credential_error=None,
            slot=slot,
        ):
            if credential_type in (LockCred.PIN, LockCred.INSIDE_DOOR_PIN):
                return _code_activity(slot, credential_type, model)
            return Activity(
                _CREDENTIAL_EVENT_TYPES.get(credential_type, EVENT_TYPE_CREDENTIAL),
                slot,
                credential_type,
            )
        case CredentialOperation(credential_error=None):
            return Activity(EVENT_TYPE_CREDENTIAL, None, None)
        case CredentialOperation():
            return Activity(EVENT_TYPE_CREDENTIAL_ERROR, None, None)
        # In field captures a press of the keypad's Yale button was recorded as
        # DOOR_STATE_CHANGED with key_slot 0xFF, and a command over Bluetooth with
        # key_slot 0.
        case (
            LockOperation(op_code=OpCode.DOOR_STATE_CHANGED, key_slot=0xFF)
            | LockOperation(op_code=OpCode.ONE_TOUCH)
        ):
            return Activity(EVENT_TYPE_KEYPAD_BUTTON, None, None)
        case LockOperation(op_code=OpCode.DOOR_STATE_CHANGED):
            return Activity(EVENT_TYPE_REMOTE, None, None)
        case LockOperation(
            op_code=OpCode.DOOR_MANUAL_STATE_CHANGE | OpCode.INSIDE_BUTTON
        ):
            return Activity(EVENT_TYPE_MANUAL, None, None)
        case LockOperation(op_code=OpCode.AUTO_RELOCK):
            return Activity(EVENT_TYPE_AUTO_LOCK, None, None)
        case LockOperation(op_code=OpCode.ALIRO):
            # The name of OpCode.ALIRO in lower case is EVENT_TYPE_ALIRO, the type of a
            # credential's use, so the operation has a type of its own.
            return Activity(EVENT_TYPE_ALIRO_OPERATION, None, None)
        case LockOperation(op_code=OpCode() as op_code):
            return Activity(op_code.name.lower(), None, None)
        case LockOperation():
            return Activity(EVENT_TYPE_LOCK_OPERATION, None, None)
        case DoorStateChanged(current_door_state=door_state):
            return Activity(
                _DOOR_EVENT_TYPES.get(door_state, EVENT_TYPE_DOOR_STATE_CHANGED),
                None,
                None,
            )
        case (
            CodeAdded(slot=slot)
            | CodeDeleted(slot=slot)
            | CodeAddedv2(slot=slot)
            | CodeDeletedv2(slot=slot)
        ):
            return Activity(_RECORD_EVENT_TYPES[type(record)], slot, LockCred.PIN)
        case (
            CredentialAdded(credential_type=LockCred() as credential_type, slot=slot)
            | CredentialDeleted(
                credential_type=LockCred() as credential_type, slot=slot
            )
        ):
            return Activity(_RECORD_EVENT_TYPES[type(record)], slot, credential_type)
    return Activity(
        _RECORD_EVENT_TYPES.get(type(record), EVENT_TYPE_UNKNOWN_RECORD), None, None
    )


def _attribute_value(value: Any) -> Any:
    """Return a decoded field as an attribute value."""
    match value:
        case Enum():
            return value.name.lower()
        case tuple():
            return list(value)
    return value


def attributes_for(record: LogRecord, backlog: bool) -> dict[str, Any]:
    """Return the event attributes of a record: its lock time, its decoded fields, and backlog."""
    attributes: dict[str, Any] = {ATTR_BACKLOG: backlog}
    for field in fields(record):
        value = getattr(record, field.name)
        if field.name == "time_stamp":
            attributes[ATTR_TIMESTAMP] = dt_util.utc_from_timestamp(value).isoformat()
        elif field.name != "raw":
            attributes[field.name] = _attribute_value(value)
    if type(record) is LogRecord:
        attributes[ATTR_RAW] = record.raw.hex()
    return attributes


@callback
def _async_process_platform(
    hass: HomeAssistant, domain: str, platform: ModuleType
) -> None:
    """Collect the async_credential_name of an integration's yalexs_ble_activity platform."""
    if (namer := getattr(platform, "async_credential_name", None)) is None:
        _LOGGER.warning(
            "The %s platform of %s has no async_credential_name, so %s names no "
            "credential",
            DOMAIN,
            domain,
            domain,
        )
        return
    hass.data[DATA_NAMERS].append(namer)


async def async_collect_namers(hass: HomeAssistant) -> None:
    """Collect the yalexs_ble_activity platforms of the integrations loaded now and later, once per run."""
    if DATA_NAMERS in hass.data:
        return
    hass.data[DATA_NAMERS] = []
    await async_process_integration_platforms(hass, DOMAIN, _async_process_platform)


@callback
def credential_name(
    hass: HomeAssistant, address: str, credential_type: LockCred, slot: int
) -> str | None:
    """Return the credential's name from the first collected async_credential_name that has one, or None."""
    for namer in hass.data[DATA_NAMERS]:
        try:
            name = namer(hass, address, credential_type, slot)
        except Exception:
            # One broken credential integration must not lose the event.
            _LOGGER.exception(
                "async_credential_name in %s raised an exception", namer.__module__
            )
            continue
        if name is not None:
            return name
    return None
