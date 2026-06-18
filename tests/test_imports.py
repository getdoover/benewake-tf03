"""Basic tests: ensure modules import and the config schema is valid."""


def test_import_app():
    from benewake_tf03.application import BenewakeTF03

    assert BenewakeTF03


def test_config():
    from benewake_tf03.app_config import BenewakeTF03Config

    config = BenewakeTF03Config()
    assert isinstance(BenewakeTF03Config.to_schema(), dict)
    # Defaults to the sensor's native serial streaming mode (no Modbus setup).
    assert config.comms_mode.default == "serial"
    # The TF03 RS485 interface defaults to 115200 baud in both modes.
    assert config.serial_baud.default == 115200
    assert config.modbus_settings.serial_baud.default == 115200


def test_tags():
    from benewake_tf03.app_tags import BenewakeTF03Tags

    assert BenewakeTF03Tags


def test_ui():
    from benewake_tf03.app_ui import BenewakeTF03UI

    # Building the schema (as `export-ui` does) exercises the tag bindings.
    ui = BenewakeTF03UI(None, None, None)
    assert ui.to_schema(resolve_config=False)


def test_state():
    from benewake_tf03.app_state import TF03State

    assert TF03State
