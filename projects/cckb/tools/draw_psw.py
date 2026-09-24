"""電源スイッチ SS-12D00G3（右の角）の絵を 2 枚出す。**寸法は持たない**（組み立てモデル assembly.py の立体を切る）。

    .venv/bin/python3 projects/cckb/tools/draw_psw.py   # → build/cckb/psw_section.png・psw_corner_iso.png

1. psw_section.png: 電源スイッチの足の並び（x = PSW_AT.x）で切った断面。スイッチは**1 つの部品として
   太い線で囲む**（本体は基板の上・足は基板を貫いて下で切る・レバーはふたの穴の中）。高さの数字つき
2. psw_corner_iso.png: 右の角を斜め上から。ふたを持ち上げた状態（ふたの穴・刻印とレバーの位置関係）
出したら Read で見ること。
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402

import assembly as A  # noqa: E402
from case import box  # noqa: E402

plt.rcParams["font.family"] = ["Hiragino Sans", "Hiragino Kaku Gothic ProN", "sans-serif"]


def outline_segments(part, plane):
    """B-rep の断面の面の**外周の辺**を [(横, z), (横, z)] で（面の中の三角形の境界ではない）。"""
    from build123d import Face, Plane

    axis, val = plane
    pl = Plane(origin=(val, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    big = pl * Face.make_rect(1000, 1000)
    segs = []
    for s in A.solids_of(part):
        c = s & big
        if c is None:
            continue
        for f in c.faces():
            for e in f.outer_wire().edges():
                pts = [e.position_at(u) for u in (0.0, 0.25, 0.5, 0.75, 1.0)]
                segs += [((a.Y, a.Z), (b.Y, b.Z)) for a, b in zip(pts, pts[1:])]
    return segs


def section(asm, g, out):
    s, z = asm.s, asm.z
    x = s.PSW_AT[0]
    on = s.PSW_ON
    sw = asm.psw(lever=on, envelope=False)
    fig, ax = plt.subplots(figsize=(12, 7.2), dpi=170)
    parts = [("tray_R", "トレイ（床と右の壁）"), ("pcb", "基板"), ("lid_R", "右のふた（電池のふた）")]
    for name, label in parts:
        tris = A.section_faces(g[name], ("x", x))
        ax.add_collection(PolyCollection(tris, facecolors=A.COLORS[name], edgecolors=A.COLORS[name],
                                         linewidths=0.2, label=label))
    tris = A.section_faces(sw, ("x", x))
    ax.add_collection(PolyCollection(tris, facecolors="#f5c6c0", edgecolors="#f5c6c0", linewidths=0.2))
    for a, b in outline_segments(sw, ("x", x)):
        ax.plot([a[0], b[0]], [a[1], b[1]], color="#c0392b", lw=2.2, solid_capstyle="round")
    y0 = s.PSW_AT[1]
    lo, tip, hi = asm.r.psw_tip_range()
    labels = [("rim", "ふたの上面"), ("lid_bottom", "ふたの下面"), ("psw_tip", "レバーの先（名目）"),
              ("psw_top", "スイッチ本体の上面"), ("psw_seat", "本体の下面（爪 %.1f で浮く）" % s.PSW_TAB),
              ("pcb_top", "基板の上面"), ("pcb_bottom", "基板の下面"),
              ("psw_pin_end", "足の先（切ったあと）"), ("floor_top", "床の上面")]
    xl = y0 - 21
    for key, text in labels:
        v = z[key]
        ax.axhline(v, color="0.55", lw=0.4, ls=":")
        va = {"rim": "bottom", "psw_tip": "top", "psw_seat": "bottom", "pcb_top": "top"}.get(key, "center")
        ax.text(xl, v, f"z {v:5.2f}  {text}", fontsize=7.5, va=va,
                bbox=dict(fc="white", ec="none", pad=0.3))
    ax.axhspan(lo, hi, color="r", alpha=0.07)
    lev = asm.r.psw_lever(on)
    ax.annotate(f"レバー（入の位置＝{'奥' if on > 0 else '手前'}）\n先は名目でふたの上面の {z['rim'] - tip:.1f} 下\n"
                f"（公差を積むと {z['rim'] - hi:+.1f}〜{z['rim'] - lo:+.1f}。薄い赤の帯）",
                xy=((lev[1] + lev[3]) / 2, tip - 0.4), xytext=(y0 + 5.5, z["rim"] + 2.2), fontsize=8,
                arrowprops=dict(arrowstyle="->", color="#c0392b"), color="#c0392b")
    ax.annotate("電源スイッチ SS-12D00G3（1 つの部品）\n本体は基板の上に載る", xy=(y0 + 1.5, z["psw_top"] - 1.5),
                xytext=(y0 + 6.5, z["psw_top"] - 0.5), fontsize=8,
                arrowprops=dict(arrowstyle="->", color="#c0392b"), color="#c0392b")
    ax.annotate(f"足 3 本は基板を貫き、はんだの後で\n基板の下面から {s.PSW_PIN_TRIM} に切る（床まで "
                f"{z['psw_pin_end'] - z['floor_top']:.1f}）", xy=(y0 + 2.5, z["pcb_bottom"] - 0.5),
                xytext=(y0 + 6.5, z["pcb_bottom"] - 1.6), fontsize=8,
                arrowprops=dict(arrowstyle="->", color="#c0392b"), color="#c0392b")
    sl = asm.case.psw_slot()
    ax.annotate(f"ふたの穴 {sl[3] - sl[1]:.1f} × {sl[2] - sl[0]:.1f}\n（両端に爪を入れる {asm.c.PSW_SLOT_NAIL} ずつ）",
                xy=(sl[1] + 0.3, z["rim"] - 0.3), xytext=(y0 - 12, z["rim"] + 2.2), fontsize=8,
                arrowprops=dict(arrowstyle="->", color="0.3"))
    ax.set_xlim(y0 - 21.5, y0 + 17)
    ax.set_ylim(-0.8, z["rim"] + 4.2)
    ax.set_aspect("equal")
    ax.set_xlabel("y [mm]（右が奥）")
    ax.set_ylabel("z [mm]（机 = 0）")
    ax.set_title(f"電源スイッチの断面（x = {x:.3f}・足の並びを通る）: 赤い線で囲んだのが電源スイッチ 1 個",
                 fontsize=10)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=7)
    ax.grid(True, lw=0.3, alpha=0.4)
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def iso_png(meshes, out, lift, notes=(), elev=38, azim=-58):
    """斜め上からの絵。画家のアルゴリズムに**裏向きの面を捨てる**（assembly.exploded_png は下の面が上の面に
    重なって、ふたの穴と刻印が見えなかった）と、光の向きで明るさを付ける。"""
    import numpy as np
    import trimesh
    from matplotlib.colors import to_rgb
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    e, a = np.radians(elev), np.radians(azim)
    view = np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])
    light = np.array([-0.3, -0.5, 1.0])
    light /= np.linalg.norm(light)
    tris, cols = [], []
    for name, m in meshes.items():
        v, f = trimesh.remesh.subdivide_to_size(m.vertices, m.faces, max_edge=1.0)
        t3 = v[f].copy()
        t3[:, :, 2] += lift.get(name, 0.0)
        n = np.cross(t3[:, 1] - t3[:, 0], t3[:, 2] - t3[:, 0])
        n /= np.linalg.norm(n, axis=1)[:, None] + 1e-12
        keep = n @ view > 1e-6
        base = np.array(to_rgb(A.COLORS.get(name, "#cccccc")))
        shade = 0.55 + 0.45 * np.clip(n[keep] @ light, 0, 1)
        tris.append(t3[keep])
        cols.append(np.clip(base[None, :] * shade[:, None], 0, 1))
    tris, cols = np.concatenate(tris), np.concatenate(cols)
    order = np.argsort(tris.mean(axis=1) @ view)
    fig = plt.figure(figsize=(14, 9), dpi=150)
    ax = fig.add_subplot(111, projection="3d")
    ax.add_collection3d(Poly3DCollection(tris[order], facecolors=cols[order], edgecolor=cols[order],
                                         linewidths=0.1, alpha=1.0))
    lo, hi = tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0)
    ax.set_xlim(lo[0], hi[0])
    ax.set_ylim(lo[1], hi[1])
    ax.set_zlim(lo[2], hi[2])
    ax.set_box_aspect(hi - lo)
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    fig.text(0.02, 0.98, "\n".join(notes), fontsize=10, va="top", color="#222222")
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def corner_iso(asm, g, out, lift=12.0):
    """右の角を斜め上から（ふたを lift 持ち上げる）。トレイと基板は角だけ切り出す。"""
    s, z = asm.s, asm.z
    c = asm.i.cover("right")
    clip = box(c[0] - 4, c[1] - 1, -1, c[2] + 1, c[3] + 4, 40)
    parts = {"tray_R": g["tray_R"] & clip, "pcb": g["pcb"] & clip, "holder": g["holder"], "cell": g["cell"],
             "psw": asm.psw(lever=s.PSW_ON, envelope=False), "lid_R": g["lid_R"], "screw_lid": g["screw_lid"]}
    meshes = {k: A.mesh_of(v) for k, v in parts.items()}
    sl = asm.case.psw_slot()
    notes = [f"右の角（右手前から見下ろす）。右のふた（橙）を {lift:.0f}mm 持ち上げた",
             f"ふたの右端の四角い穴 {sl[3] - sl[1]:.1f}×{sl[2] - sl[0]:.1f}: ふたを閉めるとレバー（赤の細い柱）がこの中に来る。"
             f"先は名目でふたの上面の {z['rim'] - z['psw_tip']:.1f} 下",
             f"穴の左の刻印「ON ↑」: レバーを矢印の向き（{'奥' if s.PSW_ON > 0 else '手前'}）へ爪で押すと入",
             "赤: 電源スイッチ SS-12D00G3（基板の右の縁）・灰: 電池ホルダ・黄: CR1632・緑: 基板・青: トレイ",
             "ふたは真上に外す（レバーは穴の中を縦に抜ける）"]
    return iso_png(meshes, out, {"lid_R": lift, "screw_lid": lift}, notes)


def main():
    geo = A.board_geometry()
    asm = A.Assembly(geo)
    g = {k: v for k, v in asm.printed().items()}
    g["pcb"] = asm.pcb()
    g["holder"] = asm.holder()
    g["cell"] = asm.cell()
    g["screw_lid"] = asm.screw_lid()
    out = asm.i.p.build
    out.mkdir(parents=True, exist_ok=True)
    for p in (section(asm, g, out / "psw_section.png"), corner_iso(asm, g, out / "psw_corner_iso.png")):
        print("OK", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
