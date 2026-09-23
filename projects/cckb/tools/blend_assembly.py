"""組み立てモデルを Blender で**開ける状態**にまとめる（CCKB）。**Blender の Python で動かす。**

projects/cckb/assembly.py が build/cckb/assembly/*.stl と style.json（色）を書く。これを読み込み、
部品ごとに色を付け、平行投影のカメラを置いて cckb.blend に保存し、カメラから見た絵
（cckb_blender.png）も出す。**PNG は飾りではない**: 材質とカメラが効いたかを開かずに確かめる証拠。

    /Applications/Blender.app/Contents/MacOS/Blender -b -P projects/cckb/tools/blend_assembly.py

Blender は -P のスクリプトが例外で落ちても 0 を返す（lessons E）ので、最後に
「OK <物の数>」を出す。呼ぶ側はその行と、できたファイルを見る。
HHKB の tools/blend_assembly.py を参照実装にした（CCKB では 1 枚・平行投影だけ）。
"""

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector

OUT = Path(__file__).resolve().parents[3] / "build" / "cckb" / "assembly"
VIEW_DIR = Vector((0.9, -1.2, 1.0)).normalized()


def _import_stl(path):
    before = set(bpy.data.objects)
    bpy.ops.wm.stl_import(filepath=str(path))
    new = set(bpy.data.objects) - before
    if not new:
        raise RuntimeError(f"読み込めなかった: {path}")
    return new.pop()


def _material(name, hex_color, alpha):
    r, g, b = (int(hex_color[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (r, g, b, alpha)
    return mat


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 0.001
    scene.unit_settings.length_unit = "MILLIMETERS"
    style = json.loads((OUT / "style.json").read_text())
    objs = []
    for path in sorted(OUT.glob("*.stl")):
        obj = _import_stl(path)
        obj.name = path.stem
        color, alpha = style.get(path.stem, ("#888888", 1.0))
        obj.data.materials.append(_material(path.stem, color, alpha))
        objs.append(obj)
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p[i] for p in pts) for i in range(3)))
    hi = Vector((max(p[i] for p in pts) for i in range(3)))
    center, size = (lo + hi) / 2, max(hi - lo)
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.type = "ORTHO"
    cam_data.clip_start, cam_data.clip_end = 1.0, size * 20
    cam = bpy.data.objects.new("Camera", cam_data)
    scene.collection.objects.link(cam)
    cam.rotation_euler = (-VIEW_DIR).to_track_quat("-Z", "Y").to_euler()
    cam.location = center + VIEW_DIR * size * 3
    bpy.context.view_layer.update()
    inv = cam.matrix_world.inverted()
    local = [inv @ p for p in pts]
    xs, ys = [p.x for p in local], [p.y for p in local]
    scene.render.resolution_x, scene.render.resolution_y = 1800, 1000
    aspect = 1800 / 1000
    cam_data.ortho_scale = max(max(xs) - min(xs), (max(ys) - min(ys)) * aspect) * 1.06
    cam.location += cam.matrix_world.to_3x3() @ Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, 0))
    scene.camera = cam
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.light = "STUDIO"
    scene.render.filepath = str(OUT / "cckb_blender.png")
    bpy.ops.render.render(write_still=True)
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                for sp in area.spaces:
                    if sp.type == "VIEW_3D":
                        sp.shading.color_type = "MATERIAL"
                        sp.clip_start, sp.clip_end = 1.0, size * 20
                        sp.region_3d.view_location = center
                        sp.region_3d.view_distance = size * 1.6
                        sp.region_3d.view_rotation = cam.rotation_euler.to_quaternion()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "cckb.blend"))
    print(f"OK {len(objs)} {OUT / 'cckb.blend'} {math.floor(size)}")


main()
