import cadquery as cq
from cadquery import exporters
from pathlib import Path
import math
import numpy as np


path_save = Path("cad-models")
path_save.mkdir(exist_ok=True)

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

## Housing Sensors
# 1. Base Geometry
box_width =  90
box_height = 80
height_org = height
height = 20



wall_thickness = 1.5

box_inner_height = box_height - 2 * wall_thickness
box_inner_width = box_width - 2 * wall_thickness

results = cq.Workplane("front").box(box_width, box_height, height)
inner = cq.Workplane("front").box(box_inner_width, box_inner_height, height-wall_thickness/2).translate( (0, 0, wall_thickness))
results = results.cut(inner)

sep1 = cq.Workplane("front").box(box_width, wall_thickness, height).translate( (0, 5, 0) )
results = results.add(sep1)

sep2 = cq.Workplane("front").box(wall_thickness, box_height/2-5, height).translate( (0, box_height/4+2.5, 0) )
results = results.add(sep2)

usbc_open = cq.Workplane("front").box(12, 2*wall_thickness, height-wall_thickness).translate( (-box_width/4, box_height/2, wall_thickness/2) )
results = results.cut(usbc_open)

hx711_open = cq.Workplane("front").box(4, 2*wall_thickness, 6).translate( (box_width*0.4, box_height/2, height/2-6/2) )
results = results.cut(hx711_open)

internal_usbc_open = cq.Workplane("front").box(6, 2*wall_thickness, height-wall_thickness).translate( (-box_width/4, 5, wall_thickness/2) )
results = results.cut(internal_usbc_open)

internal_hx711_open = cq.Workplane("front").box(6, 2*wall_thickness, height-wall_thickness).translate( (box_width/4, 5, wall_thickness/2) )
results = results.cut(internal_hx711_open)


sketch = (
    cq.Sketch()
    .trapezoid(18.5, height/4, -60) # width, height, interior angle in degrees
)
trapezoid = cq.Workplane("XZ").placeSketch(sketch).extrude(-height_org).translate( (box_width/2, -height/2-2.5, -height_org/8*3+2)).rotate( (0, 0, 0), (1, 0, 0), 270).translate(
    (-box_width*.45, box_height/2+5+2, -wall_thickness-1)
)
results.add(trapezoid)

# Cable
hole = cq.Workplane("front").circle(2).extrude(3).rotate( (0, 0, 0), (1, 0, 0), 270).translate( (-4, -box_height/2, 0) )
results = results.cut(hole)
hole = cq.Workplane("front").circle(2).extrude(3).rotate( (0, 0, 0), (1, 0, 0), 270).translate( (4, -box_height/2, 0) )
results = results.cut(hole)

display(results)

exporters.export(results, str(path_save / "bird_scale_box.stl"))


