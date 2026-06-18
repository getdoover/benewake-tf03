import logging
import time

from pydoover.docker import Application

from .app_config import BenewakeTF03Config
from .app_state import TF03State
from .app_ui import BenewakeTF03UI
from .comms import SerialReader

log = logging.getLogger()

# Modbus register map for the TF03 RS485 (function code 0x03 - read holding register).
# See TF03 RS485/RS232 Product Manual V1.3.2, section 6.3.
REG_DISTANCE = 0x0000  # distance, unit: cm
REG_STRENGTH = 0x0001  # signal strength (0 - 3500)
REGISTER_TYPE = 3  # 3 -> read holding registers (Modbus function code 0x03)
NUM_REGS = 2  # read distance + strength in one transaction

# When the target is out of range (or the signal is too weak) the TF03 reports its
# over-range threshold value rather than a real distance. Default is 18000 cm.
OVER_RANGE_CM = 18000


class BenewakeTF03(Application):
    config: BenewakeTF03Config

    loop_target_period = 2  # seconds between sensor reads

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Last good reading: (distance_cm, signal_strength, timestamp)
        self.last_reading: tuple[int, int, float] | None = None
        self.comms_mode = "serial"
        self.serial_reader: SerialReader | None = None

    async def setup(self):
        self.ui = BenewakeTF03UI(self.config)
        self.state = TF03State()

        self.comms_mode = self.config.comms_mode.value
        if self.comms_mode == "serial":
            # Read the TF03's native streaming output straight off the serial port.
            self.serial_reader = SerialReader(
                self.config.serial_port.value,
                self.config.serial_baud.value,
            )
            self.serial_reader.start()
            log.info(
                f"TF03 in SERIAL mode on {self.config.serial_port.value} "
                f"@ {self.config.serial_baud.value} baud"
            )
        else:
            # Modbus mode: hand the bus config to the framework's modbus interface
            # under the name it auto-opens (`modbus_config`), then open the bus.
            # We only do this in modbus mode so the serial port is never grabbed
            # by modbus_interface when running in serial mode.
            self.config.modbus_config = self.config.modbus_settings
            await self.modbus_iface.setup()
            log.info("TF03 in MODBUS mode")

        self.ui_manager.add_children(*self.ui.fetch())
        self.ui_manager.set_display_name(self.config.sensor_name.value)

    async def close(self):
        if self.serial_reader is not None:
            self.serial_reader.stop()
        await super().close()

    async def main_loop(self):
        await self.read_sensor()
        await self.state.spin()

        if self.state.state == "no_comms" or self.last_reading is None:
            log.warning("No comms with TF03 - clearing reading")
            self.ui.update_no_comms()
            await self.set_tag("distance_m", None)
            await self.set_tag("reading_reliable", False)
            return

        distance_cm, strength, ts = self.last_reading

        # Convert to metres and apply the calibration offset.
        distance_m = round(distance_cm / 100.0 + self.config.mounting_offset_m.value, 3)

        reliable = (
            strength >= self.config.min_signal_strength.value
            and distance_cm < OVER_RANGE_CM
            and distance_m <= self.config.max_valid_distance_m.value
        )

        self.ui.update(distance_m, distance_cm, strength, reliable, ts)

        # Publish tags. `distance_m` is the headline value other apps / the cloud read.
        await self.set_tag("distance_m", distance_m if reliable else None)
        await self.set_tag("distance_raw_cm", distance_cm)
        await self.set_tag("signal_strength", strength)
        await self.set_tag("reading_reliable", reliable)

    async def read_sensor(self):
        """Read distance + signal strength from the TF03.

        Uses the native serial stream or Modbus polling depending on comms_mode.
        Updates the comms state machine and caches the last good reading.
        """
        if self.comms_mode == "serial":
            reading = await self.read_serial()
        else:
            reading = await self.read_modbus()

        if reading is None:
            await self.state.register_no_comms()
            return

        distance_cm, strength = reading
        log.debug(f"TF03 read: distance={distance_cm} cm, strength={strength}")

        self.last_reading = (distance_cm, strength, time.time())
        await self.state.register_comms()

    async def read_serial(self) -> tuple[int, int] | None:
        """Latest (distance_cm, strength) from the native serial stream, or None."""
        reading = self.serial_reader.read()
        if reading is None:
            log.info("No fresh TF03 serial frame")
        return reading

    async def read_modbus(self) -> tuple[int, int] | None:
        """Read (distance_cm, strength) over Modbus, or None on failure."""
        result = await self.modbus_iface.read_registers_async(
            modbus_id=self.config.modbus_id.value,
            start_address=REG_DISTANCE,
            num_registers=NUM_REGS,
            register_type=REGISTER_TYPE,
        )

        if not result or len(result) < NUM_REGS:
            log.info("Failed to read from TF03 (no/short Modbus response)")
            return None

        return int(result[0]), int(result[1])
