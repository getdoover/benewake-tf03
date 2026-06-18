# Benewake TF03 LiDAR (RS485)

A Doover device app that reads distance from a **Benewake TF03-100 RS485** long-range
LiDAR and publishes it as a tag (`distance_m`) and on the device dashboard.

The app supports **two comms modes** (selectable in config):

- **`serial`** (default) — reads the TF03's **native RS485/UART streaming output**
  directly. This is the sensor's factory-default behaviour, so it works out of the
  box with **no sensor configuration required**.
- **`modbus`** — polls the sensor over **Modbus-RTU** via the shared
  `modbus_interface` app, so the TF03 can share an RS485 bus with other Modbus
  devices. Requires enabling Modbus on the sensor first (see below).

---

## What it does

- Reads **distance** (in cm) and **signal strength** from the TF03 and publishes
  the distance in metres (with an optional calibration offset) as the tag
  **`distance_m`**.
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

## Comms modes

### Serial (default) — native RS485 streaming

In its "standard output" mode the TF03 continuously transmits a 9-byte frame
(default 100 Hz) with no request needed:

```
0x59 0x59  Dist_L Dist_H  Str_L Str_H  0x00 0x00  Checksum
```

(distance & strength little-endian, checksum = low byte of the sum of the first 8
bytes). The app opens the serial port directly and decodes this stream — **nothing
needs to be configured on the sensor**.

Set **Comms Mode** to `serial`, then set **Serial Port** to the device the TF03 is
wired to (e.g. `/dev/ttyAMA0`, `/dev/ttyUSB0`) and keep **Serial Baud** at the
factory default of **115200** (8N1).

### Modbus — shared RS485 bus

Use this mode when the TF03 shares an RS485 bus with other Modbus devices. It reads
distance (register `0x0000`, cm) and signal strength (register `0x0001`) over Modbus
function code `0x03`, via the shared `modbus_interface` app.

> **One-time setup:** the TF03 ships with **Modbus disabled**. You must enable it
> once (saved to flash, so it persists). Either use the Benewake configuration tool,
> or send these over the serial port at 115200 8N1:
>
> ```
> Enable Modbus:   5A 05 6F 00 CE
> Save settings:   5A 04 11 6F
> Restart:         5A 04 02 60
> ```
>
> Quick check — read distance from slave address 1:
> ```
> TX:  01 03 00 00 00 01 84 0A
> RX:  01 03 02 <DIST_H> <DIST_L> <CRC_L> <CRC_H>     (distance in cm)
> ```

Set **Comms Mode** to `modbus`, the **Modbus Address** (default 1, range 1–247),
and the **Modbus Config** bus (serial port, **115200** 8N1).

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

## Configuration

| Field | Default | Notes |
|-------|---------|-------|
| Sensor Name | `TF03 LiDAR` | Dashboard display name |
| Comms Mode | `serial` | `serial` (native stream) or `modbus` (polled) |
| Serial Port | `/dev/ttyAMA0` | *(serial mode)* device the TF03 is wired to; a `socket://host:port` URL is also accepted |
| Serial Baud | `115200` | *(serial mode)* TF03 factory default |
| Modbus Address | `1` | *(modbus mode)* TF03 slave address (1–247) |
| Mounting Offset (m) | `0.0` | Added to the raw distance for calibration |
| Minimum Signal Strength | `40` | Below this, readings are flagged unreliable |
| Maximum Valid Distance (m) | `100.0` | Above this is treated as no-target / over-range |
| Modbus Config | serial, `/dev/ttyAMA0`, **115200** 8N1 | *(modbus mode)* the RS485 bus the sensor is on |

---

## Local testing (no hardware)

Two simulators are included:

- **Serial-stream simulator** (`simulators/serial_sample/`) streams the native
  9-byte frames over TCP. The default `simulators/app_config.json` runs the app in
  `serial` mode pointed at it via `serial_port: socket://127.0.0.1:9600`.
- **Modbus-TCP simulator** (`simulators/sample/`) mimics the two Modbus registers.
  To test modbus mode, set `comms_mode` to `modbus` in `app_config.json` and point
  `modbus_config` at it (`bus_type: tcp`, `tcp_uri: 127.0.0.1:5020`).

```bash
doover app run          # builds & runs the app + simulators via docker compose
doover app test         # run import / config / frame-parser tests
doover app lint --fix   # lint & format
```

---

## Reference

Protocol details are from the *TF03 Series User Manual* (Benewake): the native
serial "Data Frame" (9-byte `0x59 0x59 …`) and the "RS485 Modbus Protocol". Distance
is reported in **cm**; signal strength ranges 0–3500 with a reliability threshold of
40. When the signal is weak or the target is out of range the sensor returns an
over-range value (Modbus mode reports up to 18000 cm).
