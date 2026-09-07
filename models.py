import cadquery as cq
from cadquery import exporters
from pathlib import Path
import math
import re


path_save = Path("cad-models")
path_save.mkdir(exist_ok=True)

try:  # provided by CQ-editor / jupyter-cadquery; a no-op when run as a script
    display
except NameError:

    def display(*_args, **_kwargs):
        pass


## ===========================================================================
## Terrasse — outdoor housing for the bird-scale node
## ===========================================================================
##
## Two printed parts:
##
##   terrasse_body   walls + closed top. Open at the BOTTOM.
##   terrasse_floor  bottom plate. Carries the bending-beam anchor.
##
## The four requirements, and how each is met:
##
##   a) waterproof from above  There is no seam and no penetration in the roof.
##      The top is one integral wall, and the only joint faces down, where
##      water cannot climb to it. The top 5 mm flare out 2 mm past the walls
##      as an eave, so water crossing the roof leaves the box clear of the
##      side walls instead of running down them.
##   b) cord attachment        Two ears at roof level, outboard of the walls.
##      One cord through both makes a bail: it hangs level and pierces
##      nothing. Load path is ear -> wall -> floor -> anchor, in line.
##   c) beam anchor            A pad on the underside of the floor, matching
##      the bending-beam clamp (25 x 12 face, two screws 15 mm apart), with
##      captive nuts reachable from inside the box.
##   d) ventilation            A chamber against the -Y wall, walled off from
##      the electronics so the board's own heat does not reach the SHT31.
##      Air enters through slots in the floor and leaves through downward-
##      tilted slots high in the side wall -> a chimney. Both openings face
##      down or outward-down; neither admits falling or driving rain.
##
## Print the body with the ROOF ON THE BUILD PLATE (opening up). Every
## feature is then either vertical or steps inward, so nothing needs support
## and the roof gets the smooth plate-side surface. Print the floor with the
## anchor pad on the plate, which leaves the nut pockets opening upward.

# --- envelope, as specified -----------------------------------------------
ENV_X, ENV_Y, ENV_Z = 50.0, 60.0, 50.0   # length, width, height

WALL = 2.0        # side and roof wall
FLOOR_T = 3.0     # floor plate
EAVE = 2.0        # how far the drip edge stands proud of the wall
EAVE_H = 5.0      # height of the drip-edge band

BODY_X = ENV_X - 2 * EAVE        # 46, wall outside
BODY_Y = ENV_Y - 2 * EAVE        # 56
IN_X = BODY_X - 2 * WALL         # 42, usable inside
IN_Y = BODY_Y - 2 * WALL         # 52
Z_FLOOR = FLOOR_T                # 3,  interior floor
Z_CEIL = ENV_Z - WALL            # 48, interior ceiling

# --- hanging ears ---------------------------------------------------------
# A rounded tab rather than a rectangle: the eye is a circle anyway, and a
# square corner on a part that hangs at eye level looks unfinished.
EAR_NECK = 4.5                   # straight part, wall to eye centre
EAR_W = 11.0
EAR_R = 5.5                      # radius of the eye end
EAR_HOLE = 4.0                   # 3 mm cord knots through comfortably

CORNER_R = 3.0                   # vertical corners, both housings
TOP_BREAK = 1.5                  # how much the top edge is taken off

# --- vent chamber, in the -X/-Y corner ------------------------------------
# It used to span the middle of the -Y wall, which left the longest clear run
# in the box at 38 mm. A 103450 cell needs 50, and Y (52 mm) is the only axis
# that has it -- so the chamber moved into a corner and gave the run back.
CH_X, CH_Y = 17.0, 16.0
BAFFLE = 2.0
CH_X0 = -IN_X / 2                # -21, against the -X wall
CH_Y0 = -IN_Y / 2                # -26, against the -Y wall
# The corner post lands inside the cavity and is unioned back in afterwards,
# so the chamber is L-shaped. That is deliberate: a post in the box corner
# fuses into both outer walls, which is where it belongs, and the L still
# holds the sensor card with room to spare.

