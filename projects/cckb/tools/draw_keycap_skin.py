"""キャップの天板を膜にした前後の断面（原寸の比・y = 0 でキーの中心を切る）→ build/cckb/keycap_skin_before_after.png

    .venv/bin/python3 projects/cckb/tools/draw_keycap_skin.py <前の keycaps.py> <前の case_spec.py> <前の spec.py>

前の 3 つは `git show 6bee045:projects/cckb/<名前>.py` で取り出した物（膜にする前）。
4 枚: 前・押す前 / 前・押し切り / いま・押す前 / いま・押し切り。高さは基板の上面から。
スイッチは組み立てと同じ図の包絡（assembly.Assembly.switch_solids の 1 個分を、基板の上面を 0 に置き直した物）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJ = HERE.parent
ROOT = PROJ.parents[1]
for p in (str(ROOT), str(PROJ)):
    if p not in sys.path:
        sys.path.insert(0, p)


def load_module(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def switch(spec, cs, sw, travel):
    """基板の上面 = 0 のスイッチ 1 個（胴・つば・上の胴・静音のつば・ステムと窪みと十字）。travel だけステムが沈む。"""
    import keycaps as KC
    from case import box, cyl, fuse

    h, f2 = sw.cutout / 2, cs.SW_FLANGE / 2
    pt = spec.PLATE_TOP_ABOVE_PCB
    top, collar, stem = spec.SWITCH_TOP_ABOVE_PCB, spec.SWITCH_COLLAR_ABOVE_PCB, spec.SWITCH_STEM_ABOVE_PCB
    housing = fuse([box(-h, -h, 0, h, h, pt), box(-f2, -f2, pt, f2, f2, pt + cs.SW_FLANGE_T),
                    box(-h, -h, pt + cs.SW_FLANGE_T, h, h, top), cyl(0, 0, top - 0.01, collar, spec.SWITCH_COLLAR_D)])
    housing = housing - cyl(0, 0, top - 3.05 - 0.1, collar + 1, cs.SW_STEM_D + 0.1)
    floor = cs.SW_RECESS_FLOOR
    st = cyl(0, 0, top - travel, stem - travel, cs.SW_STEM_D) - cyl(0, 0, floor - travel, stem + 1, cs.SW_RECESS_D)
    st = fuse([st] + KC.cross(0.0, floor - travel - 0.01, stem - travel, cs.STEM_CROSS))
    return housing, st


def main(argv):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from build123d import Pos
    from matplotlib.collections import PolyCollection
    from matplotlib.patches import Patch

    import assembly as A
    import case_spec as CS
    import interface as I
    import keycaps as KC

    plt.rcParams["font.family"] = ["Hiragino Sans", "Hiragino Kaku Gothic ProN", "sans-serif"]
    ifc = I.Interface()
    s = ifc.s
    kc_old = load_module("keycaps_old", argv[0])
    cs_old = load_module("case_spec_old", argv[1])
    spec_old = load_module("spec_old", argv[2])
    tr = KC.travel_max(s)
    stem = s.SWITCH_STEM_ABOVE_PCB
    rows = [("前（天板 1.2・上面 14.4）", kc_old.keycap(1.0, spec_old, ifc.sw, cs_old), spec_old.KEYCAP_TOP_T),
            (f"いま（膜 {s.KEYCAP_TOP_T}・上面 {ifc.z()['keycap_top']:.1f}）", KC.keycap(1.0, s, ifc.sw, CS), s.KEYCAP_TOP_T)]
    colors = {"housing": "#555555", "stem": "#8e8e8e", "cap": "#5dade2"}
    fig, axes = plt.subplots(2, 2, figsize=(15, 8), dpi=110)
    for i, (label, cap, t) in enumerate(rows):
        for j, pressed in enumerate((False, True)):
            ax = axes[i][j]
            dz = tr if pressed else 0.0
            housing, st = switch(s, CS, ifc.sw, dz)
            parts = {"housing": housing, "stem": st, "cap": Pos(0, 0, stem - dz) * cap}
            for name, part in parts.items():
                tris = A.section_faces(part, ("y", 0.0))
                ax.add_collection(PolyCollection(tris, facecolors=colors[name], edgecolors=colors[name], linewidths=0.2))
            top = stem + t - dz
            for z, txt, c in ((s.SWITCH_TOP_ABOVE_PCB, "ハウジング 5.30", "#555555"),
                              (s.SWITCH_COLLAR_ABOVE_PCB, "つば 5.70", "#c0392b"), (top, f"キャップの上面 {top:.2f}", "#1a5276"),
                              (s.RIM_ABOVE_PCB, f"縁 {s.RIM_ABOVE_PCB:.2f}", "#b9770e")):
                ax.axhline(z, color=c, lw=0.6, ls="--")
                ax.text(9.6, z + 0.05, txt, fontsize=7, color=c)
            ax.set_xlim(-9.5, 12.5)
            ax.set_ylim(4.0, 10.0)
            ax.set_aspect("equal")
            ax.grid(True, lw=0.3, alpha=0.4)
            ax.set_title(f"{label}  {'押し切り（行程 3.05）' if pressed else '押す前'}", fontsize=9)
            ax.set_xlabel("x [mm]（キーの中心から）")
            ax.set_ylabel("z [mm]（基板の上面から）")
    fig.legend(handles=[Patch(color=colors["housing"], label="ハウジング（図の包絡）"),
                        Patch(color=colors["stem"], label="ステム"), Patch(color=colors["cap"], label="キャップ")],
               loc="lower center", ncol=3, fontsize=8)
    fig.suptitle("1u のキャップ y = 0 の断面（縦横同じ縮尺）。縁の線は机からではなく基板の上面からの高さ 7.0", fontsize=10)
    out = ROOT / "build/cckb/keycap_skin_before_after.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, bbox_inches="tight")
    print(out)


if __name__ == "__main__":
    main(sys.argv[1:])
