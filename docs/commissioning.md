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

**Verified on hardware 2026-09-06:**

- **The cell is connected and the node runs on it.** With USB unplugged it
  keeps publishing, `battery_voltage` included, which is the only proof that
  matters — the divider sits on the rail the charger drives, so a reading near
  4.1 V with USB attached is indistinguishable from the 4.11 V measured above
  with no cell at all.
- **It charges.** 3.80 V before a short USB session, 3.93 V after.

### The socket is wired with the colours crossed, and that is correct

On this pigtail, **black goes to `B+` and red to `B−`.**

That looks wrong and is not. The JST-PH housing is keyed, so the cell's plug
mates one way only; what is *not* standardised is which contact of the housing
carries positive. This pigtail was made with the opposite convention from the
cell's plug, so matching the colours at the solder joints would have mated them
backwards. **Decide this by continuity and a voltmeter, never by wire colour** —
probe which socket contact reaches `B+`, then check the cell's plug puts red on
that contact.

### A reversed cell reads exactly like a broken divider

It was mated backwards the first time. Nothing was damaged and the cell stayed
cold, but the failure was thoroughly misleading and cost an evening:

1. The 1S protection board **latched off**. `P+`/`P−` collapsed to 1.2 V while
   the cell's own terminals still held 3.8 V.
2. The divider sits on the *protected* rail by design (see the module note in
   [`src/battery.rs`](../src/battery.rs)), so it measured that dead rail and
   reported **exactly 0 mV** — tripping the firmware's "no cell at all — check
   the divider is fitted" warning.
3. The board went on running the whole time, because it was on USB.

So the symptom was a firmware message naming the divider, on a node that was
otherwise healthy, with an intact divider. **0 mV does not distinguish "divider
open" from "protected rail dead."** The signature that separates them is
measuring the two rails against each other: **3.8 V at the cell, 1.2 V at
`P+`** can only be the protection board.

Recovery needed no soldering: plugging in USB applies the charger's voltage
across `P+`, which is the ordinary way to unlatch a DW01A-class board. It went
1.2 V → 4.1 V and has behaved since. The protection did its job — it shut off
instead of dying.

**Not done:**

- **Not calibrated.** `offset` is the factory default, so weight publishes as
  roughly -20 kg. Calibration is `tare` on an empty, mounted pan and then
  `scale_factor` against a known mass, both over the Home Assistant knobs, no
  reflash. It waits on the enclosure.

**Open question — the runtime config path is not fully trustworthy:**

`deep_sleep = 0` sat retained on the broker for days and **never took effect**:
the node kept its 2 s poll cycle throughout. `heartbeat_interval = 60`, set the
same way on the same path, clearly *did* — the publish cadence was ~78–90 s
instead of the ~14 minutes a 600 s heartbeat gives. Both are back to their
defaults now (`600` / `1`).

Worth understanding before relying on that path, because **`tare` and
`scale_factor` go through the same code** and the calibration above depends on
them landing.

**Four things that cost an evening, so that they do not cost another one:**

- **The tare baseline lives in RTC RAM** and is taken on the first boot after a
  power cycle. The beam has to be left completely alone for that boot. Taring
  while handling it captured a loaded state and left the node 38k ticks off —
  far outside the drift band and far below the threshold, so every poll landed
  in `Decision::Unexplained` and the baseline was, correctly, never absorbed.
  There is no way out of that except another power cycle.
- **A battery node's USB port enumerates only in flashes.** The earlier note
  here said it does not enumerate at all; that was wrong. It appears for a
  fraction of each 2 s poll cycle. Polling `/dev/ttyACM*` every **20 ms** and
  reading it passively catches whole log lines, including the heartbeat window
  where Wi-Fi comes up; polling every 200 ms mostly misses. Verified
  2026-09-06. Flashing still needs the boot window right after plugging in, or
  the BOOT/RESET hold, and `espflash monitor` is still the wrong tool — see
  [`FLASHING.md`](../FLASHING.md).
- **Never debug this node on USB with the cell disconnected.** Verified
  2026-09-09, after an evening spent on the wrong three theories. The LiPo is
  what buffers the radio's TX bursts; without it the board browns out and
  resets at the first transmission, and the failure is silent in the worst way:
  the serial log ends on `Wi-Fi modem sleep: max`, which `main.rs` prints
  immediately *before* `connect_async().await`. So output stops at the first RF
  current peak, the USB port vanishes, and the board reboots — with **no**
  `Connected to Wi-Fi` and, crucially, **no `connect to … failed (attempt N)`
  either**. Nothing is failing to join; it never gets that far. The SHT31-D
  fails the same way at the same time, logging the contradictory pair
  `no SHT31-D at 0x44 or 0x45` and `I²C scan: 0x44 answered`. Reattach the cell
  and both come back at once: 4.09 V, 24.5 °C, 38.9 %.

  Two hours went into the credentials before that. They were never the problem
  — the boot banner reads `wifi: 'wifi_42_ext' (built in)`, `.env` agrees, the
  network scans at signal 84 on 2.4 GHz, and nothing is stored in flash, so
  `clear` is a no-op. That banner is printed before the console window and is
  almost impossible to catch, since the C3 discards serial output no host is
  reading yet; it took five cold boots to see it once.
- **Discovery is announced once per *power cycle*, not per boot.**
  `FLAG_DISCOVERY` lives in RTC RAM, which survives deep sleep and even a
  reflash. After the retained `homeassistant/` topics were cleared by hand the
  node never re-announced, and its entities were simply missing while its
  readings kept arriving. Pulling power restored all nine. `state.rs` says it
  outright: *"to force a re-announce you have to pull power, not just flash and
  reset."*

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
- **Solar for `terrasse`: panel and charger ordered 2026-09-08**, nothing built.
  Waveshare 18 V / 10 W panel and a Soldered CN3791 MPPT board (SKU 333136).
  **The board charges at 3 A as shipped** — `R8` has to come off and be replaced
  with 1.2 Ω before it is ever connected to a cell. Parts list and reasoning in
  [`solar.md`](solar.md). It depends on the same missing measurement as the
  radio options, and on the battery divider actually having been flashed —
  that divider is the only instrument that can say whether the panel works.
- **The stored-credential fallback cannot fire on a battery node.**
  `wifi::FALLBACK_AFTER` is meant to set aside stored credentials after three
  consecutive refusals and fall back to the built-in pair, so a typo at the
  console cannot strand a board. But `refusals` in `main.rs` is a task-local,
  and its comment says it is deliberately *not* in RTC RAM: *"a power cycle
  should give them another try"*. That reasoning holds for a mains node. A
  battery node cold-boots every couple of seconds, so every wake is a new run
  with `refusals = 0` and the threshold of three is never reached. The
  protection is inert for precisely the node that hangs outdoors and cannot be
  reflashed casually. Not the cause of anything so far — nothing is stored on
  `terrasse` — but it is a trap set for later.
- **Mains nodes self-heat.** Measured 2026-09-04 on `schlafzimmer`: about 0.9 °C
  at the board, separated from room warming by using the unmoved SCD41 as a
  control. Mount temperature sensors away from the board on any node that
  reports one.