VENT_H = 2.5                     # outlet slots, both walls
VENT_Y_W = 7.0                   # -Y wall, clear of the corner post
VENT_X_W = 6.0                   # -X wall, likewise
VENT_Z = [32.0, 36.0, 40.0]
VENT_TILT = 30.0                 # degrees, sloping down and outward

# --- floor-to-body screws (M3) --------------------------------------------
BOSS_D, BOSS_PILOT, BOSS_H = 8.0, 2.5, 14.0
BOSS_XY = [(sx * (IN_X / 2 - BOSS_D / 2), sy * (IN_Y / 2 - BOSS_D / 2))
           for sx in (-1, 1) for sy in (-1, 1)]
SCREW_CLEAR, SCREW_CSK = 3.4, 6.6

# --- bending-beam anchor (M4) ---------------------------------------------
# Interface to the bending-beam clamp. The clamp's own model lived in this
# file until it was retired -- `git show d0df819:models.py` still has it. The
# mating dimensions stay here, because the anchor is meaningless without them.
ANCHOR_PITCH = 15.0              # clamp screw pitch
ANCHOR_HOLE = 4.3
NUT_AF, NUT_T = 7.2, 3.4         # M4 nut across flats, thickness
PAD_X, PAD_Y, PAD_H = 27.0, 14.0, 3.5
FLANGE_X, FLANGE_Y, FLANGE_H = 33.0, 18.0, 2.5
NUT_BOSS_H = 5.0                 # boss inside the box carrying the nuts

CABLE_D, CABLE_XY = 6.0, (-8.0, 15.0)   # load-cell cable, up through the floor
DRAIN_D, DRAIN_XY = 3.0, (-8.0, 22.0)   # condensate drain, main compartment

# --- battery: one 103450 cell (10 x 34 x 50) on edge, running in Y ---------
# Held by two cable ties rather than clamped between ribs. A pouch cell wants
# that: it swells a little as it ages, and a rigid pocket sized to a new one
# is a press fit on an old one.
CELL_T, CELL_L, CELL_H = 10.0, 50.0, 34.0
CELL_X = 6.0                     # lane centre; cell spans x = 1 .. 11
CELL_Z = FLOOR_T + NUT_BOSS_H    # 8, the cell rests on the nut boss
SUPPORT_Y = 21.0                 # end supports, level with that boss
TIE_Y = 15.0                     # cable-tie crossings
TIE_W, TIE_CH = 1.6, 1.5         # tie slot width, recess depth underneath


def _box(l, w, h, at=(0.0, 0.0, 0.0)):
    """Axis-aligned box, centred in X/Y, sitting on z=at[2]."""
    return (
        cq.Workplane("XY")
        .box(l, w, h, centered=(True, True, False))
        .translate(at)
    )


def _export(shape, stem):
    """Write <stem>.stl and <stem>.step, both reproducible.

    OpenCASCADE stamps the wall-clock time into the STEP header, so an
    unchanged model would show up as a diff on every run. The meshes are
    tracked, so that churn is not free -- pin the field instead.
    """
    exporters.export(shape, str(path_save / (stem + ".stl")))
    step = path_save / (stem + ".step")
    exporters.export(shape, str(step))
    step.write_text(
        re.sub(
            r"(FILE_NAME\('[^']*',')[^']*(')",
            r"\g<1>1970-01-01T00:00:00\g<2>",
            step.read_text(),
            count=1,
        )
    )


# ---------------------------------------------------------------------------
# Body
# ---------------------------------------------------------------------------
# Corners are rounded on the source boxes, before anything is cut into them:
# at that point `|Z` selects exactly the four vertical edges and nothing else.
body = _box(BODY_X, BODY_Y, ENV_Z - Z_FLOOR, (0, 0, Z_FLOOR)).edges("|Z").fillet(CORNER_R)
body = body.union(
    _box(ENV_X, ENV_Y, EAVE_H, (0, 0, ENV_Z - EAVE_H)).edges("|Z").fillet(CORNER_R)
)

