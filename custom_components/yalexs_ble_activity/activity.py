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
    LockStatus,
    LogRecord,
    MatterMessage,
    OpCode,
    ProductMessage,
    Tamper,
)

from homeassistant.components.event import ATTR_EVENT_TYPE
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.integration_platform import (
    async_process_integration_platforms,
)
from homeassistant.util import dt as dt_util
from homeassistant.util.hass_dict import HassKey

from .const import (
    ATTR_BACKLOG,
    ATTR_LOG_TYPE,
    ATTR_NAME,
    ATTR_SERIAL,
    ATTR_SOURCE,
    ATTR_TIMESTAMP,
    DOMAIN,
    EVENT_TYPE_ALL_CODES_DELETED,
    EVENT_TYPE_BATTERY_INFO,
    EVENT_TYPE_BCM_TEST,
    EVENT_TYPE_CODE_ADDED,
    EVENT_TYPE_CODE_ADDED_V2,
    EVENT_TYPE_CODE_DELETED,
    EVENT_TYPE_CODE_DELETED_V2,
    EVENT_TYPE_CREDENTIAL_ADDED,
    EVENT_TYPE_CREDENTIAL_DELETED,
    EVENT_TYPE_CREDENTIAL_ERROR,
    EVENT_TYPE_DIALOG_REBOOT,
    EVENT_TYPE_DOOR_AJAR,
    EVENT_TYPE_DOOR_CLOSED,
    EVENT_TYPE_DOOR_OPENED,
    EVENT_TYPE_DOOR_STATE_CHANGED,
    EVENT_TYPE_DPS_INFO,
    EVENT_TYPE_FACTORY_RESET,
    EVENT_TYPE_JAMMED,
    EVENT_TYPE_KEYPAD_CLOSE,
    EVENT_TYPE_KEYPAD_INFO,
    EVENT_TYPE_KEYPAD_OPEN,
    EVENT_TYPE_KEYPAD_WRONG_CODE,
    EVENT_TYPE_LOCAL_EVENT_NOTIFICATION,
    EVENT_TYPE_LOCK_STATE,
    EVENT_TYPE_LOCKED,
    EVENT_TYPE_MATTER_MESSAGE,
    EVENT_TYPE_PRODUCT_MESSAGE,
    EVENT_TYPE_SECURED,
    EVENT_TYPE_TAMPER,
    EVENT_TYPE_UNKNOWN_RECORD,
    EVENT_TYPE_UNLATCHED,
    EVENT_TYPE_UNLOCKED,
    SOURCE_ALIRO,
    SOURCE_ALIRO_OPERATION,
    SOURCE_AUTO_LOCK,
    SOURCE_CREDENTIAL,
    SOURCE_FACE,
    SOURCE_FINGER,
    SOURCE_HOMEKEY_OPERATION,
    SOURCE_KEYPAD_BUTTON,
    SOURCE_LOCK_OPERATION,
    SOURCE_MANUAL,
    SOURCE_MASTER_CODE,
    SOURCE_PALM,
    SOURCE_PIN,
    SOURCE_REMOTE,
    SOURCE_RF,
)
from .models import LockModel

_LOGGER = logging.getLogger(__name__)

type CredentialNamer = Callable[[HomeAssistant, str, LockCred, int], str | None]

DATA_NAMERS: HassKey[list[CredentialNamer]] = HassKey(f"{DOMAIN}_namers")

_LOCK_STATE_EVENT_TYPES = {
    LockStatus.LOCKED: EVENT_TYPE_LOCKED,
    LockStatus.UNLOCKED: EVENT_TYPE_UNLOCKED,
    LockStatus.SECUREMODE: EVENT_TYPE_SECURED,
    LockStatus.UNLATCHED: EVENT_TYPE_UNLATCHED,
    LockStatus.JAMMED: EVENT_TYPE_JAMMED,
}

_CREDENTIAL_SOURCES = {
    LockCred.RF: SOURCE_RF,
    LockCred.FINGER: SOURCE_FINGER,
    LockCred.FACE: SOURCE_FACE,
    LockCred.PALM: SOURCE_PALM,
    LockCred.ALIRO: SOURCE_ALIRO,
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
    DPSInfo: EVENT_TYPE_DPS_INFO,
    BatteryInfo: EVENT_TYPE_BATTERY_INFO,
    LocalEventNotification: EVENT_TYPE_LOCAL_EVENT_NOTIFICATION,
    ProductMessage: EVENT_TYPE_PRODUCT_MESSAGE,
    MatterMessage: EVENT_TYPE_MATTER_MESSAGE,
    DialogReboot: EVENT_TYPE_DIALOG_REBOOT,
}

# A record field with one of these names is published as record_<name>, so that the
# event has the field's value and an attribute of that name is always its own.
_EVENT_ATTRIBUTES = {
    ATTR_BACKLOG,
    ATTR_LOG_TYPE,
    ATTR_TIMESTAMP,
    ATTR_SERIAL,
    ATTR_EVENT_TYPE,
    ATTR_SOURCE,
    ATTR_NAME,
    ATTR_DEVICE_ID,
}


class Activity(NamedTuple):
    """The event type and source of a record, and the credential slot and type a name is asked for."""

    event_type: str
    source: str | None
    slot: int | None
    credential_type: LockCred | None


def _named(value: Enum) -> bool:
    """Return whether value is a member its enum defines; a member the enum makes for a value it does not define is not in __members__."""
    return value.name in type(value).__members__


