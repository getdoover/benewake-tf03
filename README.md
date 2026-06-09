# Benewake TF03 LiDAR (RS485)

A Doover device app that reads distance from a **Benewake TF03-100 RS485** long-range
LiDAR over Modbus-RTU and publishes it as a tag (`distance_m`) and on the device
dashboard.

The app talks to the sensor through the shared `modbus_interface` app, so the TF03
can share an RS485 bus with other Modbus devices on the same device.

---

## What it does

- Reads **distance** (register `0x0000`, in cm) and **signal strength**
  (register `0x0001`) from the TF03 over Modbus function code `0x03`.
- Converts the distance to metres, applies an optional calibration offset, and
  publishes it as the tag **`distance_m`**.
- Flags readings as unreliable when the signal strength is below the configured
  threshold or the target is out of range, and blanks the displayed distance.
- Shows the live distance, raw cm reading, signal strength, and a "time since last
  read" on the dashboard, with warnings for lost comms / weak signal.

### Tags published

| Tag | Meaning |
|-----|---------|
| `distance_m` | Distance in metres (`null` when the reading is unreliable) |
| `distance_raw_cm` | Raw distance straight from the sensor, in cm |
| `signal_strength` | Signal strength (0–3500); below ~40 is unreliable |
| `reading_reliable` | `true`/`false` quality flag |

---

## Wiring (TF03-100 RS485 version)

New-version TF03 (Aug 2020 onward) 6-wire harness:

| Wire colour | Pin | Connect to |
|-------------|-----|------------|
| Red | VCC | 5–24 V supply |
| Green | RS485-A | RS485 A / D+ |
| White | RS485-B | RS485 B / D− |
| Black | GND | Ground |
| Blue / Brown | UART (debug) | Leave unused for RS485 |

> The TF03 RS485 interface is half-duplex; do **not** exceed 115200 baud.
> Serial parameters: **115200 baud, 8 data bits, 1 stop bit, no parity.**

---

## ⚠️ One-time setup: enable Modbus on the sensor

The TF03 ships with **Modbus disabled** — out of the box it continuously streams
its native `0x59 0x59 …` serial frames instead of answering Modbus requests. You
must enable Modbus once (it is saved to flash, so it persists across power cycles).

Easiest options:

1. **Benewake configuration software** (TF03 RS485 GUI tool) — connect the sensor
   via a USB-to-RS485 adapter and switch the protocol to *Modbus*.
2. **Send the enable command** over the serial port at 115200 8N1, then save +
   restart:

   ```
   Enable Modbus:   5A 05 6F 00 CE        (or 5A 05 15 01 75 to enable + save + restart)
   Save settings:   5A 04 11 6F
   Restart:         5A 04 02 60
   ```

   After restart the sensor responds to Modbus. Quick check — a "read distance"
   request to slave address 1:

   ```
   TX:  01 03 00 00 00 01 84 0A
   RX:  01 03 02 <DIST_H> <DIST_L> <CRC_L> <CRC_H>     (distance in cm)
   ```

The default Modbus slave address is **1** (configurable 1–247).

---

## Configuration

| Field | Default | Notes |
|-------|---------|-------|
| Sensor Name | `TF03 LiDAR` | Dashboard display name |
| Modbus Address | `1` | TF03 slave address (1–247) |
| Mounting Offset (m) | `0.0` | Added to the raw distance for calibration |
| Minimum Signal Strength | `40` | Below this, readings are flagged unreliable |
| Maximum Valid Distance (m) | `100.0` | Above this is treated as no-target / over-range |
| Modbus Config | serial, `/dev/ttyS0`, **115200** 8N1 | The RS485 bus the sensor is on |

Set **Modbus Config → Serial Port** to the adapter on your device (e.g.
`/dev/ttySC0`, `/dev/ttyUSB0`) and keep the baud at **115200** for the TF03.

---

## Local testing (no hardware)

A Modbus-TCP simulator is included that mimics the two TF03 registers with a
slowly oscillating distance:

```bash
doover app run          # builds & runs the app + simulator via docker compose
```

The sample `simulators/app_config.json` points the app at the simulator over TCP
(`127.0.0.1:5020`). For a real device, switch `modbus_config.bus_type` back to
`serial` and set the serial port.

```bash
doover app test         # run import / config tests
doover app lint --fix   # lint & format
```

---

## Reference

Protocol details are from the *TF03 RS485/RS232 Product Manual V1.3.2* (Benewake).
Distance is reported in **cm**; signal strength ranges 0–3500 with a reliability
threshold of 40. When the signal is weak or the target is out of range the sensor
returns its over-range threshold value (default 18000 cm).