# Hollow it out. The cavity reaches the bottom of the walls, so the box is
# open downward and the roof stays a single unbroken wall.
body = body.cut(_box(IN_X, IN_Y, Z_CEIL - Z_FLOOR, (0, 0, Z_FLOOR)))

# Hanging ears, flush with the eave band.
for sx in (-1, 1):
    eye = sx * (ENV_X / 2 + EAR_NECK)
    body = body.union(_box(EAR_NECK, EAR_W, EAVE_H,
                           (sx * (ENV_X / 2 + EAR_NECK / 2), 0, ENV_Z - EAVE_H)))
    body = body.union(
        cq.Workplane("XY").circle(EAR_R).extrude(EAVE_H)
        .translate((eye, 0, ENV_Z - EAVE_H))
    )
    body = body.cut(
        cq.Workplane("XY").circle(EAR_HOLE / 2).extrude(EAVE_H)
        .translate((eye, 0, ENV_Z - EAVE_H))
    )

# Vent chamber: add the corner block, then hollow it out. Two baffles, on the
# +X and +Y sides; the outer walls close the other two.
body = body.union(
    _box(CH_X + BAFFLE, CH_Y + BAFFLE, Z_CEIL - Z_FLOOR,
         (CH_X0 + (CH_X + BAFFLE) / 2, CH_Y0 + (CH_Y + BAFFLE) / 2, Z_FLOOR))
)
body = body.cut(
    _box(CH_X, CH_Y, Z_CEIL - Z_FLOOR,
         (CH_X0 + CH_X / 2, CH_Y0 + CH_Y / 2, Z_FLOOR))
)

# Cable pass-through in the +Y baffle, for the SHT31's flying lead. Seal it
# with a dab of silicone on assembly: it is the one path from the chamber into
# the electronics volume, and it is there for the wire, not for air.
body = body.cut(
    _box(6.0, 3 * BAFFLE, 4.0, (CH_X0 + 9.0, CH_Y0 + CH_Y + BAFFLE / 2, 42.0))
)

# Outlet slots, tilted down and outward so nothing runs in. Two walls now,
# each in the stretch the corner post does not stand behind.
for z in VENT_Z:
    body = body.cut(
        cq.Workplane("XY").box(VENT_Y_W, 12.0, VENT_H)
        .rotate((0, 0, 0), (1, 0, 0), VENT_TILT)
        .translate((CH_X0 + 12.5, -BODY_Y / 2 + WALL / 2, z))
    )
    body = body.cut(
        cq.Workplane("XY").box(12.0, VENT_X_W, VENT_H)
        .rotate((0, 0, 0), (0, 1, 0), -VENT_TILT)
        .translate((-BODY_X / 2 + WALL / 2, CH_Y0 + 12.0, z))
    )

# Screw bosses for the floor.
for (px, py) in BOSS_XY:
    body = body.union(_box(BOSS_D, BOSS_D, BOSS_H, (px, py, Z_FLOOR)))
    body = body.cut(
        cq.Workplane("XY").circle(BOSS_PILOT / 2).extrude(BOSS_H)
        .translate((px, py, Z_FLOOR))
    )

# The roof edge gets a chamfer, not a round. This part prints roof-down, so
# that edge is the first layer: a fillet there starts as a knife edge with a
# horizontal tangent and each layer steps outward over air. A 45 degree break
# prints cleanly, softens the same edge, and leaves the eave's underside sharp,
# which is the edge that actually sheds the water.
body = body.faces(">Z").edges().chamfer(TOP_BREAK)

display(body)
_export(body, "terrasse_body")


# ---------------------------------------------------------------------------
# Floor
# ---------------------------------------------------------------------------
floor = _box(BODY_X, BODY_Y, FLOOR_T).edges("|Z").fillet(CORNER_R)

# Countersunk screw holes, heads on the underside. Done while the plate is
# still a plain box, so `<Z` is the plate face and not the anchor pad.
floor = (
    floor.faces("<Z").workplane()
    .pushPoints(BOSS_XY)
    .cskHole(SCREW_CLEAR, SCREW_CSK, 90)
)