def _kind_event_type(record: LogRecord) -> str:
    """Return the event type of the record's nearest class in _RECORD_EVENT_TYPES, else unknown_record."""
    for record_class in type(record).__mro__:
        if (event_type := _RECORD_EVENT_TYPES.get(record_class)) is not None:
            return event_type
    return EVENT_TYPE_UNKNOWN_RECORD


def _operation_lock_state(record: LogRecord) -> LockStatus | None:
    """Return the lock state of a record of an operation or a credential's use, else None."""
    match record:
        case (
            LockOperation(current_lock_state=lock_state)
            | CodeOperation(current_lock_state=lock_state)
            | CredentialOperation(current_lock_state=lock_state)
            | HomekeyOperation(current_lock_state=lock_state)
        ):
            return lock_state
    return None


def _code_source(
    slot: int, credential_type: LockCred, model: LockModel
) -> tuple[str, int | None, LockCred | None]:
    """Return master_code at the model row's master code slot, else pin with slot and credential_type."""
    if slot == model.master_code_slot:
        return SOURCE_MASTER_CODE, None, None
    return SOURCE_PIN, slot, credential_type


def _source_or_kind(
    record: LogRecord, model: LockModel
) -> tuple[str, int | None, LockCred | None]:
    """Return the source of a use or an operation, else the record's kind, with the slot and credential type to name."""
    match record:
        case CodeOperation(slot=slot):
            return _code_source(slot, LockCred.PIN, model)
        case CredentialOperation(
            credential_type=LockCred() as credential_type,
            credential_error=None,
            slot=slot,
        ) if _named(credential_type):
            if credential_type in (LockCred.PIN, LockCred.INSIDE_DOOR_PIN):
                return _code_source(slot, credential_type, model)
            return (
                _CREDENTIAL_SOURCES.get(credential_type, SOURCE_CREDENTIAL),
                slot,
                credential_type,
            )
        case CredentialOperation(credential_error=None):
            return SOURCE_CREDENTIAL, None, None
        case CredentialOperation():
            return EVENT_TYPE_CREDENTIAL_ERROR, None, None
        # In field captures a press of the keypad's Yale button was recorded as
        # DOOR_STATE_CHANGED with key_slot 0xFF, and a command over Bluetooth with
        # key_slot 0.
        case (
            LockOperation(op_code=OpCode.DOOR_STATE_CHANGED, key_slot=0xFF)
            | LockOperation(op_code=OpCode.ONE_TOUCH)
        ):
            return SOURCE_KEYPAD_BUTTON, None, None
        case LockOperation(op_code=OpCode.DOOR_STATE_CHANGED):
            return SOURCE_REMOTE, None, None
        case LockOperation(
            op_code=OpCode.DOOR_MANUAL_STATE_CHANGE | OpCode.INSIDE_BUTTON
        ):
            return SOURCE_MANUAL, None, None
        case LockOperation(op_code=OpCode.AUTO_RELOCK):
            return SOURCE_AUTO_LOCK, None, None
        case LockOperation(op_code=OpCode.ALIRO):
            # The name of OpCode.ALIRO in lower case is SOURCE_ALIRO, the source of a
            # credential's use, so the operation has a source of its own.
            return SOURCE_ALIRO_OPERATION, None, None
        case LockOperation(op_code=OpCode() as op_code) if _named(op_code):
            return op_code.name.lower(), None, None
        case LockOperation():
            return SOURCE_LOCK_OPERATION, None, None
        case HomekeyOperation():
            return SOURCE_HOMEKEY_OPERATION, None, None
        case DoorStateChanged(current_door_state=door_state):
            return (
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
            return _kind_event_type(record), slot, LockCred.PIN
        case (
            CredentialAdded(credential_type=LockCred() as credential_type, slot=slot)
            | CredentialDeleted(
                credential_type=LockCred() as credential_type, slot=slot
            )
        ) if _named(credential_type):
            return _kind_event_type(record), slot, credential_type
    return _kind_event_type(record), None, None


def activity_for(record: LogRecord, model: LockModel) -> Activity:
    """Return the activity of a record: the lock state with the source of a use or an operation, else the record's kind."""
    source_or_kind, slot, credential_type = _source_or_kind(record, model)
    if (lock_state := _operation_lock_state(record)) is None:
        return Activity(source_or_kind, None, slot, credential_type)
    return Activity(
        _LOCK_STATE_EVENT_TYPES.get(lock_state, EVENT_TYPE_LOCK_STATE),
        source_or_kind,
        slot,
        credential_type,
    )


def _attribute_value(value: Any) -> Any:
    """Return a decoded field as an attribute value."""
    match value:
        case Enum() if _named(value):
            return value.name.lower()
        case Enum():
            return value.value
        case tuple():
            return list(value)
    return value


def attributes_for(record: LogRecord, backlog: bool) -> dict[str, Any]:
    """Return the event attributes of a record: backlog, its log type, its lock time, and its decoded fields."""
    attributes: dict[str, Any] = {
        ATTR_BACKLOG: backlog,
        ATTR_LOG_TYPE: record.log_type,
    }
    for field in fields(record):
        value = getattr(record, field.name)
        if field.name == "time_stamp":
            attributes[ATTR_TIMESTAMP] = dt_util.utc_from_timestamp(value).isoformat()
        elif field.name != "raw":
            name = (
                f"record_{field.name}"
                if field.name in _EVENT_ATTRIBUTES
                else field.name
            )
            attributes[name] = _attribute_value(value)
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
