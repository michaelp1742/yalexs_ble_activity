"""Tests for the Yale Access Bluetooth Activity lock models."""

from custom_components.yalexs_ble_activity.models import LOCK_MODELS


def test_lock_models_hold_the_established_parameters() -> None:
    """Each row holds the slot and PIN parameters established for its model."""
    assert [
        (
            model.key,
            model.name,
            model.first_pin_slot,
            model.last_pin_slot,
            model.master_code_slot,
            model.pin_length_min,
            model.pin_length_max,
        )
        for model in LOCK_MODELS
    ] == [
        ("unity", "Yale Unity Entrance Lock", 0x01, 0x64, 0xFFEE, 6, 6),
        (
            "yrd256",
            "Yale Assure Lock SL (YRD256) with a network module",
            0x01,
            0xFA,
            0xFFEE,
            4,
            8,
        ),
        (
            "doorman_classic",
            "Yale Doorman Classic (V2N) with the Yale Access Module",
            0x00,
            0x09,
            None,
            6,
            6,
        ),
        ("doorman_l3", "Yale Doorman L3", None, None, None, 6, 10),
        ("other", "Not listed", None, None, None, None, None),
    ]