# Beam anchor: flange, then the pad that meets the clamp.
floor = floor.union(_box(FLANGE_X, FLANGE_Y, FLANGE_H, (0, 0, -FLANGE_H)))
floor = floor.union(_box(PAD_X, PAD_Y, PAD_H, (0, 0, -FLANGE_H - PAD_H)))
# Boss inside the box, so the anchor screws run through 14 mm of material.
floor = floor.union(_box(PAD_X, PAD_Y, NUT_BOSS_H, (0, 0, FLOOR_T)))

anchor_pts = [(-ANCHOR_PITCH / 2, 0.0), (ANCHOR_PITCH / 2, 0.0)]
anchor_z0 = -FLANGE_H - PAD_H
for (px, py) in anchor_pts:
    floor = floor.cut(
        cq.Workplane("XY").circle(ANCHOR_HOLE / 2)
        .extrude(FLOOR_T + NUT_BOSS_H - anchor_z0)
        .translate((px, py, anchor_z0))
    )
    # Captive nut, dropped in from inside the box.
    floor = floor.cut(
        cq.Workplane("XY").polygon(6, NUT_AF / math.cos(math.radians(30)))
        .extrude(NUT_T)
        .translate((px, py, FLOOR_T + NUT_BOSS_H - NUT_T))
    )

# Load-cell cable, with a collar underneath that sheds water off the lead.
floor = floor.union(
    cq.Workplane("XY").circle(5.0).extrude(4.0)
    .translate((CABLE_XY[0], CABLE_XY[1], -4.0))
)
floor = floor.cut(
    cq.Workplane("XY").circle(CABLE_D / 2).extrude(FLOOR_T + 4.0)
    .translate((CABLE_XY[0], CABLE_XY[1], -4.0))
)

# Condensate drain for the electronics volume.
floor = floor.cut(
    cq.Workplane("XY").circle(DRAIN_D / 2).extrude(FLOOR_T)
    .translate((DRAIN_XY[0], DRAIN_XY[1], 0))
)

# Air inlet, in the leg of the L the sensor card does not stand in.
for sy in (-24.5, -21.5, -18.5):
    floor = floor.cut(_box(8.0, 2.0, FLOOR_T, (CH_X0 + 12.5, sy, 0)))

# Card slot for the SHT31 breakout, standing on edge across the chamber's
# other leg. Held clear of the outer wall: it belongs to the floor, the wall
# to the body, and they have to come apart.
floor = floor.union(_box(16.0, 6.0, 6.0, (CH_X0 + 9.0, CH_Y0 + 12.0, FLOOR_T)))
floor = floor.cut(_box(20.0, 2.0, 5.0, (CH_X0 + 9.0, CH_Y0 + 12.0, FLOOR_T + 1.5)))

# Battery lane. Two end supports bring the cell up level with the nut boss,
# so it rests on three points along its 50 mm and clears the floor -- which
# is where condensate and the drain are.
for sy in (-1, 1):
    floor = floor.union(_box(12.0, 3.0, NUT_BOSS_H,
                             (CELL_X, sy * SUPPORT_Y, FLOOR_T)))
# Cable ties: up one slot, over the cell, down the other, and back through a
# recess in the underside so the box still sits flat.
for sy in (-1, 1):
    floor = floor.cut(_box(17.0, 6.0, TIE_CH, (CELL_X + 0.5, sy * TIE_Y, 0)))
    for tx in (CELL_X - 6.5, CELL_X + 6.3):
        floor = floor.cut(_box(TIE_W, 5.0, FLOOR_T, (tx, sy * TIE_Y, 0)))

display(floor)
_export(floor, "terrasse_floor")

print("terrasse body  %.1f cm3   bbox %s" % (
    body.val().Volume() / 1000.0, body.val().BoundingBox()))
print("terrasse floor %.1f cm3   bbox %s" % (
    floor.val().Volume() / 1000.0, floor.val().BoundingBox()))


