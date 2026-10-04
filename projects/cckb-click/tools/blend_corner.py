"""右手前の角を、上からと手前から描く（2 枚。電池の蓋を付けた状態）。**Blender の Python で動かす。**

projects/cckb-click/click_case.py が書いた build/cckb-click/assembly_main/asm__<グループ>.stl と style.json を読む。

    /Applications/Blender.app/Contents/MacOS/Blender -b -P projects/cckb-click/tools/blend_corner.py

Blender は -P のスクリプトが例外で落ちても 0 を返すので、最後に「OK <絵の数>」を出す（呼ぶ側はファイルも見る）。
"""

import json
from pathlib import Path

import bpy
from mathutils import Vector

OUT = Path(__file__).resolve().parents[3] / "build" / "cckb-click" / "assembly_main"
RES = (1500, 900)
CENTER = Vector((127.0, -41.0, 2.0))            # 右手前の角（電池の口と電源スイッチの間）
VIEWS = {"top": (Vector((0.0, -0.25, 1.0)), 46.0), "front": (Vector((0.55, -1.0, 0.45)), 46.0)}


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    style = json.loads((OUT / "style.json").read_text())
    objs = {}
    for path in sorted(OUT.glob("asm__*.stl")):
        before = set(bpy.data.objects)
        bpy.ops.wm.stl_import(filepath=str(path))
        obj = (set(bpy.data.objects) - before).pop()
        obj.name = path.stem
        color, alpha = style.get(path.stem, ("#888888", 1.0))
        mat = bpy.data.materials.new(path.stem)
        mat.diffuse_color = tuple(int(color[i:i + 2], 16) / 255.0 for i in (1, 3, 5)) + (alpha,)
        obj.data.materials.append(mat)
        objs[path.stem.split("__")[1]] = obj
    if "frame_right" not in objs:
        raise RuntimeError(f"右の枠の STL が無い: {sorted(objs)}")
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.type = "ORTHO"
    cam = bpy.data.objects.new("Camera", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = RES
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.show_cavity = True
    n = 0
    for view, (direction, scale) in VIEWS.items():
        d = direction.normalized()
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        cam.location = CENTER + d * 400.0
        cam.data.clip_start, cam.data.clip_end = 1.0, 2000.0
        cam.data.ortho_scale = scale
        scene.render.filepath = str(OUT / f"corner_{view}.png")
        bpy.ops.render.render(write_still=True)
        n += 1
    print(f"OK {n}")


main()
