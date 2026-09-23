"""スイッチプレートを生成する（build123d）。

外形は「キー領域 + 余白（spec.PLATE_MARGIN_X/Y）」の角丸矩形。穴は MX 開口・
スタビ開口・取付ネジのバカ穴（spec.MOUNTS）。座標は layout.centered と同じ
（キー領域の中心が原点・Y 上向き）。

**傾けて載せる機種は、平面図の奥行が cos(傾き) 倍に縮む。**HHKB ではこの
「平ら／平面図」の取り違えを 3 度踏んだ。ケース側で傾けるときは、プレートの
平らな寸法と平面図の寸法を別の名前で持つこと（docs/knowledge/case-and-print.md）。

    .venv/bin/python3 -m foundry.plate <機種>
"""

from __future__ import annotations

import sys

from build123d import (BuildLine, BuildPart, BuildSketch, Circle, Kind, Locations,
                       Mode, Polyline, Rectangle, RectangleRounded, add, extrude,
                       make_face, offset)

from .layout import centered
from .mech import PLATE_T, STAB_KERF, SWITCH_CUTOUT, stab_flipped, stab_offset_for

M2_CLEAR_D = 2.4         # M2 のバカ穴（0.4 の逃げ）


def stab_polygon(s, at=(0.0, 0.0), flipped=False):
    """半間隔 s の Cherry スタビ開口（28 点・kerf 0）を中心 `at` に置いた点列。

    出典: swillkb の実装 swill/kad key.go DrawCherryStab。**係数の並びを変えない**
    （組み立て直すと間違える）。swillkb は Y 下向きなので符号を反転する。
    平行移動は自分で行う（BuildLine の中身には Locations が効かず、全開口が
    原点に重なった）。
    """
    pts = [
        (s - 3.375, -2.3), (s - 3.375, -5.53), (s + 3.375, -5.53),
        (s + 3.375, -2.3), (s + 4.2, -2.3), (s + 4.2, 0.5),
        (s + 3.375, 0.5), (s + 3.375, 6.77), (s + 1.65, 6.77),
        (s + 1.65, 7.97), (s - 1.65, 7.97), (s - 1.65, 6.77),
        (s - 3.375, 6.77), (s - 3.375, 2.3), (-s + 3.375, 2.3),
        (-s + 3.375, 6.77), (-s + 1.65, 6.77), (-s + 1.65, 7.97),
        (-s - 1.65, 7.97), (-s - 1.65, 6.77), (-s - 3.375, 6.77),
        (-s - 3.375, 0.5), (-s - 4.2, 0.5), (-s - 4.2, -2.3),
        (-s - 3.375, -2.3), (-s - 3.375, -5.53), (-s + 3.375, -5.53),
        (-s + 3.375, -2.3),
    ]
    ax, ay = at
    if flipped:
        return [(ax - x, ay + y) for x, y in pts]
    return [(ax + x, ay - y) for x, y in pts]


def stab_cutout_face(s, at=(0.0, 0.0), kerf=STAB_KERF, flipped=False):
    """スタビ開口の面を、規格の輪郭から kerf だけ外へ広げて返す。

    **点列に ±kerf を足さない。**28 点は凹凸が混じり点ごとに外向きが違う（HHKB #30）。
    多角形のオフセットに任せる（INTERSECTION は角を丸めず相似に広げる）。
    """
    with BuildSketch(mode=Mode.PRIVATE) as sk:
        with BuildLine():
            Polyline(*stab_polygon(s, at=at, flipped=flipped), close=True)
        make_face()
        if kerf:
            offset(amount=kerf, kind=Kind.INTERSECTION)
    return sk.sketch


def plate_size(spec, keys):
    _, (kw, kh) = centered(keys)
    return kw + spec.PLATE_MARGIN_X * 2, kh + spec.PLATE_MARGIN_Y * 2


def build_plate(spec, keys, piece):
    """1 枚のプレート。返り値は (part, (幅, 奥行), キー中心の並び)。"""
    positions, _ = centered(keys)
    w, h = plate_size(spec, keys)
    stabs = [(pos, stab_offset_for(k.w_u), stab_flipped(k, keys))
             for pos, k in zip(positions, keys)]
    with BuildPart() as plate:
        with BuildSketch():
            RectangleRounded(w, h, spec.CORNER_R)
            with Locations(*positions):
                Rectangle(SWITCH_CUTOUT, SWITCH_CUTOUT, mode=Mode.SUBTRACT)
            for pos, s, f in stabs:
                if s is not None:
                    add(stab_cutout_face(s, at=pos, flipped=f), mode=Mode.SUBTRACT)
            mounts = spec.MOUNTS[piece]
            if mounts:
                with Locations(*mounts):
                    Circle(M2_CLEAR_D / 2, mode=Mode.SUBTRACT)
        extrude(amount=PLATE_T)
    return plate.part, (w, h), positions


def main(argv):
    from .project import load
    from .verify import render_outline_2d, to_mesh

    p = load(argv[0])
    p.build.mkdir(parents=True, exist_ok=True)
    for piece, keys in p.pieces().items():
        part, (w, h), _ = build_plate(p.spec, keys, piece)
        mesh, stl = to_mesh(part, p.build / f"plate_{piece}.stl")
        png = render_outline_2d(part, p.build / f"plate_{piece}.png",
                                title=f"{p.name} plate {piece}  {w:.2f} x {h:.2f} mm")
        # **出力を読んでから報告する。**水密でなければ刷れない
        print(f"{'OK' if mesh.is_watertight else 'NG'} {piece:6s} {len(keys):3d} keys "
              f"{w:7.2f} x {h:6.2f} x {PLATE_T}mm 水密={mesh.is_watertight}")
        print(f"   {stl}\n   {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