## ===========================================================================
## Wohnzimmer — indoor housing for the air-quality node
## ===========================================================================
##
## Two printed parts:
##
##   wohnzimmer_tray   floor, walls and the three compartments
##   wohnzimmer_lid    flat cover, four screws
##
## Indoors, so nothing here is about rain. The shape is driven by two
## constraints the commissioning notes already state:
##
##   "keep the SHT31-D away from the board [...] a board-warmed SHT31 reports
##    a relative humidity that is too low, the correction then subtracts too
##    little, and the error lands in the PM figures"
##   "a sealed enclosure would have it measuring the enclosure"
##
## Hence three compartments in a row, divided by full-height baffles that also
## carry the wz_lid across its span:
##
##   -X  sensor chamber   SHT31 + SCD41, vented on three sides, ~90 mm of
##                        still air away from the board. Both sensors here
##                        want room air and neither runs a fan.
##       SDS011 bay       a pocket the module drops into. Its intake is tubed
##                        to a stub in the +Y wall so it draws room air, not
##                        its own exhaust; the exhaust leaves through the -Y
##                        wall, 84 mm away on the far side of the module.
##   +X  board bay        a fitted pocket, cable out through the +X wall.
##
## A 10 mm service strip runs along +Y past the SDS011 for the intake tube and
## for the sensor wiring, which has to cross the bay to reach the board. The
## baffles are notched at floor level to let it through.
##
## Print both parts flat on the plate, wz_tray floor down. Slots are vertical
## cuts in vertical walls, so only their tops bridge -- no support needed.

WZ_X, WZ_Y, WZ_Z = 145.0, 89.0, 32.0
WZ_WALL = 2.5
WZ_FLOOR = 3.0
WZ_LID = 3.0

WZ_IN_X = WZ_X - 2 * WZ_WALL      # 140
WZ_IN_Y = WZ_Y - 2 * WZ_WALL      # 84
WZ_IN_H = WZ_Z - WZ_FLOOR - WZ_LID  # 26
WZ_TOP = WZ_FLOOR + WZ_IN_H       # 29, where the wz_lid lands

WZ_BAF = 2.0

# Component envelopes. Measured values go here; everything else follows.
SDS_XY = 73.5                     # 71 x 70 module, pocket kept SQUARE so it
                                  # can be turned to any of four orientations
                                  # -- which edge carries the intake nozzle
                                  # differs between units, and the tube has to
                                  # reach the stub.
SDS_SERVICE = 10.0                # strip along +Y for tube and wiring
SENS_X = 18.0                     # sensor chamber depth
BOARD_X, BOARD_Y = 34.0, 56.0     # 33 x 55 board plus clearance
BOARD_RIB = 8.0                   # pocket rib height

# Compartment boundaries in X, left to right.
WZ_X0 = -WZ_IN_X / 2              # -70
SENS_X1 = WZ_X0 + SENS_X          # -52
SDS_X0 = SENS_X1 + WZ_BAF         # -50
SDS_X1 = SDS_X0 + SDS_XY          # 23.5
BOARD_X0 = SDS_X1 + WZ_BAF        # 25.5

WZ_Y1 = WZ_IN_Y / 2               # 42
SDS_RIB_Y = WZ_Y1 - SDS_SERVICE - WZ_BAF   # 30, module stops here

WZ_POST = 8.0
WZ_PILOT, WZ_CLEAR, WZ_CSK = 2.5, 3.4, 6.6
WZ_POST_XY = [(sx * (WZ_IN_X / 2 - WZ_POST / 2), sy * (WZ_IN_Y / 2 - WZ_POST / 2))
              for sx in (-1, 1) for sy in (-1, 1)]

INTAKE_OD, INTAKE_ID, INTAKE_L = 6.0, 4.0, 8.0   # stub mimics the SDS011 nozzle
SLOT_W = 2.5                                      # every vent slot


def _slots(shape, n, pitch, size, at, axis="z"):
    """Cut `n` slots of `size` (l, w, h), stepped by `pitch` along `axis`."""
    for i in range(n):
        d = (i - (n - 1) / 2) * pitch
        off = {"x": (d, 0, 0), "y": (0, d, 0), "z": (0, 0, d)}[axis]
        shape = shape.cut(_box(*size, tuple(a + b for a, b in zip(at, off))))
    return shape


