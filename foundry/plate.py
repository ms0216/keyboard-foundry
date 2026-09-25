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

from build123d import (BuildLine, BuildPart, BuildSketch, Circle, Compound, Kind, Locations,
                       Mode, Polygon, Polyline, Rectangle, RectangleRounded, RegularPolygon, add,
                       extrude, make_face, offset)

from .layout import centered
from .mech import (CHOC_STAB_OUTLINE, STAB_KERF, choc_v2_stab_plate_polys, stab_flipped,
                   switch_of)

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


def choc_v2_stab_polygons(at=(0.0, 0.0), outline=None, web=0.0):
    """Choc V2 のねじ留めスタビの左右 2 つの開口（mech.choc_v2_stab_plate_polys・kerf 0）。ワイヤは常に奥。

    輪郭はキーの中心が原点（支点ではない）。プレートに開けるときは STAB_KERF だけ外へ広げる（build_plate）。
    outline・web を渡すと、外形まで web 未満の辺を外形の外まで伸ばす。
    """
    return choc_v2_stab_plate_polys(at, outline, web, STAB_KERF)


def thin_webs(part, web, min_area=0.1):
    """板の中で幅 web 未満の所（2 つの穴・穴と外形の間の帯、細い突起）を返す。

    上を向いた面ごとに、形を web/2 だけ縮めてから戻す（opening）。幅 web 未満の所は縮めたときに消えて
    戻らない。消えた所のうち面積が min_area を超える物を数える。**凸の角も丸まって削れる**が、
    90° の角の削れは (1 − π/4)(web/2)² = 0.077mm²（web 1.2）で min_area 未満になる。
    返り値 [(面積, (x, y), (X の幅, Y の幅))]。幅 web ちょうどの帯は通す（縮める量を 0.005 減らす）。
    """
    from build123d import Axis, Kind, offset

    top = part.bounding_box().max.Z
    faces = [f for f in part.faces().filter_by(Axis.Z) if abs(f.center().Z - top) < 1e-6]
    out = []
    r = web / 2 - 0.005
    for face in faces:
        opened = offset(offset(face, amount=-r, kind=Kind.ARC), amount=r, kind=Kind.ARC)
        lost = face - opened
        for f in (lost.faces() if hasattr(lost, "faces") else []):
            if f.area > min_area:
                c, bb = f.center(), f.bounding_box()
                out.append((round(f.area, 3), (round(c.X, 2), round(c.Y, 2)),
                            (round(bb.size.X, 2), round(bb.size.Y, 2))))
    return sorted(out, key=lambda t: -t[0])


def _frame_solids(spec, keys, part):
    """part の立体のうち、スタビのキーのスイッチの枠（羽が外形まで抜けて切り離された、開口の手前の板と桟）。

    [(キーの名前, 立体)]。枠かどうかは、そのキーの開口の手前 0.5 の点を含むかで見る。
    **いちばん大きい立体（板）は枠にしない。**それ以外の浮いた立体は枠に数えない（板に残り、
    tests/test_cckb.py の「1 つの立体」が落とす）。
    """
    from build123d import Vector

    sols = list(part.solids())
    if len(sols) < 2:
        return []
    main = max(sols, key=lambda s: s.volume)
    sw = switch_of(spec)
    positions, _ = centered(keys)
    out = []
    for (x, y), k in zip(positions, keys):
        if sw.stab_offset_for(k.w_u) is None:
            continue
        probe = Vector(x, y - sw.cutout / 2 - 0.5, sw.plate_t / 2)
        for s in sols:
            if s is not main and s.is_inside(probe) and all(s is not f for _, f in out):
                out.append((k.label, s))
    return out


def plate_frames(spec, keys, piece):
    """スタビのキーのうち、羽が外形まで抜けて板から切り離されたスイッチの枠。**別に刷る部品**。

    [(キーの名前, 立体)]（組み立ての位置・z 0〜plate_t）。スイッチの ±x の辺の爪 4 つとつばが挟んで留める
    （CCKB ではスペースの 2 キー。決定記録 2026-09-25-choc-v2 §10-6）。
    """
    part, _, _ = _build_whole(spec, keys, piece)
    return _frame_solids(spec, keys, part)


def frames_for_print(frames, gap=3.0):
    """枠を刷る向き（組み立てと同じ・板の下面をベッドに）で横に並べた 1 つの Compound。"""
    from build123d import Pos

    placed, x = [], 0.0
    for _, f in frames:
        bb = f.bounding_box()
        placed.append(Pos(x - bb.min.X, -bb.min.Y, -bb.min.Z) * f)
        x += bb.size.X + gap
    return Compound(placed)


