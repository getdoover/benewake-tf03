from pathlib import Path

from pydoover import config
from pydoover.docker.modbus import ModbusConfig


class BenewakeTF03Config(config.Schema):
    """User-configurable settings for the Benewake TF03 LiDAR app."""

    def __init__(self):
        self.sensor_name = config.String(
            "Sensor Name",
            default="TF03 LiDAR",
            description="Friendly name shown on the dashboard.",
        )

        # How we talk to the sensor. The TF03 ships in "serial" mode (it just
        # streams its native 0x59 0x59 frames over RS485/UART, no request needed),
        # so that is the zero-setup default. "modbus" requires enabling Modbus on
        # the sensor first (see README) and shares the bus via modbus_interface.
        self.comms_mode = config.Enum(
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
        self.serial_port = config.String(
            "Serial Port",
            default="/dev/ttyAMA0",
            description=(
                "(Serial mode) Serial device the TF03 is wired to, e.g. "
                "/dev/ttyAMA0, /dev/ttyUSB0. A pyserial URL such as "
                "socket://host:port is also accepted (used by the simulator)."
            ),
        )

        self.serial_baud = config.Integer(
            "Serial Baud",
            default=115200,
            description=(
                "(Serial mode) Baud rate of the TF03 serial stream. Factory "
                "default is 115200 (8 data bits, no parity, 1 stop bit)."
            ),
        )

        # --- Modbus mode settings (comms_mode = "modbus") ---
        self.modbus_id = config.Integer(
            "Modbus Address",
            default=1,
            description=(
                "(Modbus mode) Modbus/RS485 slave address of the TF03. Factory "
                "default is 1. Valid range is 1-247."
            ),
        )

        self.mounting_offset_m = config.Number(
            "Mounting Offset Metres",
            default=0.0,
            description=(
                "Added to the raw measured distance for calibration "
                "(e.g. sensor recess or known bias). Usually 0."
            ),
        )

        self.min_signal_strength = config.Integer(
            "Minimum Signal Strength",
            default=40,
            description=(
                "Readings with signal strength below this are flagged as unreliable. "
                "The TF03 datasheet threshold is 40."
            ),
        )

        self.max_valid_distance_m = config.Number(
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
        self.modbus_settings = ModbusConfig("Modbus Config")
        # The TF03 RS485 interface runs at 115200 8N1 by default, so override the
        # generic 9600 default that ModbusConfig ships with.
        self.modbus_settings.serial_baud.default = 115200


def export():
    BenewakeTF03Config().export(
        Path(__file__).parents[2] / "doover_config.json", "benewake_tf03"
    )
