"""Constants for the Yale Access Bluetooth Activity integration."""

DOMAIN = "yalexs_ble_activity"
OWNER_DOMAIN = "yalexs_ble"
CONF_READ_ACTIVITY_LOG = "read_activity_log"
CONF_LOCK_MODEL = "lock_model"

ATTR_TIMESTAMP = "timestamp"
ATTR_BACKLOG = "backlog"
ATTR_NAME = "name"
ATTR_RAW = "raw"
ATTR_SERIAL = "serial"
ATTR_SLOT = "slot"

EVENT_LOG_RECORD = "yalexs_ble_activity_log_record"

EVENT_TYPE_MASTER_CODE = "master_code"
EVENT_TYPE_PIN = "pin"
EVENT_TYPE_RF = "rf"
EVENT_TYPE_FINGER = "finger"
EVENT_TYPE_FACE = "face"
EVENT_TYPE_PALM = "palm"
EVENT_TYPE_ALIRO = "aliro"
EVENT_TYPE_CREDENTIAL = "credential"
EVENT_TYPE_CREDENTIAL_ERROR = "credential_error"
EVENT_TYPE_KEYPAD_BUTTON = "keypad_button"
EVENT_TYPE_REMOTE = "remote"
EVENT_TYPE_MANUAL = "manual"
EVENT_TYPE_AUTO_LOCK = "auto_lock"
EVENT_TYPE_ALIRO_OPERATION = "aliro_operation"
EVENT_TYPE_LOCK_OPERATION = "lock_operation"
EVENT_TYPE_DOOR_OPENED = "door_opened"
EVENT_TYPE_DOOR_CLOSED = "door_closed"
EVENT_TYPE_DOOR_AJAR = "door_ajar"
EVENT_TYPE_DOOR_STATE_CHANGED = "door_state_changed"
EVENT_TYPE_CODE_ADDED = "code_added"
EVENT_TYPE_CODE_DELETED = "code_deleted"
EVENT_TYPE_CODE_ADDED_V2 = "code_added_v2"
EVENT_TYPE_CODE_DELETED_V2 = "code_deleted_v2"
EVENT_TYPE_CREDENTIAL_ADDED = "credential_added"
EVENT_TYPE_CREDENTIAL_DELETED = "credential_deleted"
EVENT_TYPE_KEYPAD_OPEN = "keypad_open"
EVENT_TYPE_KEYPAD_WRONG_CODE = "keypad_wrong_code"
EVENT_TYPE_KEYPAD_CLOSE = "keypad_close"
EVENT_TYPE_KEYPAD_INFO = "keypad_info"
EVENT_TYPE_ALL_CODES_DELETED = "all_codes_deleted"
EVENT_TYPE_FACTORY_RESET = "factory_reset"
EVENT_TYPE_TAMPER = "tamper"
EVENT_TYPE_BCM_TEST = "bcm_test"
EVENT_TYPE_HOMEKEY_OPERATION = "homekey_operation"
EVENT_TYPE_DPS_INFO = "dps_info"
EVENT_TYPE_BATTERY_INFO = "battery_info"
EVENT_TYPE_LOCAL_EVENT_NOTIFICATION = "local_event_notification"
EVENT_TYPE_PRODUCT_MESSAGE = "product_message"
EVENT_TYPE_MATTER_MESSAGE = "matter_message"
EVENT_TYPE_DIALOG_REBOOT = "dialog_reboot"
EVENT_TYPE_UNKNOWN_RECORD = "unknown_record"

# A literal is the event type of a LockOperation whose OpCode member has no
# constant above: the member's name in lower case.
EVENT_TYPES = (
    EVENT_TYPE_MASTER_CODE,
    EVENT_TYPE_PIN,
    EVENT_TYPE_RF,
    EVENT_TYPE_FINGER,
    EVENT_TYPE_FACE,
    EVENT_TYPE_PALM,
    EVENT_TYPE_ALIRO,
    EVENT_TYPE_CREDENTIAL,
    EVENT_TYPE_CREDENTIAL_ERROR,
    EVENT_TYPE_KEYPAD_BUTTON,
    EVENT_TYPE_REMOTE,
    EVENT_TYPE_MANUAL,
    EVENT_TYPE_AUTO_LOCK,
    "knock_received",
    "bluetooth_received",
    "anomaly",
    "auto_retry",
    "over_temp",
    "burn_in",
    "home_kit",
    "z_wave",
    "door_sense",
    "low_bat_auto_unlock",
    "escape_unlock",
    "uwb",
    "external_module_operation",
    "shabbat_mode",
    "scheduled_operation",
    "matter",
    "double_press",
    EVENT_TYPE_ALIRO_OPERATION,
    "undefined",
    EVENT_TYPE_LOCK_OPERATION,
    EVENT_TYPE_DOOR_OPENED,
    EVENT_TYPE_DOOR_CLOSED,
    EVENT_TYPE_DOOR_AJAR,
    EVENT_TYPE_DOOR_STATE_CHANGED,
    EVENT_TYPE_CODE_ADDED,
    EVENT_TYPE_CODE_DELETED,
    EVENT_TYPE_CODE_ADDED_V2,
    EVENT_TYPE_CODE_DELETED_V2,
    EVENT_TYPE_CREDENTIAL_ADDED,
    EVENT_TYPE_CREDENTIAL_DELETED,
    EVENT_TYPE_KEYPAD_OPEN,
    EVENT_TYPE_KEYPAD_WRONG_CODE,
    EVENT_TYPE_KEYPAD_CLOSE,
    EVENT_TYPE_KEYPAD_INFO,
    EVENT_TYPE_ALL_CODES_DELETED,
    EVENT_TYPE_FACTORY_RESET,
    EVENT_TYPE_TAMPER,
    EVENT_TYPE_BCM_TEST,
    EVENT_TYPE_HOMEKEY_OPERATION,
    EVENT_TYPE_DPS_INFO,
    EVENT_TYPE_BATTERY_INFO,
    EVENT_TYPE_LOCAL_EVENT_NOTIFICATION,
    EVENT_TYPE_PRODUCT_MESSAGE,
    EVENT_TYPE_MATTER_MESSAGE,
    EVENT_TYPE_DIALOG_REBOOT,
    EVENT_TYPE_UNKNOWN_RECORD,
)


