"""Native RS485/UART serial comms for the Benewake TF03.

In its "standard output" mode - which is the TF03's factory default - the sensor
continuously transmits a 9-byte frame (default 100 Hz) over RS485/UART with no
request needed. This module reads that stream directly, as an alternative to
polling the sensor over Modbus.

See the TF03 Series User Manual, "UART, RS485, RS232 Communication / Data Frame".
"""

import logging
import threading
import time
from collections import deque

try:
    import serial
except ImportError:  # pragma: no cover - pyserial is only needed at runtime
    serial = None

log = logging.getLogger(__name__)

FRAME_HEADER = 0x59
FRAME_LEN = 9
MAX_BUFFER = 512

# Bound on frames buffered between drain() calls. ~2.5 s at 100 Hz - enough to
# survive a stalled main loop while dropping the oldest frames under backpressure
# rather than growing without bound.
MAX_FRAMES = 256


def parse_frames(buf: bytearray) -> list[tuple[int, int]]:
    """Extract complete, checksum-valid TF03 standard-output frames from *buf*.

    The frame is 9 bytes, with distance and signal strength little-endian::

        0x59 0x59 Dist_L Dist_H Str_L Str_H Reserved Reserved Checksum

    where Checksum is the low byte of the sum of the first 8 bytes.

    Returns a list of ``(distance_cm, signal_strength)`` tuples in arrival order.
    Consumed and skipped bytes are removed from *buf*; any trailing partial frame
    is left in place for the next call.
    """
    out: list[tuple[int, int]] = []
    i = 0
    n = len(buf)
    while n - i >= FRAME_LEN:
        if buf[i] != FRAME_HEADER or buf[i + 1] != FRAME_HEADER:
            i += 1  # not a header - shift one byte and keep looking
            continue
        frame = buf[i : i + FRAME_LEN]
        if (sum(frame[:8]) & 0xFF) != frame[8]:
            i += 1  # bad checksum - drop one byte and resync
            continue
        distance_cm = frame[2] | (frame[3] << 8)
        strength = frame[4] | (frame[5] << 8)
        out.append((distance_cm, strength))
        i += FRAME_LEN
    del buf[:i]
    return out


class SerialReader:
    """Background reader for the TF03's native RS485/UART streaming output.

    A daemon thread continuously reads the serial stream and accumulates *every*
    valid frame (each stamped with monotonic + wall-clock time on arrival);
    :meth:`drain` hands the whole batch to the async main loop without blocking,
    so no frames are lost to a slower loop rate. The thread reconnects
    automatically if the port drops.

    ``port`` may be any pyserial URL - a device path (``/dev/ttyAMA0``,
    ``/dev/ttyUSB0``) or a URL handler such as ``socket://host:port`` (handy for
    the simulator and tests).
    """

    def __init__(self, port: str, baud: int):
        self.port = port
        self.baud = baud
        self._serial = None
        # (distance_cm, strength, t_mono, t_wall), oldest first.
        self._frames: deque[tuple[int, int, float, float]] = deque(maxlen=MAX_FRAMES)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if serial is None:
            raise RuntimeError(
                "pyserial is not installed - cannot use serial comms mode"
            )
        self._thread = threading.Thread(
            target=self._run, name="tf03-serial", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass

    def drain(self) -> list[tuple[int, int, float, float]]:
        """Return and clear all frames buffered since the last call.

        Each frame is ``(distance_cm, strength, t_mono, t_wall)``, oldest first:
        ``t_mono`` (``time.monotonic``) for velocity maths, ``t_wall``
        (``time.time``) for event timestamps. Returns an empty list if no frames
        have arrived - the caller treats that as a missed read.
        """
        with self._lock:
            batch = list(self._frames)
            self._frames.clear()
        return batch

    def _open(self) -> None:
        self._serial = serial.serial_for_url(
            self.port,
            baudrate=self.baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1.0,
        )

    def _run(self) -> None:
        buf = bytearray()
        while not self._stop.is_set():
            try:
                if self._serial is None:
                    self._open()
                    log.info(
                        f"Opened TF03 serial stream on {self.port} @ {self.baud} baud"
                    )
                data = self._serial.read(64)
                if not data:
                    continue  # read timeout - just loop again
                buf.extend(data)
                frames = parse_frames(buf)
                if frames:
                    # All frames in this read arrived together; stamp once.
                    t_mono = time.monotonic()
                    t_wall = time.time()
                    with self._lock:
                        for distance_cm, strength in frames:
                            self._frames.append((distance_cm, strength, t_mono, t_wall))
                if len(buf) > MAX_BUFFER:
                    del buf[:-FRAME_LEN]
            except Exception as e:
                log.warning(f"TF03 serial error on {self.port}: {e}; retrying in 2s")
                if self._serial is not None:
                    try:
                        self._serial.close()
                    except Exception:
                        pass
                    self._serial = None
                buf.clear()
                self._stop.wait(2.0)
