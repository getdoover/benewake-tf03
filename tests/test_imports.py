"""Basic tests: ensure modules import and the config schema is valid."""


def test_import_app():
    from benewake_tf03.application import BenewakeTF03

    assert BenewakeTF03


def test_config():
    from benewake_tf03.app_config import BenewakeTF03Config

    config = BenewakeTF03Config()
    assert isinstance(config.to_dict(), dict)
    # The TF03 RS485 interface defaults to 115200 baud.
    assert config.modbus_config.serial_baud.default == 115200


def test_ui():
    from benewake_tf03.app_config import BenewakeTF03Config
    from benewake_tf03.app_ui import BenewakeTF03UI

    ui = BenewakeTF03UI(BenewakeTF03Config())
    assert ui.fetch()


def test_state():
    from benewake_tf03.app_state import TF03State

    assert TF03State
