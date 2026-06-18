"""A minimal native-serial simulator for a Benewake TF03 LiDAR.

Streams the TF03's 9-byte "standard output" frames over a TCP socket so the app
can read them in serial mode via a pyserial ``socket://host:port`` URL, with no
real hardware. The distance slowly oscillates so the dashboard moves.

Frame (little-endian distance & strength)::

    0x59 0x59 Dist_L Dist_H Str_L Str_H 0x00 0x00 Checksum
"""

import asyncio
import logging
import os

log = logging.getLogger()

FRAME_HEADER = 0x59


def build_frame(distance_cm: int, strength: int) -> bytes:
    body = bytes(
        [
            FRAME_HEADER,
            FRAME_HEADER,
            distance_cm & 0xFF,
            (distance_cm >> 8) & 0xFF,
            strength & 0xFF,
            (strength >> 8) & 0xFF,
            0x00,
            0x00,
        ]
    )
    return body + bytes([sum(body) & 0xFF])


class TF03SerialSim:
    def __init__(self, host: str, port: int, min_cm: int, max_cm: int, hz: float):
        self.host = host
        self.port = port
        self.min_cm = min_cm
        self.max_cm = max_cm
        self.period = 1.0 / hz
        self.current_cm = min_cm
        self.step = max(1, (max_cm - min_cm) // 100)

    def tick(self) -> int:
        self.current_cm += self.step
        if self.current_cm > self.max_cm:
            self.current_cm = self.min_cm
        return self.current_cm

    async def handle_client(self, reader, writer):
        peer = writer.get_extra_info("peername")
        log.info(f"TF03 serial sim: client connected {peer}")
        try:
            while True:
                distance_cm = self.tick()
                writer.write(build_frame(distance_cm, 350))
                await writer.drain()
                await asyncio.sleep(self.period)
        except (ConnectionResetError, BrokenPipeError):
            log.info("TF03 serial sim: client disconnected")
        finally:
            writer.close()

    async def run(self):
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        log.info(f"TF03 serial sim streaming on {self.host}:{self.port}")
        async with server:
            await server.serve_forever()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG if os.environ.get("DEBUG") == "1" else logging.INFO
    )
    sim = TF03SerialSim(
        os.environ.get("SERIAL_HOST", "0.0.0.0"),
        int(os.environ.get("SERIAL_PORT", 9600)),
        int(os.environ.get("MIN_CM", 100)),  # 1 m
        int(os.environ.get("MAX_CM", 5000)),  # 50 m
        float(os.environ.get("HZ", 10)),
    )
    asyncio.run(sim.run())
