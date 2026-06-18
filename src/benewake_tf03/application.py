import logging
import time

from pydoover.docker import Application

from .app_config import BenewakeTF03Config
from .app_state import TF03State
from .app_tags import BenewakeTF03Tags
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

# Upper bound on the configurable update rate. The sensor streams at 100 Hz, but
# the Doover client can't keep up much past this, so we cap it.
MAX_UPDATE_RATE_HZ = 100


class BenewakeTF03(Application):
    config: BenewakeTF03Config
    tags: BenewakeTF03Tags
    ui: BenewakeTF03UI

    config_cls = BenewakeTF03Config
    tags_cls = BenewakeTF03Tags
    ui_cls = BenewakeTF03UI

    async def setup(self):
        # Last good reading: (distance_cm, signal_strength, timestamp)
        self.last_reading: tuple[int, int, float] | None = None
        self.comms_mode = "serial"
        self.serial_reader: SerialReader | None = None

        self.state = TF03State()

        # Set how fast the main loop samples the latest frame and publishes tags.
        self.loop_target_period = self._loop_period_from_config()

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

    async def close(self):
        if self.serial_reader is not None:
            self.serial_reader.stop()
        await super().close()

    def _loop_period_from_config(self) -> float:
        """Main-loop period (seconds) from the configured update rate in Hz."""
        freq = self.config.update_rate_hz.value
        if not freq or freq <= 0:
            return 1.0
        if freq > MAX_UPDATE_RATE_HZ:
            log.warning(
                f"Update Rate {freq} Hz exceeds the {MAX_UPDATE_RATE_HZ} Hz max; "
                f"capping to {MAX_UPDATE_RATE_HZ} Hz"
            )
            freq = MAX_UPDATE_RATE_HZ
        return 1 / freq

    async def main_loop(self):
        await self.read_sensor()
        await self.state.spin()

        if self.state.state == "no_comms" or self.last_reading is None:
            log.warning("No comms with TF03 - clearing reading")
            # Blank the reading and raise the comms warning. The signal warning
            # stays hidden so it doesn't stack on top of the no-comms warning.
            await self.tags.distance_m.set(None)
            await self.tags.distance_raw_cm.set(None)
            await self.tags.signal_strength.set(None)
            await self.tags.reading_reliable.set(False)
            await self.tags.comms_ok.set(False)
            await self.tags.signal_warning_hidden.set(True)
            return

        distance_cm, strength, ts = self.last_reading

        # Convert to metres and apply the calibration offset.
        distance_m = round(distance_cm / 100.0 + self.config.mounting_offset_m.value, 3)

        reliable = (
            strength >= self.config.min_signal_strength.value
            and distance_cm < OVER_RANGE_CM
            and distance_m <= self.config.max_valid_distance_m.value
        )

        # Publish tags; the UI binds to these. `distance_m` is the headline
        # value other apps / the cloud read - cleared when unreliable.
        await self.tags.distance_m.set(distance_m if reliable else None)
        await self.tags.distance_raw_cm.set(distance_cm)
        await self.tags.signal_strength.set(strength)
        await self.tags.reading_reliable.set(reliable)
        await self.tags.comms_ok.set(True)
        await self.tags.signal_warning_hidden.set(reliable)
        await self.tags.last_read.set(int(ts * 1000))

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
