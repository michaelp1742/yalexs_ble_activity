# Yale Access Bluetooth Activity

A parallel integration to `yalexs_ble`, Home Assistant's
[Yale Access Bluetooth](https://www.home-assistant.io/integrations/yalexs_ble/) integration. It publishes the lock's
activity log as an event entity: each record Home Assistant reads off the lock fires one event, whose type names the
source of a credential's use or of a lock operation (a keypad code, the master code, an RF tag, the keypad's button,
the inside button, a command over Bluetooth, the lock's own relock), or the kind of any other record (a door opened, a
code added, the keypad's info). It reads the records through Yale Access Bluetooth's connection to the lock and changes
nothing in that integration. It has no PIN actions, changes no setting on the lock, and stores no names.

## Requirements

- Home Assistant 2026.10.0 or later.
- The Yale Access Bluetooth integration, set up for the lock.
- yalexs-ble from [Yale-Libs/yalexs-ble#426](https://github.com/Yale-Libs/yalexs-ble/pull/426) on, or a release that
  contains it. This integration imports the library's `register_log_record_callback`, `parse_log_event_packet`, and
  record classes, and relies on the drain that #426 adds, which reads the log after each connection and each lock or
  door change. Home Assistant 2026.10 pins yalexs-ble 4.0.1, an earlier release; with it the import fails and Home
  Assistant logs `Unable to import component` with the `ImportError`.
- At each start, Home Assistant installs the yalexs-ble version that Yale Access Bluetooth pins, in place of any
  other. Another version stays installed when Home Assistant runs with `--skip-pip-packages yalexs-ble`, or with
  `--skip-pip`, which skips the requirements of every integration.
- The yalexs-ble build this integration needs requires cryptography 50.0.2 or later. Home Assistant 2026.11 pins
  cryptography 50.0.2. Home Assistant 2026.10 pins cryptography 50.0.1, so on 2026.10 no cryptography version meets
  both.
- For the names of PINs, [Yale Access Bluetooth Keypad](https://github.com/Michaelp1742/yalexs_ble_keypad), set up
  for the lock. Without it, every event works and no PIN is named.

## Installation

With [HACS](https://hacs.xyz/):

1. In HACS, open the menu at the top right and pick **Custom repositories**.
2. Add `https://github.com/michaelp1742/yalexs_ble_activity` with the type **Integration**.
3. Find **Yale Access Bluetooth Activity** in HACS, download it, and restart Home Assistant.

Without HACS, copy `custom_components/yalexs_ble_activity` into the `custom_components` folder of your Home Assistant
configuration, then restart Home Assistant.

## Setup

1. In **Settings** > **Devices & services**, add **Yale Access Bluetooth Activity**.
2. Pick the lock. The list shows each lock that Yale Access Bluetooth has loaded and that has no activity entry yet.
3. Pick the lock's model. No model is picked in advance, and nothing is read from the lock to guess it.

The entry starts with its option off. It then adds no entity and reads nothing from the lock. The model can be changed
later in the entry's options.

## The lock models

The model gives the slot and PIN parameters established for the lock. This integration reads only the master code's
slot, at which a code fires a **Master code** event; the other values are not read. A blank is a value not
established.

| Model | First PIN slot | Last PIN slot | Master code slot | PIN length |
|---|---|---|---|---|
| Yale Unity Entrance Lock | 1 | 100 | `0xFFEE` | 6 |
| Yale Assure Lock SL (YRD256) with a network module | 1 | 250 | `0xFFEE` | 4 to 8 |
| Yale Doorman Classic (V2N) with the Yale Access Module | 0 | 9 | | 6 |
| Yale Doorman L3 | | | | 6 to 10 |
| Not listed | | | | |

Every model is a Yale lock, and the records are decoded in Yale's numbering. An August lock is not supported.

## The option

In the entry's options, turn on **Publish the lock's activity**.

Home Assistant reads each record off the lock. A record it reads never reaches the Yale Home or August app's activity
feed or the cloud. The option is off for a new entry for that reason.

With the option on, the entry adds the event entity **Activity**, for example `event.front_door_activity`, on a device
of the entry's own, which has the same Bluetooth connection as the Yale Access Bluetooth device for the lock and is
listed under that device's **Linked devices**. The library reads the log only while an integration has a reader
registered on the lock, and this integration's reader belongs to the entity, so disabling the entity stops this
integration's reads; the log is still read while another integration, such as Yale Access Bluetooth Battery, reads
it. Turning the option off reloads the entry, which then reads nothing from the lock; the entity stays, shown as
unavailable, and keeps its history.

## The events

Each record that Home Assistant reads off the lock fires one event, in the order the lock wrote the records. The lock's
answer when no record is unread fires nothing.

A credential's use and a lock operation fire the type of their source:

| Event type | Logbook | Record |
|---|---|---|
| `pin` | Keypad code | a keypad code, at any slot but the model's master code slot |
| `master_code` | Master code | a keypad code at the model's master code slot |
| `rf` | RF tag | an RF tag |
| `finger`, `face`, `palm`, `aliro` | Fingerprint, Face, Palm, Aliro | a credential of that type |
| `credential` | Credential | a credential of another type |
| `credential_error` | Credential refused | a credential the lock refused |
| `keypad_button` | Keypad button | the keypad's Yale button |
| `remote` | Remote | a command over Bluetooth, such as from the Yale Home app or from Home Assistant |
| `manual` | Manual | the inside button, or the lock turned by hand |
| `auto_lock` | Auto lock | the lock's own relock |
| `lock_operation` | Lock operation | a lock operation whose op code the library does not name |

A lock operation of another kind fires its own type: `knock_received`, `bluetooth_received`, `anomaly`, `auto_retry`,
`over_temp`, `burn_in`, `home_kit`, `z_wave`, `door_sense`, `low_bat_auto_unlock`, `escape_unlock`, `uwb`,
`external_module_operation`, `shabbat_mode`, `scheduled_operation`, `matter`, `double_press`, `aliro_operation`, and
`undefined`.

Every other record fires the type of its kind: `door_opened`, `door_closed`, `door_ajar`, `door_state_changed`,
`code_added`, `code_deleted`, `code_added_v2`, `code_deleted_v2`, `credential_added`, `credential_deleted`,
`keypad_open`, `keypad_wrong_code`, `keypad_close`, `keypad_info`, `all_codes_deleted`, `factory_reset`, `tamper`,
`bcm_test`, `homekey_operation`, `dps_info`, `battery_info`, `local_event_notification`, `product_message`,
`matter_message`, and `dialog_reboot`. A record that Yale's numbering does not decode fires `unknown_record`.

On the locks tested, a keypad code the lock accepts writes two records, the keypad's info and then the code, so it
fires `keypad_info` and then `pin`, or `master_code` at the master code slot. A `keypad_info` alone is an entry the
lock did not act on, such as an invalid code or a key pressed without a code; an invalid code has also left no record.
A fingerprint at the Yale Smart Keypad 2 - Fingerprint is recorded as a code at the slot of the PIN associated with
it, so it fires `pin`.

An unlock from the Yale Home app is a Remote event when Home Assistant reads its record. While the app is connected to
the lock, it can read the record first, and the unlock then fires no event.

### The attributes

| Attribute | Value |
|---|---|
| `timestamp` | the lock's time of the record, in UTC, to the second |
| `backlog` | `true` for a record that was unread on the lock when the reads began, such as one written while Home Assistant was down |
| `name` | on a record of a credential's use, addition, or deletion at a slot, the slot's name from Yale Access Bluetooth Keypad, or `null` |
| `log_type` | the record's type number |
| every other field of the record | under the library's name, such as `slot`, `current_lock_state`, `current_door_state`, `key_slot`, `op_code`, `battery_level`, `credential_type`, or `credential_error`; a named value in lower case, such as `unlocked`, and a value with no name as its number |
| `raw` | on `unknown_record` only, the record's 18 bytes in hexadecimal |

An event of a code record holds the code as the lock wrote it: the `code` of a code's addition, and the `keycode` of
the keypad's open, wrong code, and close records, in plain text. The recorder keeps each of the entity's states with
its attributes in its database, so a code is in the entity's history until the recorder purges the state, and in each
backup that includes the database. A recorder `exclude` of the entity keeps its states out of the database.

Records written while Home Assistant was down, for an upgrade, a rebuild, or a hardware failure, are read when it
restarts and fire with `backlog` true, in the order the lock wrote them. An automation that should not run for them
checks `backlog` in a condition. When another integration, such as Yale Access Bluetooth Battery, also reads the
lock's log, the lock is read once for both, and the records unread when the first of them registered its reader are
the ones flagged `backlog`; a record that integration read before this entity was added fires nothing here.

### Automations

An automation that needs the cause triggers on the event entity, with `event_type`, and reads the name from the
attributes:

```yaml
triggers:
  - trigger: event.received
    target:
      entity_id: event.front_door_activity
    options:
      event_type:
        - pin
conditions:
  - condition: template
    value_template: "{{ trigger.to_state.attributes.name == 'Michael' and not trigger.to_state.attributes.backlog }}"
```

## Limits

- Real time holds for a record that a read follows: Home Assistant reads the log after a lock change, a door change,
  or a new connection. A record the lock writes with no change, such as a code the app adds, waits for the next read.
- The lock entity of Yale Access Bluetooth and this event entity are two streams, not aligned: the lock entity changes
  when the lock reports its status, and the event fires when the record is read, 0.5 to 2 seconds later on the
  locks tested.
- A record the app read first fires nothing.
- The event entity's state is the time Home Assistant read the record. The lock's time is the `timestamp` attribute, to
  the second, and as right as the lock's clock.
- The logbook line shows the event's type only, for example "Front Door Activity: Keypad code"; the slot and the name
  are in the attributes, not in the line.

## Names from other integrations

A credential integration names a slot by shipping a `yalexs_ble_activity.py` module at the top of its package with
one function:

```python
@callback
def async_credential_name(
    hass: HomeAssistant, address: str, credential_type: LockCred, slot: int
) -> str | None:
    """Return the name of the credential at slot on the lock at address, or None."""
```

This integration asks each such module in turn, and the first name that is not `None` is the event's `name`. A module
that raises is logged and passed over. The module imports nothing from this integration, and neither integration
lists the other in its manifest. Yale Access Bluetooth Keypad ships one, which names the PINs it keeps, where a name
was stored with the PIN.

## Icon

The integration's icon is drawn from the account tag icon (`mdi-account-tag`) of Material Design Icons by
[Pictogrammers](https://pictogrammers.com/), which is under the Apache License 2.0.

## Development

```sh
uv venv --python 3.14
uv pip install -r requirements_test.txt
.venv/bin/python -m pytest
.venv/bin/pre-commit run --all-files
```

`requirements_test.txt` installs yalexs-ble from a local clone; change that line to a yalexs-ble from #426 on to build
the environment elsewhere.
