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


# The word of each event type, as its state name in the translations.
EVENT_TYPE_WORDS = {
    EVENT_TYPE_MASTER_CODE: "Master code",
    EVENT_TYPE_PIN: "Keypad code",
    EVENT_TYPE_RF: "RF tag",
    EVENT_TYPE_FINGER: "Fingerprint",
    EVENT_TYPE_FACE: "Face",
    EVENT_TYPE_PALM: "Palm",
    EVENT_TYPE_ALIRO: "Aliro",
    EVENT_TYPE_CREDENTIAL: "Credential",
    EVENT_TYPE_CREDENTIAL_ERROR: "Credential refused",
    EVENT_TYPE_KEYPAD_BUTTON: "Keypad button",
    EVENT_TYPE_REMOTE: "Remote",
    EVENT_TYPE_MANUAL: "Manual",
    EVENT_TYPE_AUTO_LOCK: "Auto lock",
    "knock_received": "Knock received",
    "bluetooth_received": "Bluetooth received",
    "anomaly": "Anomaly",
    "auto_retry": "Auto retry",
    "over_temp": "Over temperature",
    "burn_in": "Burn-in",
    "home_kit": "HomeKit",
    "z_wave": "Z-Wave",
    "door_sense": "DoorSense",
    "low_bat_auto_unlock": "Low battery auto unlock",
    "escape_unlock": "Escape unlock",
    "uwb": "UWB",
    "external_module_operation": "External module operation",
    "shabbat_mode": "Shabbat mode",
    "scheduled_operation": "Scheduled operation",
    "matter": "Matter",
    "double_press": "Double press",
    EVENT_TYPE_ALIRO_OPERATION: "Aliro operation",
    "undefined": "Undefined",
    EVENT_TYPE_LOCK_OPERATION: "Lock operation",
    EVENT_TYPE_DOOR_OPENED: "Door opened",
    EVENT_TYPE_DOOR_CLOSED: "Door closed",
    EVENT_TYPE_DOOR_AJAR: "Door ajar",
    EVENT_TYPE_DOOR_STATE_CHANGED: "Door state changed",
    EVENT_TYPE_CODE_ADDED: "Code added",
    EVENT_TYPE_CODE_DELETED: "Code deleted",
    EVENT_TYPE_CODE_ADDED_V2: "Code added (v2)",
    EVENT_TYPE_CODE_DELETED_V2: "Code deleted (v2)",
    EVENT_TYPE_CREDENTIAL_ADDED: "Credential added",
    EVENT_TYPE_CREDENTIAL_DELETED: "Credential deleted",
    EVENT_TYPE_KEYPAD_OPEN: "Keypad open",
    EVENT_TYPE_KEYPAD_WRONG_CODE: "Keypad wrong code",
    EVENT_TYPE_KEYPAD_CLOSE: "Keypad close",
    EVENT_TYPE_KEYPAD_INFO: "Keypad info",
    EVENT_TYPE_ALL_CODES_DELETED: "All codes deleted",
    EVENT_TYPE_FACTORY_RESET: "Factory reset",
    EVENT_TYPE_TAMPER: "Tamper",
    EVENT_TYPE_BCM_TEST: "BCM test",
    EVENT_TYPE_HOMEKEY_OPERATION: "Home Key operation",
    EVENT_TYPE_DPS_INFO: "DPS info",
    EVENT_TYPE_BATTERY_INFO: "Battery info",
    EVENT_TYPE_LOCAL_EVENT_NOTIFICATION: "Local event notification",
    EVENT_TYPE_PRODUCT_MESSAGE: "Product message",
    EVENT_TYPE_MATTER_MESSAGE: "Matter message",
    EVENT_TYPE_DIALOG_REBOOT: "Dialog reboot",
    EVENT_TYPE_UNKNOWN_RECORD: "Unknown record",
}
