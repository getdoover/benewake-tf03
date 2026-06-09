import logging
import time

from pydoover.docker import Application

from .app_config import BenewakeTF03Config
from .app_state import TF03State
from .app_ui import BenewakeTF03UI

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

    async def setup(self):
        self.ui = BenewakeTF03UI(self.config)
        self.state = TF03State()

        # Last good reading: (distance_cm, signal_strength, timestamp)
        self.last_reading: tuple[int, int, float] | None = None

        self.ui_manager.add_children(*self.ui.fetch())
        self.ui_manager.set_display_name(self.config.sensor_name.value)

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
        """Read distance + signal strength from the TF03 over Modbus.

        Updates the comms state machine and caches the last good reading.
        """
        result = await self.modbus_iface.read_registers_async(
            modbus_id=self.config.modbus_id.value,
            start_address=REG_DISTANCE,
            num_registers=NUM_REGS,
            register_type=REGISTER_TYPE,
        )

        if not result or len(result) < NUM_REGS:
            log.info("Failed to read from TF03 (no/short Modbus response)")
            await self.state.register_no_comms()
            return

        distance_cm, strength = int(result[0]), int(result[1])
        log.debug(f"TF03 read: distance={distance_cm} cm, strength={strength}")

        self.last_reading = (distance_cm, strength, time.time())
        await self.state.register_comms()
