import cadquery as cq
from cadquery import exporters
from pathlib import Path
import math
import numpy as np


path_save = Path("cad-models")
path_save.mkdir(exist_ok=True)

try:  # provided by CQ-editor / jupyter-cadquery; a no-op when run as a script
    display
except NameError:

    def display(*_args, **_kwargs):
        pass


## halterung biegebalken 1
## Vogelwaage Dicke Schrauben
# Dimensions
height = 12
width = 12
length = 25

total_length = 80
balken_length = total_length / 2 + 20

drill_distance = 15
dia_screw = 4
dia_screw_head = 8
dia_wire = 1

# 1. Base Geometry
results = cq.Workplane("front").box(length, width, height)

balken = (
    cq.Workplane("front")
    .box(balken_length, width, height / 2)
    .translate((balken_length / 2 - length / 2, 0, -height / 4))
)

# Fuse the two solids into one
results = results.union(balken)

# 2. Add Countersunk Holes
# We select the top face (>Z) and drill down using pushed points
results = (
    results.faces("<Z")
    .workplane()
    .pushPoints([(-drill_distance / 2, 0), (drill_distance / 2, 0)])
    .cskHole(dia_screw, dia_screw_head, 90)
)

# 3. Add Wire Hole
# Target the top face of the extended beam section
wire_x_offset = total_length / 2 - length / 2
results = (
    results.faces("<Z")
    .workplane()
    .pushPoints([(wire_x_offset, 0)])
    .hole(dia_wire)
)

# Render and Export
display(results)
exporters.export(results, str(path_save / "bird_scale_part1.stl"))

## halterung biegebalken 2
## Vogelwaage Dicke Schrauben
# Dimensions
height = 12
width = 12
length = 25

total_length = 80
balken_length = total_length / 2 + 20

drill_distance = 15
dia_screw = 5
dia_screw_head = 10
dia_wire = 1

# 1. Base Geometry
results = cq.Workplane("front").box(length, width, height)

balken = (
    cq.Workplane("front")
    .box(balken_length, width, height / 2)
    .translate((balken_length / 2 - length / 2, 0, -height / 4))
)

# Fuse the two solids into one
results = results.union(balken)

# 2. Add Countersunk Holes
# We select the top face (>Z) and drill down using pushed points
results = (
    results.faces("<Z")
    .workplane()
    .pushPoints([(-drill_distance / 2, 0), (drill_distance / 2, 0)])
    .cskHole(dia_screw, dia_screw_head, 90)
)

# 3. Add Wire Hole
# Target the top face of the extended beam section
wire_x_offset = total_length / 2 - length / 2
results = (
    results.faces("<Z")
    .workplane()
    .pushPoints([(wire_x_offset, 0)])
    .hole(dia_wire)
)

## trapezoid
# Create a 2D trapezoid using Sketch
# trapezoid(w, h, angle)
sketch = (
    cq.Sketch()
    .trapezoid(20, height/4, -60) # width, height, interior angle in degrees
)

# Extrude into 3D
trapezoid = cq.Workplane("XZ").placeSketch(sketch).extrude(-20).translate( (wire_x_offset, -10, -height/8*3))

results = results.cut(trapezoid)

# Render and Export
display(results)
exporters.export(results, str(path_save / "bird_scale_with_box_part2.stl"))

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
##      the clamp above (25 x 12 face, two screws at `drill_distance`), with
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
EAR_L, EAR_W = 9.0, 12.0
EAR_HOLE = 4.0                   # 3 mm cord knots through comfortably

# --- vent chamber, centred on the -Y wall ---------------------------------
CH_X, CH_Y = 22.0, 12.0         # width lands on the corner posts, see below
BAFFLE = 2.0
CH_Y0 = -IN_Y / 2                # -26

VENT_W, VENT_H = 14.0, 2.5       # outlet slots in the side wall
VENT_Z = [32.0, 36.0, 40.0]
VENT_TILT = 30.0                 # degrees, sloping down and outward

# --- floor-to-body screws (M3) --------------------------------------------
BOSS_D, BOSS_PILOT, BOSS_H = 8.0, 2.5, 14.0
BOSS_XY = [(sx * (IN_X / 2 - BOSS_D / 2), sy * (IN_Y / 2 - BOSS_D / 2))
           for sx in (-1, 1) for sy in (-1, 1)]
SCREW_CLEAR, SCREW_CSK = 3.4, 6.6

# --- bending-beam anchor (M4) ---------------------------------------------
ANCHOR_PITCH = drill_distance    # 15 mm, the clamp pitch set above
ANCHOR_HOLE = 4.3
NUT_AF, NUT_T = 7.2, 3.4         # M4 nut across flats, thickness
PAD_X, PAD_Y, PAD_H = 27.0, 14.0, 3.5
FLANGE_X, FLANGE_Y, FLANGE_H = 33.0, 18.0, 2.5
NUT_BOSS_H = 5.0                 # boss inside the box carrying the nuts

CABLE_D, CABLE_Y = 6.0, 15.0     # load-cell cable, up through the floor
DRAIN_D, DRAIN_Y = 3.0, 24.0     # condensate drain, main compartment