# ---------------------------------------------------------------------------
# Tray
# ---------------------------------------------------------------------------
wz_tray = _box(WZ_X, WZ_Y, WZ_TOP).edges("|Z").fillet(CORNER_R)
wz_tray = wz_tray.cut(_box(WZ_IN_X, WZ_IN_Y, WZ_IN_H, (0, 0, WZ_FLOOR)))

# Baffles. Full height: they separate the three air volumes and they are what
# keeps a 145 mm wz_lid from sagging between its four corner screws.
for bx in (SENS_X1 + WZ_BAF / 2, SDS_X1 + WZ_BAF / 2):
    wz_tray = wz_tray.union(_box(WZ_BAF, WZ_IN_Y, WZ_IN_H, (bx, 0, WZ_FLOOR)))
    # Notch at floor level, inside the service strip, for the sensor wiring.
    wz_tray = wz_tray.cut(_box(3 * WZ_BAF, 8.0, 6.0, (bx, WZ_Y1 - SDS_SERVICE / 2, WZ_FLOOR)))

# Rib that stops the SDS011 short of the service strip.
wz_tray = wz_tray.union(_box(SDS_XY, WZ_BAF, 6.0,
                       ((SDS_X0 + SDS_X1) / 2, SDS_RIB_Y + WZ_BAF / 2, WZ_FLOOR)))

# Intake stub in the +Y wall: push a short silicone tube from the module's
# nozzle onto this, and the fan draws room air instead of the bay's own
# exhaust. Without it the sensor slowly re-measures what it just measured.
stub_c = ((SDS_X0 + SDS_X1) / 2, WZ_Y1 + WZ_WALL - INTAKE_L / 2, WZ_FLOOR + 9.0)
wz_tray = wz_tray.union(
    cq.Workplane("XZ").circle(INTAKE_OD / 2).extrude(INTAKE_L)
    .translate((stub_c[0], WZ_Y1 + WZ_WALL, stub_c[2]))
)
wz_tray = wz_tray.cut(
    cq.Workplane("XZ").circle(INTAKE_ID / 2).extrude(INTAKE_L + WZ_WALL + 2)
    .translate((stub_c[0], WZ_Y1 + WZ_WALL + 1, stub_c[2]))
)

# Exhaust, -Y wall, the full length of the bay and as far from the intake as
# the box allows.
for z in (8.0, 13.0, 18.0):
    wz_tray = _slots(wz_tray, 4, 17.0, (14.0, 3 * WZ_WALL, SLOT_W),
                  ((SDS_X0 + SDS_X1) / 2, -WZ_Y1, WZ_FLOOR + z), axis="x")

# Sensor chamber: vented on the -X end and both long walls, so it sees room
# air by convection alone. No fan reaches in here.
for z in (7.0, 12.0, 17.0):
    wz_tray = _slots(wz_tray, 2, 34.0, (3 * WZ_WALL, 26.0, SLOT_W),
                  (-WZ_IN_X / 2, 0, WZ_FLOOR + z), axis="y")
    # Kept inboard of the corner posts: a slot cut across one would open the
    # wall onto solid plastic and vent nothing.
    for sy in (-1, 1):
        wz_tray = wz_tray.cut(_box(8.0, 3 * WZ_WALL, SLOT_W,
                             (WZ_X0 + WZ_POST + 5.0, sy * WZ_Y1, WZ_FLOOR + z)))

# Card slot for the SHT31, standing on edge at the far end of the chamber
# from the SCD41, which shares the compartment and does run slightly warm.
wz_tray = wz_tray.union(_box(6.0, 18.0, 6.0, (WZ_X0 + SENS_X / 2, -22.0, WZ_FLOOR)))
wz_tray = wz_tray.cut(_box(2.0, 22.0, 5.0, (WZ_X0 + SENS_X / 2, -22.0, WZ_FLOOR + 1.5)))

# Board pocket, and the cable out through the +X wall.
wz_tray = wz_tray.union(_box(WZ_BAF, BOARD_Y, BOARD_RIB,
                       (BOARD_X0 + BOARD_X + WZ_BAF / 2, 0, WZ_FLOOR)))
