"""The lock models of the Yale Access Bluetooth Activity integration."""

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class LockModel:
    """The slot and PIN parameters established for one lock model, None where not established."""

    key: str
    name: str
    first_pin_slot: int | None
    last_pin_slot: int | None
    master_code_slot: int | None
    pin_length_min: int | None
    pin_length_max: int | None


LOCK_MODELS: tuple[LockModel, ...] = (
    # The values are the cloud capabilities of two Unity locks (pinSlotMin, pinSlotMax, masterPinSlot, pinLength) and the Unity Slim user guide.
    LockModel(
        key="unity",
        name="Yale Unity Entrance Lock",
        first_pin_slot=0x01,
        last_pin_slot=0x64,
        master_code_slot=0xFFEE,
        pin_length_min=6,
        pin_length_max=6,
    ),
    # The YRD256 manual (P/N YRL-SLKFTSINSTL-FUL Rev B) gives 250 codes with a network module, 25 without, and PINs of 4 to 8 digits; the first slot is home-assistant/core#185596's, and the master code's slot is from a CodeOperation record of the master code.
    LockModel(
        key="yrd256",
        name="Yale Assure Lock SL (YRD256) with a network module",
        first_pin_slot=0x01,
        last_pin_slot=0xFA,
        master_code_slot=0xFFEE,
        pin_length_min=4,
        pin_length_max=8,
    ),
    # The Yale app uses slots 0 to 9 and the lock refuses slot 10 (jonasfh/snippen-doorman-service PR #22 and issue #26); codes are 6 digits (manual M3639.2015).
    LockModel(
        key="doorman_classic",
        name="Yale Doorman Classic (V2N) with the Yale Access Module",
        first_pin_slot=0x00,
        last_pin_slot=0x09,
        master_code_slot=None,
        pin_length_min=6,
        pin_length_max=6,
    ),
    # The Doorman L3 manual (Rev. 1, 2024) gives user codes the master code's length, 6 to 10 digits; its slots are not fixed, 30 codes by its specification and keypad slots 01 to 20 in its menu.
    LockModel(
        key="doorman_l3",
        name="Yale Doorman L3",
        first_pin_slot=None,
        last_pin_slot=None,
        master_code_slot=None,
        pin_length_min=6,
        pin_length_max=10,
    ),
    # The row for any lock without a row of its own in LOCK_MODELS.
    LockModel(
        key="other",
        name="Not listed",
        first_pin_slot=None,
        last_pin_slot=None,
        master_code_slot=None,
        pin_length_min=None,
        pin_length_max=None,
    ),
)
