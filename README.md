# Yale Access Bluetooth Activity

A parallel integration to `yalexs_ble`, Home Assistant's
[Yale Access Bluetooth](https://www.home-assistant.io/integrations/yalexs_ble/) integration. It shows the lock's own
log in a logbook of its own: each record Home Assistant reads off the lock is one line in the logbook of this
integration's device, at the time the lock wrote the record, in the lock's order, such as "Front Door keypad code by
Guest at slot 15". Each record also fires an event for automations, whose type names the source of a credential's use
or of a lock operation (a keypad code, the master code, an RF tag, the keypad's button, the inside button, a command
over Bluetooth, the lock's own relock), or the kind of any other record (a door opened, a code added, the keypad's
info). The integration keeps the lock's clock in step with Home Assistant's. It reads the records through Yale Access
Bluetooth's connection to the lock and changes nothing in that integration. It has no PIN actions, changes no setting
on the lock but its clock, and stores no names.

## Requirements

- Home Assistant 2026.10.0 or later.
- The Yale Access Bluetooth integration, set up for the lock.
- yalexs-ble from [Yale-Libs/yalexs-ble#426](https://github.com/Yale-Libs/yalexs-ble/pull/426) on, or a release that
  contains it, for `register_log_record_callback` and `parse_log_event_packet`. The yalexs-ble that Home Assistant
  2026.10 installs, 4.0.1, has neither, and with it Home Assistant cannot load this integration and logs an
  `ImportError`.
- At each start, Home Assistant installs the yalexs-ble version that Yale Access Bluetooth pins, in place of any
  other. Another version stays installed when Home Assistant runs with `--skip-pip-packages yalexs-ble`, or with
  `--skip-pip`, which skips the requirements of every integration.
- yalexs-ble from #426 requires cryptography 50.0.2 or later. Home Assistant 2026.11 pins cryptography 50.0.2.
  Home Assistant 2026.10 pins cryptography 50.0.1, so on 2026.10 no cryptography version meets both.
- For the names of PINs, [Yale Access Bluetooth Keypad](https://github.com/Michaelp1742/yalexs_ble_keypad), set up
  for the lock. Without it, every line and event works and no PIN is named.

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

The entry starts with its option off. It then adds no device and no entity, and reads and writes nothing on the lock.
The model can be changed later in the entry's options.

## The lock models

The model gives the slot and PIN parameters established for the lock. This integration uses one value from the model,
the master code slot: a keypad code entered at that slot is shown as the master code rather than a PIN. The other
values are not used. A blank is a value not established.

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
feed or the cloud. The option is off for a new entry for that reason. With the option on, Home Assistant also keeps
the lock's clock in step with its own (below).

With the option on, the entry adds a device of its own, named after the lock, which has the same Bluetooth connection
as the Yale Access Bluetooth device for the lock and is listed under that device's **Linked devices**. The entry reads
the lock's log whenever it is loaded with the option on. Turning the option off reloads the entry, which then reads and
writes nothing on the lock; the device and its logbook stay.

## The logbook

The logbook of this integration's device, on the device's page or in **Activity** filtered to the device, lists one
line per record, in the order the lock wrote them:

- "Front Door keypad code by Guest at slot 15", a keypad code with its name from Yale Access Bluetooth Keypad;
- "Front Door keypad code at slot 1", a slot with no name;
- "Front Door code added for Guest at slot 4", an addition or a deletion;
- "Front Door master code", a code at the model's master code slot;
- "Front Door keypad info", "Front Door door opened", "Front Door auto lock", and so on for every other record.

The line is the device's name, the type's words, the name where one is known, and the slot where the record has one,
but for the master code, whose slot is the model's. A slot above `0xFF` is written in hexadecimal: a code added at the
master code slot reads "code added at slot 0xFFEE".

Each line is placed at the record's own time, the lock's clock when it wrote the record, not the time Home Assistant
read it. A keypad code entered before the lock relocked sits before the relock's line, whenever the two were read, and
the records read after Home Assistant was down sit at the times they were written. Records written in the same second
are placed 1 ms apart, in the order read. The logbook of the Yale Access Bluetooth lock and its device gets no line
from a record: its lines are at Home Assistant's time, and the two logbooks are kept apart.

A record is discarded, with a debug line in the log, when it is earlier than the last record placed for the lock, or
more than 10 seconds ahead of Home Assistant's time when it is read. Until the first record is placed, the earliest time
is one day before the entry's last setup, so an older backlog is not placed. The last record's time and the serial
number are kept across restarts.

## The events

Each record placed in the logbook fires the event `yalexs_ble_activity_log_record`. Its `event_type` names the
record. A credential's use and a lock operation have the type of their source:

| Event type | Logbook | Record |
|---|---|---|
| `pin` | keypad code | a keypad code, at any slot but the model's master code slot |
| `master_code` | master code | a keypad code at the model's master code slot |
| `rf` | RF tag | an RF tag |
| `finger`, `face`, `palm`, `aliro` | fingerprint, face, palm, Aliro | a credential of that type |
| `credential` | credential | a credential of another type |
| `credential_error` | credential refused | a credential the lock refused |
| `keypad_button` | keypad button | the keypad's Yale button |
| `remote` | remote | a command over Bluetooth, such as from the Yale Home app or from Home Assistant |
| `manual` | manual | the inside button, or the lock turned by hand |
| `auto_lock` | auto lock | the lock's own relock |
| `lock_operation` | lock operation | a lock operation whose op code the library does not name |

A lock operation of another kind has its own type: `knock_received`, `bluetooth_received`, `anomaly`, `auto_retry`,
`over_temp`, `burn_in`, `home_kit`, `z_wave`, `door_sense`, `low_bat_auto_unlock`, `escape_unlock`, `uwb`,
`external_module_operation`, `shabbat_mode`, `scheduled_operation`, `matter`, `double_press`, `aliro_operation`, and
`undefined`.

Every other record has the type of its kind: `door_opened`, `door_closed`, `door_ajar`, `door_state_changed`,
`code_added`, `code_deleted`, `code_added_v2`, `code_deleted_v2`, `credential_added`, `credential_deleted`,
`keypad_open`, `keypad_wrong_code`, `keypad_close`, `keypad_info`, `all_codes_deleted`, `factory_reset`, `tamper`,
`bcm_test`, `homekey_operation`, `dps_info`, `battery_info`, `local_event_notification`, `product_message`,
`matter_message`, and `dialog_reboot`. A record that Yale's numbering does not decode is `unknown_record`. The lock's
answer when no record is unread is no record. The `code_added_v2` and `code_deleted_v2` lines read "code added" and
"code deleted"; the version is the record's format.

On the locks tested, a keypad code the lock accepts writes two records, the keypad's info and then the code, so it
gives `keypad_info` and then `pin`, or `master_code` at the master code slot. A `keypad_info` alone is an entry the
lock did not act on, such as an invalid code or a key pressed without a code; an invalid code has also left no record.
A fingerprint at the Yale Smart Keypad 2 - Fingerprint is recorded as a code at the slot of the PIN associated with
it, a lock slot of its own, so it gives `pin`, and its line names that slot, for example "keypad code at slot 9".
Nothing in the record says the slot is a fingerprint, so the line reads as a keypad code, and it has a name only when
a credential integration names that slot.

An unlock from the Yale Home app is a `remote` record when Home Assistant reads it. While the app is connected to the
lock, it can read the record first, and the unlock then gives nothing here.

### The event's data

| Key | Value |
|---|---|
| `event_type` | the type above |
| `serial` | one more than the previous record's for the lock, kept across restarts: the order read |
| `timestamp` | the lock's time of the record, in UTC, to the second; absent on a record with no decoded time |
| `backlog` | `true` for a record that was unread on the lock when the reads began, such as one written while Home Assistant was down |
| `name` | on a record of a credential's use, addition, or deletion at a slot, the slot's name from Yale Access Bluetooth Keypad, or `null` |
| `device_id` | this integration's device for the lock |
| `log_type` | the record's type number |
| every other field of the record | under the library's name, such as `slot`, `current_lock_state`, `current_door_state`, `key_slot`, `op_code`, `battery_level`, `battery_level_percent`, `error`, `credential_type`, or `credential_error`; a named value in lower case, such as `unlocked`, and a value with no name as its number |
| `raw` | on `unknown_record` only, the record's 18 bytes in hexadecimal |

On a lock operation, `error` and `battery_level_percent` are one byte of the record, published under both names, so
the two always hold the same number.

The event of a code record holds the code as the lock wrote it: the `code` of a code's addition, and the `keycode` of
the keypad's open, wrong code, and close records, in plain text. The recorder keeps each event with its data in its
database, so a code is in the database until the recorder purges the event, and in each backup that includes the
database. A recorder `exclude` of the event type keeps the events out of the database, and the logbook then has no line
for them beyond the ones a page already open shows as they fire.

Records written while Home Assistant was down, for an upgrade, a rebuild, or a hardware failure, are read when it
restarts and fire with `backlog` true, in the order the lock wrote them. An automation that should not run for them
checks `backlog` in a condition. When another integration, such as Yale Access Bluetooth Battery, also reads the
lock's log, the lock is read once for both, and the records unread when the first of them registered its reader are
the ones flagged `backlog`; a record that integration read before this entry registered fires nothing here.

### Automations

An automation triggers on the event, with the record's type in `event_data`, and reads the name from the event's
data:

```yaml
triggers:
  - trigger: event
    event_type: yalexs_ble_activity_log_record
    event_data:
      event_type: pin
conditions:
  - condition: template
    value_template: "{{ trigger.event.data.name == 'Michael' and not trigger.event.data.backlog }}"
```

With more than one lock, `device_id` in `event_data` picks the lock.

### The event entity

The device also has the event entity **Activity**, for example `event.front_door_activity`, disabled by default.
Enabled, it fires an entity event for each record placed in the logbook, with the same data but `device_id`, for
automations on `event.received`. Its time is Home Assistant's time when the record fires, not the record's own time, so
its lines join the device's logbook at those times, beside the records' lines.

### The keypad's battery

A `keypad_info` record holds the keypad's battery reading in `battery_level`, a raw number whose scale is not known.
With the option on, a `keypad_info` record Home Assistant reads never reaches the cloud, whose keypad battery state
stops at the last record the app uploaded, so this record is the only current reading of the keypad's battery. A
trigger-based template sensor keeps the last value:

```yaml
template:
  - triggers:
      - trigger: event
        event_type: yalexs_ble_activity_log_record
        event_data:
          event_type: keypad_info
          device_id: 0123456789abcdef0123456789abcdef
    sensor:
      - name: Front Door keypad battery
        unique_id: front_door_keypad_battery
        state: "{{ trigger.event.data.battery_level }}"
```

In place of the example `device_id`, use the ID of this integration's device for the lock, the last part of the
address of the device's page, so that each lock's keypad has a sensor of its own. The sensor shows the raw value and
keeps it across a restart. It changes only when the keypad is used.

## The lock's clock

A line's time is only as right as the lock's clock, so with the option on Home Assistant keeps the lock's clock in step
with its own and never moves it past its own time.

The lock's clock counts whole seconds and does not say when, between Home Assistant's request and its reply, it read
them. A reading therefore bounds how far the lock's clock is from Home Assistant's to a window a little over a second
wide: above the lock's second less the time the reply arrived, and at or below the next second less the time the
request was written. Home Assistant takes a reading from:

- a clock read, at the entry's setup before its first read of the log, and for a lock with no other reading for 6
  hours;
- the lock's answer that says the log is empty (a `GetLogError`, `0x80`), when the read before it took the last unread
  record. That answer holds the lock's time at that read, and is paired with that record's request and reply. When a
  read finds the log already empty, the answer repeats the previous one's time, so it is no reading.

A reading whose reply came more than `MAX_SAMPLE_ROUND_TRIP` after its request is not used. Between writes, Home
Assistant keeps the part of the window common to every reading, so the estimate narrows below a second as readings fall
at other points of the lock's second. A reading outside the estimate starts it again and logs a debug line.

Home Assistant writes the clock only when the whole estimate lies on one side of its own time:

- More than 10 seconds off, at setup or at any later reading, it sets the clock: to its own time for a lock behind, and
  `MAX_SAMPLE_ROUND_TRIP` ahead of it for a lock ahead, since a write lands up to its round trip late.
- Otherwise, at a later reading, it moves the clock up to 1 second toward its own time, when the estimate after the
  move stays on the lock's side. A lock behind ends within 1 second of Home Assistant's time, and a lock ahead within
  1 second plus `MAX_SAMPLE_ROUND_TRIP`.

The `yalexs-ble` library sends each write at the moment that gives its second's fraction, and the estimate starts again
from the write. Each write logs one info line, such as "Front Door clock 2.6 to 1.3 s behind; moved up to 1 s toward
Home Assistant's time". A read or write that fails logs a debug line, and the next reading goes ahead as usual.

## Limits

- A record read is gone for the Yale Home and August apps and the cloud; the option is off by default for that reason.
- Real time holds for a record that a read follows: Home Assistant reads the log after a lock change, a door change, or
  a new connection. A record the lock writes with no change, such as a code the app adds, waits for the next read; its
  line is still at its own time.
- A line's time is the record's own time, to the second, and as right as the lock's clock. A line shows a moment after
  the time it holds: on the locks tested, the record of a lock change or of a keypad code was read 0.5 to 2 seconds
  after the lock reported the change, and a record that waited for a read shows later.
- A lock clock set back drops the records written in the step's span, since they are earlier than the last record
  placed. A lock whose clock is more than 10 seconds ahead has its clock set to just ahead of Home Assistant's time at
  the entry's setup, or at the next reading; a record read before then is discarded when its own time is more than 10
  seconds ahead of Home Assistant's time at the read.
- Another integration reading the same lock, such as Yale Access Bluetooth Battery, shares the reads: a record it read
  before this entry registered fires nothing here.
- A record the app read first fires nothing.
- The event entity's time is Home Assistant's time when the record fires; its lines, when it is enabled, sit in the
  device's logbook at those times.
- The records are decoded in Yale's numbering; an August lock is not supported.

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

This integration asks each such module in turn for each record it places, and the first name that is not `None` is the
record's `name`. A module that raises is logged and passed over. The module imports nothing from this integration, and
neither integration lists the other in its manifest. Yale Access Bluetooth Keypad ships one, which names the PINs it
keeps, where a name was stored with the PIN.

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