for sy in (-1, 1):
    wz_tray = wz_tray.union(_box(BOARD_X + WZ_BAF, WZ_BAF, BOARD_RIB,
                           (BOARD_X0 + (BOARD_X + WZ_BAF) / 2,
                            sy * (BOARD_Y + WZ_BAF) / 2, WZ_FLOOR)))
wz_tray = wz_tray.cut(_box(18.0, 14.0, 10.0, (WZ_IN_X / 2, 0, WZ_FLOOR)))
for z in (16.0, 20.0):
    wz_tray = wz_tray.cut(_box(3 * WZ_WALL, 26.0, SLOT_W, (WZ_IN_X / 2, 0, WZ_FLOOR + z)))

# Corner posts for the wz_lid.
for (px, py) in WZ_POST_XY:
    wz_tray = wz_tray.union(_box(WZ_POST, WZ_POST, WZ_IN_H, (px, py, WZ_FLOOR)))
    wz_tray = wz_tray.cut(
        cq.Workplane("XY").circle(WZ_PILOT / 2).extrude(WZ_IN_H)
        .translate((px, py, WZ_FLOOR))
    )

display(wz_tray)
_export(wz_tray, "wohnzimmer_tray")


# ---------------------------------------------------------------------------
# Lid
# ---------------------------------------------------------------------------
# The wz_lid prints underside-down, so its top edge is the LAST thing laid down
# and each layer of the round is smaller than the one below it. Free to print,
# unlike the same edge on the terrasse roof.
wz_lid = _box(WZ_X, WZ_Y, WZ_LID).edges("|Z").fillet(CORNER_R)
wz_lid = wz_lid.faces(">Z").edges().fillet(TOP_BREAK)
wz_lid = (
    wz_lid.faces(">Z").workplane()
    .pushPoints(WZ_POST_XY)
    .cskHole(WZ_CLEAR, WZ_CSK, 90)
)

display(wz_lid)
_export(wz_lid, "wohnzimmer_lid")

print("wohnzimmer wz_tray %.1f cm3  wz_lid %.1f cm3" % (
    wz_tray.val().Volume() / 1000.0, wz_lid.val().Volume() / 1000.0))


## ===========================================================================
## Küche / Bad — indoor housing for the plain climate nodes
## ===========================================================================
##
## One design, printed twice: node.rs describes `kueche` as "the same build as
## BAD", and the contents are the same too -- a XIAO and an SHT31 on jumper
## wires, nothing else.
##
## Small, but the same rule still applies: the SHT31 does not share air with
## the board. Two compartments, a baffle between them, and the sensor end
## vented on three sides. A node whose only job is temperature and humidity
## has nothing to report if it reports the inside of its own box.

KL_X, KL_Y, KL_Z = 65.0, 39.0, 30.0
KL_WALL, KL_FLOOR, KL_LID = 2.5, 3.0, 3.0

KL_IN_X = KL_X - 2 * KL_WALL      # 60
KL_IN_Y = KL_Y - 2 * KL_WALL      # 34
KL_IN_H = KL_Z - KL_FLOOR - KL_LID  # 24
KL_TOP = KL_FLOOR + KL_IN_H       # 27

KL_BAF = 2.0
KL_SENS_X = 22.0                  # sensor chamber depth
KL_POST = 8.0
KL_POST_XY = [(sx * (KL_IN_X / 2 - KL_POST / 2), sy * (KL_IN_Y / 2 - KL_POST / 2))
              for sx in (-1, 1) for sy in (-1, 1)]

KL_X0 = -KL_IN_X / 2              # -30
KL_SENS_X1 = KL_X0 + KL_SENS_X    # -8
KL_BOARD_X0 = KL_SENS_X1 + KL_BAF  # -6

# XIAO ESP32-C3, 21 x 17.5 mm, lying flat on the kl_tray floor.
XIAO_X, XIAO_Y = 22.5, 19.0
XIAO_X0 = 2.5                     # leaves 8.5 mm of slack space for the
                                  # jumper wires between baffle and board
