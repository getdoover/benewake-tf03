import logging
import time

from pydoover.docker import Application

from .app_config import BenewakeTF03Config
from .app_state import TF03State
from .app_tags import BenewakeTF03Tags
from .app_ui import BenewakeTF03UI
from .comms import SerialReader
from .detector import DropDetector

DROP_EVENT_CHANNEL = "tf03_drop_events"

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
    tags: BenewakeTF03Tags
    ui: BenewakeTF03UI

    config_cls = BenewakeTF03Config
    tags_cls = BenewakeTF03Tags
    ui_cls = BenewakeTF03UI

    async def setup(self):
        # Last reading published to tags: (distance_cm, signal_strength, timestamp)
        self.last_reading: tuple[int, int, float] | None = None
        # Latest descent velocity (m/s, positive = dropping) for the live tag.
        self.last_velocity: float | None = None
        self.comms_mode = "serial"
        self.serial_reader: SerialReader | None = None
        self.detector: DropDetector | None = None

        self.state = TF03State()

        # Set how fast the main loop processes frames and publishes tags.
        self.loop_target_period = self._loop_period_from_config()

        self.comms_mode = self.config.comms_mode.value
        if self.comms_mode == "serial":
            # Read the TF03's native streaming output straight off the serial port.
            self.serial_reader = SerialReader(
                self.config.serial_port.value,
                self.config.serial_baud.value,
            )
            self.serial_reader.start()
            if self.config.enable_drop_detection.value:
                self.detector = DropDetector(
                    velocity_threshold_mps=self.config.drop_velocity_threshold_mps.value,
                    min_magnitude_m=self.config.min_drop_magnitude_m.value,
                    persistence_frames=self.config.drop_persistence_frames.value,
                    distance_increases_on_drop=self.config.drop_distance_increases.value,
                )
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
        return 1 / self.config.update_rate_hz.value

    async def main_loop(self):
        await self.read_sensor()
        await self.state.spin()
        await self.publish_tags()

    async def publish_tags(self):
        """Publish the latest reading + velocity to tags for the UI / cloud."""
        if self.state.state == "no_comms" or self.last_reading is None:
            log.warning("No comms with TF03 - clearing reading")
            # Blank the reading and raise the comms warning. The signal warning
            # stays hidden so it doesn't stack on top of the no-comms warning.
            await self.tags.distance_m.set(None)
            await self.tags.distance_raw_cm.set(None)
            await self.tags.signal_strength.set(None)
            await self.tags.velocity_mps.set(None)
            await self.tags.reading_reliable.set(False)
            await self.tags.comms_ok.set(False)
            await self.tags.signal_warning_hidden.set(True)
            return

        distance_cm, strength, ts = self.last_reading
        distance_m = self._distance_m(distance_cm)
        reliable = self._is_reliable(distance_cm, strength, distance_m)

        # `distance_m` is the headline value other apps / the cloud read -
        # cleared when unreliable.
        await self.tags.distance_m.set(distance_m if reliable else None)
        await self.tags.distance_raw_cm.set(distance_cm)
        await self.tags.signal_strength.set(strength)
        await self.tags.velocity_mps.set(
            round(self.last_velocity, 3) if self.last_velocity is not None else None
        )
        await self.tags.reading_reliable.set(reliable)
        await self.tags.comms_ok.set(True)
        await self.tags.signal_warning_hidden.set(reliable)
        await self.tags.last_read.set(int(ts * 1000))

    def _distance_m(self, distance_cm: int) -> float:
        """Calibrated distance in metres (raw + mounting offset)."""
        return round(distance_cm / 100.0 + self.config.mounting_offset_m.value, 3)

    def _is_reliable(self, distance_cm: int, strength: int, distance_m: float) -> bool:
        return (
            strength >= self.config.min_signal_strength.value
            and distance_cm < OVER_RANGE_CM
            and distance_m <= self.config.max_valid_distance_m.value
        )

    async def read_sensor(self):
        """Update the comms state machine and cache the latest reading.

        Serial mode drains the full 100 Hz batch and runs drop detection; Modbus
        mode does a single low-rate poll.
        """
        if self.comms_mode == "serial":
            await self.process_serial_batch()
            return

        reading = await self.read_modbus()
        if reading is None:
            await self.state.register_no_comms()
            return

        distance_cm, strength = reading
        log.debug(f"TF03 read: distance={distance_cm} cm, strength={strength}")
        self.last_reading = (distance_cm, strength, time.time())
        await self.state.register_comms()

    async def process_serial_batch(self):
        """Drain every buffered 100 Hz frame, run drop detection, cache the last.

        Each reliable (signal-valid, in-range) frame is fed to the detector so a
        transient drop between publish ticks is never missed; weak/over-range
        frames are gated out first so a momentary dropout can't fake a velocity
        spike. A completed drop is logged to the tf03_drop_events channel.
        """
        batch = self.serial_reader.drain()
        if not batch:
            await self.state.register_no_comms()
            return

        for distance_cm, strength, t_mono, t_wall in batch:
            if self.detector is None:
                continue
            distance_m = self._distance_m(distance_cm)
            if not self._is_reliable(distance_cm, strength, distance_m):
                continue
            event = self.detector.feed(distance_m, t_mono, t_wall)
            if event is not None:
                await self.emit_drop_event(event)

        last_cm, last_strength, _, last_wall = batch[-1]
        self.last_reading = (last_cm, last_strength, last_wall)
        self.last_velocity = self.detector.last_velocity_mps if self.detector else None
        await self.state.register_comms()

    async def emit_drop_event(self, event):
        """Log one detected drop to the shared tf03_drop_events channel.

        The message is flat and self-describing via ``app_key`` so multiple range
        sensors on one device share the channel without collision.
        """
        payload = {
            "app_key": self.app_key,
            "ts": int(event.start_ts * 1000),
            "pre_distance_m": round(event.pre_distance_m, 3),
            "extent_distance_m": round(event.extent_distance_m, 3),
            "magnitude_m": round(event.magnitude_m, 3),
            "peak_velocity_mps": round(event.peak_velocity_mps, 3),
            "duration_ms": event.duration_ms,
            "trace": event.trace,
        }
        log.warning(
            f"TF03 drop detected: {payload['magnitude_m']} m @ "
            f"{payload['peak_velocity_mps']} m/s over {payload['duration_ms']} ms"
        )
        await self.create_message(DROP_EVENT_CHANNEL, payload)

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