def plate_size(spec, keys):
    _, (kw, kh) = centered(keys)
    return kw + spec.PLATE_MARGIN_X * 2, kh + spec.PLATE_MARGIN_Y * 2


def build_plate(spec, keys, piece):
    """1 枚のプレート。返り値は (part, (幅, 奥行), キー中心の並び)。

    スタビの羽が外形まで抜けて切り離されたスイッチの枠は**含めない**（plate_frames が別の部品として返す）。
    """
    part, size, positions = _build_whole(spec, keys, piece)
    frames = _frame_solids(spec, keys, part)
    if frames:
        rest = [s for s in part.solids() if not any(s.wrapped.IsSame(f.wrapped) for _, f in frames)]
        part = rest[0] if len(rest) == 1 else Compound(rest)
    return part, size, positions


def _build_whole(spec, keys, piece):
    """プレートの立体（枠も含む）。"""
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
                elif sw.stab_kind == "choc_v2_screw":
                    # スタビは基板にねじで留まり、プレートには掛からない。本体・ワイヤが通る穴を開ける
                    # （輪郭はキーの中心から。支点の半間隔 s は輪郭に織り込み済みで、検査が見る）
                    for poly in choc_v2_stab_polygons(at=pos, outline=(-w / 2, -h / 2, w / 2, h / 2),
                                                      web=spec.PLATE_MIN_WEB):
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


def split_plate(spec, part, piece, keys):
    """PLATE_SPLIT があればプレートを左右に分ける。無ければ [(piece, part)]。

    PLATE_SPLIT[piece] は段ごと（上の段から）の分ける x。段の中は縦に切り、段の境目で
    横に渡る。**x はキーの境目に置く**（スイッチ・スタビの開口を切らない。機種の検査が見る）。

    段の数と高さは keys（その部品のキー）から数え、外形から割り出した段の高さと合わなければ
    落とす。前は個数を段数とみなして黙って別の所で切った（最終レビュー M1）。
    """
    xs = getattr(spec, "PLATE_SPLIT", {}).get(piece)
    if not xs:
        return [(piece, part)]
    rows = sorted({round(k.y_mm, 4) for k in keys})
    if len(xs) != len(rows):
        raise ValueError(f"PLATE_SPLIT[{piece!r}] は {len(xs)} 個、キーの段は {len(rows)} 段")

    bb = part.bounding_box()
    pad = 10.0
    top, bottom = bb.max.Y + pad, bb.min.Y - pad
    n = len(xs)
    step = (bb.max.Y - bb.min.Y - 2 * spec.PLATE_MARGIN_Y) / n     # 段の高さ（1u）
    pitches = {round(b - a, 4) for a, b in zip(rows, rows[1:])}
    if pitches and pitches != {round(step, 4)}:
        raise ValueError(f"{piece}: 外形から割り出した段の高さ {step:.4f} がキーの段の間隔 {sorted(pitches)} と違う"
                         "（外形が段の外に張り出している）")
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
    bad = 0
    for piece, keys in p.pieces().items():
        whole, _, _ = build_plate(p.spec, keys, piece)
        print(f"{piece}: キー {len(keys)}")          # 数を見る（HHKB で使っていた情報。M11）
        for name, part in split_plate(p.spec, whole, piece, keys):
            size = part.bounding_box().size
            w, h = size.X, size.Y
            mesh, stl = to_mesh(part, p.build / f"plate_{name}.stl")
            png = render_outline_2d(part, p.build / f"plate_{name}.png",
                                    title=f"{p.name} plate {name}  {w:.2f} x {h:.2f} mm")
            # **出力を読んでから報告する。**水密でなければ刷れない
            print(f"{'OK' if mesh.is_watertight else 'NG'} {name:6s} "
                  f"{w:7.2f} x {h:6.2f} x {switch_of(p.spec).plate_t}mm 水密={mesh.is_watertight}")
            print(f"   {stl}\n   {png}")
            bad += not mesh.is_watertight
        frames = plate_frames(p.spec, keys, piece)
        if frames:
            part = frames_for_print(frames)
            mesh, stl = to_mesh(part, p.build / f"plate_frames_{piece}.stl")
            png = render_outline_2d(part, p.build / f"plate_frames_{piece}.png",
                                    title=f"{p.name} plate frames {piece}  ({', '.join(n for n, _ in frames)})")
            print(f"{'OK' if mesh.is_watertight else 'NG'} 枠 {len(frames)} 個（{', '.join(n for n, _ in frames)}）"
                  f" 水密={mesh.is_watertight}")
            print(f"   {stl}\n   {png}")
            bad += not mesh.is_watertight
    return 1 if bad else 0          # NG を print だけにしない（スクリプトから判定できるように）


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