XIAO_RIB = 4.0
USB_W, USB_H = 15.0, 9.0

kl_tray = _box(KL_X, KL_Y, KL_TOP).edges("|Z").fillet(CORNER_R)
kl_tray = kl_tray.cut(_box(KL_IN_X, KL_IN_Y, KL_IN_H, (0, 0, KL_FLOOR)))

# Baffle, with a notch at floor level for the jumper wires. Kept small: it is
# there for four wires, not for air.
kl_tray = kl_tray.union(_box(KL_BAF, KL_IN_Y, KL_IN_H,
                       (KL_SENS_X1 + KL_BAF / 2, 0, KL_FLOOR)))
kl_tray = kl_tray.cut(_box(3 * KL_BAF, 7.0, 5.0, (KL_SENS_X1 + KL_BAF / 2, 0, KL_FLOOR)))

# Sensor chamber: -X end and both long walls, the vents kept inboard of the
# corner posts so they open onto air rather than onto a post.
for z in (6.0, 11.0, 16.0):
    kl_tray = kl_tray.cut(_box(3 * KL_WALL, 20.0, SLOT_W, (KL_X0, 0, KL_FLOOR + z)))
    for sy in (-1, 1):
        kl_tray = kl_tray.cut(_box(8.0, 3 * KL_WALL, SLOT_W,
                             (KL_X0 + KL_POST + 5.0, sy * KL_IN_Y / 2, KL_FLOOR + z)))

# Card slot for the SHT31 breakout.
kl_tray = kl_tray.union(_box(6.0, 18.0, 6.0, (KL_X0 + KL_SENS_X / 2, 0, KL_FLOOR)))
kl_tray = kl_tray.cut(_box(2.0, 22.0, 5.0, (KL_X0 + KL_SENS_X / 2, 0, KL_FLOOR + 1.5)))

# XIAO pocket, USB-C end toward the +X wall.
kl_tray = kl_tray.union(_box(KL_BAF, XIAO_Y + 2 * KL_BAF, XIAO_RIB,
                       (XIAO_X0 - KL_BAF / 2, 0, KL_FLOOR)))
kl_tray = kl_tray.union(_box(KL_BAF, XIAO_Y + 2 * KL_BAF, XIAO_RIB,
                       (XIAO_X0 + XIAO_X + KL_BAF / 2, 0, KL_FLOOR)))
for sy in (-1, 1):
    kl_tray = kl_tray.union(_box(XIAO_X + 2 * KL_BAF, KL_BAF, XIAO_RIB,
                           (XIAO_X0 + XIAO_X / 2, sy * (XIAO_Y + KL_BAF) / 2, KL_FLOOR)))

# Cable out. Sized for a USB-C plug's overmould, not just the connector.
kl_tray = kl_tray.cut(_box(3 * KL_WALL, USB_W, USB_H, (KL_IN_X / 2, 0, KL_FLOOR + 0.5)))

for (px, py) in KL_POST_XY:
    kl_tray = kl_tray.union(_box(KL_POST, KL_POST, KL_IN_H, (px, py, KL_FLOOR)))
    kl_tray = kl_tray.cut(
        cq.Workplane("XY").circle(WZ_PILOT / 2).extrude(KL_IN_H)
        .translate((px, py, KL_FLOOR))
    )

display(kl_tray)
_export(kl_tray, "climate_tray")

kl_lid = _box(KL_X, KL_Y, KL_LID).edges("|Z").fillet(CORNER_R)
kl_lid = kl_lid.faces(">Z").edges().fillet(TOP_BREAK)
kl_lid = (
    kl_lid.faces(">Z").workplane()
    .pushPoints(KL_POST_XY)
    .cskHole(WZ_CLEAR, WZ_CSK, 90)
)

display(kl_lid)
_export(kl_lid, "climate_lid")

print("climate kl_tray %.1f cm3  kl_lid %.1f cm3" % (
    kl_tray.val().Volume() / 1000.0, kl_lid.val().Volume() / 1000.0))
