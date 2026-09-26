"""試し刷りの小片（公差のクーポン）。**本番の部品を刷る前に刷る。**

「未実測なら先に公差のクーポン」（docs/knowledge/case-and-print.md）。どれも本番と同じ厚さ・
同じ向きで刷り、本番の部品（スイッチ・スタビ・ナット・インサート・M2 ネジ）をはめて選ぶ。
**どの穴かは縁の切り欠きの数で見分ける**（1 本目 = 表の最初の値）。

  coupon_switch  プレート 1.2 にスイッチの開口 13.90 / 13.95 / 14.00 / 14.05（V2 の爪が掛かって抜けないか）
  coupon_stab    プレート 1.2 に V2 のスタビの U 字の開口（支点 ±11.9）＋スイッチの開口。広げ 0.05 / 0.15 / 0.25 の 3 枚
                 （スタビはプレートに掛からない。基板に留めたスタビの本体・ワイヤが開口に触れないかを見る）
  coupon_stem    キャップの受け口（十字の筒）。1 段目: 十字の穴の幅 1.35〜1.50（列・手前の切り欠き 1〜4 本）×
                 長さ 4.10〜4.20（行・左の切り欠き 1〜3 本）の格子 12 本。2 段目: 筒の外径 5.3 / 5.4 / 5.5 の小さな
                 天板 3 枚（切り欠き 1〜3 本。こじって外し、腕の先が割れないか）と、スタビの受け口の板 2 枚
                 （支点の間 24.0 = 切り欠き 1 本・23.8 = 2 本。届いたスタビの軸に同時に挿さる方。本番は 23.8）
  coupon_stab_return  **スタビの軸がキャップと一緒に戻るか**（2026-09-26・監査 E 重要 1）。基板の代わりの板（厚さ
                 spec.PCB_T・本番の基板と同じ穴の位置。刷った穴は COUPON_BOARD_HOLE_CLEAR だけ広げる）と、本番の
                 2.25u のキャップ 1 個。板にスタビをねじで留め、スイッチを挿し、キャップを挿して押し切って離す。
                 スタビの両端の軸が、スイッチのばねで戻るキャップと一緒に上まで戻るか（10 回）。台が箱の口に
                 当たらないか（押し切りで擦れる音・引っ掛かり）
  coupon_nut     プレート 1.2 に M2 ナットの六角の穴 4.1 / 4.2 / 4.3（落ちて入り、回らないか）
  coupon_insert  インサートの柱 φ5.2（下穴 2.9 / 3.0 / 3.1）と、ネジを捕まえる膜（穴 1.4 / 1.6 / 1.8）
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from build123d import Compound, Pos, Rot, extrude  # noqa: E402

import case_spec as CS  # noqa: E402
from case import box, cyl, fuse, hex_prism  # noqa: E402
from foundry.layout import UNIT  # noqa: E402
from foundry.mech import CHOC_V2  # noqa: E402
from foundry.plate import M2_CLEAR_D, choc_v2_stab_polygons, stab_cutout_face  # noqa: E402


def notches(part, n, x0, y_edge, t, depth=1.0, w=0.8, pitch=2.0):
    """縁（y = y_edge の手前の辺）に n 本の切り欠き。"""
    for k in range(n):
        x = x0 + k * pitch
        part = part - box(x, y_edge - 1, -1, x + w, y_edge + depth, t + 1)
    return part


def row(parts, gap):
    """立体を x に並べて 1 つの Compound にする（1 つの STL で刷る）。"""
    out, x = [], 0.0
    for p in parts:
        bb = p.bounding_box()
        out.append(Pos(x - bb.min.X, -bb.min.Y, -bb.min.Z) * p)
        x += bb.size.X + gap
    return Compound(out)


def switch_coupon(cs=CS, sw=CHOC_V2):
    t = sw.plate_t
    n = len(cs.COUPON_SWITCH_CUTOUTS)
    w, d = n * UNIT, UNIT
    part = box(0, 0, 0, w, d, t)
    for k, c in enumerate(cs.COUPON_SWITCH_CUTOUTS):
        x = (k + 0.5) * UNIT
        part = part - box(x - c / 2, d / 2 - c / 2, -1, x + c / 2, d / 2 + c / 2, t + 1)
        part = notches(part, k + 1, x - 3, 0.0, t)
    return part


def stab_coupon(kerf, idx, cs=CS, sw=CHOC_V2):
    """V2 のスタビのプレートの開口（U 字・羽 2 つ・ワイヤの帯）とスイッチの開口。周りに 3.0 の板。"""
    t = sw.plate_t
    polys = choc_v2_stab_polygons()
    xs = [x for poly in polys for x, _ in poly]
    ys = [y for poly in polys for _, y in poly]
    m = 3.0
    x0, x1, y0, y1 = min(xs) - m, max(xs) + m, min(ys) - m, max(ys) + m
    part = box(x0, y0, 0, x1, y1, t)
    part = part - box(-sw.cutout / 2, -sw.cutout / 2, -1, sw.cutout / 2, sw.cutout / 2, t + 1)
    for poly in polys:
        face = stab_cutout_face(0.0, polygon=poly, kerf=kerf)
        part = part - Pos(0, 0, -1) * extrude(face, t + 2)
    return notches(part, idx + 1, x0 + 2, y0, t)


def side_notches(part, n, x_edge, y0, t, depth=1.0, w=0.8, pitch=2.0):
    """左の縁（x = x_edge）に n 本の切り欠き。"""
    for k in range(n):
        y = y0 + k * pitch
        part = part - box(x_edge - 1, y, -1, x_edge + depth, y + w, t + 1)
    return part


def stem_grid(cs=CS, spec=None):
    """十字の穴の幅（列）× 長さ（行）の格子。筒は本番の外径・長さ。天板の厚さは本番と同じ。"""
    import keycaps

    t = spec.KEYCAP_TOP_T
    pitch, m = 8.0, 3.0
    nx, ny = len(cs.COUPON_CROSS_WIDTHS), len(cs.COUPON_CROSS_LENGTHS)
    w, d = nx * pitch + 2 * m, ny * pitch + 2 * m
    part = box(0, 0, 0, w, d, t)
    tubes, holes = [], []
    for i, cw in enumerate(cs.COUPON_CROSS_WIDTHS):
        for j, cl in enumerate(cs.COUPON_CROSS_LENGTHS):
            x, y = m + (i + 0.5) * pitch, m + (j + 0.5) * pitch
            tubes.append(Pos(x, y, 0) * keycaps.switch_socket(cs))
            holes += [Pos(x, y, 0) * q for q in keycaps.cross(0.0, -cs.STEM_TUBE_L - 1, 0.0, (cl, cw))]
    part = fuse([part] + tubes) - fuse(holes)
    for i in range(nx):
        part = notches(part, i + 1, m + i * pitch + 1.0, 0.0, t, pitch=1.4, w=0.6)
    for j in range(ny):
        part = side_notches(part, j + 1, 0.0, m + j * pitch + 1.0, t, pitch=1.4, w=0.6)
    return Rot(180, 0, 0) * part.clean()          # 天板をベッドに（本番のキャップと同じ向き）


def stem_coupon(od, idx, cs=CS, spec=None):
    """筒の外径 od の小さな天板（14 角・本番の十字の穴・つばの窪み）。こじって外す試しにも使う。"""
    import keycaps

    t = spec.KEYCAP_TOP_T
    a = 14.0
    part = fuse([box(-a / 2, -a / 2, 0, a / 2, a / 2, t), keycaps.switch_socket(cs, od=od)])
    part = part - fuse(keycaps.socket_holes(spec, cs))
    part = notches(part, idx + 1, -a / 2 + 1.5, -a / 2, t)
    return Rot(180, 0, 0) * part.clean()


def stab_cap_coupon(pivot, idx, cs=CS, spec=None):
    """スタビの受け口 2 つ（±pivot）とスイッチの筒を 1 枚の天板に（2.25u のキャップの中央の帯）。"""
    import keycaps

    t = spec.KEYCAP_TOP_T
    w, d = 2 * pivot + cs.STAB_SOCKET_BOSS_D + 4.0, 10.0
    xs = (-pivot, pivot)
    part = fuse([box(-w / 2, -d / 2, 0, w / 2, d / 2, t), keycaps.switch_socket(cs)]
                + keycaps.stab_bosses(xs, spec, cs))
    part = part - fuse(keycaps.socket_holes(spec, cs, stab_xs=xs))
    part = notches(part, idx + 1, -w / 2 + 1.5, -d / 2, t)
    return Rot(180, 0, 0) * part.clean()


def board_standin(ifc, cs=CS):
    """基板の代わりの板（2.25u のキー 1 つ分・厚さ spec.PCB_T）。穴は**発注する基板と同じ位置**:
    スイッチの中心・端子 2・位置決め（lib の足跡を interface.switch_holes が読んだ物）、スタビの箱の穴・ねじ・爪
    （interface.stab_reliefs・stab_holes をキーの中心へ戻した物）。刷った穴は締まるので COUPON_BOARD_HOLE_CLEAR だけ広げる。"""
    from interface import poly_box

    s = ifc.s
    t = s.PCB_T
    c = cs.COUPON_BOARD_HOLE_CLEAR
    kx, ky = next((x, y) for (x, y), k in zip(ifc.positions, ifc.keys) if k.w_u == 2.25)
    w = 2.25 * UNIT
    part = box(-w / 2, -UNIT / 2 - 1.0, 0, w / 2, UNIT / 2 + 3.5, t)
    x0, y0 = ifc.matrix_positions()[0]
    holes = [cyl(hx - x0, hy - y0, -1, t + 1, max(hw, hh) + 2 * c)
             for ref, _, (hx, hy), (hw, hh) in ifc.switch_holes() if ref == "SW1"]
    for kind, (hx, hy), d in ifc.stab_holes():
        if abs(hy - ky) < UNIT / 2 and abs(hx - kx) < w / 2:
            holes.append(cyl(hx - kx, hy - ky, -1, t + 1, d + 2 * c))
    for poly in ifc.stab_reliefs():
        bx0, by0, bx1, by1 = poly_box(poly)
        if abs((by0 + by1) / 2 - ky) < 1e-6 and abs((bx0 + bx1) / 2 - kx) < w / 2:
            holes.append(box(bx0 - kx - c, by0 - ky - c, -1, bx1 - kx + c, by1 - ky + c, t + 1))
    assert len(holes) == 4 + 4 + 2, len(holes)
    return (part - fuse(holes)).clean()


def stab_return_coupon(ifc, cs=CS):
    """基板の代わりの板と、本番の 2.25u のキャップ（天板をベッドに）を並べた物。"""
    import keycaps

    cap = Rot(180, 0, 0) * keycaps.keycap(2.25, ifc.s, ifc.sw, cs)
    return row([board_standin(ifc, cs), cap], cs.COUPON_GAP)


def stack(rows, gap):
    """行（Compound）を y に積む。"""
    out, y = [], 0.0
    for r in rows:
        bb = r.bounding_box()
        out.append(Pos(-bb.min.X, y - bb.min.Y, -bb.min.Z) * r)
        y += bb.size.Y + gap
    return Compound(out)


def nut_coupon(cs=CS, sw=CHOC_V2):
    t = sw.plate_t
    n = len(cs.COUPON_NUT_AFS)
    pitch = 10.0
    part = box(0, 0, 0, n * pitch, 10.0, t)
    for k, af in enumerate(cs.COUPON_NUT_AFS):
        part = part - hex_prism((k + 0.5) * pitch, 5.0, af, -1, t + 1)
        part = notches(part, k + 1, k * pitch + 1.0, 0.0, t, pitch=1.6)
    return part


def insert_coupon(spec, cs=CS):
    """床（spec.CASE_FLOOR）の上に、柱（下穴を比べる）と、膜のボス（ネジを捕まえる穴を比べる）。"""
    base_t = spec.CASE_FLOOR
    pitch = 9.0
    n = len(cs.COUPON_INSERT_HOLES) + len(cs.COUPON_CAPTIVE_HOLES)
    part = box(0, 0, 0, n * pitch, 10.0, base_t)
    h = cs.INSERT_L + cs.INSERT_HOLE_EXTRA + 1.0
    for k, hd in enumerate(cs.COUPON_INSERT_HOLES):
        x = (k + 0.5) * pitch
        part = part.fuse(cyl(x, 5.0, base_t - 0.1, base_t + h, spec.LID_PILLAR_D))
        part = part - cyl(x, 5.0, base_t + h - cs.INSERT_L - cs.INSERT_HOLE_EXTRA, base_t + h + 1, hd)
        part = notches(part, k + 1, k * pitch + 1.0, 0.0, base_t, pitch=1.6)
    # 膜: 本番（右のふたを天板を下に刷る）と同じく、ベッド側から φ2.4 の穴、上端に膜
    web_h = cs.LID_BOSS_H + spec.LID_T
    for j, hd in enumerate(cs.COUPON_CAPTIVE_HOLES):
        k = len(cs.COUPON_INSERT_HOLES) + j
        x = (k + 0.5) * pitch
        part = part.fuse(cyl(x, 5.0, 0, web_h, spec.LID_PILLAR_D))
        part = part - cyl(x, 5.0, -1, web_h - cs.CAPTIVE_WEB_T, M2_CLEAR_D)
        part = part - cyl(x, 5.0, web_h - cs.CAPTIVE_WEB_T - 0.01, web_h + 1, hd)
        part = notches(part, j + 1, k * pitch + 1.0, 0.0, base_t, pitch=1.6)
    return part.clean()


def parts(ifc=None, cs=CS):
    import interface as I

    ifc = ifc or I.Interface()
    s = ifc.s
    return {
        "coupon_switch": switch_coupon(cs, ifc.sw),
        "coupon_stab": row([stab_coupon(k, i, cs, ifc.sw)
                            for i, k in enumerate(cs.COUPON_STAB_KERFS)], cs.COUPON_GAP),
        "coupon_stem": stack([row([stem_grid(cs, s)], cs.COUPON_GAP),
                              row([stem_coupon(od, i, cs, s) for i, od in enumerate(cs.COUPON_TUBE_ODS)]
                                  + [stab_cap_coupon(pv, i, cs, s) for i, pv in enumerate(cs.COUPON_STAB_PIVOTS)],
                                  cs.COUPON_GAP)], cs.COUPON_GAP),
        "coupon_stab_return": stab_return_coupon(ifc, cs),
        "coupon_nut": nut_coupon(cs, ifc.sw),
        "coupon_insert": insert_coupon(s, cs),
    }
