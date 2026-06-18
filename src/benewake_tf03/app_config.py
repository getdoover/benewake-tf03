from pathlib import Path

from pydoover import config
from pydoover.config import ApplicationPosition
from pydoover.docker.modbus import ModbusConfig


class BenewakeTF03Config(config.Schema):
    """User-configurable settings for the Benewake TF03 LiDAR app."""

    sensor_name = config.String(
        "Sensor Name",
        default="TF03 LiDAR",
        description="Friendly name shown on the dashboard.",
    )

    # How we talk to the sensor. The TF03 ships in "serial" mode (it just
    # streams its native 0x59 0x59 frames over RS485/UART, no request needed),
    # so that is the zero-setup default. "modbus" requires enabling Modbus on
    # the sensor first (see README) and shares the bus via modbus_interface.
    comms_mode = config.Enum(
        "Comms Mode",
        choices=["serial", "modbus"],
        default="serial",
        description=(
            "How to read the sensor. 'serial' reads the TF03's native RS485/UART "
            "streaming output directly (factory default - no sensor setup needed). "
            "'modbus' polls it over Modbus-RTU via the shared modbus_interface "
            "(requires Modbus to be enabled on the sensor first)."
        ),
    )

    # --- Serial mode settings (comms_mode = "serial") ---
    serial_port = config.String(
        "Serial Port",
        default="/dev/ttyAMA0",
        description=(
            "(Serial mode) Serial device the TF03 is wired to, e.g. "
            "/dev/ttyAMA0, /dev/ttyUSB0. A pyserial URL such as "
            "socket://host:port is also accepted (used by the simulator)."
        ),
    )

    serial_baud = config.Integer(
        "Serial Baud",
        default=115200,
        description=(
            "(Serial mode) Baud rate of the TF03 serial stream. Factory "
            "default is 115200 (8 data bits, no parity, 1 stop bit)."
        ),
    )

    # --- Modbus mode settings (comms_mode = "modbus") ---
    modbus_id = config.Integer(
        "Modbus Address",
        default=1,
        description=(
            "(Modbus mode) Modbus/RS485 slave address of the TF03. Factory "
            "default is 1. Valid range is 1-247."
        ),
    )

    mounting_offset_m = config.Number(
        "Mounting Offset Metres",
        default=0.0,
        description=(
            "Added to the raw measured distance for calibration "
            "(e.g. sensor recess or known bias). Usually 0."
        ),
    )

    min_signal_strength = config.Integer(
        "Minimum Signal Strength",
        default=40,
        description=(
            "Readings with signal strength below this are flagged as unreliable. "
            "The TF03 datasheet threshold is 40."
        ),
    )

    max_valid_distance_m = config.Number(
        "Maximum Valid Distance Metres",
        default=100.0,
        description=(
            "Distances above this are treated as 'no target' / over-range. "
            "The TF03-100 measuring range is 100 m."
        ),
    )

    # The shared RS485/Modbus bus configuration (modbus mode only). The
    # modbus_interface app uses this to open the serial (or TCP) bus the
    # sensor is connected to.
    #
    # NOTE: this is deliberately NOT named `modbus_config`. The Application
    # framework auto-opens any attribute called `config.modbus_config` at
    # startup - which would grab the serial port even in serial mode (a
    # conflict), or crash if no modbus_interface is present. We open the bus
    # ourselves, only in modbus mode (see application.py).
    modbus_settings = ModbusConfig("Modbus Config")
    modbus_settings.serial_baud.default = 115200

    position = ApplicationPosition()


def export():
    BenewakeTF03Config.export(
        Path(__file__).parents[2] / "doover_config.json", "benewake_tf03"
    )
