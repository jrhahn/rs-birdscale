# Commissioning log

What is physically built, on which board, and what still has to happen to it.

The rest of `docs/` describes how the firmware is *meant* to work. This page
records the state of the actual hardware, which nothing in the code can tell
you: a node's slot being `Slot::on()` says a sensor is expected, not that one
is soldered on.

Keep it honest rather than complete. A stale entry here is worse than a missing
one, because it will be believed.

---

## Boards

Identified by the MAC in the USB serial descriptor, which is also what
`espflash board-info` reports. **Check it before flashing.** Two boards were
plugged in at once during the 2026-09-04 session and the wrong one got written;
the MAC is the only thing that distinguishes them, and reading it takes a
second.

| MAC | Node | Power | Address |
| --- | --- | --- | --- |
| `e0:72:a1:18:e2:c0` | `terrasse` | battery | 192.168.1.81 |
| `ac:27:6e:80:51:f8` | `wohnzimmer` | mains | — |
| `ac:27:6e:82:43:94` | `kueche` | mains | 192.168.1.30 |

`schlafzimmer` and `bad` predate this log; their boards have not been opened.

---

## `terrasse` — outdoor, battery

Replaced the node formerly called `draussen`. It carries the bird-feeder scale.

**Verified on hardware 2026-09-04:**

- **HX711** on `D0`/`D1`. Resting readings scatter about ±70 counts out of a
  ±8.4M range — a clean, low-noise chain. A press produced a real presence
  edge: `visit` is published only on the arrival path, so seeing it proves the
  threshold crossing fired and `watch_visit` ran through the press.
- **SHT31-D** at `0x44`, no prefix — it owns the plain `temperature` and
  `humidity` keys.
- **Battery divider** on `D2`, reading 4.11 V off the XIAO's charger with no
  cell fitted. That is the check worth doing before connecting a LiPo: it
  proves the divider is wired and scaled while nothing is at stake.

**Not done:**

- **The cell is not connected.** A connector is fitted on `B+`/`B-`. JST-PH
  polarity is not standardised between vendors, so measure the socket against
  the cell's plug before the first mate — the 1S protection board guards
  against over-discharge, over-charge and over-current, *not* against reverse
  polarity.
- **Not calibrated.** `offset` is the factory default, so weight publishes as
  roughly -20 kg. Calibration is `tare` on an empty, mounted pan and then
  `scale_factor` against a known mass, both over the Home Assistant knobs, no
  reflash. It waits on the enclosure.
- **`deep_sleep = 0` is still set retained on the broker.** Convenient for
  calibration — the node stays awake and answers immediately instead of on a
  ~14 minute cycle — but it must go back to `1` before the node runs on the
  cell, or the battery is flat within a day or two.

**Two things that cost an evening, so that they do not cost another one:**

- **The tare baseline lives in RTC RAM** and is taken on the first boot after a
  power cycle. The beam has to be left completely alone for that boot. Taring
  while handling it captured a loaded state and left the node 38k ticks off —
  far outside the drift band and far below the threshold, so every poll landed
  in `Decision::Unexplained` and the baseline was, correctly, never absorbed.
  There is no way out of that except another power cycle.
- **A battery node's USB port does not enumerate** while it polls: the wake
  window is shorter than enumeration takes. Flashing one needs the boot window
  right after plugging in, or the BOOT/RESET hold. Its serial log is not a
  reliable witness either — see the `espflash monitor` warning in
  [`FLASHING.md`](../FLASHING.md).

---

## `wohnzimmer` — mains

**Verified on hardware 2026-09-05**, all three sensors and both buses:

- **SHT31-D** at `0x44`.
- **SDS011** on `D3`/`D10`, crossed correctly. Both raw and humidity-corrected
  values arrive, and the correction is visibly doing something — the corrected
  figures sit below the raw ones, which is what the κ term should do at that
  humidity. It needs the SHT31 on the same board, which is the whole reason the
  particulate sensor lives here rather than in the kitchen.
- **SCD41** at `0x62` — verified with a unit **borrowed from
  `schlafzimmer`, which has since gone back**. The slot stays on: the fleet
  plan says this node has one, there simply is no second unit yet. Its three
  entities read unavailable in Home Assistant until one arrives.

**When assembling:** keep the SHT31-D away from the board. On this node that
matters twice over, because the particulate humidity correction reads *its*
humidity — a board-warmed SHT31 reports a relative humidity that is too low, the
correction then subtracts too little, and the error lands in the PM figures.

The SDS011's fan needs a clear air path. Its 15-minute cadence protects the fan
and the optics; a sealed enclosure would have it measuring the enclosure.

---

## `kueche` — mains

SHT31-D only, verified 2026-09-04. Nothing outstanding.

---

## Open across the fleet

- **Nothing has had its current measured.** Every battery figure in
  [`base-platform.md`](base-platform.md) is estimated from datasheets around a
  single measured number (a 269 ms boot). Both radio options recorded there stay
  parked behind that measurement, including the cheap one.
- **Mains nodes self-heat.** Measured 2026-09-04 on `schlafzimmer`: about 0.9 °C
  at the board, separated from room warming by using the unmoved SCD41 as a
  control. Mount temperature sensors away from the board on any node that
  reports one.
