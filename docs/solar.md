# Solar for the terrasse node — design notes

> **Panel and charger ordered 2026-09-08; nothing is built.** This is the
> design and the parts list, not a commissioning record. Every current figure it
> rests on is an estimate; see
> [Before you build any of this](#before-you-build-any-of-this) at the bottom.
> When it *is* built, the record goes in
> [`commissioning.md`](commissioning.md), not here.

## Why bother

The node's estimated average draw is **~3.3 mA** ([base-platform.md](base-platform.md#where-the-battery-actually-goes)),
which is:

| | |
| --- | --- |
| per day | ~79 mAh ≈ **0.3 Wh** |
| on the 2000 mAh cell | **~25 days** |

Twenty-five days is not a crisis, so the case for solar is not runtime. It is
that **the box never has to be opened again**. The outdoor board has already
lost its USB port once, and every recharge is another cycle on a connector that
lives in the rain inside an enclosure whose whole shape is an argument about
keeping water out. A node that tops itself up is a node whose lid stays shut.

## The panel, and what it forces

[Waveshare 18 V / 10 W polysilicon](https://www.berrybase.de/waveshare-polysilizium-solarpanel-18v-10w-36-zellen-340x232x17-mm-20-umwandlungseffizienz-ip67),
€11.50:

| | |
| --- | --- |
| Vmp / Imp | 17.6 V / 0.57 A |
| Voc / Isc | 21.6 V / 0.61 A |
| Size, weight | 340 × 232 × 17 mm, 935 g |
| Sealing, lead | IP67, 90 cm to a 3.5 × 1.35 mm DC plug |

10 W is roughly thirty times what the node needs, and that is the point. The
sizing case for a solar node in Germany is not the annual average, it is the
worst week in December. At ~1 peak-sun-hour a day and 70 % system efficiency
this panel returns ~7 Wh/day against a 0.3 Wh/day demand — a margin of about
23×, which means the buffer never gets drawn down and the question stops being
interesting. A 2 W panel would also work, carried by the cell through the dark
weeks; this one removes the need to think about it.

Two consequences follow from picking 18 V, and both are load-bearing:

- **It rules out every linear charger**, including the XIAO's own. See below.
- **It rules out the panel touching the box.** 935 g and 0.08 m² of sail area
  cannot hang off an enclosure that is suspended on a cord and whose purpose is
  weighing birds to the gram. Wind load and cable tension both tilt the box,
  and the bending beam measures what hangs below it *through* that tilt. The
  panel gets its own mount — wall, railing, post — and the cable reaches the
  box with a slack loop and no tension.

## Charger: CN3791, and why not the obvious modules

Do **not** feed the panel into the XIAO's `5V` pad. The onboard charger is a
small linear part (ETA4054-class, ~370 mA) with no input-voltage regulation: on
a current-limited source it pulls until the panel collapses, browns out, and
retries. The 21.6 V open-circuit is far outside what that pad tolerates in any
case.

The obvious shelf answer is an integrated module — Waveshare's
[Solar Power Management Module 6–24 V](https://www.berrybase.de/en/solar-power-management-modul-fuer-6v-24v-solar-panel)
(€8.80) or [Solar Power Manager D](https://www.berrybase.de/en/waveshare-solar-power-manager-modul-d-5v-3a-usb-c-fuer-6v-24v-solarpanels-ohne-batteriehalter).
**Both are disqualified by their own datasheets: quiescent current <2 mA.**
That is 60 % of the node's entire budget — the regulator would idle away more
than the node spends measuring, and it would do it all night. They also carry a
permanent 5 V boost stage this node has no use for.

A bare **CN3791** instead — a buck-topology MPPT charger, whose relevant
numbers are:

| | |
| --- | --- |
| Input | 4.5–28 V (abs. max on `VCC` 30 V) |
| Sleep drain from the cell | **≤15 µA** (`IBAT2`), i.e. 0.5 % of budget |
| Charge current | `120 mV / RCS` |
| MPPT | external divider, pin regulated to 1.205 V |
| Output | 4.2 V ±1 % |

Specifically the **Soldered MPPT Li-Ion CN3791 charger board** (SKU 333136,
€12.95), and not one of the €5 generic modules. It costs more and it is worth
it, because the hardware is open: schematic, BOM and KiCad files are
[on GitHub](https://github.com/SolderedElectronics/MPPT-Li-Ion-CN3791-charger-board-hardware-design),
which is the only reason any of the following is knowable rather than assumed.

Its listed range is "6–18 V", which describes the **MPPT adjustment range, not
the voltage rating** — the parts are comfortable well past this panel's 21.6 V
Voc (~23.5 V on a cold clear day). Read off the V1.2.1 BOM:

| Ref | Part | Rating |
| --- | --- | --- |
| C3 | VKMD…1H221 electrolytic | 220 µF / 50 V |
| D3 | **AOD4185** P-channel MOSFET | −40 V, Vgs ±25 V |
| D4 | RBR5LAM30A Schottky | 30 V / 5 A |
| U1 | CN3791 | 28 V operating, 30 V absolute |

Nothing on the board is marginal against this panel. On a no-name module none
of that is documented, and the input capacitor is the part most likely to have
been chosen at 25 V.

### The one change that is not optional

**`R8` must be replaced with 1.2 Ω** (1 %, ≥0.25 W).

The board ships `R8 = 40 mΩ`, which by `120 mV / RCS` is a **3 A charge
current** — 1.5 C into a 2000 mAh cell, and roughly thirty times what this node
can use. At 1.2 Ω it becomes **100 mA ≈ C/20**.

That single resistor is also what answers the cold-charging problem. A LiPo must
not be charged below 0 °C — lithium plating, permanent capacity loss, and on a
German terrace that is four months of the year rather than an edge case. But
plating is strongly rate-dependent: [Battery University](https://www.batteryuniversity.com/article/bu-410-charging-at-high-and-low-temperatures/)
puts the permitted rate at −30 °C at 0.02 C, so C/20 sits in the reduced-rate
regime that temperature-aware chargers aim for, not in the fast-charge danger
zone. And 100 mA is still ample: the 79 mAh daily budget is covered in **48
minutes** of charging.

`R8` is a **1210** part — large, and reworkable with an ordinary iron.

### Two jumpers to set while it is open

**`K2` — set the MPPT point to 18 V.** `R5` = 300 k is the fixed upper leg and
the 4×2 header selects the lower one from `R3` = 30 k, `R4` = 62 k, `R6` =
130 k, `R7` = 75 k. With the pin regulated to 1.205 V, `V = 1.205 × (300k +
Rb)/Rb`:

| Bridge | Rb | Setpoint |
| --- | --- | --- |
| R7 | 75 k | 6.0 V |
| R6 ∥ R7 | 47.6 k | 8.8 V ≈ 9 V |
| R4 ∥ R7 | 33.9 k | 11.9 V ≈ 12 V |
| **R3 ∥ R7** | **21.4 k** | **18.1 V** ← this panel |

At C/20 the panel is never loaded near its maximum power point anyway, so this
is correctness rather than yield. It is still the setting to use, and it is
something the fixed-variant generic modules cannot do at all.

**`JP1` — cut the power LED.** It is a designed-in jumper for exactly that.

The status LEDs `D1`/`D2` can stay: per the schematic they hang off `VCC`, the
**panel** side, so they cost harvest in sunshine and nothing from the cell at
night. This is the one place where the usual "desolder every LED on a cheap
module" advice does not apply — but it would have, had the board pulled them
from the battery rail.

### Why there is no NTC

The CN3791 has ten pins — `VG`, `GND`, `CHRG`, `DONE`, `COM`, `MPPT`, `BAT`,
`CSP`, `VCC`, `DRV` — and **no `TEMP` pin and no `CE` pin**. Its smaller sibling
the CN3065 does have battery temperature monitoring, but tops out at 6.5 V input
and so cannot see an 18 V panel at all. Choosing this panel means the cold-charge
question is answered by the charge current (above), optionally backed by
firmware (below), and not by the charger IC.

## Does the cold actually bind?

It feels like it should. It mostly does not, for three reasons that stack.

**Charging only happens in daylight, and daylight is the warm part of the day.**
The panel makes nothing at night or at dawn, which is when it is coldest — those
hours cost nothing because they were never productive. Charging happens roughly
10:00–15:00, at the daily temperature maximum. So the case that actually blocks
a charge is an **Eistag** (Tmax < 0 °C), not a Frosttag (Tmin < 0 °C). Frost
nights are ordinary in Germany; ice days are not. Per DWD figures the count
swings hard by winter — Berlin had 4 in the mild 2006/07 and 43 in the severe
2009/10 — and is falling across the climate reference periods. Even a severe
winter leaves well over a hundred usable days in the winter half-year.

**One usable day covers about a week.** The requirement is not one charge window
per buffer length. Consumption is 79 mAh/day; one permitted day at 100 mA over
~5 usable daylight hours returns ~500 mAh, i.e. **six days of running**. So the
node needs roughly one charge day in seven, against a 25-day buffer that is
still there underneath as the second reserve.

**And at C/20 the sub-zero prohibition is not absolute anyway** — see `R8`
above. The rate is what makes cold charging dangerous, and the rate has already
been dealt with.

If a backstop is still wanted, the firmware inhibit below should trip at
**−5 °C, not 0 °C**. It then fires on a handful of days a winter instead of
every frost day, and costs essentially no harvest.

## Wiring

```
Panel (+) ─── DC coupler ─── [ CN3791 VIN+ ]            ┌── XIAO B+
Panel (−) ──────────────────[ CN3791 VIN− ]             │
                            [ CN3791 BAT+ ]───── P+ ────┤
                            [ CN3791 GND  ]───── P− ────┴── XIAO GND
                                                  │
                                          protection board ── cell (B+/B−)
```

**The charger lands on `P+`/`P−`, not on the cell's own `B+`/`B−`.** The
protection board's overcharge FET sits in the `P−` path; wiring the charger to
the cell side puts it outside that protection entirely. `P−` is the same ground
the battery divider's foot already goes to — see
[wiring.md](wiring.md#battery-sense), which explains why
that matters for the divider too.

**The charger can go at either end**, which was not true of the first draft of
this page. The argument for keeping it indoors was that the long run should
carry the high voltage at low current — but once `R8` caps charging at 100 mA
there is no high-current side to protect: 5 m of 0.5 mm² is ~0.34 Ω there and
back, i.e. **34 mV** of drop. Put it wherever it fits, which is a question the
enclosure answers below and not an electrical one.

Nothing about the cell, the protection board or the divider changes.

## Parts

| # | Part | Spec | Source | ~Price |
| --- | --- | --- | --- | --- |
| 1 | Solar panel | Waveshare 18 V / 10 W, IP67, 3.5 × 1.35 mm DC plug | BerryBase | €11.50 |
| 2 | Charger | **Soldered MPPT Li-Ion CN3791**, SKU 333136, 54 × 38 mm | BerryBase | €12.95 |
| 3 | DC coupler | 3.5 × 1.35 mm socket with flying lead, mates with #1 | — | ~€2 |
| 4 | Extension | 2-core, ~0.5 mm², UV-resistant, length to suit the mount | — | ~€5 |
| 5 | Sense resistor | **1.2 Ω, 1 %, ≥0.25 W, 1210** — replaces `R8` | — | <€1 |
| 6 | Cable gland | M8 or PG7, with seal | — | ~€2 |
| 7 | Panel mount | bracket or clamp for 60–70° tilt, facing south | — | — |

Cell, protection board and divider are already on the node. **#1 and #2 were
ordered on 2026-09-08.**

## Mechanical

**The gland goes through the floor or a low side wall — never the roof.** The
enclosure is a cup opening downward precisely so that its only joint faces the
ground; [`models.py`](../models.py) states it as a requirement ("no seam and no
penetration in the roof"). A gland in the top would give up the one property the
whole shape exists to provide. Enter low, with a drip loop below the box.

**The board does not fit in the box as it stands.** The Soldered charger is
54 × 38 mm, and the terrasse enclosure has no spare volume at all: the interior
is 80 × 70 × 55, and [`models.py`](../models.py) records that a packing search
put the smallest interior taking the existing four parts at 76 × 66 × 52. There
was never room for a fifth. Two ways out, and the cable gland means
[`models.py`](../models.py) has to be re-run either way:

1. **Reprint a taller body.** One enclosure, one weatherproofing problem. The
   `wohnzimmer` box has already been through this.
2. **Put the charger in its own pod at the panel.** Now permitted by the wiring
   note above — but it is a second enclosure that has to survive the same rain,
   and the existing one is already solved.

The first is the cheaper mistake to make.

**Mount the panel at 60–70° from horizontal, facing south.** Steeper than the
summer optimum on purpose: the design case is December, and snow and leaves slide
off a steep panel instead of sitting on it.

## Optional: a firmware charge inhibit

If C/20 is not enough reassurance, the node is well placed to do better. The
SHT31-D already reports temperature, and on `terrasse` the pads **D3, D8 and
D10** are free ([wiring.md](wiring.md#which-pads-stay-free)). A high-side
P-channel switch in the panel line does it: AO3401A or similar (−30 V, since Voc
reaches ~23.5 V cold), gate divider 100 k/22 k against source because Vgs is
limited to ±12 V, driven by a 2N7002 from the GPIO.

**Bias the pulldown so the default is charging ON and the GPIO *inhibits*, not
the other way round.** A node whose firmware has hung and which therefore cannot
charge is the more expensive failure in January than some plating.

**Trip it at −5 °C, not 0 °C** — see
[Does the cold actually bind?](#does-the-cold-actually-bind) for why 0 °C throws
away charging days it does not need to.

## Consequences for the telemetry

Once a charger is attached, **`battery_voltage` stops being a state-of-charge
reading during daylight** — it reports the charge voltage, ~4.1–4.2 V, whatever
the cell actually holds. The meaningful sample is **shortly before sunrise**.
Rising week over week means the panel is carrying the node; falling means it is
not. Any Home Assistant template that treats the daytime value as charge state
will be wrong from the day this is fitted.

## Before you build any of this

- **The 3.3 mA is an estimate, not a measurement.** The whole sizing rests on
  it, and the only measured number underneath it is a 269 ms boot time. The two
  terms that would move it most are the load cell's bridge resistance (a 350 Ω
  cell triples that term) and the light-sleep floor. It settles the panel sizing
  and the radio question at once, and it does not need a bench meter — see
  [Measuring it with what you have](base-platform.md#measuring-it-with-what-you-have).
- **The battery divider has never been flashed to hardware.** `src/battery.rs`
  is committed and untested on the board. It is also the only instrument that
  can tell you whether any of this works, so it wants to be working *first*.
