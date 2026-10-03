"""cckb-click の本番の組み立てを Blender で**開ける状態**にまとめる。**Blender の Python で動かす。**

projects/cckb-click/click_case.py が build/cckb-click/assembly_main/*.stl（<asm|exploded>__<グループ>.stl）と style.json（色）を書く。
これを読み込み、「組んだ状態」「分解」の 2 つのコレクションの下にグループごとのコレクションを作り、平行投影のカメラを置いて
cckb-click.blend に保存し、2 枚の絵（組んだ状態・分解）を出す。**PNG は飾りではない**: 材質とカメラが効いたかを開かずに確かめる証拠。

    /Applications/Blender.app/Contents/MacOS/Blender -b -P projects/cckb-click/tools/blend_main.py

Blender は -P のスクリプトが例外で落ちても 0 を返す（lessons E）ので、最後に「OK <物の数>」を出す。
"""

import json
from pathlib import Path

import bpy
from mathutils import Vector

OUT = Path(__file__).resolve().parents[3] / "build" / "cckb-click" / "assembly_main"
VIEW_DIR = Vector((0.35, -1.0, 0.9)).normalized()
RES = (1600, 800)
TOP = {"asm": "組んだ状態", "exploded": "分解"}


def frame_camera(scene, cam, objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p[i] for p in pts) for i in range(3)))
    hi = Vector((max(p[i] for p in pts) for i in range(3)))
    center, size = (lo + hi) / 2, max(hi - lo)
    cam.data.clip_start, cam.data.clip_end = 1.0, size * 20
    cam.rotation_euler = (-VIEW_DIR).to_track_quat("-Z", "Y").to_euler()
    cam.location = center + VIEW_DIR * size * 3
    bpy.context.view_layer.update()
    inv = cam.matrix_world.inverted()
    local = [inv @ p for p in pts]
    xs, ys = [p.x for p in local], [p.y for p in local]
    cam.data.ortho_scale = max(max(xs) - min(xs), (max(ys) - min(ys)) * RES[0] / RES[1]) * 1.06
    cam.location += cam.matrix_world.to_3x3() @ Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, 0))
    return center, size


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 0.001
    scene.unit_settings.length_unit = "MILLIMETERS"
    style = json.loads((OUT / "style.json").read_text())
    tops, objs = {}, {t: [] for t in TOP}
    for tag, name in TOP.items():
        tops[tag] = bpy.data.collections.new(name)
        scene.collection.children.link(tops[tag])
    for path in sorted(OUT.glob("*.stl")):
        tag, group = path.stem.split("__")
        before = set(bpy.data.objects)
        bpy.ops.wm.stl_import(filepath=str(path))
        new = set(bpy.data.objects) - before
        if not new:
            raise RuntimeError(f"読み込めなかった: {path}")
        obj = new.pop()
        obj.name = path.stem
        color, alpha = style.get(path.stem, ("#888888", 1.0))
        r, g, b = (int(color[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
        mat = bpy.data.materials.new(path.stem)
        mat.diffuse_color = (r, g, b, alpha)
        obj.data.materials.append(mat)
        col = bpy.data.collections.new(f"{TOP[tag]}/{group}")
        tops[tag].children.link(col)
        for c in list(obj.users_collection):
            c.objects.unlink(obj)
        col.objects.link(obj)
        objs[tag].append(obj)
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.type = "ORTHO"
    cam = bpy.data.objects.new("Camera", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = RES
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.light = "STUDIO"
    for tag, png in (("exploded", "cckb-click_exploded.png"), ("asm", "cckb-click_assembled.png")):
        for t in TOP:
            for o in objs[t]:
                o.hide_render = t != tag
        center, size = frame_camera(scene, cam, objs[tag])
        scene.render.filepath = str(OUT / png)
        bpy.ops.render.render(write_still=True)
    for t in TOP:
        for o in objs[t]:
            o.hide_render = False
    # 開いたときは組んだ状態を見せる（分解は目のアイコンで出す）
    for layer in scene.view_layers:
        for lc in layer.layer_collection.children:
            if lc.name == TOP["exploded"]:
                lc.hide_viewport = True
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
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "cckb-click.blend"))
    print(f"OK {sum(len(v) for v in objs.values())} {OUT / 'cckb-click.blend'}")


main()