def _box(l, w, h, at=(0.0, 0.0, 0.0)):
    """Axis-aligned box, centred in X/Y, sitting on z=at[2]."""
    return (
        cq.Workplane("XY")
        .box(l, w, h, centered=(True, True, False))
        .translate(at)
    )


# ---------------------------------------------------------------------------
# Body
# ---------------------------------------------------------------------------
body = _box(BODY_X, BODY_Y, ENV_Z - Z_FLOOR, (0, 0, Z_FLOOR))
body = body.union(_box(ENV_X, ENV_Y, EAVE_H, (0, 0, ENV_Z - EAVE_H)))

# Hollow it out. The cavity reaches the bottom of the walls, so the box is
# open downward and the roof stays a single unbroken wall.
body = body.cut(_box(IN_X, IN_Y, Z_CEIL - Z_FLOOR, (0, 0, Z_FLOOR)))

# Hanging ears, flush with the eave band.
for sx in (-1, 1):
    ex = sx * (ENV_X / 2 + EAR_L / 2)
    body = body.union(_box(EAR_L, EAR_W, EAVE_H, (ex, 0, ENV_Z - EAVE_H)))
    body = body.cut(
        cq.Workplane("XY")
        .circle(EAR_HOLE / 2)
        .extrude(EAVE_H)
        .translate((ex, 0, ENV_Z - EAVE_H))
    )

# Vent chamber: add the baffle block, then hollow the chamber out of it.
body = body.union(
    _box(CH_X + 2 * BAFFLE, CH_Y + BAFFLE, Z_CEIL - Z_FLOOR,
         (0, CH_Y0 + (CH_Y + BAFFLE) / 2, Z_FLOOR))
)
body = body.cut(
    _box(CH_X, CH_Y, Z_CEIL - Z_FLOOR, (0, CH_Y0 + CH_Y / 2, Z_FLOOR))
)

# Cable pass-through in the baffle, for the SHT31's flying lead. Seal it with
# a dab of silicone on assembly: it is the one path from the chamber into the
# electronics volume, and it is there for the wire, not for air.
body = body.cut(_box(6.0, 3 * BAFFLE, 4.0, (0, CH_Y0 + CH_Y, 42.0)))

# Outlet slots, tilted down and outward so nothing runs in.
for z in VENT_Z:
    slot = (
        cq.Workplane("XY")
        .box(VENT_W, 12.0, VENT_H)
        .rotate((0, 0, 0), (1, 0, 0), VENT_TILT)
        .translate((0, -BODY_Y / 2 + WALL / 2, z))
    )
    body = body.cut(slot)

# Screw bosses for the floor.
for (px, py) in BOSS_XY:
    body = body.union(_box(BOSS_D, BOSS_D, BOSS_H, (px, py, Z_FLOOR)))
    body = body.cut(
        cq.Workplane("XY").circle(BOSS_PILOT / 2).extrude(BOSS_H)
        .translate((px, py, Z_FLOOR))
    )

display(body)
exporters.export(body, str(path_save / "terrasse_body.stl"))
exporters.export(body, str(path_save / "terrasse_body.step"))


# ---------------------------------------------------------------------------
# Floor
# ---------------------------------------------------------------------------
floor = _box(BODY_X, BODY_Y, FLOOR_T)

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
    cq.Workplane("XY").circle(5.0).extrude(4.0).translate((0, CABLE_Y, -4.0))
)
floor = floor.cut(
    cq.Workplane("XY").circle(CABLE_D / 2).extrude(FLOOR_T + 4.0)
    .translate((0, CABLE_Y, -4.0))
)

# Condensate drain for the electronics volume.
floor = floor.cut(
    cq.Workplane("XY").circle(DRAIN_D / 2).extrude(FLOOR_T)
    .translate((0, DRAIN_Y, 0))
)

# Air inlet under the vent chamber: two slots behind the sensor card and
# two flanking it, so the card does not sit on top of its own inlet.
for sy in (-18.9, -15.4):
    floor = floor.cut(_box(16.0, 2.0, FLOOR_T, (0, sy, 0)))
for sx in (-9.5, 9.5):
    floor = floor.cut(_box(2.0, 10.0, FLOOR_T, (sx, -20.5, 0)))

# Card slot for the SHT31 breakout, standing on edge in the chamber. Held
# 0.75 mm off the outer wall: it belongs to the floor, the wall to the body,
# and they have to come apart.
floor = floor.union(_box(16.0, 5.5, 6.0, (0, -22.5, FLOOR_T)))
floor = floor.cut(_box(20.0, 2.0, 5.0, (0, -22.5, FLOOR_T + 1.5)))

display(floor)
exporters.export(floor, str(path_save / "terrasse_floor.stl"))
exporters.export(floor, str(path_save / "terrasse_floor.step"))

print("terrasse body  %.1f cm3   bbox %s" % (
    body.val().Volume() / 1000.0, body.val().BoundingBox()))
print("terrasse floor %.1f cm3   bbox %s" % (
    floor.val().Volume() / 1000.0, floor.val().BoundingBox()))
