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
                       Mode, Polyline, Rectangle, RectangleRounded, RegularPolygon, add,
                       extrude, make_face, offset)

from .layout import centered
from .mech import CHOC_STAB_OUTLINE, STAB_KERF, stab_flipped, switch_of

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


def stab_cutout_face(s, at=(0.0, 0.0), kerf=STAB_KERF, flipped=False, polygon=None):
    """スタビ開口の面を、規格の輪郭から kerf だけ外へ広げて返す。

    `polygon` を渡すとその点列を使う（Choc の開口）。無ければ Cherry の 28 点。
    **点列に ±kerf を足さない。**28 点は凹凸が混じり点ごとに外向きが違う（HHKB #30）。
    多角形のオフセットに任せる（INTERSECTION は角を丸めず相似に広げる）。
    """
    pts = polygon if polygon is not None else stab_polygon(s, at=at, flipped=flipped)
    with BuildSketch(mode=Mode.PRIVATE) as sk:
        with BuildLine():
            Polyline(*pts, close=True)
        make_face()
        if kerf:
            offset(amount=kerf, kind=Kind.INTERSECTION)
    return sk.sketch


def choc_stab_polygons(s, at=(0.0, 0.0)):
    """Choc スタビの左右 2 つの開口（mech.CHOC_STAB_OUTLINE・kerf 0）。ワイヤは常に奥。

    プレートに開けるときは Cherry と同じく STAB_KERF だけ外へ広げる（build_plate）。
    """
    ax, ay = at
    right = [(ax + s + x, ay + y) for x, y in CHOC_STAB_OUTLINE]
    left = [(ax - s - x, ay + y) for x, y in reversed(CHOC_STAB_OUTLINE)]
    return [left, right]


def plate_size(spec, keys):
    _, (kw, kh) = centered(keys)
    return kw + spec.PLATE_MARGIN_X * 2, kh + spec.PLATE_MARGIN_Y * 2


def build_plate(spec, keys, piece):
    """1 枚のプレート。返り値は (part, (幅, 奥行), キー中心の並び)。"""
    sw = switch_of(spec)
    positions, _ = centered(keys)
    w, h = plate_size(spec, keys)
    stabs = [(pos, sw.stab_offset_for(k.w_u), stab_flipped(k, keys))
             for pos, k in zip(positions, keys)]
    with BuildPart() as plate:
        with BuildSketch():
            RectangleRounded(w, h, spec.CORNER_R)
            with Locations(*positions):
                Rectangle(sw.cutout, sw.cutout, mode=Mode.SUBTRACT)
            for pos, s, f in stabs:
                if s is None:
                    continue
                if sw.stab_kind == "cherry":
                    add(stab_cutout_face(s, at=pos, flipped=f), mode=Mode.SUBTRACT)
                elif sw.stab_kind == "choc":
                    # Keebio の輪郭は幅がハウジングと同じ 6.30（隙間 0）。刷った PLA では
                    # 締まるので Cherry と同じ STAB_KERF を足す（mech.CHOC_STAB_OUTLINE）
                    for poly in choc_stab_polygons(s, at=pos):
                        add(stab_cutout_face(s, polygon=poly), mode=Mode.SUBTRACT)
                else:
                    raise NotImplementedError(
                        f"{sw.name}: スタビ開口 {sw.stab_kind!r} の形が plate.py に無い")
            for cx, cy, ow, oh in spec.PLATE_OPENINGS[piece]:
                with Locations((cx, cy)):
                    Rectangle(ow, oh, mode=Mode.SUBTRACT)
            mounts = spec.MOUNTS[piece]
            # MOUNT_POCKET_AF があれば、ネジのバカ穴ではなく**ナットの回り止めの六角の穴**
            # （基板の上面に置いた M2 ナットがプレートの中に収まる。CCKB）。二面を ±x に向ける
            af = getattr(spec, "MOUNT_POCKET_AF", None)
            if mounts:
                with Locations(*mounts):
                    if af:
                        RegularPolygon(af / 3 ** 0.5, 6, rotation=30, mode=Mode.SUBTRACT)
                    else:
                        Circle(M2_CLEAR_D / 2, mode=Mode.SUBTRACT)
        extrude(amount=sw.plate_t)
    return plate.part, (w, h), positions


def split_plate(spec, part, piece):
    """PLATE_SPLIT があればプレートを左右に分ける。無ければ [(piece, part)]。

    PLATE_SPLIT[piece] は段ごと（上の段から）の分ける x。段の中は縦に切り、段の境目で
    横に渡る。**x はキーの境目に置く**（スイッチ・スタビの開口を切らない。機種の検査が見る）。
    """
    xs = getattr(spec, "PLATE_SPLIT", {}).get(piece)
    if not xs:
        return [(piece, part)]
    from build123d import Polygon

    bb = part.bounding_box()
    pad = 10.0
    top, bottom = bb.max.Y + pad, bb.min.Y - pad
    n = len(xs)
    step = (bb.max.Y - bb.min.Y - 2 * spec.PLATE_MARGIN_Y) / n     # 段の高さ（1u）
    y0 = bb.max.Y - spec.PLATE_MARGIN_Y
    ys = [top] + [y0 - i * step for i in range(1, n)] + [bottom]
    seam = []
    for i, x in enumerate(xs):
        seam += [(x, ys[i]), (x, ys[i + 1])]
    left_pts = [(bb.min.X - pad, top)] + seam + [(bb.min.X - pad, bottom)]
    with BuildPart() as cutter:
        with BuildSketch():
            Polygon(*left_pts, align=None)
        extrude(amount=bb.max.Z + pad, both=True)
    left = part & cutter.part
    right = part - cutter.part
    return [(f"{piece}_L", left), (f"{piece}_R", right)]


def main(argv):
    from .project import load
    from .verify import render_outline_2d, to_mesh

    p = load(argv[0])
    p.build.mkdir(parents=True, exist_ok=True)
    for piece, keys in p.pieces().items():
        whole, _, _ = build_plate(p.spec, keys, piece)
        for name, part in split_plate(p.spec, whole, piece):
            size = part.bounding_box().size
            w, h = size.X, size.Y
            mesh, stl = to_mesh(part, p.build / f"plate_{name}.stl")
            png = render_outline_2d(part, p.build / f"plate_{name}.png",
                                    title=f"{p.name} plate {name}  {w:.2f} x {h:.2f} mm")
            # **出力を読んでから報告する。**水密でなければ刷れない
            print(f"{'OK' if mesh.is_watertight else 'NG'} {name:6s} "
                  f"{w:7.2f} x {h:6.2f} x {switch_of(p.spec).plate_t}mm 水密={mesh.is_watertight}")
            print(f"   {stl}\n   {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
