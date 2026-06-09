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

        self.modbus_id = config.Integer(
            "Modbus Address",
            default=1,
            description=(
                "Modbus/RS485 slave address of the TF03. Factory default is 1. "
                "Valid range is 1-247."
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

        # The shared RS485/Modbus bus configuration. The modbus_interface app uses
        # this to open the serial (or TCP) bus the sensor is connected to.
        self.modbus_config = ModbusConfig()
        # The TF03 RS485 interface runs at 115200 8N1 by default, so override the
        # generic 9600 default that ModbusConfig ships with.
        self.modbus_config.serial_baud.default = 115200


def export():
    BenewakeTF03Config().export(
        Path(__file__).parents[2] / "doover_config.json", "benewake_tf03"
    )