# The logbook words of each event type, as they read mid-sentence.
EVENT_TYPE_WORDS = {
    EVENT_TYPE_MASTER_CODE: "master code",
    EVENT_TYPE_PIN: "keypad code",
    EVENT_TYPE_RF: "RF tag",
    EVENT_TYPE_FINGER: "fingerprint",
    EVENT_TYPE_FACE: "face",
    EVENT_TYPE_PALM: "palm",
    EVENT_TYPE_ALIRO: "Aliro",
    EVENT_TYPE_CREDENTIAL: "credential",
    EVENT_TYPE_CREDENTIAL_ERROR: "credential refused",
    EVENT_TYPE_KEYPAD_BUTTON: "keypad button",
    EVENT_TYPE_REMOTE: "remote",
    EVENT_TYPE_MANUAL: "manual",
    EVENT_TYPE_AUTO_LOCK: "auto lock",
    "knock_received": "knock received",
    "bluetooth_received": "Bluetooth received",
    "anomaly": "anomaly",
    "auto_retry": "auto retry",
    "over_temp": "over temperature",
    "burn_in": "burn-in",
    "home_kit": "HomeKit",
    "z_wave": "Z-Wave",
    "door_sense": "DoorSense",
    "low_bat_auto_unlock": "low battery auto unlock",
    "escape_unlock": "escape unlock",
    "uwb": "UWB",
    "external_module_operation": "external module operation",
    "shabbat_mode": "Shabbat mode",
    "scheduled_operation": "scheduled operation",
    "matter": "Matter",
    "double_press": "double press",
    EVENT_TYPE_ALIRO_OPERATION: "Aliro operation",
    "undefined": "undefined",
    EVENT_TYPE_LOCK_OPERATION: "lock operation",
    EVENT_TYPE_DOOR_OPENED: "door opened",
    EVENT_TYPE_DOOR_CLOSED: "door closed",
    EVENT_TYPE_DOOR_AJAR: "door ajar",
    EVENT_TYPE_DOOR_STATE_CHANGED: "door state changed",
    EVENT_TYPE_CODE_ADDED: "code added",
    EVENT_TYPE_CODE_DELETED: "code deleted",
    EVENT_TYPE_CODE_ADDED_V2: "code added",
    EVENT_TYPE_CODE_DELETED_V2: "code deleted",
    EVENT_TYPE_CREDENTIAL_ADDED: "credential added",
    EVENT_TYPE_CREDENTIAL_DELETED: "credential deleted",
    EVENT_TYPE_KEYPAD_OPEN: "keypad open",
    EVENT_TYPE_KEYPAD_WRONG_CODE: "keypad wrong code",
    EVENT_TYPE_KEYPAD_CLOSE: "keypad close",
    EVENT_TYPE_KEYPAD_INFO: "keypad info",
    EVENT_TYPE_ALL_CODES_DELETED: "all codes deleted",
    EVENT_TYPE_FACTORY_RESET: "factory reset",
    EVENT_TYPE_TAMPER: "tamper",
    EVENT_TYPE_BCM_TEST: "BCM test",
    EVENT_TYPE_HOMEKEY_OPERATION: "Home Key operation",
    EVENT_TYPE_DPS_INFO: "DPS info",
    EVENT_TYPE_BATTERY_INFO: "battery info",
    EVENT_TYPE_LOCAL_EVENT_NOTIFICATION: "local event notification",
    EVENT_TYPE_PRODUCT_MESSAGE: "product message",
    EVENT_TYPE_MATTER_MESSAGE: "Matter message",
    EVENT_TYPE_DIALOG_REBOOT: "dialog reboot",
    EVENT_TYPE_UNKNOWN_RECORD: "unknown record",
}
