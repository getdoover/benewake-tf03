"""A minimal Modbus simulator for a Benewake TF03 LiDAR.

Exposes the two registers the app reads:
    holding register 0x0000 -> distance in cm
    holding register 0x0001 -> signal strength

The distance slowly oscillates so you can see the dashboard move. Run it as a
TCP Modbus server and point the app's modbus_config at it (bus_type: tcp).
"""

import asyncio
import logging
import os

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.server import StartAsyncTcpServer

log = logging.getLogger()

REG_DISTANCE = 0x0000
REG_STRENGTH = 0x0001


class TF03Sim:
    def __init__(self, host: str, port: int, min_cm: int, max_cm: int):
        self.host = host
        self.port = port
        self.min_cm = min_cm
        self.max_cm = max_cm
        self.current_cm = min_cm
        self.step = max(1, (max_cm - min_cm) // 100)
        self.context: ModbusServerContext | None = None
        self.slave: ModbusSlaveContext | None = None

    async def start_server(self):
        self.slave = ModbusSlaveContext(
            hr=ModbusSequentialDataBlock(0x00, [0] * 16),
        )
        self.context = ModbusServerContext(slaves=self.slave, single=True)
        return await StartAsyncTcpServer(
            context=self.context,
            address=(self.host, self.port),
            framer="socket",
        )

    def tick(self):
        self.current_cm += self.step
        if self.current_cm > self.max_cm:
            self.current_cm = self.min_cm

        # Healthy signal strength well above the 40 threshold.
        self.slave.setValues(0x03, REG_DISTANCE, [int(self.current_cm)])
        self.slave.setValues(0x03, REG_STRENGTH, [350])
        log.info(f"TF03 sim: distance={self.current_cm} cm")

    async def run(self):
        asyncio.create_task(self.start_server())
        await asyncio.sleep(1)
        while True:
            self.tick()
            await asyncio.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG if os.environ.get("DEBUG") == "1" else logging.INFO
    )
    sim = TF03Sim(
        os.environ.get("MODBUS_HOST", "0.0.0.0"),
        int(os.environ.get("MODBUS_PORT", 5020)),
        int(os.environ.get("MIN_CM", 100)),     # 1 m
        int(os.environ.get("MAX_CM", 5000)),    # 50 m
    )
    asyncio.run(sim.run())
